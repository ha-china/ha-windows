"""
mDNS/Zeroconf 服务广播模块
向局域网广播 ESPHome 设备，让 Home Assistant 能够发现
"""

import asyncio
import logging
import socket
from typing import Optional, Dict, Any
from dataclasses import dataclass

from zeroconf import ServiceInfo, Zeroconf
from zeroconf.asyncio import AsyncZeroconf

from src.i18n import get_i18n

logger = logging.getLogger(__name__)
_i18n = get_i18n()


@dataclass
class DeviceInfo:
    """设备信息"""

    name: str = "Windows Assistant"
    version: str = "1.0.0"
    platform: str = "Windows"
    board: str = "PC"
    mac_address: Optional[str] = None

    def __post_init__(self):
        """初始化后处理"""
        if self.mac_address is None:
            # 获取本机 MAC 地址
            self.mac_address = self._get_mac_address()

    @staticmethod
    def _get_mac_address() -> str:
        """获取本机 MAC 地址"""
        try:
            # 获取第一个非回网接口的 MAC 地址
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()

            # 通过 IP 获取 MAC
            import uuid
            mac = uuid.getnode()
            mac_str = ':'.join(f'{(mac >> (i * 8)) & 0xff:02x}' for i in range(5, -1, -1))
            return mac_str
        except Exception:
            # 返回默认 MAC
            return "00:00:00:00:00:01"


class MDNSBroadcaster:
    """
    mDNS 服务广播器

    向局域网广播 ESPHome 设备服务，让 Home Assistant 能够发现并连接
    """

    # ESPHome 的 mDNS 服务类型
    ESPHOME_SERVICE_TYPE = "_esphomelib._tcp.local."
    SERVICE_PORT = 6053  # ESPHome API 默认端口

    def __init__(self, device_info: Optional[DeviceInfo] = None):
        """
        初始化 mDNS 广播器

        Args:
            device_info: 设备信息，默认使用 DeviceInfo()
        """
        self.device_info = device_info or DeviceInfo()
        self.aiozc: Optional[AsyncZeroconf] = None
        self.service_info: Optional[ServiceInfo] = None
        self._is_registered = False

    async def register_service(self, port: int = SERVICE_PORT) -> bool:
        """
        注册 mDNS 服务，向网络广播设备存在

        Args:
            port: ESPHome API 监听端口

        Returns:
            bool: 注册是否成功
        """
        try:
            logger.info(_i18n.t('registering_mdns'))

            # 创建 AsyncZeroconf 实例
            self.aiozc = AsyncZeroconf()

            # 获取本机 IP 地址
            local_ip = self._get_local_ip()
            if not local_ip:
                logger.error("无法获取本机 IP 地址")
                return False

            # 构建 TXT 记录（ESPHome 设备属性）
            txt_record = self._build_txt_record()

            # 创建服务信息
            # 服务名称格式: {device_name}._esphomelib._tcp.local.
            service_name = f"{self.device_info.name}.{self.ESPHOME_SERVICE_TYPE}"

            self.service_info = ServiceInfo(
                self.ESPHOME_SERVICE_TYPE,
                service_name,
                addresses=[socket.inet_aton(local_ip)],
                port=port,
                properties=txt_record,
                server=f"{socket.gethostname().split('.')[0]}.local.",
            )

            # 注册服务
            await self.aiozc.async_register_service(self.service_info)
            self._is_registered = True

            logger.info(f"✅ mDNS 服务注册成功!")
            logger.info(f"   设备名称: {self.device_info.name}")
            logger.info(f"   本机 IP: {local_ip}")
            logger.info(f"   监听端口: {port}")
            logger.info(f"   MAC 地址: {self.device_info.mac_address}")

            return True

        except Exception as e:
            logger.error(f"❌ mDNS 服务注册失败: {e}")
            return False

    def _build_txt_record(self) -> Dict[str, str]:
        """
        构建 ESPHome 设备的 TXT 记录

        这些属性会被 Home Assistant 读取，用于识别设备

        Returns:
            Dict[str, str]: TXT 记录字典
        """
        txt_record = {
            # ESPHome 核心属性
            "version": self.device_info.version,
            "platform": self.device_info.platform,
            "board": self.device_info.board,
            # MAC 地址用于设备唯一标识
            "mac": self.device_info.mac_address,
            # 设备名称
            "friendly_name": self.device_info.name,
            # 设备类型标识
            "package_import": "false",
            "project_name": "HomeAssistantWindows.windows_client",
            "project_version": self.device_info.version,
        }
        return txt_record

    @staticmethod
    def _get_local_ip() -> Optional[str]:
        """
        获取本机局域网 IP 地址

        Returns:
            Optional[str]: 本机 IP 地址，获取失败返回 None
        """
        try:
            # 通过连接外部地址获取本机 IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return None

    @property
    def is_registered(self) -> bool:
        """服务是否已注册"""
        return self._is_registered

    async def unregister_service(self) -> None:
        """注销 mDNS 服务"""
        if self.aiozc and self.service_info and self._is_registered:
            try:
                await self.aiozc.async_unregister_service(self.service_info)
                logger.info("mDNS 服务已注销")
            except Exception as e:
                logger.error(f"注销服务失败: {e}")
            finally:
                await self._cleanup()
                self._is_registered = False

    async def _cleanup(self) -> None:
        """清理资源"""
        if self.aiozc:
            try:
                await self.aiozc.async_close()
            except Exception:
                pass
            self.aiozc = None
        self.service_info = None

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.register_service()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.unregister_service()


# 便捷函数
async def register_device(
    device_name: str = "Windows Assistant",
    port: int = MDNSBroadcaster.SERVICE_PORT,
) -> MDNSBroadcaster:
    """
    注册设备到 mDNS 网络

    Args:
        device_name: 设备名称
        port: API 服务端口

    Returns:
        MDNSBroadcaster: 广播器实例
    """
    device_info = DeviceInfo(name=device_name)
    broadcaster = MDNSBroadcaster(device_info)
    await broadcaster.register_service(port)
    return broadcaster


if __name__ == "__main__":
    # 测试代码 - 广播设备 30 秒
    import asyncio

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    async def test():
        print("开始广播 ESPHome 设备...")

        broadcaster = MDNSBroadcaster()
        success = await broadcaster.register_service()

        if success:
            print(f"\n✅ 设备已广播到网络!")
            print(f"   在 Home Assistant 中添加 ESPHome 设备即可发现")
            print(f"\n等待 30 秒后自动退出...")

            await asyncio.sleep(30)

            await broadcaster.unregister_service()

    asyncio.run(test())
