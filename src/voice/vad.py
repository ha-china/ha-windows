"""
VAD（Voice Activity Detection）语音活动检测模块
使用 webrtcvad 检测语音和静音
"""

import logging
from typing import Optional

import webrtcvad
import numpy as np

from src.i18n import get_i18n

logger = logging.getLogger(__name__)
_i18n = get_i18n()


class VAD:
    """语音活动检测器"""

    # 音频参数
    SAMPLE_RATE = 16000  # 16kHz
    FRAME_DURATION_MS = 30  # 帧时长（毫秒）

    # 计算：
    # frame_size = (sample_rate * frame_duration_ms) / 1000
    # frame_size = (16000 * 30) / 1000 = 480 样本

    @staticmethod
    def get_frame_size() -> int:
        """获取帧大小"""
        return int(VAD.SAMPLE_RATE * VAD.FRAME_DURATION_MS / 1000)

    def __init__(self, aggressiveness: int = 2):
        """
        初始化 VAD

        Args:
            aggressiveness: 检测激进程度（0-3）
                            0: 最不激进（更多噪声被识别为语音）
                            1: 不激进
                            2: 激进（默认）
                            3: 最激进（需要更清晰的语音）
        """
        if not 0 <= aggressiveness <= 3:
            raise ValueError("aggressiveness 必须在 0-3 之间")

        self.vad = webrtcvad.Vad(aggressiveness)
        self.silence_threshold = 1.0  # 静音阈值（秒）

        logger.info(f"VAD 已初始化（激进程度: {aggressiveness}）")

    def is_speech(self, audio_frame: bytes) -> bool:
        """
        检测音频帧是否包含语音

        Args:
            audio_frame: 音频帧（PCM 格式，16-bit signed little-endian）

        Returns:
            bool: 是否包含语音
        """
        try:
            # 检查帧大小
            frame_size = self.get_frame_size()
            expected_bytes = frame_size * 2  # 16-bit = 2 字节

            if len(audio_frame) < expected_bytes:
                logger.warning(
                    f"音频帧太小: {len(audio_frame)} 字节 "
                    f"（期望: {expected_bytes} 字节）"
                )
                return False

            # 使用 WebRTC VAD 检测
            is_speech = self.vad.is_speech(audio_frame, self.SAMPLE_RATE)

            return is_speech

        except Exception as e:
            logger.error(f"VAD 检测失败: {e}")
            return False

    def is_speech_numpy(self, audio_array: np.ndarray) -> bool:
        """
        检测 NumPy 音频数组是否包含语音

        Args:
            audio_array: 音频数组（float32，-1.0 到 1.0）

        Returns:
            bool: 是否包含语音
        """
        # 转换为 PCM 格式
        pcm_data = self._numpy_to_pcm(audio_array)
        return self.is_speech(pcm_data)

    def detect_silence(
        self,
        audio_frames: list[bytes],
        threshold: float = 1.0
    ) -> bool:
        """
        检测音频帧序列是否包含足够的静音

        Args:
            audio_frames: 音频帧列表
            threshold: 静音阈值（秒）

        Returns:
            bool: 是否检测到静音
        """
        frame_duration = self.FRAME_DURATION_MS / 1000.0
        silence_frames = int(threshold / frame_duration)

        # 统计连续的静音帧
        consecutive_silence = 0

        for frame in audio_frames:
            if not self.is_speech(frame):
                consecutive_silence += 1
                if consecutive_silence >= silence_frames:
                    return True
            else:
                consecutive_silence = 0

        return False

    def _numpy_to_pcm(self, audio_array: np.ndarray) -> bytes:
        """
        将 NumPy 音频数组转换为 PCM 格式

        Args:
            audio_array: 音频数组（float32，-1.0 到 1.0）

        Returns:
            bytes: PCM 格式的音频数据
        """
        # 限制范围
        clipped = np.clip(audio_array, -1.0, 1.0)

        # 转换为 16 位有符号整数
        int16_data = (clipped * 32767.0).astype(np.int16)

        # 转换为字节流
        return int16_data.tobytes()

    def set_aggressiveness(self, aggressiveness: int) -> None:
        """
        设置检测激进程度

        Args:
            aggressiveness: 激进程度（0-3）
        """
        if not 0 <= aggressiveness <= 3:
            raise ValueError("aggressiveness 必须在 0-3 之间")

        self.vad.set_aggressiveness(aggressiveness)
        logger.info(f"VAD 激进程度已设置为: {aggressiveness}")

    def set_silence_threshold(self, threshold: float) -> None:
        """
        设置静音阈值

        Args:
            threshold: 静音阈值（秒）
        """
        if threshold < 0:
            raise ValueError("threshold 必须大于等于 0")

        self.silence_threshold = threshold
        logger.info(f"静音阈值已设置为: {threshold} 秒")


class StreamingVAD:
    """流式 VAD 处理器"""

    def __init__(self, aggressiveness: int = 2, silence_threshold: float = 1.0):
        """
        初始化流式 VAD

        Args:
            aggressiveness: VAD 激进程度
            silence_threshold: 静音阈值（秒）
        """
        self.vad = VAD(aggressiveness)
        self.silence_threshold = silence_threshold

        self._speech_frames = 0
        self._silence_frames = 0
        self._is_speaking = False

    def process_frame(self, audio_frame: bytes) -> tuple[bool, bool]:
        """
        处理音频帧

        Args:
            audio_frame: 音频帧

        Returns:
            tuple[bool, bool]: (是否为语音, 是否检测到静音结束)
        """
        is_speech = self.vad.is_speech(audio_frame)

        if is_speech:
            self._speech_frames += 1
            self._silence_frames = 0
            self._is_speaking = True
        else:
            self._silence_frames += 1
            if not self._is_speaking:
                # 还未开始说话
                pass

        # 检测是否说话结束
        frame_duration = self.vad.FRAME_DURATION_MS / 1000.0
        silence_frames_needed = int(self.silence_threshold / frame_duration)

        speech_ended = (
            self._is_speaking and
            self._silence_frames >= silence_frames_needed
        )

        if speech_ended:
            # 重置状态
            self._is_speaking = False
            self._silence_frames = 0
            self._speech_frames = 0

        return is_speech, speech_ended

    def reset(self) -> None:
        """重置状态"""
        self._speech_frames = 0
        self._silence_frames = 0
        self._is_speaking = False


# 便捷函数
def create_vad(aggressiveness: int = 2) -> VAD:
    """
    创建 VAD 实例

    Args:
        aggressiveness: 激进程度（0-3）

    Returns:
        VAD: VAD 实例
    """
    return VAD(aggressiveness)


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.INFO)

    def test_vad():
        """测试 VAD"""
        logger.info("测试 VAD（语音活动检测）")

        # 创建 VAD
        vad = VAD(aggressiveness=2)

        # 创建测试音频帧
        frame_size = vad.get_frame_size()

        # 测试 1: 静音帧
        silence_frame = bytes(frame_size * 2)  # 全零
        is_speech = vad.is_speech(silence_frame)
        logger.info(f"静音帧检测结果: {'语音' if is_speech else '静音'}")

        # 测试 2: 模拟语音帧（随机噪声）
        import random
        noise_frame = bytes(
            random.getrandbits(8) for _ in range(frame_size * 2)
        )
        is_speech = vad.is_speech(noise_frame)
        logger.info(f"噪声帧检测结果: {'语音' if is_speech else '静音'}")

        logger.info("\nVAD 测试完成")

    # 运行测试
    test_vad()
