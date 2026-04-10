"""
Windows System Monitor Module

Monitors Windows system status using psutil.
Also provides ESPHome entity definitions and states for server mode.
"""

import asyncio
import ctypes
import logging
import platform
import re
from typing import Dict, List, Optional, Tuple

import psutil
from aioesphomeapi.api_pb2 import (
    ListEntitiesDoneResponse,
    ListEntitiesSensorResponse,
    ListEntitiesTextSensorResponse,
    SensorStateResponse,
    TextSensorStateResponse,
    SensorStateClass,
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
# Keys 1-10 reserved for basic sensors, 20+ for dynamic disk sensors
SENSOR_KEYS = {
    "version": 0,
    "cpu_usage": 1,
    "memory_usage": 2,
    "memory_free": 7,
    "battery_status": 4,
    "battery_level": 5,
    "ip_address": 6,
    "boot_time": 8,
    "uptime": 9,
    "process_count": 10,
    "network_upload": 11,
    "network_download": 12,
    "process_memory_mb": 13,
    "thread_count": 14,
    "handle_count": 15,
    "gdi_count": 16,
    "user_object_count": 17,
}

GR_GDIOBJECTS = 0
GR_USEROBJECTS = 1

# Dynamic key offset for disk sensors (each disk uses 2 keys: usage% and free GB)
DISK_KEY_OFFSET = 20


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
        psutil.cpu_percent(interval=None)
        logger.info("Windows monitor initialized")

    @staticmethod
    def _mount_point_to_object_id(mount_point: str) -> str:
        """Convert mount point to safe object id suffix."""
        if not mount_point:
            return "root"

        normalized = mount_point.strip().lower().replace('\\', '/').rstrip('/')
        if not normalized:
            return "root"

        if normalized == '/':
            return "root"

        if len(normalized) == 2 and normalized[1] == ':':
            return normalized[0]

        # Keep only alphanumerics for stable entity ids
        return re.sub(r'[^a-z0-9]+', '_', normalized).strip('_') or "disk"

    @staticmethod
    def _mount_point_display_name(mount_point: str) -> str:
        """Human-readable mount point label for entity names."""
        if not mount_point or mount_point == '/':
            return '/'

        normalized = mount_point.rstrip('\\/')
        if len(normalized) == 2 and normalized[1] == ':':
            return normalized[0].upper()
        return normalized or '/'

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
            cpu_percent = psutil.cpu_percent(interval=None)
            cpu_count = psutil.cpu_count()
            cpu_freq = psutil.cpu_freq()

            return {
                "cpu_percent": cpu_percent,
                "cpu_count": cpu_count,
                "cpu_freq_current": cpu_freq.current if cpu_freq else None,
                "cpu_freq_max": cpu_freq.max if cpu_freq else None,
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
                "total": mem.total,
                "available": mem.available,
                "used": mem.used,
                "free": mem.free,
                "percent": mem.percent,
            }
        except Exception as e:
            logger.error(f"Failed to get memory info: {e}")
            return {}

    def get_disk_info(self, fixed_only: bool = True) -> Dict:
        """
        Get disk information

        Args:
            fixed_only: If True, only return fixed drives (exclude removable/cdrom)

        Returns:
            Dict: Disk information (all partitions)
        """
        try:
            disk_info = {}

            for partition in psutil.disk_partitions():
                # Skip cdrom and empty filesystem
                if "cdrom" in partition.opts or partition.fstype == "":
                    continue

                # Skip removable drives if fixed_only
                if fixed_only and "removable" in partition.opts:
                    continue

                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    disk_info[partition.mountpoint] = {
                        "device": partition.device,
                        "fstype": partition.fstype,
                        "total": usage.total,
                        "used": usage.used,
                        "free": usage.free,
                        "percent": usage.percent,
                        "free_gb": round(usage.free / (1024**3), 1),
                        "total_gb": round(usage.total / (1024**3), 1),
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
                "percent": battery.percent,
                "power_plugged": battery.power_plugged,
                "secsleft": battery.secsleft,
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

            # Get IP address
            ip_address = ""
            for iface, addrs in psutil.net_if_addrs().items():
                for addr in addrs:
                    # IPv4 address, not loopback
                    if addr.family == 2 and not addr.address.startswith("127."):
                        ip_address = addr.address
                        break
                if ip_address:
                    break

            return {
                "bytes_sent": net_io.bytes_sent,
                "bytes_recv": net_io.bytes_recv,
                "bytes_sent_gb": round(net_io.bytes_sent / (1024**3), 2),
                "bytes_recv_gb": round(net_io.bytes_recv / (1024**3), 2),
                "packets_sent": net_io.packets_sent,
                "packets_recv": net_io.packets_recv,
                "connections": net_connections,
                "ip_address": ip_address,
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
            import time
            from datetime import datetime

            uptime_seconds = time.time() - self._boot_time
            uptime_hours = round(uptime_seconds / 3600, 1)
            boot_datetime = datetime.fromtimestamp(self._boot_time)

            return {
                "system": platform.system(),
                "release": platform.release(),
                "version": platform.version(),
                "machine": platform.machine(),
                "processor": platform.processor(),
                "hostname": platform.node(),
                "boot_time": self._boot_time,
                "boot_time_iso": boot_datetime.isoformat(),
                "uptime_seconds": uptime_seconds,
                "uptime_hours": uptime_hours,
                "process_count": len(psutil.pids()),
            }
        except Exception as e:
            logger.error(f"Failed to get system info: {e}")
            return {}

    def get_process_info(self) -> Dict:
        """Get current process diagnostics for leak tracking."""
        try:
            process = psutil.Process()
            memory_info = process.memory_info()

            try:
                handle_count = process.num_handles()
            except (AttributeError, NotImplementedError):
                handle_count = None

            gdi_count = None
            user_object_count = None
            if platform.system() == "Windows":
                try:
                    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                    user32 = ctypes.WinDLL("user32", use_last_error=True)
                    process_handle = kernel32.GetCurrentProcess()
                    gdi_count = user32.GetGuiResources(process_handle, GR_GDIOBJECTS)
                    user_object_count = user32.GetGuiResources(process_handle, GR_USEROBJECTS)
                except Exception as e:
                    logger.debug(f"Failed to get GUI resource counts: {e}")

            return {
                "rss_mb": round(memory_info.rss / (1024 ** 2), 1),
                "thread_count": process.num_threads(),
                "handle_count": handle_count,
                "gdi_count": gdi_count,
                "user_object_count": user_object_count,
            }
        except Exception as e:
            logger.error(f"Failed to get process info: {e}")
            return {}

    def get_all_info(self) -> Dict:
        """
        Get all information

        Returns:
            Dict: All system information
        """
        return {
            "cpu": self.get_cpu_info(),
            "memory": self.get_memory_info(),
            "disk": self.get_disk_info(),
            "battery": self.get_battery_info(),
            "network": self.get_network_info(),
            "system": self.get_system_info(),
            "process": self.get_process_info(),
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

        # Version - always available (first entity, diagnostic category)
        available.append(("version", "Version", "mdi:tag", SENSOR_KEYS["version"]))

        # CPU - always available
        available.append(("cpu_usage", "CPU Usage", "mdi:cpu-64-bit", SENSOR_KEYS["cpu_usage"]))

        # Memory usage % and free GB
        available.append(("memory_usage", "Memory Usage", "mdi:memory", SENSOR_KEYS["memory_usage"]))
        available.append(("memory_free", "Memory Free", "mdi:memory", SENSOR_KEYS["memory_free"]))

        # Disk sensors - for each fixed drive, add usage% and free GB
        disk_info = info.get("disk", {})
        disk_key = DISK_KEY_OFFSET
        for mount_point in sorted(disk_info.keys()):
            mount_id = self._mount_point_to_object_id(mount_point)
            mount_name = self._mount_point_display_name(mount_point)

            # Disk usage %
            usage_id = f"disk_{mount_id}_usage"
            available.append((usage_id, f"Disk {mount_name} Usage", "mdi:harddisk", disk_key))
            disk_key += 1

            # Disk free GB
            free_id = f"disk_{mount_id}_free"
            available.append((free_id, f"Disk {mount_name} Free", "mdi:harddisk", disk_key))
            disk_key += 1

        # Battery - only if battery info available
        if info.get("battery"):
            available.append(("battery_status", "Battery Status", "mdi:battery", SENSOR_KEYS["battery_status"]))
            available.append(("battery_level", "Battery Level", "mdi:battery-90", SENSOR_KEYS["battery_level"]))

        # Network - always available
        available.append(("ip_address", "IP Address", "mdi:ip-network", SENSOR_KEYS["ip_address"]))
        available.append(("network_upload", "Network Upload", "mdi:upload", SENSOR_KEYS["network_upload"]))
        available.append(("network_download", "Network Download", "mdi:download", SENSOR_KEYS["network_download"]))

        # System info - always available
        available.append(("boot_time", "Boot Time", "mdi:clock-start", SENSOR_KEYS["boot_time"]))
        available.append(("uptime", "Uptime", "mdi:timer-outline", SENSOR_KEYS["uptime"]))
        available.append(("process_count", "Process Count", "mdi:application-cog", SENSOR_KEYS["process_count"]))
        available.append(("process_memory_mb", "Process RSS", "mdi:memory", SENSOR_KEYS["process_memory_mb"]))
        available.append(("thread_count", "Process Threads", "mdi:table-column", SENSOR_KEYS["thread_count"]))

        process_info = info.get("process", {})
        if process_info.get("handle_count") is not None:
            available.append(("handle_count", "Process Handles", "mdi:link-box-variant", SENSOR_KEYS["handle_count"]))
        if process_info.get("gdi_count") is not None:
            available.append(("gdi_count", "Process GDI Objects", "mdi:vector-square", SENSOR_KEYS["gdi_count"]))
        if process_info.get("user_object_count") is not None:
            available.append(("user_object_count", "Process USER Objects", "mdi:application-outline", SENSOR_KEYS["user_object_count"]))

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
            # Import EntityCategory for diagnostic entities
            from aioesphomeapi.api_pb2 import EntityCategory

            # Version sensor (diagnostic category)
            if object_id == "version":
                sensor = ListEntitiesTextSensorResponse(
                    object_id=object_id,
                    key=key,
                    name=name,
                    icon=icon,
                    entity_category=EntityCategory.ENTITY_CATEGORY_DIAGNOSTIC,
                )
            elif object_id == "process_memory_mb":
                sensor = ListEntitiesSensorResponse(
                    object_id=object_id,
                    key=key,
                    name=name,
                    icon=icon,
                    unit_of_measurement="MB",
                    accuracy_decimals=1,
                    state_class=SensorStateClass.STATE_CLASS_MEASUREMENT,
                    entity_category=EntityCategory.ENTITY_CATEGORY_DIAGNOSTIC,
                )
            # Percentage sensors
            elif object_id in ("cpu_usage", "memory_usage", "battery_level") or object_id.endswith("_usage"):
                sensor = ListEntitiesSensorResponse(
                    object_id=object_id,
                    key=key,
                    name=name,
                    icon=icon,
                    unit_of_measurement="%",
                    accuracy_decimals=1,
                    state_class=SensorStateClass.STATE_CLASS_MEASUREMENT,
                )
            # GB sensors (memory free, disk free, network upload/download)
            elif object_id in ("memory_free", "network_upload", "network_download") or object_id.endswith("_free"):
                sensor = ListEntitiesSensorResponse(
                    object_id=object_id,
                    key=key,
                    name=name,
                    icon=icon,
                    unit_of_measurement="GB",
                    accuracy_decimals=2,
                    state_class=(
                        SensorStateClass.STATE_CLASS_TOTAL_INCREASING
                        if object_id.startswith("network_")
                        else SensorStateClass.STATE_CLASS_MEASUREMENT
                    ),
                )
            # Hours sensor (uptime)
            elif object_id == "uptime":
                sensor = ListEntitiesSensorResponse(
                    object_id=object_id,
                    key=key,
                    name=name,
                    icon=icon,
                    unit_of_measurement="h",
                    accuracy_decimals=1,
                    state_class=SensorStateClass.STATE_CLASS_TOTAL_INCREASING,
                )
            # Count sensor (process_count)
            elif object_id in ("process_count", "thread_count", "handle_count", "gdi_count", "user_object_count"):
                sensor = ListEntitiesSensorResponse(
                    object_id=object_id,
                    key=key,
                    name=name,
                    icon=icon,
                    accuracy_decimals=0,
                    state_class=SensorStateClass.STATE_CLASS_MEASUREMENT,
                    entity_category=EntityCategory.ENTITY_CATEGORY_DIAGNOSTIC,
                )
            else:
                # Text sensor for status values (network_status, battery_status, boot_time)
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

        # Version
        if "version" in self._entity_map:
            try:
                from src import __version__

                version = __version__
            except Exception:
                version = "unknown"
            _, _, key = self._entity_map["version"]
            states.append(TextSensorStateResponse(key=key, state=version))

        # CPU usage
        if "cpu_usage" in self._entity_map:
            cpu_info = info.get("cpu", {})
            cpu_percent = cpu_info.get("cpu_percent", 0)
            _, _, key = self._entity_map["cpu_usage"]
            states.append(SensorStateResponse(key=key, state=float(cpu_percent)))

        # Memory usage %
        if "memory_usage" in self._entity_map:
            mem_info = info.get("memory", {})
            mem_percent = mem_info.get("percent", 0)
            _, _, key = self._entity_map["memory_usage"]
            states.append(SensorStateResponse(key=key, state=float(mem_percent)))

        # Memory free GB
        if "memory_free" in self._entity_map:
            mem_info = info.get("memory", {})
            mem_available = mem_info.get("available", 0)
            mem_free_gb = round(mem_available / (1024**3), 1)
            _, _, key = self._entity_map["memory_free"]
            states.append(SensorStateResponse(key=key, state=float(mem_free_gb)))

        # Disk sensors - usage% and free GB for each drive
        disk_info = info.get("disk", {})
        for mount_point, disk_data in disk_info.items():
            mount_id = self._mount_point_to_object_id(mount_point)

            # Disk usage %
            usage_id = f"disk_{mount_id}_usage"
            if usage_id in self._entity_map:
                _, _, key = self._entity_map[usage_id]
                states.append(SensorStateResponse(key=key, state=float(disk_data.get("percent", 0))))

            # Disk free GB
            free_id = f"disk_{mount_id}_free"
            if free_id in self._entity_map:
                _, _, key = self._entity_map[free_id]
                states.append(SensorStateResponse(key=key, state=float(disk_data.get("free_gb", 0))))

        # Battery status
        if "battery_status" in self._entity_map:
            battery_info = info.get("battery")
            if battery_info:
                status = "Charging" if battery_info.get("power_plugged") else "Discharging"
                _, _, key = self._entity_map["battery_status"]
                states.append(TextSensorStateResponse(key=key, state=status))

        # Battery level
        if "battery_level" in self._entity_map:
            battery_info = info.get("battery")
            if battery_info:
                _, _, key = self._entity_map["battery_level"]
                states.append(SensorStateResponse(key=key, state=float(battery_info.get("percent", 0))))

        # IP Address
        if "ip_address" in self._entity_map:
            net_info = info.get("network", {})
            ip = net_info.get("ip_address", "")
            _, _, key = self._entity_map["ip_address"]
            states.append(TextSensorStateResponse(key=key, state=ip))

        # Network upload (GB)
        if "network_upload" in self._entity_map:
            net_info = info.get("network", {})
            _, _, key = self._entity_map["network_upload"]
            states.append(SensorStateResponse(key=key, state=float(net_info.get("bytes_sent_gb", 0))))

        # Network download (GB)
        if "network_download" in self._entity_map:
            net_info = info.get("network", {})
            _, _, key = self._entity_map["network_download"]
            states.append(SensorStateResponse(key=key, state=float(net_info.get("bytes_recv_gb", 0))))

        # Boot time (ISO format)
        if "boot_time" in self._entity_map:
            sys_info = info.get("system", {})
            _, _, key = self._entity_map["boot_time"]
            states.append(TextSensorStateResponse(key=key, state=sys_info.get("boot_time_iso", "")))

        # Uptime (hours)
        if "uptime" in self._entity_map:
            sys_info = info.get("system", {})
            _, _, key = self._entity_map["uptime"]
            states.append(SensorStateResponse(key=key, state=float(sys_info.get("uptime_hours", 0))))

        # Process count
        if "process_count" in self._entity_map:
            sys_info = info.get("system", {})
            _, _, key = self._entity_map["process_count"]
            states.append(SensorStateResponse(key=key, state=float(sys_info.get("process_count", 0))))

        # Process memory (MB)
        if "process_memory_mb" in self._entity_map:
            process_info = info.get("process", {})
            _, _, key = self._entity_map["process_memory_mb"]
            states.append(SensorStateResponse(key=key, state=float(process_info.get("rss_mb", 0))))

        # Thread count
        if "thread_count" in self._entity_map:
            process_info = info.get("process", {})
            _, _, key = self._entity_map["thread_count"]
            states.append(SensorStateResponse(key=key, state=float(process_info.get("thread_count", 0))))

        # Handle count
        if "handle_count" in self._entity_map:
            process_info = info.get("process", {})
            handle_count = process_info.get("handle_count")
            if handle_count is not None:
                _, _, key = self._entity_map["handle_count"]
                states.append(SensorStateResponse(key=key, state=float(handle_count)))

        if "gdi_count" in self._entity_map:
            process_info = info.get("process", {})
            gdi_count = process_info.get("gdi_count")
            if gdi_count is not None:
                _, _, key = self._entity_map["gdi_count"]
                states.append(SensorStateResponse(key=key, state=float(gdi_count)))

        if "user_object_count" in self._entity_map:
            process_info = info.get("process", {})
            user_object_count = process_info.get("user_object_count")
            if user_object_count is not None:
                _, _, key = self._entity_map["user_object_count"]
                states.append(SensorStateResponse(key=key, state=float(user_object_count)))

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
        task = asyncio.create_task(
            async_monitor.start_monitoring(
                lambda info: logger.info(f"Monitor update: CPU {info['cpu'].get('cpu_percent')}%")
            )
        )

        await asyncio.sleep(5)

        async_monitor.stop_monitoring()
        await task

        logger.info("\nMonitor test completed")

    # Run test
    asyncio.run(test_monitor())
