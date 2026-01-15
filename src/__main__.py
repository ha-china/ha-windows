"""
Home Assistant Windows Client Main Entry Point
Package entry point, supports running with python -m src
"""

import sys
import os

# PyInstaller packaged path setup
if getattr(sys, 'frozen', False):
    # PyInstaller packaged environment
    # _MEIPASS is the temp extraction directory, src is already inside
    # Need to add src directory to sys.path for correct module imports
    import os
    src_path = os.path.join(sys._MEIPASS, 'src')
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

from src.main import main

if __name__ == "__main__":
    main()
