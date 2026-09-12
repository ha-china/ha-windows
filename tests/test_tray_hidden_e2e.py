"""End-to-end roundtrip for tray-hidden mode with REAL components.

Uses the real SendspinReceiver (on a test port) and the real orchestration
in HomeAssistantWindows._set_tray_icon_hidden, asserting that hide/show
cycles complete without killing the event loop and that features are
actually unloaded and restored (issue #11 follow-up).
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from src.core.models import create_default_state
from src.core.esphome_protocol import ESPHomeServer
from src.main import HomeAssistantWindows


@pytest.fixture
def app(tmp_path, monkeypatch):
    """A real HomeAssistantWindows wired to a real ESPHomeServer.

    Externals that cannot run hermetically are stubbed: the tray (pystray),
    the audio recorder (microphone) and wake word detectors. Sendspin runs
    for real on a test port.
    """
    monkeypatch.setattr(
        "src.sendspin_player.player.DEFAULT_PORT", 18928
    )

    state = create_default_state("repro")
    state.preferences_path = tmp_path / "preferences.json"

    app = HomeAssistantWindows(device_name="repro", port=17053)
    app.api_server = ESPHomeServer(
        host="127.0.0.1", port=17053, device_name="repro", state=state
    )
    app.tray = MagicMock()
    # Real _stop_wake_word_detection is safe on empty state; stub _start so
    # the microphone is never opened.
    started = []

    async def fake_start_wake_word():
        if getattr(state.preferences, "tray_icon_hidden", False):
            return
        started.append("wake_word")
        app._audio_recorder = MagicMock()

    monkeypatch.setattr(app, "_start_wake_word_detection", fake_start_wake_word)
    app._started = started
    yield app, state


@pytest.mark.asyncio
async def test_hide_unloads_and_show_restores(app):
    app, state = app
    loop = asyncio.get_running_loop()
    app._event_loop = loop
    await app.api_server.start()
    try:
        # Show mode: start features like the app would at boot
        await app._start_sendspin()
        await app._start_wake_word_detection()
        assert app.sendspin is not None and app.sendspin.is_running

        # --- HIDE --------------------------------------------------------
        app._set_tray_icon_hidden(True)
        # _stop_sendspin runs as a task on the loop
        for _ in range(50):
            if app.sendspin is None:
                break
            await asyncio.sleep(0.1)
        assert app.sendspin is None, "Sendspin must be unloaded on hide"
        assert state.preferences.tray_icon_hidden is True
        assert state.preferences_path.exists(), "preference must be persisted"
        app.tray.set_icon_visible.assert_called_with(False)
        assert app._audio_recorder is None, "recorder must be released"

        # The loop must still be alive and responsive
        await asyncio.sleep(0.5)
        assert loop.is_running() and not loop.is_closed()

        # --- SHOW --------------------------------------------------------
        app._set_tray_icon_hidden(False)
        for _ in range(100):
            if app.sendspin is not None and app.sendspin.is_running:
                break
            await asyncio.sleep(0.1)
        assert app.sendspin is not None and app.sendspin.is_running, (
            "Sendspin must be restored on show"
        )
        assert app._started == ["wake_word"], (
            "wake word setup must be re-run on show"
        )
        assert state.preferences.tray_icon_hidden is False
        app.tray.set_icon_visible.assert_called_with(True)

        # The loop must still be alive after the full roundtrip
        await asyncio.sleep(0.5)
        assert loop.is_running() and not loop.is_closed()
    finally:
        if app.sendspin is not None:
            await app._stop_sendspin()
        app._stop_wake_word_detection()
        await app.api_server.stop()
