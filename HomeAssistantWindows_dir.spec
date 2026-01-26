# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for directory mode (one-dir)
# Used for creating installer packages
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_dynamic_libs

# Collect data files from packages
datas = []
datas += collect_data_files('customtkinter', include_py_files=False)
datas += collect_data_files('aioesphomeapi', include_py_files=False)
datas += collect_data_files('pymicro_wakeword', include_py_files=False)
datas += collect_data_files('soundcard', include_py_files=False)
datas += collect_data_files('pygame', include_py_files=False)
datas += collect_data_files('vlc', include_py_files=False)
datas += collect_data_files('webrtcvad', include_py_files=False)

# Add source files
datas += [('src', 'src')]

# Collect binaries
binaries = []
binaries += collect_dynamic_libs('customtkinter')
binaries += collect_dynamic_libs('aioesphomeapi')
binaries += collect_dynamic_libs('pymicro_wakeword')
binaries += collect_dynamic_libs('soundcard')
binaries += collect_dynamic_libs('pygame')
binaries += collect_dynamic_libs('vlc')
binaries += collect_dynamic_libs('webrtcvad')

# Hidden imports
hiddenimports = [
    'customtkinter',
    'aioesphomeapi',
    'soundcard',
    'pygame',
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
    # Collect all submodules
    *collect_submodules('customtkinter'),
    *collect_submodules('aioesphomeapi'),
    *collect_submodules('pymicro_wakeword'),
    *collect_submodules('soundcard'),
    *collect_submodules('pygame'),
    *collect_submodules('vlc'),
]

a = Analysis(
    ['src\\__main__.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=['hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'pandas', 'scipy', 'pytest', 'tkinter'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='HomeAssistantWindows',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='version_info.txt',
    icon=['src\\logo.ico'],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='HomeAssistantWindows',
)