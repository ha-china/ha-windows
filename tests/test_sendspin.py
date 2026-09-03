"""Tests for the Sendspin audio receiver.

These tests cover the logic that does not require a real Music Assistant
server: client id persistence, server command handling (volume/mute), metadata
callbacks, audio chunk queueing and device info parsing.
"""

import asyncio
import os
import sys
import winreg
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from src.sendspin_player import player as player_module
from src.sendspin_player.player import SendspinReceiver


class TestClientId:
    def test_load_or_create_identity_persists(self, tmp_path):
        recv = SendspinReceiver(name="Test")
        with patch("src.sendspin_player.player.get_user_data_dir", return_value=tmp_path):
            ident1 = recv._load_or_create_identity()
            ident2 = recv._load_or_create_identity()
        assert ident1.peer_id == ident2.peer_id

    def test_identity_peer_id_is_base64url(self, tmp_path):
        import re

        recv = SendspinReceiver(name="Test")
        with patch("src.sendspin_player.player.get_user_data_dir", return_value=tmp_path):
            ident = recv._load_or_create_identity()
        # base64url, unpadded, ~43 chars
        assert re.fullmatch(r"[A-Za-z0-9_-]{43}", ident.peer_id)


class TestDeviceInfo:
    @patch("winreg.OpenKey")
    @patch("winreg.QueryValueEx")
    def test_parses_hardware(self, mock_query, mock_open):
        mock_query.side_effect = [
            ("Micro-Star International Co., Ltd.", winreg.REG_SZ),
            ("MS-7C67", winreg.REG_SZ),
        ]
        product, manufacturer = player_module.get_device_info()
        assert product == "MS-7C67"
        assert manufacturer == "Micro-Star International Co., Ltd."

    @patch("winreg.OpenKey", side_effect=OSError("boom"))
    def test_fallback_on_error(self, mock_open):
        product, manufacturer = player_module.get_device_info()
        assert product == "Windows PC"
        assert manufacturer == "Microsoft"

    def test_get_hostname(self):
        name = player_module.get_hostname()
        assert name and len(name) > 0


def _make_command_payload(command_value: str, **fields):
    """Build a ServerCommandPayload-like object with the given player command."""
    payload = MagicMock()
    player_cmd = MagicMock()
    command = MagicMock()
    command.value = command_value
    player_cmd.command = command
    for key, value in fields.items():
        setattr(player_cmd, key, value)
    payload.player = player_cmd
    return payload


class TestServerCommand:
    def _playing_receiver(self):
        recv = SendspinReceiver(name="Test")
        recv._playing = True  # server volume/mute only applies while playing
        return recv

    def test_volume_command_while_playing(self):
        recv = self._playing_receiver()
        volumes = []
        recv.set_volume_callback(lambda vol, muted: volumes.append((vol, muted)))
        with patch.object(SendspinReceiver, "_report_player_state"):
            recv._on_server_command(_make_command_payload("volume", volume=42))
        assert recv.volume_percent == 42
        assert volumes == [(42, False)]

    def test_volume_command_ignored_while_stopped(self):
        """MA replays stored volume/mute at connect; nothing is playing then,
        so the system volume must stay untouched (launch-mute regression)."""
        recv = SendspinReceiver(name="Test")
        volumes = []
        recv.set_volume_callback(lambda vol, muted: volumes.append((vol, muted)))
        recv._set_system_volume = MagicMock()
        recv._set_system_mute = MagicMock()
        with patch.object(SendspinReceiver, "_report_player_state"):
            recv._on_server_command(_make_command_payload("volume", volume=42))
            recv._on_server_command(_make_command_payload("mute", mute=True))
        recv._set_system_volume.assert_not_called()
        recv._set_system_mute.assert_not_called()
        assert volumes == []

    def test_volume_clamped_at_set(self):
        recv = self._playing_receiver()
        with patch.object(SendspinReceiver, "_report_player_state"):
            recv._on_server_command(_make_command_payload("volume", volume=150))
        assert recv.volume_percent == 100

    def test_mute_command_while_playing(self):
        recv = self._playing_receiver()
        volumes = []
        recv.set_volume_callback(lambda vol, muted: volumes.append((vol, muted)))
        with patch.object(SendspinReceiver, "_report_player_state"):
            recv._on_server_command(_make_command_payload("mute", mute=True))
        assert recv._muted is True
        assert volumes == [(recv.volume_percent, True)]

    def test_no_player_payload_ignored(self):
        recv = SendspinReceiver(name="Test")
        payload = MagicMock()
        payload.player = None
        with (
            patch.object(SendspinReceiver, "_notify_volume") as mock_notify,
        ):
            recv._on_server_command(payload)
        mock_notify.assert_not_called()

    def test_apply_local_volume_mutes_at_zero(self):
        recv = SendspinReceiver(name="Test")
        recv.apply_local_volume(0)
        assert recv.volume_percent == 0
        assert recv._muted is True
        recv.apply_local_volume(30)
        assert recv._muted is False


