"""
PyInstaller hook for pygame
Ensures pygame mixer is properly initialized
"""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Collect all pygame data files
datas = collect_data_files('pygame')

# Collect all pygame submodules
hiddenimports = collect_submodules('pygame')

# Ensure pygame mixer is imported
hiddenimports += ['pygame.mixer', 'pygame.mixer.music']