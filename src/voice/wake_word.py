"""
Wake Word Detection Module

Supports both pymicro-wakeword and pyopen-wakeword for wake word detection.
"""

import json
import logging
import os
import platform
from pathlib import Path
from typing import Callable, Dict, Optional, Union

import numpy as np

logger = logging.getLogger(__name__)

# Default wake word directory (relative to src/)
DEFAULT_WAKEWORD_DIR = Path(__file__).parent.parent / "wakewords"
DEFAULT_OPEN_WAKEWORD_DIR = DEFAULT_WAKEWORD_DIR / "openWakeWord"


def _get_user_data_dir() -> Path:
    """Get the app data directory used for user-managed files."""
    home = Path(os.path.expanduser("~"))
    system = platform.system()

    if system == "Windows":
        return home / "AppData" / "Local" / "HomeAssistantWindows"
    if system == "Darwin":
        return home / "Library" / "Logs" / "HomeAssistantWindows"
    return home / ".local" / "state" / "HomeAssistantWindows"


USER_WAKEWORD_MODELS_DIR = _get_user_data_dir() / "WakeWordModels"
USER_MICRO_WAKEWORD_DIR = USER_WAKEWORD_MODELS_DIR / "MicroWakeWord"
USER_OPEN_WAKEWORD_DIR = USER_WAKEWORD_MODELS_DIR / "OpenWakeWord"

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
    if wakeword_dir is not None:
        return _load_public_wake_words_from_directory(wakeword_dir)

    USER_MICRO_WAKEWORD_DIR.mkdir(parents=True, exist_ok=True)
    USER_OPEN_WAKEWORD_DIR.mkdir(parents=True, exist_ok=True)

    wake_words: Dict[str, AvailableWakeWord] = {}
    for directory in (
        DEFAULT_WAKEWORD_DIR,
        DEFAULT_OPEN_WAKEWORD_DIR,
        USER_MICRO_WAKEWORD_DIR,
        USER_OPEN_WAKEWORD_DIR,
    ):
        loaded = _load_public_wake_words_from_directory(directory)
        for model_id, wake_word in loaded.items():
            if model_id in wake_words:
                logger.warning(
                    "Wake word '%s' from %s overrides existing definition",
                    model_id,
                    directory,
                )
            wake_words[model_id] = wake_word

    logger.info(
        "Loaded %d wake word models from built-in and user directories under %s",
        len(wake_words),
        USER_WAKEWORD_MODELS_DIR,
    )
    return wake_words


def load_wake_word(model_name: str, wakeword_dir: Optional[Path] = None) -> Optional[AvailableWakeWord]:
    """Load a single wake word model, including internal-only models like stop."""
    directories = (wakeword_dir,) if wakeword_dir is not None else (
        DEFAULT_WAKEWORD_DIR,
        DEFAULT_OPEN_WAKEWORD_DIR,
        USER_MICRO_WAKEWORD_DIR,
        USER_OPEN_WAKEWORD_DIR,
    )

    for directory in directories:
        loaded = _load_wake_words_from_directory(directory)
        wake_word = loaded.get(model_name)
        if wake_word is not None:
            return wake_word

    return None


def _load_public_wake_words_from_directory(wakeword_dir: Path) -> Dict[str, AvailableWakeWord]:
    """Load public wake words from a single directory."""
    wake_words = _load_wake_words_from_directory(wakeword_dir)
    wake_words.pop("stop", None)
    return wake_words


def _load_wake_words_from_directory(wakeword_dir: Path) -> Dict[str, AvailableWakeWord]:
    """Load wake word definitions from a single directory."""
    wake_words: Dict[str, AvailableWakeWord] = {}

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
            wake_word_path = json_file

            if ww_type == WakeWordType.MICRO_WAKE_WORD:
                model_file = config.get('model')
                if model_file:
                    model_path = json_file.parent / model_file
                    if not model_path.exists():
                        logger.error(f"MicroWakeWord model file not found: {model_path}")
                        continue

            if ww_type == WakeWordType.OPEN_WAKE_WORD:
                model_file = config.get('model')
                if not model_file:
                    logger.error(f"OpenWakeWord config missing model field: {json_file}")
                    continue
                wake_word_path = json_file.parent / model_file
                if not wake_word_path.exists():
                    logger.error(f"OpenWakeWord model file not found: {wake_word_path}")
                    continue

            wake_words[model_id] = AvailableWakeWord(
                id=model_id,
                type=ww_type,
                wake_word=wake_word,
                trained_languages=trained_languages,
                wake_word_path=wake_word_path,
            )
            logger.debug(f"Loaded wake word: {model_id} -> '{wake_word}'")

        except Exception as e:
            logger.error(f"Failed to load wake word config {json_file}: {e}")

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
            wakeword_dir: Optional directory containing wake word models
        """
        self.model_name = model_name
        self.wakeword_dir = wakeword_dir
        self._on_wake_word: Optional[Callable[[str], None]] = None
        self._wake_word_phrase: str = model_name
        self._last_detection_logged = False  # Track if we already logged this detection

        # Detector type and model
        self._detector_type: Optional[str] = None
        self._model: Optional[Union[MicroWakeWord, OpenWakeWord]] = None
        self._features: Optional[Union[MicroWakeWordFeatures, OpenWakeWordFeatures]] = None

        # Load wake word info
        wake_word_info = load_wake_word(model_name, self.wakeword_dir)
        if wake_word_info is None:
            logger.error(f"Wake word model not found: {model_name}")
            return

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
            self._features = OpenWakeWordFeatures.from_builtin()
            logger.debug(f"Wake word detector initialized (OpenWakeWord): '{self._wake_word_phrase}' ({self.model_name})")
        except Exception as e:
            logger.error(f"Failed to initialize OpenWakeWord: {e}")
            self._model = None
            self._features = None

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
        embeddings = self._features.process_streaming(audio_chunk)

        for embedding in embeddings:
            for prob in self._model.process_streaming(embedding):
                if prob <= 0.5:
                    continue

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
            self._features = OpenWakeWordFeatures.from_builtin()
        self._last_detection_logged = False

    def close(self) -> None:
        """Release detector resources held by native wake word libraries."""
        for attr in ("_features", "_model"):
            resource = getattr(self, attr, None)
            if resource is None:
                continue

            close = getattr(resource, "close", None)
            if callable(close):
                try:
                    close()
                except Exception as e:
                    logger.debug(f"Failed to close {attr} for {self.model_name}: {e}")

            setattr(self, attr, None)

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
        wake_words = load_available_wake_words(wakeword_dir)
        return [(model_id, wake_word.wake_word) for model_id, wake_word in wake_words.items()]

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
