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
    - Toggle floating mic button visibility
    - Status notifications
    """

    def __init__(self):
        """Initialize system tray icon"""
        self.icon: Optional[pystray.Icon] = None
        self._running = False
        self._loop_thread: Optional[threading.Thread] = None
        self._icon_ready = threading.Event()
        self._floating_visible = True  # Track floating button visibility

        # Status information
        self._status_info = {
            'name': 'Unknown',
            'ip': 'Unknown',
            'port': 'Unknown',
        }

        # Callbacks
        self._on_show_floating: Optional[Callable] = None
        self._on_hide_floating: Optional[Callable] = None
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
        """Handle icon click event - toggle floating button"""
        self._toggle_floating()

    def _toggle_floating(self) -> None:
        """Toggle floating button visibility"""
        if self._floating_visible:
            # Hide floating button
            if self._on_hide_floating:
                try:
                    self._on_hide_floating()
                    self._floating_visible = False
                    logger.info("Floating button hidden")
                except Exception as e:
                    logger.error(f"Error hiding floating button: {e}")
        else:
            # Show floating button
            if self._on_show_floating:
                try:
                    self._on_show_floating()
                    self._floating_visible = True
                    logger.info("Floating button shown")
                except Exception as e:
                    logger.error(f"Error showing floating button: {e}")

    def _open_window(self) -> None:
        """Open the main window (show floating button)"""
        if not self._floating_visible and self._on_show_floating:
            try:
                self._on_show_floating()
                self._floating_visible = True
            except Exception as e:
                logger.error(f"Error showing floating button: {e}")

    def _on_show_status(self, icon, item) -> None:
        """Handle show status menu item"""
        logger.info("Show status menu clicked")
        self.show_status()

    def _on_toggle_floating_menu(self, icon, item) -> None:
        """Handle toggle floating button menu item"""
        self._toggle_floating()

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

    def _on_about_menu(self, icon, item) -> None:
        """Handle about menu item"""
        logger.info("About menu clicked")
        self.show_about()

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
        self.icon = pystray.Icon(
            name='HomeAssistant Windows',
            icon=self.create_icon_image(),
            menu=pystray.Menu(
                pystray.MenuItem(
                    lambda item: _i18n.t('hide_icon') if self._floating_visible else _i18n.t('show_icon'),
                    self._on_toggle_floating_menu,
                    default=True
                ),
                pystray.MenuItem(_i18n.t('status_running'), self._on_show_status),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem('About', self._on_about_menu),
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

    def set_callbacks(self, on_show_floating: Callable = None,
                      on_hide_floating: Callable = None, on_quit: Callable = None) -> None:
        """
        Set callback functions

        Args:
            on_show_floating: Called to show floating button
            on_hide_floating: Called to hide floating button
            on_quit: Called when quit is requested
        """
        self._on_show_floating = on_show_floating
        self._on_hide_floating = on_hide_floating
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

    def show_about(self) -> None:
        """Show about dialog with version and repository info"""
        try:
            from src import __version__
            
            # Repository URL (hardcoded as it's the official repo)
            repo_url = "https://github.com/ha-china/ha-windows"
            
            about_text = (
                f"Home Assistant Windows\n\n"
                f"Version: {__version__}\n\n"
                f"Repository:\n{repo_url}\n\n"
                f"© 2024 ha-china"
            )
            self.icon.notify(about_text, title="About")
        except Exception as e:
            logger.error(f"Failed to show about: {e}")

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
