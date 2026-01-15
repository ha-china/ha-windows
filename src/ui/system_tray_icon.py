"""
System Tray Icon Module
Provides Windows system tray icon for the application
"""

import logging
import socket
import threading
from typing import Optional, Callable

import pystray
from PIL import Image, ImageDraw

from src.i18n import get_i18n

logger = logging.getLogger(__name__)
_i18n = get_i18n()


class SystemTrayIcon:
    """
    System Tray Icon Manager

    Features:
    - Display tray icon
    - Click/double-click to open window
    - Status notifications
    """

    def __init__(self):
        """Initialize system tray icon"""
        self.icon: Optional[pystray.Icon] = None
        self._running = False
        self._loop_thread: Optional[threading.Thread] = None
        self._icon_ready = threading.Event()

        # Status information
        self._status_info = {
            'name': 'Unknown',
            'ip': 'Unknown',
            'port': 'Unknown',
        }

        # Callbacks
        self._on_open_window: Optional[Callable] = None
        self._on_quit: Optional[Callable] = None

    def create_icon_image(self, width: int = 64, height: int = 64) -> Image.Image:
        """
        Create tray icon image

        Args:
            width: Icon width
            height: Icon height

        Returns:
            Image: Icon image
        """
        # Create a simple HA-style icon
        image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        # Draw circular background (HA blue)
        padding = 4
        draw.ellipse(
            [padding, padding, width - padding, height - padding],
            fill=(61, 174, 233, 255)  # Home Assistant blue
        )

        # Draw simple house shape
        house_margin = 16
        roof_points = [
            (house_margin, height // 2),
            (width // 2, house_margin),
            (width - house_margin, height // 2),
        ]
        draw.polygon(roof_points, fill=(255, 255, 255, 255))

        # House body
        house_body = [
            (house_margin + 4, height // 2),
            (width - house_margin - 4, height - house_margin),
        ]
        draw.rectangle(house_body, fill=(255, 255, 255, 255))

        return image

    def _on_icon_clicked(self, icon, item) -> None:
        """Handle icon click event (open window)"""
        logger.info("Tray icon clicked - opening window")
        self._open_window()

    def _open_window(self) -> None:
        """Open the main window"""
        if self._on_open_window:
            try:
                self._on_open_window()
            except Exception as e:
                logger.error(f"Error opening window: {e}")
        else:
            # Show status notification as fallback
            self.show_status()

    def _on_show_status(self, icon, item) -> None:
        """Handle show status menu item"""
        logger.info("Show status menu clicked")
        self.show_status()

    def _on_open_window_menu(self, icon, item) -> None:
        """Handle open window menu item"""
        logger.info("Open window menu clicked")
        self._open_window()

    def _on_quit_menu(self, icon, item) -> None:
        """Handle quit menu item"""
        logger.info("Quit menu clicked")
        if self._on_quit:
            try:
                self._on_quit()
            except Exception as e:
                logger.error(f"Error in quit callback: {e}")
        # Stop icon after callback (callback should set running=False)
        self._running = False
        icon.stop()

    def _run_icon(self, icon: pystray.Icon) -> None:
        """
        Run icon in background thread

        Args:
            icon: pystray Icon instance
        """
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

        # Auto-detect values if not provided
        if name is None:
            name = socket.gethostname()
        if ip is None:
            ip = self._get_local_ip()

        self._status_info = {
            'name': name,
            'ip': ip,
            'port': str(port) if port else 'Unknown',
        }

        # Create icon with menu
        # The default action (first item or item with default=True) is triggered on click
        self.icon = pystray.Icon(
            name='HomeAssistant Windows',
            icon=self.create_icon_image(),
            menu=pystray.Menu(
                pystray.MenuItem(
                    _i18n.t('open_window') if hasattr(_i18n, 't') else "Open Window",
                    self._on_open_window_menu,
                    default=True  # This makes it the default action on click
                ),
                pystray.MenuItem(_i18n.t('status_running'), self._on_show_status),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(_i18n.t('quit'), self._on_quit_menu),
            )
        )

        # Set tooltip
        self.icon.title = f"HA Windows: {name}\n{_i18n.t('ip_label')}: {ip}:{port if port else 'Unknown'}"

        # Run in background thread
        self._running = True
        self._icon_ready.clear()
        self._loop_thread = threading.Thread(
            target=self._run_icon,
            args=(self.icon,),
            daemon=True,
        )
        self._loop_thread.start()

        # Wait for icon to be ready
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
            # Use UDP to local network (doesn't actually send data)
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
            s.close()

            if ip and not ip.startswith("127.") and not ip.startswith("169.254."):
                return ip
        except Exception:
            pass

        try:
            # Fallback: use hostname
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

        # Update tooltip with i18n support
        if self.icon:
            self.icon.title = (
                f"HA Windows: {self._status_info['name']}\n"
                f"{_i18n.t('ip_label')}: {self._status_info['ip']}:{self._status_info['port']}"
            )

    def set_callbacks(self, on_open_window: Callable = None, on_quit: Callable = None) -> None:
        """
        Set callback functions

        Args:
            on_open_window: Called when icon is clicked or "Open Window" menu is selected
            on_quit: Called when quit is requested
        """
        self._on_open_window = on_open_window
        self._on_quit = on_quit

    def show_status(self) -> None:
        """Show status notification with i18n support"""
        if self.icon:
            status_text = (
                f"{_i18n.t('app_name')}\n\n"
                f"{_i18n.t('device_label')}: {self._status_info['name']}\n"
                f"{_i18n.t('ip_label')}: {self._status_info['ip']}\n"
                f"{_i18n.t('port_label')}: {self._status_info['port']}\n\n"
                f"{_i18n.t('status_running')}"
            )
            self.icon.notify(status_text, title=_i18n.t('device_status'))

    def stop(self) -> None:
        """Stop system tray icon"""
        if self.icon and self._running:
            self._running = False
            try:
                self.icon.stop()
            except Exception:
                pass  # May already be stopped
            logger.info("System tray icon stopped")

    def notify(self, message: str, title: str = None) -> None:
        """
        Show notification

        Args:
            message: Notification message
            title: Notification title (default: app_name)
        """
        if self.icon:
            try:
                if title is None:
                    title = _i18n.t('app_name')
                self.icon.notify(message, title=title)
            except Exception as e:
                logger.error(f"Failed to show notification: {e}")


# Global singleton
_tray_instance: Optional[SystemTrayIcon] = None


def get_tray() -> SystemTrayIcon:
    """Get system tray singleton instance"""
    global _tray_instance
    if _tray_instance is None:
        _tray_instance = SystemTrayIcon()
    return _tray_instance
