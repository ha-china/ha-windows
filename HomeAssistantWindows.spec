# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('src', 'src')]
binaries = []
hiddenimports = ['customtkinter', 'aioesphomeapi', 'soundcard', 'mpv', 'numpy', 'psutil', 'win10toast', 'pymicro_wakeword', 'webrtcvad', 'zeroconf', 'pycaw', 'PIL', 'pystray', 'i18n', 'core.mdns_discovery', 'core.esphome_protocol', 'ui.system_tray_icon', 'voice.audio_recorder', 'voice.mpv_player', 'voice.wake_word', 'voice.vad', 'voice.voice_assistant', 'commands.command_executor', 'commands.system_commands', 'commands.media_commands', 'commands.audio_commands', 'sensors.windows_monitor', 'notify.announcement', 'ui.main_window']
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('aioesphomeapi')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pymicro_wakeword')
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
    excludes=['matplotlib', 'pandas', 'scipy', 'pytest'],
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
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='version_info.txt',
    icon=['src\\logo.ico'],
)
