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
    def test_pcm_chunk_queued(self):
        recv = SendspinReceiver(name="Test")
        recv._audio_queue = asyncio.Queue()
        audio_format = MagicMock()
        audio_format.codec.value = "pcm"
        recv._on_audio_chunk(0, b"\x00" * 4800, audio_format)
        assert not recv._audio_queue.empty()

    def test_non_pcm_chunk_dropped(self):
        recv = SendspinReceiver(name="Test")
        recv._audio_queue = asyncio.Queue()
        audio_format = MagicMock()
        audio_format.codec.value = "flac"
        recv._on_audio_chunk(0, b"\x00" * 4800, audio_format)
        assert recv._audio_queue.empty()

    def test_chunk_ignored_when_no_stream(self):
        recv = SendspinReceiver(name="Test")
        recv._audio_queue = None
        audio_format = MagicMock()
        audio_format.codec.value = "pcm"
        recv._on_audio_chunk(0, b"\x00" * 4800, audio_format)  # should not raise


class TestPlayback:
    @pytest.mark.asyncio
    async def test_playback_loop_writes_to_stream(self):
        import numpy as np

        recv = SendspinReceiver(name="Test")
        recv._audio_queue = asyncio.Queue()
        recv._client = MagicMock()

        mock_stream = MagicMock()
        mock_sd = MagicMock()
        mock_sd.OutputStream.return_value = mock_stream

        with (
            patch.dict("sys.modules", {"sounddevice": mock_sd}),
            patch.dict("sys.modules", {"numpy": np}),
        ):
            pcm = np.zeros(4800, dtype=np.int16).tobytes()
            await recv._audio_queue.put(pcm)
            await recv._audio_queue.put(None)
            task = asyncio.create_task(recv._playback_loop())
            await asyncio.wait_for(task, timeout=5)

        mock_stream.start.assert_called_once()
        assert mock_stream.write.call_count >= 1
        mock_stream.stop.assert_called_once()
        mock_stream.close.assert_called_once()
