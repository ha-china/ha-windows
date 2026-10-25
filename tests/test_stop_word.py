"""Regression tests for the stop-word interrupt chain (issue #17).

state.stop_word must be armed at startup (main.py loads the shipped "stop"
model); without it every branch guarded on it stays dead and saying "stop"
can never interrupt playback. These tests cover the model files, the
activation around TTS/timer/announce playback, and the hotkey-cancel path.
"""

from unittest.mock import MagicMock, patch

from aioesphomeapi.api_pb2 import VoiceAssistantAnnounceRequest
from aioesphomeapi.model import VoiceAssistantTimerEventType

from src.core.esphome_protocol import ESPHomeProtocol
from src.core.models import create_default_state


def make_protocol() -> ESPHomeProtocol:
    protocol = ESPHomeProtocol(create_default_state("test_device"))
    protocol.state.tts_player = MagicMock()
    protocol.state.music_player = MagicMock()
    return protocol


def arm_stop_word(protocol: ESPHomeProtocol) -> None:
    """Mirror what main.py does at startup."""
    from src.voice.wake_word import load_wake_word

    protocol.state.stop_word = load_wake_word("stop")


def activate_stop_word(protocol: ESPHomeProtocol) -> None:
    protocol.state.active_wake_words.add(protocol.state.stop_word.id)


class TestStopWordModel:
    def test_stop_model_ships_and_loads(self):
        """The internal 'stop' model must be loadable even though it is
        hidden from the public wake word list (INTERNAL_WAKE_WORD_IDS)."""
        from src.voice.wake_word import load_wake_word

        stop = load_wake_word("stop")
        assert stop is not None
        assert stop.id == "stop"

    def test_stop_model_hidden_from_public_list(self):
        from src.voice.wake_word import load_available_wake_words

        assert "stop" not in load_available_wake_words()


class TestStopWordActivation:
    def test_play_tts_activates_stop_word(self):
        protocol = make_protocol()
        arm_stop_word(protocol)

        protocol._tts_url = "http://example.com/tts.mp3"
        protocol.play_tts()

        assert protocol.state.stop_word.id in protocol.state.active_wake_words

    def test_tts_finished_deactivates_stop_word(self):
        protocol = make_protocol()
        arm_stop_word(protocol)
        activate_stop_word(protocol)
        protocol._is_playing_tts = True

        protocol._tts_finished()

        assert protocol.state.stop_word.id not in protocol.state.active_wake_words

    def test_timer_finished_activates_stop_word(self):
        protocol = make_protocol()
        arm_stop_word(protocol)

        protocol.handle_timer_event(VoiceAssistantTimerEventType.VOICE_ASSISTANT_TIMER_FINISHED, MagicMock())

        assert protocol.state.stop_word.id in protocol.state.active_wake_words

    def test_announce_activates_stop_word(self):
        """Announcements (no TTS_END event) also arm the stop word."""
        protocol = make_protocol()
        arm_stop_word(protocol)

        msg = VoiceAssistantAnnounceRequest(text="hello", media_id="http://example.com/a.mp3")
        protocol._handle_announce_request(msg)

        assert protocol.state.stop_word.id in protocol.state.active_wake_words


class TestStopWordInterrupt:
    def test_stop_stops_playback_and_reports_finished(self):
        protocol = make_protocol()
        arm_stop_word(protocol)
        activate_stop_word(protocol)
        protocol._is_playing_tts = True

        protocol.stop()

        protocol.state.tts_player.stop.assert_called_once()
        assert protocol.state.stop_word.id not in protocol.state.active_wake_words
        assert protocol._is_playing_tts is False


class TestHotkeyCancel:
    def test_hotkey_during_tts_cancels_playback(self):
        protocol = make_protocol()
        protocol._is_playing_tts = True

        with patch.object(protocol, "wakeup") as wakeup:
            protocol._on_voice_input_trigger()

        wakeup.assert_not_called()
        protocol.state.tts_player.stop.assert_called_once()

    def test_hotkey_during_timer_ring_cancels_sound(self):
        protocol = make_protocol()
        protocol._timer_finished = True

        with patch.object(protocol, "wakeup") as wakeup:
            protocol._on_voice_input_trigger()

        wakeup.assert_not_called()
        assert protocol._timer_finished is False

    def test_hotkey_while_idle_starts_conversation(self):
        protocol = make_protocol()

        with patch.object(protocol, "wakeup") as wakeup:
            protocol._on_voice_input_trigger()

        wakeup.assert_called_once_with(wake_word_phrase="")


class TestStopWordNotArmed:
    def test_without_stop_word_chain_is_inert(self):
        """The pre-fix state: nothing may crash when stop_word is None."""
        protocol = make_protocol()
        assert protocol.state.stop_word is None

        protocol._tts_url = "http://example.com/tts.mp3"
        protocol.play_tts()  # must not raise, just no stop-word activation
        protocol.stop()  # must not raise

        assert protocol.state.tts_player.stop.called
