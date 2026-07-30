"""
Windows Platform Implementation
Provides Windows-specific implementations for the platform abstraction layer
"""

import subprocess
import winreg
import sys
import os
import logging
from typing import Optional, Dict, List, Callable

from src.platforms.base import PlatformBase, Notification

logger = logging.getLogger(__name__)


class WindowsPlatform(PlatformBase):
    """Windows platform implementation"""
    
    REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
    APP_NAME = "HomeAssistantWindows"
    
    def __init__(self):
        """Initialize Windows platform"""
        self._tray_icon = None
        logger.info("Windows platform initialized")
    
    # ========== Platform Info ==========
    
    def get_platform_name(self) -> str:
        """Get platform name"""
        return "Windows"
    
    # ========== Notification System ==========
    
    def show_notification(self, notification: Notification) -> bool:
        """
        Show Windows toast notification
        
        Args:
            notification: Notification data
            
        Returns:
            bool: True if successful
        """
        try:
            from windows_toasts import Toast, ToastDisplayImage, InteractableWindowsToaster, ToastImagePosition
            
            toaster = InteractableWindowsToaster("Home Assistant")
            toast = Toast()
            toast.text_fields = [notification.title, notification.message]
            
            # Add icon if available
            if notification.icon_path and os.path.exists(notification.icon_path):
                try:
                    toast.AddImage(ToastDisplayImage.fromPath(
                        notification.icon_path,
                        position=ToastImagePosition.Hero
                    ))
                except Exception as e:
                    logger.warning(f"Failed to add icon to notification: {e}")
            
            toaster.show_toast(toast)
            logger.info(f"Notification shown: {notification.title}")
            return True
            
        except ImportError:
            logger.warning("windows-toasts not available, skipping notification")
            return False
        except Exception as e:
            logger.error(f"Failed to show notification: {e}")
            return False
    
    # ========== Audio Control ==========
    
    def get_volume(self) -> int:
        """
        Get Windows system volume
        
        Returns:
            int: Volume level (0-100)
        """
        try:
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, 1, None)
            volume = interface.QueryInterface(IAudioEndpointVolume)
            
            current_volume = volume.GetMasterVolumeLevelScalar()
            return int(current_volume * 100)
            
        except Exception as e:
            logger.error(f"Failed to get volume: {e}")
            return 50  # Return default volume
    
    def set_volume(self, volume: int) -> bool:
        """
        Set Windows system volume
        
        Args:
            volume: Volume level (0-100)
            
        Returns:
            bool: True if successful
        """
        try:
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            
            # Clamp volume to valid range
            volume = max(0, min(100, volume))
            
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, 1, None)
            volume_control = interface.QueryInterface(IAudioEndpointVolume)
            
            volume_control.SetMasterVolumeLevelScalar(volume / 100.0, None)
            logger.info(f"Volume set to {volume}%")
            return True
            
        except Exception as e:
            logger.error(f"Failed to set volume: {e}")
            return False
    
    def list_audio_devices(self) -> Dict[str, List[str]]:
        """
        List all audio devices on Windows
        
        Returns:
            Dict with 'input_devices' and 'output_devices' lists
        """
        try:
            import soundcard
            
            # Get all output devices
            speakers = soundcard.all_speakers()
            output_devices = [speaker.name for speaker in speakers]
            
            # Get all input devices
            mics = soundcard.all_microphones()
            input_devices = [mic.name for mic in mics]
            
            logger.info(f"Found {len(output_devices)} output devices, {len(input_devices)} input devices")
            
            return {
                'input_devices': input_devices,
                'output_devices': output_devices
            }
            
        except Exception as e:
            logger.error(f"Failed to list audio devices: {e}")
            return {
                'input_devices': [],
                'output_devices': []
            }
    
    def set_audio_output_device(self, device_name: str) -> bool:
        """
        Set audio output device (placeholder)
        
        Note: This requires complex Windows API calls
        Currently just logs the request
        
        Args:
            device_name: Device name
            
        Returns:
            bool: True (placeholder)
        """
        logger.info(f"Request to set audio output to: {device_name}")
        logger.warning("Audio device switching not fully implemented")
        return True
    
    def set_audio_input_device(self, device_name: str) -> bool:
        """
        Set audio input device (placeholder)
        
        Note: This requires reinitializing audio recorder
        
        Args:
            device_name: Device name
            
        Returns:
            bool: True (placeholder)
        """
        logger.info(f"Request to set audio input to: {device_name}")
        logger.warning("Audio device switching not fully implemented")
        return True
    
    # ========== Autostart ==========
    
    def enable_autostart(self) -> bool:
        """
        Enable Windows autostart via registry
        
        Returns:
            bool: True if successful
        """
        exe_path = self.get_exe_path()
        if not exe_path:
            logger.error("Cannot enable autostart: no executable path")
            return False
        
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                self.REGISTRY_KEY,
                0,
                winreg.KEY_SET_VALUE
            ) as key:
                winreg.SetValueEx(
                    key,
                    self.APP_NAME,
                    0,
                    winreg.REG_SZ,
                    exe_path
                )
            logger.info(f"Autostart enabled: {exe_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to enable autostart: {e}")
            return False
    
    def disable_autostart(self) -> bool:
        """
        Disable Windows autostart
        
        Returns:
            bool: True if successful
        """
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                self.REGISTRY_KEY,
                0,
                winreg.KEY_SET_VALUE
            ) as key:
                winreg.DeleteValue(key, self.APP_NAME)
            logger.info("Autostart disabled")
            return True
            
        except (FileNotFoundError, OSError):
            # Already disabled
            logger.info("Autostart already disabled")
            return True
            
        except Exception as e:
            logger.error(f"Failed to disable autostart: {e}")
            return False
    
    def is_autostart_enabled(self) -> bool:
        """
        Check if Windows autostart is enabled
        
        Returns:
            bool: True if enabled
        """
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, self.REGISTRY_KEY) as key:
                value, _ = winreg.QueryValueEx(key, self.APP_NAME)
                exe_path = self.get_exe_path()
                return value == exe_path
                
        except (FileNotFoundError, OSError):
            return False
            
        except Exception as e:
            logger.error(f"Failed to check autostart status: {e}")
            return False
    
    def get_exe_path(self) -> Optional[str]:
        """
        Get path to running executable
        
        Returns:
            str: Path to executable or script
        """
        if getattr(sys, 'frozen', False):
            # Running as compiled EXE
            return sys.executable
        else:
            # Running in development mode
            return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '__main__.py'))
    
    # ========== System Commands ==========
    
    def shutdown(self) -> bool:
        """
        Shutdown Windows
        
        Returns:
            bool: True if successful
        """
        try:
            logger.warning("Executing Windows shutdown")
            subprocess.run(['shutdown', '/s', '/t', '0'], check=True)
            return True
        except Exception as e:
            logger.error(f"Shutdown failed: {e}")
            return False
    
    def restart(self) -> bool:
        """
        Restart Windows
        
        Returns:
            bool: True if successful
        """
        try:
            logger.warning("Executing Windows restart")
            subprocess.run(['shutdown', '/r', '/t', '0'], check=True)
            return True
        except Exception as e:
            logger.error(f"Restart failed: {e}")
            return False
    
    def sleep(self) -> bool:
        """
        Sleep Windows (standby)
        
        Returns:
            bool: True if successful
        """
        try:
            logger.info("Executing Windows sleep")
            subprocess.run(['rundll32.exe', 'powrprof.dll,SetSuspendState', '0,1,0'], check=True)
            return True
        except Exception as e:
            logger.error(f"Sleep failed: {e}")
            return False
    
    def hibernate(self) -> bool:
        """
        Hibernate Windows
        
        Returns:
            bool: True if successful
        """
        try:
            logger.info("Executing Windows hibernate")
            subprocess.run(['shutdown', '/h'], check=True)
            return True
        except Exception as e:
            logger.error(f"Hibernate failed: {e}")
            return False
    
    def lock_screen(self) -> bool:
        """
        Lock Windows screen
        
        Returns:
            bool: True if successful
        """
        try:
            logger.info("Executing Windows lock screen")
            subprocess.run(['rundll32.exe', 'user32.dll,LockWorkStation'], check=True)
            return True
        except Exception as e:
            logger.error(f"Lock screen failed: {e}")
            return False
    
    def logoff(self) -> bool:
        """
        Log off Windows user
        
        Returns:
            bool: True if successful
        """
        try:
            logger.warning("Executing Windows logoff")
            subprocess.run(['shutdown', '/l'], check=True)
            return True
        except Exception as e:
            logger.error(f"Logoff failed: {e}")
            return False
    
    # ========== System Tray ==========
    
    def create_tray_icon(self, callback: Optional[Callable] = None):
        """
        Create Windows system tray icon
        
        Note: This is handled by the SystemTrayIcon class
        This method is a placeholder for compatibility
        
        Args:
            callback: Callback function for icon events
        """
        # The actual tray icon is created by src.ui.system_tray_icon
        # This method exists for API compatibility
        pass
    
    def update_tray_icon(self, **kwargs):
        """
        Update Windows tray icon (placeholder)
        
        Args:
            **kwargs: Icon properties to update
        """
        # The actual tray icon update is handled by SystemTrayIcon class
        pass
    
    def show_tray_notification(self, title: str, message: str):
        """
        Show Windows tray notification
        
        Args:
            title: Notification title
            message: Notification message
        """
        notification = Notification(title=title, message=message)
        self.show_notification(notification)
    
    # ========== Utility Methods ==========
    
    def is_platform_supported(self) -> bool:
        """Check if Windows is supported"""
        return True
    
    def get_platform_info(self) -> Dict[str, str]:
        """Get Windows platform information"""
        info = super().get_platform_info()
        info.update({
            'platform': 'Windows',
            'edition': self._get_windows_edition(),
        })
        return info
    
    def _get_windows_edition(self) -> str:
        """Get Windows edition (Pro, Home, etc.)"""
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as key:
                edition, _ = winreg.QueryValueEx(key, "ProductName")
                return edition
        except Exception:
            return "Unknown"