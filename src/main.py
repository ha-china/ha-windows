"""
Home Assistant Windows 客户端主程序
模拟 ESPHome 设备，让 Home Assistant 可以发现并连接
"""

import sys
import logging
import asyncio
import argparse
from pathlib import Path

# PyInstaller 打包后的路径设置
if getattr(sys, 'frozen', False):
    import os
    src_path = os.path.join(sys._MEIPASS, 'src')
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

from src.i18n import get_i18n, set_language
from src.core.mdns_discovery import MDNSBroadcaster, DeviceInfo
from src.core.esphome_server import ESPHomeServer

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('ha_windows.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


class HomeAssistantWindows:
    """
    Home Assistant Windows 客户端主类

    功能：
    1. 启动 ESPHome API 服务器（监听 6053 端口）
    2. 注册 mDNS 服务广播（让 HA 发现设备）
    3. 等待 Home Assistant 连接
    """

    DEFAULT_PORT = 6053
    DEFAULT_DEVICE_NAME = "Windows Assistant"

    def __init__(self, device_name: str = None, port: int = None):
        """
        初始化客户端

        Args:
            device_name: 设备名称
            port: API 服务端口
        """
        self.device_name = device_name or self.DEFAULT_DEVICE_NAME
        self.port = port or self.DEFAULT_PORT

        # 组件
        self.mdns_broadcaster: MDNSBroadcaster = None
        self.api_server: ESPHomeServer = None

        self.running = False

    async def run(self):
        """运行主程序"""
        try:
            logger.info("=" * 60)
            logger.info(f"🖥️  {self.device_name}")
            logger.info(f"版本: 1.0.0")
            logger.info("=" * 60)

            # Step 1: 启动 ESPHome API 服务器
            await self._start_api_server()

            # Step 2: 注册 mDNS 服务广播
            await self._register_mdns_service()

            # Step 3: 运行主循环
            self.running = True
            await self._main_loop()

        except KeyboardInterrupt:
            logger.info("用户中断，正在退出...")
        except Exception as e:
            logger.error(f"主程序错误: {e}", exc_info=True)
        finally:
            await self._cleanup()

    async def _start_api_server(self):
        """启动 ESPHome API 服务器"""
        logger.info("启动 ESPHome API 服务器...")

        self.api_server = ESPHomeServer(
            host="0.0.0.0",
            port=self.port,
        )

        success = await self.api_server.start()

        if not success:
            raise RuntimeError("API 服务器启动失败")

        # 在后台运行服务器
        asyncio.create_task(self.api_server.serve_forever())

    async def _register_mdns_service(self):
        """注册 mDNS 服务广播"""
        logger.info("注册 mDNS 服务广播...")

        device_info = DeviceInfo(
            name=self.device_name,
            version="1.0.0",
            platform="Windows",
            board="PC",
        )

        self.mdns_broadcaster = MDNSBroadcaster(device_info)
        success = await self.mdns_broadcaster.register_service(self.port)

        if not success:
            raise RuntimeError("mDNS 服务注册失败")

    async def _main_loop(self):
        """主循环"""
        logger.info("")
        logger.info("✅ 设备已启动并广播到网络!")
        logger.info("")
        logger.info("📍 在 Home Assistant 中操作:")
        logger.info("   1. 设置 > 设备与服务 > 添加集成")
        logger.info("   2. 搜索 'ESPHome' 或添加手动")
        logger.info("   3. 应该能发现此设备")
        logger.info("")
        logger.info("按 Ctrl+C 退出程序...")
        logger.info("")

        # 保持运行
        while self.running:
            await asyncio.sleep(1)

    async def _cleanup(self):
        """清理资源"""
        logger.info("正在清理资源...")

        self.running = False

        # 注销 mDNS 服务
        if self.mdns_broadcaster:
            try:
                await self.mdns_broadcaster.unregister_service()
            except Exception as e:
                logger.error(f"注销 mDNS 服务失败: {e}")

        # 停止 API 服务器
        if self.api_server:
            try:
                await self.api_server.stop()
            except Exception as e:
                logger.error(f"停止 API 服务器失败: {e}")


def main():
    """主函数"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description="Home Assistant Windows 客户端 - 模拟 ESPHome 设备"
    )
    parser.add_argument(
        '--name',
        default="Windows Assistant",
        help='设备名称（默认: Windows Assistant）'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=6053,
        help='API 服务端口（默认: 6053）'
    )
    parser.add_argument(
        '--language',
        choices=['zh_CN', 'en_US'],
        default='zh_CN',
        help='设置界面语言'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='启用调试模式'
    )

    args = parser.parse_args()

    # 设置语言
    set_language(args.language)

    # 设置日志级别
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # 创建并运行客户端
    client = HomeAssistantWindows(
        device_name=args.name,
        port=args.port,
    )

    # 运行异步主程序
    try:
        asyncio.run(client.run())
    except KeyboardInterrupt:
        logger.info("程序已退出")
        sys.exit(0)


if __name__ == "__main__":
    main()
