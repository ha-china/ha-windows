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
import socket
from typing import Dict, List, Optional, Tuple

import psutil
from aioesphomeapi.api_pb2 import (
    EntityCategory,
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
    # NVIDIA GPU sensors (optional, only registered when NVML is available)
    "gpu_name": 40,
    "gpu_temperature": 41,
    "gpu_usage": 42,
    "gpu_memory_usage": 43,
    "gpu_memory_used": 44,
    "gpu_power": 45,
}
GR_GDIOBJECTS = 0
GR_USEROBJECTS = 1

# Dynamic key offset for disk sensors (each disk uses 2 keys: usage% and free GB)
DISK_KEY_OFFSET = 20

# Dynamic key offset for LibreHardwareMonitor sensors (CPU temp, fans, voltages...)
HW_SENSOR_KEY_OFFSET = 100


def _num(section: dict, key: str, default: float = 0) -> float:
    """Read a numeric value from an info section, tolerating bad data."""
    try:
        return float(section.get(key, default))
    except (TypeError, ValueError):
        return float(default)


def _opt_num(section: dict, key: str) -> Optional[float]:
    """Read a numeric value that may legitimately be absent (None -> skip)."""
    value = section.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# Stable key helpers
def _stable_key(name: str, base: int = 0) -> int:
    """Generate a deterministic integer key from a string."""
    h = 0
    for c in name:
        h = (h * 31 + ord(c)) & 0xFFFFF
    return base + (h % 1000)


# ---------------------------------------------------------------------------
# Entity definition rules
#
# One ordered rule list drives ListEntities*Response construction. Order is
# significant: the first matching rule wins, mirroring the historical if/elif
# chain (e.g. the generic "_usage" percentage rule intentionally precedes and
# therefore shadows the more specific GPU rules).
# ---------------------------------------------------------------------------

_M = SensorStateClass.STATE_CLASS_MEASUREMENT
_TI = SensorStateClass.STATE_CLASS_TOTAL_INCREASING
_DIAG = EntityCategory.ENTITY_CATEGORY_DIAGNOSTIC


def _sensor_rule(matcher, **kwargs):
    """Rule producing a numeric sensor definition."""
    def build(meta, object_id, name, icon, key):
        return ListEntitiesSensorResponse(
            object_id=object_id, key=key, name=name, icon=icon, **kwargs
        )
    return (matcher, build)


def _text_rule(matcher, **kwargs):
    """Rule producing a text sensor definition."""
    def build(meta, object_id, name, icon, key):
        return ListEntitiesTextSensorResponse(
            object_id=object_id, key=key, name=name, icon=icon, **kwargs
        )
    return (matcher, build)


def _hw_sensor_rule():
    """LibreHardwareMonitor sensors: unit/device class come from live metadata."""
    def build(meta, object_id, name, icon, key):
        entry = meta.get(object_id) or {}
        unit = entry.get("unit", "")
        device_class = "temperature" if unit == "°C" else None
        return ListEntitiesSensorResponse(
            object_id=object_id,
            key=key,
            name=name,
            icon=icon,
            unit_of_measurement=unit or None,
            accuracy_decimals=1,
            state_class=_M,
            device_class=device_class,
        )
    return (lambda oid, key: key >= HW_SENSOR_KEY_OFFSET, build)


_ENTITY_RULES = (
    _text_rule(lambda oid, key: oid == "version", entity_category=_DIAG),
    _sensor_rule(
        lambda oid, key: oid == "process_memory_mb",
        unit_of_measurement="MB",
        accuracy_decimals=1,
        state_class=_M,
        entity_category=_DIAG,
    ),
    # Percentage sensors (also catches every "<name>_usage" variant)
    _sensor_rule(
        lambda oid, key: oid in ("cpu_usage", "memory_usage", "battery_level")
        or oid.endswith("_usage"),
        unit_of_measurement="%",
        accuracy_decimals=1,
        state_class=_M,
    ),
    # GB sensors; network counters are monotonically increasing totals
    (lambda oid, key: oid in ("memory_free", "network_upload", "network_download")
     or oid.endswith("_free"),
     lambda meta, object_id, name, icon, key: ListEntitiesSensorResponse(
         object_id=object_id, key=key, name=name, icon=icon,
         unit_of_measurement="GB", accuracy_decimals=2,
         state_class=(_TI if object_id.startswith("network_") else _M),
     )),
    _sensor_rule(
        lambda oid, key: oid == "uptime",
        unit_of_measurement="h",
        accuracy_decimals=1,
        state_class=_TI,
    ),
    # Diagnostic count sensors
    _sensor_rule(
        lambda oid, key: oid in ("process_count", "thread_count", "handle_count",
                                 "gdi_count", "user_object_count"),
        accuracy_decimals=0,
        state_class=_M,
        entity_category=_DIAG,
    ),
    _text_rule(lambda oid, key: oid == "gpu_name"),
    _sensor_rule(
        lambda oid, key: oid == "gpu_temperature",
        unit_of_measurement="°C",
        accuracy_decimals=0,
        state_class=_M,
        device_class="temperature",
    ),
    _sensor_rule(
        lambda oid, key: oid == "gpu_memory_used",
        unit_of_measurement="GB",
        accuracy_decimals=2,
        state_class=_M,
    ),
    _sensor_rule(
        lambda oid, key: oid == "gpu_power",
        unit_of_measurement="W",
        accuracy_decimals=1,
        state_class=_M,
    ),
    _hw_sensor_rule(),
)


