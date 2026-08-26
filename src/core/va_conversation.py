"""
Voice assistant conversation mixin

Behavior-preserving extraction from ESPHomeProtocol (see esphome_protocol.py).
Methods run on the composed protocol instance and share its ``self`` state.
"""

import asyncio
import logging
from typing import Callable, Dict, List, Optional

from aioesphomeapi.api_pb2 import (
    SubscribeHomeAssistantStatesRequest,
    VoiceAssistantAudio,
    VoiceAssistantConfigurationRequest,
    VoiceAssistantConfigurationResponse,
    VoiceAssistantEventResponse,
    VoiceAssistantRequest,
    VoiceAssistantSetConfiguration,
    VoiceAssistantTimerEventResponse,
    VoiceAssistantWakeWord,
)
from aioesphomeapi.model import VoiceAssistantEventType, VoiceAssistantTimerEventType

from src.core.models import get_user_data_dir

logger = logging.getLogger(__name__)


class VoiceAssistantMixin:
    """Voice assistant conversation state machine: events, config, streaming."""

    def _handle_voice_event(self, msg: VoiceAssistantEventResponse) -> None:
        """Handle Voice Assistant event"""
        # Parse event data
        data: Dict[str, str] = {}
        for arg in msg.data:
            data[arg.name] = arg.value

        event_type = VoiceAssistantEventType(msg.event_type)
        self.handle_voice_event(event_type, data)

    def handle_voice_event(self, event_type: VoiceAssistantEventType, data: Dict[str, str]) -> None:
        """
        Handle Voice Assistant event

        References linux-voice-assistant's handle_voice_event
        """
        logger.debug(f"Voice event: type={event_type.name}, data={data}")

        if event_type == VoiceAssistantEventType.VOICE_ASSISTANT_RUN_START:
            # Conversation started
            self._tts_url = data.get("url")
            self._tts_played = False
            self._continue_conversation = False
            self._processing = False
            self._debug_audio_chunks = []
            self._set_phase('listening')

        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_INTENT_START:
            if self.state.thinking_sound_enabled and self.state.processing_sound and not self._processing:
                self._processing = True
                self.duck()
                self.state.tts_player.play(self.state.processing_sound)
            self._set_phase('thinking')

        elif event_type in (
            VoiceAssistantEventType.VOICE_ASSISTANT_STT_VAD_END,
            VoiceAssistantEventType.VOICE_ASSISTANT_STT_END,
        ):
            # Speech recognition ended, stop audio stream and recording
            logger.info(f"🎤 Received {event_type.name}, clearing streaming flag")
            self._is_streaming_audio = False
            self._stop_audio_streaming()
            logger.debug("🎤 Speech recognition ended, stopping recording")
            # Capture STT text for conversation bubble
            if event_type == VoiceAssistantEventType.VOICE_ASSISTANT_STT_END:
                stt_text = data.get("text", "")
                if stt_text and self._conversation_callback:
                    try:
                        self._conversation_callback("stt", stt_text)
                    except Exception as e:
                        logger.error(f"Conversation callback error: {e}")

        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_INTENT_PROGRESS:
            # Intent processing progress
            if data.get("tts_start_streaming") == "1":
                logger.info("🎤 INTENT_PROGRESS: tts_start_streaming")
                self._set_phase('replying')
                self.play_tts()

        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_INTENT_END:
            # Intent processing ended
            logger.info("🎤 Received INTENT_END")
            self._processing = False
            if data.get("continue_conversation") == "1":
                self._continue_conversation = True

        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_TTS_START:
            # TTS generation started, emit phase for UI feedback
            logger.info("🎤 Received TTS_START")
            self._set_phase('replying')
            # Capture response text for conversation bubble
            response_text = data.get("text", "")
            if response_text and self._conversation_callback:
                try:
                    self._conversation_callback("tts", response_text)
                except Exception as e:
                    logger.error(f"Conversation callback error: {e}")

        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_TTS_END:
            # TTS generation ended
            url = data.get("url", "")
            logger.info(f"🎤 Received TTS_END with URL: {url[:60]}...")
            self._tts_url = url
            self.play_tts()

        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_RUN_END:
            # Conversation ended
            logger.info("🎤 Received RUN_END, clearing streaming flag")
            self._is_streaming_audio = False
            self._processing = False
            self._stop_audio_streaming()
            if not self._tts_played:
                self._tts_finished()
            self._tts_played = False
            if not self._is_playing_tts:
                self._set_phase('idle')

        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_ERROR:
            # Benign errors: user said nothing / pipeline idle timeouts. ESPHome
            # itself returns to idle for these instead of flagging an error.
            if data.get("code") in ("stt-no-text-recognized", "wake-word-timeout",
                                    "no_wake_word", "wake_word_detection_aborted",
                                    "timeout"):
                logger.info(f"🎤 Voice assistant benign error: {data.get('code')}")
                if data.get("code") == "stt-no-text-recognized":
                    # Keep the audio that failed so it can be inspected
                    self._dump_debug_audio(data.get("code"))
                    # Tell the user instead of failing silently
                    self._notify_no_speech()
                self._is_streaming_audio = False
                self._processing = False
                self._stop_audio_streaming()
                self._set_phase('idle')
                return

            logger.error(f"Voice assistant error: {data}")
            self._is_streaming_audio = False
            self._processing = False
            self._stop_audio_streaming()
            self._set_phase('error')

        else:
            logger.info(f"Unhandled voice assistant event: {event_type.name} (type={event_type.value})")

    def _handle_timer_event(self, msg: VoiceAssistantTimerEventResponse) -> None:
        """Handle timer event"""
        event_type = VoiceAssistantTimerEventType(msg.event_type)
        self.handle_timer_event(event_type, msg)

    def handle_timer_event(self, event_type: VoiceAssistantTimerEventType, msg) -> None:
        """
        Handle timer event

        References linux-voice-assistant's handle_timer_event
        """
        logger.debug(f"Timer event: type={event_type.name}")

        if event_type == VoiceAssistantTimerEventType.VOICE_ASSISTANT_TIMER_FINISHED:
            if not self._timer_finished:
                # Add stop word to active wake words
                if self.state.stop_word:
                    self.state.active_wake_words.add(self.state.stop_word.id)
                self._timer_finished = True
                self.duck()
                self._play_timer_finished()

    # ========== Voice Assistant Configuration ==========

    def _handle_voice_config(self, msg: VoiceAssistantConfigurationRequest) -> None:
        """Handle voice assistant configuration request"""
        # Build available wake words list
        available_wake_words = [
            VoiceAssistantWakeWord(
                id=ww.id,
                wake_word=ww.wake_word,
                trained_languages=ww.trained_languages,
            )
            for ww in self.state.available_wake_words.values()
        ]

        # Process external wake words
        for eww in msg.external_wake_words:
            if eww.model_type != "micro":
                continue
            available_wake_words.append(
                VoiceAssistantWakeWord(
                    id=eww.id,
                    wake_word=eww.wake_word,
                    trained_languages=eww.trained_languages,
                )
            )
            self._external_wake_words[eww.id] = eww

        response = VoiceAssistantConfigurationResponse(
            available_wake_words=available_wake_words,
            active_wake_words=[
                wake_word_id
                # snapshot: the audio thread mutates this set concurrently
                for wake_word_id in list(self.state.active_wake_words)
                if wake_word_id in self.state.available_wake_words
            ],
            max_active_wake_words=2,
        )

        self.send_messages([response])
        logger.info("✅ Connected to Home Assistant")

    def _handle_set_voice_config(self, msg: VoiceAssistantSetConfiguration) -> None:
        """Handle set voice assistant configuration"""
        active_wake_words: List[str] = []

        for wake_word_id in msg.active_wake_words:
            if wake_word_id in self.state.wake_words:
                if wake_word_id not in active_wake_words:
                    active_wake_words.append(wake_word_id)
                continue

            model_info = self.state.available_wake_words.get(wake_word_id)
            if model_info:
                logger.debug(f"Setting wake word: {wake_word_id}")
                if wake_word_id not in active_wake_words:
                    active_wake_words.append(wake_word_id)

            if len(active_wake_words) >= 2:
                break

        self.state.active_wake_words = set(active_wake_words)
        self.state.preferences.active_wake_words = active_wake_words
        self.state.save_preferences()
        self.state.wake_words_changed = True

        logger.info(f"🎤 Active wake words updated: {self.state.active_wake_words}")

    # ========== Announcement Processing ==========


    def _start_audio_streaming(self) -> None:
        """Start audio streaming (audio is handled by main program's recorder)"""
        # Main program's recorder will send audio when _is_streaming_audio is True
        logger.debug("🎤 Audio streaming started (main recorder will send audio)")

    def _stop_audio_streaming(self) -> None:
        """Stop audio streaming"""
        # Main program's recorder continues running, just clear the flag
        logger.debug("🎤 Audio streaming stopped")

    def handle_audio(self, audio_chunk: bytes) -> None:
        """
        Handle audio chunk

        Only send audio when in streaming state
        """
        if not self._is_streaming_audio:
            return

        # Log first few audio chunks
        self._audio_chunks_sent += 1
        if self._audio_chunks_sent <= 5:
            logger.info(f"🎤 Sending audio chunk #{self._audio_chunks_sent}: {len(audio_chunk)} bytes")

        # Capture streamed audio so failures can be diagnosed from real data
        # (last conversation only, overwritten each time; capped at ~8 MB)
        if len(self._debug_audio_chunks) < 256:
            self._debug_audio_chunks.append(audio_chunk)

        self.send_messages([VoiceAssistantAudio(data=audio_chunk)])

    def _notify_no_speech(self) -> None:
        """Show a bubble telling the user no speech was recognized."""
        try:
            from src.i18n import get_i18n
            from src.ui.conversation_bubble import show_conversation_bubble

            show_conversation_bubble("info", get_i18n().t('error_no_speech'))
        except Exception as e:
            logger.debug(f"No-speech bubble failed: {e}")

    def _dump_debug_audio(self, reason: str) -> None:
        """Write the audio actually sent to HA as a WAV for diagnosis."""
        if not getattr(self, "_debug_audio_chunks", None):
            return
        try:
            import wave

            out_dir = get_user_data_dir() / "debug"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / "last_stt_stream.wav"
            with wave.open(str(out_path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b"".join(self._debug_audio_chunks))
            logger.info(f"🎤 Debug audio dumped ({reason}): {out_path}")
        except Exception as e:
            logger.debug(f"Failed to dump debug audio: {e}")
        finally:
            self._debug_audio_chunks = []

    def wakeup(self, wake_word_phrase: str = "") -> None:
        """
        Wake word detection callback

        References linux-voice-assistant's wakeup
        """
        if self._timer_finished:
            # If timer is ringing, stop timer
            self._timer_finished = False
            self.state.tts_player.stop()
            logger.debug("Stopped timer sound")
            return

        if self.state.preferences.muted:
            # Muted: no audio would reach HA, the pipeline would fail with
            # stt-no-text-recognized. Ignore the trigger instead.
            logger.info("🎤 Wake word trigger ignored (microphone muted)")
            return

        logger.info(f"🎤 Wake word triggered: {wake_word_phrase}")
        logger.info(f"🎤 Current streaming state before wakeup: {self._is_streaming_audio}")

        # Send voice assistant request
        logger.debug("Sending VoiceAssistantRequest(start=True)")
        self.send_messages([VoiceAssistantRequest(start=True, wake_word_phrase=wake_word_phrase)])

        # Duck volume
        self.duck()

        # Start audio stream
        self._is_streaming_audio = True
        logger.info("🎤 Set streaming to True")

        # Start microphone recording
        self._start_audio_streaming()

        # Play wakeup sound
        if self.state.wakeup_sound:
            logger.debug(f"Playing wakeup sound: {self.state.wakeup_sound}")
            self.state.tts_player.play(self.state.wakeup_sound)
        else:
            logger.warning("Wakeup sound not set")

    def stop(self) -> None:
        """Stop current operation"""
        if self.state.stop_word:
            self.state.active_wake_words.discard(self.state.stop_word.id)
        self.state.tts_player.stop()

        if self._timer_finished:
            self._timer_finished = False
            logger.debug("Stopped timer sound")
        else:
            logger.debug("Manually stopped TTS")
            self._tts_finished()

    def _on_voice_input_trigger(self) -> None:
        """Handle voice input trigger from button"""
        logger.info("🎤 Voice input triggered via button (no wake word)")
        # Trigger voice assistant without wake word
        self.wakeup(wake_word_phrase="")

    def _on_hotkey_changed(self, hotkey: str) -> None:
        """Handle hotkey change"""
        logger.info(f"Hotkey changed to: {hotkey}")

        # Update preferences
        self.state.preferences.voice_input_hotkey = hotkey
        self.state.save_preferences()

        # Update config sensor state
        if self._config_sensor_manager:
            self._config_sensor_manager.set_hotkey(hotkey)
            self.send_messages(self._config_sensor_manager.get_states())

        # Update hotkey manager
        if self._hotkey_manager and self._hotkey_manager.is_available():
            if hotkey:
                self._hotkey_manager.set_hotkey(hotkey, self._on_voice_input_trigger)
            else:
                self._hotkey_manager.remove_hotkey()
        elif hotkey:
            logger.warning("Hotkey saved but runtime hotkey backend is unavailable on this platform")

    def _set_thinking_sound_enabled(self, enabled: bool) -> None:
        """Persist thinking sound switch state."""
        self.state.thinking_sound_enabled = bool(enabled)
        self.state.preferences.thinking_sound = 1 if self.state.thinking_sound_enabled else 0
        self.state.save_preferences()

        if self._thinking_sound_entity is not None:
            self.send_messages(list(self._thinking_sound_entity.handle_message(SubscribeHomeAssistantStatesRequest())))

