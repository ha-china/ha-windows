"""
End-to-End Integration Tests for Home Assistant Windows Client

Tests the complete ESPHome protocol flow and voice assistant integration.

Task 16.1: 编写端到端集成测试
- 测试完整的 ESPHome 协议流程
- 测试语音助手端到端流程
- Requirements: All
"""

import asyncio
import logging
import socket
from typing import List, Optional, Dict, Any
from unittest.mock import MagicMock, patch, AsyncMock
from dataclasses import dataclass

import pytest

# Import core modules
from src.core.esphome_protocol import (
    ESPHomeProtocol,
    ESPHomeServer,
    create_default_state,
    PROTO_TO_MESSAGE_TYPE,
)
from src.core.models import ServerState, AudioPlayer, AvailableWakeWord, WakeWordType
from src.core.mdns_discovery import MDNSBroadcaster, DeviceInfo

# Import ESPHome API types
from aioesphomeapi.api_pb2 import (
    HelloRequest,
    HelloResponse,
    AuthenticationRequest,
    AuthenticationResponse,
    DeviceInfoRequest,
    DeviceInfoResponse,
    ListEntitiesRequest,
    ListEntitiesDoneResponse,
    VoiceAssistantConfigurationRequest,
    VoiceAssistantConfigurationResponse,
    VoiceAssistantRequest,
    VoiceAssistantAudio,
    VoiceAssistantEventResponse,
    VoiceAssistantAnnounceRequest,
    VoiceAssistantAnnounceFinished,
    PingRequest,
    PingResponse,
    DisconnectRequest,
    DisconnectResponse,
    SubscribeHomeAssistantStatesRequest,
    MediaPlayerCommandRequest,
)
from aioesphomeapi.core import MESSAGE_TYPE_TO_PROTO
from aioesphomeapi.model import VoiceAssistantEventType, VoiceAssistantFeature

logger = logging.getLogger(__name__)


# =============================================================================
# Test Fixtures and Helpers
# =============================================================================

def create_test_server_state(name: str = "test_device") -> ServerState:
    """Create a test server state with mocked audio players."""
    state = create_default_state(name)
    state.tts_player = MagicMock(spec=AudioPlayer)
    state.music_player = MagicMock(spec=AudioPlayer)
    return state


def create_test_protocol(name: str = "test_device") -> ESPHomeProtocol:
    """Create a test ESPHomeProtocol with mocked transport."""
    state = create_test_server_state(name)
    protocol = ESPHomeProtocol(state)
    
    # Mock transport
    mock_transport = MagicMock()
    mock_transport.writelines = MagicMock()
    mock_transport.get_extra_info = MagicMock(return_value=("127.0.0.1", 12345))
    protocol._transport = mock_transport
    protocol._writelines = mock_transport.writelines
    
    return protocol


def encode_message(msg) -> bytes:
    """Encode a protobuf message for sending to the protocol."""
    msg_type = PROTO_TO_MESSAGE_TYPE[msg.__class__]
    msg_data = msg.SerializeToString()
    
    # Build packet: preamble (0x00) + length varint + type varint + data
    def encode_varint(value: int) -> bytes:
        result = []
        while value > 127:
            result.append((value & 0x7F) | 0x80)
            value >>= 7
        result.append(value)
        return bytes(result)
    
    packet = bytes([0x00])  # preamble
    packet += encode_varint(len(msg_data))  # length
    packet += encode_varint(msg_type)  # type
    packet += msg_data  # data
    
    return packet


class MessageCapture:
    """Helper to capture sent messages from protocol."""
    
    def __init__(self, protocol: ESPHomeProtocol):
        self.protocol = protocol
        self.sent_messages: List[Any] = []
        self._original_send = protocol.send_messages
        protocol.send_messages = self._capture_send
    
    def _capture_send(self, msgs: List[Any]) -> None:
        self.sent_messages.extend(msgs)
        self._original_send(msgs)
    
    def get_messages_of_type(self, msg_type) -> List[Any]:
        return [m for m in self.sent_messages if isinstance(m, msg_type)]
    
    def clear(self):
        self.sent_messages.clear()


# =============================================================================
# Integration Test: Complete ESPHome Protocol Flow
# =============================================================================

