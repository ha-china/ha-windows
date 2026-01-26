"""
PyInstaller hook for soundcard
Ensures audio device libraries are included
"""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_dynamic_libs

# Collect soundcard data files
datas = collect_data_files('soundcard')

# Collect all soundcard submodules
hiddenimports = collect_submodules('soundcard')

# Collect dynamic libraries (PortAudio, etc.)
binaries = collect_dynamic_libs('soundcard')