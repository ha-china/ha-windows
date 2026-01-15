"""
System Commands Module
Implements Windows system control commands (shutdown, restart, lock screen, etc.)
"""

import logging
import subprocess
import platform

from src.i18n import get_i18n

logger = logging.getLogger(__name__)
_i18n = get_i18n()


class SystemCommands:
    """System Control Commands"""

    @staticmethod
    def shutdown() -> dict:
        """
        Shutdown

        Returns:
            dict: Execution result
        """
        try:
            logger.warning("Executing shutdown command")
            subprocess.run(['shutdown', '/s', '/t', '0'], check=True)
            return {
                'success': True,
                'message': _i18n.t('command_executed'),
                'action': 'shutdown'
            }
        except Exception as e:
            logger.error(f"Shutdown failed: {e}")
            return {
                'success': False,
                'message': _i18n.t('command_failed'),
                'error': str(e)
            }

    @staticmethod
    def restart() -> dict:
        """
        Restart

        Returns:
            dict: Execution result
        """
        try:
            logger.warning("Executing restart command")
            subprocess.run(['shutdown', '/r', '/t', '0'], check=True)
            return {
                'success': True,
                'message': _i18n.t('command_executed'),
                'action': 'restart'
            }
        except Exception as e:
            logger.error(f"Restart failed: {e}")
            return {
                'success': False,
                'message': _i18n.t('command_failed'),
                'error': str(e)
            }

    @staticmethod
    def sleep() -> dict:
        """
        Sleep

        Returns:
            dict: Execution result
        """
        try:
            logger.info("Executing sleep command")
            # Windows sleep command
            subprocess.run(['rundll32.exe', 'powrprof.dll,SetSuspendState', '0,1,0'], check=True)
            return {
                'success': True,
                'message': _i18n.t('command_executed'),
                'action': 'sleep'
            }
        except Exception as e:
            logger.error(f"Sleep failed: {e}")
            return {
                'success': False,
                'message': _i18n.t('command_failed'),
                'error': str(e)
            }

    @staticmethod
    def hibernate() -> dict:
        """
        Hibernate

        Returns:
            dict: Execution result
        """
        try:
            logger.info("Executing hibernate command")
            subprocess.run(['shutdown', '/h'], check=True)
            return {
                'success': True,
                'message': _i18n.t('command_executed'),
                'action': 'hibernate'
            }
        except Exception as e:
            logger.error(f"Hibernate failed: {e}")
            return {
                'success': False,
                'message': _i18n.t('command_failed'),
                'error': str(e)
            }

    @staticmethod
    def lock() -> dict:
        """
        Lock screen (Win+L)

        Returns:
            dict: Execution result
        """
        try:
            logger.info("Executing lock screen command")
            subprocess.run(['rundll32.exe', 'user32.dll,LockWorkStation'], check=True)
            return {
                'success': True,
                'message': _i18n.t('command_executed'),
                'action': 'lock'
            }
        except Exception as e:
            logger.error(f"Lock screen failed: {e}")
            return {
                'success': False,
                'message': _i18n.t('command_failed'),
                'error': str(e)
            }

    @staticmethod
    def logoff() -> dict:
        """
        Log off

        Returns:
            dict: Execution result
        """
        try:
            logger.warning("Executing log off command")
            subprocess.run(['shutdown', '/l'], check=True)
            return {
                'success': True,
                'message': _i18n.t('command_executed'),
                'action': 'logoff'
            }
        except Exception as e:
            logger.error(f"Log off failed: {e}")
            return {
                'success': False,
                'message': _i18n.t('command_failed'),
                'error': str(e)
            }


if __name__ == "__main__":
    # Test code
    logging.basicConfig(level=logging.INFO)

    def test_system_commands():
        """Test system commands"""
        logger.info("Testing system commands (demo only, dangerous commands will not be executed)")

        # Only test lock screen (relatively safe)
        commands = SystemCommands()

        logger.info("Available system commands:")
        logger.info("  - shutdown: Shutdown")
        logger.info("  - restart: Restart")
        logger.info("  - sleep: Sleep")
        logger.info("  - hibernate: Hibernate")
        logger.info("  - lock: Lock screen")
        logger.info("  - logoff: Log off")

    # Run test
    test_system_commands()
