"""
系统命令模块
实现 Windows 系统控制命令（关机、重启、锁屏等）
"""

import logging
import subprocess
import platform

from src.i18n import get_i18n

logger = logging.getLogger(__name__)
_i18n = get_i18n()


class SystemCommands:
    """系统控制命令"""

    @staticmethod
    def shutdown() -> dict:
        """
        关机

        Returns:
            dict: 执行结果
        """
        try:
            logger.warning("执行关机命令")
            subprocess.run(['shutdown', '/s', '/t', '0'], check=True)
            return {
                'success': True,
                'message': _i18n.t('command_executed'),
                'action': 'shutdown'
            }
        except Exception as e:
            logger.error(f"关机失败: {e}")
            return {
                'success': False,
                'message': _i18n.t('command_failed'),
                'error': str(e)
            }

    @staticmethod
    def restart() -> dict:
        """
        重启

        Returns:
            dict: 执行结果
        """
        try:
            logger.warning("执行重启命令")
            subprocess.run(['shutdown', '/r', '/t', '0'], check=True)
            return {
                'success': True,
                'message': _i18n.t('command_executed'),
                'action': 'restart'
            }
        except Exception as e:
            logger.error(f"重启失败: {e}")
            return {
                'success': False,
                'message': _i18n.t('command_failed'),
                'error': str(e)
            }

    @staticmethod
    def sleep() -> dict:
        """
        睡眠

        Returns:
            dict: 执行结果
        """
        try:
            logger.info("执行睡眠命令")
            # Windows 睡眠命令
            subprocess.run(['rundll32.exe', 'powrprof.dll,SetSuspendState', '0,1,0'], check=True)
            return {
                'success': True,
                'message': _i18n.t('command_executed'),
                'action': 'sleep'
            }
        except Exception as e:
            logger.error(f"睡眠失败: {e}")
            return {
                'success': False,
                'message': _i18n.t('command_failed'),
                'error': str(e)
            }

    @staticmethod
    def hibernate() -> dict:
        """
        休眠

        Returns:
            dict: 执行结果
        """
        try:
            logger.info("执行休眠命令")
            subprocess.run(['shutdown', '/h'], check=True)
            return {
                'success': True,
                'message': _i18n.t('command_executed'),
                'action': 'hibernate'
            }
        except Exception as e:
            logger.error(f"休眠失败: {e}")
            return {
                'success': False,
                'message': _i18n.t('command_failed'),
                'error': str(e)
            }

    @staticmethod
    def lock() -> dict:
        """
        锁定屏幕（Win+L）

        Returns:
            dict: 执行结果
        """
        try:
            logger.info("执行锁定屏幕命令")
            subprocess.run(['rundll32.exe', 'user32.dll,LockWorkStation'], check=True)
            return {
                'success': True,
                'message': _i18n.t('command_executed'),
                'action': 'lock'
            }
        except Exception as e:
            logger.error(f"锁定屏幕失败: {e}")
            return {
                'success': False,
                'message': _i18n.t('command_failed'),
                'error': str(e)
            }

    @staticmethod
    def logoff() -> dict:
        """
        注销

        Returns:
            dict: 执行结果
        """
        try:
            logger.warning("执行注销命令")
            subprocess.run(['shutdown', '/l'], check=True)
            return {
                'success': True,
                'message': _i18n.t('command_executed'),
                'action': 'logoff'
            }
        except Exception as e:
            logger.error(f"注销失败: {e}")
            return {
                'success': False,
                'message': _i18n.t('command_failed'),
                'error': str(e)
            }


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.INFO)

    def test_system_commands():
        """测试系统命令"""
        logger.info("测试系统命令（仅演示，不会实际执行危险命令）")

        # 只测试锁屏（相对安全）
        commands = SystemCommands()

        logger.info("可用的系统命令:")
        logger.info("  - shutdown: 关机")
        logger.info("  - restart: 重启")
        logger.info("  - sleep: 睡眠")
        logger.info("  - hibernate: 休眠")
        logger.info("  - lock: 锁定屏幕")
        logger.info("  - logoff: 注销")

    # 运行测试
    test_system_commands()
