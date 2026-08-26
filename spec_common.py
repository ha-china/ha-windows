# -*- mode: python ; coding: utf-8 -*-
"""Shared PyInstaller configuration for both one-file and one-dir builds.

Both HomeAssistantWindows.spec and HomeAssistantWindows_dir.spec import this
module so the two build targets can never drift apart again.

Rules:
- NEVER exclude numpy.* submodules: numpy 2.x imports numpy.version eagerly
  in __init__ (breaking frozen builds) and lazy-loads the rest.
- UPX stays disabled: a UPX-compressed python DLL breaks one-file mode
  ("Failed to load Python DLL") when extracted to %TEMP%.
"""

from PyInstaller.utils.hooks import (
    collect_all,
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

# ---------------------------------------------------------------- excludes
EXCLUDES = [
    'matplotlib',
    'pandas',
    'scipy',
    'pytest',
    'IPython',
    'jupyter',
    'win10toast',
]

# ---------------------------------------------------------------- data files
# Only runtime data: wake word models and UI sounds. Source code itself lives
# in the PYZ archive, so bundling the whole src/ tree is unnecessary.
DATAS = [
    ('src/wakewords', 'src/wakewords'),
    ('src/sounds', 'src/sounds'),
]
# NOTE: packages handled by collect_all() below (aioesphomeapi, pycaw, comtypes,
# pymicro_wakeword, pyopen_wakeword, pygame, orjson, mashumaro, HardwareMonitor)
# must NOT be added here again - that would duplicate their data files.
for _pkg in [
    'sounddevice',
    'webrtcvad',
    'zeroconf',
    'ifaddr',
    'PIL',
    'pystray',
    'windows_toasts',
    'aiosendspin',
    'typing_extensions',
]:
    DATAS += collect_data_files(_pkg, include_py_files=False)

# ---------------------------------------------------------------- binaries
BINARIES = []
for _pkg in [
    'sounddevice',
    'webrtcvad',
    'zeroconf',
    'ifaddr',
    'PIL',
    'pystray',
]:
    BINARIES += collect_dynamic_libs(_pkg)

# Packages collected in full (datas + binaries + hiddenimports)
for _pkg in [
    'aioesphomeapi',
    'pycaw',
    'comtypes',
    'pymicro_wakeword',  # tensorflowlite_c.dll
    'pyopen_wakeword',
    'pygame',  # SDL2_mixer.dll etc - audio playback/volume backend
    'orjson',  # compiled .pyd, must be collected
    'mashumaro',
    'HardwareMonitor',  # LibreHardwareMonitor .NET DLLs in lib/
]:
    _ret = collect_all(_pkg)
    DATAS += _ret[0]
    BINARIES += _ret[1]

# ---------------------------------------------------------------- hidden imports
HIDDEN_IMPORTS = [
    # third-party
    'windows_toasts',
    'pycaw',
    'comtypes',
    'pystray',
    'aioesphomeapi',
    'aiosendspin',
    'mashumaro',
    'orjson',
    'typing_extensions',
    'sounddevice',
    'numpy',
    'psutil',
    'pynvml',
    'HardwareMonitor',
    'pymicro_wakeword',
    'pyopen_wakeword',
    'webrtcvad',
    'zeroconf',
    'PIL',
    'pygame',
    'pygame.mixer',
    'pygame.mixer_music',
    # aiohttp stack (implicit aioesphomeapi/aiosendspin deps)
    'aiohttp',
    'yarl',
    'multidict',
    'idna',
    'frozenlist',
    'aiosignal',
    # misc
    'ifaddr',
    'winsound',
    'ctypes',
    'ctypes.wintypes',
    # src modules
    'src.i18n',
    'src.core.mdns_discovery',
    'src.core.esphome_protocol',
    'src.core.va_conversation',
    'src.core.media_playback',
    'src.core.entity_registry',
    'src.ui.system_tray_icon',
    'src.ui.main_window',
    'src.voice.audio_recorder',
    'src.voice.mpv_player',
    'src.voice.wake_word',
    'src.voice.vad',
    'src.commands.command_executor',
    'src.commands.system_commands',
    'src.commands.media_commands',
    'src.commands.audio_commands',
    'src.sensors.windows_monitor',
    'src.notify.announcement',
    'src.notify.toast_notification',
    'src.notify.service_entity',
    'src.autostart',
    'src.platforms',
    'src.platforms.base',
    'src.platforms.windows',
]

# Dynamic imports that static analysis cannot see. Packages already covered by
# collect_all() above are intentionally NOT repeated here.
for _pkg in [
    'sounddevice',
    'webrtcvad',
    'zeroconf',
    'ifaddr',
    'PIL',
    'pystray',
    'windows_toasts',
    'aiosendspin',
    'aiohttp',
    'yarl',
    'multidict',
    'idna',
    'typing_extensions',
]:
    HIDDEN_IMPORTS += collect_submodules(_pkg)