class TestESPHomeProtocolFlow:
    """
    Integration tests for the complete ESPHome protocol flow.
    
    Tests the full handshake sequence and entity discovery.
    """

    def test_complete_handshake_sequence(self):
        """
        Test the complete ESPHome handshake sequence:
        HelloRequest -> HelloResponse -> AuthRequest -> AuthResponse
        """
        protocol = create_test_protocol("integration_test")
        capture = MessageCapture(protocol)
        
        # Step 1: Send HelloRequest
        hello_req = HelloRequest(
            client_info="Home Assistant",
            api_version_major=1,
            api_version_minor=10,
        )
        protocol.data_received(encode_message(hello_req))
        
        # Verify HelloResponse
        hello_responses = capture.get_messages_of_type(HelloResponse)
        assert len(hello_responses) == 1, "Should receive exactly one HelloResponse"
        assert hello_responses[0].name == "integration_test"
        assert hello_responses[0].api_version_major == 1
        
        capture.clear()
        
        # Step 2: Send AuthenticationRequest
        auth_req = AuthenticationRequest()
        protocol.data_received(encode_message(auth_req))
        
        # Verify AuthenticationResponse
        auth_responses = capture.get_messages_of_type(AuthenticationResponse)
        assert len(auth_responses) == 1, "Should receive exactly one AuthResponse"

    def test_device_info_request(self):
        """
        Test DeviceInfoRequest returns correct device information.
        """
        protocol = create_test_protocol("my_windows_pc")
        capture = MessageCapture(protocol)
        
        # Send DeviceInfoRequest
        device_info_req = DeviceInfoRequest()
        protocol.data_received(encode_message(device_info_req))
        
        # Verify DeviceInfoResponse
        responses = capture.get_messages_of_type(DeviceInfoResponse)
        assert len(responses) == 1
        
        response = responses[0]
        assert response.name == "my_windows_pc"
        assert response.uses_password is False
        
        # Verify voice assistant features
        expected_features = (
            VoiceAssistantFeature.VOICE_ASSISTANT
            | VoiceAssistantFeature.API_AUDIO
            | VoiceAssistantFeature.ANNOUNCE
            | VoiceAssistantFeature.START_CONVERSATION
            | VoiceAssistantFeature.TIMERS
        )
        assert response.voice_assistant_feature_flags == expected_features

    def test_list_entities_request(self):
        """
        Test ListEntitiesRequest returns sensor and media player entities.
        """
        protocol = create_test_protocol()
        capture = MessageCapture(protocol)
        
        # Send ListEntitiesRequest
        list_req = ListEntitiesRequest()
        protocol.data_received(encode_message(list_req))
        
        # Verify ListEntitiesDoneResponse is sent
        done_responses = capture.get_messages_of_type(ListEntitiesDoneResponse)
        assert len(done_responses) == 1, "Should receive ListEntitiesDoneResponse"
        
        # Verify we got some entity definitions (sensors + media player)
        # The exact count depends on available sensors
        assert len(capture.sent_messages) >= 2, "Should have entity definitions + done"

    def test_ping_pong(self):
        """
        Test PingRequest returns PingResponse.
        """
        protocol = create_test_protocol()
        capture = MessageCapture(protocol)
        
        # Send PingRequest
        ping_req = PingRequest()
        protocol.data_received(encode_message(ping_req))
        
        # Verify PingResponse
        responses = capture.get_messages_of_type(PingResponse)
        assert len(responses) == 1

    def test_disconnect_request(self):
        """
        Test DisconnectRequest closes the connection properly.
        """
        protocol = create_test_protocol()
        capture = MessageCapture(protocol)
        
        # Send DisconnectRequest
        disconnect_req = DisconnectRequest()
        protocol.data_received(encode_message(disconnect_req))
        
        # Verify DisconnectResponse
        responses = capture.get_messages_of_type(DisconnectResponse)
        assert len(responses) == 1
        
        # Verify transport.close() was called
        protocol._transport.close.assert_called_once()

    def test_voice_assistant_configuration(self):
        """
        Test VoiceAssistantConfigurationRequest returns available wake words.
        """
        protocol = create_test_protocol()
        capture = MessageCapture(protocol)
        
        # Send VoiceAssistantConfigurationRequest
        config_req = VoiceAssistantConfigurationRequest()
        protocol.data_received(encode_message(config_req))
        
        # Verify VoiceAssistantConfigurationResponse
        responses = capture.get_messages_of_type(VoiceAssistantConfigurationResponse)
        assert len(responses) == 1
        
        response = responses[0]
        # Should have at least one wake word
        assert len(response.available_wake_words) >= 1
        assert response.max_active_wake_words >= 1


# =============================================================================
# Integration Test: Voice Assistant End-to-End Flow
# =============================================================================

