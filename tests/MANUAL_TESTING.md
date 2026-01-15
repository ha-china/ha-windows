# Manual Testing Guide for Home Assistant Windows Client

## Task 16.2: 在真实 Home Assistant 环境中测试

This guide describes how to test the Windows client with a real Home Assistant instance.

## Prerequisites

1. **Home Assistant** running on the same network
2. **ESPHome integration** installed in Home Assistant
3. **Python dependencies** installed: `pip install -r requirements.txt`

## Quick Start

Run the manual test script:

```bash
python tests/manual_ha_test.py --name "My_Windows_PC"
```

## Test Checklist

### 1. Device Discovery (Requirement 1)

- [ ] Start the Windows client
- [ ] Open Home Assistant > Settings > Devices & Services
- [ ] Click "Add Integration" and search for "ESPHome"
- [ ] Verify the device is discovered automatically
- [ ] Verify connection completes without password

**Expected Result:** Device appears in ESPHome integration with correct name.

### 2. Sensor Entities (Requirement 5)

After connection, verify these sensors appear in Home Assistant:

- [ ] CPU Usage (%)
- [ ] Memory Usage (%)
- [ ] Disk Usage (%)
- [ ] Network Status
- [ ] Battery Level (if laptop)
- [ ] Battery Status (if laptop)

**Expected Result:** All sensors show valid values and update periodically.

### 3. MediaPlayer Entity (Requirement 7)

- [ ] Verify MediaPlayer entity appears in HA
- [ ] Test Play/Pause controls
- [ ] Test Volume slider
- [ ] Test Mute toggle

**Expected Result:** MediaPlayer controls affect Windows system audio.

### 4. Voice Assistant (Requirement 2)

If wake word detection is configured:

- [ ] Say the wake word (e.g., "OK Nabu")
- [ ] Verify audio is streamed to HA
- [ ] Verify TTS response is played on Windows

**Expected Result:** Complete voice conversation works end-to-end.

### 5. Announcements (Requirement 3)

From Home Assistant:

1. Go to Developer Tools > Services
2. Call `tts.speak` or `notify.send_message` targeting the Windows device
3. Verify announcement plays on Windows

- [ ] Announcement audio plays
- [ ] Pre-announce chime plays (if configured)
- [ ] Volume is ducked during announcement
- [ ] Volume is restored after announcement

**Expected Result:** TTS announcements play correctly with audio ducking.

### 6. Timer Support (Requirement 4)

- [ ] Set a timer via voice command
- [ ] Wait for timer to finish
- [ ] Verify timer finished sound plays
- [ ] Say "stop" to stop the timer sound

**Expected Result:** Timer events trigger sound playback.

### 7. Connection Stability (Requirement 11)

- [ ] Leave connection running for 10+ minutes
- [ ] Verify no disconnections
- [ ] Test reconnection after network interruption

**Expected Result:** Connection remains stable; auto-reconnects if dropped.

### 8. Windows Notifications (Requirement 10)

- [ ] Send notification from HA to Windows client
- [ ] Verify Toast notification appears
- [ ] Verify title and message are correct
- [ ] Test notification with image (if supported)

**Expected Result:** Windows Toast notifications display correctly.

## Troubleshooting

### Device Not Discovered

1. Check firewall allows port 6053
2. Verify both devices on same network/subnet
3. Check mDNS is not blocked

### Connection Fails

1. Check no other ESPHome device using same name
2. Verify port 6053 is not in use
3. Check Windows Defender/antivirus settings

### Voice Assistant Not Working

1. Verify microphone permissions
2. Check audio input device is correct
3. Verify wake word model is loaded

### No Audio Playback

1. Check audio output device
2. Verify MPV is installed (if using MPV player)
3. Check volume is not muted

## Test Results

Record your test results:

| Test | Status | Notes |
|------|--------|-------|
| Device Discovery | ⬜ | |
| Sensor Entities | ⬜ | |
| MediaPlayer Entity | ⬜ | |
| Voice Assistant | ⬜ | |
| Announcements | ⬜ | |
| Timer Support | ⬜ | |
| Connection Stability | ⬜ | |
| Windows Notifications | ⬜ | |

Legend: ✅ Pass | ❌ Fail | ⬜ Not Tested
