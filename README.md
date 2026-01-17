# Home Assistant Windows Client

A Windows client that emulates an ESPHome device for seamless Home Assistant integration. Enables voice assistant, system monitoring, remote control, and more.

> **🐍 Built with Python** - This project is developed entirely in Python, making it easy to migrate to macOS or Linux. Most of the code is cross-platform, only a few Windows-specific modules (like `pycaw` for audio control) need to be replaced with platform-specific alternatives.

> **📝 Early Stage** - This is still an early version. If you have feature requests, please submit them in the [Issues](https://github.com/ha-china/ha-windows/issues). I will evaluate each request based on exe size impact and system performance, and gradually add features.

## ✨ Features

### 🎤 Voice Assistant
- **Wake Word Detection**: Multiple wake words supported (Okay Nabu, Hey Jarvis, Alexa, etc.)
- **Floating Mic Button**: Push-to-talk with draggable floating button
- **Voice Recognition**: Process voice commands through Home Assistant's Assist
- **TTS Playback**: Play voice responses from Home Assistant

### 📊 System Monitoring Sensors
- **CPU Usage** (%)
- **Memory Usage** (%)
- **Memory Free** (GB)
- **Disk Usage** (%) - per drive
- **Disk Free** (GB) - per drive
- **Battery Level/Status** (if available)
- **IP Address** - Local IPv4 address
- **Boot Time** - System boot timestamp
- **Uptime** (hours)
- **Process Count**
- **Network Upload** (GB) - Total uploaded data
- **Network Download** (GB) - Total downloaded data

### 🎮 Remote Control Buttons
- **Shutdown** - Shutdown the computer
- **Restart** - Restart the computer
- **Screenshot** - Take a screenshot

### 🔧 Services
Call these services from Home Assistant:

#### Notification Services
- **notify** - Display Windows toast notification
  ```yaml
  service: esphome.my_pc_notify
  data:
    title: "Title"
    message: "Message content"
  ```

- **notify_with_image** - Display notification with image
  ```yaml
  service: esphome.my_pc_notify_with_image
  data:
    title: "Motion Detected"
    message: "Front door camera"
    image_url: "http://your-ha:8123/api/camera_proxy/camera.front_door"
  ```

#### System Control Services
- **run_command** - Execute any CMD command
  ```yaml
  service: esphome.my_pc_run_command
  data:
    command: "notepad.exe"
  ```

- **open_url** - Open URL in browser
  ```yaml
  service: esphome.my_pc_open_url
  data:
    url: "https://www.home-assistant.io"
  ```

- **set_volume** - Set system volume (0-100)
  ```yaml
  service: esphome.my_pc_set_volume
  data:
    volume: 50
  ```

#### Media Control Services
- **media_play_pause** - Play/Pause
- **media_next** - Next track
- **media_previous** - Previous track

### 🎵 Media Player
The client exposes a media player entity that can:
- Play TTS (Text-to-Speech) announcements
- Play audio from URLs
- Control playback (play/pause/stop)

Use Home Assistant's `media_player.play_media` or `tts.speak` service to play audio.

**Optional: Install VLC for streaming support**

For long audio (music), install [VLC media player](https://www.videolan.org/vlc/) to enable true streaming playback. Without VLC, audio is downloaded to memory first (fine for short TTS).

## 📥 Installation

### Option 1: Download Executable (Recommended)
1. Download `HomeAssistantWindows.exe` from [Releases](https://github.com/ha-china/ha-windows/releases)
2. Run the executable
3. The client will appear in your system tray

### Option 2: Run from Source
```bash
# Clone repository
git clone https://github.com/ha-china/ha-windows.git
cd ha-windows

# Install dependencies
pip install -r requirements.txt

# Run
python -m src
```

## 🔧 Setup in Home Assistant

The client is automatically discovered by Home Assistant via mDNS:

1. Go to **Settings** > **Devices & Services**
2. You should see a new ESPHome device discovered
3. Click **Configure** to add it

Or add manually:
1. Go to **Settings** > **Devices & Services** > **Add Integration**
2. Search for **ESPHome**
3. Enter the device IP and port (default: 6053)

## 💡 Usage

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



## 🎯 Wake Words

Available wake words:
- Okay Nabu (default)
- Hey Jarvis
- Alexa
- Hey Mycroft
- Hey Home Assistant
- Okay Computer
- Hey Luna

Configure wake word in Home Assistant's ESPHome device settings.

## 📝 Automation Examples

### Send Notification
```yaml
automation:
  - alias: "PC Notification Test"
    trigger:
      - platform: state
        entity_id: binary_sensor.front_door
        to: "on"
    action:
      - service: esphome.my_pc_notify
        data:
          title: "Doorbell"
          message: "Someone is at the door"
```

### Notification with Camera Snapshot
```yaml
automation:
  - alias: "Front Door Motion Alert"
    trigger:
      - platform: state
        entity_id: binary_sensor.front_door_motion
        to: "on"
    action:
      - service: esphome.my_pc_notify_with_image
        data:
          title: "Motion Detected"
          message: "Front door camera"
          image_url: "http://www.example.com/example.jpg"
```

### Remote Shutdown
```yaml
automation:
  - alias: "Auto Shutdown at Night"
    trigger:
      - platform: time
        at: "23:00:00"
    action:
      - service: button.press
        target:
          entity_id: button.my_pc_shutdown
```

### Execute Command
```yaml
automation:
  - alias: "Open Notepad"
    trigger:
      - platform: state
        entity_id: input_boolean.open_notepad
        to: "on"
    action:
      - service: esphome.my_pc_run_command
        data:
          command: "notepad.exe"
```

### Control Volume
```yaml
automation:
  - alias: "Lower Volume at Night"
    trigger:
      - platform: time
        at: "22:00:00"
    action:
      - service: esphome.my_pc_set_volume
        data:
          volume: 30
```

## 🛠️ Development

### Build from Source
```bash
# Install dependencies
pip install -r requirements.txt

# Build executable
python setup.py --build

# Output in dist/HomeAssistantWindows.exe
```

### Run Tests
```bash
pytest tests/
```

## 📋 System Requirements

- Windows 10/11
- Python 3.12+ (if running from source)
- Microphone (for voice assistant)
- Network connection to Home Assistant

## 🤝 Contributing

Contributions are welcome! Feel free to submit a Pull Request.

## 📄 License

MIT License

## 🙏 Acknowledgments

- [linux-voice-assistant](https://github.com/OHF-Voice/linux-voice-assistant) - Voice assistant protocol implementation reference
- [ESPHome](https://esphome.io/) - API protocol and Home Assistant integration
- [Home Assistant](https://www.home-assistant.io/) - Smart home platform
