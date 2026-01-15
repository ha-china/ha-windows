"""
Wake Word Detection Module

Uses pymicro-wakeword for wake word detection (same as ESPHome microWakeWord).
"""

import logging
from pathlib import Path
from typing import Callable, Optional
import json

import numpy as np

logger = logging.getLogger(__name__)

# Default wake word directory (relative to src/)
DEFAULT_WAKEWORD_DIR = Path(__file__).parent.parent / "wakewords"

# Try to import pymicro-wakeword
_microwakeword_available = False
try:
    from pymicro_wakeword import MicroWakeWord, MicroWakeWordFeatures
    _microwakeword_available = True
    logger.info("pymicro-wakeword available for wake word detection")
except ImportError:
    logger.warning("pymicro-wakeword not available")


class WakeWordDetector:
    """Wake word detector using pymicro-wakeword"""

    def __init__(
        self,
        model_name: str = 'okay_nabu',
        wakeword_dir: Optional[Path] = None,
    ):
        """
        Initialize wake word detector

        Args:
            model_name: Wake word model name (e.g., 'okay_nabu', 'hey_jarvis')
            wakeword_dir: Directory containing wake word models
        """
        self.model_name = model_name
        self.wakeword_dir = wakeword_dir or DEFAULT_WAKEWORD_DIR
        self._on_wake_word: Optional[Callable[[str], None]] = None
        self._model: Optional[MicroWakeWord] = None
        self._features: Optional[MicroWakeWordFeatures] = None
        self._wake_word_phrase: str = model_name

        if not _microwakeword_available:
            logger.warning("pymicro-wakeword not installed, wake word detection disabled")
            return

        # Load model
        config_path = self.wakeword_dir / f"{model_name}.json"
        if not config_path.exists():
            logger.error(f"Wake word config not found: {config_path}")
            return

        try:
            # Read config to get wake word phrase
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                self._wake_word_phrase = config.get('wake_word', model_name)

            # Load model
            self._model = MicroWakeWord.from_config(config_path)
            self._features = MicroWakeWordFeatures()

            logger.info(f"Wake word detector initialized: '{self._wake_word_phrase}' ({model_name})")

        except Exception as e:
            logger.error(f"Failed to initialize wake word model: {e}")
            self._model = None

    def on_wake_word(self, callback: Callable[[str], None]) -> None:
        """
        Register wake word callback

        Args:
            callback: Callback function when wake word is detected, receives wake word phrase
        """
        self._on_wake_word = callback

    def process_audio(self, audio_chunk: bytes) -> bool:
        """
        Process audio and detect wake word

        Args:
            audio_chunk: Audio data (bytes, 16-bit PCM, 16kHz mono)

        Returns:
            bool: Whether wake word was detected
        """
        if self._model is None or self._features is None:
            return False

        try:
            # Extract features from raw audio bytes
            features = self._features.process_streaming(audio_chunk)

            # Process each feature frame
            for feature in features:
                if self._model.process_streaming(feature):
                    logger.info(f"Wake word detected: {self._wake_word_phrase}")
                    if self._on_wake_word:
                        self._on_wake_word(self._wake_word_phrase)
                    return True

            return False

        except Exception as e:
            logger.error(f"Wake word detection failed: {e}")
            return False

    def reset(self) -> None:
        """Reset detector state"""
        # MicroWakeWord doesn't have a reset method, but we can recreate features
        if _microwakeword_available:
            self._features = MicroWakeWordFeatures()

    @property
    def wake_word_phrase(self) -> str:
        """Get the wake word phrase"""
        return self._wake_word_phrase

    @staticmethod
    def list_available_models(wakeword_dir: Optional[Path] = None) -> list:
        """
        List available wake word models

        Args:
            wakeword_dir: Directory containing wake word models

        Returns:
            list: List of (model_name, wake_word_phrase) tuples
        """
        wakeword_dir = wakeword_dir or DEFAULT_WAKEWORD_DIR
        models = []

        if not wakeword_dir.exists():
            return models

        for json_file in wakeword_dir.glob("*.json"):
            model_name = json_file.stem
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    wake_word = config.get('wake_word', model_name)
                    models.append((model_name, wake_word))
            except Exception:
                models.append((model_name, model_name))

        return models

    @staticmethod
    def is_available() -> bool:
        """Check if wake word detection is available"""
        return _microwakeword_available


if __name__ == "__main__":
    # Test code
    logging.basicConfig(level=logging.INFO)

    def test_detector():
        """Test wake word detector"""
        logger.info("Testing wake word detector")

        if not WakeWordDetector.is_available():
            logger.error("pymicro-wakeword not available")
            return

        # List available models
        models = WakeWordDetector.list_available_models()
        logger.info(f"Available models ({len(models)}):")
        for model_name, wake_word in models:
            logger.info(f"  - {model_name}: '{wake_word}'")

        # Create detector
        detector = WakeWordDetector('okay_nabu')

        def on_detected(wake_word: str):
            logger.info(f"Callback: Wake word '{wake_word}' detected!")

        detector.on_wake_word(on_detected)

        # Simulate audio data processing
        logger.info("\nProcessing silence (should not detect)...")
        audio_data = np.zeros(1024, dtype=np.int16)
        detected = detector.process_audio(audio_data)
        logger.info(f"Detected: {detected}")

    # Run test
    test_detector()
