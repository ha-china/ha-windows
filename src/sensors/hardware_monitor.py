"""Hardware sensor monitoring via LibreHardwareMonitor (HardwareMonitor package).

Fully optional and fault tolerant:
- Not installed / import fails  -> no entities
- No admin / no ring0 driver    -> partial entities (GPU temp, clocks, loads)
- Full driver access            -> CPU temp, fans, voltages, motherboard sensors

Every sensor read is individually guarded; whatever is unavailable simply
does not show up, mirroring the battery/GPU-NVML pattern.
"""

import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# Sensor names considered meaningful for Home Assistant reporting.
# (sensor_type, name_exact) for unique sensors; name_prefix for families.
_UNIQUE_SENSORS = [
    # type, exact name, object_id, display name, icon, unit
    ("Temperature", "CPU Package", "hw_cpu_temperature", "CPU Temperature", "mdi:thermometer", "°C"),
    ("Temperature", "GPU Core", "hw_gpu_temperature", "GPU Temperature (LHW)", "mdi:thermometer", "°C"),
    ("Temperature", "GPU Hot Spot", "hw_gpu_hotspot", "GPU Hot Spot", "mdi:thermometer", "°C"),
    ("Clock", "GPU Core", "hw_gpu_clock", "GPU Clock", "mdi:speedometer", "MHz"),
    ("Clock", "GPU Memory", "hw_gpu_mem_clock", "GPU Memory Clock", "mdi:speedometer", "MHz"),
    ("Power", "CPU Package", "hw_cpu_power", "CPU Power", "mdi:flash", "W"),
    ("Power", "GPU Package", "hw_gpu_power", "GPU Power (LHW)", "mdi:flash", "W"),
    ("Load", "CPU Total", "hw_cpu_total_load", "CPU Total Load (LHW)", "mdi:cpu-64-bit", "%"),
    ("Load", "CPU Core Max", "hw_cpu_core_max", "CPU Core Max Load", "mdi:cpu-64-bit", "%"),
    ("Data", "Memory Used", "hw_mem_used", "Memory Used (LHW)", "mdi:memory", "GB"),
    ("Data", "Memory Available", "hw_mem_available", "Memory Available (LHW)", "mdi:memory", "GB"),
    ("SmallData", "GPU Memory Used", "hw_gpu_mem_used_mb", "GPU Memory Used (LHW)", "mdi:memory", "MB"),
    ("SmallData", "GPU Memory Free", "hw_gpu_mem_free_mb", "GPU Memory Free (LHW)", "mdi:memory", "MB"),
    ("Voltage", "GPU Core Voltage", "hw_gpu_voltage", "GPU Core Voltage", "mdi:sine-wave", "V"),
]

# Family sensors: first instance of each type/name prefix per hardware
_FAMILY_PREFIXES = [
    # type, name prefix, object_id base, display base, icon, unit
    ("Load", "CPU Core #", "hw_cpu_core", "CPU Core", "mdi:cpu-64-bit", "%"),
    ("Temperature", "Temperature #", "hw_mb_temp", "Motherboard Temp", "mdi:thermometer", "°C"),
    ("Fan", "Fan #", "hw_fan", "Fan", "mdi:fan", "RPM"),
    ("Voltage", "Voltage #", "hw_voltage", "Voltage", "mdi:sine-wave", "V"),
    ("Clock", "CPU Core #", "hw_cpu_core_clock", "CPU Core Clock", "mdi:speedometer", "MHz"),
]

_lock = threading.Lock()
_computer = None
_init_tried = False


def _try_init():
    """Initialize the LHW Computer object once (thread-safe)."""
    global _computer, _init_tried
    with _lock:
        if _init_tried:
            return _computer is not None
        _init_tried = True
        try:
            # The package logs noisy import-time warnings about admin rights
            # and the PawnIO driver; we handle both cases gracefully below,
            # so silence its logger before importing.
            import logging as _logging

            _logging.getLogger("HardwareMonitor").setLevel(_logging.CRITICAL)
            _logging.getLogger("PyHardwareMonitor").setLevel(_logging.CRITICAL)

            from HardwareMonitor import Hardware

            computer = Hardware.Computer()
            computer.IsCpuEnabled = True
            computer.IsGpuEnabled = True
            computer.IsMemoryEnabled = True
            computer.IsMotherboardEnabled = True
            computer.IsStorageEnabled = False  # SMART via driver only, keep light
            computer.IsControllerEnabled = False
            computer.IsNetworkEnabled = False
            computer.IsPsuEnabled = False
            computer.IsBatteryEnabled = False  # psutil already covers battery
            computer.Open()
            _computer = computer
            logger.info("LibreHardwareMonitor initialized")
        except ImportError:
            logger.debug("HardwareMonitor package not installed, hardware sensors disabled")
        except Exception as e:
            logger.debug(f"LibreHardwareMonitor unavailable: {e}")
    return _computer is not None


def hardware_monitor_available() -> bool:
    """Return True if the LHW engine could be initialized."""
    return _try_init()


def read_hardware_sensors() -> Optional[dict]:
    """Read meaningful sensors once.

    Returns a dict {object_id: float} or None when the engine is
    unavailable. Individual failures degrade to missing keys.
    """
    if not _try_init():
        return None

    result: dict = {}
    try:
        from HardwareMonitor import Hardware

        with _lock:
            for hw in _computer.Hardware:
                try:
                    hw.Update()
                except Exception as e:
                    logger.debug(f"HardwareMonitor update failed for {hw.Name}: {e}")
                    continue
                for sensor in hw.Sensors:
                    _collect(sensor, hw, result)
                for sub in getattr(hw, "SubHardware", []):
                    try:
                        sub.Update()
                    except Exception:
                        continue
                    for sensor in sub.Sensors:
                        _collect(sensor, sub, result)
    except Exception as e:
        logger.debug(f"HardwareMonitor read failed: {e}")
    return result or None


def _sensor_type_name(sensor) -> str:
    try:
        return str(sensor.SensorType).split(".")[-1].split(" ")[0]
    except Exception:
        return ""


def _collect(sensor, hw, result: dict) -> None:
    """Match a single LHW sensor against the reporting whitelist."""
    try:
        value = sensor.Value
        if value is None:
            return
        sensor_type = _sensor_type_name(sensor)
        name = str(sensor.Name)

        # Power/Voltage/Fan return 0.0 when the ring0 driver is absent (not a
        # real reading); skip them to avoid polluting the entity list.
        if sensor_type in ("Power", "Voltage", "Fan") and float(value) == 0.0:
            return

        for stype, exact, object_id, _dn, _icon, _unit in _UNIQUE_SENSORS:
            if sensor_type == stype and name == exact:
                result[object_id] = float(value)
                return

        for stype, prefix, base, _dn, _icon, _unit in _FAMILY_PREFIXES:
            if sensor_type == stype and name.startswith(prefix):
                suffix = name[len(prefix):].strip()
                key = f"{base}_{suffix.lower()}" if suffix else base
                # keep first hardware's instance to avoid duplicates
                if key not in result:
                    result[key] = float(value)
                return
    except Exception:
        pass


def get_sensor_meta() -> dict:
    """Return {object_id: (display_name, icon, unit)} for whitelisted sensors."""
    meta: dict = {}
    for _stype, exact, object_id, dn, icon, unit in _UNIQUE_SENSORS:
        meta[object_id] = (dn, icon, unit)
    for _stype, _prefix, base, dn, icon, unit in _FAMILY_PREFIXES:
        meta[base] = (dn, icon, unit)  # family entries updated dynamically
    return meta
