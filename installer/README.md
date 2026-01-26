# Home Assistant Windows Installer

This directory contains the NSIS installer script for creating a Windows installer package.

## Features

- **Main Program Installation**: Installs the HomeAssistantWindows.exe and required files
- **Auto Start on Boot**: Optional feature to start the application automatically when Windows boots
- **Start Menu Shortcuts**: Creates shortcuts in the Start Menu
- **Desktop Shortcut**: Creates a shortcut on the desktop
- **Clean Uninstall**: Removes all files, shortcuts, and registry entries

## Building the Installer

### Prerequisites

1. **NSIS (Nullsoft Scriptable Install System)**
   - Download from: https://nsis.sourceforge.io/
   - Install to: `C:\Program Files (x86)\NSIS\`

2. **Build the application first**
   ```bash
   python setup.py --build
   ```
   This will create a directory at `dist/HomeAssistantWindows/` containing all files.

### Build Steps

1. **Manual Build (Windows)**
   ```powershell
   .\installer\build_installer.ps1
   ```

2. **Automated Build (GitHub Actions)**
   - See `.github/workflows/build-installer.yml`

### Directory Mode vs Single File

This installer uses **directory mode** (one-dir) instead of single-file mode (one-file):
- ✅ Faster startup - no need to extract to temp directory
- ✅ Smaller installer - files are compressed by NSIS instead of UPX
- ✅ Better performance - files are already in place
- ✅ Easier debugging - can inspect individual files

## Installer Options

The installer provides the following components:

1. **Main Program** (Required)
   - Installs the entire HomeAssistantWindows directory
   - Includes all dependencies, libraries, and wake word models
   - Creates necessary directories

2. **Auto Start on Boot** (Optional)
   - Adds the application to Windows startup registry
   - Application will launch automatically on Windows boot

3. **Start Menu Shortcuts** (Optional)
   - Creates Start Menu folder with shortcuts
   - Includes uninstall shortcut

## Uninstallation

The uninstaller will:
- Stop the running application
- Remove all installed files
- Remove shortcuts
- Clean up registry entries
- Preserve user data in `%APPDATA%\HomeAssistantWindows`

## Customization

### Version Information

Edit `installer.nsi` to update version information:

```nsis
!define PRODUCT_VERSION "1.0.0"
```

### Installer Images

Replace the following files to customize installer appearance:
- `installer\header.bmp` - Header image (150x57 pixels)
- `installer\welcome.bmp` - Welcome page image (164x314 pixels)

### License

Ensure `LICENSE` file exists in the project root for the license page.

## Troubleshooting

### NSIS not found

Ensure NSIS is installed to the default location:
```
C:\Program Files (x86)\NSIS\
```

If installed elsewhere, update `build_installer.ps1` with the correct path.

### Build directory not found

Build the application first:
```bash
python setup.py --build
```

This will create `dist/HomeAssistantWindows/` directory with all files.

### Missing files

Ensure the build output exists before building:
- `dist/HomeAssistantWindows/` directory (created by PyInstaller)
- `installer/installer.nsi` (installer script)
- `LICENSE` file (for license page)