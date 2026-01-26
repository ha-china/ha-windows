"""
PyInstaller build configuration
Used to package Home Assistant Windows client into a single exe file
"""

import os
import sys
import io

# Set stdout to UTF-8 encoding (fix Windows encoding issue)
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from PyInstaller.__main__ import run

# Import version number
try:
    from src import __version__ as APP_VERSION
except ImportError:
    APP_VERSION = "0.0.0"

# Project information
APP_NAME = "HomeAssistantWindows"
APP_AUTHOR = "老王"
APP_DESCRIPTION = "Zero-config Home Assistant Windows native client"

# Main program entry point (use __main__.py so relative imports work correctly)
MAIN_SCRIPT = "src/__main__.py"

# If main program doesn't exist, create a temporary one
if not os.path.exists(MAIN_SCRIPT):
    print(f"Warning: {MAIN_SCRIPT} does not exist, please create the main program first")
    sys.exit(1)


def build_exe():
    """
    Build a single exe file using PyInstaller (one-file mode)
    """
    # PyInstaller arguments
    pyinstaller_args = [
        MAIN_SCRIPT,
        "--onefile",  # Package into a single exe file
        "--windowed",  # No console window (use GUI)
        "--name=" + APP_NAME,  # exe file name
        "--icon=src/logo.ico" if os.path.exists("src/logo.ico") else "",
        f"--version-file=version_info.txt" if os.path.exists("version_info.txt") else "",
        "--clean",  # Clean temporary files
        "--noconfirm",  # Overwrite output directory without asking
        "--distpath=dist",  # Output directory
        "--workpath=build",  # Build directory
        "--additional-hooks-dir=hooks",  # Custom hooks directory (fix webrtcvad issue)
        # Hidden imports (these modules may not be automatically detected)
        "--hidden-import=customtkinter",
        "--hidden-import=aioesphomeapi",
        "--hidden-import=soundcard",
        "--hidden-import=mpv",
        "--hidden-import=numpy",
        "--hidden-import=psutil",
        "--hidden-import=win10toast",
        "--hidden-import=pymicro_wakeword",
        "--hidden-import=webrtcvad",
        "--hidden-import=zeroconf",
        "--hidden-import=pycaw",
        "--hidden-import=PIL",
        "--hidden-import=pystray",
        # src module hidden imports (important!)
        "--hidden-import=src.i18n",
        "--hidden-import=src.core.mdns_discovery",
        "--hidden-import=src.core.esphome_protocol",
        "--hidden-import=src.ui.system_tray_icon",
        "--hidden-import=src.voice.audio_recorder",
        "--hidden-import=src.voice.mpv_player",
        "--hidden-import=src.voice.wake_word",
        "--hidden-import=src.voice.vad",
        "--hidden-import=src.voice.voice_assistant",
        "--hidden-import=src.commands.command_executor",
        "--hidden-import=src.commands.system_commands",
        "--hidden-import=src.commands.media_commands",
        "--hidden-import=src.commands.audio_commands",
        "--hidden-import=src.sensors.windows_monitor",
        "--hidden-import=src.notify.announcement",
        "--hidden-import=src.notify.toast_notification",
        "--hidden-import=src.notify.service_entity",
        "--hidden-import=src.ui.main_window",
        "--hidden-import=src.autostart",
        "--hidden-import=windows_toasts",
        # Collect all submodules
        "--collect-all=customtkinter",
        "--collect-all=aioesphomeapi",
        "--collect-all=pymicro_wakeword",  # Include tensorflowlite_c.dll
        # Add src directory to Python path
        "--add-data=src;src",
        # Exclude unnecessary modules (reduce size)
        "--exclude-module=matplotlib",
        "--exclude-module=pandas",
        "--exclude-module=scipy",
        "--exclude-module=pytest",
    ]

    # Filter empty arguments
    pyinstaller_args = [arg for arg in pyinstaller_args if arg]

    print(f"Building {APP_NAME} v{APP_VERSION} (single-file mode)...")
    print(f"PyInstaller arguments: {' '.join(pyinstaller_args)}")

    # Run PyInstaller
    run(pyinstaller_args)

    print(f"\nBuild completed!")
    print(f"Output file: dist/{APP_NAME}.exe")


