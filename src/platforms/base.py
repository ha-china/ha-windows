"""
Platform Abstraction Base Class
Defines the interface for platform-specific implementations
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, List, Callable
from dataclasses import dataclass


@dataclass
class Notification:
    """Notification data structure"""
    title: str
    message: str
    icon_path: Optional[str] = None
    image_url: Optional[str] = None
    duration: int = 5


@dataclass
class AudioDevice:
    """Audio device information"""
    name: str
    id: str
    is_input: bool
    is_output: bool


class PlatformBase(ABC):
    """
    Platform abstraction base class
    
    All platform-specific implementations must inherit from this class
    and implement all abstract methods.
    """
    
    @abstractmethod
    def get_platform_name(self) -> str:
        """
        Get platform name
        
        Returns:
            str: Platform name (e.g., "Windows", "macOS", "Linux")
        """
        pass
    
    # ========== Notification System ==========
    
    @abstractmethod
    def show_notification(self, notification: Notification) -> bool:
        """
        Show system notification
        
        Args:
            notification: Notification data
            
        Returns:
            bool: True if successful, False otherwise
        """
        pass
    
    # ========== Audio Control ==========
    
    @abstractmethod
    def get_volume(self) -> int:
        """
        Get system volume level
        
        Returns:
            int: Volume level (0-100)
        """
        pass
    
    @abstractmethod
    def set_volume(self, volume: int) -> bool:
        """
        Set system volume level
        
        Args:
            volume: Volume level (0-100)
            
        Returns:
            bool: True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    def list_audio_devices(self) -> Dict[str, List[str]]:
        """
        List all audio devices
        
        Returns:
            Dict with 'input_devices' and 'output_devices' lists
        """
        pass
    
    @abstractmethod
    def set_audio_output_device(self, device_name: str) -> bool:
        """
        Set audio output device
        
        Args:
            device_name: Device name
            
        Returns:
            bool: True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    def set_audio_input_device(self, device_name: str) -> bool:
        """
        Set audio input device
        
        Args:
            device_name: Device name
            
        Returns:
            bool: True if successful, False otherwise
        """
        pass
    
    # ========== Autostart ==========
    
    @abstractmethod
    def enable_autostart(self) -> bool:
        """
        Enable application autostart
        
        Returns:
            bool: True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    def disable_autostart(self) -> bool:
        """
        Disable application autostart
        
        Returns:
            bool: True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    def is_autostart_enabled(self) -> bool:
        """
        Check if autostart is enabled
        
        Returns:
            bool: True if enabled, False otherwise
        """
        pass
    
    @abstractmethod
    def get_exe_path(self) -> Optional[str]:
        """
        Get path to the running executable
        
        Returns:
            str: Path to executable, or None if not running as frozen
        """
        pass
    
    # ========== System Commands ==========
    
    @abstractmethod
    def shutdown(self) -> bool:
        """
        Shutdown system
        
        Returns:
            bool: True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    def restart(self) -> bool:
        """
        Restart system
        
        Returns:
            bool: True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    def sleep(self) -> bool:
        """
        Sleep/Standby system
        
        Returns:
            bool: True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    def hibernate(self) -> bool:
        """
        Hibernate system
        
        Returns:
            bool: True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    def lock_screen(self) -> bool:
        """
        Lock screen
        
        Returns:
            bool: True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    def logoff(self) -> bool:
        """
        Log off current user
        
        Returns:
            bool: True if successful, False otherwise
        """
        pass
    
    # ========== System Tray ==========
    
    @abstractmethod
    def create_tray_icon(self, callback: Optional[Callable] = None):
        """
        Create system tray icon
        
        Args:
            callback: Callback function for icon events
        """
        pass
    
    @abstractmethod
    def update_tray_icon(self, **kwargs):
        """
        Update tray icon
        
        Args:
            **kwargs: Icon properties to update
        """
        pass
    
    @abstractmethod
    def show_tray_notification(self, title: str, message: str):
        """
        Show tray notification
        
        Args:
            title: Notification title
            message: Notification message
        """
        pass
    
    # ========== Utility Methods ==========
    
    def is_platform_supported(self) -> bool:
        """
        Check if platform is fully supported
        
        Returns:
            bool: True if platform is supported
        """
        return True
    
    def get_platform_info(self) -> Dict[str, str]:
        """
        Get platform information
        
        Returns:
            Dict with platform details
        """
        import platform as plt
        return {
            'system': plt.system(),
            'release': plt.release(),
            'version': plt.version(),
            'machine': plt.machine(),
            'processor': plt.processor(),
        }