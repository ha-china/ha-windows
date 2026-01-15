"""
Property-Based Tests for ESPHome Protocol State Machine

Tests Property 5: Audio Streaming State Machine

Validates: Requirements 2.3, 2.4
"""

import logging
from typing import Dict, List, Optional
from unittest.mock import MagicMock, patch
from dataclasses import dataclass, field

import pytest
from hypothesis import given, strategies as st, settings, assume
from hypothesis.stateful import RuleBasedStateMachine, rule, invariant, initialize

# Import the ESPHome protocol module
from src.core.esphome_protocol import ESPHomeProtocol, create_default_state
from src.core.models import ServerState, AudioPlayer, AvailableWakeWord, WakeWordType

# Import ESPHome API types
from aioesphomeapi.model import VoiceAssistantEventType


# =============================================================================
# Strategies for generating test data
# =============================================================================

# Strategy for generating audio chunks (16kHz mono PCM, 32ms chunks = 512 samples * 2 bytes)
audio_chunk_strategy = st.binary(min_size=512, max_size=2048)

# Strategy for generating wake word phrases
wake_word_strategy = st.sampled_from(["ok nabu", "hey jarvis", "alexa", "hey google"])

# Strategy for generating TTS URLs
tts_url_strategy = st.from_regex(
    r'https?://[a-z0-9]+\.[a-z]{2,3}/tts/[a-z0-9_]+\.mp3',
    fullmatch=True
)

# Strategy for generating voice event types that affect streaming state
streaming_event_strategy = st.sampled_from([
    VoiceAssistantEventType.VOICE_ASSISTANT_RUN_START,
    VoiceAssistantEventType.VOICE_ASSISTANT_STT_VAD_END,
    VoiceAssistantEventType.VOICE_ASSISTANT_STT_END,
    VoiceAssistantEventType.VOICE_ASSISTANT_RUN_END,
])


# =============================================================================
# Helper functions
# =============================================================================

def create_test_protocol() -> ESPHomeProtocol:
    """Create a test ESPHomeProtocol instance with mocked dependencies."""
    state = create_default_state("test_device")
    
    # Mock the audio players
    state.tts_player = MagicMock(spec=AudioPlayer)
    state.music_player = MagicMock(spec=AudioPlayer)
    
    protocol = ESPHomeProtocol(state)
    
    # Mock the transport to capture sent messages
    mock_transport = MagicMock()
    mock_transport.writelines = MagicMock()
    protocol._transport = mock_transport
    protocol._writelines = mock_transport.writelines
    
    return protocol


# =============================================================================
# Property 5: Audio Streaming State Machine
# For any voice conversation, the Windows_Client SHALL stream audio only while
# in LISTENING state, and SHALL stop streaming when STT_END event is received.
# Validates: Requirements 2.3, 2.4
# =============================================================================

