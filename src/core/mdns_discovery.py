"""
mDNS/Zeroconf 发现模块
用于自动发现局域网内的 Home Assistant 实例
"""

import asyncio
import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from zeroconf import ServiceBrowser, Zeroconf, ServiceStateChange
from zeroconf.asyncio import AsyncZeroconf, AsyncServiceBrowser

from ..i18n import get_i18n

logger = logging.getLogger(__name__)
_i18n = get_i18n()


@dataclass
class HomeAssistantInstance:
    """Home Assistant 实例信息"""

    name: str
    host: str
    port: int
    ipv4_addresses: List[str]
    properties: Dict[str, Any]

    @property
    def url(self) -> str:
        """获取 HA URL"""
        return f"http://{self.host}:{self.port}"

    @property
    def esphome_port(self) -> int:
        """获取 ESPHome API 端口（通常是 6053）"""
        # ESPHome 默认端口是 6053
        return 6053

    @property
    def esphome_url(self) -> str:
        """获取 ESPHome API URL"""
        return f"http://{self.host}:{self.esphome_port}"

    def __str__(self) -> str:
        return f"{self.name} ({self.url})"


class MDNSDiscovery:
    """mDNS 服务发现器"""

    # Home Assistant 的 mDNS 服务类型
    HOME_ASSISTANT_SERVICE = "_home-assistant._tcp.local."
    ESPHOME_SERVICE = "_esphomelib._tcp.local."

    def __init__(self):
        """初始化 mDNS 发现器"""
        self.aiobrowser: Optional[AsyncServiceBrowser] = None
        self.aiozc: Optional[AsyncZeroconf] = None
        self.discovered_instances: List[HomeAssistantInstance] = []

    async def discover_home_assistant(
        self, timeout: float = 5.0
    ) -> List[HomeAssistantInstance]:
        """
        发现局域网内的 Home Assistant 实例

        Args:
            timeout: 发现超时时间（秒）

        Returns:
            List[HomeAssistantInstance]: 发现的 HA 实例列表
        """
        logger.info(_i18n.t('discovering_ha'))

        self.discovered_instances.clear()
        instances = []

        try:
            # 创建 AsyncZeroconf 实例
            self.aiozc = AsyncZeroconf()

            # 定义服务类型监听列表
            service_types = [
                self.HOME_ASSISTANT_SERVICE,
                self.ESPHOME_SERVICE,
            ]

            # 创建服务浏览器
            self.aiobrowser = AsyncServiceBrowser(
                self.aiozc.zeroconf,
                service_types,
                handlers=[self._on_service_state_change],
            )

            # 等待服务发现
            await asyncio.sleep(timeout)

            # 收集发现的实例
            instances = self.discovered_instances.copy()

            logger.info(
                _i18n.t('ha_found').format(len(instances))
                if instances
                else _i18n.t('ha_not_found')
            )

        except Exception as e:
            logger.error(f"mDNS 发现失败: {e}")

        finally:
            # 清理资源
            await self._cleanup()

        return instances

    def _on_service_state_change(
        self,
        zeroconf: Zeroconf,
        service_type: str,
        name: str,
        state_change: ServiceStateChange,
    ) -> None:
        """
        服务状态变化回调

        Args:
            zeroconf: Zeroconf 实例
            service_type: 服务类型
            name: 服务名称
            state_change: 状态变化
        """
        if state_change == ServiceStateChange.Added:
            self._on_service_added(zeroconf, service_type, name)

    def _on_service_added(
        self, zeroconf: Zeroconf, service_type: str, name: str
    ) -> None:
        """
        处理新发现的服务的

        Args:
            zeroconf: Zeroconf 实例
            service_type: 服务类型
            name: 服务名称
        """
        try:
            # 查询服务信息
            info = zeroconf.get_service_info(service_type, name)

            if info is None:
                return

            # 解析服务信息
            instance = self._parse_service_info(service_type, name, info)

            if instance:
                # 避免重复添加
                if not any(
                    inst.host == instance.host and inst.port == instance.port
                    for inst in self.discovered_instances
                ):
                    self.discovered_instances.append(instance)
                    logger.info(f"发现服务: {instance}")

        except Exception as e:
            logger.error(f"解析服务信息失败: {e}")

    def _parse_service_info(
        self, service_type: str, name: str, info
    ) -> Optional[HomeAssistantInstance]:
        """
        解析服务信息为 HomeAssistantInstance

        Args:
            service_type: 服务类型
            name: 服务名称
            info: 服务信息

        Returns:
            Optional[HomeAssistantInstance]: 解析后的实例信息
        """
        try:
            # 获取 IPv4 地址
            ipv4_addresses = [
                addr
                for addr in info.parsed_addresses()
                if len(addr.split(".")) == 4  # IPv4
            ]

            if not ipv4_addresses:
                return None

            host = ipv4_addresses[0]
            port = info.port

            # 解析属性
            properties = {}
            for key, value in info.properties.items():
                if isinstance(value, bytes):
                    try:
                        properties[key.decode("utf-8")] = value.decode("utf-8")
                    except UnicodeDecodeError:
                        properties[key.decode("utf-8")] = str(value)
                else:
                    properties[key] = value

            # 解析服务名称
            # 格式通常是: "My Home Assistant._home-assistant._tcp.local."
            # 去掉后缀
            service_name = name.replace(f".{service_type}", "").split(".")[0]

            # 创建实例
            instance = HomeAssistantInstance(
                name=service_name,
                host=host,
                port=port,
                ipv4_addresses=ipv4_addresses,
                properties=properties,
            )

            return instance

        except Exception as e:
            logger.error(f"解析服务信息失败: {e}")
            return None

    async def _cleanup(self) -> None:
        """清理资源"""
        if self.aiobrowser:
            await self.aiobrowser.async_cancel()
            self.aiobrowser = None

        if self.aiozc:
            await self.aiozc.async_close()
            self.aiozc = None


