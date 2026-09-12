# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachallg.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.4.0] - 2026-09-12

### Added
- 托盘隐藏模式 (issue #11): 托盘菜单可隐藏图标，隐藏时仅保留设备状态传感器上报，语音助手 / Sendspin / 远程指令（媒体播放器、按钮、服务、麦克风静音/思考音 switch）全部 unload；HA 设备页 Controls 区新增「隐藏图标」switch 作为唯一恢复入口，开关即 unload/load；偏好持久化，重启保持
- 新增 `src/sensors/tray_icon_switch.py` 托盘图标开关实体

### Fixed
- 修复语音被静音: 上一个 pipeline run 的迟到 `RUN_END`（hide/show 重连后 HA 先 abort 旧 run）会清掉新会话的 streaming 标志，导致整轮对话无音频；现在语音边界 `VAD_END`/`STT_END` 才是权威停止点
- 修复隐藏模式三个恢复缺陷: `_event_loop` 仅在唤醒词初始化时赋值，隐藏启动后回调全部丢失；`_schedule` 在事件循环线程上改用 `create_task`；pystray 默认 setup 无条件显示图标，改用自定义 setup 尊重隐藏意图
- 修复托盘隐藏后被 HA 重连触发的 phase 重绘恢复（`_replace_icon` 在隐藏状态下不再重新添加图标）
- 修复开关语义反转导致隐藏不生效/状态回退；switch 状态直接等于 hidden 标志；Tray Icon switch key 700→701，强制 HA 重建实体以从 Configuration 归入 Controls
- 修复 `output_device` 偏好未写入 `save/load_preferences` 导致输出设备选择不持久化

### Removed
- 移除 Screenshot 按钮: CommandExecutor 中从未注册该命令，按下只会被白名单拒绝的死功能

## [1.3.0] - 2026-09-09

### Added
- 音频输出设备选择 (issue #12): 托盘菜单新增「音频输出」子菜单（与麦克风选择同级），支持 pygame（TTS/公告）、VLC（音乐流）和 Sendspin 三个后端统一切换；选择持久化到偏好文件，启动时自动恢复
- 新增 `src/core/audio_output.py`：输出设备枚举（WASAPI 优先、去重）、名称解析、pygame mixer 重建（未知设备自动回退系统默认）、pycaw 渲染端点 ID 查询（供 VLC mmdevice 切换）
- Sendspin 热切换：播放中切换输出设备立即生效（重建流并重锚定 DAC 时钟映射）；设备打开失败自动回退系统默认，不会中断播放
- About 对话框重新设计：无边框深色圆角卡片（与 pairing dialog / mini player 设计语言一致）、反锯齿 accent 徽章、accent 色版本号、可点击 GitHub 链接、pill 关闭按钮、支持拖拽和 Esc 关闭

### Fixed
- Sendspin 播放中切换输出设备不生效：热切换时未更新 `player.device`，导致每次重启都开在旧设备上；设备名称解析优先 WASAPI（此前可能命中 MME/DirectSound 同名副本），并记录实际打开的设备到日志

## [1.2.0] - 2026-09-04

### Fixed
- SyncAudioPlayer: fixed `SAMPLE_RATE` undefined in PortAudio callback (NameError crashed audio, could take down the receiver → no mDNS → MA couldn't discover); fixed partial-chunk overwriting the next queued frame; fixed `_dac_to_loop_us` double-call polluting clock calibration
- tk UI threads (mini player / pairing dialog / conversation bubble): `ensure()` now checks thread liveness, `_poll()` wraps all ticks in try/except so the after-loop never dies silently (was the root cause of mini player disappearing); dead threads now auto-restart on next `show()`
- `_on_stream_start`/`_on_stream_end`: wrapped `_start_player()`/`_stop_playback()` in try/except so a player failure no longer blocks the playing-state callback (mini player now always shows)
- Sendspin receiver start: retries up to 6 times (2s interval) when port 8928 is busy, instead of silently entering a zombie state on immediate restart
- Single-instance lock via named mutex (`Global\HomeAssistantWindows-SingleInstance`): prevents port-8928 races on quick relaunch; on conflict shows a bilingual dialog (force-kill stale process or abort), kills by command-line/EXE path (never kills unrelated `python.exe`)
- i18n `_detect_system_language`: now actually detects the Windows user locale via `GetUserDefaultLocaleName` instead of forcing `en_US`; `--language` defaults to auto-detect

### Added
- Sendspin pairing PIN popup (tkinter, dark theme, matches mini player position): large 54pt PIN on tinted card, click-to-copy to clipboard, auto-hides on pairing completion
- PSK mismatch detection: 3 consecutive handshake failures + existing pairing record → re-pair confirmation dialog; `reset_pairing()` clears the pairing store
- CI artifacts retention reduced to 7 days

## [1.1.0] - 2026-09-02

### Changed
- Upgraded all dependencies to latest stable: aiosendspin 6.0.5 -> 9.1.1 (new Noise-encrypted pairing, persistent client Identity, time-synchronized playback), aioesphomeapi -> 46.3.0, zeroconf -> 0.151.3, pygame 2.6.1, pymicro-wakeword 2.4.1, Pillow 12.3.0, sounddevice 0.5.6

### Added
- Sendspin time-synchronized audio playback: chunks are scheduled at the exact client time via the shared clock, eliminating the buffer-induced audio/UI lag
- Persistent client identity and pairing store (restarts keep the same Music Assistant player and pairing)

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
