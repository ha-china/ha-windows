"""
Shared Data Models

References linux-voice-assistant's models.py
"""

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from queue import Queue
from threading import Lock
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Any, Callable

if TYPE_CHECKING:
    from .esphome_protocol import ESPHomeProtocol

logger = logging.getLogger(__name__)


# pycaw availability flag (lazy import to avoid COM conflicts)
PYCAW_AVAILABLE = None  # Will be set on first use


def _check_pycaw():
    """Check pycaw availability (lazy import)"""
    global PYCAW_AVAILABLE
    if PYCAW_AVAILABLE is None:
        try:
            from pycaw.pycaw import AudioUtilities  # noqa: F401
            PYCAW_AVAILABLE = True
        except (ImportError, OSError):
            PYCAW_AVAILABLE = False
            logger.warning("pycaw not available, duck/unduck will be disabled")
    return PYCAW_AVAILABLE


class WakeWordType(str, Enum):
    """Wake word type"""
    MICRO_WAKE_WORD = "micro"
    OPEN_WAKE_WORD = "openWakeWord"


@dataclass
class AvailableWakeWord:
    """Available wake word"""
    id: str
    type: WakeWordType
    wake_word: str
    trained_languages: List[str]
    wake_word_path: Optional[Path] = None

    def load(self) -> Any:
        """Load wake word model"""
        if self.type == WakeWordType.MICRO_WAKE_WORD:
            try:
                from pymicro_wakeword import MicroWakeWord
                return MicroWakeWord.from_config(config_path=self.wake_word_path)
            except ImportError:
                logger.warning("pymicro_wakeword not installed")
                return None

        if self.type == WakeWordType.OPEN_WAKE_WORD:
            try:
                from pyopen_wakeword import OpenWakeWord
                oww_model = OpenWakeWord.from_model(model_path=self.wake_word_path)
                setattr(oww_model, "wake_word", self.wake_word)
                return oww_model
            except ImportError:
                logger.warning("pyopen_wakeword not installed")
                return None

        raise ValueError(f"Unexpected wake word type: {self.type}")


@dataclass
class Preferences:
    """User preferences"""
    active_wake_words: List[str] = field(default_factory=list)


