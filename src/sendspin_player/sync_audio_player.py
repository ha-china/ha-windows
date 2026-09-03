"""SyncAudioPlayer: PortAudio callback-mode synchronized playback.

Sendspin official design: the DAC clock drives playback. sounddevice runs a
callback on the PortAudio thread and `time_info.outputBufferDacTime` tells us
exactly when the output buffer reaches the speaker. Incoming chunks carry the
server timeline; `compute_play_time` maps it onto the shared loop clock. The
callback compares the mapped DAC moment against each chunk's scheduled play
instant and writes real PCM only when due - silence otherwise. A server-time
cursor plus smooth cursor correction keeps the audio permanently inside the
target skew window (no monotonically growing backlog).
"""
from __future__ import annotations

import logging
import queue
from typing import Callable, Optional

from aiosendspin.client.time_sync import SendspinTimeFilter

logger = logging.getLogger(__name__)

# PCM format (must match the ClientHello supported format advertised upstream).
SAMPLE_RATE = 48000
CHANNELS = 2
BIT_DEPTH = 16
_BYTES_PER_FRAME = CHANNELS * (BIT_DEPTH // 8)   # 4 bytes / frame (int16 stereo)


class SyncAudioPlayer:
    """PortAudio callback-mode player aligned to the server timeline."""

    _MIN_CHUNKS_TO_START = 16        # buffer this many chunks before first sound
    _BLOCKSIZE = 2048                # PortAudio frames per callback (~42 ms @ 48 kHz)
    _CORRECTION_DEADBAND_US = 2000   # ignore skew below this
    _REANCHOR_THRESHOLD_US = 500000  # reset cursor if skew exceeds this
    _REANCHOR_COOLDOWN_US = 5000000

    def __init__(
        self,
        compute_play_time: Callable[[int], int],
        now_us: Callable[[], int],
        is_synced: Callable[[], bool],
        on_skew: Callable[[int, bool], None],
    ) -> None:
        self._compute_play_time = compute_play_time
        self._now_us = now_us
        self._is_synced = is_synced
        self._on_skew = on_skew
        self._queue: "queue.Queue[tuple[int, bytes]]" = queue.Queue()
        self._leftover: Optional[tuple[int, bytes]] = None  # partial chunk tail
        self._stream = None
        self._started = False
        self._dac_loop_samples: list[tuple[float, float]] = []
        self._dac_loop_ratio = 1.0
        self._cursor_us = 0
        self._cursor_rem_us = 0   # sub-µs remainder for exact sample pacing
        self._first_ts: Optional[int] = None
        self._has_played = False
        self._last_reanchor_loop = 0
        self._frames_since_report = 0
        self._sync_filter = SendspinTimeFilter(process_std_dev=0.01, forget_factor=1.01)

    # ------------------------------------------------------------- lifecycle

    def start(self) -> None:
        if self._stream is not None:
            return
        import sounddevice as sd

        self._stream = sd.RawOutputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=self._BLOCKSIZE,
            callback=self._audio_callback,
            latency="high",
        )
        self._stream.start()
        self._started = True
        logger.info("SyncAudioPlayer: stream started (blocksize=%d, latency=high)",
                    self._BLOCKSIZE)

    def stop(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                logger.debug(f"SyncAudioPlayer stop error: {e}")
            self._stream = None
        self._started = False
        self._drain()
        self._leftover = None
        self._cursor_us = 0
        self._cursor_rem_us = 0
        self._first_ts = None
        self._has_played = False

    def enqueue(self, server_timestamp_us: int, data: bytes) -> None:
        """Queue a PCM chunk (any thread)."""
        if not self._started or self._stream is None:
            return
        if self._first_ts is None:
            self._first_ts = server_timestamp_us
            # NOTE: the cursor lives in the LOCAL loop-clock domain; it is
            # anchored in the callback via compute_play_time(first_ts).
            # Never seed it with the raw server timestamp (epoch µs) or the
            # reported skew becomes a ~2 billion ms garbage value.
        self._queue.put((server_timestamp_us, data))
        # Bound: the cap must stay ABOVE the startup gate (16 chunks) or the
        # gate can never be reached and playback stays silent forever.
        while self._queue.qsize() > 64:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def is_ready(self) -> bool:
        return self._started and self._stream is not None

    # ------------------------------------------------------------ callback

    def _audio_callback(self, outdata, frames, time_info, status) -> None:
        """PortAudio callback: write PCM when the server timeline is due."""
        # Default: silence for this block
        outdata[:] = b"\x00" * len(outdata)
        if time_info is None or getattr(time_info, "outputBufferDacTime", None) is None:
            return
        loop_us = self._dac_to_loop_us(time_info.outputBufferDacTime)
        if status and getattr(status, "output_underrun", False):
            if self._first_ts is not None:
                self._cursor_us = self._compute_play_time(self._first_ts)
                logger.debug("SyncAudioPlayer: underrun, re-cursor")

        # Startup gate: wait until enough chunks are buffered to absorb jitter
        if not self._has_played:
            if self._queue.qsize() < self._MIN_CHUNKS_TO_START:
                self._notify_skew(loop_us)
                return
            if self._first_ts is not None:
                self._cursor_us = self._compute_play_time(self._first_ts)
            self._has_played = True
            self._last_reanchor_loop = loop_us
            logger.info("SyncAudioPlayer: starting after %d buffered chunks",
                        self._queue.qsize())

        # Underflow guard: keep consuming while there is any audio
        if not self._queue.empty() or self._leftover is not None:
            self._consume(outdata, frames, loop_us)

        # Smooth skew correction (bounded)
        self._apply_correction(loop_us)
        self._notify_skew(loop_us)

    def _consume(self, outdata, frames: int, loop_us: int) -> None:
        """Copy as many due samples as possible into the output buffer."""
        out_pos = 0
        samples_needed = frames
        while samples_needed > 0:
            # 1) Finish a partial chunk left over from the previous callback.
            if self._leftover is not None:
                _ts, data = self._leftover
                chunk_samples = len(data) // _BYTES_PER_FRAME
                take = min(chunk_samples, samples_needed)
                take_bytes = take * _BYTES_PER_FRAME
                outdata[out_pos:out_pos + take_bytes] = data[:take_bytes]
                out_pos += take_bytes
                samples_needed -= take
                self._advance_cursor(take)
                if take < chunk_samples:
                    # Still more in this chunk; buffer is full for this call.
                    self._leftover = (_ts, data[take_bytes:])
                    return
                self._leftover = None
                continue
            # 2) Pull the next queued chunk. Peek first so future-scheduled
            #    chunks stay queued until their play instant arrives.
            if self._queue.empty():
                break
            ts, data = self._queue.queue[0]
            play_at_us = self._compute_play_time(ts)
            if play_at_us > loop_us:
                break  # not due yet - the rest stays silence
            self._queue.get_nowait()
            chunk_samples = len(data) // _BYTES_PER_FRAME
            take = min(chunk_samples, samples_needed)
            take_bytes = take * _BYTES_PER_FRAME
            outdata[out_pos:out_pos + take_bytes] = data[:take_bytes]
            out_pos += take_bytes
            samples_needed -= take
            self._advance_cursor(take)
            if take < chunk_samples:
                self._leftover = (ts, data[take_bytes:])
        # remainder stays silence (already zeroed)

    def _advance_cursor(self, samples: int) -> None:
        """Advance the loop-clock cursor by exactly `samples` frames.

        1e6/48000 = 20.833... us per sample; integer division truncates to 20,
        which drifts ~40 ms per second - keep the sub-µs remainder.
        """
        self._cursor_rem_us += samples * 1_000_000
        whole_us = self._cursor_rem_us // SAMPLE_RATE
        self._cursor_us += whole_us
        self._cursor_rem_us -= whole_us * SAMPLE_RATE

    # -------------------------------------------------------------- clock map

    def _dac_to_loop_us(self, dac_sec: float) -> int:
        """Map DAC clock seconds onto the loop clock (calibrated ratio).

        The first callback anchors the mapping immediately (DAC moment == the
        loop time observed right now); later callbacks refine the drift ratio
        from the accumulated sample pairs.
        """
        now_loop = self._now_us()
        if not self._dac_loop_samples:
            # Anchor now: at this loop instant, the DAC clock reads dac_sec.
            self._dac_loop_samples = [(dac_sec, float(now_loop))]
            return now_loop
        t0, l0 = self._dac_loop_samples[0]
        mapped = l0 + (dac_sec - t0) * self._dac_loop_ratio * 1_000_000
        # Refine: track the newest pair to follow ratio drift over time.
        t_last, l_last = self._dac_loop_samples[-1]
        if dac_sec - t_last > 0.05:  # every ~50 ms of DAC progress
            r = (now_loop - l_last) / ((dac_sec - t_last) * 1_000_000)
            if 0.999 <= r <= 1.001:
                self._dac_loop_ratio = r
            self._dac_loop_samples.append((dac_sec, float(now_loop)))
            if len(self._dac_loop_samples) > 64:
                self._dac_loop_samples = self._dac_loop_samples[-32:]
        return int(mapped)

    # ------------------------------------------------------------- correction

    def _apply_correction(self, loop_us: int) -> None:
        """Smoothly absorb drift: nudge the cursor toward the DAC moment."""
        if self._first_ts is None:
            return
        # Compare the cursor (next frame's play instant) with the actual
        # playback position (DAC-mapped loop time).
        err = self._cursor_us - loop_us
        if abs(err) > self._REANCHOR_THRESHOLD_US:
            now = self._now_us()
            if now - self._last_reanchor_loop > self._REANCHOR_COOLDOWN_US:
                self._cursor_us = self._compute_play_time(self._first_ts)
                self._last_reanchor_loop = now
                logger.info("SyncAudioPlayer: re-anchored (skew %d ms)", err // 1000)
                return
        if abs(err) < self._CORRECTION_DEADBAND_US:
            return
        # Feed the filter for smoothing, then nudge incrementally
        self._sync_filter.update(err, 0, loop_us)
        filtered = self._sync_filter.offset
        if abs(filtered) > self._CORRECTION_DEADBAND_US:
            self._cursor_us -= err // 50  # gradual: 2% per callback, bounded

    # --------------------------------------------------------------- report

    def _notify_skew(self, loop_us: int) -> None:
        """Report bounded skew (cursor vs DAC moment), ms.

        Only after playback started: before that the cursor is unanchored
        (0), and skew would read as the whole machine uptime in negative ms.
        """
        if not self._has_played or self._stream is None:
            return
        self._frames_since_report += 1
        if self._frames_since_report < 16:
            return
        self._frames_since_report = 0
        skew_ms = int((self._cursor_us - loop_us) // 1000)
        if self._on_skew:
            try:
                self._on_skew(skew_ms, self._is_synced())
            except Exception as e:
                logger.debug(f"Skew callback error: {e}")

    def _drain(self) -> None:
        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            pass