def _build_entity_response(hardware_meta, object_id, name, icon, key):
    """Construct the ListEntities* response for one entity via the rule table."""
    for matcher, build in _ENTITY_RULES:
        if matcher(object_id, key):
            return build(hardware_meta, object_id, name, icon, key)
    # Default: text sensor for status values (network_status, battery_status...)
    return ListEntitiesTextSensorResponse(object_id=object_id, key=key, name=name, icon=icon)


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
        self._hardware_meta: Dict[str, Dict] = {}
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
                    if addr.family == socket.AF_INET and not addr.address.startswith("127."):
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

    def get_gpu_info(self) -> Optional[Dict]:
        """Get NVIDIA GPU info via NVML.

        Returns None on machines without an NVIDIA GPU (or without the
        driver / nvidia-ml-py); no entities are registered in that case.
        """
        try:
            from src.sensors.gpu_monitor import get_gpu_info as nvml_info

            return nvml_info()
        except Exception as e:
            logger.debug(f"GPU info unavailable: {e}")
            return None

    def get_hardware_info(self) -> Dict:
        """Get hardware sensor values via LibreHardwareMonitor.

        Returns {object_id: {"name":..., "icon":..., "unit":..., "value": float}}
        or an empty dict when unavailable (not installed / no driver / no
        admin). CPU temperature, fans and voltages need the ring0 driver.
        """
        try:
            from src.sensors import hardware_monitor as hwm

            values = hwm.read_hardware_sensors()
            if not values:
                return {}
            meta = hwm.get_sensor_meta()

            def unit_for(object_id: str, default_unit: str = "") -> str:
                u = meta.get(object_id, (None, None, None))[2] if not object_id.isdigit() else None
                # family keys like hw_cpu_core_1 -> base meta lookup failed; derive from prefix
                if not u:
                    base = "_".join(object_id.split("_")[:-1])
                    u = meta.get(base, (None, None, ""))[2]
                return u or default_unit

            result: Dict = {}
            for object_id, value in values.items():
                base = "_".join(object_id.split("_")[:-1])
                entry_meta = meta.get(object_id) or meta.get(base) or (object_id, "mdi:gauge", "")
                display_name, icon, unit = entry_meta
                # Humanize family suffix: "CPU Core 1" from hw_cpu_core_1
                suffix = object_id[len(base):].lstrip("_")
                if suffix and not object_id in meta:
                    display_name = f"{display_name} {suffix}"
                result[object_id] = {
                    "name": display_name,
                    "icon": icon,
                    "unit": unit,
                    "value": value,
                }
            return result
        except Exception as e:
            logger.debug(f"Hardware info unavailable: {e}")
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
            "gpu": self.get_gpu_info(),
            "hardware": self.get_hardware_info(),
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

        # NVIDIA GPU sensors - only if NVML is available (graceful on AMD/Intel/no-GPU machines)
        gpu_info = info.get("gpu") or {}
        if gpu_info:
            available.append(("gpu_name", "GPU", "mdi:expansion-card", SENSOR_KEYS["gpu_name"]))
            if gpu_info.get("temperature") is not None:
                available.append(("gpu_temperature", "GPU Temperature", "mdi:thermometer", SENSOR_KEYS["gpu_temperature"]))
            if gpu_info.get("gpu_utilization") is not None:
                available.append(("gpu_usage", "GPU Usage", "mdi:expansion-card", SENSOR_KEYS["gpu_usage"]))
            if gpu_info.get("memory_utilization") is not None:
                available.append(("gpu_memory_usage", "GPU Memory Usage", "mdi:memory", SENSOR_KEYS["gpu_memory_usage"]))
            if gpu_info.get("vram_used_gb") is not None:
                available.append(("gpu_memory_used", "GPU Memory Used", "mdi:memory", SENSOR_KEYS["gpu_memory_used"]))
            if gpu_info.get("power_watts") is not None:
                available.append(("gpu_power", "GPU Power", "mdi:flash", SENSOR_KEYS["gpu_power"]))

        # LibreHardwareMonitor sensors (CPU temp, fans, voltages...) - stable keys
        hw_info = info.get("hardware") or {}
        self._hardware_meta = hw_info
        if hw_info:
            for i, (object_id, entry) in enumerate(hw_info.items()):
                # Use a deterministic key derived from the object_id so that
                # the same sensor always gets the same key across restarts.
                stable_key = _stable_key(object_id, HW_SENSOR_KEY_OFFSET)
                available.append((object_id, entry["name"], entry["icon"], stable_key))

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
            entities.append(_build_entity_response(self._hardware_meta, object_id, name, icon, key))
        entities.append(ListEntitiesDoneResponse())
        return entities

    def get_esp_sensor_states(self, **extra_states) -> List:
        """
        Get current ESPHome sensor states

        Args:
            **extra_states: Additional text states (e.g., command_result)

        Returns:
            List of state responses
        """
        if not self._entity_map:
            self.discover_esp_entities()

        states = []
        info = self.get_all_info()

        def emit(object_id: str, value) -> None:
            """Append a sensor state if the entity exists and value is known."""
            if object_id not in self._entity_map or value is None:
                return
            _, _, key = self._entity_map[object_id]
            if isinstance(value, str):
                states.append(TextSensorStateResponse(key=key, state=value))
            else:
                states.append(SensorStateResponse(key=key, state=float(value)))

        # Version
        try:
            from src import __version__

            version = __version__
        except Exception:
            version = "unknown"
        emit("version", version)

        # Fixed numeric sensors, in stable order. Extractors return None to
        # skip the update (e.g. no battery present).
        fixed_numeric = (
            ("cpu_usage", lambda i: _num(i.get("cpu", {}), "cpu_percent")),
            ("memory_usage", lambda i: _num(i.get("memory", {}), "percent")),
            ("memory_free", lambda i: round(_num(i.get("memory", {}), "available") / (1024**3), 1)),
            ("battery_level", lambda i: _num(i["battery"], "percent") if i.get("battery") else None),
            ("network_upload", lambda i: _num(i.get("network", {}), "bytes_sent_gb")),
            ("network_download", lambda i: _num(i.get("network", {}), "bytes_recv_gb")),
            ("uptime", lambda i: _num(i.get("system", {}), "uptime_hours")),
            ("process_count", lambda i: _num(i.get("system", {}), "process_count")),
            ("process_memory_mb", lambda i: _num(i.get("process", {}), "rss_mb")),
            ("thread_count", lambda i: _num(i.get("process", {}), "thread_count")),
            ("handle_count", lambda i: _opt_num(i.get("process", {}), "handle_count")),
            ("gdi_count", lambda i: _opt_num(i.get("process", {}), "gdi_count")),
            ("user_object_count", lambda i: _opt_num(i.get("process", {}), "user_object_count")),
        )
        for object_id, extractor in fixed_numeric:
            emit(object_id, extractor(info))

        # Disk sensors - usage% and free GB for each drive
        disk_info = info.get("disk", {})
        for mount_point, disk_data in disk_info.items():
            mount_id = self._mount_point_to_object_id(mount_point)
            emit(f"disk_{mount_id}_usage", _num(disk_data, "percent"))
            emit(f"disk_{mount_id}_free", _num(disk_data, "free_gb"))

        # Text sensors
        battery = info.get("battery")
        emit(
            "battery_status",
            ("Charging" if battery.get("power_plugged") else "Discharging") if battery else None,
        )
        emit("ip_address", info.get("network", {}).get("ip_address", ""))
        emit("boot_time", info.get("system", {}).get("boot_time_iso", ""))

        # NVIDIA GPU sensors (only present when NVML is available)
        gpu_info = info.get("gpu") or {}
        emit("gpu_name", str(gpu_info.get("name", "unknown")))
        for object_id, field in [
            ("gpu_temperature", "temperature"),
            ("gpu_usage", "gpu_utilization"),
            ("gpu_memory_usage", "memory_utilization"),
            ("gpu_memory_used", "vram_used_gb"),
            ("gpu_power", "power_watts"),
        ]:
            if gpu_info.get(field) is not None:
                emit(object_id, float(gpu_info[field]))

        # LibreHardwareMonitor sensors (dynamic keys >= HW_SENSOR_KEY_OFFSET)
        hw_info = info.get("hardware") or {}
        self._hardware_meta = hw_info or self._hardware_meta
        for object_id, entry in hw_info.items():
            if object_id in self._entity_map and entry.get("value") is not None:
                emit(object_id, float(entry["value"]))

        # Extra states (command_result, voice_status, etc.)
        for entity_name, state_value in extra_states.items():
            emit(entity_name, str(state_value))

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
