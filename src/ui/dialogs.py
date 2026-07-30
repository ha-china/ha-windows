"""
Native Windows Dialogs using ctypes (Win32 API)
Zero additional dependencies, native look and feel.
"""

import ctypes
import logging
from ctypes import wintypes
from typing import Optional

logger = logging.getLogger(__name__)

# Windows API constants
MB_OK = 0
MB_ICONINFORMATION = 0x40
MB_ICONWARNING = 0x30
MB_ICONERROR = 0x10
MB_TASKMODAL = 0x2000
MB_SETFOREGROUND = 0x00010000
MB_TOPMOST = 0x00040000

# Load user32
_user32 = ctypes.windll.user32
_user32.MessageBoxW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT]
_user32.MessageBoxW.restype = wintypes.INT


def _message_box(title: str, message: str, icon: int = MB_ICONINFORMATION) -> None:
    """Show a native Windows message box."""
    try:
        _user32.MessageBoxW(
            None,
            message,
            title,
            MB_OK | icon | MB_TASKMODAL | MB_SETFOREGROUND | MB_TOPMOST,
        )
    except Exception as e:
        logger.error(f"Failed to show message box: {e}")


def show_status_dialog(name: str, ip: str, port: str, version: str) -> None:
    """Show device status as a native Windows message box."""
    message = (
        f"Device:  {name}\n"
        f"IP:      {ip}\n"
        f"Port:    {port}\n"
        f"Version: {version}\n"
        f"Status:  Running"
    )
    _message_box("Device Status", message)


def show_about_dialog(version: str) -> None:
    """Show about dialog as a native Windows message box."""
    message = (
        f"Home Assistant Windows v{version}\n\n"
        f"Windows native client that emulates an ESPHome device\n"
        f"for seamless Home Assistant integration.\n\n"
        f"https://github.com/ha-china/ha-windows\n\n"
        f"\u00a9 2024 ha-china"
    )
    _message_box("About", message)