class TestVoiceAssistantFlow:
    """
    Integration tests for the voice assistant end-to-end flow.
    
    Tests wake word detection, audio streaming, and TTS playback.
    """

    def test_wake_word_to_audio_streaming(self):
        """
        Test the flow from wake word detection to audio streaming.
        """
        protocol = create_test_protocol()
        capture = MessageCapture(protocol)
        
        # Simulate wake word detection
        protocol.wakeup("ok nabu")
        
        # Verify VoiceAssistantRequest was sent
        requests = capture.get_messages_of_type(VoiceAssistantRequest)
        assert len(requests) == 1
        assert requests[0].start is True
        assert requests[0].wake_word_phrase == "ok nabu"
        
        # Verify streaming is enabled
        assert protocol._is_streaming_audio is True
        
        # Verify duck was called
        protocol.state.music_player.duck.assert_called()

    def test_audio_streaming_during_conversation(self):
        """
        Test audio chunks are sent during active conversation.
        """
        protocol = create_test_protocol()
        capture = MessageCapture(protocol)
        
        # Start conversation
        protocol.wakeup("hey jarvis")
        capture.clear()
        
        # Send audio chunks
        test_audio = b"\x00\x01" * 256  # 512 bytes
        protocol.handle_audio(test_audio)
        
        # Verify audio was sent
        audio_msgs = capture.get_messages_of_type(VoiceAssistantAudio)
        assert len(audio_msgs) == 1
        assert audio_msgs[0].data == test_audio

    def test_stt_end_stops_streaming(self):
        """
        Test that STT_END event stops audio streaming.
        """
        protocol = create_test_protocol()
        
        # Start conversation
        protocol.wakeup("ok nabu")
        assert protocol._is_streaming_audio is True
        
        # Receive STT_END event
        protocol.handle_voice_event(
            VoiceAssistantEventType.VOICE_ASSISTANT_STT_END,
            {}
        )
        
        # Verify streaming stopped
        assert protocol._is_streaming_audio is False

    def test_tts_playback_flow(self):
        """
        Test TTS URL is played when received.
        """
        protocol = create_test_protocol()
        
        # Start conversation
        protocol.wakeup("ok nabu")
        
        # Receive TTS_END with URL
        tts_url = "http://homeassistant.local/tts/test.mp3"
        protocol.handle_voice_event(
            VoiceAssistantEventType.VOICE_ASSISTANT_TTS_END,
            {"url": tts_url}
        )
        
        # Verify TTS player was called
        protocol.state.tts_player.play.assert_called()
        call_args = protocol.state.tts_player.play.call_args
        assert call_args[0][0] == tts_url

    def test_continue_conversation_flow(self):
        """
        Test continue_conversation restarts listening after TTS.
        """
        protocol = create_test_protocol()
        capture = MessageCapture(protocol)
        
        # Start conversation
        protocol.wakeup("ok nabu")
        
        # Receive INTENT_END with continue_conversation
        protocol.handle_voice_event(
            VoiceAssistantEventType.VOICE_ASSISTANT_INTENT_END,
            {"continue_conversation": "1"}
        )
        
        # Verify continue flag is set
        assert protocol._continue_conversation is True

    def test_announcement_playback(self):
        """
        Test announcement request triggers audio playback.
        """
        protocol = create_test_protocol()
        capture = MessageCapture(protocol)
        
        # Create mock play that calls done_callback immediately
        def mock_play(url, done_callback=None):
            if done_callback:
                done_callback()
        protocol.state.tts_player.play = MagicMock(side_effect=mock_play)
        
        # Send announcement request
        announce_req = VoiceAssistantAnnounceRequest(
            media_id="http://ha.local/media/announce.mp3",
            text="Test announcement",
        )
        protocol.data_received(encode_message(announce_req))
        
        # Verify duck was called
        protocol.state.music_player.duck.assert_called()
        
        # Verify TTS player was called
        protocol.state.tts_player.play.assert_called()
        
        # Verify announce finished was sent
        finished_msgs = capture.get_messages_of_type(VoiceAssistantAnnounceFinished)
        assert len(finished_msgs) == 1

    def test_announcement_with_preannounce(self):
        """
        Test announcement with preannounce plays both in sequence.
        """
        protocol = create_test_protocol()
        
        # Track play calls
        play_calls = []
        def mock_play(url, done_callback=None):
            play_calls.append(url)
            if done_callback:
                done_callback()
        protocol.state.tts_player.play = MagicMock(side_effect=mock_play)
        
        # Send announcement with preannounce
        announce_req = VoiceAssistantAnnounceRequest(
            media_id="http://ha.local/media/main.mp3",
            preannounce_media_id="http://ha.local/media/chime.mp3",
            text="Test",
        )
        protocol.data_received(encode_message(announce_req))
        
        # Verify both URLs were played in order
        assert len(play_calls) == 2
        assert play_calls[0] == "http://ha.local/media/chime.mp3"
        assert play_calls[1] == "http://ha.local/media/main.mp3"


