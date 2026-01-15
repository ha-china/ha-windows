"""
Home Assistant Windows Client Startup Script
"""

import sys
import os

# Add project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import and run main program
if __name__ == "__main__":
    from src.main import main
    main()