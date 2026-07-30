"""
PyInstaller hook for sounddevice
Ensures audio device libraries are included
"""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_dynamic_libs

# Collect sounddevice data files
datas = collect_data_files('sounddevice')

# Collect all sounddevice submodules
hiddenimports = collect_submodules('sounddevice')

# Collect dynamic libraries (PortAudio, etc.)
binaries = collect_dynamic_libs('sounddevice')