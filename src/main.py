"""
Home Assistant Windows 客户端主程序入口
零配置 HA Windows 原生客户端，支持 Voice Assistant
"""

import sys
import logging
import asyncio
import argparse
from pathlib import Path

# PyInstaller 打包后的路径设置
if getattr(sys, 'frozen', False):
    # PyInstaller 打包后的环境
    # _MEIPASS 是临时解压目录，src 已经在里面了
    # 不需要额外设置路径，因为现在是从 src 包启动
    pass

from i18n import get_i18n, set_language
from core.mdns_discovery import discover_ha
from core.esphome_connection import ESPHomeConnectionManager

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
_i18n = get_i18n()


class HomeAssistantWindows:
    """Home Assistant Windows 客户端主类"""

    def __init__(self):
        """初始化客户端"""
        self.connection_manager = ESPHomeConnectionManager()
        self.running = False

    async def run(self):
        """运行主程序"""
        try:
            logger.info("=" * 60)
            logger.info(_i18n.t('app_name'))
            logger.info(f"Version: 0.1.0")
            logger.info("=" * 60)

            # Step 1: 发现 Home Assistant 实例
            await self._discover_and_connect()

            # Step 2: 运行主循环
            self.running = True
            await self._main_loop()

        except KeyboardInterrupt:
            logger.info("用户中断，正在退出...")
        except Exception as e:
            logger.error(f"主程序错误: {e}", exc_info=True)
        finally:
            await self._cleanup()

    async def _discover_and_connect(self):
        """发现并连接到 Home Assistant"""
        logger.info(_i18n.t('discovering_ha'))

        # 发现 HA 实例
        instances = await asyncio.to_thread(discover_ha, timeout=10.0)

        if not instances:
            logger.error(_i18n.t('ha_not_found'))
            logger.error("请确保:")
            logger.error("  1. Home Assistant 正在运行")
            logger.error("  2. 与 Windows 电脑在同一局域网")
            logger.error("  3. Home Assistant 的 mDNS 服务已启用")
            return False

        # 显示发现的实例
        logger.info(f"\n发现 {len(instances)} 个 Home Assistant 实例:")
        for i, instance in enumerate(instances, 1):
            logger.info(f"  {i}. {instance.name} - {instance.url}")
            logger.info(f"     ESPHome: {instance.esphome_url}")

        # 选择实例（如果多个）
        if len(instances) == 1:
            instance = instances[0]
        else:
            # TODO: 实现 UI 让用户选择
            logger.info("\n默认选择第一个实例")
            instance = instances[0]

        # 连接到选定的实例
        logger.info(f"\n正在连接到: {instance.name}")
        connection = await self.connection_manager.connect_to_instance(instance)

        if connection.is_connected():
            logger.info("✅ " + _i18n.t('connection_successful'))
            return True
        else:
            logger.error("❌ " + _i18n.t('connection_failed'))
            return False

    async def _main_loop(self):
        """主循环"""
        logger.info("\n主程序已启动，按 Ctrl+C 退出")

        # TODO: 实现实际的功能循环
        # 目前只是保持运行
        while self.running:
            await asyncio.sleep(1)

    async def _cleanup(self):
        """清理资源"""
        logger.info("正在清理资源...")
        await self.connection_manager.disconnect_all()
        self.running = False


def main():
    """主函数"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description="Home Assistant Windows 客户端"
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
    client = HomeAssistantWindows()

    # 运行异步主程序
    try:
        asyncio.run(client.run())
    except KeyboardInterrupt:
        logger.info("程序已退出")
        sys.exit(0)


if __name__ == "__main__":
    main()