# =============================================================================
# Integration Test: Connection Lifecycle
# =============================================================================

class TestConnectionLifecycle:
    """
    Integration tests for connection lifecycle management.
    """

    def test_connection_made_initializes_state(self):
        """
        Test connection_made properly initializes the protocol.
        """
        state = create_test_server_state()
        protocol = ESPHomeProtocol(state)
        
        mock_transport = MagicMock()
        mock_transport.get_extra_info = MagicMock(return_value=("192.168.1.100", 54321))
        
        protocol.connection_made(mock_transport)
        
        assert protocol._transport == mock_transport
        assert protocol._writelines is not None

    def test_connection_lost_resets_state(self):
        """
        Test connection_lost properly resets protocol state.
        """
        protocol = create_test_protocol()
        
        # Set up some state
        protocol._is_streaming_audio = True
        protocol._tts_url = "http://test.url"
        protocol._continue_conversation = True
        
        # Simulate connection lost
        protocol.connection_lost(None)
        
        # Verify state is reset
        assert protocol._is_streaming_audio is False
        assert protocol._tts_url is None
        assert protocol._continue_conversation is False
        assert protocol._transport is None
        
        # Verify unduck was called
        protocol.state.music_player.unduck.assert_called()

    def test_multiple_messages_in_single_packet(self):
        """
        Test handling multiple messages received in a single data packet.
        """
        protocol = create_test_protocol()
        capture = MessageCapture(protocol)
        
        # Encode multiple messages into one packet
        hello_req = HelloRequest(client_info="Test", api_version_major=1, api_version_minor=10)
        ping_req = PingRequest()
        
        combined_data = encode_message(hello_req) + encode_message(ping_req)
        
        # Send combined packet
        protocol.data_received(combined_data)
        
        # Verify both messages were processed
        hello_responses = capture.get_messages_of_type(HelloResponse)
        ping_responses = capture.get_messages_of_type(PingResponse)
        
        assert len(hello_responses) == 1
        assert len(ping_responses) == 1


# =============================================================================
# Integration Test: Sensor and MediaPlayer Integration
# =============================================================================

class TestSensorMediaPlayerIntegration:
    """
    Integration tests for sensor and media player functionality.
    """

    def test_subscribe_states_returns_sensor_values(self):
        """
        Test SubscribeHomeAssistantStatesRequest returns sensor states.
        """
        protocol = create_test_protocol()
        capture = MessageCapture(protocol)
        
        # Send subscribe request
        subscribe_req = SubscribeHomeAssistantStatesRequest()
        protocol.data_received(encode_message(subscribe_req))
        
        # Should receive sensor state responses
        assert len(capture.sent_messages) >= 1, "Should receive sensor states"

    def test_media_player_entity_included(self):
        """
        Test MediaPlayer entity is included in entity list.
        """
        protocol = create_test_protocol()
        capture = MessageCapture(protocol)
        
        # Request entity list
        list_req = ListEntitiesRequest()
        protocol.data_received(encode_message(list_req))
        
        # Check for media player entity in responses
        # The media player should be included
        from aioesphomeapi.api_pb2 import ListEntitiesMediaPlayerResponse
        media_player_entities = capture.get_messages_of_type(ListEntitiesMediaPlayerResponse)
        assert len(media_player_entities) == 1, "Should have one MediaPlayer entity"


# =============================================================================
# Integration Test: Error Handling
# =============================================================================

