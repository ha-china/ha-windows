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


# Windows volume control
try:
    from pycaw.pycaw import AudioUtilities
    PYCAW_AVAILABLE = True
except ImportError:
    PYCAW_AVAILABLE = False
    logger.warning("pycaw not available, duck/unduck will be disabled")


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
        if not PYCAW_AVAILABLE:
            logger.warning("pycaw not available, volume control disabled")
            return
        
        try:
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
            return
        
        try:
            volume = max(0.0, min(1.0, volume))
            self._volume_interface.SetMasterVolumeLevelScalar(volume, None)
            logger.debug(f"Volume set to {volume:.2f}")
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
    """Audio player interface with streaming URL support"""
    
    def __init__(self):
        self._volume = 100
        self._duck_volume = 50
        self._is_playing = False
        self._done_callback: Optional[Callable] = None
        self._volume_controller = get_volume_controller()
        self._play_thread: Optional[Any] = None
        
        # Initialize pygame mixer
        self._pygame_available = False
        try:
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            self._pygame_available = True
        except Exception as e:
            logger.warning(f"pygame not available: {e}")
    
    @property
    def is_playing(self) -> bool:
        return self._is_playing
    
    def play(self, url: str, done_callback: Optional[Callable] = None) -> None:
        """Play audio (supports streaming URLs directly)"""
        import threading
        
        logger.info(f"Playing: {url}")
        self._is_playing = True
        self._done_callback = done_callback
        
        # Play in background thread
        self._play_thread = threading.Thread(
            target=self._play_audio,
            args=(url,),
            daemon=True
        )
        self._play_thread.start()
    
    def _play_audio(self, url: str) -> None:
        """Play audio (supports streaming URLs)"""
        import io
        import time
        
        try:
            if self._pygame_available:
                import pygame
                
                if url.startswith(('http://', 'https://')):
                    # Stream URL to memory and play
                    import urllib.request
                    logger.info(f"Streaming from URL: {url}")
                    
                    with urllib.request.urlopen(url, timeout=30) as response:
                        audio_data = response.read()
                    
                    # Play from memory
                    audio_io = io.BytesIO(audio_data)
                    pygame.mixer.music.load(audio_io)
                    pygame.mixer.music.play()
                else:
                    # Local file
                    logger.info(f"Playing local file: {url}")
                    pygame.mixer.music.load(url)
                    pygame.mixer.music.play()
                
                # Wait for playback to complete
                while pygame.mixer.music.get_busy():
                    time.sleep(0.1)
                
                logger.info("Playback finished")
            else:
                # Fallback: winsound for local WAV files only
                if url.startswith(('http://', 'https://')):
                    logger.error("Cannot stream URL without pygame")
                    return
                
                import winsound
                if url.lower().endswith('.wav'):
                    winsound.PlaySound(url, winsound.SND_FILENAME)
                    logger.info("Playback finished")
                else:
                    logger.error(f"winsound only supports WAV files: {url}")
        
        except Exception as e:
            logger.error(f"Playback error: {e}")
        
        finally:
            self._on_playback_finished()
    
    def stop(self) -> None:
        """Stop playback"""
        logger.info("Stopping playback")
        try:
            if self._pygame_available:
                import pygame
                pygame.mixer.music.stop()
            else:
                import winsound
                winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception as e:
            logger.error(f"Stop error: {e}")
        self._is_playing = False
    
    def pause(self) -> None:
        """Pause playback"""
        logger.info("Pausing playback")
        if self._pygame_available:
            import pygame
            pygame.mixer.music.pause()
        self._is_playing = False
    
    def resume(self) -> None:
        """Resume playback"""
        logger.info("Resuming playback")
        if self._pygame_available:
            import pygame
            pygame.mixer.music.unpause()
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
        self._duck_volume = self._volume // 2
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
