"""
Audio Recording Module
Uses sounddevice library to record microphone audio
"""

import asyncio
import logging
import threading
from typing import Optional, Callable
from queue import Empty, Full, Queue

import numpy as np
import sounddevice as sd

from src.i18n import get_i18n

logger = logging.getLogger(__name__)
_i18n = get_i18n()


class AudioRecorder:
    """Audio Recorder"""

    # Audio parameters
    SAMPLE_RATE = 16000  # 16kHz (ESPHome Voice Assistant standard)
    CHANNELS = 1  # Mono
    BLOCK_SIZE = 1024  # Samples per read

    def __init__(self, device: Optional[str] = None):
        """
        Initialize audio recorder

        Args:
            device: Audio device name or index (None = default microphone)
        """
        self.device = device
        self.device_id: Optional[int] = None
        self.is_recording = False
        self.audio_queue: Queue[bytes] = Queue(maxsize=200)
        self.recording_thread: Optional[threading.Thread] = None
        self._stream: Optional[sd.InputStream] = None

    @staticmethod
    def list_microphones() -> list[str]:
        """
        List all available microphones (input devices)

        Returns:
            list[str]: List of microphone names
        """
        try:
            devices = sd.query_devices()
            inputs = [d["name"] for d in devices if d["max_input_channels"] > 0]
            return inputs
        except Exception as e:
            logger.error(f"Failed to get microphone list: {e}")
            return []

    def _resolve_device(self) -> Optional[int]:
        """Resolve device name to device ID"""
        if self.device is None:
            return None

        try:
            device_id = int(self.device)
            return device_id
        except (ValueError, TypeError):
            pass

        devices = sd.query_devices()
        for i, dev in enumerate(devices):
            if dev["name"] == self.device and dev["max_input_channels"] > 0:
                return i

        logger.warning(f"Specified microphone not found: {self.device}, using default")
        return None

    def start_recording(self, audio_callback: Optional[Callable[[bytes], None]] = None):
        """
        Start recording

        Args:
            audio_callback: Audio data callback function
        """
        if self.is_recording:
            logger.warning("Recording already in progress")
            return

        try:
            self.device_id = self._resolve_device()
            if self.device_id is not None:
                dev_info = sd.query_devices(self.device_id)
                logger.debug(f"Using microphone: {dev_info['name']}")

            self.is_recording = True

            # Start recording thread
            self.recording_thread = threading.Thread(
                target=self._record_loop,
                args=(audio_callback,),
                daemon=True
            )
            self.recording_thread.start()

            logger.debug("Recording started")

        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            self.is_recording = False
            raise

    def stop_recording(self):
        """Stop recording"""
        if not self.is_recording:
            return

        self.is_recording = False

        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                logger.debug(f"Error closing stream: {e}")
            self._stream = None

        if self.recording_thread:
            self.recording_thread.join(timeout=2.0)
            self.recording_thread = None

        try:
            while True:
                self.audio_queue.get_nowait()
        except Empty:
            pass

        logger.debug("Recording stopped")

    def _record_loop(self, audio_callback: Optional[Callable[[bytes], None]]):
        """
        Recording loop (runs in separate thread)

        Args:
            audio_callback: Audio data callback function
        """
        try:
            def callback(indata, frames, time_info, status):
                if status:
                    logger.debug(f"Recording status: {status}")
                if not self.is_recording:
                    raise sd.CallbackStop

                audio_pcm = self._array_to_pcm(indata)

                if audio_callback:
                    audio_callback(audio_pcm)
                else:
                    try:
                        self.audio_queue.put_nowait(audio_pcm)
                    except Full:
                        try:
                            self.audio_queue.get_nowait()
                            self.audio_queue.put_nowait(audio_pcm)
                        except (Empty, Full):
                            pass

            self._stream = sd.InputStream(
                device=self.device_id,
                samplerate=self.SAMPLE_RATE,
                channels=self.CHANNELS,
                dtype='float32',
                blocksize=self.BLOCK_SIZE,
                callback=callback,
            )
            self._stream.start()

            while self.is_recording:
                sd.sleep(100)

        except Exception as e:
            logger.error(f"Recording loop error: {e}")
        finally:
            if self._stream:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None
            self.is_recording = False

    def _array_to_pcm(self, audio_array: np.ndarray) -> bytes:
        """
        Convert NumPy audio array to PCM byte stream

        Args:
            audio_array: Audio array (float32, shape (frames, channels))

        Returns:
            bytes: PCM format audio data (16-bit signed little-endian)
        """
        audio_array = np.squeeze(audio_array)
        clipped = np.clip(audio_array, -1.0, 1.0)
        int16_data = (clipped * 32767.0).astype(np.int16)
        return int16_data.tobytes()

    def get_audio_chunk(self, timeout: float = 1.0) -> Optional[bytes]:
        """
        Get audio chunk (blocking)

        Args:
            timeout: Timeout in seconds

        Returns:
            Optional[bytes]: Audio data, or None if timeout
        """
        try:
            return self.audio_queue.get(timeout=timeout)
        except Exception:
            return None

    async def get_audio_chunk_async(self) -> Optional[bytes]:
        """
        Get audio chunk asynchronously

        Returns:
            Optional[bytes]: Audio data
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.get_audio_chunk)

    @staticmethod
    def create_silence(duration: float = 0.1) -> bytes:
        """
        Create silent audio

        Args:
            duration: Silence duration in seconds

        Returns:
            bytes: PCM format silence data
        """
        num_samples = int(AudioRecorder.SAMPLE_RATE * duration)
        silence = np.zeros(num_samples, dtype=np.int16)
        return silence.tobytes()


class AsyncAudioRecorder:
    """Async audio recorder wrapper"""

    def __init__(self, device: Optional[str] = None):
        """
        Initialize async audio recorder

        Args:
            device: Audio device name
        """
        self.recorder = AudioRecorder(device)
        self.audio_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=200)
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def start_recording(self):
        """Start recording"""
        self._loop = asyncio.get_running_loop()
        self.recorder.start_recording(self._on_audio_data)
        logger.info("Async recording started")

    def _enqueue_audio_data(self, audio_data: bytes) -> None:
        """Enqueue audio in event loop thread with bounded growth."""
        if self.audio_queue.full():
            try:
                self.audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass

        try:
            self.audio_queue.put_nowait(audio_data)
        except asyncio.QueueFull:
            pass

    def _on_audio_data(self, audio_data: bytes):
        """
        Audio data callback

        Args:
            audio_data: Audio data
        """
        try:
            if self._loop is None:
                return
            self._loop.call_soon_threadsafe(self._enqueue_audio_data, audio_data)
        except Exception as e:
            logger.error(f"Audio data callback failed: {e}")

    def stop_recording(self):
        """Stop recording"""
        self.recorder.stop_recording()

        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._clear_queue)

        logger.info("Async recording stopped")

    def _clear_queue(self) -> None:
        """Clear buffered audio chunks from async queue."""
        try:
            while True:
                self.audio_queue.get_nowait()
        except asyncio.QueueEmpty:
            pass

    async def get_audio_chunk(self) -> bytes:
        """
        Get audio chunk

        Returns:
            bytes: Audio data
        """
        return await self.audio_queue.get()


if __name__ == "__main__":
    # Test code
    logging.basicConfig(level=logging.INFO)

    async def test_recording():
        """Test recording"""
        logger.info("Testing audio recorder")

        # List microphones
        mics = AudioRecorder.list_microphones()
        logger.info(f"Available microphones ({len(mics)}):")
        for i, mic in enumerate(mics, 1):
            logger.info(f"  {i}. {mic}")

        # Create recorder
        recorder = AsyncAudioRecorder()

        # Record for 5 seconds
        logger.info("\nStarting 5 second recording...")
        await recorder.start_recording()

        chunks = []
        end_time = asyncio.get_event_loop().time() + 5

        while asyncio.get_event_loop().time() < end_time:
            try:
                chunk = await asyncio.wait_for(
                    recorder.get_audio_chunk(),
                    timeout=0.5
                )
                if chunk:
                    chunks.append(chunk)
                    logger.debug(f"Received audio chunk: {len(chunk)} bytes")
            except asyncio.TimeoutError:
                break

        recorder.stop_recording()

        # Statistics
        total_bytes = sum(len(chunk) for chunk in chunks)
        total_seconds = total_bytes / 2 / 16000  # 16-bit, 16kHz
        logger.info("Recording complete:")
        logger.info(f"  Total bytes: {total_bytes}")
        logger.info(f"  Total duration: {total_seconds:.2f} seconds")
        logger.info(f"  Chunk count: {len(chunks)}")

    # Run test
    asyncio.run(test_recording())