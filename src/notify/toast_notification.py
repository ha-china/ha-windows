"""
Windows Toast Notification Handler

使用 win10toast 库显示 Windows Toast 通知
支持标题、消息、图片和操作按钮
"""

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Callable, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# 尝试导入 Toast 库
try:
    from win10toast import ToastNotifier
    WIN10TOAST_AVAILABLE = True
except ImportError:
    WIN10TOAST_AVAILABLE = False
    logger.warning("win10toast not available")


@dataclass
class NotificationAction:
    """通知操作按钮"""
    id: str
    label: str
    callback: Optional[Callable] = None


@dataclass
class Notification:
    """通知数据"""
    title: str
    message: str
    icon_path: Optional[str] = None
    image_url: Optional[str] = None
    duration: int = 5
    actions: Optional[List[NotificationAction]] = None
    on_click: Optional[Callable] = None
    on_dismiss: Optional[Callable] = None


class NotificationHandler:
    """Windows Toast 通知处理器"""
    
    def __init__(self, app_name: str = "Home Assistant"):
        self.app_name = app_name
        self._toaster: Optional["ToastNotifier"] = None
        self._temp_dir = Path(tempfile.gettempdir()) / "ha_windows_notifications"
        self._temp_dir.mkdir(parents=True, exist_ok=True)
        self._init_toaster()
        logger.info(f"NotificationHandler initialized: {app_name}")
    
    def _init_toaster(self) -> None:
        if not WIN10TOAST_AVAILABLE:
            return
        try:
            self._toaster = ToastNotifier()
        except Exception as e:
            logger.error(f"Failed to initialize toast notifier: {e}")
    
    def show(self, notification: Notification) -> bool:
        if self._toaster is None:
            return False
        try:
            self._toaster.show_toast(
                title=notification.title,
                msg=notification.message,
                icon_path=notification.icon_path,
                duration=notification.duration,
                threaded=True,
            )
            logger.info(f"Notification shown: {notification.title}")
            return True
        except Exception as e:
            logger.error(f"Failed to show notification: {e}")
            return False
    
    def show_simple(self, title: str, message: str, duration: int = 5) -> bool:
        return self.show(Notification(title=title, message=message, duration=duration))
    
    async def show_async(self, notification: Notification) -> bool:
        if notification.image_url:
            local_path = await self._download_image(notification.image_url)
            if local_path:
                notification.icon_path = local_path
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.show, notification)
    
    async def _download_image(self, url: str) -> Optional[str]:
        try:
            import aiohttp
            import hashlib
            url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
            ext = Path(url).suffix or ".png"
            local_path = self._temp_dir / f"img_{url_hash}{ext}"
            if local_path.exists():
                return str(local_path)
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        with open(local_path, "wb") as f:
                            f.write(await response.read())
                        return str(local_path)
        except Exception as e:
            logger.error(f"Failed to download image: {e}")
        return None
    
    def cleanup(self) -> None:
        """清理临时文件"""
        try:
            for f in self._temp_dir.glob("img_*"):
                f.unlink()
        except Exception:
            pass


# 全局实例
_handler: Optional[NotificationHandler] = None


def get_notification_handler() -> NotificationHandler:
    global _handler
    if _handler is None:
        _handler = NotificationHandler()
    return _handler


async def show_notification(title: str, message: str, image_url: Optional[str] = None) -> bool:
    handler = get_notification_handler()
    notification = Notification(title=title, message=message, image_url=image_url)
    return await handler.show_async(notification)
