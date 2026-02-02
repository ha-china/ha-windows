"""
macOS Platform Implementation
Provides macOS-specific implementations for the platform abstraction layer
"""

import subprocess
import sys
import os
import logging
import plistlib
from typing import Optional, Dict, List, Callable

from src.platforms.base import PlatformBase, Notification

logger = logging.getLogger(__name__)


class MacOSPlatform(PlatformBase):
    """macOS platform implementation"""
    
    APP_NAME = "com.homeassistant.agent"
    PLIST_PATH = os.path.expanduser('~/Library/LaunchAgents/com.homeassistant.agent.plist')
    
    def __init__(self):
        """Initialize macOS platform"""
        self._tray_icon = None
        logger.info("macOS platform initialized")
    
    # ========== Platform Info ==========
    
    def get_platform_name(self) -> str:
        """Get platform name"""
        return "macOS"
    
    # ========== Notification System ==========
    
    def show_notification(self, notification: Notification) -> bool:
        """
        Show macOS notification using osascript
        
        Args:
            notification: Notification data
            
        Returns:
            bool: True if successful
        """
        try:
            # Escape quotes in message
            title_escaped = notification.title.replace('"', '\\"')
            message_escaped = notification.message.replace('"', '\\"')
            
            cmd = [
                'osascript', '-e',
                f'display notification "{message_escaped}" with title "{title_escaped}"'
            ]
            
            subprocess.run(cmd, check=True)
            logger.info(f"Notification shown: {notification.title}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to show notification: {e}")
            return False
    
    # ========== Audio Control ==========
    
    def get_volume(self) -> int:
        """
        Get macOS system volume
        
        Returns:
            int: Volume level (0-100)
        """
        try:
            # Use osascript to get volume
            cmd = ['osascript', '-e', 'output volume of (get volume settings)']
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            volume = int(result.stdout.strip())
            return volume
            
        except Exception as e:
            logger.error(f"Failed to get volume: {e}")
            return 50  # Return default volume
    
    def set_volume(self, volume: int) -> bool:
        """
        Set macOS system volume
        
        Args:
            volume: Volume level (0-100)
            
        Returns:
            bool: True if successful
        """
        try:
            # Clamp volume to valid range
            volume = max(0, min(100, volume))
            
            # Use osascript to set volume
            cmd = ['osascript', '-e', f'set volume {volume}']
            subprocess.run(cmd, check=True)
            logger.info(f"Volume set to {volume}%")
            return True
            
        except Exception as e:
            logger.error(f"Failed to set volume: {e}")
            return False
    
    def list_audio_devices(self) -> Dict[str, List[str]]:
        """
        List all audio devices on macOS
        
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
        
        Note: This requires complex macOS API calls
        Currently just logs the request
        
        Args:
            device_name: Device name
            
        Returns:
            bool: True (placeholder)
        """
        logger.info(f"Request to set audio output to: {device_name}")
        logger.warning("Audio device switching not fully implemented on macOS")
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
        logger.warning("Audio device switching not fully implemented on macOS")
        return True
    
    # ========== Autostart ==========
    
    def enable_autostart(self) -> bool:
        """
        Enable macOS autostart via launchd
        
        Returns:
            bool: True if successful
        """
        exe_path = self.get_exe_path()
        if not exe_path:
            logger.error("Cannot enable autostart: no executable path")
            return False
        
        try:
            # Create plist content
            plist_content = {
                'Label': self.APP_NAME,
                'ProgramArguments': [exe_path],
                'RunAtLoad': True,
                'KeepAlive': {
                    'SuccessfulExit': False,
                    'Crashed': True
                },
                'ProcessType': 'Interactive',
                'StandardOutPath': os.path.expanduser('~/Library/Logs/HomeAssistant/stdout.log'),
                'StandardErrorPath': os.path.expanduser('~/Library/Logs/HomeAssistant/stderr.log'),
            }
            
            # Ensure directory exists
            plist_dir = os.path.dirname(self.PLIST_PATH)
            os.makedirs(plist_dir, exist_ok=True)
            
            # Write plist file
            with open(self.PLIST_PATH, 'wb') as f:
                plistlib.dump(plist_content, f)
            
            # Load the launch agent
            subprocess.run(['launchctl', 'load', self.PLIST_PATH], check=True)
            
            logger.info(f"Autostart enabled: {self.PLIST_PATH}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to enable autostart: {e}")
            return False
    
    def disable_autostart(self) -> bool:
        """
        Disable macOS autostart
        
        Returns:
            bool: True if successful
        """
        try:
            # Unload the launch agent
            subprocess.run(['launchctl', 'unload', self.PLIST_PATH], check=True)
            
            # Remove plist file
            if os.path.exists(self.PLIST_PATH):
                os.remove(self.PLIST_PATH)
            
            logger.info("Autostart disabled")
            return True
            
        except (FileNotFoundError, subprocess.CalledProcessError):
            # Already disabled
            logger.info("Autostart already disabled")
            return True
            
        except Exception as e:
            logger.error(f"Failed to disable autostart: {e}")
            return False
    
    def is_autostart_enabled(self) -> bool:
        """
        Check if macOS autostart is enabled
        
        Returns:
            bool: True if enabled
        """
        try:
            # Check if plist file exists
            if not os.path.exists(self.PLIST_PATH):
                return False
            
            # Check if launch agent is loaded
            cmd = ['launchctl', 'list', self.APP_NAME]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            return result.returncode == 0
            
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
            # Running as compiled app
            return sys.executable
        else:
            # Running in development mode
            return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '__main__.py'))
    
    # ========== System Commands ==========
    
    def shutdown(self) -> bool:
        """
        Shutdown macOS
        
        Returns:
            bool: True if successful
        """
        try:
            logger.warning("Executing macOS shutdown")
            subprocess.run(['osascript', '-e', 'tell app "System Events" to shut down'], check=True)
            return True
        except Exception as e:
            logger.error(f"Shutdown failed: {e}")
            return False
    
    def restart(self) -> bool:
        """
        Restart macOS
        
        Returns:
            bool: True if successful
        """
        try:
            logger.warning("Executing macOS restart")
            subprocess.run(['osascript', '-e', 'tell app "System Events" to restart'], check=True)
            return True
        except Exception as e:
            logger.error(f"Restart failed: {e}")
            return False
    
    def sleep(self) -> bool:
        """
        Sleep macOS (standby)
        
        Returns:
            bool: True if successful
        """
        try:
            logger.info("Executing macOS sleep")
            subprocess.run(['pmset', 'sleepnow'], check=True)
            return True
        except Exception as e:
            logger.error(f"Sleep failed: {e}")
            return False
    
    def hibernate(self) -> bool:
        """
        Hibernate macOS (not directly supported, use sleep instead)
        
        Returns:
            bool: True if successful
        """
        # macOS doesn't have traditional hibernate, use sleep instead
        logger.info("macOS doesn't support hibernate, using sleep instead")
        return self.sleep()
    
    def lock_screen(self) -> bool:
        """
        Lock macOS screen
        
        Returns:
            bool: True if successful
        """
        try:
            logger.info("Executing macOS lock screen")
            subprocess.run([
                '/System/Library/CoreServices/Menu Extras/User.menu/Contents/Resources/CGSession',
                '-suspend'
            ], check=True)
            return True
        except Exception as e:
            logger.error(f"Lock screen failed: {e}")
            return False
    
    def logoff(self) -> bool:
        """
        Log off macOS user
        
        Returns:
            bool: True if successful
        """
        try:
            logger.warning("Executing macOS logoff")
            subprocess.run(['osascript', '-e', 'tell application "System Events" to log out'], check=True)
            return True
        except Exception as e:
            logger.error(f"Logoff failed: {e}")
            return False
    
    # ========== System Tray ==========
    
    def create_tray_icon(self, callback: Optional[Callable] = None):
        """
        Create macOS menu bar icon
        
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
        Update macOS tray icon (placeholder)
        
        Args:
            **kwargs: Icon properties to update
        """
        # The actual tray icon update is handled by SystemTrayIcon class
        pass
    
    def show_tray_notification(self, title: str, message: str):
        """
        Show macOS tray notification
        
        Args:
            title: Notification title
            message: Notification message
        """
        notification = Notification(title=title, message=message)
        self.show_notification(notification)
    
    # ========== Utility Methods ==========
    
    def is_platform_supported(self) -> bool:
        """Check if macOS is supported"""
        return True
    
    def get_platform_info(self) -> Dict[str, str]:
        """Get macOS platform information"""
        info = super().get_platform_info()
        info.update({
            'platform': 'macOS',
            'version': self._get_macos_version(),
        })
        return info
    
    def _get_macos_version(self) -> str:
        """Get macOS version"""
        try:
            cmd = ['sw_vers', '-productVersion']
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except Exception:
            return "Unknown"
