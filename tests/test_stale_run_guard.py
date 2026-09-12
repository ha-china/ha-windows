"""Regression tests for the streaming-flag lifecycle (voice mute bug).

HA aborts the previous pipeline run when the satellite sends start=True;
its RUN_END can arrive right after the fresh trigger. RUN_END must never
clear the streaming flag - speech boundaries (VAD_END / STT_END) are the
authoritative stop and were always sufficient in the normal flow.
"""

from aioesphomeapi.api_pb2 import VoiceAssistantEventResponse
from aioesphomeapi.model import VoiceAssistantEventType

from src.core.esphome_protocol import ESPHomeProtocol
from src.core.models import create_default_state


def make_protocol() -> ESPHomeProtocol:
    return ESPHomeProtocol(create_default_state("test_device"))


def event(protocol: ESPHomeProtocol, event_type: VoiceAssistantEventType) -> None:
    protocol.handle_voice_event(event_type, {})


class TestStreamingFlagLifecycle:
    def test_stale_run_end_keeps_fresh_streaming(self):
        """The replaced run's RUN_END must not mute the fresh conversation."""
        protocol = make_protocol()
        protocol._is_streaming_audio = True  # set by wakeup()

        event(protocol, VoiceAssistantEventType.VOICE_ASSISTANT_RUN_END)

        assert protocol._is_streaming_audio is True

    def test_vad_end_clears_streaming(self):
        """Speech boundary: the authoritative stop (original contract)."""
        protocol = make_protocol()
        protocol._is_streaming_audio = True

        event(protocol, VoiceAssistantEventType.VOICE_ASSISTANT_STT_VAD_END)

        assert protocol._is_streaming_audio is False

    def test_stt_end_clears_streaming(self):
        protocol = make_protocol()
        protocol._is_streaming_audio = True

        event(protocol, VoiceAssistantEventType.VOICE_ASSISTANT_STT_END)

        assert protocol._is_streaming_audio is False

    def test_full_normal_conversation_cycle(self):
        """wakeup -> audio -> VAD_END -> RUN_END: flag cleared at speech end."""
        protocol = make_protocol()
        protocol._is_streaming_audio = True  # wakeup()

        event(protocol, VoiceAssistantEventType.VOICE_ASSISTANT_STT_VAD_END)
        assert protocol._is_streaming_audio is False

        # A late RUN_END after the speech boundary changes nothing
        event(protocol, VoiceAssistantEventType.VOICE_ASSISTANT_RUN_END)
        assert protocol._is_streaming_audio is False

    def test_run_end_through_real_protobuf_path(self):
        protocol = make_protocol()
        protocol._is_streaming_audio = True
        msg = VoiceAssistantEventResponse(event_type=VoiceAssistantEventType.VOICE_ASSISTANT_RUN_END.value)

        protocol._handle_voice_event(msg)

        assert protocol._is_streaming_audio is True
