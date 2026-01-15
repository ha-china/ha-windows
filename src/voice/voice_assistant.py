"""
Voice Assistant Module

Integrates audio recording, VAD, wake word detection, and audio streaming.
For use with ESPHome server mode (HA connects to Windows).
"""

import asyncio
import logging
import threading
from typing import Callable, Optional, Dict

from .audio_recorder import AsyncAudioRecorder
from .wake_word import AsyncWakeWordDetector
from .vad import StreamingVAD

from src.i18n import get_i18n

logger = logging.getLogger(__name__)
_i18n = get_i18n()


class AudioStreamHandler:
    """
    Audio Stream Handler for ESPHome Voice Assistant

    Manages audio recording with VAD and queues audio chunks for HTTP streaming.
    Used by ESPHome protocol server when HA requests audio.
    """

    def __init__(self):
        """Initialize audio stream handler"""
        self._recording = False
        self._audio_queue: Optional[asyncio.Queue] = None
        self._recorder: Optional[AsyncAudioRecorder] = None
        self._vad: Optional[StreamingVAD] = None
        self._recording_task: Optional[asyncio.Task] = None

    def get_recorder(self) -> AsyncAudioRecorder:
        """Get or create audio recorder"""
        if self._recorder is None:
            self._recorder = AsyncAudioRecorder()
            logger.info("Audio recorder initialized")
        return self._recorder

    def get_vad(self) -> StreamingVAD:
        """Get or create VAD detector"""
        if self._vad is None:
            self._vad = StreamingVAD(aggressiveness=2, silence_threshold=1.0)
            logger.info("VAD detector initialized")
        return self._vad

    async def start_recording(self) -> Optional[Callable[[], asyncio.Queue]]:
        """
        Start audio recording with VAD

        Returns:
            Callable that returns the audio queue, or None if already recording
        """
        if self._recording:
            logger.warning("Recording already in progress")
            return None

        self._recording = True
        self._audio_queue = asyncio.Queue()

        # Start recording task
        self._recording_task = asyncio.create_task(self._record_loop())

        logger.info("Audio recording started")
        return lambda: self._audio_queue

    async def _record_loop(self):
        """Recording loop with VAD - stops on silence detection"""
        recorder = self.get_recorder()
        vad = self.get_vad()

        await recorder.start_recording()

        silence_count = 0
        max_silence = 30  # 3 seconds of silence (30 chunks)

        try:
            while self._recording:
                # Get audio chunk
                chunk = await recorder.get_audio_chunk()
                if not chunk:
                    continue

                # Put in queue for HTTP streaming
                await self._audio_queue.put(chunk)

                # Check for silence (VAD)
                is_speech, speech_ended = vad.process_frame(chunk)
                
                # If speech ended (detected silence after speech), stop recording
                if speech_ended:
                    logger.info("Speech ended, stopping recording")
                    break

        except asyncio.CancelledError:
            logger.info("Recording task cancelled")
        finally:
            await recorder.stop_recording()
            self._recording = False
            # Signal end of recording
            await self._audio_queue.put(None)
            logger.info("Audio recording stopped")

    async def stop_recording(self):
        """Stop audio recording"""
        if not self._recording:
            return

        self._recording = False

        if self._recording_task:
            self._recording_task.cancel()
            try:
                await self._recording_task
            except asyncio.CancelledError:
                pass
            self._recording_task = None

        logger.info("Audio recording stopped")

    def is_recording(self) -> bool:
        """Check if currently recording"""
        return self._recording


