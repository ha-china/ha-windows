# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachallg.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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