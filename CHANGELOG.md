# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachallg.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-08-26

First stable release. The Windows satellite is feature-complete for daily use:
voice assistant with wake words, Sendspin music streaming with a fully themed
mini player, HA hardware sensors, notifications and remote command execution.

### Changed
- Mini player accent colors now always derive from the artwork (no fallback) -
  every track recolors the player, including gray covers (warm/cool tint)

### Fixed
- Track changes sometimes left the play button / progress fill in the previous
  track's color
- Play/pause state lagging seconds behind the user's own button presses

## [0.10.0] - 2026-08-26

### Added
- Mini player visual redesign ("ambient glass"): blurred album art backdrop, rounded transparent window, anti-aliased circular controls, ink-centered glyphs, progress bar with adjacent time labels
- Dynamic color theming: buttons, slider tracks and accent color (play button / progress fill / lyric) are derived from each track's artwork - every track recolors the player
- Optimistic playback state: play/pause/stop button presses update the UI instantly instead of waiting seconds for the next metadata push

### Fixed
- Launch no longer mutes the PC: Music Assistant's replayed (possibly stale) volume/mute state is ignored while nothing is playing, and the real system volume/mute is reported at connect
- Mini player artwork/duration/volume arriving before the window existed were silently dropped (now cached and re-applied on show)

## [0.9.0] - 2026-08-26

### Added
- Sendspin mini player: floating always-on-top window with album artwork, synced lyrics (LRCLIB), progress bar, play/pause/prev/next/stop controls, volume slider and mute toggle
- Tray menu: mini player and Sendspin toggles grouped under a Sendspin submenu
- "Run as administrator" tray action (self-relaunch with elevation)
- Tests for service entity dispatch, command whitelist behavior, update version comparison and media volume clamping

### Fixed
- HA media services (media_play_pause/next/previous) silently failing due to invalid "media:" prefix in command dispatch
- Tray Sendspin toggle silently failing (asyncio task scheduled from the tray thread without a running event loop)
- `notify` command referencing the unpackaged win10toast backend; now uses windows_toasts
- Volume feedback loop: slider drag is debounced (250 ms) and reported volume no longer reads back the live system value
- Device identity file corruption now backs up the file instead of silently regenerating (prevents HA device drift)
- Preferences writes are lock-protected and atomic (temp file + replace), safe across tray/audio/event-loop threads
- Graceful shutdown waits for cleanup to finish (8 s watchdog) instead of a fixed 1 s force-exit race
- Wake word set iteration no longer races against concurrent mutation from the audio thread

### Changed
- Version metadata unified: installer.nsi accepts build-time PRODUCT_VERSION injection; CI validates pyproject/__init__/nsi/version_info/CHANGELOG consistency
- Installer kills a running instance before upgrading; uninstall removes only app-owned files plus both legacy autostart registry values
- PyInstaller spec slimmed: removed duplicated data/binary collection, unused submodules (PIL/pygame/vlc extras) and src source-tree duplication
- mDNS broadcast reports the real application version instead of hardcoded 1.0.0

## [0.8.0] - 2026-08-15

### Added
- NVIDIA GPU monitoring via NVML: GPU name, temperature, core utilization, VRAM usage/used, power (auto-hidden on non-NVIDIA systems)
- Hardware monitoring via LibreHardwareMonitor: CPU core loads, GPU clocks/hotspot/voltage, plus CPU temperature/power, motherboard temps, fans, voltages when PawnIO driver is installed
- `get_hardware_identity()` shared function for consistent SMBIOS data across ESPHome device info card and Sendspin

### Fixed
- Hardware sensor single hardware update failure no longer causes all sensors to be lost
- Removed redundant LHW sensors (memory, GPU temperature, GPU power) that duplicate psutil/NVML sources
- LHW sensors now use stable entity keys derived from object_id, preventing HA unique ID duplication errors on restart

### Changed
- psutil upgraded from 5.9.6 to 7.2.2 (bug fixes, performance improvements)
- Sendspin device info switched from PowerShell subprocess to direct winreg SMBIOS read (eliminates console flash on startup)
- New dependencies: nvidia-ml-py, HardwareMonitor

## [0.7.2] - 2026-08-15

### Changed
- Sendspin device info switched from PowerShell subprocess to direct winreg SMBIOS read (eliminates console flash on startup)

## [0.7.1] - 2026-08-15

### Added
- Sendspin connection status updates in tray menu (real-time connected/disconnected)

### Fixed
- Single-file EXE startup failure: disabled UPX compression (caused "Failed to load Python DLL") and removed numpy submodule excludes (broke numpy 2.x init)
- Unified spec_common.py for both one-file and one-dir builds to prevent config drift

## [0.7.0] - 2026-08-14

