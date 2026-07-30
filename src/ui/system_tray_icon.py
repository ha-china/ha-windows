"""
System Tray Icon Module
Provides Windows system tray icon for the application
"""

import ctypes
import logging
import os
import socket
import tempfile
import threading
from typing import Optional, Callable

import pystray
from PIL import Image, ImageDraw

from src.i18n import get_i18n

# Windows API constants
_NIM_MODIFY = 1
_NIF_ICON = 2
_IMAGE_ICON = 1
_LR_DEFAULTSIZE = 0x0040
_LR_LOADFROMFILE = 0x0010

class _NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ('cbSize', ctypes.wintypes.DWORD),
        ('hWnd', ctypes.wintypes.HWND),
        ('uID', ctypes.wintypes.UINT),
        ('uFlags', ctypes.wintypes.UINT),
        ('uCallbackMessage', ctypes.wintypes.UINT),
        ('hIcon', ctypes.wintypes.HANDLE),
        ('szTip', ctypes.wintypes.WCHAR * 128),
        ('dwState', ctypes.wintypes.DWORD),
        ('dwStateMask', ctypes.wintypes.DWORD),
        ('szInfo', ctypes.wintypes.WCHAR * 256),
        ('uVersion', ctypes.wintypes.UINT),
        ('szInfoTitle', ctypes.wintypes.WCHAR * 64),
        ('dwInfoFlags', ctypes.wintypes.DWORD),
        ('guidItem', ctypes.c_byte * 16),
        ('hBalloonIcon', ctypes.wintypes.HANDLE),
    ]

_user32 = ctypes.windll.user32
_shell32 = ctypes.windll.shell32
from src.ui.dialogs import show_status_dialog, show_about_dialog

logger = logging.getLogger(__name__)
_i18n = get_i18n()


