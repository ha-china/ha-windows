# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('src', 'src')]
binaries = []
hiddenimports = ['windows_toasts', 'pycaw', 'comtypes', 'pystray', 'win10toast', 'src.platforms.windows', 'aioesphomeapi', 'sounddevice', 'numpy', 'psutil', 'pymicro_wakeword', 'pyopen_wakeword', 'webrtcvad', 'zeroconf', 'PIL', 'pygame', 'pygame.mixer', 'pygame.mixer_music', 'src.i18n', 'src.core.mdns_discovery', 'src.core.esphome_protocol', 'src.ui.system_tray_icon', 'src.voice.audio_recorder', 'src.voice.mpv_player', 'src.voice.wake_word', 'src.voice.vad', 'src.commands.command_executor', 'src.commands.system_commands', 'src.commands.media_commands', 'src.commands.audio_commands', 'src.sensors.windows_monitor', 'src.notify.announcement', 'src.notify.toast_notification', 'src.notify.service_entity', 'src.ui.main_window', 'src.autostart', 'src.platforms', 'src.platforms.base']
tmp_ret = collect_all('aioesphomeapi')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pycaw')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('comtypes')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pymicro_wakeword')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pyopen_wakeword')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pygame')
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
    excludes=['matplotlib', 'pandas', 'scipy', 'pytest', 'numpy.random', 'numpy.fft', 'numpy.linalg', 'numpy.f2py', 'numpy.ma', 'numpy.matrixlib', 'numpy.polynomial', 'numpy.distutils', 'numpy.doc', 'numpy.testing', 'numpy.compat', 'numpy.records', 'numpy._core._multiarray_tests', 'numpy._core._simd', 'numpy._core.memmap', 'numpy._core.defchararray', 'numpy.ctypeslib', 'numpy.version', 'numpy.strings', 'numpy.char', 'numpy.emath', 'numpy.rec', 'win10toast'],
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
    strip=True,
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