### Added
- Sendspin audio receiver: stream audio from Music Assistant to Windows via Sendspin protocol (PCM 16-bit 48 kHz stereo, no av dependency)
- Conversation bubbles: custom colored tkinter popup for STT/TTS content (blue/green/gray), with tray toggle and transparency support

### Changed
- Tray menu bilingual for all items (About, Unknown, dialog buttons)

## [0.6.3] - 2026-08-14

### Added
- Microphone mute switch (tray + ESPHome sync)
- AI bilingual changelog in release workflow

### Changed
- Replaced windows_toasts with conversation bubbles for voice assistant text display

## [0.6.2] - 2026-08-06

### Added
- Microphone selection in tray menu (choose recording device)

## [0.6.1] - 2026-08-03

### Fixed
- Restored pygame as audio playback backend

## [0.6.0] - 2026-07-30

### Added
- Tray icon status indicator (color changes by phase: idle/idle, recording/connecting/error)
- ESPHome phase callback for voice assistant state tracking
- Native tkinter dialogs replacing PySide6 (EXE size reduced from 146MB to 57MB)
- Support for workflow_dispatch trigger on release detection

### Changed
- Replaced shell notifications with Shell_NotifyIconW for reliable tray updates
- Removed floating mic button and related code
- Updated aioesphomeapi to >=45.7.0
- ESPHome version auto-read from aioesphomeapi.__version__
- Removed macOS cross-platform code (Windows-only focus)

### Fixed
- Tray icon not updating (uID mismatch, Shell_NotifyIconW return value check)
- Replying phase color too close to idle (changed to bright pink)
- VLC lazy loading to avoid hang on systems without VLC
- Sound recording AssertionError (soundcard 0.4.5 bug, locked to compatible version)
- tkinter dialog not appearing on repeated clicks

### Fixed
- Clean up partially initialized mDNS resources immediately when zeroconf registration fails.
- Periodically recreate the mDNS broadcaster during long-running sessions to release cached zeroconf state.

## [0.5.1] - 2026-04-10

### Fixed
- Fixed startup crashes caused by wake word type annotations being evaluated before `AvailableWakeWord` was imported.
- Fixed cleanup crashes when startup failed before the system tray icon was created.

## [0.5.0] - 2026-04-10

### Improved
- Bundled `pyopen_wakeword` runtime assets into both portable and installer builds so packaged Windows releases can initialize OpenWakeWord models correctly.
- Deduplicated public wake words by phrase and prefer MicroWakeWord models when both wake word engines provide the same phrase.
- Replaced autogenerated GitHub release notes with a release summary that lists pull request numbers, titles, links, and a short description for each PR since the previous release.

## [0.4.9] - 2026-04-10

### Improved
- Split the internal `stop` interrupt model from the public wake word configuration flow so Home Assistant no longer shows it as a selectable wake word.
- Made remote audio downloads cancellable during pygame fallback playback so interrupted TTS and announcements stop releasing temp files and network resources sooner.
- Added diagnostic process sensors for RSS memory, thread count, handle count, GDI object count, and USER object count to help investigate long-run Windows memory and resource leaks.

## [0.4.8] - 2026-03-18

### Added
- Added a `Thinking Sound` config switch entity and bundled a default processing sound from the reference project.

### Improved
- Synced more ESPHome device metadata so Home Assistant receives richer device information.
- Improved the media player entity with fuller feature flags, better mute/unmute behavior, and persistent volume handling.
- Added support for playing a short processing sound during voice assistant intent handling when enabled.

## [0.4.7] - 2026-03-18

### Fixed
- Fixed ESPHome entity key collisions that could prevent entity definitions and state updates from refreshing correctly in Home Assistant.
- Added periodic ESPHome state updates after subscription so system sensors continue to refresh instead of only reporting once.
- Adjusted CPU usage sampling for periodic reporting so the Home Assistant CPU usage graph shows more reliable values.

## [0.4.6] - 2026-03-18

### Improved
- ESPHome and mDNS device identity now use a persistent MAC stored in the user data directory instead of depending on the runtime network environment.

## [0.4.5] - 2026-03-18

### Added
- Added user-managed wake word model directories under the app data folder for both `MicroWakeWord` and `OpenWakeWord` models.

### Improved
- Updated wake word discovery to load built-in and user-provided MicroWakeWord and OpenWakeWord models together.
- Invalid, missing, or corrupted wake word model files are now skipped safely instead of crashing the app.
- Documented the custom wake word model directory structure in the README.

## [0.4.4] - 2026-03-18

