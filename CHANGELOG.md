# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- OpenWakeWord support for enhanced wake word detection
- pyproject.toml with Black, isort, and MyPy configurations
- Development scripts for formatting, linting, and testing
- CHANGELOG.md for tracking version changes

### Changed
- Improved code quality with type hints and linting
- Fixed duplicate wake word detection during TTS playback
- Disabled duck/unduck volume control to prevent audio issues

### Fixed
- Flake8 issues: f-string placeholders, unused imports, whitespace
- MyPy type issues: Optional types, None checks
- Type hints in audio_recorder and mdns_discovery modules

## [0.3.2] - 2026-01-24

### Added
- Code quality tools configuration (Black, isort, MyPy)
- Development scripts (format, lint, test, run, setup)
- Wake word detection pause during TTS playback

### Changed
- Version bump from 0.3.1 to 0.3.2
- Improved code maintainability and quality

### Fixed
- Duplicate wake word detection during TTS playback
- Duck/unduck volume control causing audio issues
- Flake8 linting issues
- MyPy type checking issues

## [0.3.1] - Previous Release

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