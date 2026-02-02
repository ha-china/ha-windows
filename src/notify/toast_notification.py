"""
Cross-platform Notification Handler

Uses platform abstraction layer to display notifications
Windows: windows-toasts library
macOS: osascript
"""

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Callable, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Import platform abstraction layer
try:
    from src.platforms import get_platform_instance, Notification as PlatformNotification
    PLATFORM_AVAILABLE = True
except ImportError:
    PLATFORM_AVAILABLE = False
    PlatformNotification = None

# Windows-specific imports (for backward compatibility)
try:
    from windows_toasts import Toast, ToastDisplayImage, InteractableWindowsToaster, ToastImagePosition
    WINDOWS_TOASTS_AVAILABLE = True
except ImportError:
    WINDOWS_TOASTS_AVAILABLE = False
    logger.debug("windows-toasts not available")


@dataclass
class NotificationAction:
    """Notification action button"""
    id: str
    label: str
    callback: Optional[Callable] = None


@dataclass
class Notification:
    """Notification data"""
    title: str
    message: str
    icon_path: Optional[str] = None
    image_url: Optional[str] = None
    duration: int = 5
    actions: Optional[List[NotificationAction]] = None
    on_click: Optional[Callable] = None
    on_dismiss: Optional[Callable] = None


class NotificationHandler:
    """Cross-platform notification handler"""

    def __init__(self, app_name: str = "Home Assistant"):
        self.app_name = app_name
        self._toaster: Optional["InteractableWindowsToaster"] = None
        self._temp_dir = Path(tempfile.gettempdir()) / "ha_notifications"
        self._temp_dir.mkdir(parents=True, exist_ok=True)
        self._platform = None
        
        # Try to initialize platform abstraction
        if PLATFORM_AVAILABLE:
            try:
                self._platform = get_platform_instance()
                logger.info(f"NotificationHandler initialized with {self._platform.get_platform_name()}")
            except Exception as e:
                logger.debug(f"Platform abstraction not available: {e}")
                self._platform = None
        
        # Initialize Windows toaster as fallback
        self._init_windows_toaster()
        logger.info(f"NotificationHandler initialized: {app_name}")

    def _init_windows_toaster(self) -> None:
        """Initialize Windows toast toaster (fallback)"""
        if not WINDOWS_TOASTS_AVAILABLE:
            return
        try:
            self._toaster = InteractableWindowsToaster(self.app_name)
        except Exception as e:
            logger.error(f"Failed to initialize Windows toaster: {e}")

    def show(self, notification: Notification) -> bool:
        """
        Show notification using platform abstraction layer
        
        Args:
            notification: Notification data
            
        Returns:
            bool: True if successful
        """
        # Try platform abstraction layer first
        if self._platform and PlatformNotification:
            try:
                platform_notification = PlatformNotification(
                    title=notification.title,
                    message=notification.message,
                    icon_path=notification.icon_path,
                    image_url=notification.image_url,
                    duration=notification.duration
                )
                success = self._platform.show_notification(platform_notification)
                if success:
                    logger.info(f"Notification shown via platform abstraction: {notification.title}")
                    return True
            except Exception as e:
                logger.warning(f"Platform notification failed: {e}, falling back to Windows-specific")
        
        # Fallback to Windows-specific implementation
        return self._show_windows(notification)

    def _show_windows(self, notification: Notification) -> bool:
        """Show Windows toast notification (fallback)"""
        if not WINDOWS_TOASTS_AVAILABLE or self._toaster is None:
            logger.error("windows-toasts not available")
            return False

        try:
            toast = Toast()
            toast.text_fields = [notification.title, notification.message]

            # Add hero image if available
            if notification.icon_path:
                image_path = Path(notification.icon_path)
                if image_path.exists():
                    toast.AddImage(ToastDisplayImage.fromPath(
                        str(image_path.absolute()),
                        position=ToastImagePosition.Hero
                    ))

            self._toaster.show_toast(toast)
            logger.info(f"Notification shown via Windows toast: {notification.title}")
            return True

        except Exception as e:
            logger.error(f"Failed to show Windows notification: {e}")
            return False

    def show_simple(self, title: str, message: str, duration: int = 5) -> bool:
        """Show simple notification"""
        return self.show(Notification(title=title, message=message, duration=duration))

    async def show_async(self, notification: Notification) -> bool:
        """Show notification asynchronously"""
        if notification.image_url:
            local_path = await self._download_image(notification.image_url)
            if local_path:
                notification.icon_path = local_path
                logger.info(f"Image downloaded to: {local_path}")
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.show, notification)

    async def _download_image(self, url: str) -> Optional[str]:
        """Download image from URL"""
        try:
            import aiohttp
            import hashlib

            url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
            url_path = url.split('?')[0]
            ext = Path(url_path).suffix.lower()
            if ext not in ['.png', '.jpg', '.jpeg', '.gif', '.bmp']:
                ext = ".png"

            local_path = self._temp_dir / f"img_{url_hash}{ext}"

            if local_path.exists():
                logger.info(f"Using cached image: {local_path}")
                return str(local_path)

            logger.info(f"Downloading image from: {url}")
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        content = await response.read()
                        with open(local_path, "wb") as f:
                            f.write(content)
                        logger.info(f"Image saved: {local_path} ({len(content)} bytes)")
                        return str(local_path)
                    else:
                        logger.error(f"Failed to download image: HTTP {response.status}")
        except Exception as e:
            logger.error(f"Failed to download image: {e}")
        return None

    def cleanup(self) -> None:
        """Cleanup temporary files"""
        try:
            for f in self._temp_dir.glob("img_*"):
                f.unlink()
        except Exception:
            pass


_handler: Optional[NotificationHandler] = None


def get_notification_handler() -> NotificationHandler:
    """Get notification handler singleton"""
    global _handler
    if _handler is None:
        _handler = NotificationHandler()
    return _handler


async def show_notification(title: str, message: str, image_url: Optional[str] = None) -> bool:
    """
    Show notification asynchronously
    
    Args:
        title: Notification title
        message: Notification message
        image_url: Optional image URL
        
    Returns:
        bool: True if successful
    """
    handler = get_notification_handler()
    notification = Notification(title=title, message=message, image_url=image_url)
    return await handler.show_async(notification)