def build_dir():
    """
    Build a directory using PyInstaller (one-dir mode)
    Used for creating installer packages
    """
    # PyInstaller arguments
    pyinstaller_args = [
        MAIN_SCRIPT,
        "--windowed",  # No console window
        "--name=" + APP_NAME,  # exe file name
        "--icon=src/logo.ico" if os.path.exists("src/logo.ico") else "",
        f"--version-file=version_info.txt" if os.path.exists("version_info.txt") else "",
        "--clean",  # Clean temporary files
        "--noconfirm",  # Overwrite output directory without asking
        "--distpath=dist",  # Output directory
        "--workpath=build",  # Build directory
        "--additional-hooks-dir=hooks",  # Custom hooks directory (fix webrtcvad issue)
        # Hidden imports (these modules may not be automatically detected)
        "--hidden-import=customtkinter",
        "--hidden-import=aioesphomeapi",
        "--hidden-import=soundcard",
        "--hidden-import=mpv",
        "--hidden-import=numpy",
        "--hidden-import=psutil",
        "--hidden-import=win10toast",
        "--hidden-import=pymicro_wakeword",
        "--hidden-import=webrtcvad",
        "--hidden-import=zeroconf",
        "--hidden-import=pycaw",
        "--hidden-import=PIL",
        "--hidden-import=pystray",
        # src module hidden imports (important!)
        "--hidden-import=src.i18n",
        "--hidden-import=src.core.mdns_discovery",
        "--hidden-import=src.core.esphome_protocol",
        "--hidden-import=src.ui.system_tray_icon",
        "--hidden-import=src.voice.audio_recorder",
        "--hidden-import=src.voice.mpv_player",
        "--hidden-import=src.voice.wake_word",
        "--hidden-import=src.voice.vad",
        "--hidden-import=src.voice.voice_assistant",
        "--hidden-import=src.commands.command_executor",
        "--hidden-import=src.commands.system_commands",
        "--hidden-import=src.commands.media_commands",
        "--hidden-import=src.commands.audio_commands",
        "--hidden-import=src.sensors.windows_monitor",
        "--hidden-import=src.notify.announcement",
        "--hidden-import=src.notify.toast_notification",
        "--hidden-import=src.notify.service_entity",
        "--hidden-import=src.ui.main_window",
        "--hidden-import=src.autostart",
        "--hidden-import=windows_toasts",
        # Collect all submodules
        "--collect-all=customtkinter",
        "--collect-all=aioesphomeapi",
        "--collect-all=pymicro_wakeword",  # Include tensorflowlite_c.dll
        # Add src directory to Python path
        "--add-data=src;src",
        # Exclude unnecessary modules (reduce size)
        "--exclude-module=matplotlib",
        "--exclude-module=pandas",
        "--exclude-module=scipy",
        "--exclude-module=pytest",
    ]

    # Filter empty arguments
    pyinstaller_args = [arg for arg in pyinstaller_args if arg]

    print(f"Building {APP_NAME} v{APP_VERSION} (directory mode)...")
    print(f"PyInstaller arguments: {' '.join(pyinstaller_args)}")

    # Run PyInstaller
    run(pyinstaller_args)

    print(f"\nBuild completed!")
    print(f"Output directory: dist/{APP_NAME}/")
    print(f"Executable file: dist/{APP_NAME}/{APP_NAME}.exe")


def create_version_info():
    """
    Create version info file (optional)
    Used for Windows exe version information
    """
    version_info_content = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({APP_VERSION.replace('.', ',')}, 0),
    prodvers=({APP_VERSION.replace('.', ',')}, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'{APP_AUTHOR}'),
        StringStruct(u'FileDescription', u'{APP_DESCRIPTION}'),
        StringStruct(u'FileVersion', u'{APP_VERSION}'),
        StringStruct(u'InternalName', u'{APP_NAME}'),
        StringStruct(u'LegalCopyright', u'Copyright © 2024'),
        StringStruct(u'OriginalFilename', u'{APP_NAME}.exe'),
        StringStruct(u'ProductName', u'{APP_NAME}'),
        StringStruct(u'ProductVersion', u'{APP_VERSION}')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""

    with open("version_info.txt", "w", encoding="utf-8") as f:
        f.write(version_info_content)

    print("Version info file created: version_info.txt")


def main():
    """Main function"""
    import argparse

    parser = argparse.ArgumentParser(description="Home Assistant Windows client build script")
    parser.add_argument(
        "--version-info",
        action="store_true",
        help="Create version info file",
    )
    parser.add_argument(
        "--build",
        action="store_true",
        help="Build single-file exe (one-file mode)",
    )
    parser.add_argument(
        "--build-dir",
        action="store_true",
        help="Build directory mode (one-dir mode, for installer)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Execute all steps (create version info + build single-file)",
    )

    args = parser.parse_args()

    if args.version_info or args.all:
        create_version_info()

    if args.build or args.all:
        build_exe()

    if args.build_dir:
        build_dir()

    if not any([args.version_info, args.build, args.build_dir, args.all]):
        # Default to build (single-file mode)
        parser.print_help()
        print("\nNo arguments specified, executing default build (single-file mode)...")
        build_exe()


if __name__ == "__main__":
    main()
