"""
Global Hotkey Manager Module

Manages global keyboard shortcuts for voice input and other functions.
"""

import logging
import threading
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
        self._listening_thread: Optional[threading.Thread] = None
        self._running = False
        self._keyboard_available = False

        # Check if keyboard library is available
        try:
            import keyboard
            self._keyboard_available = True
            logger.info("Keyboard library available for global hotkeys")
        except ImportError:
            logger.warning("Keyboard library not available, hotkeys disabled")
            logger.warning("Install with: pip install keyboard")

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
            logger.error("Cannot set hotkey: keyboard library not available")
            return False

        # Remove previous hotkey if exists
        if self._hotkey:
            self.remove_hotkey()

        self._hotkey = hotkey
        self._callback = callback

        # Start listening for hotkey
        self._start_listening()
        logger.info(f"Hotkey set: {hotkey}")
        return True

    def _start_listening(self) -> None:
        """Start listening for hotkey in background thread"""
        if not self._hotkey or not self._callback:
            return

        def hotkey_listener():
            """Hotkey listener function"""
            import keyboard

            try:
                self._running = True
                logger.info(f"Listening for hotkey: {self._hotkey}")

                # Wait for hotkey press
                keyboard.wait(self._hotkey)

                if self._running:
                    logger.info(f"Hotkey triggered: {self._hotkey}")
                    # Call the callback in a separate thread to avoid blocking
                    callback_thread = threading.Thread(
                        target=self._safe_callback,
                        daemon=True
                    )
                    callback_thread.start()
            except Exception as e:
                logger.error(f"Error in hotkey listener: {e}")
            finally:
                self._running = False

        # Start listener thread
        self._listening_thread = threading.Thread(
            target=hotkey_listener,
            daemon=True
        )
        self._listening_thread.start()

    def _safe_callback(self) -> None:
        """Safely execute callback with error handling"""
        try:
            if self._callback:
                self._callback()
        except Exception as e:
            logger.error(f"Error in hotkey callback: {e}")

    def remove_hotkey(self) -> None:
        """Remove current hotkey"""
        self._running = False
        self._hotkey = None
        self._callback = None
        self._listening_thread = None
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