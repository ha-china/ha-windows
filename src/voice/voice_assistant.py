"""
Voice Assistant 协议实现
集成音频录制、VAD、唤醒词检测和 ESPHome 连接
"""

import asyncio
import logging
from typing import Optional, Callable

from .audio_recorder import AsyncAudioRecorder
from .mpv_player import AsyncMpvMediaPlayer
from .wake_word import AsyncWakeWordDetector
from .vad import StreamingVAD

from ..core.esphome_connection import ESPHomeConnection
from ..i18n import get_i18n

logger = logging.getLogger(__name__)
_i18n = get_i18n()


class VoiceAssistant:
    """Voice Assistant 集成"""

    def __init__(
        self,
        connection: ESPHomeConnection,
        audio_device: Optional[str] = None,
        wake_word_model: str = 'hey_jarvis',
    ):
        """
        初始化 Voice Assistant

        Args:
            connection: ESPHome 连接
            audio_device: 音频设备名称
            wake_word_model: 唤醒词模型
        """
        self.connection = connection

        # 音频组件
        self.recorder = AsyncAudioRecorder(audio_device)
        self.player = AsyncMpvMediaPlayer()
        self.wake_word_detector = AsyncWakeWordDetector(wake_word_model)
        self.vad = StreamingVAD(aggressiveness=2, silence_threshold=1.0)

        # 状态
        self._running = False
        self._listening = False
        self._processing = False

        # 回调
        self._on_response: Optional[Callable] = None

        logger.info("Voice Assistant 已初始化")

    def on_response(self, callback: Callable) -> None:
        """
        注册响应回调

        Args:
            callback: 响应回调函数
        """
        self._on_response = callback

    async def start(self, use_wake_word: bool = True) -> None:
        """
        启动 Voice Assistant

        Args:
            use_wake_word: 是否使用唤醒词
        """
        if self._running:
            logger.warning("Voice Assistant 已在运行")
            return

        self._running = True

        if use_wake_word:
            # 唤醒词模式
            await self._wake_word_loop()
        else:
            # 手动模式（按钮触发）
            await self._manual_loop()

    async def stop(self) -> None:
        """停止 Voice Assistant"""
        self._running = False
        self._listening = False
        self._processing = False

        await self.recorder.stop_recording()
        await self.player.stop()

    async def _wake_word_loop(self) -> None:
        """唤醒词循环"""
        logger.info("启动唤醒词模式")

        await self.recorder.start_recording()

        try:
            while self._running:
                # 获取音频块
                audio_chunk = await self.recorder.get_audio_chunk()

                if not audio_chunk:
                    continue

                # 转换为 numpy 数组
                import numpy as np
                audio_array = np.frombuffer(audio_chunk, dtype=np.int16).astype(np.float32) / 32768.0

                # 检测唤醒词
                detected = self.wake_word_detector.process_audio(audio_array)

                if detected:
                    logger.info("检测到唤醒词！")
                    await self._start_conversation()

        finally:
            await self.recorder.stop_recording()

    async def _manual_loop(self) -> None:
        """手动模式循环"""
        logger.info("启动手动模式")

        while self._running:
            # 等待触发信号
            await asyncio.sleep(1)

    async def trigger(self) -> None:
        """手动触发 Voice Assistant"""
        if not self._running:
            logger.warning("Voice Assistant 未启动")
            return

        if self._processing:
            logger.warning("Voice Assistant 正在处理")
            return

        await self._start_conversation()

    async def _start_conversation(self) -> None:
        """开始对话"""
        self._listening = True
        self._processing = True

        logger.info("开始聆听...")

        try:
            # 开始录音
            # await self.recorder.start_recording()

            # 使用 VAD 检测语音结束
            audio_data = await self._record_with_vad()

            self._listening = False
            logger.info("语音录制完成")

            # 发送到 Home Assistant
            await self._send_to_assistant(audio_data)

        except Exception as e:
            logger.error(f"对话失败: {e}")
            self._listening = False
            self._processing = False

    async def _record_with_vad(self) -> bytes:
        """
        使用 VAD 录制语音

        Returns:
            bytes: 录制的音频数据
        """
        audio_chunks = []

        # TODO: 实现实际的 VAD 录音
        # 这里只是示例代码

        # 模拟录音 3 秒
        await asyncio.sleep(3)

        # 收集音频块
        for _ in range(10):  # 收集 10 个块
            chunk = await self.recorder.get_audio_chunk()
            if chunk:
                audio_chunks.append(chunk)

        # 合并所有块
        return b''.join(audio_chunks)

    async def _send_to_assistant(self, audio_data: bytes) -> None:
        """
        发送音频到 Home Assistant

        Args:
            audio_data: 音频数据
        """
        try:
            logger.info("发送音频到 Home Assistant...")

            # TODO: 实现 ESPHome Voice Assistant API 调用
            # 这里需要参考 linux-voice-assistant 的实现

            # 模拟等待响应
            await asyncio.sleep(2)

            # 假设收到 TTS URL
            tts_url = "https://example.com/tts.mp3"

            # 播放响应
            await self.player.play_url(tts_url, announcement=True)

            logger.info("响应播放完成")

            if self._on_response:
                await self._on_response("示例响应")

        except Exception as e:
            logger.error(f"发送到 Assistant 失败: {e}")
        finally:
            self._processing = False

    def cleanup(self) -> None:
        """清理资源"""
        self.player.cleanup()


# 便捷函数
def create_voice_assistant(
    connection: ESPHomeConnection,
    audio_device: Optional[str] = None,
    wake_word_model: str = 'hey_jarvis',
) -> VoiceAssistant:
    """
    创建 Voice Assistant（便捷函数）

    Args:
        connection: ESPHome 连接
        audio_device: 音频设备
        wake_word_model: 唤醒词模型

    Returns:
        VoiceAssistant: Voice Assistant 实例
    """
    return VoiceAssistant(connection, audio_device, wake_word_model)


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.INFO)

    async def test_voice_assistant():
        """测试 Voice Assistant"""
        logger.info("测试 Voice Assistant")

        # 注意：需要实际的 ESPHome 连接
        logger.info("Voice Assistant 测试需要完整的连接")


    # 运行测试
    asyncio.run(test_voice_assistant())
