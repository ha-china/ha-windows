"""
VAD (Voice Activity Detection) Module
Uses webrtcvad to detect speech and silence
"""

import logging

import webrtcvad
import numpy as np

from src.i18n import get_i18n

logger = logging.getLogger(__name__)
_i18n = get_i18n()


class VAD:
    """Voice Activity Detector"""

    # Audio parameters
    SAMPLE_RATE = 16000  # 16kHz
    FRAME_DURATION_MS = 30  # Frame duration (milliseconds)

    # Calculation:
    # frame_size = (sample_rate * frame_duration_ms) / 1000
    # frame_size = (16000 * 30) / 1000 = 480 samples

    @staticmethod
    def get_frame_size() -> int:
        """Get frame size"""
        return int(VAD.SAMPLE_RATE * VAD.FRAME_DURATION_MS / 1000)

    def __init__(self, aggressiveness: int = 2):
        """
        Initialize VAD

        Args:
            aggressiveness: Detection aggressiveness (0-3)
                            0: Least aggressive (more noise recognized as speech)
                            1: Not aggressive
                            2: Aggressive (default)
                            3: Most aggressive (requires clearer speech)
        """
        if not 0 <= aggressiveness <= 3:
            raise ValueError("aggressiveness must be between 0-3")

        self.vad = webrtcvad.Vad(aggressiveness)
        self.silence_threshold = 1.0  # Silence threshold (seconds)

        logger.debug(f"VAD initialized (aggressiveness: {aggressiveness})")

    def is_speech(self, audio_frame: bytes) -> bool:
        """
        Detect if audio frame contains speech

        Args:
            audio_frame: Audio frame (PCM format, 16-bit signed little-endian)

        Returns:
            bool: Whether it contains speech
        """
        try:
            # Check frame size
            frame_size = self.get_frame_size()
            expected_bytes = frame_size * 2  # 16-bit = 2 bytes

            if len(audio_frame) < expected_bytes:
                logger.warning(
                    f"Audio frame too small: {len(audio_frame)} bytes "
                    f"(expected: {expected_bytes} bytes)"
                )
                return False

            # Use WebRTC VAD for detection
            is_speech = self.vad.is_speech(audio_frame, self.SAMPLE_RATE)

            return is_speech

        except Exception as e:
            logger.error(f"VAD detection failed: {e}")
            return False

    def is_speech_numpy(self, audio_array: np.ndarray) -> bool:
        """
        Detect if NumPy audio array contains speech

        Args:
            audio_array: Audio array (float32, -1.0 to 1.0)

        Returns:
            bool: Whether it contains speech
        """
        # Convert to PCM format
        pcm_data = self._numpy_to_pcm(audio_array)
        return self.is_speech(pcm_data)

    def detect_silence(
        self,
        audio_frames: list[bytes],
        threshold: float = 1.0
    ) -> bool:
        """
        Detect if audio frame sequence contains enough silence

        Args:
            audio_frames: List of audio frames
            threshold: Silence threshold (seconds)

        Returns:
            bool: Whether silence was detected
        """
        frame_duration = self.FRAME_DURATION_MS / 1000.0
        silence_frames = int(threshold / frame_duration)

        # Count consecutive silence frames
        consecutive_silence = 0

        for frame in audio_frames:
            if not self.is_speech(frame):
                consecutive_silence += 1
                if consecutive_silence >= silence_frames:
                    return True
            else:
                consecutive_silence = 0

        return False

    def _numpy_to_pcm(self, audio_array: np.ndarray) -> bytes:
        """
        Convert NumPy audio array to PCM format

        Args:
            audio_array: Audio array (float32, -1.0 to 1.0)

        Returns:
            bytes: PCM format audio data
        """
        # Clip range
        clipped = np.clip(audio_array, -1.0, 1.0)

        # Convert to 16-bit signed integer
        int16_data = (clipped * 32767.0).astype(np.int16)

        # Convert to byte stream
        return int16_data.tobytes()

    def set_aggressiveness(self, aggressiveness: int) -> None:
        """
        Set detection aggressiveness

        Args:
            aggressiveness: Aggressiveness (0-3)
        """
        if not 0 <= aggressiveness <= 3:
            raise ValueError("aggressiveness must be between 0-3")

        self.vad.set_aggressiveness(aggressiveness)
        logger.info(f"VAD aggressiveness set to: {aggressiveness}")

    def set_silence_threshold(self, threshold: float) -> None:
        """
        Set silence threshold

        Args:
            threshold: Silence threshold (seconds)
        """
        if threshold < 0:
            raise ValueError("threshold must be >= 0")

        self.silence_threshold = threshold
        logger.info(f"Silence threshold set to: {threshold} seconds")


class StreamingVAD:
    """Streaming VAD processor"""

    def __init__(self, aggressiveness: int = 2, silence_threshold: float = 1.0):
        """
        Initialize streaming VAD

        Args:
            aggressiveness: VAD aggressiveness
            silence_threshold: Silence threshold (seconds)
        """
        self.vad = VAD(aggressiveness)
        self.silence_threshold = silence_threshold

        self._speech_frames = 0
        self._silence_frames = 0
        self._is_speaking = False

    def process_frame(self, audio_frame: bytes) -> tuple[bool, bool]:
        """
        Process audio frame

        Args:
            audio_frame: Audio frame

        Returns:
            tuple[bool, bool]: (is speech, speech ended detected)
        """
        is_speech = self.vad.is_speech(audio_frame)

        if is_speech:
            self._speech_frames += 1
            self._silence_frames = 0
            self._is_speaking = True
        else:
            self._silence_frames += 1
            if not self._is_speaking:
                # Not started speaking yet
                pass

        # Detect if speech ended
        frame_duration = self.vad.FRAME_DURATION_MS / 1000.0
        silence_frames_needed = int(self.silence_threshold / frame_duration)

        speech_ended = (
            self._is_speaking
            and self._silence_frames >= silence_frames_needed
        )

        if speech_ended:
            # Reset state
            self._is_speaking = False
            self._silence_frames = 0
            self._speech_frames = 0

        return is_speech, speech_ended

    def reset(self) -> None:
        """Reset state"""
        self._speech_frames = 0
        self._silence_frames = 0
        self._is_speaking = False


# Convenience function
def create_vad(aggressiveness: int = 2) -> VAD:
    """
    Create VAD instance

    Args:
        aggressiveness: Aggressiveness (0-3)

    Returns:
        VAD: VAD instance
    """
    return VAD(aggressiveness)


if __name__ == "__main__":
    # Test code
    logging.basicConfig(level=logging.INFO)

    def test_vad():
        """Test VAD"""
        logger.info("Testing VAD (Voice Activity Detection)")

        # Create VAD
        vad = VAD(aggressiveness=2)

        # Create test audio frame
        frame_size = vad.get_frame_size()

        # Test 1: Silence frame
        silence_frame = bytes(frame_size * 2)  # All zeros
        is_speech = vad.is_speech(silence_frame)
        logger.info(f"Silence frame detection result: {'speech' if is_speech else 'silence'}")

        # Test 2: Simulated speech frame (random noise)
        import random
        noise_frame = bytes(
            random.getrandbits(8) for _ in range(frame_size * 2)
        )
        is_speech = vad.is_speech(noise_frame)
        logger.info(f"Noise frame detection result: {'speech' if is_speech else 'silence'}")

        logger.info("\nVAD test complete")

    # Run test
    test_vad()