class WindowsVolumeController:
    """Windows system volume controller (using pycaw)"""

    _instance: Optional["WindowsVolumeController"] = None
    _lock = Lock()

    def __new__(cls) -> "WindowsVolumeController":
        """Singleton pattern"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._volume_interface: Optional[Any] = None
        self._original_volume: float = 1.0
        self._is_ducked: bool = False
        self._duck_ratio: float = 0.3  # Duck to 30% of original volume
        self._init_lock = Lock()
        self._initialized = True

        self._init_volume_interface()

    def _init_volume_interface(self) -> None:
        """Initialize volume interface"""
        if not _check_pycaw():
            logger.warning("pycaw not available, volume control disabled")
            return

        try:
            from pycaw.pycaw import AudioUtilities
            devices = AudioUtilities.GetSpeakers()
            # New pycaw uses EndpointVolume property
            self._volume_interface = devices.EndpointVolume
            logger.info("Windows volume controller initialized")
        except Exception as e:
            logger.error(f"Failed to initialize volume interface: {e}")
            self._volume_interface = None

    def get_volume(self) -> float:
        """Get current volume (0.0-1.0)"""
        if self._volume_interface is None:
            return 1.0

        try:
            return self._volume_interface.GetMasterVolumeLevelScalar()
        except Exception as e:
            logger.error(f"Failed to get volume: {e}")
            return 1.0

    def set_volume(self, volume: float) -> None:
        """Set volume (0.0-1.0)"""
        if self._volume_interface is None:
            logger.warning("Volume interface not initialized")
            return

        try:
            volume = max(0.0, min(1.0, volume))
            old_volume = self.get_volume()
            self._volume_interface.SetMasterVolumeLevelScalar(volume, None)
            new_volume = self.get_volume()
            logger.info(f"Volume changed: {old_volume:.2f} -> {new_volume:.2f} (requested: {volume:.2f})")
        except Exception as e:
            logger.error(f"Failed to set volume: {e}")

    def duck(self) -> None:
        """Lower system volume (Duck)"""
        with self._init_lock:
            if self._is_ducked:
                logger.debug("Already ducked, skipping")
                return

            self._original_volume = self.get_volume()
            duck_volume = self._original_volume * self._duck_ratio
            self.set_volume(duck_volume)
            self._is_ducked = True
            logger.info(f"Ducked: {self._original_volume:.2f} -> {duck_volume:.2f}")

    def unduck(self) -> None:
        """Restore system volume (Unduck)"""
        with self._init_lock:
            if not self._is_ducked:
                logger.debug("Not ducked, skipping unduck")
                return

            self.set_volume(self._original_volume)
            self._is_ducked = False
            logger.info(f"Unducked: restored to {self._original_volume:.2f}")

    @property
    def is_ducked(self) -> bool:
        return self._is_ducked


# Global volume controller instance
_volume_controller: Optional[WindowsVolumeController] = None


def get_volume_controller() -> WindowsVolumeController:
    """Get global volume controller"""
    global _volume_controller
    if _volume_controller is None:
        _volume_controller = WindowsVolumeController()
    return _volume_controller


class AudioPlayer:
    """Audio player with optional VLC streaming support"""

    def __init__(self):
        self._volume = 100
        self._is_playing = False
        self._done_callback: Optional[Callable] = None
        self._volume_controller = get_volume_controller()
        self._play_thread: Optional[Any] = None

        # Try VLC first (best for streaming, requires VLC installed)
        self._vlc_instance: Optional[Any] = None
        self._vlc_player: Optional[Any] = None
        self._vlc_available = False

        try:
            import vlc
            self._vlc_instance = vlc.Instance('--no-xlib')
            self._vlc_player = self._vlc_instance.media_player_new()
            self._vlc_available = True
            logger.info("VLC player initialized (streaming supported)")
        except Exception as e:
            logger.info(f"VLC not available (install VLC for streaming): {e}")

        # Fallback to pygame
        self._pygame_available = False
        try:
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            self._pygame_available = True
            if not self._vlc_available:
                logger.info("Using pygame for audio (no streaming)")
        except Exception as e:
            logger.warning(f"pygame not available: {e}")

    @property
    def is_playing(self) -> bool:
        if self._vlc_available and self._vlc_player:
            import vlc
            state = self._vlc_player.get_state()
            return state in (vlc.State.Playing, vlc.State.Buffering)
        return self._is_playing

    def play(self, url: str, done_callback: Optional[Callable] = None) -> None:
        """Play audio (true streaming for URLs)"""
        import threading

        logger.info(f"Playing: {url}")
        self._is_playing = True
        self._done_callback = done_callback

        if self._vlc_available:
            # VLC handles streaming natively
            self._play_vlc(url)
        else:
            # Fallback to pygame in background thread
            self._play_thread = threading.Thread(
                target=self._play_pygame,
                args=(url,),
                daemon=True
            )
            self._play_thread.start()

    def _play_vlc(self, url: str) -> None:
        """Play with VLC (true streaming)"""
        import threading

        try:
            import vlc

            media = self._vlc_instance.media_new(url)
            self._vlc_player.set_media(media)
            self._vlc_player.audio_set_volume(self._volume)
            self._vlc_player.play()

            logger.debug("VLC streaming started")

            # Monitor playback in background
            def monitor():
                import time
                time.sleep(0.5)  # Wait for playback to start
                while True:
                    state = self._vlc_player.get_state()
                    if state in (vlc.State.Ended, vlc.State.Stopped, vlc.State.Error):
                        break
                    time.sleep(0.1)
                logger.debug("VLC playback finished")
                self._on_playback_finished()

            threading.Thread(target=monitor, daemon=True).start()

        except Exception as e:
            logger.error(f"VLC playback error: {e}")
            self._on_playback_finished()

    def _play_pygame(self, url: str) -> None:
        """Play with pygame (downloads to memory first)"""
        import io
        import time

        try:
            import pygame

            if url.startswith(('http://', 'https://')):
                import urllib.request
                logger.info(f"Downloading audio: {url}")

                with urllib.request.urlopen(url, timeout=30) as response:
                    audio_data = response.read()

                audio_io = io.BytesIO(audio_data)
                pygame.mixer.music.load(audio_io)
            else:
                pygame.mixer.music.load(url)

            pygame.mixer.music.set_volume(self._volume / 100)
            pygame.mixer.music.play()

            while pygame.mixer.music.get_busy():
                time.sleep(0.1)

            logger.info("pygame playback finished")

        except Exception as e:
            logger.error(f"pygame playback error: {e}")

        finally:
            self._on_playback_finished()

    def stop(self) -> None:
        """Stop playback"""
        logger.info("Stopping playback")
        try:
            if self._vlc_available and self._vlc_player:
                self._vlc_player.stop()
            elif self._pygame_available:
                import pygame
                pygame.mixer.music.stop()
        except Exception as e:
            logger.error(f"Stop error: {e}")
        self._is_playing = False

    def pause(self) -> None:
        """Pause playback"""
        logger.info("Pausing playback")
        try:
            if self._vlc_available and self._vlc_player:
                self._vlc_player.pause()
            elif self._pygame_available:
                import pygame
                pygame.mixer.music.pause()
        except Exception as e:
            logger.error(f"Pause error: {e}")
        self._is_playing = False

    def resume(self) -> None:
        """Resume playback"""
        logger.info("Resuming playback")
        try:
            if self._vlc_available and self._vlc_player:
                self._vlc_player.pause()  # VLC toggle pause
            elif self._pygame_available:
                import pygame
                pygame.mixer.music.unpause()
        except Exception as e:
            logger.error(f"Resume error: {e}")
        self._is_playing = True

    def duck(self) -> None:
        """Lower system volume"""
        self._volume_controller.duck()

    def unduck(self) -> None:
        """Restore system volume"""
        self._volume_controller.unduck()

    def set_volume(self, volume: int) -> None:
        """Set volume (0-100)"""
        self._volume = max(0, min(100, volume))
        try:
            if self._vlc_available and self._vlc_player:
                self._vlc_player.audio_set_volume(self._volume)
            elif self._pygame_available:
                import pygame
                pygame.mixer.music.set_volume(self._volume / 100)
        except Exception as e:
            logger.error(f"Set volume error: {e}")
        logger.debug(f"Volume set to {self._volume}")

    def _on_playback_finished(self) -> None:
        """Playback finished callback"""
        self._is_playing = False
        if self._done_callback:
            try:
                self._done_callback()
            except Exception as e:
                logger.error(f"Error in done callback: {e}")
            finally:
                self._done_callback = None


@dataclass
class ServerState:
    """
    Server state management

    References linux-voice-assistant's ServerState
    """
    name: str
    mac_address: str

    # Audio queue
    audio_queue: "Queue[Optional[bytes]]" = field(default_factory=Queue)

    # Entity list
    entities: List[Any] = field(default_factory=list)

    # Wake words
    available_wake_words: Dict[str, AvailableWakeWord] = field(default_factory=dict)
    wake_words: Dict[str, Any] = field(default_factory=dict)
    active_wake_words: Set[str] = field(default_factory=set)
    stop_word: Optional[Any] = None

    # Audio players
    music_player: AudioPlayer = field(default_factory=AudioPlayer)
    tts_player: AudioPlayer = field(default_factory=AudioPlayer)

    # Sound effects
    wakeup_sound: str = ""
    timer_finished_sound: str = ""

    # Preferences
    preferences: Preferences = field(default_factory=Preferences)
    preferences_path: Path = field(default_factory=lambda: Path("preferences.json"))
    download_dir: Path = field(default_factory=lambda: Path("downloads"))

    # Entity references
    media_player_entity: Optional[Any] = None
    satellite: Optional["ESPHomeProtocol"] = None

    # State flags
    wake_words_changed: bool = False
    refractory_seconds: float = 2.0

    def save_preferences(self) -> None:
        """Save preferences"""
        logger.debug(f"Saving preferences: {self.preferences_path}")
        try:
            self.preferences_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.preferences_path, "w", encoding="utf-8") as f:
                json.dump({
                    "active_wake_words": self.preferences.active_wake_words
                }, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"Failed to save preferences: {e}")

    def load_preferences(self) -> None:
        """Load preferences"""
        if not self.preferences_path.exists():
            return

        try:
            with open(self.preferences_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.preferences.active_wake_words = data.get("active_wake_words", [])
        except Exception as e:
            logger.error(f"Failed to load preferences: {e}")