class SystemTrayIcon:
    """
    System Tray Icon Manager

    Features:
    - Display tray icon
    - Status notifications
    """

    # Phase constants
    PHASE_IDLE = 'idle'
    PHASE_WAITING = 'waiting'
    PHASE_LISTENING = 'listening'
    PHASE_THINKING = 'thinking'
    PHASE_REPLYING = 'replying'
    PHASE_ERROR = 'error'
    PHASE_NOT_READY = 'not_ready'

    # Phase colors (RGB)
    _PHASE_COLORS = {
        PHASE_IDLE: (61, 174, 233),       # blue
        PHASE_WAITING: (255, 200, 0),     # amber
        PHASE_LISTENING: (76, 217, 100),  # green
        PHASE_THINKING: (255, 149, 0),    # orange
        PHASE_REPLYING: (90, 200, 250),   # cyan
        PHASE_ERROR: (255, 59, 48),       # red
        PHASE_NOT_READY: (142, 142, 147), # gray
    }

    def __init__(self, state=None):
        """Initialize system tray icon"""
        self.icon: Optional[pystray.Icon] = None
        self._running = False
        self._loop_thread: Optional[threading.Thread] = None
        self._icon_ready = threading.Event()
        self._state = state  # Reference to ServerState for saving preferences
        self._current_phase = self.PHASE_IDLE

        # Status information
        self._status_info = {
            'name': 'Unknown',
            'ip': 'Unknown',
            'port': 'Unknown',
        }

        # Callbacks
        self._on_quit: Optional[Callable] = None
        self._version = "0.0.0"

    def create_icon_image(self, width: int = 64, height: int = 64) -> Image.Image:
        """
        Create tray icon image

        Args:
            width: Icon width
            height: Icon height

        Returns:
            Image: Icon image
        """
        color = self._PHASE_COLORS.get(self._current_phase, self._PHASE_COLORS[self.PHASE_IDLE])

        image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        draw.ellipse(
            [4, 4, width - 4, height - 4],
            fill=(*color, 255)
        )

        house_margin = 16
        draw.polygon([
            (house_margin, height // 2),
            (width // 2, house_margin),
            (width - house_margin, height // 2),
        ], fill=(255, 255, 255, 255))

        draw.rectangle([
            (house_margin + 4, height // 2),
            (width - house_margin - 4, height - house_margin),
        ], fill=(255, 255, 255, 255))

        return image

    def set_version(self, version: str) -> None:
        """Set app version for dialogs"""
        self._version = version

    def set_phase(self, phase: str) -> None:
        """Update tray icon and tooltip to reflect voice assistant phase"""
        if phase not in self._PHASE_COLORS:
            return
        self._current_phase = phase
        if self.icon:
            self._update_tray_icon(image=self.create_icon_image(), phase=phase)
            info = self._status_info
            self.icon.title = (
                f"HA Windows: {info['name']} [{phase}]\n"
                f"{_i18n.t('ip_label')}: {info['ip']}:{info['port']}"
            )

    def _update_tray_icon(self, image: Image.Image, phase: str = "") -> None:
        """Force tray icon update via direct Windows API"""
        hwnd = getattr(self.icon, '_hwnd', None)
        if not hwnd:
            logger.debug("No HWND available for icon update")
            return

        fd, path = tempfile.mkstemp('.ico')
        try:
            with os.fdopen(fd, 'wb') as f:
                image.save(f, 'ICO')
            hicon = _user32.LoadImageW(
                None, path, _IMAGE_ICON, 0, 0,
                _LR_DEFAULTSIZE | _LR_LOADFROMFILE)
            if not hicon:
                logger.debug(f"LoadImageW failed: {ctypes.get_last_error()}")
                return
            try:
                nid = _NOTIFYICONDATAW(
                    cbSize=ctypes.sizeof(_NOTIFYICONDATAW),
                    hWnd=hwnd,
                    uFlags=_NIF_ICON,
                    hIcon=hicon,
                )
                _shell32.Shell_NotifyIconW(_NIM_MODIFY, ctypes.byref(nid))
            finally:
                _user32.DestroyIcon(hicon)
        finally:
            try:
                os.unlink(path)
            except Exception:
                pass

    def _on_show_status(self, icon, item) -> None:
        """Handle show status menu item"""
        logger.info("Show status menu clicked")
        info = self._status_info
        show_status_dialog(info['name'], info['ip'], info['port'], self._version)

    def _on_quit_menu(self, icon, item) -> None:
        """Handle quit menu item"""
        logger.info("Quit menu clicked")
        if self._on_quit:
            try:
                self._on_quit()
            except Exception as e:
                logger.error(f"Error in quit callback: {e}")
        self._running = False
        icon.stop()

    def _on_about_menu(self, icon, item) -> None:
        """Handle about menu item"""
        logger.info("About menu clicked")
        show_about_dialog(self._version)

    def _run_icon(self, icon: pystray.Icon) -> None:
        """Run icon in background thread"""
        self._icon_ready.set()
        icon.run()

    def start(self, name: str = None, ip: str = None, port: int = None) -> None:
        """
        Start system tray icon

        Args:
            name: Device name (default: hostname)
            ip: Local IP address (default: auto-detect)
            port: Listening port
        """
        if self._running:
            logger.warning("Tray icon already running")
            return

        if name is None:
            name = socket.gethostname()
        if ip is None:
            ip = self._get_local_ip()

        self._status_info = {
            'name': name,
            'ip': ip,
            'port': str(port) if port else 'Unknown',
        }

        self.icon = pystray.Icon(
            name='HomeAssistant Windows',
            icon=self.create_icon_image(),
            menu=pystray.Menu(
                pystray.MenuItem(_i18n.t('status_running'), self._on_show_status),
                pystray.MenuItem('About', self._on_about_menu),
                pystray.MenuItem(_i18n.t('quit'), self._on_quit_menu),
            )
        )

        self.icon.title = f"HA Windows: {name}\n{_i18n.t('ip_label')}: {ip}:{port if port else 'Unknown'}"

        self._running = True
        self._icon_ready.clear()
        self._loop_thread = threading.Thread(
            target=self._run_icon,
            args=(self.icon,),
            daemon=True,
        )
        self._loop_thread.start()

        self._icon_ready.wait(timeout=5)

        if not self._icon_ready.is_set():
            logger.warning("Tray icon may not have started properly")
        else:
            logger.info("System tray icon started")

    def _get_local_ip(self) -> str:
        """
        Get local LAN IP address (without connecting to external servers)

        Returns:
            str: Local IP address
        """
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
            s.close()

            if ip and not ip.startswith("127.") and not ip.startswith("169.254."):
                return ip
        except Exception:
            pass

        try:
            hostname = socket.gethostname()
            ip = socket.gethostbyname(hostname)
            if ip and not ip.startswith("127.") and not ip.startswith("169.254."):
                return ip
        except Exception:
            pass

        return "127.0.0.1"

    def update_status(self, name: str = None, ip: str = None, port: int = None) -> None:
        """
        Update status information

        Args:
            name: Device name
            ip: Local IP address
            port: Listening port
        """
        if name is not None:
            self._status_info['name'] = name
        if ip is not None:
            self._status_info['ip'] = ip
        if port is not None:
            self._status_info['port'] = str(port)

        if self.icon:
            self.icon.title = (
                f"HA Windows: {self._status_info['name']}\n"
                f"{_i18n.t('ip_label')}: {self._status_info['ip']}:{self._status_info['port']}"
            )

    def set_callbacks(self, on_quit: Callable = None) -> None:
        """
        Set callback functions

        Args:
            on_quit: Called when quit is requested
        """
        self._on_quit = on_quit

    def stop(self) -> None:
        """Stop system tray icon"""
        if self.icon and self._running:
            self._running = False
            try:
                self.icon.stop()
            except Exception:
                pass

            logger.info("System tray icon stopped")


# Global singleton
_tray_instance: Optional[SystemTrayIcon] = None


def get_tray(state=None) -> SystemTrayIcon:
    """Get system tray singleton instance"""
    global _tray_instance
    if _tray_instance is None:
        _tray_instance = SystemTrayIcon(state=state)
    return _tray_instance