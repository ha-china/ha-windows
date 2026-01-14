"""
MPV 媒体播放器模块
使用 python-mpv 播放音频（TTS 等）
"""

import asyncio
import logging
from typing import Optional, Callable
from enum import Enum

from mpv import MPV

from src.i18n import get_i18n

logger = logging.getLogger(__name__)
_i18n = get_i18n()


class PlaybackState(Enum):
    """播放状态"""
    STOPPED = "stopped"
    PLAYING = "playing"
    PAUSED = "paused"


class MpvMediaPlayer:
    """MPV 媒体播放器封装"""

    def __init__(self, audio_device: Optional[str] = None):
        """
        初始化 MPV 播放器

        Args:
            audio_device: 音频输出设备名称（None = 默认设备）
        """
        # 音量控制参数
        self._duck_volume = 50  # Duck 音量（语音对话时）
        self._normal_volume = 100  # 正常音量
        self._current_volume = 100

        # 播放状态
        self.state = PlaybackState.STOPPED

        # 创建 MPV 实例
        self.player = MPV(
            # 音频设置
            audio_device=audio_device,
            volume=self._current_volume,

            # 视频设置（禁用视频输出）
            vo='null',
            vid='no',

            # 其他设置
            quiet=True,
            # 保持播放器在后台运行
            keep_open=False,
        )

        # 注册事件回调
        self._on_playback_start: Optional[Callable] = None
        self._on_playback_end: Optional[Callable] = None

        logger.info(f"MPV 播放器已初始化")

    @property
    def volume(self) -> int:
        """获取当前音量"""
        return self._current_volume

    @volume.setter
    def volume(self, value: int):
        """
        设置音量

        Args:
            value: 音量值（0-100）
        """
        self._current_volume = max(0, min(100, value))
        self.player.volume = self._current_volume
        logger.debug(f"音量设置为: {self._current_volume}")

    def play_url(self, url: str, announcement: bool = False) -> None:
        """
        播放音频 URL

        Args:
            url: 音频 URL（HTTP、本地文件等）
            announcement: 是否为通知（降低其他音量）
        """
        try:
            logger.info(f"播放音频: {url}")

            # 如果是通知，降低音量
            if announcement:
                self.duck()

            # 播放音频
            self.player.play(url)

            self.state = PlaybackState.PLAYING

            logger.info("音频播放已开始")

        except Exception as e:
            logger.error(f"播放失败: {e}")
            self.state = PlaybackState.STOPPED
            raise

    def play_file(self, file_path: str) -> None:
        """
        播放本地音频文件

        Args:
            file_path: 音频文件路径
        """
        self.play_url(file_path)

    def stop(self) -> None:
        """停止播放"""
        try:
            if self.state != PlaybackState.STOPPED:
                self.player.terminate()
                self.state = PlaybackState.STOPPED
                logger.info("播放已停止")

        except Exception as e:
            logger.error(f"停止播放失败: {e}")

    def pause(self) -> None:
        """暂停播放"""
        try:
            if self.state == PlaybackState.PLAYING:
                self.player.pause = True
                self.state = PlaybackState.PAUSED
                logger.info("播放已暂停")

        except Exception as e:
            logger.error(f"暂停播放失败: {e}")

    def resume(self) -> None:
        """恢复播放"""
        try:
            if self.state == PlaybackState.PAUSED:
                self.player.pause = False
                self.state = PlaybackState.PLAYING
                logger.info("播放已恢复")

        except Exception as e:
            logger.error(f"恢复播放失败: {e}")

    def duck(self) -> None:
        """
        降低音量（Duck）
        用于语音对话时降低背景音量
        """
        self.volume = self._duck_volume
        logger.debug(f"音量已降低到: {self._duck_volume}")

    def unduck(self) -> None:
        """
        恢复音量（Unduck）
        语音对话结束后恢复正常音量
        """
        self.volume = self._normal_volume
        logger.debug(f"音量已恢复到: {self._normal_volume}")

    def set_duck_volume(self, volume: int) -> None:
        """
        设置 Duck 音量

        Args:
            volume: Duck 音量值（0-100）
        """
        self._duck_volume = max(0, min(100, volume))

    def set_normal_volume(self, volume: int) -> None:
        """
        设置正常音量

        Args:
            volume: 正常音量值（0-100）
        """
        self._normal_volume = max(0, min(100, volume))

    @staticmethod
    def list_audio_devices() -> list[str]:
        """
        列出所有可用的音频输出设备

        Returns:
            list[str]: 音频设备名称列表
        """
        try:
            mpv = MPV()
            devices = mpv.command('audio-device-list')
            device_names = []

            for device in devices:
                if 'name' in device:
                    device_names.append(device['name'])

            return device_names

        except Exception as e:
            logger.error(f"获取音频设备列表失败: {e}")
            return []

    def cleanup(self) -> None:
        """清理资源"""
        try:
            self.stop()
            # MPV 会自动清理
            logger.info("MPV 播放器已清理")

        except Exception as e:
            logger.error(f"清理 MPV 失败: {e}")


