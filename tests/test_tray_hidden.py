"""Tests for tray-hidden (sensors-only) mode (issue #11)."""

import pytest

from aioesphomeapi.api_pb2 import (
    ButtonCommandRequest,
    DeviceInfoRequest,
    ListEntitiesRequest,
    MediaPlayerCommandRequest,
    SubscribeHomeAssistantStatesRequest,
    SwitchCommandRequest,
)

from src.core.models import create_default_state, ServerState
from src.core.esphome_protocol import ESPHomeProtocol


def make_state(tmp_path, tray_icon_hidden: bool) -> ServerState:
    state = create_default_state("test_device")
    state.preferences_path = tmp_path / "preferences.json"
    state.preferences.tray_icon_hidden = tray_icon_hidden
    return state


def make_protocol(tmp_path, tray_icon_hidden: bool) -> ESPHomeProtocol:
    return ESPHomeProtocol(make_state(tmp_path, tray_icon_hidden))


def entity_object_ids(msgs) -> list:
    ids = []
    for m in msgs:
        object_id = getattr(m, "object_id", None)
        if object_id:
            ids.append(object_id)
    return ids


class TestPreferences:
    def test_tray_hidden_round_trip(self, tmp_path):
        state = make_state(tmp_path, tray_icon_hidden=False)
        state.preferences.tray_icon_hidden = True
        state.preferences.output_device = "Headphones"
        state.save_preferences()

        state2 = create_default_state("test_device")
        state2.preferences_path = state.preferences_path
        state2.load_preferences()

        assert state2.preferences.tray_icon_hidden is True
        assert (
            state2.preferences.output_device == "Headphones"
        ), "output_device must persist (was silently dropped before the fix)"

    def test_default_visible(self, tmp_path):
        state = make_state(tmp_path, tray_icon_hidden=False)
        assert state.preferences.tray_icon_hidden is False


