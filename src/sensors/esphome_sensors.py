"""
ESPHome 传感器上报模块
将 Windows 系统状态上报到 Home Assistant
"""

import asyncio
import logging
from typing import Dict, Optional

from aioesphomeapi import APIClient

from .windows_monitor import WindowsMonitor
from ..core.mdns_discovery import HomeAssistantInstance
from ..i18n import get_i18n

logger = logging.getLogger(__name__)
_i18n = get_i18n()


class ESPHomeSensors:
    """ESPHome 传感器上报器"""

    # 传感器键值定义
    SENSOR_CPU_PERCENT = 0
    SENSOR_MEM_PERCENT = 1
    SENSOR_MEM_USED = 2
    SENSOR_MEM_TOTAL = 3
    SENSOR_DISK_PERCENT = 4
    SENSOR_DISK_USED = 5
    SENSOR_DISK_TOTAL = 6
    SENSOR_BATTERY_PERCENT = 7
    SENSOR_BATTERY_CHARGING = 8
    SENSOR_NET_BYTES_SENT = 9
    SENSOR_NET_BYTES_RECV = 10

    def __init__(self, instance: HomeAssistantInstance):
        """
        初始化传感器上报器

        Args:
            instance: Home Assistant 实例
        """
        self.instance = instance
        self.monitor = WindowsMonitor()
        self.client: Optional[APIClient] = None
        self._running = False

        logger.info("ESPHome 传感器上报器已初始化")

    async def connect(self) -> bool:
        """
        连接到 Home Assistant ESPHome API

        Returns:
            bool: 连接是否成功
        """
        try:
            logger.info(f"连接传感器服务: {instance.esphome_url}")

            self.client = APIClient(
                address=self.instance.host,
                port=self.instance.esphome_port,
                password=None,
            )

            await self.client.connect(login=True)

            logger.info("传感器服务连接成功")
            return True

        except Exception as e:
            logger.error(f"传感器服务连接失败: {e}")
            return False

    async def disconnect(self) -> None:
        """断开连接"""
        if self.client:
            await self.client.disconnect()
            self.client = None

    async def start_reporting(self, interval: float = 10.0) -> None:
        """
        开始上报传感器数据

        Args:
            interval: 上报间隔（秒）
        """
        self._running = True

        while self._running:
            try:
                # 获取系统信息
                info = self.monitor.get_all_info()

                # 上报传感器数据
                await self._report_sensors(info)

                # 等待下一次上报
                await asyncio.sleep(interval)

            except Exception as e:
                logger.error(f"传感器上报失败: {e}")
                await asyncio.sleep(interval)

    def stop_reporting(self) -> None:
        """停止上报"""
        self._running = False

    async def _report_sensors(self, info: Dict) -> None:
        """
        上报传感器数据

        Args:
            info: 系统信息
        """
        try:
            if not self.client:
                logger.warning("未连接到 ESPHome API")
                return

            # CPU 使用率
            cpu_info = info.get('cpu', {})
            if 'cpu_percent' in cpu_info:
                await self._send_sensor_state(
                    self.SENSOR_CPU_PERCENT,
                    cpu_info['cpu_percent']
                )

            # 内存信息
            mem_info = info.get('memory', {})
            if 'percent' in mem_info:
                await self._send_sensor_state(
                    self.SENSOR_MEM_PERCENT,
                    mem_info['percent']
                )
            if 'used' in mem_info:
                await self._send_sensor_state(
                    self.SENSOR_MEM_USED,
                    mem_info['used'] / (1024 ** 3)  # GB
                )
            if 'total' in mem_info:
                await self._send_sensor_state(
                    self.SENSOR_MEM_TOTAL,
                    mem_info['total'] / (1024 ** 3)  # GB
                )

            # 磁盘信息（C 盘）
            disk_info = info.get('disk', {})
            if 'C:\\' in disk_info:
                c_disk = disk_info['C:\\']
                if 'percent' in c_disk:
                    await self._send_sensor_state(
                        self.SENSOR_DISK_PERCENT,
                        c_disk['percent']
                    )
                if 'used' in c_disk:
                    await self._send_sensor_state(
                        self.SENSOR_DISK_USED,
                        c_disk['used'] / (1024 ** 3)  # GB
                    )
                if 'total' in c_disk:
                    await self._send_sensor_state(
                        self.SENSOR_DISK_TOTAL,
                        c_disk['total'] / (1024 ** 3)  # GB
                    )

            # 电池信息
            battery_info = info.get('battery')
            if battery_info:
                if 'percent' in battery_info:
                    await self._send_sensor_state(
                        self.SENSOR_BATTERY_PERCENT,
                        battery_info['percent']
                    )
                if 'power_plugged' in battery_info:
                    await self._send_sensor_state(
                        self.SENSOR_BATTERY_CHARGING,
                        1 if battery_info['power_plugged'] else 0
                    )

            # 网络信息
            net_info = info.get('network', {})
            if 'bytes_sent' in net_info:
                await self._send_sensor_state(
                    self.SENSOR_NET_BYTES_SENT,
                    net_info['bytes_sent'] / (1024 ** 3)  # GB
                )
            if 'bytes_recv' in net_info:
                await self._send_sensor_state(
                    self.SENSOR_NET_BYTES_RECV,
                    net_info['bytes_recv'] / (1024 ** 3)  # GB
                )

        except Exception as e:
            logger.error(f"上报传感器数据失败: {e}")

    async def _send_sensor_state(self, key: int, state: float) -> None:
        """
        发送传感器状态

        Args:
            key: 传感器键值
            state: 传感器状态值
        """
        # TODO: 实现实际的 ESPHome 传感器状态上报
        # 这里需要参考 linux-voice-assistant 的实现
        # 可能需要调用特定的 API 方法

        logger.debug(f"传感器上报: key={key}, value={state}")


# 便捷函数
async def start_sensor_reporting(
    instance: HomeAssistantInstance,
    interval: float = 10.0
) -> ESPHomeSensors:
    """
    启动传感器上报（便捷函数）

    Args:
        instance: Home Assistant 实例
        interval: 上报间隔

    Returns:
        ESPHomeSensors: 传感器上报器实例
    """
    reporter = ESPHomeSensors(instance)

    # 连接
    if not await reporter.connect():
        raise RuntimeError("无法连接到传感器服务")

    # 启动上报任务
    asyncio.create_task(reporter.start_reporting(interval))

    return reporter


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.INFO)

    async def test_sensors():
        """测试传感器上报"""
        logger.info("测试 ESPHome 传感器上报")

        from ..core.mdns_discovery import discover_ha

        # 发现 HA
        instances = await asyncio.to_thread(discover_ha, timeout=10.0)

        if not instances:
            logger.error("未发现 Home Assistant 实例")
            return

        instance = instances[0]

        # 创建上报器
        reporter = ESPHomeSensors(instance)

        # 测试连接
        if await reporter.connect():
            logger.info("传感器服务连接成功")

            # 测试上报（只上报一次）
            info = reporter.monitor.get_all_info()
            await reporter._report_sensors(info)

            # 断开连接
            await reporter.disconnect()
        else:
            logger.error("传感器服务连接失败")

    # 运行测试
    asyncio.run(test_sensors())
