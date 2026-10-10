"""Tests for the wake word sensitivity number entity and detector mapping."""

import sys
import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np

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
from src.voice.wake_word import (
    CUTOFF_FLOORS,
    DEFAULT_CUTOFF_FLOOR,
    DEFAULT_WAKE_WORD_SENSITIVITY,
    WakeWordDetector,
)


class TestPreferencesSensitivity:
    def test_default_sensitivity(self):
        prefs = Preferences()
        # 0.5 ≈ HA Voice PE "Moderately sensitive" on the manifest-anchored scale
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
        assert state.preferences.wake_word_sensitivity == DEFAULT_WAKE_WORD_SENSITIVITY


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
        assert detector.sensitivity == DEFAULT_WAKE_WORD_SENSITIVITY == 0.5

    def test_set_sensitivity_clamps(self):
        detector = self._bare_detector()
        detector.set_sensitivity(3.0)
        assert detector.sensitivity == 1.0
        detector.set_sensitivity(-1.0)
        assert detector.sensitivity == 0.0

    def test_sensitivity_zero_keeps_manifest_cutoff(self):
        detector = self._bare_detector()
        detector._detector_type = WakeWordType.MICRO_WAKE_WORD
        detector._model = SimpleNamespace(probability_cutoff=0.97)
        detector._manifest_cutoff = 0.97
        detector.set_sensitivity(0.0)
        assert abs(detector._model.probability_cutoff - 0.97) < 0.001

    def test_sensitivity_one_lands_on_tuned_floor(self):
        # hey_jarvis floor mirrors Voice PE "Very sensitive" (0.83)
        detector = self._bare_detector()
        detector.model_name = "hey_jarvis"
        detector._detector_type = WakeWordType.MICRO_WAKE_WORD
        detector._model = SimpleNamespace(probability_cutoff=0.97)
        detector._manifest_cutoff = 0.97
        detector.set_sensitivity(1.0)
        assert abs(detector._model.probability_cutoff - CUTOFF_FLOORS["hey_jarvis"]) < 0.001

    def test_sensitivity_interpolates_linearly(self):
        detector = self._bare_detector()
        detector.model_name = "hey_jarvis"
        detector._detector_type = WakeWordType.MICRO_WAKE_WORD
        detector._model = SimpleNamespace(probability_cutoff=0.97)
        detector._manifest_cutoff = 0.97
        detector.set_sensitivity(0.5)
        expected = 0.97 - (0.97 - CUTOFF_FLOORS["hey_jarvis"]) * 0.5
        assert abs(detector._model.probability_cutoff - expected) < 0.001

    def test_floor_clamped_to_manifest(self):
        # A model whose manifest is below the generic floor never gets a
        # cutoff above its manifest (0 = manifest default)
        detector = WakeWordDetector("definitely_not_a_real_model")
        detector._detector_type = WakeWordType.MICRO_WAKE_WORD
        detector._model = SimpleNamespace(probability_cutoff=0.55)
        detector._manifest_cutoff = 0.55
        detector.set_sensitivity(1.0)
        assert abs(detector._model.probability_cutoff - 0.55) < 0.001

    def test_unknown_model_uses_generic_floor(self):
        detector = self._bare_detector()
        detector._detector_type = WakeWordType.MICRO_WAKE_WORD
        detector._model = SimpleNamespace(probability_cutoff=0.9)
        detector._manifest_cutoff = 0.9
        detector.set_sensitivity(1.0)
        assert abs(detector._model.probability_cutoff - min(DEFAULT_CUTOFF_FLOOR, 0.9)) < 0.001

    def test_open_wakeword_uses_own_anchor_and_floor(self):
        detector = self._bare_detector()
        detector._detector_type = WakeWordType.OPEN_WAKE_WORD
        detector._manifest_cutoff = 0.5
        detector.set_sensitivity(0.0)
        assert abs(detector._probability_cutoff - 0.5) < 0.001
        detector.set_sensitivity(1.0)
        assert abs(detector._probability_cutoff - 0.35) < 0.001


class TestWakeWordDetectorVadGate:
    def _gated_detector(self, vad_prob, vad_cutoff=0.5):
        """A micro detector with stubbed wake + VAD models."""
        detector = WakeWordDetector("definitely_not_a_real_model", enable_vad=True)
        detector._detector_type = WakeWordType.MICRO_WAKE_WORD
        detector._model = SimpleNamespace(
            probability_cutoff=0.9,
            process_streaming=lambda feature: True,  # wake word fires every frame
        )
        detector._features = SimpleNamespace(process_streaming=lambda chunk: [np.zeros((1, 1, 1))])
        if vad_prob is None:
            detector._vad_model = None
            detector._vad_features = None
        else:
            detector._vad_model = SimpleNamespace(
                probability_cutoff=vad_cutoff,
                process_streaming_prob=lambda feature: vad_prob,
            )
            detector._vad_features = SimpleNamespace(
                process_streaming=lambda chunk: [np.zeros((1, 1, 1))]
            )
        return detector

    def test_vad_blocks_wake_word_without_speech(self):
        detector = self._gated_detector(vad_prob=0.1)
        assert detector.process_audio(b"\x00\x00" * 160) is False

    def test_vad_allows_wake_word_with_speech(self):
        detector = self._gated_detector(vad_prob=0.9)
        assert detector.process_audio(b"\x00\x00" * 160) is True

    def test_vad_unavailable_never_blocks(self):
        detector = self._gated_detector(vad_prob=None)
        assert detector.process_audio(b"\x00\x00" * 160) is True

    def test_vad_gate_suppresses_callback(self):
        detector = self._gated_detector(vad_prob=0.1)
        callback = MagicMock()
        detector.on_wake_word(callback)
        detector.process_audio(b"\x00\x00" * 160)
        callback.assert_not_called()

    def test_vad_gate_feeds_audio_to_vad_stream(self):
        detector = self._gated_detector(vad_prob=0.9)
        fed = []
        detector._vad_features = SimpleNamespace(process_streaming=lambda chunk: fed.append(chunk) or [])
        detector.process_audio(b"\x00\x00" * 160)
        assert fed == [b"\x00\x00" * 160]


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
