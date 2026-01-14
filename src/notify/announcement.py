"""
通知处理模块
处理来自 Home Assistant 的通知（ESPHome Announcement）
"""

import asyncio
import logging
from typing import Callable, Optional

from ..voice.mpv_player import AsyncMpvMediaPlayer
from ..i18n import get_i18n

logger = logging.getLogger(__name__)
_i18n = get_i18n()


class AnnouncementHandler:
    """ESPHome Announcement 处理器"""

    def __init__(self):
        """初始化通知处理器"""
        self.player: Optional[AsyncMpvMediaPlayer] = None
        self._on_announcement: Optional[Callable] = None

        logger.info("通知处理器已初始化")

    def on_announcement(self, callback: Callable) -> None:
        """
        注册通知回调

        Args:
            callback: 通知回调函数
        """
        self._on_announcement = callback

    async def handle_announcement(self, url: str, announcement: bool = True) -> None:
        """
        处理 ESPHome Announcement（TTS 播报）

        Args:
            url: TTS 音频 URL
            announcement: 是否为通知类型
        """
        try:
            logger.info(f"处理播报: {url}")

            # 创建播放器
            if not self.player:
                self.player = AsyncMpvMediaPlayer()

            # 播放 TTS
            await self.player.play_url(url, announcement=announcement, wait=True)

            # 调用回调
            if self._on_announcement:
                await self._on_announcement(url)

            logger.info("播报完成")

        except Exception as e:
            logger.error(f"播报失败: {e}")
            raise

    async def play_tts(self, text: str, language: str = 'zh-CN') -> None:
        """
        播放 TTS（需要 HA 生成音频 URL）

        Args:
            text: 要播报的文本
            language: 语言代码
        """
        # TODO: 实现 TTS 播放
        # 这需要调用 Home Assistant 的 TTS 服务生成音频 URL
        # 然后使用 handle_announcement 播放

        logger.info(f"TTS 播报: {text} ({language})")
        logger.warning("TTS 播放功能尚未完全实现")

    def cleanup(self) -> None:
        """清理资源"""
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