class TestAudioStreamingStateMachine:
    """
    Property 5: Audio Streaming State Machine
    
    **Feature: ha-windows-client, Property 5: Audio Streaming State Machine**
    **Validates: Requirements 2.3, 2.4**
    """

    @given(audio_chunk=audio_chunk_strategy)
    @settings(max_examples=100, deadline=None)
    def test_audio_not_sent_when_not_streaming(self, audio_chunk: bytes):
        """
        Property 5: For any audio chunk, when _is_streaming_audio is False,
        the audio SHALL NOT be sent to Home Assistant.
        
        **Feature: ha-windows-client, Property 5: Audio Streaming State Machine**
        **Validates: Requirements 2.3, 2.4**
        """
        protocol = create_test_protocol()
        
        # Ensure streaming is disabled
        protocol._is_streaming_audio = False
        
        # Track sent messages
        sent_messages = []
        original_send = protocol.send_messages
        def mock_send(msgs):
            sent_messages.extend(msgs)
            original_send(msgs)
        protocol.send_messages = mock_send
        
        # Try to send audio
        protocol.handle_audio(audio_chunk)
        
        # Property: no audio messages should be sent when not streaming
        audio_messages = [m for m in sent_messages if hasattr(m, 'data')]
        assert len(audio_messages) == 0, \
            "Audio should NOT be sent when _is_streaming_audio is False"

    @given(audio_chunk=audio_chunk_strategy)
    @settings(max_examples=100, deadline=None)
    def test_audio_sent_when_streaming(self, audio_chunk: bytes):
        """
        Property 5: For any audio chunk, when _is_streaming_audio is True,
        the audio SHALL be sent to Home Assistant via VoiceAssistantAudio.
        
        **Feature: ha-windows-client, Property 5: Audio Streaming State Machine**
        **Validates: Requirements 2.3**
        """
        protocol = create_test_protocol()
        
        # Enable streaming
        protocol._is_streaming_audio = True
        
        # Track sent messages
        sent_messages = []
        original_send = protocol.send_messages
        def mock_send(msgs):
            sent_messages.extend(msgs)
            original_send(msgs)
        protocol.send_messages = mock_send
        
        # Send audio
        protocol.handle_audio(audio_chunk)
        
        # Property: audio message should be sent when streaming
        audio_messages = [m for m in sent_messages if hasattr(m, 'data')]
        assert len(audio_messages) == 1, \
            "Exactly one audio message should be sent when streaming"
        assert audio_messages[0].data == audio_chunk, \
            "Audio data should match the input chunk"

    @given(wake_word=wake_word_strategy)
    @settings(max_examples=100, deadline=None)
    def test_wakeup_enables_streaming(self, wake_word: str):
        """
        Property 5: For any wake word detection, wakeup() SHALL set
        _is_streaming_audio to True.
        
        **Feature: ha-windows-client, Property 5: Audio Streaming State Machine**
        **Validates: Requirements 2.3**
        """
        protocol = create_test_protocol()
        
        # Ensure streaming is initially disabled
        protocol._is_streaming_audio = False
        
        # Trigger wakeup
        protocol.wakeup(wake_word)
        
        # Property: streaming should be enabled after wakeup
        assert protocol._is_streaming_audio is True, \
            f"_is_streaming_audio should be True after wakeup with '{wake_word}'"

    def test_stt_end_disables_streaming(self):
        """
        Property 5: When STT_END event is received, _is_streaming_audio
        SHALL be set to False.
        
        **Feature: ha-windows-client, Property 5: Audio Streaming State Machine**
        **Validates: Requirements 2.4**
        """
        protocol = create_test_protocol()
        
        # Enable streaming first
        protocol._is_streaming_audio = True
        
        # Send STT_END event
        protocol.handle_voice_event(
            VoiceAssistantEventType.VOICE_ASSISTANT_STT_END,
            {}
        )
        
        # Property: streaming should be disabled after STT_END
        assert protocol._is_streaming_audio is False, \
            "_is_streaming_audio should be False after STT_END event"

    def test_stt_vad_end_disables_streaming(self):
        """
        Property 5: When STT_VAD_END event is received, _is_streaming_audio
        SHALL be set to False.
        
        **Feature: ha-windows-client, Property 5: Audio Streaming State Machine**
        **Validates: Requirements 2.4**
        """
        protocol = create_test_protocol()
        
        # Enable streaming first
        protocol._is_streaming_audio = True
        
        # Send STT_VAD_END event
        protocol.handle_voice_event(
            VoiceAssistantEventType.VOICE_ASSISTANT_STT_VAD_END,
            {}
        )
        
        # Property: streaming should be disabled after STT_VAD_END
        assert protocol._is_streaming_audio is False, \
            "_is_streaming_audio should be False after STT_VAD_END event"

    def test_run_end_disables_streaming(self):
        """
        Property 5: When RUN_END event is received, _is_streaming_audio
        SHALL be set to False.
        
        **Feature: ha-windows-client, Property 5: Audio Streaming State Machine**
        **Validates: Requirements 2.4**
        """
        protocol = create_test_protocol()
        
        # Enable streaming first
        protocol._is_streaming_audio = True
        
        # Send RUN_END event
        protocol.handle_voice_event(
            VoiceAssistantEventType.VOICE_ASSISTANT_RUN_END,
            {}
        )
        
        # Property: streaming should be disabled after RUN_END
        assert protocol._is_streaming_audio is False, \
            "_is_streaming_audio should be False after RUN_END event"

    @given(
        wake_word=wake_word_strategy,
        audio_chunks=st.lists(audio_chunk_strategy, min_size=1, max_size=10)
    )
    @settings(max_examples=100, deadline=None)
    def test_streaming_state_machine_sequence(
        self, wake_word: str, audio_chunks: List[bytes]
    ):
        """
        Property 5: For any sequence of wake word -> audio chunks -> STT_END,
        audio SHALL only be sent during the streaming phase.
        
        **Feature: ha-windows-client, Property 5: Audio Streaming State Machine**
        **Validates: Requirements 2.3, 2.4**
        """
        protocol = create_test_protocol()
        
        # Track sent audio messages
        sent_audio_count = 0
        original_send = protocol.send_messages
        def mock_send(msgs):
            nonlocal sent_audio_count
            for m in msgs:
                if hasattr(m, 'data'):
                    sent_audio_count += 1
            original_send(msgs)
        protocol.send_messages = mock_send
        
        # Phase 1: Before wakeup - no streaming
        assert protocol._is_streaming_audio is False
        protocol.handle_audio(b"pre_wakeup_audio")
        assert sent_audio_count == 0, "No audio should be sent before wakeup"
        
        # Phase 2: After wakeup - streaming enabled
        protocol.wakeup(wake_word)
        assert protocol._is_streaming_audio is True
        
        # Send audio chunks during streaming
        for chunk in audio_chunks:
            protocol.handle_audio(chunk)
        
        assert sent_audio_count == len(audio_chunks), \
            f"All {len(audio_chunks)} audio chunks should be sent during streaming"
        
        # Phase 3: After STT_END - streaming disabled
        protocol.handle_voice_event(
            VoiceAssistantEventType.VOICE_ASSISTANT_STT_END,
            {}
        )
        assert protocol._is_streaming_audio is False
        
        # Try to send more audio after STT_END
        pre_end_count = sent_audio_count
        protocol.handle_audio(b"post_stt_end_audio")
        assert sent_audio_count == pre_end_count, \
            "No audio should be sent after STT_END"

    @given(
        event_type=streaming_event_strategy,
        initial_streaming=st.booleans()
    )
    @settings(max_examples=100, deadline=None)
    def test_event_type_streaming_state_transitions(
        self, event_type: VoiceAssistantEventType, initial_streaming: bool
    ):
        """
        Property 5: For any voice event type, the streaming state SHALL
        transition correctly based on the event type.
        
        **Feature: ha-windows-client, Property 5: Audio Streaming State Machine**
        **Validates: Requirements 2.3, 2.4**
        """
        protocol = create_test_protocol()
        protocol._is_streaming_audio = initial_streaming
        
        # Handle the event
        protocol.handle_voice_event(event_type, {})
        
        # Check expected state based on event type
        if event_type in (
            VoiceAssistantEventType.VOICE_ASSISTANT_STT_VAD_END,
            VoiceAssistantEventType.VOICE_ASSISTANT_STT_END,
            VoiceAssistantEventType.VOICE_ASSISTANT_RUN_END,
        ):
            # These events should disable streaming
            assert protocol._is_streaming_audio is False, \
                f"Event {event_type.name} should disable streaming"
        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_RUN_START:
            # RUN_START doesn't change streaming state directly
            # (streaming is enabled by wakeup, not RUN_START)
            pass


