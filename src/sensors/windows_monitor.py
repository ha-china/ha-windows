"""
Windows 系统监控模块
使用 psutil 监控 Windows 系统状态
"""

import asyncio
import logging
import platform
from typing import Dict, Optional

import psutil

from ..i18n import get_i18n

logger = logging.getLogger(__name__)
_i18n = get_i18n()


class WindowsMonitor:
    """Windows 系统监控器"""

    def __init__(self):
        """初始化系统监控器"""
        self._boot_time = psutil.boot_time()
        logger.info("Windows 监控器已初始化")

    def get_cpu_info(self) -> Dict:
        """
        获取 CPU 信息

        Returns:
            Dict: CPU 信息
        """
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            cpu_freq = psutil.cpu_freq()

            return {
                'cpu_percent': cpu_percent,
                'cpu_count': cpu_count,
                'cpu_freq_current': cpu_freq.current if cpu_freq else None,
                'cpu_freq_max': cpu_freq.max if cpu_freq else None,
            }
        except Exception as e:
            logger.error(f"获取 CPU 信息失败: {e}")
            return {}

    def get_memory_info(self) -> Dict:
        """
        获取内存信息

        Returns:
            Dict: 内存信息
        """
        try:
            mem = psutil.virtual_memory()

            return {
                'total': mem.total,
                'available': mem.available,
                'used': mem.used,
                'free': mem.free,
                'percent': mem.percent,
            }
        except Exception as e:
            logger.error(f"获取内存信息失败: {e}")
            return {}

    def get_disk_info(self) -> Dict:
        """
        获取磁盘信息

        Returns:
            Dict: 磁盘信息（所有分区）
        """
        try:
            disk_info = {}

            for partition in psutil.disk_partitions():
                if 'cdrom' in partition.opts or partition.fstype == '':
                    continue

                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    disk_info[partition.mountpoint] = {
                        'device': partition.device,
                        'fstype': partition.fstype,
                        'total': usage.total,
                        'used': usage.used,
                        'free': usage.free,
                        'percent': usage.percent,
                    }
                except PermissionError:
                    continue

            return disk_info
        except Exception as e:
            logger.error(f"获取磁盘信息失败: {e}")
            return {}

    def get_battery_info(self) -> Optional[Dict]:
        """
        获取电池信息（笔记本）

        Returns:
            Optional[Dict]: 电池信息，如果没有电池则返回 None
        """
        try:
            battery = psutil.sensors_battery()

            if battery is None:
                return None

            return {
                'percent': battery.percent,
                'power_plugged': battery.power_plugged,
                'secsleft': battery.secsleft,
            }
        except Exception as e:
            logger.error(f"获取电池信息失败: {e}")
            return None

    def get_network_info(self) -> Dict:
        """
        获取网络信息

        Returns:
            Dict: 网络信息
        """
        try:
            net_io = psutil.net_io_counters()
            net_connections = len(psutil.net_connections())

            return {
                'bytes_sent': net_io.bytes_sent,
                'bytes_recv': net_io.bytes_recv,
                'packets_sent': net_io.packets_sent,
                'packets_recv': net_io.packets_recv,
                'connections': net_connections,
            }
        except Exception as e:
            logger.error(f"获取网络信息失败: {e}")
            return {}

    def get_system_info(self) -> Dict:
        """
        获取系统信息

        Returns:
            Dict: 系统信息
        """
        try:
            return {
                'system': platform.system(),
                'release': platform.release(),
                'version': platform.version(),
                'machine': platform.machine(),
                'processor': platform.processor(),
                'hostname': platform.node(),
                'boot_time': self._boot_time,
            }
        except Exception as e:
            logger.error(f"获取系统信息失败: {e}")
            return {}

    def get_all_info(self) -> Dict:
        """
        获取所有信息

        Returns:
            Dict: 所有系统信息
        """
        return {
            'cpu': self.get_cpu_info(),
            'memory': self.get_memory_info(),
            'disk': self.get_disk_info(),
            'battery': self.get_battery_info(),
            'network': self.get_network_info(),
            'system': self.get_system_info(),
        }


class AsyncWindowsMonitor:
    """异步 Windows 系统监控器"""

    def __init__(self, update_interval: float = 5.0):
        """
        初始化异步监控器

        Args:
            update_interval: 更新间隔（秒）
        """
        self.monitor = WindowsMonitor()
        self.update_interval = update_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start_monitoring(self, callback=None):
        """
        开始监控

        Args:
            callback: 数据更新回调函数
        """
        self._running = True

        while self._running:
            try:
                # 获取系统信息
                info = await asyncio.to_thread(self.monitor.get_all_info)

                # 调用回调
                if callback:
                    await callback(info)

                # 等待下一次更新
                await asyncio.sleep(self.update_interval)

            except Exception as e:
                logger.error(f"监控错误: {e}")
                await asyncio.sleep(self.update_interval)

    def stop_monitoring(self):
        """停止监控"""
        self._running = False


# 便捷函数
def get_system_info() -> Dict:
    """
    获取系统信息（同步）

    Returns:
        Dict: 系统信息
    """
    monitor = WindowsMonitor()
    return monitor.get_all_info()


async def get_system_info_async() -> Dict:
    """
    获取系统信息（异步）

    Returns:
        Dict: 系统信息
    """
    monitor = WindowsMonitor()
    return await asyncio.to_thread(monitor.get_all_info)


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.INFO)

    import json

    async def test_monitor():
        """测试监控器"""
        logger.info("测试 Windows 监控器")

        monitor = WindowsMonitor()

        # 获取所有信息
        info = monitor.get_all_info()

        # 格式化输出
        logger.info("\n系统信息:")
        logger.info(json.dumps(info, indent=2, default=str))

        # 测试异步监控
        async_monitor = AsyncWindowsMonitor(update_interval=2.0)

        logger.info("\n异步监控测试（5 秒）...")
        task = asyncio.create_task(async_monitor.start_monitoring(
            lambda info: logger.info(f"监控更新: CPU {info['cpu'].get('cpu_percent')}%")
        ))

        await asyncio.sleep(5)

        async_monitor.stop_monitoring()
        await task

        logger.info("\n监控测试完成")

    # 运行测试
    asyncio.run(test_monitor())
