"""
Windows System Monitor Module

Monitors Windows system status using psutil.
Also provides ESPHome entity definitions and states for server mode.
"""

import asyncio
import logging
import platform
from typing import Dict, List, Optional, Tuple

import psutil
from aioesphomeapi.api_pb2 import (
    ListEntitiesDoneResponse,
    ListEntitiesTextSensorResponse,
    TextSensorStateResponse,
)

from src.i18n import get_i18n

# Lazy import for media player to avoid circular dependency
def _get_media_player_module():
    """Lazy import media player module"""
    try:
        from src.voice import mpv_player
        return mpv_player
    except ImportError:
        return None

logger = logging.getLogger(__name__)
_i18n = get_i18n()

# ESPHome sensor/entity key definitions (server mode)
SENSOR_KEYS = {
    "cpu_usage": 1,
    "memory_usage": 2,
    "disk_usage": 3,
    "battery_status": 4,
    "battery_level": 5,
    "network_status": 6,
}


class WindowsMonitor:
    """
    Windows System Monitor

    Monitors Windows system status using psutil.
    Also provides ESPHome entity definitions and states for server mode.
    """

    def __init__(self):
        """Initialize system monitor"""
        self._boot_time = psutil.boot_time()
        self._available_entities: List[Tuple[str, str, str, int]] = []
        self._entity_map: Dict[str, Tuple[str, str, int]] = {}
        logger.info("Windows monitor initialized")

    # ========================================================================
    # System Info Methods
    # ========================================================================

    def get_cpu_info(self) -> Dict:
        """
        Get CPU information

        Returns:
            Dict: CPU information
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
            logger.error(f"Failed to get CPU info: {e}")
            return {}

    def get_memory_info(self) -> Dict:
        """
        Get memory information

        Returns:
            Dict: Memory information
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
            logger.error(f"Failed to get memory info: {e}")
            return {}

    def get_disk_info(self) -> Dict:
        """
        Get disk information

        Returns:
            Dict: Disk information (all partitions)
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
            logger.error(f"Failed to get disk info: {e}")
            return {}

    def get_battery_info(self) -> Optional[Dict]:
        """
        Get battery information (laptop)

        Returns:
            Optional[Dict]: Battery information, None if no battery
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
            logger.error(f"Failed to get battery info: {e}")
            return None

    def get_network_info(self) -> Dict:
        """
        Get network information

        Returns:
            Dict: Network information
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
            logger.error(f"Failed to get network info: {e}")
            return {}

    def get_system_info(self) -> Dict:
        """
        Get system information

        Returns:
            Dict: System information
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
            logger.error(f"Failed to get system info: {e}")
            return {}

    def get_all_info(self) -> Dict:
        """
        Get all information

        Returns:
            Dict: All system information
        """
        return {
            'cpu': self.get_cpu_info(),
            'memory': self.get_memory_info(),
            'disk': self.get_disk_info(),
            'battery': self.get_battery_info(),
            'network': self.get_network_info(),
            'system': self.get_system_info(),
        }

    # ========================================================================
    # ESPHome Entity Methods (Server Mode)
    # ========================================================================

    def discover_esp_entities(self) -> List[Tuple[str, str, str, int]]:
        """
        Discover available ESPHome entities (only include those with valid data)

        Returns:
            List of tuples: (object_id, name, icon, key)
        """
        info = self.get_all_info()
        available = []

        # CPU - always available
        available.append(("cpu_usage", "CPU Usage", "mdi:cpu-64-bit", SENSOR_KEYS["cpu_usage"]))

        # Memory - always available
        available.append(("memory_usage", "Memory Usage", "mdi:memory", SENSOR_KEYS["memory_usage"]))

        # Disk - check if C drive exists
        if 'C:\\' in info.get('disk', {}):
            available.append(("disk_usage", "Disk Usage", "mdi:harddisk", SENSOR_KEYS["disk_usage"]))

        # Battery - only if battery info available
        if info.get('battery'):
            available.append(("battery_status", "Battery Status", "mdi:battery", SENSOR_KEYS["battery_status"]))
            available.append(("battery_level", "Battery Level", "mdi:battery-90", SENSOR_KEYS["battery_level"]))

