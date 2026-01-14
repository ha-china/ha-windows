"""
唤醒词检测模块
使用 pymicro-wakeword 检测唤醒词
"""

import asyncio
import logging
from typing import Callable, Optional

import numpy as np
from pymicro_wakeword import MicroWakeWord

from ..i18n import get_i18n

logger = logging.getLogger(__name__)
_i18n = get_i18n())


class WakeWordDetector:
    """唤醒词检测器"""

    # 支持的唤醒词模型
    AVAILABLE_MODELS = {
        'hey_jarvis': 'hey_jarvis',
        'smart_home': 'smart_home',
        'alexa': 'alexa',
    }

    def __init__(self, model_name: str = 'hey_jarvis'):
        """
        初始化唤醒词检测器

        Args:
            model_name: 唤醒词模型名称
        """
        if model_name not in self.AVAILABLE_MODELS:
            logger.warning(f"未知的唤醒词模型: {model_name}，使用默认模型")
            model_name = 'hey_jarvis'

        self.model_name = model_name
        self.model = MicroWakeWord(model_name)

        self._on_wake_word: Optional[Callable] = None

        logger.info(f"唤醒词检测器已初始化（模型: {model_name}）")

    def on_wake_word(self, callback: Callable[[], None]) -> None:
        """
        注册唤醒词回调

        Args:
            callback: 唤醒词触发时的回调函数
        """
        self._on_wake_word = callback

    def process_audio(self, audio_chunk: np.ndarray) -> bool:
        """
        处理音频并检测唤醒词

        Args:
            audio_chunk: 音频数据（numpy 数组，16kHz mono）

        Returns:
            bool: 是否检测到唤醒词
        """
        try:
            # 使用 pymicro-wakeword 处理音频
            detected = self.model.process_streaming(audio_chunk)

            if detected and self._on_wake_word:
                logger.info(f"检测到唤醒词: {self.model_name}")
                # 调用回调函数
                self._on_wake_word()

            return detected

        except Exception as e:
            logger.error(f"唤醒词检测失败: {e}")
            return False


class AsyncWakeWordDetector:
    """异步唤醒词检测器"""

    def __init__(self, model_name: str = 'hey_jarvis'):
        """
        初始化异步唤醒词检测器

        Args:
            model_name: 唤醒词模型名称
        """
        self.detector = WakeWordDetector(model_name)
        self._wake_word_event = asyncio.Event()

        # 设置回调
        self.detector.on_wake_word(self._on_wake_word)

    def _on_wake_word(self) -> None:
        """唤醒词回调"""
        self._wake_word_event.set()

    def process_audio(self, audio_chunk: np.ndarray) -> bool:
        """
        处理音频并检测唤醒词

        Args:
            audio_chunk: 音频数据

        Returns:
            bool: 是否检测到唤醒词
        """
        return self.detector.process_audio(audio_chunk)

    async def wait_for_wake_word(self, timeout: Optional[float] = None) -> bool:
        """
        等待唤醒词

        Args:
            timeout: 超时时间（秒），None 表示无限等待

        Returns:
            bool: 是否检测到唤醒词
        """
        try:
            await asyncio.wait_for(self._wake_word_event.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            return False
        finally:
            self._wake_word_event.clear()

    @staticmethod
    def list_available_models() -> list[str]:
        """
        列出可用的唤醒词模型

        Returns:
            list[str]: 模型名称列表
        """
        return list(WakeWordDetector.AVAILABLE_MODELS.keys())


# 便捷函数
def create_wake_word_detector(model_name: str = 'hey_jarvis') -> WakeWordDetector:
    """
    创建唤醒词检测器

    Args:
        model_name: 唤醒词模型名称

    Returns:
        WakeWordDetector: 唤醒词检测器实例
    """
    return WakeWordDetector(model_name)


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.INFO)

    async def test_detector():
        """测试唤醒词检测器"""
        logger.info("测试唤醒词检测器")

        # 列出可用模型
        models = AsyncWakeWordDetector.list_available_models()
        logger.info(f"可用模型 ({len(models)}):")
        for model in models:
            logger.info(f"  - {model}")

        logger.info("\n注意: 完整测试需要真实的麦克风输入")
        logger.info("这里只是演示 API 使用")

        # 创建检测器
        detector = AsyncWakeWordDetector('hey_jarvis')

        # 模拟音频数据处理
        # 实际使用时应该从麦克风读取真实音频
        audio_data = np.zeros(16000, dtype=np.float32)  # 1 秒静音
        detected = detector.process_audio(audio_data)

        if not detected:
            logger.info("未检测到唤醒词（静音）")

    # 运行测试
    asyncio.run(test_detector())