class TestEntityGating:
    """In tray-hidden mode only sensors + the Tray Icon switch are served."""

    FUNC_ENTITY_IDS = (
        "windows_media_player",
        "shutdown",
        "restart",
        "screenshot",
        "thinking_sound",
        "microphone_mute",
        "voice_input_hotkey",
    )

    def test_visible_mode_lists_functional_entities(self, tmp_path):
        protocol = make_protocol(tmp_path, tray_icon_hidden=False)
        msgs = list(protocol.handle_message(ListEntitiesRequest()))
        ids = entity_object_ids(msgs)

        for object_id in self.FUNC_ENTITY_IDS:
            assert object_id in ids, f"{object_id} missing in normal mode"

    def test_hidden_mode_lists_only_sensors_and_tray_switch(self, tmp_path):
        protocol = make_protocol(tmp_path, tray_icon_hidden=True)
        msgs = list(protocol.handle_message(ListEntitiesRequest()))
        ids = entity_object_ids(msgs)

        assert "tray_icon" in ids, "Tray Icon switch must stay available to restore"
        for object_id in self.FUNC_ENTITY_IDS:
            assert object_id not in ids, f"{object_id} must be unloaded in hidden mode"

    def test_hidden_mode_clears_va_feature_flags(self, tmp_path):
        protocol = make_protocol(tmp_path, tray_icon_hidden=True)
        msgs = list(protocol.handle_message(DeviceInfoRequest()))

        flags = [getattr(m, "voice_assistant_feature_flags", None) for m in msgs]
        flags = [f for f in flags if f is not None]
        assert flags and all(f == 0 for f in flags), f"VA flags must be 0: {flags}"

    def test_visible_mode_keeps_va_feature_flags(self, tmp_path):
        protocol = make_protocol(tmp_path, tray_icon_hidden=False)
        msgs = list(protocol.handle_message(DeviceInfoRequest()))

        flags = [getattr(m, "voice_assistant_feature_flags", None) for m in msgs]
        flags = [f for f in flags if f is not None]
        assert flags and all(f > 0 for f in flags), f"VA flags must be set: {flags}"

    def test_hidden_mode_subscribe_states_only_sensors_and_switch(self, tmp_path):
        protocol = make_protocol(tmp_path, tray_icon_hidden=True)
        list(protocol.handle_message(ListEntitiesRequest()))
        msgs = list(protocol.handle_message(SubscribeHomeAssistantStatesRequest()))

        # Only sensor state keys + tray switch state key (701) expected
        state_keys = {getattr(m, "key", None) for m in msgs}
        assert 701 in state_keys, "Tray Icon switch state must be pushed"
        functional_keys = {100, 101, 120, 300, 400, 500, 600}
        assert not (state_keys & functional_keys), f"Functional entity states leaked: {state_keys & functional_keys}"

    def test_switch_commands_ignored_for_unloaded_entities(self, tmp_path):
        protocol = make_protocol(tmp_path, tray_icon_hidden=True)
        list(protocol.handle_message(ListEntitiesRequest()))

        msgs = list(protocol.handle_message(SwitchCommandRequest(key=600, state=True)))
        assert not msgs, "mic mute switch must not respond in hidden mode"

        msgs = list(protocol.handle_message(MediaPlayerCommandRequest(key=300, command=0)))
        assert not msgs, "media player must not respond in hidden mode"

        msgs = list(protocol.handle_message(ButtonCommandRequest(key=100)))
        assert not msgs, "buttons must not respond in hidden mode"

    def test_tray_icon_switch_responds_in_hidden_mode(self, tmp_path):
        """The switch is the restore path and must always work (ON = hidden)."""
        protocol = make_protocol(tmp_path, tray_icon_hidden=True)
        list(protocol.handle_message(ListEntitiesRequest()))

        msgs = list(protocol.handle_message(SwitchCommandRequest(key=701, state=True)))

        assert msgs, "Tray Icon switch must respond in hidden mode"
        assert getattr(msgs[0], "state", None) is True

    def test_switch_state_tracks_mode_flag(self, tmp_path):
        """Regression: switch state must match the mode flag exactly.

        An earlier version inverted the semantics so turning the switch off
        was a no-op and the state bounced back on the next state push.
        """
        protocol = make_protocol(tmp_path, tray_icon_hidden=False)
        invoked = []
        protocol.set_tray_hidden_callback(lambda hidden: invoked.append(hidden))
        list(protocol.handle_message(ListEntitiesRequest()))

        msgs = list(protocol.handle_message(SwitchCommandRequest(key=701, state=True)))
        assert invoked == [True], f"ON must signal hidden=True, got {invoked}"
        assert msgs and getattr(msgs[0], "state", None) is True

        invoked.clear()
        msgs = list(protocol.handle_message(SwitchCommandRequest(key=701, state=False)))
        assert invoked == [False], f"OFF must signal hidden=False, got {invoked}"
        assert msgs and getattr(msgs[0], "state", None) is False

    def test_tray_icon_switch_has_no_entity_category(self, tmp_path):
        """No category: HA must group the switch under 'Controls'."""
        from aioesphomeapi.model import EntityCategory

        protocol = make_protocol(tmp_path, tray_icon_hidden=False)
        msgs = list(protocol.handle_message(ListEntitiesRequest()))

        switch_defs = [m for m in msgs if getattr(m, "object_id", "") == "tray_icon"]
        assert switch_defs, "tray_icon switch definition missing"
        assert getattr(switch_defs[0], "entity_category", None) in (
            None,
            EntityCategory.NONE,
        ), "tray_icon must not be a CONFIG entity (belongs in Controls)"

    def test_tray_icon_switch_name_is_localized(self, tmp_path):
        protocol = make_protocol(tmp_path, tray_icon_hidden=False)
        msgs = list(protocol.handle_message(ListEntitiesRequest()))

        switch_defs = [m for m in msgs if getattr(m, "object_id", "") == "tray_icon"]
        assert switch_defs, "tray_icon switch definition missing"
        assert getattr(switch_defs[0], "name", ""), "switch must have a name"


class TestTrayIconRepaintGuard:
    """Regression: phase changes after an HA reconnect must not resurrect
    a hidden tray icon (_replace_icon used to re-add it unconditionally)."""

    def _make_tray(self):
        from src.ui.system_tray_icon import SystemTrayIcon

        tray = SystemTrayIcon()
        tray._status_info = {"name": "n", "ip": "1.2.3.4", "port": "6053"}
        tray._current_phase = SystemTrayIcon.PHASE_IDLE
        return tray

    def test_replace_icon_suppressed_when_hidden(self, monkeypatch):
        from types import SimpleNamespace

        from src.ui import system_tray_icon as sti

        tray = self._make_tray()
        calls = []
        monkeypatch.setattr(
            sti,
            "_shell32",
            SimpleNamespace(Shell_NotifyIconW=lambda cmd, nid: calls.append(cmd)),
        )
        monkeypatch.setattr(
            sti,
            "_user32",
            SimpleNamespace(LoadImageW=lambda *a, **k: 42, DestroyIcon=lambda h: None),
        )

        tray._icon_visible = False
        tray._replace_icon(123)
        assert calls == [], "hidden icon must not be re-added"

        tray._icon_visible = True
        tray._replace_icon(123)
        assert len(calls) == 2, "visible icon must be deleted + re-added"

    def test_set_icon_visible_tracks_intent_without_icon(self):
        tray = self._make_tray()

        tray.set_icon_visible(False)
        assert tray._icon_visible is False, "intent must be tracked even when the pystray icon is missing"