# Network - always available
        available.append(("network_status", "Network Status", "mdi:network", SENSOR_KEYS["network_status"]))

        self._available_entities = available
        self._entity_map = {obj_id: (name, icon, key) for obj_id, name, icon, key in available}

        logger.info(f"Discovered {len(available)} ESPHome sensor entities")
        return available

    def get_esp_entity_count(self) -> int:
        """Get number of available ESPHome entities"""
        if not self._available_entities:
            self.discover_esp_entities()
        return len(self._available_entities)

    def get_esp_entity_definitions(self) -> List:
        """
        Get ESPHome entity definitions for ListEntitiesResponse

        Returns:
            List of entity definitions
        """
        if not self._available_entities:
            self.discover_esp_entities()

        entities = []
        for object_id, name, icon, key in self._available_entities:
            sensor = ListEntitiesTextSensorResponse(
                object_id=object_id,
                key=key,
                name=name,
                icon=icon,
            )
            entities.append(sensor)
        
        entities.append(ListEntitiesDoneResponse())
        return entities

    def get_esp_sensor_states(self, **extra_states) -> List:
        """
        Get current ESPHome sensor states

        Args:
            **extra_states: Additional states (e.g., command_result, voice_status)

        Returns:
            List of state responses
        """
        if not self._entity_map:
            self.discover_esp_entities()

        states = []
        info = self.get_all_info()

        if "cpu_usage" in self._entity_map:
            cpu_info = info.get('cpu', {})
            cpu_percent = cpu_info.get('cpu_percent', 0)
            _, _, key = self._entity_map["cpu_usage"]
            states.append(TextSensorStateResponse(key=key, state=f"{cpu_percent:.1f}%"))

        if "memory_usage" in self._entity_map:
            mem_info = info.get('memory', {})
            mem_percent = mem_info.get('percent', 0)
            _, _, key = self._entity_map["memory_usage"]
            states.append(TextSensorStateResponse(key=key, state=f"{mem_percent:.1f}%"))

        if "disk_usage" in self._entity_map:
            disk_info = info.get('disk', {})
            if 'C:\\' in disk_info:
                disk_percent = disk_info['C:\\'].get('percent', 0)
                _, _, key = self._entity_map["disk_usage"]
                states.append(TextSensorStateResponse(key=key, state=f"{disk_percent:.1f}%"))

        if "battery_status" in self._entity_map:
            battery_info = info.get('battery')
            if battery_info:
                status = "Charging" if battery_info.get('power_plugged') else "Discharging"
                _, _, key = self._entity_map["battery_status"]
                states.append(TextSensorStateResponse(key=key, state=status))

                if "battery_level" in self._entity_map:
                    _, _, key = self._entity_map["battery_level"]
                    states.append(TextSensorStateResponse(key=key, state=f"{battery_info.get('percent', 0)}%"))

        if "network_status" in self._entity_map:
            net_info = info.get('network', {})
            online = "Online" if net_info.get('bytes_sent', 0) > 0 or net_info.get('bytes_recv', 0) > 0 else "Offline"
            _, _, key = self._entity_map["network_status"]
            states.append(TextSensorStateResponse(key=key, state=online))

        # Extra states (command_result, voice_status, etc.)
        for entity_name, state_value in extra_states.items():
            if entity_name in self._entity_map:
                _, _, key = self._entity_map[entity_name]
                states.append(TextSensorStateResponse(key=key, state=str(state_value)))

        return states


class AsyncWindowsMonitor:
    """Async Windows system monitor"""

    def __init__(self, update_interval: float = 5.0):
        """
        Initialize async monitor

        Args:
            update_interval: Update interval in seconds
        """
        self.monitor = WindowsMonitor()
        self.update_interval = update_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start_monitoring(self, callback=None):
        """
        Start monitoring

        Args:
            callback: Data update callback function
        """
        self._running = True

        while self._running:
            try:
                # Get system info
                info = await asyncio.to_thread(self.monitor.get_all_info)

                # Call callback
                if callback:
                    await callback(info)

                # Wait for next update
                await asyncio.sleep(self.update_interval)

            except Exception as e:
                logger.error(f"Monitoring error: {e}")
                await asyncio.sleep(self.update_interval)

    def stop_monitoring(self):
        """Stop monitoring"""
        self._running = False


# Convenience functions
def get_system_info() -> Dict:
    """
    Get system info (sync)

    Returns:
        Dict: System information
    """
    monitor = WindowsMonitor()
    return monitor.get_all_info()


async def get_system_info_async() -> Dict:
    """
    Get system info (async)

    Returns:
        Dict: System information
    """
    monitor = WindowsMonitor()
    return await asyncio.to_thread(monitor.get_all_info)


if __name__ == "__main__":
    # Test code
    logging.basicConfig(level=logging.INFO)

    import json

    async def test_monitor():
        """Test monitor"""
        logger.info("Testing Windows monitor")

        monitor = WindowsMonitor()

        # Get all info
        info = monitor.get_all_info()

        # Format output
        logger.info("\nSystem info:")
        logger.info(json.dumps(info, indent=2, default=str))

        # Test async monitoring
        async_monitor = AsyncWindowsMonitor(update_interval=2.0)

        logger.info("\nAsync monitor test (5 seconds)...")
        task = asyncio.create_task(async_monitor.start_monitoring(
            lambda info: logger.info(f"Monitor update: CPU {info['cpu'].get('cpu_percent')}%")
        ))

        await asyncio.sleep(5)

        async_monitor.stop_monitoring()
        await task

        logger.info("\nMonitor test completed")

    # Run test
    asyncio.run(test_monitor())