# =============================================================================
# Stateful Property-Based Test for State Machine
# =============================================================================

class AudioStreamingStateMachine(RuleBasedStateMachine):
    """
    Stateful property-based test for the audio streaming state machine.
    
    This tests that the state machine maintains correct invariants across
    arbitrary sequences of operations.
    
    **Feature: ha-windows-client, Property 5: Audio Streaming State Machine**
    **Validates: Requirements 2.3, 2.4**
    """
    
    def __init__(self):
        super().__init__()
        self.protocol = None
        self.sent_audio_count = 0
        self.expected_streaming = False
    
    @initialize()
    def init_protocol(self):
        """Initialize the protocol for each test run."""
        self.protocol = create_test_protocol()
        self.sent_audio_count = 0
        self.expected_streaming = False
        
        # Track sent messages
        original_send = self.protocol.send_messages
        def mock_send(msgs):
            for m in msgs:
                if hasattr(m, 'data'):
                    self.sent_audio_count += 1
            original_send(msgs)
        self.protocol.send_messages = mock_send
    
    @rule()
    def wakeup(self):
        """Trigger wake word detection."""
        if self.protocol._timer_finished:
            # If timer is finished, wakeup stops the timer instead
            self.protocol.wakeup("ok nabu")
            self.expected_streaming = False
        else:
            self.protocol.wakeup("ok nabu")
            self.expected_streaming = True
    
    @rule()
    def send_stt_end(self):
        """Send STT_END event."""
        self.protocol.handle_voice_event(
            VoiceAssistantEventType.VOICE_ASSISTANT_STT_END,
            {}
        )
        self.expected_streaming = False
    
    @rule()
    def send_stt_vad_end(self):
        """Send STT_VAD_END event."""
        self.protocol.handle_voice_event(
            VoiceAssistantEventType.VOICE_ASSISTANT_STT_VAD_END,
            {}
        )
        self.expected_streaming = False
    
    @rule()
    def send_run_end(self):
        """Send RUN_END event."""
        self.protocol.handle_voice_event(
            VoiceAssistantEventType.VOICE_ASSISTANT_RUN_END,
            {}
        )
        self.expected_streaming = False
    
    @rule(audio=audio_chunk_strategy)
    def send_audio(self, audio: bytes):
        """Send an audio chunk."""
        count_before = self.sent_audio_count
        self.protocol.handle_audio(audio)
        
        if self.expected_streaming:
            # Audio should be sent when streaming
            assert self.sent_audio_count == count_before + 1, \
                "Audio should be sent when streaming is enabled"
        else:
            # Audio should NOT be sent when not streaming
            assert self.sent_audio_count == count_before, \
                "Audio should NOT be sent when streaming is disabled"
    
    @invariant()
    def streaming_state_matches_expected(self):
        """Invariant: actual streaming state matches expected state."""
        if self.protocol is not None:
            assert self.protocol._is_streaming_audio == self.expected_streaming, \
                f"Streaming state mismatch: expected {self.expected_streaming}, " \
                f"got {self.protocol._is_streaming_audio}"


