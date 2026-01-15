"""
Announcement Handler Module

Handles announcements from Home Assistant (ESPHome Announcement).
"""

import asyncio
import logging
from typing import Callable, Optional

from src.voice.mpv_player import AsyncAudioPlayer
from src.i18n import get_i18n

logger = logging.getLogger(__name__)
_i18n = get_i18n()


class AnnouncementHandler:
    """ESPHome Announcement Handler"""

    def __init__(self):
        """Initialize announcement handler"""
        self.player: Optional[AsyncAudioPlayer] = None
        self._on_announcement: Optional[Callable] = None

        logger.info("Announcement handler initialized")

    def on_announcement(self, callback: Callable) -> None:
        """
        Register announcement callback

        Args:
            callback: Announcement callback function
        """
        self._on_announcement = callback

    async def handle_announcement(self, url: str, announcement: bool = True) -> None:
        """
        Handle ESPHome Announcement (TTS playback with streaming)

        Args:
            url: TTS audio URL
            announcement: Whether it's announcement type
        """
        try:
            logger.info(f"Handling announcement: {url}")

            # Create player
            if not self.player:
                self.player = AsyncAudioPlayer()

            # Use streaming playback - no need to download first
            await self.player.play_url(url, announcement=announcement, wait=True)

            # Call callback
            if self._on_announcement:
                await self._on_announcement(url)

            logger.info("Announcement finished")

        except Exception as e:
            logger.error(f"Announcement failed: {e}")
            raise

    async def play_tts(self, text: str, language: str = 'zh-CN') -> None:
        """
        Play TTS (requires HA to generate audio URL)

        Args:
            text: Text to speak
            language: Language code
        """
        # TODO: Implement TTS playback
        # This requires calling Home Assistant's TTS service to generate audio URL
        # Then use handle_announcement to play

        logger.info(f"TTS announcement: {text} ({language})")
        logger.warning("TTS playback not fully implemented")

    def cleanup(self) -> None:
        """Cleanup resources"""
        if self.player:
            self.player.cleanup()
            self.player = None


class AsyncAnnouncementHandler:
    """异步通知处理器"""

    def __init__(self):
        """初始化异步通知处理器"""
        self.handler = AnnouncementHandler()
        self._queue: asyncio.Queue = asyncio.Queue()

    async def handle_announcement(self, url: str, announcement: bool = True) -> None:
        """
        异步处理播报

        Args:
            url: TTS 音频 URL
            announcement: 是否为通知类型
        """
        await self.handler.handle_announcement(url, announcement)

    async def start_processing(self) -> None:
        """开始处理通知队列"""
        while True:
            try:
                # 从队列获取通知
                announcement_data = await self._queue.get()

                # 处理通知
                await self.handler.handle_announcement(**announcement_data)

            except Exception as e:
                logger.error(f"处理通知失败: {e}")

    async def queue_announcement(self, url: str, announcement: bool = True) -> None:
        """
        将通知加入队列

        Args:
            url: TTS 音频 URL
            announcement: 是否为通知类型
        """
        await self._queue.put({
            'url': url,
            'announcement': announcement
        })

    def cleanup(self) -> None:
        """清理资源"""
        self.handler.cleanup()


# 便捷函数
async def play_announcement(url: str, announcement: bool = True) -> None:
    """
    播放通知（便捷函数）

    Args:
        url: TTS 音频 URL
        announcement: 是否为通知类型
    """
    handler = AnnouncementHandler()
    try:
        await handler.handle_announcement(url, announcement)
    finally:
        handler.cleanup()


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.INFO)

    async def test_announcement():
        """测试通知处理器"""
        logger.info("测试通知处理器")

        handler = AnnouncementHandler()

        # 测试播报（使用本地音频文件）
        # 如果有测试音频文件，可以取消注释下面的代码
        # test_url = "file:///path/to/test.mp3"
        # await handler.handle_announcement(test_url)

        logger.info("通知处理器测试完成（需要实际音频 URL）")

    # 运行测试
    asyncio.run(test_announcement())