class VoiceAssistant:
    """Voice Assistant Integration"""

    def __init__(
        self,
        audio_device: Optional[str] = None,
        wake_word_model: str = 'okay_nabu',
        send_audio_callback: Optional[Callable[[bytes], None]] = None,
    ):
        """
        Initialize Voice Assistant

        Args:
            audio_device: Audio device name
            wake_word_model: Wake word model
            send_audio_callback: Audio data send callback
        """
        # Audio components
        self.recorder = AsyncAudioRecorder(audio_device)
        self.wake_word_detector = AsyncWakeWordDetector(wake_word_model)
        self.vad = StreamingVAD(aggressiveness=2, silence_threshold=1.0)

        # State
        self._running = False
        self._listening = False
        self._processing = False

        # Callbacks
        self._on_response: Optional[Callable] = None
        self._send_audio_callback = send_audio_callback

        logger.info("Voice Assistant initialized")

    def on_response(self, callback: Callable) -> None:
        """
        Register response callback

        Args:
            callback: Response callback function
        """
        self._on_response = callback

    async def start(self, use_wake_word: bool = True) -> None:
        """
        Start Voice Assistant

        Args:
            use_wake_word: Whether to use wake word
        """
        if self._running:
            logger.warning("Voice Assistant already running")
            return

        self._running = True

        if use_wake_word:
            # Wake word mode
            await self._wake_word_loop()
        else:
            # Manual mode (button trigger)
            await self._manual_loop()

    async def stop(self) -> None:
        """Stop Voice Assistant"""
        self._running = False
        self._listening = False
        self._processing = False

        await self.recorder.stop_recording()

    async def _wake_word_loop(self) -> None:
        """Wake word loop"""
        logger.info("Starting wake word mode")

        await self.recorder.start_recording()

        try:
            while self._running:
                # Get audio chunk
                audio_chunk = await self.recorder.get_audio_chunk()

                if not audio_chunk:
                    continue

                # Convert to numpy array
                import numpy as np
                audio_array = np.frombuffer(audio_chunk, dtype=np.int16).astype(np.float32) / 32768.0

                # Detect wake word
                detected = self.wake_word_detector.process_audio(audio_array)

                if detected:
                    logger.info("Wake word detected!")
                    await self._start_conversation()

        finally:
            await self.recorder.stop_recording()

    async def _manual_loop(self) -> None:
        """Manual mode loop"""
        logger.info("Starting manual mode")

        while self._running:
            # Wait for trigger signal
            await asyncio.sleep(1)

    async def trigger(self) -> None:
        """Manually trigger Voice Assistant"""
        if not self._running:
            logger.warning("Voice Assistant not started")
            return

        if self._processing:
            logger.warning("Voice Assistant is processing")
            return

        await self._start_conversation()

    async def _start_conversation(self) -> None:
        """Start conversation"""
        self._listening = True
        self._processing = True

        logger.info("Starting to listen...")

        try:
            # Start recording
            # await self.recorder.start_recording()

            # Use VAD to detect speech end
            audio_data = await self._record_with_vad()

            self._listening = False
            logger.info("Voice recording complete")

            # Send to Home Assistant
            await self._send_to_assistant(audio_data)

        except Exception as e:
            logger.error(f"Conversation failed: {e}")
            self._listening = False
            self._processing = False

    async def _record_with_vad(self) -> bytes:
        """
        Record voice with VAD

        Returns:
            bytes: Recorded audio data
        """
        audio_chunks = []

        # TODO: Implement actual VAD recording
        # This is just example code

        # Simulate 3 second recording
        await asyncio.sleep(3)

        # Collect audio chunks
        for _ in range(10):  # Collect 10 chunks
            chunk = await self.recorder.get_audio_chunk()
            if chunk:
                audio_chunks.append(chunk)

        # Merge all chunks
        return b''.join(audio_chunks)

    async def _send_to_assistant(self, audio_data: bytes) -> None:
        """
        Send audio to Home Assistant (via callback function)

        Args:
            audio_data: Audio data
        """
        try:
            logger.info(f"Sending audio to Home Assistant (size={len(audio_data)})...")

            # Use callback function to send audio data
            if self._send_audio_callback:
                self._send_audio_callback(audio_data)
            else:
                logger.warning("Audio send callback not set, audio data will be ignored")

            # Response handling is the caller's responsibility
            # TTS playback is handled by esphome_protocol.py's _handle_voice_assistant_audio

            logger.info("Audio data sent")

        except Exception as e:
            logger.error(f"Failed to send to Assistant: {e}")
        finally:
            self._processing = False

    def cleanup(self) -> None:
        """Cleanup resources"""
        pass  # No resources to cleanup


# Convenience function
def create_voice_assistant(
    audio_device: Optional[str] = None,
    wake_word_model: str = 'okay_nabu',
    send_audio_callback: Optional[Callable[[bytes], None]] = None,
) -> VoiceAssistant:
    """
    Create Voice Assistant (convenience function)

    Args:
        audio_device: Audio device
        wake_word_model: Wake word model
        send_audio_callback: Audio data send callback function

    Returns:
        VoiceAssistant: Voice Assistant instance
    """
    return VoiceAssistant(audio_device, wake_word_model, send_audio_callback)


if __name__ == "__main__":
    # Test code
    logging.basicConfig(level=logging.INFO)

    async def test_voice_assistant():
        """Test Voice Assistant"""
        logger.info("Testing Voice Assistant")

        # Note: Requires actual ESPHome connection
        logger.info("Voice Assistant test requires complete connection")

    # Run test
    asyncio.run(test_voice_assistant())
