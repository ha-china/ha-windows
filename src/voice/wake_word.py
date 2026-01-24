"""
Wake Word Detection Module

Supports both pymicro-wakeword and pyopen-wakeword for wake word detection.
"""

import json
import logging
from pathlib import Path
from typing import Callable, Dict, Optional, Union

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

# Try to import pyopen-wakeword
_openwakeword_available = False
try:
    from pyopen_wakeword import OpenWakeWord, OpenWakeWordFeatures
    _openwakeword_available = True
    logger.info("pyopen-wakeword available for wake word detection")
except ImportError:
    logger.warning("pyopen-wakeword not available")

# Import models for type hints
from src.core.models import AvailableWakeWord, WakeWordType


def load_available_wake_words(wakeword_dir: Optional[Path] = None) -> Dict[str, AvailableWakeWord]:
    """
    Load all available wake words from wakewords directory

    Args:
        wakeword_dir: Directory containing wake word models

    Returns:
        Dict mapping wake word ID to AvailableWakeWord
    """
    wakeword_dir = wakeword_dir or DEFAULT_WAKEWORD_DIR
    wake_words = {}

    if not wakeword_dir.exists():
        logger.warning(f"Wake word directory not found: {wakeword_dir}")
        return wake_words

    for json_file in wakeword_dir.glob("*.json"):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                config = json.load(f)

            model_id = json_file.stem
            wake_word = config.get('wake_word', model_id)
            trained_languages = config.get('trained_languages', ['en'])
            model_type = config.get('type', 'micro')

            ww_type = WakeWordType.MICRO_WAKE_WORD if model_type == 'micro' else WakeWordType.OPEN_WAKE_WORD

            wake_words[model_id] = AvailableWakeWord(
                id=model_id,
                type=ww_type,
                wake_word=wake_word,
                trained_languages=trained_languages,
                wake_word_path=json_file,
            )
            logger.debug(f"Loaded wake word: {model_id} -> '{wake_word}'")

        except Exception as e:
            logger.error(f"Failed to load wake word config {json_file}: {e}")

    logger.info(f"Loaded {len(wake_words)} wake word models")
    return wake_words


class WakeWordDetector:
    """Wake word detector supporting both MicroWakeWord and OpenWakeWord"""

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
        self._wake_word_phrase: str = model_name
        self._last_detection_logged = False  # Track if we already logged this detection

        # Detector type and model
        self._detector_type: Optional[str] = None
        self._model: Optional[Union[MicroWakeWord, OpenWakeWord]] = None
        self._features: Optional[Union[MicroWakeWordFeatures, OpenWakeWordFeatures]] = None

        # Load wake word info
        wake_words = load_available_wake_words(self.wakeword_dir)
        if model_name not in wake_words:
            logger.error(f"Wake word model not found: {model_name}")
            return

        wake_word_info = wake_words[model_name]
        self._wake_word_phrase = wake_word_info.wake_word
        self._detector_type = wake_word_info.type

        # Initialize detector based on type
        if self._detector_type == WakeWordType.MICRO_WAKE_WORD:
            self._init_micro_wakeword(wake_word_info)
        elif self._detector_type == WakeWordType.OPEN_WAKE_WORD:
            self._init_open_wakeword(wake_word_info)
        else:
            logger.error(f"Unknown wake word type: {self._detector_type}")

    def _init_micro_wakeword(self, wake_word_info: AvailableWakeWord) -> None:
        """Initialize MicroWakeWord detector"""
        if not _microwakeword_available:
            logger.warning("pymicro-wakeword not installed")
            return

        try:
            # Load model
            self._model = MicroWakeWord.from_config(wake_word_info.wake_word_path)
            self._features = MicroWakeWordFeatures()
            logger.debug(f"Wake word detector initialized (MicroWakeWord): '{self._wake_word_phrase}' ({self.model_name})")
        except Exception as e:
            logger.error(f"Failed to initialize MicroWakeWord: {e}")
            self._model = None

    def _init_open_wakeword(self, wake_word_info: AvailableWakeWord) -> None:
        """Initialize OpenWakeWord detector"""
        if not _openwakeword_available:
            logger.warning("pyopen-wakeword not installed")
            return

        try:
            # Load model
            self._model = OpenWakeWord.from_model(model_path=wake_word_info.wake_word_path)
            self._features = OpenWakeWordFeatures()
            logger.debug(f"Wake word detector initialized (OpenWakeWord): '{self._wake_word_phrase}' ({self.model_name})")
        except Exception as e:
            logger.error(f"Failed to initialize OpenWakeWord: {e}")
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
            # Process based on detector type
            if self._detector_type == "micro":
                return self._process_micro_wakeword(audio_chunk)
            elif self._detector_type == "openWakeWord":
                return self._process_open_wakeword(audio_chunk)
            else:
                return False

        except Exception as e:
            logger.error(f"Wake word detection failed: {e}")
            return False

    def _process_micro_wakeword(self, audio_chunk: bytes) -> bool:
        """Process audio with MicroWakeWord detector"""
        # Extract features from raw audio bytes
        features = self._features.process_streaming(audio_chunk)

        # Process each feature frame
        detected = False
        for feature in features:
            if self._model.process_streaming(feature):
                detected = True
                # Only log once per detection sequence
                if not self._last_detection_logged:
                    logger.info(f"Wake word detected: {self._wake_word_phrase}")
                    self._last_detection_logged = True
                if self._on_wake_word:
                    self._on_wake_word(self._wake_word_phrase)
                break  # Stop processing after first detection

        # Reset flag if no detection (allows next detection to be logged)
        if not detected and self._last_detection_logged:
            self._last_detection_logged = False

        return detected

    def _process_open_wakeword(self, audio_chunk: bytes) -> bool:
        """Process audio with OpenWakeWord detector"""
        # Convert audio bytes to numpy array
        audio_array = np.frombuffer(audio_chunk, dtype=np.int16).astype(np.float32) / 32768.0

        # Extract features
        oww_inputs = self._features.process_streaming(audio_array)

        # Process each input
        for prob in oww_inputs:
            if prob > 0.5:  # Detection threshold
                # Only log once per detection sequence
                if not self._last_detection_logged:
                    logger.info(f"Wake word detected: {self._wake_word_phrase}")
                    self._last_detection_logged = True
                if self._on_wake_word:
                    self._on_wake_word(self._wake_word_phrase)
                return True

        # Reset flag if no detection (allows next detection to be logged)
        if self._last_detection_logged:
            self._last_detection_logged = False

        return False

    def reset(self) -> None:
        """Reset detector state"""
        if self._detector_type == "micro" and _microwakeword_available:
            self._features = MicroWakeWordFeatures()
        elif self._detector_type == "openWakeWord" and _openwakeword_available:
            self._features = OpenWakeWordFeatures()
        self._last_detection_logged = False

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
        return _microwakeword_available or _openwakeword_available


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
