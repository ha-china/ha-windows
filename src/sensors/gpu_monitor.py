"""NVIDIA GPU monitoring via NVML (nvidia-ml-py).

Fully optional: on machines without an NVIDIA GPU (or without the driver,
or without the nvidia-ml-py package) every call degrades to None / empty and
no entities are registered - the same pattern as the battery sensors.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy NVML state: None = not tried yet, False = unavailable, True = initialized
_nvml_ready = None
_gpu_count = 0


def _try_init() -> bool:
    """Try to initialize NVML once; cache the result."""
    global _nvml_ready, _gpu_count
    if _nvml_ready is not None:
        return _nvml_ready
    try:
        import warnings as _w

        with _w.catch_warnings():
            _w.simplefilter("ignore", FutureWarning)
            import pynvml  # noqa: PLC0415 - optional dependency

        pynvml.nvmlInit()
        _gpu_count = pynvml.nvmlDeviceGetCount()
        _nvml_ready = True
        logger.info(f"NVML initialized, {_gpu_count} NVIDIA GPU(s) found")
    except ImportError:
        _nvml_ready = False
        logger.debug("nvidia-ml-py not installed, GPU sensors disabled")
    except Exception as e:
        _nvml_ready = False
        logger.debug(f"NVML unavailable (no NVIDIA GPU or driver): {e}")
    return _nvml_ready


def gpu_available() -> bool:
    """Return True if an NVIDIA GPU is readable."""
    return _try_init() and _gpu_count > 0


def get_gpu_info() -> Optional[dict]:
    """Get primary GPU info via NVML.

    Returns None when NVML is unavailable (non-NVIDIA machines, missing
    driver, or nvidia-ml-py not installed).
    """
    if not _try_init():
        return None
    try:
        import pynvml

        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        info: dict = {}

        try:
            info["name"] = pynvml.nvmlDeviceGetName(handle)
            if isinstance(info["name"], bytes):
                info["name"] = info["name"].decode("utf-8", "replace")
        except Exception:
            pass

        try:
            driver = pynvml.nvmlSystemGetDriverVersion()
            if isinstance(driver, bytes):
                driver = driver.decode("utf-8", "replace")
            info["driver_version"] = driver
        except Exception:
            pass

        try:
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            info["gpu_utilization"] = util.gpu
            info["memory_utilization"] = util.memory
        except Exception:
            pass

        try:
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            info["vram_total_gb"] = round(mem.total / 2**30, 2)
            info["vram_used_gb"] = round(mem.used / 2**30, 2)
            info["vram_free_gb"] = round(mem.free / 2**30, 2)
        except Exception:
            pass

        try:
            info["temperature"] = pynvml.nvmlDeviceGetTemperature(
                handle, pynvml.NVML_TEMPERATURE_GPU
            )
        except Exception:
            pass

        try:
            info["power_watts"] = round(pynvml.nvmlDeviceGetPowerUsage(handle) / 1000, 1)
        except Exception:
            pass

        return info if info else None
    except Exception as e:
        logger.debug(f"NVML query failed: {e}")
        return None