class TestErrorHandling:
    """
    Integration tests for error handling scenarios.
    """

    def test_invalid_message_type_handled(self):
        """
        Test that invalid message types are handled gracefully.
        """
        protocol = create_test_protocol()
        
        # Send invalid packet (unknown message type 9999)
        invalid_packet = bytes([0x00, 0x00, 0x8F, 0x4E])  # type = 9999
        
        # Should not raise exception
        protocol.data_received(invalid_packet)

    def test_malformed_packet_handled(self):
        """
        Test that malformed packets are handled gracefully.
        """
        protocol = create_test_protocol()
        
        # Send incomplete packet
        incomplete_packet = bytes([0x00, 0x10])  # Missing data
        
        # Should not raise exception, just wait for more data
        protocol.data_received(incomplete_packet)

    def test_empty_audio_chunk_handled(self):
        """
        Test that empty audio chunks are handled.
        """
        protocol = create_test_protocol()
        capture = MessageCapture(protocol)
        
        # Enable streaming
        protocol._is_streaming_audio = True
        
        # Send empty audio
        protocol.handle_audio(b"")
        
        # Should still send (empty) audio message
        audio_msgs = capture.get_messages_of_type(VoiceAssistantAudio)
        assert len(audio_msgs) == 1


# =============================================================================
# Integration Test: Full Conversation Flow
# =============================================================================

class TestFullConversationFlow:
    """
    Integration test for a complete voice conversation flow.
    """

    def test_complete_voice_conversation(self):
        """
        Test a complete voice conversation from wake word to TTS response.
        
        Flow:
        1. Wake word detected -> VoiceAssistantRequest sent
        2. RUN_START received
        3. Audio chunks sent
        4. STT_END received -> streaming stops
        5. TTS_END received -> TTS played
        6. RUN_END received -> conversation ends
        """
        protocol = create_test_protocol()
        capture = MessageCapture(protocol)
        
        # Mock TTS player to track calls
        tts_played = []
        def mock_play(url, done_callback=None):
            tts_played.append(url)
            if done_callback:
                done_callback()
        protocol.state.tts_player.play = MagicMock(side_effect=mock_play)
        
        # Step 1: Wake word detected
        protocol.wakeup("ok nabu")
        
        requests = capture.get_messages_of_type(VoiceAssistantRequest)
        assert len(requests) == 1
        assert protocol._is_streaming_audio is True
        
        # Step 2: RUN_START received
        protocol.handle_voice_event(
            VoiceAssistantEventType.VOICE_ASSISTANT_RUN_START,
            {}
        )
        
        # Step 3: Send audio chunks
        for i in range(5):
            protocol.handle_audio(b"\x00\x01" * 256)
        
        audio_msgs = capture.get_messages_of_type(VoiceAssistantAudio)
        assert len(audio_msgs) == 5
        
        # Step 4: STT_END received
        protocol.handle_voice_event(
            VoiceAssistantEventType.VOICE_ASSISTANT_STT_END,
            {}
        )
        assert protocol._is_streaming_audio is False
        
        # Step 5: TTS_END received
        tts_url = "http://ha.local/tts/response.mp3"
        protocol.handle_voice_event(
            VoiceAssistantEventType.VOICE_ASSISTANT_TTS_END,
            {"url": tts_url}
        )
        
        assert tts_url in tts_played
        
        # Step 6: RUN_END received
        protocol.handle_voice_event(
            VoiceAssistantEventType.VOICE_ASSISTANT_RUN_END,
            {}
        )
        
        # Verify announce finished was sent
        finished_msgs = capture.get_messages_of_type(VoiceAssistantAnnounceFinished)
        assert len(finished_msgs) >= 1


# =============================================================================
# Integration Test: mDNS Service Registration
# =============================================================================

class TestMDNSIntegration:
    """
    Integration tests for mDNS service registration.
    """

    def test_device_info_creation(self):
        """
        Test DeviceInfo is created with correct defaults.
        """
        device_info = DeviceInfo()
        
        # Should have a name (hostname)
        assert device_info.name is not None
        assert len(device_info.name) > 0
        
        # Should have a MAC address
        assert device_info.mac_address is not None
        assert ":" in device_info.mac_address or len(device_info.mac_address) == 12

    def test_device_info_custom_values(self):
        """
        Test DeviceInfo accepts custom values.
        """
        device_info = DeviceInfo(
            name="custom_device",
            version="2.0.0",
            platform="TestPlatform",
            board="TestBoard",
        )
        
        assert device_info.name == "custom_device"
        assert device_info.version == "2.0.0"
        assert device_info.platform == "TestPlatform"
        assert device_info.board == "TestBoard"

    def test_mdns_broadcaster_initialization(self):
        """
        Test MDNSBroadcaster initializes correctly.
        """
        device_info = DeviceInfo(name="test_broadcaster")
        broadcaster = MDNSBroadcaster(device_info)
        
        assert broadcaster.device_info.name == "test_broadcaster"
        assert broadcaster.is_registered is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
