"""
音频设备控制命令模块
实现音频输入/输出设备切换
"""

import logging
from typing import List

from src.i18n import get_i18n

logger = logging.getLogger(__name__)
_i18n = get_i18n()


class AudioCommands:
    """音频设备控制命令"""

    @staticmethod
    def list_devices() -> dict:
        """
        列出所有音频设备

        Returns:
            dict: 设备列表
        """
        try:
            import soundcard

            # 获取所有输出设备
            speakers = soundcard.all_speakers()
            output_devices = [speaker.name for speaker in speakers]

            # 获取所有输入设备
            mics = soundcard.all_microphones()
            input_devices = [mic.name for mic in mics]

            logger.info(f"输出设备: {len(output_devices)} 个")
            logger.info(f"输入设备: {len(input_devices)} 个")

            return {
                'success': True,
                'message': _i18n.t('command_executed'),
                'action': 'list_audio_devices',
                'output_devices': output_devices,
                'input_devices': input_devices
            }
        except Exception as e:
            logger.error(f"列出音频设备失败: {e}")
            return {
                'success': False,
                'message': _i18n.t('command_failed'),
                'error': str(e)
            }

    @staticmethod
    def set_audio_output(device_name: str) -> dict:
        """
        设置音频输出设备

        Args:
            device_name: 设备名称

        Returns:
            dict: 执行结果
        """
        try:
            logger.info(f"设置音频输出设备: {device_name}")

            # TODO: 实际切换音频输出设备
            # 这需要调用 Windows API
            # 或者使用 soundcard 库重新初始化播放器

            # 目前只是记录日志
            # 实际使用时需要配合 MPV 播放器

            return {
                'success': True,
                'message': _i18n.t('command_executed'),
                'action': 'set_audio_output',
                'device': device_name
            }
        except Exception as e:
            logger.error(f"设置音频输出失败: {e}")
            return {
                'success': False,
                'message': _i18n.t('command_failed'),
                'error': str(e)
            }

    @staticmethod
    def set_audio_input(device_name: str) -> dict:
        """
        设置音频输入设备

        Args:
            device_name: 设备名称

        Returns:
            dict: 执行结果
        """
        try:
            logger.info(f"设置音频输入设备: {device_name}")

            # TODO: 实际切换音频输入设备
            # 需要重新初始化录音器

            return {
                'success': True,
                'message': _i18n.t('command_executed'),
                'action': 'set_audio_input',
                'device': device_name
            }
        except Exception as e:
            logger.error(f"设置音频输入失败: {e}")
            return {
                'success': False,
                'message': _i18n.t('command_failed'),
                'error': str(e)
            }


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.INFO)

    def test_audio_commands():
        """测试音频命令"""
        logger.info("测试音频设备控制命令")

        commands = AudioCommands()

        # 测试列出设备
        result = commands.list_devices()

        if result['success']:
            logger.info("\n输出设备:")
            for i, device in enumerate(result['output_devices'], 1):
                logger.info(f"  {i}. {device}")

            logger.info("\n输入设备:")
            for i, device in enumerate(result['input_devices'], 1):
                logger.info(f"  {i}. {device}")

    # 运行测试
    test_audio_commands()