# Run the stateful test
TestAudioStreamingStateMachineStateful = AudioStreamingStateMachine.TestCase


# =============================================================================
# Additional edge case tests
# =============================================================================

class TestAudioStreamingEdgeCases:
    """Edge case tests for audio streaming state machine."""

    def test_multiple_wakeups_keep_streaming_enabled(self):
        """
        Multiple consecutive wakeups SHALL keep streaming enabled.
        """
        protocol = create_test_protocol()
        
        protocol.wakeup("ok nabu")
        assert protocol._is_streaming_audio is True
        
        protocol.wakeup("hey jarvis")
        assert protocol._is_streaming_audio is True

    def test_stt_end_after_stt_end_stays_disabled(self):
        """
        Multiple STT_END events SHALL keep streaming disabled.
        """
        protocol = create_test_protocol()
        
        protocol._is_streaming_audio = True
        
        protocol.handle_voice_event(
            VoiceAssistantEventType.VOICE_ASSISTANT_STT_END,
            {}
        )
        assert protocol._is_streaming_audio is False
        
        protocol.handle_voice_event(
            VoiceAssistantEventType.VOICE_ASSISTANT_STT_END,
            {}
        )
        assert protocol._is_streaming_audio is False

    def test_connection_lost_resets_streaming_state(self):
        """
        When connection is lost, streaming state SHALL be reset to False.
        """
        protocol = create_test_protocol()
        
        # Enable streaming
        protocol._is_streaming_audio = True
        
        # Simulate connection lost
        protocol.connection_lost(None)
        
        # Property: streaming should be disabled after connection lost
        assert protocol._is_streaming_audio is False, \
            "Streaming should be disabled after connection lost"

    def test_empty_audio_chunk_not_sent_when_not_streaming(self):
        """
        Empty audio chunks SHALL NOT be sent when not streaming.
        """
        protocol = create_test_protocol()
        protocol._is_streaming_audio = False
        
        sent_messages = []
        original_send = protocol.send_messages
        def mock_send(msgs):
            sent_messages.extend(msgs)
            original_send(msgs)
        protocol.send_messages = mock_send
        
        protocol.handle_audio(b"")
        
        assert len(sent_messages) == 0, \
            "Empty audio should not be sent when not streaming"

    def test_initial_streaming_state_is_false(self):
        """
        Initial streaming state SHALL be False.
        """
        protocol = create_test_protocol()
        
        assert protocol._is_streaming_audio is False, \
            "Initial streaming state should be False"
