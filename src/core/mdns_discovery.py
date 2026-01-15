"""
mDNS/Zeroconf Service Broadcast Module
Broadcasts ESPHome device to LAN for Home Assistant discovery
"""

import asyncio
import logging
import socket
from typing import Optional, Dict
from dataclasses import dataclass

from zeroconf import ServiceInfo
from zeroconf.asyncio import AsyncZeroconf

from src.i18n import get_i18n

logger = logging.getLogger(__name__)
_i18n = get_i18n()


@dataclass
class DeviceInfo:
    """Device Information"""

    name: str = None  # Default to local machine name
    version: str = "1.0.0"
    platform: str = "Windows"
    board: str = "PC"
    mac_address: Optional[str] = None

    def __post_init__(self):
        """Post-initialization processing"""
        if self.name is None:
            # Get local machine name
            self.name = self._get_hostname()
        if self.mac_address is None:
            # Get local MAC address
            self.mac_address = self._get_mac_address()

    @staticmethod
    def _get_hostname() -> str:
        """Get local machine name"""
        import socket
        try:
            hostname = socket.gethostname()
            # Remove possible domain suffix
            return hostname.split('.')[0]
        except Exception:
            return "Windows-PC"

    @staticmethod
    def _get_mac_address() -> str:
        """Get local MAC address"""
        try:
            # Get MAC address of first non-loopback interface
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            s.getsockname()[0]  # Trigger connection
            s.close()

            # Get MAC from IP
            import uuid
            mac = uuid.getnode()
            mac_str = ':'.join(f'{(mac >> (i * 8)) & 0xff:02x}' for i in range(5, -1, -1))
            return mac_str
        except Exception:
            # Return default MAC
            return "00:00:00:00:00:01"


class MDNSBroadcaster:
    """
    mDNS Service Broadcaster

    Broadcasts ESPHome device service to LAN for Home Assistant discovery and connection
    """

    # ESPHome mDNS service type
    ESPHOME_SERVICE_TYPE = "_esphomelib._tcp.local."
    SERVICE_PORT = 6053  # ESPHome API default port

    def __init__(self, device_info: Optional[DeviceInfo] = None):
        """
        Initialize mDNS broadcaster

        Args:
            device_info: Device information, defaults to DeviceInfo()
        """
        self.device_info = device_info or DeviceInfo()
        self.aiozc: Optional[AsyncZeroconf] = None
        self.service_info: Optional[ServiceInfo] = None
        self._is_registered = False

    async def register_service(self, port: int = SERVICE_PORT) -> bool:
        """
        Register mDNS service, broadcast device presence to network

        Args:
            port: ESPHome API listening port

        Returns:
            bool: Whether registration was successful
        """
        try:
            logger.info(_i18n.t('registering_mdns'))

            # Create AsyncZeroconf instance
            self.aiozc = AsyncZeroconf()

            # Get local IP address
            local_ip = self._get_local_ip()
            if not local_ip:
                logger.error("Failed to get local IP address")
                return False

            # Build TXT record (ESPHome device properties)
            txt_record = self._build_txt_record()

            # Create service info
            # Service name format: {device_name}._esphomelib._tcp.local.
            service_name = f"{self.device_info.name}.{self.ESPHOME_SERVICE_TYPE}"

            self.service_info = ServiceInfo(
                self.ESPHOME_SERVICE_TYPE,
                service_name,
                addresses=[socket.inet_aton(local_ip)],
                port=port,
                properties=txt_record,
                server=f"{socket.gethostname().split('.')[0]}.local.",
            )

            # Register service
            await self.aiozc.async_register_service(self.service_info)
            self._is_registered = True

            logger.info("mDNS service registered successfully!")
            logger.info(f"Device name: {self.device_info.name}")
            logger.info(f"Local IP: {local_ip}")
            logger.info(f"Listening port: {port}")
            logger.info(f"MAC address: {self.device_info.mac_address}")

            return True

        except Exception as e:
            logger.error(f"mDNS service registration failed: {e}")
            return False

    def _build_txt_record(self) -> Dict[str, str]:
        """
        Build ESPHome device TXT record

        Fully references linux-voice-assistant format

        Returns:
            Dict[str, str]: TXT record dictionary
        """
        # MAC address in mDNS uses no-colon format
        mac_no_colons = self.device_info.mac_address.replace(":", "").lower()

        txt_record = {
            # Reference linux-voice-assistant TXT record format
            "version": "2025.9.0",
            "mac": mac_no_colons,
            "board": "host",
            "platform": "HOST",
            "network": "ethernet",
        }
        return txt_record

    @staticmethod
    def _get_local_ip() -> Optional[str]:
        """
        Get local LAN IP address

        Returns:
            Optional[str]: Local IP address, None if failed
        """
        try:
            # Get local IP by connecting to external address
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return None

    @property
    def is_registered(self) -> bool:
        """Whether service is registered"""
        return self._is_registered

    async def unregister_service(self) -> None:
        """Unregister mDNS service"""
        if self.aiozc and self.service_info and self._is_registered:
            try:
                await self.aiozc.async_unregister_service(self.service_info)
                logger.info("mDNS service unregistered")
            except Exception as e:
                logger.error(f"Failed to unregister service: {e}")
            finally:
                await self._cleanup()
                self._is_registered = False

    async def _cleanup(self) -> None:
        """Cleanup resources"""
        if self.aiozc:
            try:
                await self.aiozc.async_close()
            except Exception:
                pass
            self.aiozc = None
        self.service_info = None

    async def __aenter__(self):
        """Async context manager entry"""
        await self.register_service()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.unregister_service()


# Convenience function
async def register_device(
    device_name: str = "Windows Assistant",
    port: int = MDNSBroadcaster.SERVICE_PORT,
) -> MDNSBroadcaster:
    """
    Register device to mDNS network

    Args:
        device_name: Device name
        port: API service port

    Returns:
        MDNSBroadcaster: Broadcaster instance
    """
    device_info = DeviceInfo(name=device_name)
    broadcaster = MDNSBroadcaster(device_info)
    await broadcaster.register_service(port)
    return broadcaster


if __name__ == "__main__":
    # Test code - broadcast device for 30 seconds
    import asyncio as aio

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    async def test():
        print("Starting ESPHome device broadcast...")

        broadcaster = MDNSBroadcaster()
        success = await broadcaster.register_service()

        if success:
            print("\nDevice broadcasted to network!")
            print("Add ESPHome device in Home Assistant to discover")
            print("\nWaiting 30 seconds before auto-exit...")

            await aio.sleep(30)

            await broadcaster.unregister_service()

    aio.run(test())
