# Home Assistant Windows Client

A Windows client that emulates an ESPHome device for Home Assistant integration. Enables voice assistant, system monitoring, and remote control capabilities.

## Features

- **Voice Assistant**: Wake word detection using microWakeWord (same as ESPHome)
- **System Monitoring**: CPU, memory, disk usage sensors
- **Media Player**: Play audio announcements and TTS
- **Remote Control**: Lock screen, shutdown, restart via Home Assistant
- **Notifications**: Windows toast notifications from Home Assistant
- **System Tray**: Runs in background with tray icon

## Requirements

- Windows 10/11
- Python 3.10+
- Home Assistant with ESPHome integration

## Installation

```bash
# Clone the repository
git clone https://github.com/your-repo/ha-windows.git
cd ha-windows

# Install dependencies
pip install -r requirements.txt
```

## Usage

```bash
# Run the client
python start.py

# Or with options
python start.py --name "My-PC" --port 6053 --language en_US
```

## Configuration

The client will be automatically discovered by Home Assistant via mDNS. You can also add it manually:

1. Go to Settings > Devices & Services > Add Integration
2. Search for "ESPHome"
3. Enter the device IP and port (default: 6053)

## Wake Words

Available wake words (from microWakeWord):
- Okay Nabu
- Hey Jarvis
- Alexa
- Hey Mycroft
- Hey Home Assistant
- Okay Computer

Wake word models are stored in `data/wakewords/`.

## Project Structure

```
ha-windows/
├── src/
│   ├── core/           # Core protocol and models
│   │   ├── esphome_protocol.py
│   │   ├── models.py
│   │   └── mdns_discovery.py
│   ├── voice/          # Voice assistant
│   │   ├── wake_word.py
│   │   ├── audio_recorder.py
│   │   └── mpv_player.py
│   ├── sensors/        # System sensors
│   ├── commands/       # Button entities
│   ├── notify/         # Notifications
│   └── ui/             # GUI components
├── data/
│   ├── wakewords/      # Wake word models
│   └── sounds/         # Sound effects
├── start.py
└── requirements.txt
```

## Dependencies

- aioesphomeapi - ESPHome protocol
- pymicro-wakeword - Wake word detection
- soundcard - Audio recording
- pygame - Audio playback
- customtkinter - GUI
- pystray - System tray
- zeroconf - mDNS discovery
- psutil - System monitoring

## License

MIT License
