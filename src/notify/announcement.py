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
    """Async announcement handler"""

    def __init__(self):
        """Initialize async announcement handler"""
        self.handler = AnnouncementHandler()
        self._queue: asyncio.Queue = asyncio.Queue()

    async def handle_announcement(self, url: str, announcement: bool = True) -> None:
        """
        Handle announcement asynchronously

        Args:
            url: TTS audio URL
            announcement: Whether it's announcement type
        """
        await self.handler.handle_announcement(url, announcement)

    async def start_processing(self) -> None:
        """Start processing announcement queue"""
        while True:
            try:
                # Get announcement from queue
                announcement_data = await self._queue.get()

                # Process announcement
                await self.handler.handle_announcement(**announcement_data)

            except Exception as e:
                logger.error(f"Failed to process announcement: {e}")

    async def queue_announcement(self, url: str, announcement: bool = True) -> None:
        """
        Add announcement to queue

        Args:
            url: TTS audio URL
            announcement: Whether it's announcement type
        """
        await self._queue.put({
            'url': url,
            'announcement': announcement
        })

    def cleanup(self) -> None:
        """Cleanup resources"""
        self.handler.cleanup()


# Convenience function
async def play_announcement(url: str, announcement: bool = True) -> None:
    """
    Play announcement (convenience function)

    Args:
        url: TTS audio URL
        announcement: Whether it's announcement type
    """
    handler = AnnouncementHandler()
    try:
        await handler.handle_announcement(url, announcement)
    finally:
        handler.cleanup()


if __name__ == "__main__":
    # Test code
    logging.basicConfig(level=logging.INFO)

    async def test_announcement():
        """Test announcement handler"""
        logger.info("Testing announcement handler")

        handler = AnnouncementHandler()

        # Test announcement (using local audio file)
        # If you have a test audio file, uncomment the code below
        # test_url = "file:///path/to/test.mp3"
        # await handler.handle_announcement(test_url)

        logger.info("Announcement handler test complete (requires actual audio URL)")

    # Run test
    asyncio.run(test_announcement())
