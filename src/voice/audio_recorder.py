"""
音频录制模块
使用 soundcard 库录制麦克风音频
"""

import asyncio
import logging
import threading
from typing import Optional, Callable
from queue import Queue

import numpy as np
import soundcard

from src.i18n import get_i18n

logger = logging.getLogger(__name__)
_i18n = get_i18n()


class AudioRecorder:
    """音频录制器"""

    # 音频参数
    SAMPLE_RATE = 16000  # 16kHz（ESPHome Voice Assistant 标准）
    CHANNELS = 1  # 单声道
    BLOCK_SIZE = 1024  # 每次读取的样本数

    def __init__(self, device: Optional[str] = None):
        """
        初始化音频录制器

        Args:
            device: 音频设备名称（None = 默认麦克风）
        """
        self.device = device
        self.mic = None
        self.is_recording = False
        self.audio_queue: Queue[bytes] = Queue()
        self.recording_thread: Optional[threading.Thread] = None

    @staticmethod
    def list_microphones() -> list[str]:
        """
        列出所有可用的麦克风

        Returns:
            list[str]: 麦克风名称列表
        """
        try:
            mics = soundcard.all_microphones()
            return [mic.name for mic in mics]
        except Exception as e:
            logger.error(f"获取麦克风列表失败: {e}")
            return []

    def _get_microphone(self):
        """获取麦克风设备"""
        if self.device:
            # 通过名称查找麦克风
            mics = soundcard.all_microphones()
            for mic in mics:
                if mic.name == self.device:
                    return mic
            logger.warning(f"未找到指定的麦克风: {self.device}，使用默认麦克风")

        # 使用默认麦克风
        return soundcard.default_microphone()

    def start_recording(self, audio_callback: Optional[Callable[[bytes], None]] = None):
        """
        开始录音

        Args:
            audio_callback: 音频数据回调函数
        """
        if self.is_recording:
            logger.warning("录音已在进行中")
            return

        try:
            self.mic = self._get_microphone()
            logger.info(f"使用麦克风: {self.mic.name}")

            self.is_recording = True

            # 启动录音线程
            self.recording_thread = threading.Thread(
                target=self._record_loop,
                args=(audio_callback,),
                daemon=True
            )
            self.recording_thread.start()

            logger.info("录音已开始")

        except Exception as e:
            logger.error(f"开始录音失败: {e}")
            self.is_recording = False
            raise

    def stop_recording(self):
        """停止录音"""
        if not self.is_recording:
            return

        self.is_recording = False

        # 等待录音线程结束
        if self.recording_thread:
            self.recording_thread.join(timeout=2.0)
            self.recording_thread = None

        logger.info("录音已停止")

    def _record_loop(self, audio_callback: Optional[Callable[[bytes], None]]):
        """
        录音循环（在独立线程中运行）

        Args:
            audio_callback: 音频数据回调函数
        """
        try:
            with self.mic.recorder(
                samplerate=self.SAMPLE_RATE,
                channels=self.CHANNELS,
                blocksize=self.BLOCK_SIZE
            ) as recorder:
                while self.is_recording:
                    # 录制音频块
                    audio_array = recorder.record(numframes=self.BLOCK_SIZE)

                    # 转换为 16 位有符号整数 PCM 格式
                    audio_pcm = self._array_to_pcm(audio_array)

                    # 调用回调函数或放入队列
                    if audio_callback:
                        audio_callback(audio_pcm)
                    else:
                        self.audio_queue.put(audio_pcm)

        except Exception as e:
            logger.error(f"录音循环错误: {e}")
            self.is_recording = False

    def _array_to_pcm(self, audio_array: np.ndarray) -> bytes:
        """
        将 NumPy 音频数组转换为 PCM 字节流

        Args:
            audio_array: 音频数组（float32，范围 -1.0 到 1.0）

        Returns:
            bytes: PCM 格式的音频数据（16-bit signed little-endian）
        """
        # 限制范围到 -1.0 到 1.0
        clipped = np.clip(audio_array, -1.0, 1.0)

        # 转换为 16 位有符号整数
        int16_data = (clipped * 32767.0).astype(np.int16)

        # 转换为字节流（little-endian）
        return int16_data.tobytes()

    def get_audio_chunk(self, timeout: float = 1.0) -> Optional[bytes]:
        """
        获取音频块（阻塞）

        Args:
            timeout: 超时时间（秒）

        Returns:
            Optional[bytes]: 音频数据，如果超时则返回 None
        """
        try:
            return self.audio_queue.get(timeout=timeout)
        except:
            return None

    async def get_audio_chunk_async(self) -> Optional[bytes]:
        """
        异步获取音频块

        Returns:
            Optional[bytes]: 音频数据
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.get_audio_chunk)

    @staticmethod
    def create_silence(duration: float = 0.1) -> bytes:
        """
        创建静音音频

        Args:
            duration: 静音时长（秒）

        Returns:
            bytes: PCM 格式的静音数据
        """
        num_samples = int(AudioRecorder.SAMPLE_RATE * duration)
        silence = np.zeros(num_samples, dtype=np.int16)
        return silence.tobytes()


class AsyncAudioRecorder:
    """异步音频录制器封装"""

    def __init__(self, device: Optional[str] = None):
        """
        初始化异步音频录制器

        Args:
            device: 音频设备名称
        """
        self.recorder = AudioRecorder(device)
        self.audio_queue: asyncio.Queue[bytes] = asyncio.Queue()

    async def start_recording(self):
        """开始录音"""
        self.recorder.start_recording(self._on_audio_data)
        logger.info("异步录音已开始")

    def _on_audio_data(self, audio_data: bytes):
        """
        音频数据回调

        Args:
            audio_data: 音频数据
        """
        # 在录音线程中调用，将数据放入异步队列
        try:
            asyncio.run_coroutine_threadsafe(
                self.audio_queue.put(audio_data),
                asyncio.get_event_loop()
            )
        except Exception as e:
            logger.error(f"音频数据回调失败: {e}")

    def stop_recording(self):
        """停止录音"""
        self.recorder.stop_recording()
        logger.info("异步录音已停止")

    async def get_audio_chunk(self) -> bytes:
        """
        获取音频块

        Returns:
            bytes: 音频数据
        """
        return await self.audio_queue.get()


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.INFO)

    import tempfile

    async def test_recording():
        """测试录音"""
        logger.info("测试音频录制器")

        # 列出麦克风
        mics = AudioRecorder.list_microphones()
        logger.info(f"可用麦克风 ({len(mics)}):")
        for i, mic in enumerate(mics, 1):
            logger.info(f"  {i}. {mic}")

        # 创建录制器
        recorder = AsyncAudioRecorder()

        # 录音 5 秒
        logger.info("\n开始录音 5 秒...")
        await recorder.start_recording()

        chunks = []
        end_time = asyncio.get_event_loop().time() + 5

        while asyncio.get_event_loop().time() < end_time:
            try:
                chunk = await asyncio.wait_for(
                    recorder.get_audio_chunk(),
                    timeout=0.5
                )
                if chunk:
                    chunks.append(chunk)
                    logger.debug(f"接收到音频块: {len(chunk)} 字节")
            except asyncio.TimeoutError:
                break

        recorder.stop_recording()

        # 统计
        total_bytes = sum(len(chunk) for chunk in chunks)
        total_seconds = total_bytes / 2 / 16000  # 16-bit, 16kHz
        logger.info(f"\n录音完成:")
        logger.info(f"  总字节: {total_bytes}")
        logger.info(f"  总时长: {total_seconds:.2f} 秒")
        logger.info(f"  块数量: {len(chunks)}")

    # 运行测试
    asyncio.run(test_recording())
