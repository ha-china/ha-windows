"""
Global Hotkey Manager Module

Manages global keyboard shortcuts for voice input and other functions.
"""

import logging
import platform
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class HotkeyManager:
    """
    Global Hotkey Manager

    Manages keyboard shortcuts that can trigger voice input without wake word.
    """

    def __init__(self):
        """Initialize hotkey manager"""
        self._hotkey: Optional[str] = None
        self._callback: Optional[Callable] = None
        self._hotkey_handle = None
        self._keyboard_available = False

        # Check if keyboard library is available
        try:
            import keyboard
            self._keyboard_available = True
            logger.info("Keyboard library available for global hotkeys")
        except ImportError:
            system = platform.system()
            if system == "Windows":
                logger.warning("Keyboard library not available, hotkeys disabled")
                logger.warning("Install with: pip install keyboard")
            else:
                logger.warning(f"Global hotkey not supported on {system} (keyboard backend unavailable)")

    def set_hotkey(self, hotkey: str, callback: Callable) -> bool:
        """
        Set global hotkey and callback

        Args:
            hotkey: Hotkey string (e.g., 'ctrl+alt+v', 'f9')
            callback: Callback function to call when hotkey is pressed

        Returns:
            bool: Whether hotkey was set successfully
        """
        if not self._keyboard_available:
            logger.error("Cannot set hotkey: backend not available on this platform")
            return False

        # Remove previous hotkey if exists
        if self._hotkey:
            self.remove_hotkey()

        self._hotkey = hotkey
        self._callback = callback

        try:
            import keyboard

            self._hotkey_handle = keyboard.add_hotkey(hotkey, self._safe_callback, suppress=False)
            logger.info(f"Hotkey set: {hotkey}")
            return True
        except Exception as e:
            logger.error(f"Failed to register hotkey '{hotkey}': {e}")
            self._hotkey = None
            self._callback = None
            self._hotkey_handle = None
            return False

    def _safe_callback(self) -> None:
        """Safely execute callback with error handling"""
        try:
            if self._callback:
                self._callback()
        except Exception as e:
            logger.error(f"Error in hotkey callback: {e}")

    def remove_hotkey(self) -> None:
        """Remove current hotkey"""
        if self._keyboard_available and self._hotkey_handle is not None:
            try:
                import keyboard

                keyboard.remove_hotkey(self._hotkey_handle)
            except Exception as e:
                logger.error(f"Failed to remove hotkey: {e}")
        self._hotkey = None
        self._callback = None
        self._hotkey_handle = None
        logger.info("Hotkey removed")

    def get_hotkey(self) -> Optional[str]:
        """Get current hotkey"""
        return self._hotkey

    def is_available(self) -> bool:
        """Check if hotkey functionality is available"""
        return self._keyboard_available

    def cleanup(self) -> None:
        """Cleanup resources"""
        self.remove_hotkey()


# Global singleton
_hotkey_manager: Optional[HotkeyManager] = None


def get_hotkey_manager() -> HotkeyManager:
    """Get hotkey manager singleton instance"""
    global _hotkey_manager
    if _hotkey_manager is None:
        _hotkey_manager = HotkeyManager()
    return _hotkey_manager
