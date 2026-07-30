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
from src.ui.dialogs import show_status_dialog, show_about_dialog

logger = logging.getLogger(__name__)
_i18n = get_i18n()

_NIM_DELETE = 2
_NIM_ADD = 0
_NIF_MESSAGE = 1
_NIF_ICON = 2
_NIF_TIP = 4
_NIF_SHOWTIP = 0x40
_IMAGE_ICON = 1
_LR_LOADFROMFILE = 0x0010
# pystray defines WM_NOTIFY as WM_USER + 11 = 1035
_WM_NOTIFY = 1035

class _NID(ctypes.Structure):
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


class SystemTrayIcon:
    """
    System Tray Icon Manager
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
        PHASE_IDLE: (61, 174, 233),
        PHASE_WAITING: (255, 200, 0),
        PHASE_LISTENING: (76, 217, 100),
        PHASE_THINKING: (255, 149, 0),
        PHASE_REPLYING: (255, 45, 85),
        PHASE_ERROR: (255, 59, 48),
        PHASE_NOT_READY: (142, 142, 147),
    }

    def __init__(self, state=None):
        self.icon: Optional[pystray.Icon] = None
        self._running = False
        self._loop_thread: Optional[threading.Thread] = None
        self._icon_ready = threading.Event()
        self._state = state
        self._current_phase = self.PHASE_IDLE
        self._status_info = {'name': 'Unknown', 'ip': 'Unknown', 'port': 'Unknown'}
        self._on_quit: Optional[Callable] = None
        self._version = "0.0.0"

    def create_icon_image(self, width: int = 64, height: int = 64) -> Image.Image:
        color = self._PHASE_COLORS.get(self._current_phase, self._PHASE_COLORS[self.PHASE_IDLE])
        image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.ellipse([4, 4, width - 4, height - 4], fill=(*color, 255))
        hm = 16
        draw.polygon([(hm, height // 2), (width // 2, hm), (width - hm, height // 2)], fill=(255, 255, 255, 255))
        draw.rectangle([(hm + 4, height // 2), (width - hm - 4, height - hm)], fill=(255, 255, 255, 255))
        return image

    def set_version(self, version: str) -> None:
        self._version = version

    def set_phase(self, phase: str) -> None:
        if phase not in self._PHASE_COLORS:
            return
        self._current_phase = phase
        if self.icon:
            hwnd = getattr(self.icon, '_hwnd', None)
            if hwnd:
                self._replace_icon(hwnd)
            info = self._status_info
            self.icon.title = (
                f"HA Windows: {info['name']} [{phase}]\n"
                f"{_i18n.t('ip_label')}: {info['ip']}:{info['port']}"
            )

    def _replace_icon(self, hwnd: int) -> None:
        """Delete and re-add tray icon to force visual update"""
        # Delete old icon
        _shell32.Shell_NotifyIconW(_NIM_DELETE, ctypes.byref(_NID(
            cbSize=ctypes.sizeof(_NID), hWnd=hwnd)))

        # Create new icon image
        image = self.create_icon_image()
        info = self._status_info
        tip = f"HA Windows: {info['name']} [{self._current_phase}]\n{_i18n.t('ip_label')}: {info['ip']}:{info['port']}"

        fd, path = tempfile.mkstemp('.ico')
        try:
            with os.fdopen(fd, 'wb') as f:
                image.save(f, 'ICO')
            hicon = _user32.LoadImageW(None, path, _IMAGE_ICON, 32, 32, _LR_LOADFROMFILE)
            if not hicon:
                return
            _shell32.Shell_NotifyIconW(_NIM_ADD, ctypes.byref(_NID(
                cbSize=ctypes.sizeof(_NID),
                hWnd=hwnd,
                uFlags=_NIF_MESSAGE | _NIF_ICON | _NIF_TIP | _NIF_SHOWTIP,
                uCallbackMessage=_WM_NOTIFY,
                hIcon=hicon,
                szTip=tip,
            )))
            _user32.DestroyIcon(hicon)
        finally:
            try:
                os.unlink(path)
            except Exception:
                pass

    def _on_show_status(self, icon, item) -> None:
        logger.info("Show status menu clicked")
        info = self._status_info
        show_status_dialog(info['name'], info['ip'], info['port'], self._version)

    def _on_quit_menu(self, icon, item) -> None:
        logger.info("Quit menu clicked")
        if self._on_quit:
            try:
                self._on_quit()
            except Exception as e:
                logger.error(f"Error in quit callback: {e}")
        self._running = False
        icon.stop()

    def _on_about_menu(self, icon, item) -> None:
        logger.info("About menu clicked")
        show_about_dialog(self._version)

    def _run_icon(self, icon: pystray.Icon) -> None:
        self._icon_ready.set()
        icon.run()

    def start(self, name: str = None, ip: str = None, port: int = None) -> None:
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
        self._on_quit = on_quit

    def stop(self) -> None:
        if self.icon and self._running:
            self._running = False
            try:
                self.icon.stop()
            except Exception:
                pass
            logger.info("System tray icon stopped")


_tray_instance: Optional[SystemTrayIcon] = None


def get_tray(state=None) -> SystemTrayIcon:
    global _tray_instance
    if _tray_instance is None:
        _tray_instance = SystemTrayIcon(state=state)
    return _tray_instance
