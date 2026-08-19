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
    def test_load_or_create_persists(self, tmp_path):
        recv = SendspinReceiver(name="Test")
        with patch("src.sendspin_player.player.get_user_data_dir", return_value=tmp_path):
            cid1 = recv._load_or_create_client_id()
            cid2 = recv._load_or_create_client_id()
        assert cid1 == cid2
        assert len(cid1) == 32

    def test_client_id_hex(self, tmp_path):
        recv = SendspinReceiver(name="Test")
        with patch("src.sendspin_player.player.get_user_data_dir", return_value=tmp_path):
            cid = recv._load_or_create_client_id()
        # 128-bit uuid rendered as 32 hex chars
        int(cid, 16)


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
    def test_volume_command(self):
        recv = SendspinReceiver(name="Test")
        with patch.object(SendspinReceiver, "_set_system_volume") as mock_vol:
            recv._on_server_command(_make_command_payload("volume", volume=42))
            mock_vol.assert_called_once_with(42)

    def test_volume_clamped_at_set(self):
        recv = SendspinReceiver(name="Test")
        with patch.object(SendspinReceiver, "_set_system_volume") as mock_vol:
            recv._on_server_command(_make_command_payload("volume", volume=150))
            mock_vol.assert_called_once_with(150)  # clamping happens in _set_system_volume

    def test_mute_command(self):
        recv = SendspinReceiver(name="Test")
        with patch.object(SendspinReceiver, "_set_system_mute") as mock_mute:
            recv._on_server_command(_make_command_payload("mute", mute=True))
            mock_mute.assert_called_once_with(True)

    def test_no_player_payload_ignored(self):
        recv = SendspinReceiver(name="Test")
        payload = MagicMock()
        payload.player = None
        with (
            patch.object(SendspinReceiver, "_set_system_volume") as mock_vol,
            patch.object(SendspinReceiver, "_set_system_mute") as mock_mute,
        ):
            recv._on_server_command(payload)
        mock_vol.assert_not_called()
        mock_mute.assert_not_called()

    def test_volume_clamped_in_helper(self):
        import sys as _sys
        import types

        mock_au = MagicMock()
        dev = MagicMock()
        mock_au.GetSpeakers.return_value = dev

        # Patch the inner `from pycaw.pycaw import AudioUtilities` import.
        pycaw_pkg = types.ModuleType("pycaw")
        pycaw_pkg.__path__ = []
        pycaw_sub = types.ModuleType("pycaw.pycaw")
        pycaw_sub.AudioUtilities = mock_au
        saved = {k: _sys.modules[k] for k in ("pycaw", "pycaw.pycaw") if k in _sys.modules}
        _sys.modules["pycaw"] = pycaw_pkg
        _sys.modules["pycaw.pycaw"] = pycaw_sub
        try:
            SendspinReceiver._set_system_volume(120)
            dev.EndpointVolume.SetMasterVolumeLevelScalar.assert_called_once_with(1.0, None)
            SendspinReceiver._set_system_volume(-5)
            dev.EndpointVolume.SetMasterVolumeLevelScalar.assert_called_with(0.0, None)
        finally:
            for k in ("pycaw", "pycaw.pycaw"):
                if k in saved:
                    _sys.modules[k] = saved[k]
                else:
                    _sys.modules.pop(k, None)


class TestMetadata:
    def test_title_callback(self):
        recv = SendspinReceiver(name="Test")
        received = []
        recv.set_metadata_callback(received.append)
        state = MagicMock()
        metadata = MagicMock()
        metadata.title = "Song Title"
        metadata.artist = "Artist"
        state.metadata = metadata
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
        state.metadata = metadata
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
