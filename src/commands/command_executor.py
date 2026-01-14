"""
命令执行器主模块
负责解析和执行来自 Home Assistant 的命令
"""

import logging
import subprocess
import webbrowser
from typing import Dict, Callable, Optional

from .system_commands import SystemCommands
from .media_commands import MediaCommands
from .audio_commands import AudioCommands

from ..i18n import get_i18n

logger = logging.getLogger(__name__)
_i18n = get_i18n()


class CommandExecutor:
    """Windows 命令执行器"""

    # 命令白名单（安全机制）
    ALLOWED_COMMANDS = {
        # 系统控制命令
        'shutdown', 'restart', 'sleep', 'hibernate', 'lock', 'logoff',

        # 媒体控制命令
        'play_pause', 'next', 'previous', 'mute', 'volume', 'volume_up', 'volume_down',

        # 音频设备命令
        'audio_input', 'audio_output', 'list_audio_devices',

        # 应用程序命令
        'launch', 'url', 'screenshot',

        # 通知命令
        'notify',
    }

    # 危险命令（需要用户确认）
    DANGEROUS_COMMANDS = {'shutdown', 'restart', 'logoff'}

    def __init__(self):
        """初始化命令执行器"""
        self._command_handlers: Dict[str, Callable] = {}

        # 初始化子命令模块
        self.system_commands = SystemCommands()
        self.media_commands = MediaCommands()
        self.audio_commands = AudioCommands()

        # 注册命令处理器
        self._register_handlers()

        logger.info("命令执行器已初始化")

    def _register_handlers(self) -> None:
        """注册命令处理器"""
        # 系统控制命令
        self._command_handlers.update({
            'shutdown': self.system_commands.shutdown,
            'restart': self.system_commands.restart,
            'sleep': self.system_commands.sleep,
            'hibernate': self.system_commands.hibernate,
            'lock': self.system_commands.lock,
            'logoff': self.system_commands.logoff,
        })

        # 媒体控制命令
        self._command_handlers.update({
            'play_pause': self.media_commands.play_pause,
            'next': self.media_commands.next,
            'previous': self.media_commands.previous,
            'mute': self.media_commands.mute,
            'volume': self.media_commands.set_volume,
            'volume_up': self.media_commands.volume_up,
            'volume_down': self.media_commands.volume_down,
        })

        # 音频设备命令
        self._command_handlers.update({
            'audio_input': self.audio_commands.set_audio_input,
            'audio_output': self.audio_commands.set_audio_output,
            'list_audio_devices': self.audio_commands.list_devices,
        })

        # 应用程序命令
        self._command_handlers.update({
            'launch': self._launch_app,
            'url': self._open_url,
            'screenshot': self._screenshot,
        })

        # 通知命令
        self._command_handlers.update({
            'notify': self._show_notification,
        })

    def execute(self, command_string: str) -> Dict:
        """
        执行命令

        Args:
            command_string: 命令字符串（格式: "command:arg1:arg2"）

        Returns:
            Dict: 执行结果
            {
                'success': bool,
                'message': str,
                'data': any
            }
        """
        try:
            # 解析命令
            parts = command_string.split(':', 1)
            cmd = parts[0]
            args = parts[1] if len(parts) > 1 else None

            logger.info(f"执行命令: {cmd} (参数: {args})")

            # 安全检查
            if cmd not in self.ALLOWED_COMMANDS:
                return {
                    'success': False,
                    'message': _i18n.t('command_not_allowed'),
                    'error': f"命令 '{cmd}' 不在白名单中"
                }

            # 危险命令确认
            if cmd in self.DANGEROUS_COMMANDS:
                # TODO: 实现 UI 确认对话框
                logger.warning(f"危险命令需要确认: {cmd}")
                # 这里暂时直接执行，实际使用时应该弹出确认对话框

            # 查找并执行命令处理器
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
                    'message': f"未找到命令处理器: {cmd}"
                }

        except Exception as e:
            logger.error(f"命令执行失败: {e}", exc_info=True)
            return {
                'success': False,
                'message': _i18n.t('command_failed'),
                'error': str(e)
            }

    def _launch_app(self, app_name: str) -> Dict:
        """启动应用程序"""
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
        """打开网址"""
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
        """截图"""
        try:
            from PIL import ImageGrab

            # 截图
            screenshot = ImageGrab.grab()

            # 保存文件
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
        """显示通知"""
        try:
            # 解析参数: "title:message:duration"
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
        """列出所有可用命令"""
        return list(self.ALLOWED_COMMANDS)


# 便捷函数
def execute_command(command_string: str) -> Dict:
    """
    执行命令（便捷函数）

    Args:
        command_string: 命令字符串

    Returns:
        Dict: 执行结果
    """
    executor = CommandExecutor()
    return executor.execute(command_string)


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.INFO)

    def test_executor():
        """测试命令执行器"""
        logger.info("测试命令执行器")

        executor = CommandExecutor()

        # 测试列表命令
        commands = executor.list_available_commands()
        logger.info(f"可用命令 ({len(commands)}):")
        for cmd in sorted(commands):
            logger.info(f"  - {cmd}")

        # 测试安全命令
        logger.info("\n测试安全命令:")
        result = executor.execute("url:https://www.home-assistant.io")
        logger.info(f"结果: {result}")

    # 运行测试
    test_executor()
