"""
Platform Abstraction Layer
Provides platform-specific implementations for cross-platform support
"""

import platform
import sys
from typing import Optional
from src.platforms.base import PlatformBase, Notification

# Import platform-specific implementations
from src.platforms.windows import WindowsPlatform
from src.platforms.macos import MacOSPlatform

# Platform detection
def get_platform() -> str:
    """Get current platform name"""
    return platform.system()

def get_platform_implementation() -> PlatformBase:
    """
    Get platform-specific implementation
    
    Returns:
        PlatformBase: Platform-specific implementation instance
    """
    current_platform = get_platform()
    
    if current_platform == "Windows":
        return WindowsPlatform()
    elif current_platform == "Darwin":  # macOS
        return MacOSPlatform()
    else:
        # Fallback to Windows for other platforms (or raise error)
        print(f"Warning: Unsupported platform {current_platform}, using Windows implementation")
        return WindowsPlatform()

# Singleton instance
_platform_instance: Optional[PlatformBase] = None

def get_platform_instance() -> PlatformBase:
    """
    Get singleton platform instance
    
    Returns:
        PlatformBase: Platform implementation instance
    """
    global _platform_instance
    if _platform_instance is None:
        _platform_instance = get_platform_implementation()
    return _platform_instance

# Convenience functions
def show_notification(title: str, message: str) -> bool:
    """Show platform notification"""
    platform = get_platform_instance()
    from src.platforms.base import Notification
    return platform.show_notification(Notification(title=title, message=message))

def get_volume() -> int:
    """Get system volume (0-100)"""
    return get_platform_instance().get_volume()

def set_volume(volume: int) -> bool:
    """Set system volume (0-100)"""
    return get_platform_instance().set_volume(volume)

def enable_autostart() -> bool:
    """Enable autostart"""
    return get_platform_instance().enable_autostart()

def disable_autostart() -> bool:
    """Disable autostart"""
    return get_platform_instance().disable_autostart()

def is_autostart_enabled() -> bool:
    """Check if autostart is enabled"""
    return get_platform_instance().is_autostart_enabled()

def shutdown() -> bool:
    """Shutdown system"""
    return get_platform_instance().shutdown()

def restart() -> bool:
    """Restart system"""
    return get_platform_instance().restart()

def sleep() -> bool:
    """Sleep system"""
    return get_platform_instance().sleep()

def lock_screen() -> bool:
    """Lock screen"""
    return get_platform_instance().lock_screen()

def hibernate() -> bool:
    """Hibernate system"""
    return get_platform_instance().hibernate()

def logoff() -> bool:
    """Log off"""
    return get_platform_instance().logoff()