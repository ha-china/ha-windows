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
DATAS = [('src', 'src')]
for _pkg in [
    'aioesphomeapi',
    'pymicro_wakeword',
    'pyopen_wakeword',
    'sounddevice',
    'webrtcvad',
    'zeroconf',
    'ifaddr',
    'comtypes',
    'PIL',
    'pystray',
    'windows_toasts',
    'aiosendspin',
    'mashumaro',
    'orjson',
    'typing_extensions',
]:
    DATAS += collect_data_files(_pkg, include_py_files=False)

# ---------------------------------------------------------------- binaries
BINARIES = []
for _pkg in [
    'aioesphomeapi',
    'pymicro_wakeword',
    'pyopen_wakeword',
    'sounddevice',
    'webrtcvad',
    'zeroconf',
    'ifaddr',
    'comtypes',
    'PIL',
    'pystray',
    'orjson',
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
    # zeroconf internals (fixes DNS cache KeyError on frozen builds)
    'zeroconf._dns',
    'zeroconf._services',
    'zeroconf._cache',
    'zeroconf._core',
    'zeroconf._handlers',
    'zeroconf._protocol',
    'zeroconf._logger',
    'zeroconf._utils',
    'zeroconf._updates',
    'zeroconf._engine',
    'zeroconf._listener',
    'zeroconf._record',
    'zeroconf._transport',
    'zeroconf._resolver',
    'zeroconf._browser',
    'zeroconf._registration',
    'zeroconf._exceptions',
    'zeroconf._const',
    'zeroconf._asyncio',
]

for _pkg in [
    'aioesphomeapi',
    'pymicro_wakeword',
    'pyopen_wakeword',
    'sounddevice',
    'pygame',
    'vlc',
    'webrtcvad',
    'zeroconf',
    'ifaddr',
    'comtypes',
    'PIL',
    'pystray',
    'windows_toasts',
    'aiosendspin',
    'aiohttp',
    'yarl',
    'multidict',
    'idna',
    'mashumaro',
    'orjson',
    'typing_extensions',
    'pycaw',
]:
    HIDDEN_IMPORTS += collect_submodules(_pkg)
