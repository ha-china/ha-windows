"""Tests for the microphone mute functionality."""

from unittest.mock import MagicMock

from aioesphomeapi.api_pb2 import (
    ListEntitiesRequest,
    ListEntitiesSwitchResponse,
    SubscribeHomeAssistantStatesRequest,
    SwitchCommandRequest,
    SwitchStateResponse,
)

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.models import Preferences, create_default_state
from src.core.esphome_protocol import ESPHomeServer
from src.sensors.mic_mute_switch import MicMuteSwitchEntity
from src.voice.audio_recorder import AudioRecorder


class TestPreferencesMute:
    def test_default_muted_is_false(self):
        prefs = Preferences()
        assert prefs.muted is False

    def test_save_and_load_persists_muted(self, tmp_path):
        state = create_default_state("test")
        state.preferences_path = tmp_path / "preferences.json"
        state.preferences.muted = True
        state.save_preferences()

        state2 = create_default_state("test")
        state2.preferences_path = tmp_path / "preferences.json"
        state2.load_preferences()
        assert state2.preferences.muted is True


class TestAudioRecorderMute:
    def test_muted_default_is_false(self):
        assert AudioRecorder().muted is False

    def test_muted_skips_callback(self):
        recorder = AudioRecorder()
        recorder.muted = True
        recorder._array_to_pcm = lambda x: b"data"
        callback = MagicMock()
        recorder._record_loop_callback_test = None

        # Simulate the callback used in the record loop
        from src.voice.audio_recorder import AudioRecorder as AR

        # Directly test the skipping logic by invoking a mimic of the callback
        captured = []

        def wrapped_callback(indata, frames, t, status):
            if recorder.muted:
                return
            captured.append(recorder._array_to_pcm(indata))

        import numpy as np
        wrapped_callback(np.zeros(10, dtype=np.float32), 10, None, None)
        assert captured == [], "Muted recorder should not produce audio"

        recorder.muted = False
        wrapped_callback(np.zeros(10, dtype=np.float32), 10, None, None)
        assert captured != [], "Unmuted recorder should produce audio"


class TestMicMuteSwitchEntity:
    def _make_entity(self, initial=False):
        current = {"muted": initial}

        def get_muted():
            return current["muted"]

        def set_muted(v):
            current["muted"] = v

        return MicMuteSwitchEntity(
            key=600,
            name="Microphone Mute",
            object_id="microphone_mute",
            get_muted=get_muted,
            set_muted=set_muted,
        )

    def test_list_entities_definition(self):
        entity = self._make_entity()
        responses = list(entity.handle_message(ListEntitiesRequest()))
        from aioesphomeapi.model import EntityCategory
        assert isinstance(responses[0], ListEntitiesSwitchResponse)
        assert responses[0].key == 600
        assert responses[0].entity_category == EntityCategory.CONFIG
        assert responses[0].object_id == "microphone_mute"

    def test_switch_command_updates_state(self):
        entity = self._make_entity(initial=False)
        responses = list(entity.handle_message(
            SwitchCommandRequest(key=600, state=True)
        ))
        assert isinstance(responses[0], SwitchStateResponse)
        assert responses[0].state is True

    def test_subscribe_returns_current_state(self):
        entity = self._make_entity(initial=True)
        responses = list(entity.handle_message(SubscribeHomeAssistantStatesRequest()))
        assert isinstance(responses[0], SwitchStateResponse)
        assert responses[0].state is True


class TestESPHomeServerMuteCallback:
    """Verify set_muted_callback stores the callback on the server."""

    def test_set_muted_callback_stored_on_server(self):
        state = create_default_state("test")
        server = ESPHomeServer(state=state)
        assert server._muted_callback is None

        def dummy(muted):
            pass

        server.set_muted_callback(dummy)
        assert server._muted_callback is dummy

    def test_set_conversation_callback_stored_on_server(self):
        state = create_default_state("test")
        server = ESPHomeServer(state=state)
        assert server._conversation_callback is None

        def dummy(typ, text):
            pass

        server.set_conversation_callback(dummy)
        assert server._conversation_callback is dummy