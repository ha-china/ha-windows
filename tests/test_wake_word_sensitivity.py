"""Tests for the wake word sensitivity number entity and detector mapping."""

import sys
import os
from types import SimpleNamespace
from unittest.mock import MagicMock

from aioesphomeapi.api_pb2 import (
    ListEntitiesNumberResponse,
    ListEntitiesRequest,
    NumberCommandRequest,
    NumberStateResponse,
    SubscribeHomeAssistantStatesRequest,
)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.models import Preferences, WakeWordType, create_default_state
from src.core.esphome_protocol import ESPHomeProtocol, ESPHomeServer
from src.sensors.wake_word_sensitivity_number import WakeWordSensitivityNumberEntity
from src.voice.wake_word import WakeWordDetector


class TestPreferencesSensitivity:
    def test_default_sensitivity(self):
        prefs = Preferences()
        assert prefs.wake_word_sensitivity == 0.5

    def test_save_and_load_persists_sensitivity(self, tmp_path):
        state = create_default_state("test")
        state.preferences_path = tmp_path / "preferences.json"
        state.preferences.wake_word_sensitivity = 0.8
        state.save_preferences()

        state2 = create_default_state("test")
        state2.preferences_path = tmp_path / "preferences.json"
        state2.load_preferences()
        assert state2.preferences.wake_word_sensitivity == 0.8

    def test_load_clamps_out_of_range_values(self, tmp_path):
        import json

        prefs_file = tmp_path / "preferences.json"
        prefs_file.write_text(json.dumps({"wake_word_sensitivity": 7.5}), encoding="utf-8")

        state = create_default_state("test")
        state.preferences_path = prefs_file
        state.load_preferences()
        assert state.preferences.wake_word_sensitivity == 1.0

    def test_load_falls_back_on_garbage(self, tmp_path):
        import json

        prefs_file = tmp_path / "preferences.json"
        prefs_file.write_text(json.dumps({"wake_word_sensitivity": "loud"}), encoding="utf-8")

        state = create_default_state("test")
        state.preferences_path = prefs_file
        state.load_preferences()
        assert state.preferences.wake_word_sensitivity == 0.5


class TestWakeWordSensitivityNumberEntity:
    def _make_entity(self, initial=0.5):
        current = {"sensitivity": initial}
        return WakeWordSensitivityNumberEntity(
            key=800,
            name="Wake Word Sensitivity",
            object_id="wake_word_sensitivity",
            get_sensitivity=lambda: current["sensitivity"],
            set_sensitivity=lambda v: current.__setitem__("sensitivity", v),
        ), current

    def test_list_entities_definition(self):
        entity, _ = self._make_entity()
        responses = list(entity.handle_message(ListEntitiesRequest()))
        from aioesphomeapi.model import EntityCategory, NumberMode
        assert isinstance(responses[0], ListEntitiesNumberResponse)
        assert responses[0].key == 800
        assert responses[0].entity_category == EntityCategory.CONFIG
        assert responses[0].mode == NumberMode.SLIDER
        assert responses[0].min_value == 0.0
        assert responses[0].max_value == 1.0

    def test_number_command_updates_state(self):
        entity, current = self._make_entity()
        responses = list(entity.handle_message(NumberCommandRequest(key=800, state=0.9)))
        assert isinstance(responses[0], NumberStateResponse)
        assert abs(responses[0].state - 0.9) < 0.001
        assert abs(current["sensitivity"] - 0.9) < 0.001

    def test_number_command_clamps_out_of_range(self):
        entity, current = self._make_entity()
        responses = list(entity.handle_message(NumberCommandRequest(key=800, state=2.0)))
        assert responses[0].state == 1.0
        assert current["sensitivity"] == 1.0

    def test_number_command_ignores_other_keys(self):
        entity, current = self._make_entity(initial=0.5)
        list(entity.handle_message(NumberCommandRequest(key=999, state=0.1)))
        assert current["sensitivity"] == 0.5

    def test_subscribe_returns_current_state(self):
        entity, _ = self._make_entity(initial=0.3)
        responses = list(entity.handle_message(SubscribeHomeAssistantStatesRequest()))
        assert isinstance(responses[0], NumberStateResponse)
        assert abs(responses[0].state - 0.3) < 0.001


class TestWakeWordDetectorSensitivity:
    def _bare_detector(self):
        # A detector whose model failed to load: exercises pure mapping logic
        return WakeWordDetector("definitely_not_a_real_model")

    def test_default_sensitivity(self):
        detector = self._bare_detector()
        assert detector.sensitivity == 0.5

    def test_set_sensitivity_maps_to_cutoff(self):
        detector = self._bare_detector()
        detector.set_sensitivity(0.8)
        assert abs(detector.sensitivity - 0.8) < 0.001

    def test_set_sensitivity_clamps(self):
        detector = self._bare_detector()
        detector.set_sensitivity(3.0)
        assert detector.sensitivity == 1.0
        detector.set_sensitivity(-1.0)
        assert detector.sensitivity == 0.0

    def test_sensitivity_updates_micro_model_cutoff(self):
        detector = self._bare_detector()
        detector._detector_type = WakeWordType.MICRO_WAKE_WORD
        detector._model = SimpleNamespace(probability_cutoff=0.97)
        detector.set_sensitivity(0.3)
        assert abs(detector._model.probability_cutoff - 0.7) < 0.001


class TestProtocolSensitivityCallback:
    """Verify the protocol persists sensitivity and notifies the callback."""

    def _make_protocol(self, tmp_path):
        state = create_default_state("test")
        state.preferences_path = tmp_path / "preferences.json"
        return ESPHomeProtocol(state), state

    def test_set_wake_word_sensitivity_persists_and_notifies(self, tmp_path):
        protocol, state = self._make_protocol(tmp_path)
        callback = MagicMock()
        protocol.set_wake_word_sensitivity_callback(callback)

        protocol._set_wake_word_sensitivity(0.75)

        assert abs(state.preferences.wake_word_sensitivity - 0.75) < 0.001
        assert state.preferences_path.exists()
        callback.assert_called_once()
        assert abs(callback.call_args[0][0] - 0.75) < 0.001

    def test_set_wake_word_sensitivity_clamps_before_persist(self, tmp_path):
        protocol, state = self._make_protocol(tmp_path)
        protocol._set_wake_word_sensitivity(42.0)
        assert state.preferences.wake_word_sensitivity == 1.0


class TestESPHomeServerSensitivityCallback:
    """Verify set_wake_word_sensitivity_callback stores the callback on the server."""

    def test_set_wake_word_sensitivity_callback_stored_on_server(self):
        state = create_default_state("test")
        server = ESPHomeServer(state=state)
        assert server._wake_word_sensitivity_callback is None

        dummy = MagicMock()
        server.set_wake_word_sensitivity_callback(dummy)
        assert server._wake_word_sensitivity_callback is dummy
