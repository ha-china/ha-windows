"""
Voice Assistant Module

Integrates audio recording, VAD, wake word detection, and audio streaming.
For use with ESPHome server mode (HA connects to Windows).
"""

import asyncio
import logging
import threading
from typing import Callable, Optional, Dict

from .audio_recorder import AsyncAudioRecorder
from .wake_word import AsyncWakeWordDetector
from .vad import StreamingVAD

from src.i18n import get_i18n

logger = logging.getLogger(__name__)
_i18n = get_i18n()


class AudioStreamHandler:
    """
    Audio Stream Handler for ESPHome Voice Assistant

    Manages audio recording with VAD and queues audio chunks for HTTP streaming.
    Used by ESPHome protocol server when HA requests audio.
    """

    def __init__(self):
        """Initialize audio stream handler"""
        self._recording = False
        self._audio_queue: Optional[asyncio.Queue] = None
        self._recorder: Optional[AsyncAudioRecorder] = None
        self._vad: Optional[StreamingVAD] = None
        self._recording_task: Optional[asyncio.Task] = None

    def get_recorder(self) -> AsyncAudioRecorder:
        """Get or create audio recorder"""
        if self._recorder is None:
            self._recorder = AsyncAudioRecorder()
            logger.info("Audio recorder initialized")
        return self._recorder

    def get_vad(self) -> StreamingVAD:
        """Get or create VAD detector"""
        if self._vad is None:
            self._vad = StreamingVAD(aggressiveness=2, silence_threshold=1.0)
            logger.info("VAD detector initialized")
        return self._vad

    async def start_recording(self) -> Optional[Callable[[], asyncio.Queue]]:
        """
        Start audio recording with VAD

        Returns:
            Callable that returns the audio queue, or None if already recording
        """
        if self._recording:
            logger.warning("Recording already in progress")
            return None

        self._recording = True
        self._audio_queue = asyncio.Queue()

        # Start recording task
        self._recording_task = asyncio.create_task(self._record_loop())

        logger.info("Audio recording started")
        return lambda: self._audio_queue

    async def _record_loop(self):
        """Recording loop with VAD - stops on silence detection"""
        recorder = self.get_recorder()
        vad = self.get_vad()

        await recorder.start_recording()

        silence_count = 0
        max_silence = 30  # 3 seconds of silence (30 chunks)

        try:
            while self._recording:
                # Get audio chunk
                chunk = await recorder.get_audio_chunk()
                if not chunk:
                    continue

                # Put in queue for HTTP streaming
                await self._audio_queue.put(chunk)

                # Check for silence (VAD)
                is_speech, speech_ended = vad.process_frame(chunk)
                
                # If speech ended (detected silence after speech), stop recording
                if speech_ended:
                    logger.info("Speech ended, stopping recording")
                    break

        except asyncio.CancelledError:
            logger.info("Recording task cancelled")
        finally:
            await recorder.stop_recording()
            self._recording = False
            # Signal end of recording
            await self._audio_queue.put(None)
            logger.info("Audio recording stopped")

    async def stop_recording(self):
        """Stop audio recording"""
        if not self._recording:
            return

        self._recording = False

        if self._recording_task:
            self._recording_task.cancel()
            try:
                await self._recording_task
            except asyncio.CancelledError:
                pass
            self._recording_task = None

        logger.info("Audio recording stopped")

    def is_recording(self) -> bool:
        """Check if currently recording"""
        return self._recording


class VoiceAssistant:
    """Voice Assistant 集成"""

    def __init__(
        self,
        audio_device: Optional[str] = None,
        wake_word_model: str = 'hey_jarvis',
        send_audio_callback: Optional[Callable[[bytes], None]] = None,
    ):
        """
        Initialize Voice Assistant

        Args:
            audio_device: Audio device name
            wake_word_model: Wake word model
            send_audio_callback: Audio data send callback
        """
        # Audio components
        self.recorder = AsyncAudioRecorder(audio_device)
        self.wake_word_detector = AsyncWakeWordDetector(wake_word_model)
        self.vad = StreamingVAD(aggressiveness=2, silence_threshold=1.0)

        # 状态
        self._running = False
        self._listening = False
        self._processing = False

        # 回调
        self._on_response: Optional[Callable] = None
        self._send_audio_callback = send_audio_callback

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
        """Stop Voice Assistant"""
        self._running = False
        self._listening = False
        self._processing = False

        await self.recorder.stop_recording()

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
        发送音频到 Home Assistant（通过回调函数）

        Args:
            audio_data: 音频数据
        """
        try:
            logger.info(f"发送音频到 Home Assistant (size={len(audio_data)})...")

            # 使用回调函数发送音频数据
            if self._send_audio_callback:
                self._send_audio_callback(audio_data)
            else:
                logger.warning("未设置音频发送回调，音频数据将被忽略")

            # 等待响应处理由调用者负责
            # TTS 播放由 esphome_protocol.py 的 _handle_voice_assistant_audio 处理

            logger.info("音频数据已发送")

        except Exception as e:
            logger.error(f"发送到 Assistant 失败: {e}")
        finally:
            self._processing = False

    def cleanup(self) -> None:
        """Cleanup resources"""
        pass  # No resources to cleanup


# 便捷函数
def create_voice_assistant(
    audio_device: Optional[str] = None,
    wake_word_model: str = 'hey_jarvis',
    send_audio_callback: Optional[Callable[[bytes], None]] = None,
) -> VoiceAssistant:
    """
    创建 Voice Assistant（便捷函数）

    Args:
        audio_device: 音频设备
        wake_word_model: 唤醒词模型
        send_audio_callback: 音频数据发送回调函数

    Returns:
        VoiceAssistant: Voice Assistant 实例
    """
    return VoiceAssistant(audio_device, wake_word_model, send_audio_callback)


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
