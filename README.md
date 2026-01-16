# Home Assistant Windows Client

A Windows client that emulates an ESPHome device for Home Assistant integration. Enables voice assistant, system monitoring, and remote control capabilities.

> **🐍 Built with Python** - This project is developed entirely in Python, making it easy to port to macOS or Linux. Most of the code is cross-platform, only a few Windows-specific modules (like `pycaw` for audio control) need to be replaced with platform-specific alternatives.

## Features

- **Voice Assistant**: Wake word detection (Okay Nabu, Hey Jarvis, etc.)
- **Floating Mic Button**: Push-to-talk with draggable floating button
- **System Monitoring**: CPU, memory, disk usage sensors
- **Media Player**: Play TTS and audio announcements from Home Assistant
- **Remote Control**: Shutdown, restart, screenshot buttons via Home Assistant
- **Windows Notifications**: Display toast notifications from Home Assistant
- **System Tray**: Runs in background with tray icon

## Installation

1. Download `HomeAssistantWindows.exe` from [Releases](https://github.com/ha-china/ha-windows/releases)
2. Run the executable
3. The client will appear in your system tray

## Setup in Home Assistant

The client is automatically discovered by Home Assistant via mDNS:

1. Go to **Settings** > **Devices & Services**
2. You should see a new ESPHome device discovered
3. Click **Configure** to add it

Or add manually:
1. Go to **Settings** > **Devices & Services** > **Add Integration**
2. Search for **ESPHome**
3. Enter the device IP and port (default: 6053)

## Usage

### System Tray
- **Left-click**: Toggle floating mic button visibility
- **Right-click**: Show menu (Show/Hide Icon, Status, Quit)

### Floating Mic Button
- **Press and hold**: Start voice input
- **Release**: Stop voice input
- **Drag**: Move button to any position
- Button turns red when listening

### Voice Assistant
Say the wake word (default: "Okay Nabu") to activate voice assistant, or use the floating mic button for push-to-talk.

### Available Sensors
- CPU Usage (%)
- Memory Usage (%)
- Memory Free (GB)
- Disk Usage (%) - per drive
- Disk Free (GB) - per drive
- Battery Level/Status (if available)
- Network Status

### Available Controls (Buttons)
- Shutdown - Shutdown the computer
- Restart - Restart the computer
- Screenshot - Take a screenshot

### Media Player
The client exposes a media player entity that can:
- Play TTS (Text-to-Speech) announcements
- Play audio from URLs
- Control playback (play/pause/stop)

Use Home Assistant's `media_player.play_media` or `tts.speak` service to play audio.

**Optional: Install VLC for streaming support**

For long audio (music), install [VLC media player](https://www.videolan.org/vlc/) to enable true streaming playback. Without VLC, audio is downloaded to memory first (fine for short TTS).

### Notifications
Send Windows toast notifications from Home Assistant using the `esphome.xxx_notify` service (where `xxx` is your device name).

Example automation:
```yaml
service: esphome.my_pc_notify
data:
  title: "Hello"
  message: "This is a notification from Home Assistant"
```

## Wake Words

Available wake words:
- Okay Nabu (default)
- Hey Jarvis
- Alexa
- Hey Mycroft
- Hey Home Assistant
- Okay Computer
- Hey Luna

Configure wake word in Home Assistant's ESPHome device settings.

## License

MIT License


## Acknowledgments

- [linux-voice-assistant](https://github.com/OHF-Voice/linux-voice-assistant) - Voice assistant protocol implementation reference
- [ESPHome](https://esphome.io/) - API protocol and Home Assistant integration
- [Home Assistant](https://www.home-assistant.io/) - Smart home platform