### Fixed
- Reduced long-run memory growth during remote audio playback by using temp-file backed playback instead of loading full responses into memory.
- Added a hard limit for the ESPHome protocol receive buffer to avoid unbounded memory growth on malformed or stalled input.
- Reworked global hotkey registration to clean up handlers correctly instead of leaving blocked listener threads behind.
- Limited the application log file to a single 5 MB file to prevent unbounded disk usage over time.

## [0.4.0] - 2026-01-27

### Added
- Global hotkey support for voice input trigger
- Set voice input hotkey service (set_voice_input_hotkey)
- Voice input hotkey text sensor for displaying current hotkey
- Floating button visibility preference (saved to user directory)
- Persistent configuration storage in AppData/Local/HomeAssistantWindows
- NSIS installer support with auto-startup option
- Directory mode build for faster startup and installer packages
- Auto-startup management module (src/autostart.py)
- GitHub Actions workflow for building installer packages
- PyInstaller hooks for pygame and soundcard dependencies
- Log file path to user directory (avoiding Program Files permission issues)

### Changed
- Floating button is hidden by default on startup
- Preferences now save to user directory instead of program directory
- Update notification now opens release page instead of direct exe download
- Optimized PyInstaller spec files for better dependency management
- Separated single-file and directory mode builds
- Reduced package size by removing unnecessary dependencies
- Improved audio dependency collection for voice assistant functionality

### Improved
- Configuration persistence across restarts
- Better user experience with customizable hotkeys
- Preferences stored in Windows AppData for better portability

### Fixed
- GUI application configuration (console=False for no black window)
- Tkinter import error (required by customtkinter)
- Zeroconf DNS cache KeyError during async cleanup
- Audio playback issues with comprehensive pygame and vlc imports
- Log file permission error when installed to Program Files
- NSIS installation in CI (switched from Chocolatey to winget)
- NSIS installer script paths and missing file references

## [0.3.3] - 2026-01-24

### Added
- OpenWakeWord support alongside MicroWakeWord
- Enhanced wake word detection with dual detector support
- Support for more wake word models and better accuracy
- CHANGELOG.md for tracking version changes

### Changed
- Updated dependencies to include pyopen-wakeword>=1.0.0
- Refactored WakeWordDetector to support both MicroWakeWord and OpenWakeWord

### Technical Details
- Added OpenWakeWordFeatures extraction and processing
- Improved wake word detection flexibility and accuracy

## [0.3.2] - 2026-01-24

### Added
- Code quality tools configuration (Black, isort, MyPy)
- Development scripts (format, lint, test, run, setup)
- Wake word detection pause during TTS playback

### Changed
- Improved code maintainability and quality with type hints and linting

### Fixed
- Duplicate wake word detection during TTS playback
- Duck/unduck volume control causing audio issues
- Flake8 linting issues: f-string placeholders, unused imports, whitespace
- MyPy type checking issues: Optional types, None checks
- Type hints in audio_recorder and mdns_discovery modules

## [0.3.1] - 2026-01-24

### Added
- Wakeup sound prompt for continue conversation
- Version update checker with Windows notification

### Fixed
- Audio streaming issues with single recorder for wake word and voice assistant
- Repository URL handling

## [0.3.0] - 2026-01-24

### Changed
- Refactored: move non-protocol code out of esphome_protocol.py
- Reduced logging verbosity in models.py

### Fixed
- Excessive logging output
- Audio playback logs changed to DEBUG level

## [0.2.9] - 2026-01-24

### Added
- Version update checker with Windows notification
- Direct exe file download for updates

### Changed
- Update notification to directly download exe file
- Removed unused RELEASES_URL constant

### Fixed
- Repository URL handling

## [0.2.8] - 2026-01-24

### Added
- About menu item in system tray
- About dialog with version and repository information

### Changed
- Improve dialog windows with better UI and i18n support
- Use proper windows instead of notifications for dialogs

### Fixed
- Status dialog implementation
- About dialog implementation

## [0.2.7] - 2026-01-24

### Fixed
- Audio streaming issues: remove call_soon_threadsafe for direct calls

## [0.2.6] - 2026-01-24

### Features
- Voice Assistant with wake word detection
- System monitoring sensors (CPU, memory, disk, battery, network)
- Remote control buttons (shutdown, restart, screenshot)
- Notification services
- Media player with TTS support
- ESPHome protocol integration
- System tray icon with floating mic button

### Services
- notify - Display Windows toast notification
- notify_with_image - Display notification with image
- run_command - Execute CMD command
- open_url - Open URL in browser
- set_volume - Set system volume (0-100)
- media_play_pause - Play/Pause media
- media_next - Next track
- media_previous - Previous track

### Wake Words
- Okay Nabu (default)
- Hey Jarvis
- Alexa
- Hey Home Assistant
- Okay Computer
- Hey Luna
- Hey Mycroft
- Choo Choo Homie
- Stop (to stop playback)
