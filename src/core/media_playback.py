"""
Announcement / TTS playback mixin

Behavior-preserving extraction from ESPHomeProtocol (see esphome_protocol.py).
Methods run on the composed protocol instance and share its ``self`` state.
"""

import asyncio
import logging
from typing import Callable, Dict, List, Optional

from aioesphomeapi.api_pb2 import (
    VoiceAssistantAnnounceFinished,
    VoiceAssistantAnnounceRequest,
    VoiceAssistantRequest,
)

logger = logging.getLogger(__name__)


class PlaybackMixin:
    """Announcements, TTS playback, volume ducking and timer sounds."""

    def _handle_announce_request(self, msg: VoiceAssistantAnnounceRequest) -> None:
        """
        Handle voice announcement request

        References linux-voice-assistant's handle_message VoiceAssistantAnnounceRequest handling
        """
        logger.info(f"Received announcement request: {msg.text}")

        # Build playlist
        urls = []
        if msg.preannounce_media_id:
            urls.append(msg.preannounce_media_id)
        urls.append(msg.media_id)

        # Set continue conversation flag
        self._continue_conversation = msg.start_conversation

        # Add stop word
        if self.state.stop_word:
            self.state.active_wake_words.add(self.state.stop_word.id)

        # Duck volume and play
        self.duck()

        # Play audio
        if urls:
            self._play_announcement(urls)
        else:
            # No audio, complete directly
            self._tts_finished()

    def _play_announcement(self, urls: List[str]) -> None:
        """Play announcement audio"""
        if not urls:
            self._tts_finished()
            return

        # Play first URL
        url = urls[0]
        remaining = urls[1:]

        def on_done():
            if remaining:
                self._play_announcement(remaining)
            else:
                self._tts_finished()

        self.state.tts_player.play(url, done_callback=on_done)

    # ========== Audio Control ==========


    def play_tts(self) -> None:
        """Play TTS response"""
        if not self._tts_url or self._tts_played:
            return

        self._processing = False
        self._tts_played = True
        self._is_playing_tts = True  # Mark that TTS is playing
        logger.info(f"Playing TTS: {self._tts_url}")

        # Add stop word
        if self.state.stop_word:
            self.state.active_wake_words.add(self.state.stop_word.id)

        self.state.tts_player.play(self._tts_url, done_callback=self._tts_finished)

    def duck(self) -> None:
        """Lower volume"""
        if not self._volume_ducking_enabled:
            return
        try:
            self.state.music_player.duck()
        except Exception as e:
            logger.error(f"Failed to duck volume: {e}")

    def unduck(self) -> None:
        """Restore volume"""
        if not self._volume_ducking_enabled:
            return
        try:
            self.state.music_player.unduck()
        except Exception as e:
            logger.error(f"Failed to unduck volume: {e}")

    def _tts_finished(self) -> None:
        """TTS playback finished callback"""
        self._processing = False
        self._is_playing_tts = False  # Mark that TTS is no longer playing
        self._set_phase('idle')

        # Remove stop word
        if self.state.stop_word:
            self.state.active_wake_words.discard(self.state.stop_word.id)

        # Send completion message
        self.send_messages([VoiceAssistantAnnounceFinished()])

        if self._continue_conversation:
            # Continue conversation
            self.send_messages([VoiceAssistantRequest(start=True)])
            self._is_streaming_audio = True

            # Play wakeup sound to prompt user to speak, then start recording
            if self.state.wakeup_sound:
                logger.debug("Playing wakeup sound for continue conversation")
                self.state.tts_player.play(self.state.wakeup_sound, done_callback=self._start_audio_streaming)
            else:
                # No wakeup sound, start recording directly
                self._start_audio_streaming()

            logger.debug("Continuing conversation")
        else:
            # Restore volume
            self.unduck()

        logger.debug("TTS playback finished")

    def _play_timer_finished(self) -> None:
        """Play timer finished sound"""
        if not self._timer_finished:
            self.unduck()
            return

        # Loop play timer sound with async delay
        loop = self._event_loop or self._loop

        if loop is not None and not loop.is_closed():
            async def on_done_async():
                await asyncio.sleep(1.0)
                if self._timer_finished:
                    loop.call_soon_threadsafe(self._play_timer_finished)

            def on_done():
                asyncio.run_coroutine_threadsafe(on_done_async(), loop)
        else:
            # No usable event loop (e.g. early startup): keep the looping
            # semantics with a plain timer thread instead.
            import threading

            def on_done():
                timer = threading.Timer(1.0, self._replay_timer_sound_if_active)
                timer.daemon = True
                timer.start()

        if self.state.timer_finished_sound:
            self.state.tts_player.play(self.state.timer_finished_sound, done_callback=on_done)

    def _replay_timer_sound_if_active(self) -> None:
        """Timer-thread re-entry point mirroring on_done_async's delay loop."""
        if self._timer_finished:
            self._play_timer_finished()

    # ========== Entity Message Processing ==========

