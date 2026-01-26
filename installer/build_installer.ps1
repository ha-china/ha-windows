# Build Installer Script
# Creates NSIS installer for Home Assistant Windows

# Check if NSIS is installed
$nsisPath = "C:\Program Files (x86)\NSIS\makensis.exe"
if (-not (Test-Path $nsisPath)) {
    Write-Error "NSIS not found at $nsisPath"
    Write-Error "Please install NSIS from https://nsis.sourceforge.io/"
    exit 1
}

# Check if build directory exists
$buildPath = "dist\HomeAssistantWindows"
if (-not (Test-Path $buildPath)) {
    Write-Error "Build directory not found at $buildPath"
    Write-Error "Please build the application first using: python setup.py --build-dir"
    exit 1
}

# Create installer directory
New-Item -ItemType Directory -Force -Path "installer" | Out-Null

# Build installer
Write-Host "Building NSIS installer..."
& $nsisPath "installer\installer.nsi"

if ($LASTEXITCODE -eq 0) {
    Write-Host "Installer built successfully!"
    $installerPath = "dist\HomeAssistantWindows_Setup.exe"
    if (Test-Path $installerPath) {
        $file = Get-Item $installerPath
        Write-Host "Output: $installerPath"
        Write-Host "Size: $([math]::Round($file.Length / 1MB, 2)) MB"
    }
} else {
    Write-Error "Installer build failed!"
    exit 1
}