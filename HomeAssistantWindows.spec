# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for single-file mode (one-file)
# Portable version - no autostart functionality
from PyInstaller.utils.hooks import collect_all

# Collect data files from packages
datas = [('src', 'src')]

# Collect binaries
binaries = []

# Hidden imports (only modules that PyInstaller cannot auto-detect)
hiddenimports = [
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
    # src modules (excluding autostart for portable version)
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
    # Note: src.autostart is NOT included in portable version
]

# Collect all dependencies for key packages
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

tmp_ret = collect_all('aioesphomeapi')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

tmp_ret = collect_all('pymicro_wakeword')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

tmp_ret = collect_all('soundcard')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

tmp_ret = collect_all('pygame')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

tmp_ret = collect_all('vlc')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

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

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='HomeAssistantWindows',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
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