class AsyncMpvMediaPlayer:
    """异步 MPV 播放器封装"""

    def __init__(self, audio_device: Optional[str] = None):
        """
        初始化异步 MPV 播放器

        Args:
            audio_device: 音频输出设备名称
        """
        self.player = MpvMediaPlayer(audio_device)
        self._playback_done = asyncio.Event()

    async def play_url(
        self,
        url: str,
        announcement: bool = False,
        wait: bool = True
    ) -> None:
        """
        播放音频 URL

        Args:
            url: 音频 URL
            announcement: 是否为通知
            wait: 是否等待播放完成
        """
        self._playback_done.clear()

        # 在线程池中执行播放
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: self.player.play_url(url, announcement)
        )

        if wait:
            # 等待播放完成
            await self._wait_for_playback_end()

    async def play_file(self, file_path: str, wait: bool = True) -> None:
        """
        播放本地音频文件

        Args:
            file_path: 音频文件路径
            wait: 是否等待播放完成
        """
        await self.play_url(file_path, wait=wait)

    async def stop(self) -> None:
        """停止播放"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.player.stop)
        self._playback_done.set()

    async def pause(self) -> None:
        """暂停播放"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.player.pause)

    async def resume(self) -> None:
        """恢复播放"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.player.resume)

    async def _wait_for_playback_end(self, timeout: float = 300.0) -> None:
        """
        等待播放结束

        Args:
            timeout: 超时时间（秒）
        """
        try:
            # TODO: 实现 MPV 播放结束事件监听
            # 目前使用简单的超时等待
            await asyncio.sleep(1)  # 至少等待 1 秒

        except asyncio.TimeoutError:
            logger.warning("等待播放结束超时")

    def cleanup(self) -> None:
        """清理资源"""
        self.player.cleanup()


# 便捷函数
def play_audio_url(url: str, announcement: bool = False) -> None:
    """
    播放音频 URL（同步）

    Args:
        url: 音频 URL
        announcement: 是否为通知
    """
    player = MpvMediaPlayer()
    try:
        player.play_url(url, announcement)
    finally:
        player.cleanup()


async def play_audio_url_async(
    url: str,
    announcement: bool = False,
    wait: bool = True
) -> None:
    """
    播放音频 URL（异步）

    Args:
        url: 音频 URL
        announcement: 是否为通知
        wait: 是否等待播放完成
    """
    player = AsyncMpvMediaPlayer()
    try:
        await player.play_url(url, announcement, wait)
    finally:
        player.cleanup()


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.INFO)

    import sys

    async def test_player():
        """测试播放器"""
        logger.info("测试 MPV 播放器")

        # 列出音频设备
        devices = MpvMediaPlayer.list_audio_devices()
        logger.info(f"可用音频设备 ({len(devices)}):")
        for i, device in enumerate(devices, 1):
            logger.info(f"  {i}. {device}")

        # 如果有命令行参数，播放指定的音频文件
        if len(sys.argv) > 1:
            url = sys.argv[1]
        else:
            logger.info("\n使用方法: python mpv_player.py <音频文件或URL>")
            return

        logger.info(f"\n播放: {url}")
        player = AsyncMpvMediaPlayer()

        try:
            await player.play_url(url, wait=True)
            logger.info("播放完成")
        finally:
            player.cleanup()

    # 运行测试
    asyncio.run(test_player())
