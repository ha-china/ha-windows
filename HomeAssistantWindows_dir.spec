# -*- mode: python ; coding: utf-8 -*-
# One-dir build for installer packages. All shared configuration lives in
# spec_common.py.
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

# EXE configuration - GUI APPLICATION (No console window)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # CRITICAL: This keeps binaries separate
    append_pkg=False,
    contents_directory='_internal',
    name='HomeAssistantWindows',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # keep consistent with one-file build; avoids UPX breakage
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
    upx=False,
    upx_exclude=[],
    name='HomeAssistantWindows',
)
