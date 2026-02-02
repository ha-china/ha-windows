"""
Auto-startup management for Home Assistant
Handles platform-specific auto-startup (Windows registry, macOS launchd, etc.)
"""

import os
import sys
from typing import Optional

# Import platform abstraction layer
try:
    from src.platforms import get_platform_instance
    PLATFORM_AVAILABLE = True
except ImportError:
    PLATFORM_AVAILABLE = False


class AutoStartManager:
    """
    Manages application auto-startup across platforms
    
    Uses platform abstraction layer for cross-platform support.
    Falls back to Windows-specific implementation for backward compatibility.
    """

    # Legacy Windows-specific constants (for backward compatibility)
    REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
    APP_NAME = "HomeAssistantWindows"

    @classmethod
    def get_exe_path(cls) -> Optional[str]:
        """
        Get the path to the running executable
        Returns None if not running as frozen (development mode)
        """
        if getattr(sys, 'frozen', False):
            # Running as compiled EXE or App
            return sys.executable
        else:
            # Running in development mode
            # Return the Python script path
            return os.path.abspath(os.path.join(os.path.dirname(__file__), '__main__.py'))

    @classmethod
    def is_enabled(cls) -> bool:
        """
        Check if auto-startup is enabled
        Returns True if the application is configured for auto-startup
        """
        if PLATFORM_AVAILABLE:
            try:
                platform = get_platform_instance()
                return platform.is_autostart_enabled()
            except Exception as e:
                print(f"Platform abstraction failed: {e}, falling back to legacy")
        
        # Fallback to Windows-specific implementation
        return cls._is_enabled_windows()

    @classmethod
    def enable(cls) -> bool:
        """
        Enable auto-startup
        Returns True on success, False on failure
        """
        if PLATFORM_AVAILABLE:
            try:
                platform = get_platform_instance()
                return platform.enable_autostart()
            except Exception as e:
                print(f"Platform abstraction failed: {e}, falling back to legacy")
        
        # Fallback to Windows-specific implementation
        return cls._enable_windows()

    @classmethod
    def disable(cls) -> bool:
        """
        Disable auto-startup
        Returns True on success, False on failure
        """
        if PLATFORM_AVAILABLE:
            try:
                platform = get_platform_instance()
                return platform.disable_autostart()
            except Exception as e:
                print(f"Platform abstraction failed: {e}, falling back to legacy")
        
        # Fallback to Windows-specific implementation
        return cls._disable_windows()

    @classmethod
    def toggle(cls) -> bool:
        """
        Toggle auto-startup
        Returns the new state (True if enabled, False if disabled)
        """
        if cls.is_enabled():
            cls.disable()
            return False
        else:
            cls.enable()
            return True

    # ========== Windows-specific fallback methods ==========
    
    @classmethod
    def _is_enabled_windows(cls) -> bool:
        """Windows-specific check for auto-startup"""
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, cls.REGISTRY_KEY) as key:
                value, _ = winreg.QueryValueEx(key, cls.APP_NAME)
                exe_path = cls.get_exe_path()
                return value == exe_path
        except (FileNotFoundError, OSError):
            return False

    @classmethod
    def _enable_windows(cls) -> bool:
        """Windows-specific enable auto-startup"""
        try:
            import winreg
            exe_path = cls.get_exe_path()
            if not exe_path:
                return False

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                cls.REGISTRY_KEY,
                0,
                winreg.KEY_SET_VALUE
            ) as key:
                winreg.SetValueEx(
                    key,
                    cls.APP_NAME,
                    0,
                    winreg.REG_SZ,
                    exe_path
                )
            return True
        except Exception as e:
            print(f"Failed to enable auto-startup: {e}")
            return False

    @classmethod
    def _disable_windows(cls) -> bool:
        """Windows-specific disable auto-startup"""
        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                cls.REGISTRY_KEY,
                0,
                winreg.KEY_SET_VALUE
            ) as key:
                winreg.DeleteValue(key, cls.APP_NAME)
            return True
        except (FileNotFoundError, OSError):
            # Already disabled
            return True
        except Exception as e:
            print(f"Failed to disable auto-startup: {e}")
            return False


def enable_autostart() -> bool:
    """Enable auto-startup (convenience function)"""
    return AutoStartManager.enable()


def disable_autostart() -> bool:
    """Disable auto-startup (convenience function)"""
    return AutoStartManager.disable()


def is_autostart_enabled() -> bool:
    """Check if auto-startup is enabled (convenience function)"""
    return AutoStartManager.is_enabled()


def toggle_autostart() -> bool:
    """Toggle auto-startup (convenience function)"""
    return AutoStartManager.toggle()


if __name__ == "__main__":
    # Test the auto-startup manager
    print(f"Current auto-startup status: {is_autostart_enabled()}")
    
    if is_autostart_enabled():
        print("Disabling auto-startup...")
        if disable_autostart():
            print("Auto-startup disabled successfully")
        else:
            print("Failed to disable auto-startup")
    else:
        print("Enabling auto-startup...")
        if enable_autostart():
            print("Auto-startup enabled successfully")
        else:
            print("Failed to enable auto-startup")
    
    print(f"New auto-startup status: {is_autostart_enabled()}")