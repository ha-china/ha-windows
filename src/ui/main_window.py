"""
主窗口 UI 模块
使用 CustomTkinter 构建现代化界面
"""

import asyncio
import logging
import threading
import tkinter as tk
from tkinter import ttk
from typing import Optional

import customtkinter as ctk

from ..i18n import get_i18n
from ..core.esphome_connection import ConnectionState

logger = logging.getLogger(__name__)
_i18n = get_i18n()


class MainWindow(ctk.CTk):
    """主窗口"""

    def __init__(self):
        """初始化主窗口"""
        super().__init__()

        # 配置窗口
        self.title(_i18n.t('app_name'))
        self.geometry("800x600")

        # 设置主题
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # 状态
        self.connection_state = ConnectionState.DISCONNECTED

        # 创建 UI
        self._create_widgets()

        # 启动异步事件循环
        self._async_loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(
            target=self._run_async_loop,
            daemon=True
        )
        self._loop_thread.start()

        logger.info("主窗口已创建")

    def _run_async_loop(self):
        """运行异步事件循环（在独立线程中）"""
        asyncio.set_event_loop(self._async_loop)
        self._async_loop.run_forever()

    def _create_widgets(self):
        """创建 UI 组件"""
        # 顶部标题栏
        title_frame = ctk.CTkFrame(self, height=60)
        title_frame.pack(side="top", fill="x", padx=10, pady=10)

        title_label = ctk.CTkLabel(
            title_frame,
            text=_i18n.t('app_name'),
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title_label.pack(side="left", padx=20)

        # 状态指示器
        self.status_label = ctk.CTkLabel(
            title_frame,
            text=f"状态: {_i18n.t('status_disconnected')}",
            font=ctk.CTkFont(size=12)
        )
        self.status_label.pack(side="right", padx=20)

        # 主内容区域
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(side="top", fill="both", expand=True, padx=10, pady=10)

        # 麦克风按钮（大按钮）
        mic_frame = ctk.CTkFrame(main_frame)
        mic_frame.pack(side="top", fill="x", pady=20)

        self.mic_button = ctk.CTkButton(
            mic_frame,
            text="🎤",
            font=ctk.CTkFont(size=48),
            width=150,
            height=150,
            fg_color=("gray75", "gray30"),
            hover_color=("gray65", "gray25"),
            command=self._on_mic_button_click
        )
        self.mic_button.pack()

        # 控制面板
        control_frame = ctk.CTkFrame(main_frame)
        control_frame.pack(side="top", fill="x", pady=20)

        # 音量滑块
        volume_label = ctk.CTkLabel(
            control_frame,
            text=_i18n.t('volume'),
            font=ctk.CTkFont(size=14)
        )
        volume_label.pack(side="left", padx=20)

        self.volume_slider = ctk.CTkSlider(
            control_frame,
            from_=0,
            to=100,
            number_of_steps=100,
            width=300
        )
        self.volume_slider.set(50)
        self.volume_slider.pack(side="left", padx=10)

        self.volume_label = ctk.CTkLabel(
            control_frame,
            text="50%",
            font=ctk.CTkFont(size=12)
        )
        self.volume_label.pack(side="left", padx=10)

        # 设置按钮
        settings_button = ctk.CTkButton(
            control_frame,
            text="⚙️",
            width=50,
            command=self._on_settings_click
        )
        settings_button.pack(side="right", padx=10)

        # 底部信息栏
        info_frame = ctk.CTkFrame(main_frame)
        info_frame.pack(side="bottom", fill="x", pady=10)

        self.info_label = ctk.CTkLabel(
            info_frame,
            text="准备就绪",
            font=ctk.CTkFont(size=12)
        )
        self.info_label.pack(side="left", padx=20)

    def _on_mic_button_click(self):
        """麦克风按钮点击事件"""
        logger.info("麦克风按钮被点击")
        self.info_label.configure(text="正在启动语音助手...")

        # TODO: 触发 Voice Assistant

    def _on_settings_click(self):
        """设置按钮点击事件"""
        logger.info("设置按钮被点击")

        # TODO: 打开设置窗口

    def update_connection_state(self, state: ConnectionState):
        """
        更新连接状态

        Args:
            state: 连接状态
        """
        self.connection_state = state

        if state == ConnectionState.CONNECTED:
            status_text = _i18n.t('status_connected')
            color = "green"
        elif state == ConnectionState.DISCONNECTED:
            status_text = _i18n.t('status_disconnected')
            color = "red"
        elif state == ConnectionState.CONNECTING:
            status_text = _i18n.t('status_connecting')
            color = "yellow"
        else:
            status_text = "错误"
            color = "red"

        self.status_label.configure(text=f"状态: {status_text}")

    def update_info(self, message: str):
        """
        更新信息栏

        Args:
            message: 信息文本
        """
        self.info_label.configure(text=message)


class AsyncMainWindow:
    """异步主窗口封装"""

    def __init__(self):
        """初始化异步主窗口"""
        self.window: Optional[MainWindow] = None
        self._running = False

    def start(self):
        """启动窗口"""
        self.window = MainWindow()
        self._running = True
        self.window.mainloop()

    def stop(self):
        """停止窗口"""
        if self.window:
            self.window.destroy()
        self._running = False

    def update_connection_state(self, state: ConnectionState):
        """更新连接状态"""
        if self.window:
            self.window.update_connection_state(state)

    def update_info(self, message: str):
        """更新信息"""
        if self.window:
            self.window.update_info(message)


# 便捷函数
def create_main_window() -> AsyncMainWindow:
    """
    创建主窗口（便捷函数）

    Returns:
        AsyncMainWindow: 主窗口实例
    """
    return AsyncMainWindow()


if __name__ == "__main__":
    # 测试 UI
    logging.basicConfig(level=logging.INFO)

    def test_ui():
        """测试 UI"""
        logger.info("测试主窗口 UI")

        window = create_main_window()
        window.start()

    # 运行测试
    test_ui()
