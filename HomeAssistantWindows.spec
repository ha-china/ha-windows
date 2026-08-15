# -*- mode: python ; coding: utf-8 -*-
# One-file build. All shared configuration lives in spec_common.py.
from spec_common import BINARIES, DATAS, EXCLUDES, HIDDEN_IMPORTS


a = Analysis(
    ['src\\__main__.py'],
    pathex=[],
    binaries=BINARIES,
    datas=DATAS,
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=['hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
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
    # UPX-compressed python DLL breaks one-file mode ("Failed to load Python
    # DLL"); strip is unsafe on Windows binaries.
    strip=False,
    upx=False,
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
