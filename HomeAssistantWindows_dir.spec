# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for directory mode (one-dir)
# Used for creating installer packages
# Goal: Small exe file with all dependencies in directory
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_dynamic_libs

# Collect data files from packages (all dependencies)
datas = []
datas += collect_data_files('customtkinter', include_py_files=False)
datas += collect_data_files('aioesphomeapi', include_py_files=False)
datas += collect_data_files('pymicro_wakeword', include_py_files=False)
datas += collect_data_files('soundcard', include_py_files=False)
datas += collect_data_files('pygame', include_py_files=False)
datas += collect_data_files('vlc', include_py_files=False)
datas += collect_data_files('webrtcvad', include_py_files=False)
datas += collect_data_files('zeroconf', include_py_files=False)
datas += collect_data_files('ifaddr', include_py_files=False)
datas += collect_data_files('pydantic', include_py_files=False)
datas += collect_data_files('pydantic_core', include_py_files=False)
datas += collect_data_files('attrs', include_py_files=False)
datas += collect_data_files('comtypes', include_py_files=False)
datas += collect_data_files('PIL', include_py_files=False)
datas += collect_data_files('pystray', include_py_files=False)
datas += collect_data_files('win10toast', include_py_files=False)
datas += collect_data_files('windows_toasts', include_py_files=False)

# Add source files
datas += [('src', 'src')]

# Collect binaries (all DLLs and libraries)
binaries = []
binaries += collect_dynamic_libs('customtkinter')
binaries += collect_dynamic_libs('aioesphomeapi')
binaries += collect_dynamic_libs('pymicro_wakeword')
binaries += collect_dynamic_libs('soundcard')
binaries += collect_dynamic_libs('pygame')
binaries += collect_dynamic_libs('vlc')
binaries += collect_dynamic_libs('webrtcvad')
binaries += collect_dynamic_libs('zeroconf')
binaries += collect_dynamic_libs('ifaddr')
binaries += collect_dynamic_libs('pydantic')
binaries += collect_dynamic_libs('pydantic_core')
binaries += collect_dynamic_libs('attrs')
binaries += collect_dynamic_libs('comtypes')
binaries += collect_dynamic_libs('PIL')
binaries += collect_dynamic_libs('pystray')

# Hidden imports (only modules that PyInstaller cannot auto-detect)
hiddenimports = [
    # GUI framework
    'tkinter',
    # Core dependencies
    'customtkinter',
    'aioesphomeapi',
    'soundcard',
    'pygame',
    'pygame.mixer',
    'pygame.mixer.music',
    'vlc',
    'numpy',
    'psutil',
    'win10toast',
    'pymicro_wakeword',
    'webrtcvad',
    'zeroconf',
    'pycaw',
    'PIL',
    'pystray',
    'windows_toasts',
    # src modules
    'src.i18n',
    'src.core.mdns_discovery',
    'src.core.esphome_protocol',
    'src.ui.system_tray_icon',
    'src.voice.audio_recorder',
    'src.voice.mpv_player',
    'src.voice.wake_word',
    'src.voice.vad',
    'src.voice.voice_assistant',
    'src.commands.command_executor',
    'src.commands.system_commands',
    'src.commands.media_commands',
    'src.commands.audio_commands',
    'src.sensors.windows_monitor',
    'src.notify.announcement',
    'src.notify.toast_notification',
    'src.notify.service_entity',
    'src.ui.main_window',
    'src.autostart',
    # Zeroconf internal modules (fixes DNS cache KeyError)
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
    # aiohttp and related
    'aiohttp',
    'yarl',
    'multidict',
    'idna',
    'frozenlist',
    'aiosignal',
    'attrs',
    # pydantic
    'pydantic',
    'pydantic_core',
    # ifaddr
    'ifaddr',
    # winsound
    'winsound',
    # ctypes for Windows APIs
    'ctypes',
    'ctypes.wintypes',
]

# Collect submodules (only for packages that need it)
hiddenimports += collect_submodules('customtkinter')
hiddenimports += collect_submodules('aioesphomeapi')
hiddenimports += collect_submodules('pymicro_wakeword')
hiddenimports += collect_submodules('soundcard')
hiddenimports += collect_submodules('pygame')
hiddenimports += collect_submodules('vlc')
hiddenimports += collect_submodules('webrtcvad')
hiddenimports += collect_submodules('zeroconf')
hiddenimports += collect_submodules('ifaddr')
hiddenimports += collect_submodules('pydantic')
hiddenimports += collect_submodules('pydantic_core')
hiddenimports += collect_submodules('attrs')
hiddenimports += collect_submodules('comtypes')
hiddenimports += collect_submodules('PIL')
hiddenimports += collect_submodules('pystray')
hiddenimports += collect_submodules('win10toast')
hiddenimports += collect_submodules('windows_toasts')
hiddenimports += collect_submodules('aiohttp')
hiddenimports += collect_submodules('yarl')
hiddenimports += collect_submodules('multidict')
hiddenimports += collect_submodules('idna')
hiddenimports += collect_submodules('pycaw')

a = Analysis(
    ['src\\__main__.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=['hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'pandas', 'scipy', 'pytest', 'IPython', 'jupyter'],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

# EXE configuration - GUI APPLICATION (No console window)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # CRITICAL: This keeps binaries separate
    name='HomeAssistantWindows',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,  # Enable UPX compression
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window (GUI mode)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='version_info.txt',
    icon=['src\\logo.ico'],
)

# Collect all files into directory
coll = COLLECT(
    exe,
    a.binaries,  # All DLLs and libraries go here
    a.datas,     # All data files go here
    strip=False,
    upx=True,    # Enable UPX compression for binaries
    upx_exclude=[],
    name='HomeAssistantWindows',
)
