"""
System Commands Module
Implements cross-platform system control commands (shutdown, restart, lock screen, etc.)
"""

import logging
import subprocess

from src.i18n import get_i18n

# Import platform abstraction layer
try:
    from src.platforms import get_platform_instance
    PLATFORM_AVAILABLE = True
except ImportError:
    PLATFORM_AVAILABLE = False

logger = logging.getLogger(__name__)
_i18n = get_i18n()


class SystemCommands:
    """System Control Commands (cross-platform)"""

    def __init__(self):
        """Initialize system commands with platform abstraction"""
        self._platform = None
        if PLATFORM_AVAILABLE:
            try:
                self._platform = get_platform_instance()
                logger.info(f"SystemCommands initialized with {self._platform.get_platform_name()}")
            except Exception as e:
                logger.warning(f"Failed to initialize platform abstraction: {e}")

    def shutdown(self) -> dict:
        """
        Shutdown

        Returns:
            dict: Execution result
        """
        if self._platform:
            try:
                logger.warning("Executing shutdown command")
                success = self._platform.shutdown()
                if success:
                    return {
                        'success': True,
                        'message': _i18n.t('command_executed'),
                        'action': 'shutdown'
                    }
            except Exception as e:
                logger.error(f"Platform shutdown failed: {e}")
        
        # Fallback to Windows-specific implementation
        return self._shutdown_windows()

    def restart(self) -> dict:
        """
        Restart

        Returns:
            dict: Execution result
        """
        if self._platform:
            try:
                logger.warning("Executing restart command")
                success = self._platform.restart()
                if success:
                    return {
                        'success': True,
                        'message': _i18n.t('command_executed'),
                        'action': 'restart'
                    }
            except Exception as e:
                logger.error(f"Platform restart failed: {e}")
        
        # Fallback to Windows-specific implementation
        return self._restart_windows()

    def sleep(self) -> dict:
        """
        Sleep

        Returns:
            dict: Execution result
        """
        if self._platform:
            try:
                logger.info("Executing sleep command")
                success = self._platform.sleep()
                if success:
                    return {
                        'success': True,
                        'message': _i18n.t('command_executed'),
                        'action': 'sleep'
                    }
            except Exception as e:
                logger.error(f"Platform sleep failed: {e}")
        
        # Fallback to Windows-specific implementation
        return self._sleep_windows()

    def hibernate(self) -> dict:
        """
        Hibernate

        Returns:
            dict: Execution result
        """
        if self._platform:
            try:
                logger.info("Executing hibernate command")
                success = self._platform.hibernate()
                if success:
                    return {
                        'success': True,
                        'message': _i18n.t('command_executed'),
                        'action': 'hibernate'
                    }
            except Exception as e:
                logger.error(f"Platform hibernate failed: {e}")
        
        # Fallback to Windows-specific implementation
        return self._hibernate_windows()

    def lock(self) -> dict:
        """
        Lock screen

        Returns:
            dict: Execution result
        """
        if self._platform:
            try:
                logger.info("Executing lock screen command")
                success = self._platform.lock_screen()
                if success:
                    return {
                        'success': True,
                        'message': _i18n.t('command_executed'),
                        'action': 'lock'
                    }
            except Exception as e:
                logger.error(f"Platform lock screen failed: {e}")
        
        # Fallback to Windows-specific implementation
        return self._lock_windows()

    def logoff(self) -> dict:
        """
        Log off

        Returns:
            dict: Execution result
        """
        if self._platform:
            try:
                logger.warning("Executing log off command")
                success = self._platform.logoff()
                if success:
                    return {
                        'success': True,
                        'message': _i18n.t('command_executed'),
                        'action': 'logoff'
                    }
            except Exception as e:
                logger.error(f"Platform logoff failed: {e}")
        
        # Fallback to Windows-specific implementation
        return self._logoff_windows()

    # ========== Windows-specific fallback methods ==========

    @staticmethod
    def _shutdown_windows() -> dict:
        """Windows-specific shutdown"""
        try:
            logger.warning("Executing Windows shutdown command")
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
    def _restart_windows() -> dict:
        """Windows-specific restart"""
        try:
            logger.warning("Executing Windows restart command")
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
    def _sleep_windows() -> dict:
        """Windows-specific sleep"""
        try:
            logger.info("Executing Windows sleep command")
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
    def _hibernate_windows() -> dict:
        """Windows-specific hibernate"""
        try:
            logger.info("Executing Windows hibernate command")
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
    def _lock_windows() -> dict:
        """Windows-specific lock screen"""
        try:
            logger.info("Executing Windows lock screen command")
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
    def _logoff_windows() -> dict:
        """Windows-specific logoff"""
        try:
            logger.warning("Executing Windows log off command")
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
        _ = SystemCommands()

        logger.info("Available system commands:")
        logger.info("  - shutdown: Shutdown")
        logger.info("  - restart: Restart")
        logger.info("  - sleep: Sleep")
        logger.info("  - hibernate: Hibernate")
        logger.info("  - lock: Lock screen")
        logger.info("  - logoff: Log off")

    # Run test
    test_system_commands()
