"""
国际化（i18n）支持模块
支持中英双语切换
"""

import locale
import os
from typing import Dict


class I18n:
    """国际化支持类"""

    def __init__(self):
        """初始化并自动检测系统语言"""
        self.language = self._detect_system_language()
        self.translations: Dict[str, Dict[str, str]] = {
            'zh_CN': {
                # 应用信息
                'app_name': 'Home Assistant Windows',
                'app_version': '版本',

                # 状态
                'status_connected': '已连接',
                'status_disconnected': '未连接',
                'status_connecting': '连接中...',
                'status_recording': '录音中',

                # 主窗口 UI
                'mic_button': '麦克风',
                'settings': '设置',
                'quit': '退出',
                'volume': '音量',
                'wake_word': '唤醒词',
                'recent_conversations': '最近对话',

                # 连接
                'registering_mdns': '正在注册 mDNS 服务...',
                'discovering_ha': '正在发现 Home Assistant...',
                'ha_found': '发现 Home Assistant: {}',
                'ha_not_found': '未发现 Home Assistant',
                'connecting_to_ha': '正在连接 Home Assistant...',
                'connection_failed': '连接失败',
                'connection_successful': '连接成功',

                # Voice Assistant
                'listening': '正在聆听...',
                'processing': '处理中...',
                'speaking': '正在说话...',
                'error_no_audio_device': '未找到音频设备',
                'error_recording': '录音失败',

                # 通知
                'notification_title': 'Home Assistant 通知',

                # 传感器
                'sensor_cpu': 'CPU 使用率',
                'sensor_memory': '内存使用率',
                'sensor_disk': '磁盘使用率',
                'sensor_battery': '电池状态',

                # 命令
                'command_executed': '命令已执行',
                'command_failed': '命令执行失败',
                'command_not_allowed': '不允许的命令',
                'dangerous_command_confirm': '确认执行危险命令？',

                # 设置
                'settings_language': '语言',
                'settings_audio_device': '音频设备',
                'settings_wake_word_model': '唤醒词模型',
                'settings_log_level': '日志级别',

                # 按钮
                'button_ok': '确定',
                'button_cancel': '取消',
                'button_yes': '是',
                'button_no': '否',
                'button_apply': '应用',
                'button_close': '关闭',

                # 错误
                'error': '错误',
                'warning': '警告',
                'info': '信息',
            },
            'en_US': {
                # App Info
                'app_name': 'Home Assistant Windows',
                'app_version': 'Version',

                # Status
                'status_connected': 'Connected',
                'status_disconnected': 'Disconnected',
                'status_connecting': 'Connecting...',
                'status_recording': 'Recording',

                # Main Window UI
                'mic_button': 'Microphone',
                'settings': 'Settings',
                'quit': 'Quit',
                'volume': 'Volume',
                'wake_word': 'Wake Word',
                'recent_conversations': 'Recent Conversations',

                # Connection
                'registering_mdns': 'Registering mDNS service...',
                'discovering_ha': 'Discovering Home Assistant...',
                'ha_found': 'Home Assistant found: {}',
                'ha_not_found': 'Home Assistant not found',
                'connecting_to_ha': 'Connecting to Home Assistant...',
                'connection_failed': 'Connection failed',
                'connection_successful': 'Connection successful',

                # Voice Assistant
                'listening': 'Listening...',
                'processing': 'Processing...',
                'speaking': 'Speaking...',
                'error_no_audio_device': 'No audio device found',
                'error_recording': 'Recording failed',

                # Notifications
                'notification_title': 'Home Assistant Notification',

                # Sensors
                'sensor_cpu': 'CPU Usage',
                'sensor_memory': 'Memory Usage',
                'sensor_disk': 'Disk Usage',
                'sensor_battery': 'Battery Status',

                # Commands
                'command_executed': 'Command executed',
                'command_failed': 'Command failed',
                'command_not_allowed': 'Command not allowed',
                'dangerous_command_confirm': 'Confirm dangerous command?',

                # Settings
                'settings_language': 'Language',
                'settings_audio_device': 'Audio Device',
                'settings_wake_word_model': 'Wake Word Model',
                'settings_log_level': 'Log Level',

                # Buttons
                'button_ok': 'OK',
                'button_cancel': 'Cancel',
                'button_yes': 'Yes',
                'button_no': 'No',
                'button_apply': 'Apply',
                'button_close': 'Close',

                # Errors
                'error': 'Error',
                'warning': 'Warning',
                'info': 'Info',
            }
        }

    def _detect_system_language(self) -> str:
        """
        自动检测系统语言

        Returns:
            str: 语言代码 ('zh_CN' 或 'en_US')
        """
        try:
            # 获取系统语言
            system_lang = locale.getdefaultlocale()[0]

            # 中文环境
            if system_lang and system_lang.startswith('zh'):
                return 'zh_CN'

            # 默认英文
            return 'en_US'
        except Exception:
            return 'zh_CN'  # 出错默认中文

    def t(self, key: str, *args, **kwargs) -> str:
        """
        获取翻译文本

        Args:
            key: 翻译键
            *args: 格式化参数
            **kwargs: 格式化参数

        Returns:
            str: 翻译后的文本
        """
        text = self.translations.get(self.language, {}).get(key, key)

        # 支持格式化
        if args or kwargs:
            try:
                return text.format(*args, **kwargs)
            except (KeyError, ValueError, IndexError):
                return text

        return text

    def set_language(self, language: str) -> bool:
        """
        设置语言

        Args:
            language: 语言代码 ('zh_CN' 或 'en_US')

        Returns:
            bool: 是否设置成功
        """
        if language in self.translations:
            self.language = language
            return True
        return False

    def get_current_language(self) -> str:
        """获取当前语言"""
        return self.language

    def get_available_languages(self) -> list:
        """获取可用语言列表"""
        return list(self.translations.keys())


# 全局单例
_i18n_instance = None


def get_i18n() -> I18n:
    """获取 i18n 单例实例"""
    global _i18n_instance
    if _i18n_instance is None:
        _i18n_instance = I18n()
    return _i18n_instance


# 便捷函数
def t(key: str, *args, **kwargs) -> str:
    """翻译函数的便捷调用"""
    return get_i18n().t(key, *args, **kwargs)


def set_language(language: str) -> bool:
    """设置语言的便捷调用"""
    return get_i18n().set_language(language)


def get_language() -> str:
    """获取当前语言的便捷调用"""
    return get_i18n().get_current_language()
