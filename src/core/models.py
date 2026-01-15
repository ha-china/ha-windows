"""
共享数据模型

参考 linux-voice-assistant 的 models.py
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


# Windows 音量控制
try:
    from pycaw.pycaw import AudioUtilities
    PYCAW_AVAILABLE = True
except ImportError:
    PYCAW_AVAILABLE = False
    logger.warning("pycaw not available, duck/unduck will be disabled")


class WakeWordType(str, Enum):
    """唤醒词类型"""
    MICRO_WAKE_WORD = "micro"
    OPEN_WAKE_WORD = "openWakeWord"


@dataclass
class AvailableWakeWord:
    """可用的唤醒词"""
    id: str
    type: WakeWordType
    wake_word: str
    trained_languages: List[str]
    wake_word_path: Optional[Path] = None

    def load(self) -> Any:
        """加载唤醒词模型"""
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
    """用户偏好设置"""
    active_wake_words: List[str] = field(default_factory=list)


class WindowsVolumeController:
    """Windows 系统音量控制器 (使用 pycaw)"""
    
    _instance: Optional["WindowsVolumeController"] = None
    _lock = Lock()
    
    def __new__(cls) -> "WindowsVolumeController":
        """单例模式"""
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
        self._duck_ratio: float = 0.3  # Duck 到原音量的 30%
        self._init_lock = Lock()
        self._initialized = True
        
        self._init_volume_interface()
    
    def _init_volume_interface(self) -> None:
        """初始化音量接口"""
        if not PYCAW_AVAILABLE:
            logger.warning("pycaw not available, volume control disabled")
            return
        
        try:
            devices = AudioUtilities.GetSpeakers()
            # 新版 pycaw 使用 EndpointVolume 属性
            self._volume_interface = devices.EndpointVolume
            logger.info("Windows volume controller initialized")
        except Exception as e:
            logger.error(f"Failed to initialize volume interface: {e}")
            self._volume_interface = None
    
    def get_volume(self) -> float:
        """获取当前音量 (0.0-1.0)"""
        if self._volume_interface is None:
            return 1.0
        
        try:
            return self._volume_interface.GetMasterVolumeLevelScalar()
        except Exception as e:
            logger.error(f"Failed to get volume: {e}")
            return 1.0
    
    def set_volume(self, volume: float) -> None:
        """设置音量 (0.0-1.0)"""
        if self._volume_interface is None:
            return
        
        try:
            volume = max(0.0, min(1.0, volume))
            self._volume_interface.SetMasterVolumeLevelScalar(volume, None)
            logger.debug(f"Volume set to {volume:.2f}")
        except Exception as e:
            logger.error(f"Failed to set volume: {e}")
    
    def duck(self) -> None:
        """降低系统音量 (Duck)"""
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
        """恢复系统音量 (Unduck)"""
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


# 全局音量控制器实例
_volume_controller: Optional[WindowsVolumeController] = None


def get_volume_controller() -> WindowsVolumeController:
    """获取全局音量控制器"""
    global _volume_controller
    if _volume_controller is None:
        _volume_controller = WindowsVolumeController()
    return _volume_controller


class AudioPlayer:
    """音频播放器接口"""
    
    def __init__(self):
        self._volume = 100
        self._duck_volume = 50
        self._is_playing = False
        self._done_callback: Optional[Callable] = None
        self._volume_controller = get_volume_controller()
        self._play_thread: Optional[Any] = None
    
    @property
    def is_playing(self) -> bool:
        return self._is_playing
    
    def play(self, url: str, done_callback: Optional[Callable] = None) -> None:
        """播放音频"""
        import threading
        
        logger.info(f"Playing: {url}")
        self._is_playing = True
        self._done_callback = done_callback
        
        # 在后台线程中播放
        self._play_thread = threading.Thread(
            target=self._play_audio,
            args=(url,),
            daemon=True
        )
        self._play_thread.start()
    
    def _play_audio(self, url: str) -> None:
        """实际播放音频（在后台线程中）"""
        import tempfile
        import os
        
        temp_file = None
        try:
            # 如果是 HTTP URL，先下载
            if url.startswith(('http://', 'https://')):
                import urllib.request
                
                # 根据 URL 判断文件类型
                if '.mp3' in url.lower():
                    suffix = '.mp3'
                elif '.wav' in url.lower():
                    suffix = '.wav'
                elif '.flac' in url.lower():
                    suffix = '.flac'
                elif '.ogg' in url.lower():
                    suffix = '.ogg'
                else:
                    suffix = '.mp3'  # 默认 mp3
                
                # 下载到临时文件
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
                    temp_file = f.name
                
                logger.info(f"Downloading audio from: {url}")
                urllib.request.urlretrieve(url, temp_file)
                file_to_play = temp_file
            else:
                file_to_play = url
            
            if not os.path.exists(file_to_play):
                logger.error(f"File not found: {file_to_play}")
                return
            
            logger.info(f"Playing file: {file_to_play}")
            
            # 尝试用 pygame 播放（支持 mp3/wav/ogg）
            try:
                import pygame
                if not pygame.mixer.get_init():
                    pygame.mixer.init()
                pygame.mixer.music.load(file_to_play)
                pygame.mixer.music.play()
                # 等待播放完成
                while pygame.mixer.music.get_busy():
                    import time
                    time.sleep(0.1)
                logger.info("Playback finished")
            except ImportError:
                # pygame 不可用，尝试 winsound（仅支持 wav）
                import winsound
                if file_to_play.lower().endswith('.wav'):
                    winsound.PlaySound(file_to_play, winsound.SND_FILENAME)
                    logger.info("Playback finished")
                else:
                    logger.error(f"Cannot play {file_to_play}: pygame not available and winsound only supports WAV")
        
        except Exception as e:
            logger.error(f"Playback error: {e}")
        
        finally:
            # 清理临时文件
            if temp_file and os.path.exists(temp_file):
                try:
                    os.unlink(temp_file)
                except Exception:
                    pass
            
            # 调用完成回调
            self._on_playback_finished()
    
    def stop(self) -> None:
        """停止播放"""
        logger.info("Stopping playback")
        try:
            import winsound
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception as e:
            logger.error(f"Stop error: {e}")
        self._is_playing = False
    
    def pause(self) -> None:
        """暂停播放"""
        logger.info("Pausing playback")
        self._is_playing = False
    
    def resume(self) -> None:
        """恢复播放"""
        logger.info("Resuming playback")
        self._is_playing = True
    
    def duck(self) -> None:
        """降低系统音量"""
        self._volume_controller.duck()
    
    def unduck(self) -> None:
        """恢复系统音量"""
        self._volume_controller.unduck()
    
    def set_volume(self, volume: int) -> None:
        """设置音量 (0-100)"""
        self._volume = max(0, min(100, volume))
        self._duck_volume = self._volume // 2
        logger.debug(f"Volume set to {self._volume}")
    
    def _on_playback_finished(self) -> None:
        """播放完成回调"""
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
    服务器状态管理
    
    参考 linux-voice-assistant 的 ServerState
    """
    name: str
    mac_address: str
    
    # 音频队列
    audio_queue: "Queue[Optional[bytes]]" = field(default_factory=Queue)
    
    # 实体列表
    entities: List[Any] = field(default_factory=list)
    
    # 唤醒词
    available_wake_words: Dict[str, AvailableWakeWord] = field(default_factory=dict)
    wake_words: Dict[str, Any] = field(default_factory=dict)
    active_wake_words: Set[str] = field(default_factory=set)
    stop_word: Optional[Any] = None
    
    # 音频播放器
    music_player: AudioPlayer = field(default_factory=AudioPlayer)
    tts_player: AudioPlayer = field(default_factory=AudioPlayer)
    
    # 音效
    wakeup_sound: str = ""
    timer_finished_sound: str = ""
    
    # 偏好设置
    preferences: Preferences = field(default_factory=Preferences)
    preferences_path: Path = field(default_factory=lambda: Path("preferences.json"))
    download_dir: Path = field(default_factory=lambda: Path("downloads"))
    
    # 实体引用
    media_player_entity: Optional[Any] = None
    satellite: Optional["ESPHomeProtocol"] = None
    
    # 状态标志
    wake_words_changed: bool = False
    refractory_seconds: float = 2.0
    
    def save_preferences(self) -> None:
        """保存偏好设置"""
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
        """加载偏好设置"""
        if not self.preferences_path.exists():
            return
        
        try:
            with open(self.preferences_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.preferences.active_wake_words = data.get("active_wake_words", [])
        except Exception as e:
            logger.error(f"Failed to load preferences: {e}")
