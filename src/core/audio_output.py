"""Audio output device selection shared by every playback backend.

A single preference drives three independent backends:
- pygame mixer (TTS / announcements): re-init with ``devicename``
- VLC (music streaming): ``audio_output_device_set("mmdevice", endpoint_id)``
- sounddevice / PortAudio (Sendspin sync player): explicit ``device=`` index

The selection is stored in ``Preferences.output_device`` ("" = system default);
this module keeps the runtime copy and applies it to the backends.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_selected_device: str = ""  # "" = follow the system default


def list_output_devices() -> list[str]:
    """Output device names, deduplicated, preferring WASAPI.

    Every device shows up once per host API (MME/DirectSound/WASAPI/WDM-KS),
    and MME truncates names to 31 chars, so listing everything is unusable.
    Mirrors AudioRecorder.list_microphones for inputs.
    """
    try:
        import sounddevice as sd

        devices = sd.query_devices()
    except Exception as e:
        logger.error(f"Failed to get output device list: {e}")
        return []

    wasapi = None
    try:
        for i, api in enumerate(sd.query_hostapis()):
            if "WASAPI" in api["name"]:
                wasapi = i
                break
    except Exception:
        pass

    def collect(hostapi: Optional[int]) -> list[str]:
        names: list[str] = []
        for d in devices:
            if d["max_output_channels"] <= 0:
                continue
            if hostapi is not None and d["hostapi"] != hostapi:
                continue
            if d["name"] not in names:
                names.append(d["name"])
        return names

    return collect(wasapi) or collect(None)


def resolve_output_device(device_name: Optional[str]) -> Optional[int]:
    """Resolve an output device name to a PortAudio index.

    Returns None for the system default or when the name is not found.
    Every name exists once per host API; the WASAPI entry is preferred so
    the opened device matches the name shown in the tray menu (MME truncates
    names, and DirectSound/WDM-KS would be an arbitrary pick otherwise).
    """
    if not device_name:
        return None
    try:
        import sounddevice as sd

        devices = list(enumerate(sd.query_devices()))
        wasapi = None
        try:
            for i, api in enumerate(sd.query_hostapis()):
                if "WASAPI" in api["name"]:
                    wasapi = i
                    break
        except Exception:
            pass

        fallback = None
        for i, dev in devices:
            if dev["max_output_channels"] <= 0 or dev["name"] != device_name:
                continue
            if wasapi is not None and dev["hostapi"] == wasapi:
                return i
            if fallback is None:
                fallback = i
        if fallback is None:
            logger.warning(f"Specified output device not found: {device_name}, using system default")
        return fallback
    except Exception as e:
        logger.error(f"Failed to resolve output device: {e}")
        return None


def get_selected_device() -> str:
    """Currently selected output device name ("" = system default)."""
    return _selected_device


def apply_output_device(device_name: Optional[str]) -> None:
    """Apply the output selection to the local backends (pygame; VLC at play time).

    device_name "" / None = follow the system default again.
    """
    global _selected_device
    _selected_device = device_name or ""
    _apply_pygame(_selected_device)


def _apply_pygame(device_name: str) -> None:
    """Re-init the shared pygame mixer on the selected device.

    SDL opens output devices by friendly name, which matches the WASAPI
    names listed above. Quitting the mixer stops any playback in progress -
    acceptable for an explicit device switch; unknown names fall back to the
    system default so audio never goes silent.
    """
    try:
        import pygame
    except ImportError:
        return

    try:
        if pygame.mixer.get_init():
            pygame.mixer.quit()
        if device_name:
            try:
                pygame.mixer.init(devicename=device_name)
                logger.info(f"pygame output device: {device_name}")
                return
            except Exception as e:
                logger.warning(
                    f"pygame failed to open output device '{device_name}': {e}, " f"falling back to system default"
                )
        pygame.mixer.init()
        logger.debug("pygame output device: system default")
    except Exception as e:
        logger.warning(f"pygame mixer re-init failed: {e}")


def resolve_endpoint_id(device_name: str) -> Optional[str]:
    """Windows render-endpoint ID for a friendly device name (for VLC mmdevice).

    Render endpoints have flow "0.0.0" in their ID; capture is "0.0.1".
    """
    try:
        from pycaw.pycaw import AudioUtilities

        for d in AudioUtilities.GetAllDevices():
            device_id = getattr(d, "id", None)
            if device_id is None or not str(device_id).startswith("{0.0.0."):
                continue
            if getattr(d, "FriendlyName", None) == device_name:
                return str(device_id)
    except Exception as e:
        logger.debug(f"Endpoint lookup failed: {e}")
    return None
