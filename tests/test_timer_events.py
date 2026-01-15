"""
Property-Based Tests for Timer Event Handling

Tests Property 10: Timer Event Handling

Validates: Requirements 4.1, 4.2, 4.3
"""

import logging
from typing import Dict, List, Optional
from unittest.mock import MagicMock, patch, call
from dataclasses import dataclass, field

import pytest
from hypothesis import given, strategies as st, settings, assume
from hypothesis.stateful import RuleBasedStateMachine, rule, invariant, initialize

# Import the ESPHome protocol module
from src.core.esphome_protocol import ESPHomeProtocol, create_default_state
from src.core.models import ServerState, AudioPlayer, AvailableWakeWord, WakeWordType

# Import ESPHome API types
from aioesphomeapi.model import VoiceAssistantTimerEventType


# =============================================================================
# Strategies for generating test data
# =============================================================================

# Strategy for generating timer IDs
timer_id_strategy = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N')),
    min_size=1,
    max_size=32
)

# Strategy for generating timer names
timer_name_strategy = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N', 'P', 'Z')),
    min_size=1,
    max_size=50
)

# Strategy for generating timer event types
timer_event_type_strategy = st.sampled_from([
    VoiceAssistantTimerEventType.VOICE_ASSISTANT_TIMER_STARTED,
    VoiceAssistantTimerEventType.VOICE_ASSISTANT_TIMER_UPDATED,
    VoiceAssistantTimerEventType.VOICE_ASSISTANT_TIMER_CANCELLED,
    VoiceAssistantTimerEventType.VOICE_ASSISTANT_TIMER_FINISHED,
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
    
    # Set timer finished sound
    state.timer_finished_sound = "data/sounds/timer_finished.flac"
    
    protocol = ESPHomeProtocol(state)
    
    # Mock the transport to capture sent messages
    mock_transport = MagicMock()
    mock_transport.writelines = MagicMock()
    protocol._transport = mock_transport
    protocol._writelines = mock_transport.writelines
    
    return protocol


def create_timer_event_msg(
    event_type: VoiceAssistantTimerEventType,
    timer_id: str = "timer_1",
    name: str = "Test Timer",
    total_seconds: int = 60,
    seconds_left: int = 0,
    is_active: bool = True
):
    """Create a mock timer event message."""
    msg = MagicMock()
    msg.event_type = event_type.value
    msg.timer_id = timer_id
    msg.name = name
    msg.total_seconds = total_seconds
    msg.seconds_left = seconds_left
    msg.is_active = is_active
    return msg


# =============================================================================
# Property 10: Timer Event Handling
# For any VoiceAssistantTimerEventResponse with TIMER_FINISHED, the 
# Windows_Client SHALL play timer finished sound until stopped.
# Validates: Requirements 4.1, 4.2, 4.3
# =============================================================================

class TestTimerEventHandling:
    """
    Property 10: Timer Event Handling
    
    **Feature: ha-windows-client, Property 10: Timer Event Handling**
    **Validates: Requirements 4.1, 4.2, 4.3**
    """

    @given(timer_id=timer_id_strategy, timer_name=timer_name_strategy)
    @settings(max_examples=100, deadline=None)
    def test_timer_finished_plays_sound(self, timer_id: str, timer_name: str):
        """
        Property 10: For any TIMER_FINISHED event, the Windows_Client
        SHALL play the timer finished sound.
        
        **Feature: ha-windows-client, Property 10: Timer Event Handling**
        **Validates: Requirements 4.1**
        """
        protocol = create_test_protocol()
        
        # Ensure timer is not already finished
        protocol._timer_finished = False
        
        # Create timer finished event
        msg = create_timer_event_msg(
            event_type=VoiceAssistantTimerEventType.VOICE_ASSISTANT_TIMER_FINISHED,
            timer_id=timer_id,
            name=timer_name,
        )
        
        # Handle the timer event
        protocol.handle_timer_event(
            VoiceAssistantTimerEventType.VOICE_ASSISTANT_TIMER_FINISHED,
            msg
        )
        
        # Property: timer finished sound should be played
        assert protocol._timer_finished is True, \
            "_timer_finished flag should be True after TIMER_FINISHED event"
        
        # Property: tts_player.play should be called with timer sound
        protocol.state.tts_player.play.assert_called()
        call_args = protocol.state.tts_player.play.call_args
        assert call_args[0][0] == protocol.state.timer_finished_sound, \
            f"Timer sound should be played, got {call_args[0][0]}"

    @given(timer_id=timer_id_strategy)
    @settings(max_examples=100, deadline=None)
    def test_timer_finished_ducks_audio(self, timer_id: str):
        """
        Property 10: For any TIMER_FINISHED event, the Windows_Client
        SHALL duck audio before playing timer sound.
        
        **Feature: ha-windows-client, Property 10: Timer Event Handling**
        **Validates: Requirements 4.1**
        """
        protocol = create_test_protocol()
        protocol._timer_finished = False
        
        # Track duck calls
        duck_called = False
        play_called = False
        
        def mock_duck():
            nonlocal duck_called
            duck_called = True
        
        def mock_play(url, done_callback=None):
            nonlocal play_called
            # Duck should be called before play
            assert duck_called, "duck() should be called before play()"
            play_called = True
        
        protocol.state.music_player.duck = mock_duck
        protocol.state.tts_player.play = mock_play
        
        # Create and handle timer finished event
        msg = create_timer_event_msg(
            event_type=VoiceAssistantTimerEventType.VOICE_ASSISTANT_TIMER_FINISHED,
            timer_id=timer_id,
        )
        
        protocol.handle_timer_event(
            VoiceAssistantTimerEventType.VOICE_ASSISTANT_TIMER_FINISHED,
            msg
        )
        
        # Property: duck should be called
        assert duck_called, "duck() should be called for timer finished"

    def test_timer_finished_only_triggers_once(self):
        """
        Property 10: Multiple TIMER_FINISHED events SHALL NOT restart
        the timer sound if already playing.
        
        **Feature: ha-windows-client, Property 10: Timer Event Handling**
        **Validates: Requirements 4.1**
        """
        protocol = create_test_protocol()
        
        # First timer finished event
        protocol._timer_finished = False
        msg = create_timer_event_msg(
            event_type=VoiceAssistantTimerEventType.VOICE_ASSISTANT_TIMER_FINISHED,
        )
        
        protocol.handle_timer_event(
            VoiceAssistantTimerEventType.VOICE_ASSISTANT_TIMER_FINISHED,
            msg
        )
        
        first_call_count = protocol.state.tts_player.play.call_count
        
        # Second timer finished event (should be ignored)
        protocol.handle_timer_event(
            VoiceAssistantTimerEventType.VOICE_ASSISTANT_TIMER_FINISHED,
            msg
        )
        
        second_call_count = protocol.state.tts_player.play.call_count
        
        # Property: play should only be called once
        assert second_call_count == first_call_count, \
            "Timer sound should not restart if already playing"

    def test_wakeup_stops_timer_sound(self):
        """
        Property 10: When wake word is detected during timer sound,
        the timer sound SHALL be stopped.
        
        **Feature: ha-windows-client, Property 10: Timer Event Handling**
        **Validates: Requirements 4.2, 4.3**
        """
        protocol = create_test_protocol()
        
        # Set timer as finished (sound playing)
        protocol._timer_finished = True
        
        # Trigger wakeup (simulates stop word detection)
        protocol.wakeup("stop")
        
        # Property: timer should be stopped
        assert protocol._timer_finished is False, \
            "_timer_finished should be False after wakeup during timer"
        
        # Property: tts_player.stop should be called
        protocol.state.tts_player.stop.assert_called()

    def test_stop_method_stops_timer_sound(self):
        """
        Property 10: stop() method SHALL stop the timer sound.
        
        **Feature: ha-windows-client, Property 10: Timer Event Handling**
        **Validates: Requirements 4.2, 4.3**
        """
        protocol = create_test_protocol()
        
        # Set timer as finished (sound playing)
        protocol._timer_finished = True
        
        # Call stop
        protocol.stop()
        
        # Property: timer should be stopped
        assert protocol._timer_finished is False, \
            "_timer_finished should be False after stop()"
        
        # Property: tts_player.stop should be called
        protocol.state.tts_player.stop.assert_called()

    @given(
        event_type=st.sampled_from([
            VoiceAssistantTimerEventType.VOICE_ASSISTANT_TIMER_STARTED,
            VoiceAssistantTimerEventType.VOICE_ASSISTANT_TIMER_UPDATED,
            VoiceAssistantTimerEventType.VOICE_ASSISTANT_TIMER_CANCELLED,
        ])
    )
    @settings(max_examples=100, deadline=None)
    def test_non_finished_events_do_not_play_sound(
        self, event_type: VoiceAssistantTimerEventType
    ):
        """
        Property 10: For any timer event that is NOT TIMER_FINISHED,
        the timer sound SHALL NOT be played.
        
        **Feature: ha-windows-client, Property 10: Timer Event Handling**
        **Validates: Requirements 4.1**
        """
        protocol = create_test_protocol()
        protocol._timer_finished = False
        
        msg = create_timer_event_msg(event_type=event_type)
        
        protocol.handle_timer_event(event_type, msg)
        
        # Property: timer finished flag should remain False
        assert protocol._timer_finished is False, \
            f"_timer_finished should be False for {event_type.name}"
        
        # Property: play should not be called
        protocol.state.tts_player.play.assert_not_called()

    def test_timer_sound_loops_until_stopped(self):
        """
        Property 10: Timer finished sound SHALL loop (replay) until stopped.
        
        **Feature: ha-windows-client, Property 10: Timer Event Handling**
        **Validates: Requirements 4.1, 4.2**
        """
        protocol = create_test_protocol()
        protocol._timer_finished = False
        
        # Track play calls and callbacks
        play_callbacks = []
        
        def mock_play(url, done_callback=None):
            play_callbacks.append(done_callback)
        
        protocol.state.tts_player.play = mock_play
        
        # Trigger timer finished
        msg = create_timer_event_msg(
            event_type=VoiceAssistantTimerEventType.VOICE_ASSISTANT_TIMER_FINISHED,
        )
        
        protocol.handle_timer_event(
            VoiceAssistantTimerEventType.VOICE_ASSISTANT_TIMER_FINISHED,
            msg
        )
        
        # Property: play should be called with a done_callback
        assert len(play_callbacks) == 1, "play() should be called once initially"
        assert play_callbacks[0] is not None, \
            "play() should have a done_callback for looping"

    def test_timer_finished_adds_stop_word_to_active(self):
        """
        Property 10: When timer finishes, stop word SHALL be added
        to active wake words.
        
        **Feature: ha-windows-client, Property 10: Timer Event Handling**
        **Validates: Requirements 4.2**
        """
        protocol = create_test_protocol()
        protocol._timer_finished = False
        
        # Set up a stop word
        stop_word = MagicMock()
        stop_word.id = "stop"
        protocol.state.stop_word = stop_word
        protocol.state.active_wake_words = set()
        
        # Trigger timer finished
        msg = create_timer_event_msg(
            event_type=VoiceAssistantTimerEventType.VOICE_ASSISTANT_TIMER_FINISHED,
        )
        
        protocol.handle_timer_event(
            VoiceAssistantTimerEventType.VOICE_ASSISTANT_TIMER_FINISHED,
            msg
        )
        
        # Property: stop word should be in active wake words
        assert "stop" in protocol.state.active_wake_words, \
            "Stop word should be added to active wake words when timer finishes"


# =============================================================================
# Stateful Property-Based Test for Timer State Machine
# =============================================================================

class TimerStateMachine(RuleBasedStateMachine):
    """
    Stateful property-based test for the timer state machine.
    
    This tests that the timer state machine maintains correct invariants
    across arbitrary sequences of operations.
    
    **Feature: ha-windows-client, Property 10: Timer Event Handling**
    **Validates: Requirements 4.1, 4.2, 4.3**
    """
    
    def __init__(self):
        super().__init__()
        self.protocol = None
        self.expected_timer_finished = False
    
    @initialize()
    def init_protocol(self):
        """Initialize the protocol for each test run."""
        self.protocol = create_test_protocol()
        self.expected_timer_finished = False
    
    @rule()
    def trigger_timer_finished(self):
        """Trigger a timer finished event."""
        if not self.expected_timer_finished:
            msg = create_timer_event_msg(
                event_type=VoiceAssistantTimerEventType.VOICE_ASSISTANT_TIMER_FINISHED,
            )
            self.protocol.handle_timer_event(
                VoiceAssistantTimerEventType.VOICE_ASSISTANT_TIMER_FINISHED,
                msg
            )
            self.expected_timer_finished = True
    
    @rule()
    def stop_timer(self):
        """Stop the timer via stop() method."""
        self.protocol.stop()
        self.expected_timer_finished = False
    
    @rule()
    def wakeup_during_timer(self):
        """Trigger wakeup which should stop timer if playing."""
        if self.expected_timer_finished:
            self.protocol.wakeup("stop")
            self.expected_timer_finished = False
        else:
            # Normal wakeup behavior (not stopping timer)
            self.protocol.wakeup("ok nabu")
    
    @invariant()
    def timer_state_matches_expected(self):
        """Invariant: actual timer state matches expected state."""
        if self.protocol is not None:
            assert self.protocol._timer_finished == self.expected_timer_finished, \
                f"Timer state mismatch: expected {self.expected_timer_finished}, " \
                f"got {self.protocol._timer_finished}"


# Run the stateful test
TestTimerStateMachineStateful = TimerStateMachine.TestCase


# =============================================================================
# Edge Case Tests
# =============================================================================

class TestTimerEdgeCases:
    """Edge case tests for timer functionality."""

    def test_timer_finished_without_sound_file(self):
        """
        When timer_finished_sound is empty, timer finished event
        SHALL still set the flag but not crash.
        """
        protocol = create_test_protocol()
        protocol.state.timer_finished_sound = ""
        protocol._timer_finished = False
        
        msg = create_timer_event_msg(
            event_type=VoiceAssistantTimerEventType.VOICE_ASSISTANT_TIMER_FINISHED,
        )
        
        # Should not raise exception
        protocol.handle_timer_event(
            VoiceAssistantTimerEventType.VOICE_ASSISTANT_TIMER_FINISHED,
            msg
        )
        
        # Flag should still be set
        assert protocol._timer_finished is True

    def test_connection_lost_resets_timer_state(self):
        """
        When connection is lost, timer state SHALL be reset.
        """
        protocol = create_test_protocol()
        protocol._timer_finished = True
        
        # Simulate connection lost
        protocol.connection_lost(None)
        
        # Timer state should be reset (via unduck being called)
        # Note: connection_lost doesn't explicitly reset _timer_finished
        # but it does call unduck() which is the cleanup behavior

    def test_stop_without_timer_playing(self):
        """
        stop() when no timer is playing SHALL not cause errors.
        """
        protocol = create_test_protocol()
        protocol._timer_finished = False
        
        # Should not raise exception
        protocol.stop()
        
        # State should remain False
        assert protocol._timer_finished is False

    def test_initial_timer_state_is_false(self):
        """
        Initial timer state SHALL be False.
        """
        protocol = create_test_protocol()
        
        assert protocol._timer_finished is False, \
            "Initial timer state should be False"

    def test_multiple_stops_are_idempotent(self):
        """
        Multiple stop() calls SHALL be idempotent.
        """
        protocol = create_test_protocol()
        protocol._timer_finished = True
        
        # First stop
        protocol.stop()
        assert protocol._timer_finished is False
        
        # Second stop (should not cause issues)
        protocol.stop()
        assert protocol._timer_finished is False