class TestMetadata:
    def test_title_callback(self):
        recv = SendspinReceiver(name="Test")
        received = []
        recv.set_metadata_callback(received.append)
        state = MagicMock()
        metadata = MagicMock()
        metadata.title = "Song Title"
        metadata.artist = "Artist"
        metadata.progress = None
        state.metadata = metadata
        with patch.object(SendspinReceiver, "_set_playing"):
            recv._on_metadata(state)
        assert received == [{"title": "Song Title", "artist": "Artist"}]

    def test_artist_fallback(self):
        recv = SendspinReceiver(name="Test")
        received = []
        recv.set_metadata_callback(received.append)
        state = MagicMock()
        metadata = MagicMock()
        metadata.title = None
        metadata.artist = "Artist Name"
        metadata.progress = None
        state.metadata = metadata
        with patch.object(SendspinReceiver, "_set_playing"):
            recv._on_metadata(state)
        assert received == [{"title": "", "artist": "Artist Name"}]

    def test_no_metadata_ignored(self):
        recv = SendspinReceiver(name="Test")
        received = []
        recv.set_metadata_callback(received.append)
        state = MagicMock()
        state.metadata = None
        recv._on_metadata(state)
        assert received == []


class TestAudioChunk:
    def _ready_player(self):
        player = MagicMock()
        player.is_ready.return_value = True
        return player

    def test_pcm_chunk_forwarded_to_player(self):
        recv = SendspinReceiver(name="Test")
        recv._player = self._ready_player()
        audio_format = MagicMock()
        audio_format.codec.value = "pcm"
        recv._on_audio_chunk(12345, b"\x00" * 4800, audio_format)
        recv._player.enqueue.assert_called_once_with(12345, b"\x00" * 4800)

    def test_non_pcm_chunk_dropped(self):
        recv = SendspinReceiver(name="Test")
        recv._player = self._ready_player()
        audio_format = MagicMock()
        audio_format.codec.value = "flac"
        recv._on_audio_chunk(0, b"\x00" * 4800, audio_format)
        recv._player.enqueue.assert_not_called()

    def test_chunk_ignored_when_no_player(self):
        recv = SendspinReceiver(name="Test")
        recv._player = None
        audio_format = MagicMock()
        audio_format.codec.value = "pcm"
        recv._on_audio_chunk(0, b"\x00" * 4800, audio_format)  # should not raise


class TestPlayback:
    """The playback path is PortAudio callback mode (SyncAudioPlayer); these
    tests drive the callback directly instead of an asyncio loop."""

    def _make_player(self, compute_play_time=None, now_us=0):
        from src.sendspin_player.sync_audio_player import SyncAudioPlayer

        player = SyncAudioPlayer(
            compute_play_time=compute_play_time or (lambda ts: ts),
            now_us=lambda: now_us,
            is_synced=lambda: True,
            on_skew=lambda ms, ok: None,
        )
        player._stream = MagicMock()  # pretend started so enqueue() accepts data
        player._started = True
        player._stream.time = 0.0
        return player

    def _out_buffer(self, frames=2048):
        import ctypes

        return (ctypes.c_char * (frames * 4))()  # int16 stereo

    def _silence(self, frames=2048):
        return b"\x00" * (frames * 4)

    def test_callback_fills_silence_before_startup_buffer(self):
        player = self._make_player(now_us=60_000_000)
        for i in range(12):  # below _MIN_CHUNKS_TO_START(16)
            player.enqueue(i * 10000, b"\x01" * 4800)

        out = self._out_buffer()
        mock_time = MagicMock()
        mock_time.outputBufferDacTime = 100.0
        player._audio_callback(out, 2048, mock_time, None)

        # Start gate: not enough buffered chunks yet -> pure silence
        assert out.raw == self._silence()

    def test_callback_writes_pcm_when_due_and_buffered(self):
        player = self._make_player(now_us=60_000_000)
        for i in range(16):  # reach the startup threshold
            player.enqueue(1000 + i * 10000, b"\x01" * 4800)  # due (play_at << now)

        out = self._out_buffer()
        mock_time = MagicMock()
        mock_time.outputBufferDacTime = 100.0
        player._audio_callback(out, 2048, mock_time, None)

        # 16 due chunks -> real PCM written, not silence
        assert out.raw != self._silence()
        assert b"\x01" in out.raw

    def test_callback_respects_schedule(self):
        player = self._make_player(now_us=0)
        # Scheduled far in the future: play_at = ts >> loop_us(0)
        for i in range(16):
            player.enqueue(61_000_000 + i * 10000, b"\x01" * 4800)

        out = self._out_buffer()
        mock_time = MagicMock()
        mock_time.outputBufferDacTime = 0.0
        player._audio_callback(out, 2048, mock_time, None)

        # Not due yet -> pure silence (future-scheduled chunks wait)
        assert out.raw == self._silence()
