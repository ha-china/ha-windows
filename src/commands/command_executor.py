"""
Command Executor Main Module
Responsible for parsing and executing commands from Home Assistant
"""

import logging
import subprocess
import webbrowser
from typing import Dict, Callable, Optional

from .system_commands import SystemCommands
from .media_commands import MediaCommands
from .audio_commands import AudioCommands

from src.i18n import get_i18n

logger = logging.getLogger(__name__)
_i18n = get_i18n()


class CommandExecutor:
    """Windows Command Executor"""

    # Command whitelist (security mechanism)
    ALLOWED_COMMANDS = {
        # System control commands
        'shutdown', 'restart', 'sleep', 'hibernate', 'lock', 'logoff',

        # Media control commands
        'play_pause', 'next', 'previous', 'mute', 'volume', 'volume_up', 'volume_down',

        # Audio device commands
        'audio_input', 'audio_output', 'list_audio_devices',

        # Application commands
        'launch', 'url', 'screenshot',

        # Notification commands
        'notify',
    }

    # Dangerous commands (require user confirmation)
    DANGEROUS_COMMANDS = {'shutdown', 'restart', 'logoff'}

    def __init__(self):
        """Initialize command executor"""
        self._command_handlers: Dict[str, Callable] = {}

        # Initialize sub-command modules
        self.system_commands = SystemCommands()
        self.media_commands = MediaCommands()
        self.audio_commands = AudioCommands()

        # Register command handlers
        self._register_handlers()

        logger.info("Command executor initialized")

    def _register_handlers(self) -> None:
        """Register command handlers"""
        # System control commands
        self._command_handlers.update({
            'shutdown': self.system_commands.shutdown,
            'restart': self.system_commands.restart,
            'sleep': self.system_commands.sleep,
            'hibernate': self.system_commands.hibernate,
            'lock': self.system_commands.lock,
            'logoff': self.system_commands.logoff,
        })

        # Media control commands
        self._command_handlers.update({
            'play_pause': self.media_commands.play_pause,
            'next': self.media_commands.next,
            'previous': self.media_commands.previous,
            'mute': self.media_commands.mute,
            'volume': self.media_commands.set_volume,
            'volume_up': self.media_commands.volume_up,
            'volume_down': self.media_commands.volume_down,
        })

        # Audio device commands
        self._command_handlers.update({
            'audio_input': self.audio_commands.set_audio_input,
            'audio_output': self.audio_commands.set_audio_output,
            'list_audio_devices': self.audio_commands.list_devices,
        })

        # Application commands
        self._command_handlers.update({
            'launch': self._launch_app,
            'url': self._open_url,
            'screenshot': self._screenshot,
        })

        # Notification commands
        self._command_handlers.update({
            'notify': self._show_notification,
        })

    def execute(self, command_string: str) -> Dict:
        """
        Execute command

        Args:
            command_string: Command string (format: "command:arg1:arg2")

        Returns:
            Dict: Execution result
            {
                'success': bool,
                'message': str,
                'data': any
            }
        """
        try:
            # Parse command
            parts = command_string.split(':', 1)
            cmd = parts[0]
            args = parts[1] if len(parts) > 1 else None

            logger.info(f"Executing command: {cmd} (args: {args})")

            # Security check
            if cmd not in self.ALLOWED_COMMANDS:
                return {
                    'success': False,
                    'message': _i18n.t('command_not_allowed'),
                    'error': f"Command '{cmd}' is not in whitelist"
                }

            # Dangerous command confirmation
            if cmd in self.DANGEROUS_COMMANDS:
                # TODO: Implement UI confirmation dialog
                logger.warning(f"Dangerous command requires confirmation: {cmd}")
                # Currently executing directly, should show confirmation dialog in actual use

            # Find and execute command handler
            if cmd in self._command_handlers:
                handler = self._command_handlers[cmd]

                if args is not None:
                    result = handler(args)
                else:
                    result = handler()

                return result
            else:
                return {
                    'success': False,
                    'message': f"Command handler not found: {cmd}"
                }

        except Exception as e:
            logger.error(f"Command execution failed: {e}", exc_info=True)
            return {
                'success': False,
                'message': _i18n.t('command_failed'),
                'error': str(e)
            }

    def _launch_app(self, app_name: str) -> Dict:
        """Launch application"""
        try:
            subprocess.Popen([app_name], shell=True)
            return {
                'success': True,
                'message': _i18n.t('command_executed'),
                'app': app_name
            }
        except Exception as e:
            return {
                'success': False,
                'message': _i18n.t('command_failed'),
                'error': str(e)
            }

    def _open_url(self, url: str) -> Dict:
        """Open URL"""
        try:
            webbrowser.open(url)
            return {
                'success': True,
                'message': _i18n.t('command_executed'),
                'url': url
            }
        except Exception as e:
            return {
                'success': False,
                'message': _i18n.t('command_failed'),
                'error': str(e)
            }

    def _screenshot(self, args: Optional[str] = None) -> Dict:
        """Take screenshot"""
        try:
            from PIL import ImageGrab

            # Take screenshot
            screenshot = ImageGrab.grab()

            # Save file
            if args:
                filename = args
            else:
                import datetime
                filename = f"screenshot_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"

            screenshot.save(filename)

            return {
                'success': True,
                'message': _i18n.t('command_executed'),
                'file': filename
            }
        except Exception as e:
            return {
                'success': False,
                'message': _i18n.t('command_failed'),
                'error': str(e)
            }

    def _show_notification(self, args: str) -> Dict:
        """Show notification"""
        try:
            # Parse arguments: "title:message:duration"
            parts = args.split(':', 2)

            title = parts[0] if len(parts) > 0 else "Home Assistant"
            message = parts[1] if len(parts) > 1 else ""
            duration = int(parts[2]) if len(parts) > 2 else 5

            from win10toast import ToastNotifier
            toaster = ToastNotifier()
            toaster.show_toast(
                title=title,
                msg=message,
                duration=duration,
                threaded=True
            )

            return {
                'success': True,
                'message': _i18n.t('command_executed')
            }
        except Exception as e:
            return {
                'success': False,
                'message': _i18n.t('command_failed'),
                'error': str(e)
            }

    def list_available_commands(self) -> list[str]:
        """List all available commands"""
        return list(self.ALLOWED_COMMANDS)


# Convenience function
def execute_command(command_string: str) -> Dict:
    """
    Execute command (convenience function)

    Args:
        command_string: Command string

    Returns:
        Dict: Execution result
    """
    executor = CommandExecutor()
    return executor.execute(command_string)


if __name__ == "__main__":
    # Test code
    logging.basicConfig(level=logging.INFO)

    def test_executor():
        """Test command executor"""
        logger.info("Testing command executor")

        executor = CommandExecutor()

        # Test list commands
        commands = executor.list_available_commands()
        logger.info(f"Available commands ({len(commands)}):")
        for cmd in sorted(commands):
            logger.info(f"  - {cmd}")

        # Test safe command
        logger.info("\nTesting safe command:")
        result = executor.execute("url:https://www.home-assistant.io")
        logger.info(f"Result: {result}")

    # Run test
    test_executor()