class MDNSDiscoverySync:
    """mDNS 发现的同步封装（用于非异步环境）"""

    def __init__(self):
        """初始化同步发现器"""
        self.discovery = MDNSDiscovery()

    def discover_home_assistant(
        self, timeout: float = 5.0
    ) -> List[HomeAssistantInstance]:
        """
        同步发现 Home Assistant 实例

        Args:
            timeout: 发现超时时间（秒）

        Returns:
            List[HomeAssistantInstance]: 发现的 HA 实例列表
        """
        try:
            # 在新的事件循环中运行异步发现
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                instances = loop.run_until_complete(
                    self.discovery.discover_home_assistant(timeout)
                )
                return instances
            finally:
                loop.close()

        except Exception as e:
            logger.error(f"同步发现失败: {e}")
            return []


# 便捷函数
async def discover_ha_async(timeout: float = 5.0) -> List[HomeAssistantInstance]:
    """
    异步发现 Home Assistant 实例

    Args:
        timeout: 发现超时时间（秒）

    Returns:
        List[HomeAssistantInstance]: 发现的 HA 实例列表
    """
    discovery = MDNSDiscovery()
    return await discovery.discover_home_assistant(timeout)


def discover_ha(timeout: float = 5.0) -> List[HomeAssistantInstance]:
    """
    同步发现 Home Assistant 实例

    Args:
        timeout: 发现超时时间（秒）

    Returns:
        List[HomeAssistantInstance]: 发现的 HA 实例列表
    """
    sync_discovery = MDNSDiscoverySync()
    return sync_discovery.discover_home_assistant(timeout)


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.INFO)

    print("开始发现 Home Assistant 实例...")

    instances = discover_ha(timeout=10.0)

    if instances:
        print(f"\n发现 {len(instances)} 个 Home Assistant 实例:")
        for i, instance in enumerate(instances, 1):
            print(f"{i}. {instance}")
            print(f"   URL: {instance.url}")
            print(f"   ESPHome: {instance.esphome_url}")
            print(f"   IPv4: {', '.join(instance.ipv4_addresses)}")
    else:
        print("未发现任何 Home Assistant 实例")
