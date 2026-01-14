"""
系统托盘图标模块
提供 Windows 系统托盘图标，让用户知道程序在运行并可以退出
"""

import asyncio
import logging
import threading
from typing import Optional, Callable

import pystray
from PIL import Image, ImageDraw

from src.i18n import get_i18n

logger = logging.getLogger(__name__)
_i18n = get_i18n()


class SystemTrayIcon:
    """
    系统托盘图标管理器

    功能：
    - 显示托盘图标
    - 右键菜单（退出、查看状态）
    - 双击事件（可选）
    """

    def __init__(self):
        """初始化系统托盘图标"""
        self.icon: Optional[pystray.Icon] = None
        self._running = False
        self._loop_thread: Optional[threading.Thread] = None
        self._icon_ready = threading.Event()

        # 状态信息
        self._status_info = {
            'name': 'Unknown',
            'ip': 'Unknown',
            'port': 'Unknown',
        }

    def create_icon_image(self, width: int = 64, height: int = 64) -> Image.Image:
        """
        创建托盘图标图像

        Args:
            width: 图标宽度
            height: 图标高度

        Returns:
            Image: 图标图像
        """
        # 创建一个简单的 HA 风格图标
        image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        # 绘制圆形背景 (HA 蓝色)
        padding = 4
        draw.ellipse(
            [padding, padding, width - padding, height - padding],
            fill=(61, 174, 233, 255)  # Home Assistant 蓝
        )

        # 绘制简单的房子图形
        house_margin = 16
        roof_points = [
            (house_margin, height // 2),
            (width // 2, house_margin),
            (width - house_margin, height // 2),
        ]
        draw.polygon(roof_points, fill=(255, 255, 255, 255))

        # 房子主体
        house_body = [
            (house_margin + 4, height // 2),
            (width - house_margin - 4, height - house_margin),
        ]
        draw.rectangle(house_body, fill=(255, 255, 255, 255))

        return image

    def _create_menu(self) -> pystray.Menu:
        """
        创建右键菜单

        Returns:
            pystray.Menu: 菜单对象
        """
        def show_status(icon):
            """显示状态（使用通知方式）"""
            status_text = (
                f"🖥️  Home Assistant Windows\n\n"
                f"设备名称: {self._status_info['name']}\n"
                f"本机 IP: {self._status_info['ip']}\n"
                f"监听端口: {self._status_info['port']}\n\n"
                f"状态: 运行中 ✅"
            )

            # 使用 pystray 内置通知
            icon.notify(status_text, title="设备状态")

            # 同时记录到日志
            logger.info(f"状态查询: {self._status_info}")

        menu = pystray.Menu(
            pystray.MenuItem("查看状态", show_status, default=True),
            pystray.MenuItem("退出", self._quit),
        )

        return menu

    def _run_icon(self, icon: pystray.Icon):
        """
        在后台线程运行图标

        Args:
            icon: pystray Icon 实例
        """
        self._icon_ready.set()
        icon.run()

    def start(self, name: str, ip: str, port: int) -> None:
        """
        启动系统托盘图标

        Args:
            name: 设备名称
            ip: 本机 IP 地址
            port: 监听端口
        """
        if self._running:
            return

        self._status_info = {
            'name': name,
            'ip': ip,
            'port': str(port),
        }

        # 创建图标
        self.icon = pystray.Icon(
            name='HomeAssistant Windows',
            icon=self.create_icon_image(),
            menu=self._create_menu(),
        )

        # 设置提示文本
        self.icon.title = f"HA Windows: {name}\nIP: {ip}:{port}"

        # 在后台线程运行
        self._running = True
        self._icon_ready.clear()
        self._loop_thread = threading.Thread(
            target=self._run_icon,
            args=(self.icon,),
            daemon=True,
        )
        self._loop_thread.start()

        # 等待图标准备好
        self._icon_ready.wait(timeout=5)

        logger.info("✅ 系统托盘图标已启动")

    def update_status(self, name: str = None, ip: str = None, port: int = None) -> None:
        """
        更新状态信息

        Args:
            name: 设备名称
            ip: 本机 IP 地址
            port: 监听端口
        """
        if name is not None:
            self._status_info['name'] = name
        if ip is not None:
            self._status_info['ip'] = ip
        if port is not None:
            self._status_info['port'] = str(port)

        # 更新提示文本
        if self.icon:
            self.icon.title = (
                f"HA Windows: {self._status_info['name']}\n"
                f"IP: {self._status_info['ip']}:{self._status_info['port']}"
            )

    def stop(self) -> None:
        """停止系统托盘图标"""
        if self.icon and self._running:
            self._running = False
            self.icon.stop()
            logger.info("系统托盘图标已停止")

    def _quit(self) -> None:
        """退出程序（通过托盘菜单）"""
        logger.info("用户通过托盘菜单退出程序")
        self.stop()
        # 触发主程序退出
        import os
        import signal
        os.kill(os.getpid(), signal.SIGINT)


# 全局单例
_tray_instance: Optional[SystemTrayIcon] = None


def get_tray() -> SystemTrayIcon:
    """获取系统托盘单例实例"""
    global _tray_instance
    if _tray_instance is None:
        _tray_instance = SystemTrayIcon()
    return _tray_instance


if __name__ == "__main__":
    # 测试代码
    import time

    logging.basicConfig(level=logging.INFO)

    tray = SystemTrayIcon()
    tray.start("测试设备", "192.168.1.100", 6053)

    print("托盘图标已启动，查看系统托盘...")
    print("按 Ctrl+C 退出")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        tray.stop()
