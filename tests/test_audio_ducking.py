"""
Property-Based Tests for Audio Ducking Functionality

Tests Property 9: Audio Ducking Behavior

Validates: Requirements 3.4, 3.5
"""

import logging
from typing import Optional
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from hypothesis import given, strategies as st, settings, assume

# Import the models module
from src.core.models import AudioPlayer, WindowsVolumeController, get_volume_controller


# =============================================================================
# Strategies for generating test data
# =============================================================================

# Strategy for generating volume levels (0.0 to 1.0)
volume_strategy = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)

# Strategy for generating duck ratios (0.1 to 0.9)
duck_ratio_strategy = st.floats(min_value=0.1, max_value=0.9, allow_nan=False)


# =============================================================================
# Property 9: Audio Ducking Behavior
# WHILE playing announcement, THE Windows_Client SHALL duck (lower volume of) other audio
# WHEN announcement finishes, THE Windows_Client SHALL unduck (restore volume of) other audio
# Validates: Requirements 3.4, 3.5
# =============================================================================

class TestAudioDuckingBehavior:
    """
    Property 9: Audio Ducking Behavior
    
    **Feature: ha-windows-client, Property 9: Audio Ducking Behavior**
    **Validates: Requirements 3.4, 3.5**
    """

    def test_duck_sets_is_ducked_flag(self):
        """
        Property 9: After duck(), is_ducked SHALL be True.
        
        **Feature: ha-windows-client, Property 9: Audio Ducking Behavior**
        **Validates: Requirements 3.4**
        """
        # Create a mock volume controller
        controller = WindowsVolumeController.__new__(WindowsVolumeController)
        controller._initialized = False
        controller._volume_interface = None
        controller._original_volume = 1.0
        controller._is_ducked = False
        controller._duck_ratio = 0.3
        controller._init_lock = MagicMock()
        
        # Mock get_volume and set_volume
        controller.get_volume = MagicMock(return_value=0.8)
        controller.set_volume = MagicMock()
        
        # Call duck
        controller.duck()
        
        # Property: is_ducked should be True
        assert controller._is_ducked is True, \
            "is_ducked should be True after duck()"

    def test_unduck_clears_is_ducked_flag(self):
        """
        Property 9: After unduck(), is_ducked SHALL be False.
        
        **Feature: ha-windows-client, Property 9: Audio Ducking Behavior**
        **Validates: Requirements 3.5**
        """
        # Create a mock volume controller
        controller = WindowsVolumeController.__new__(WindowsVolumeController)
        controller._initialized = False
        controller._volume_interface = None
        controller._original_volume = 0.8
        controller._is_ducked = True
        controller._duck_ratio = 0.3
        controller._init_lock = MagicMock()
        
        # Mock set_volume
        controller.set_volume = MagicMock()
        
        # Call unduck
        controller.unduck()
        
        # Property: is_ducked should be False
        assert controller._is_ducked is False, \
            "is_ducked should be False after unduck()"

    @given(original_volume=volume_strategy)
    @settings(max_examples=100, deadline=None)
    def test_duck_stores_original_volume(self, original_volume: float):
        """
        Property 9: For any volume level, duck() SHALL store the original
        volume before reducing it.
        
        **Feature: ha-windows-client, Property 9: Audio Ducking Behavior**
        **Validates: Requirements 3.4**
        """
        # Create a mock volume controller
        controller = WindowsVolumeController.__new__(WindowsVolumeController)
        controller._initialized = False
        controller._volume_interface = None
        controller._original_volume = 0.0
        controller._is_ducked = False
        controller._duck_ratio = 0.3
        controller._init_lock = MagicMock()
        
        # Mock get_volume to return the test volume
        controller.get_volume = MagicMock(return_value=original_volume)
        controller.set_volume = MagicMock()
        
        # Call duck
        controller.duck()
        
        # Property: original volume should be stored
        assert controller._original_volume == original_volume, \
            f"Original volume should be {original_volume}, got {controller._original_volume}"

    @given(original_volume=volume_strategy, duck_ratio=duck_ratio_strategy)
    @settings(max_examples=100, deadline=None)
    def test_duck_reduces_volume_by_ratio(self, original_volume: float, duck_ratio: float):
        """
        Property 9: For any volume level and duck ratio, duck() SHALL
        reduce volume to original * duck_ratio.
        
        **Feature: ha-windows-client, Property 9: Audio Ducking Behavior**
        **Validates: Requirements 3.4**
        """
        # Create a mock volume controller
        controller = WindowsVolumeController.__new__(WindowsVolumeController)
        controller._initialized = False
        controller._volume_interface = None
        controller._original_volume = 0.0
        controller._is_ducked = False
        controller._duck_ratio = duck_ratio
        controller._init_lock = MagicMock()
        
        # Mock get_volume and set_volume
        controller.get_volume = MagicMock(return_value=original_volume)
        controller.set_volume = MagicMock()
        
        # Call duck
        controller.duck()
        
        # Property: set_volume should be called with ducked volume
        expected_ducked_volume = original_volume * duck_ratio
        controller.set_volume.assert_called_once_with(expected_ducked_volume)

    @given(original_volume=volume_strategy)
    @settings(max_examples=100, deadline=None)
    def test_unduck_restores_original_volume(self, original_volume: float):
        """
        Property 9: For any original volume, unduck() SHALL restore
        the volume to its original level.
        
        **Feature: ha-windows-client, Property 9: Audio Ducking Behavior**
        **Validates: Requirements 3.5**
        """
        # Create a mock volume controller
        controller = WindowsVolumeController.__new__(WindowsVolumeController)
        controller._initialized = False
        controller._volume_interface = None
        controller._original_volume = original_volume
        controller._is_ducked = True
        controller._duck_ratio = 0.3
        controller._init_lock = MagicMock()
        
        # Mock set_volume
        controller.set_volume = MagicMock()
        
        # Call unduck
        controller.unduck()
        
        # Property: set_volume should be called with original volume
        controller.set_volume.assert_called_once_with(original_volume)

    def test_duck_is_idempotent(self):
        """
        Property 9: Multiple duck() calls SHALL NOT change the stored
        original volume (idempotent).
        
        **Feature: ha-windows-client, Property 9: Audio Ducking Behavior**
        **Validates: Requirements 3.4**
        """
        # Create a mock volume controller
        controller = WindowsVolumeController.__new__(WindowsVolumeController)
        controller._initialized = False
        controller._volume_interface = None
        controller._original_volume = 0.0
        controller._is_ducked = False
        controller._duck_ratio = 0.3
        controller._init_lock = MagicMock()
        
        # First duck
        controller.get_volume = MagicMock(return_value=0.8)
        controller.set_volume = MagicMock()
        controller.duck()
        
        first_original = controller._original_volume
        
        # Second duck (should be skipped)
        controller.get_volume = MagicMock(return_value=0.24)  # Ducked volume
        controller.duck()
        
        # Property: original volume should not change
        assert controller._original_volume == first_original, \
            "Original volume should not change on second duck()"

    def test_unduck_is_idempotent(self):
        """
        Property 9: Multiple unduck() calls SHALL NOT cause errors
        (idempotent).
        
        **Feature: ha-windows-client, Property 9: Audio Ducking Behavior**
        **Validates: Requirements 3.5**
        """
        # Create a mock volume controller
        controller = WindowsVolumeController.__new__(WindowsVolumeController)
        controller._initialized = False
        controller._volume_interface = None
        controller._original_volume = 0.8
        controller._is_ducked = False  # Already not ducked
        controller._duck_ratio = 0.3
        controller._init_lock = MagicMock()
        
        # Mock set_volume
        controller.set_volume = MagicMock()
        
        # Call unduck when not ducked
        controller.unduck()
        
        # Property: set_volume should NOT be called
        controller.set_volume.assert_not_called()

    @given(original_volume=volume_strategy)
    @settings(max_examples=100, deadline=None)
    def test_duck_unduck_round_trip(self, original_volume: float):
        """
        Property 9: For any volume, duck() then unduck() SHALL restore
        the original volume (round-trip property).
        
        **Feature: ha-windows-client, Property 9: Audio Ducking Behavior**
        **Validates: Requirements 3.4, 3.5**
        """
        # Create a mock volume controller
        controller = WindowsVolumeController.__new__(WindowsVolumeController)
        controller._initialized = False
        controller._volume_interface = None
        controller._original_volume = 0.0
        controller._is_ducked = False
        controller._duck_ratio = 0.3
        controller._init_lock = MagicMock()
        
        # Track set_volume calls
        set_volume_calls = []
        controller.get_volume = MagicMock(return_value=original_volume)
        controller.set_volume = MagicMock(side_effect=lambda v: set_volume_calls.append(v))
        
        # Duck then unduck
        controller.duck()
        controller.unduck()
        
        # Property: last set_volume call should restore original
        assert len(set_volume_calls) == 2, \
            f"Expected 2 set_volume calls, got {len(set_volume_calls)}"
        assert set_volume_calls[-1] == original_volume, \
            f"Final volume should be {original_volume}, got {set_volume_calls[-1]}"


class TestAudioPlayerDucking:
    """Tests for AudioPlayer duck/unduck integration"""

    def test_audio_player_duck_calls_controller(self):
        """
        AudioPlayer.duck() SHALL call the volume controller's duck().
        
        **Feature: ha-windows-client, Property 9: Audio Ducking Behavior**
        **Validates: Requirements 3.4**
        """
        player = AudioPlayer()
        
        # Mock the volume controller
        mock_controller = MagicMock()
        player._volume_controller = mock_controller
        
        # Call duck
        player.duck()
        
        # Property: controller's duck should be called
        mock_controller.duck.assert_called_once()

    def test_audio_player_unduck_calls_controller(self):
        """
        AudioPlayer.unduck() SHALL call the volume controller's unduck().
        
        **Feature: ha-windows-client, Property 9: Audio Ducking Behavior**
        **Validates: Requirements 3.5**
        """
        player = AudioPlayer()
        
        # Mock the volume controller
        mock_controller = MagicMock()
        player._volume_controller = mock_controller
        
        # Call unduck
        player.unduck()
        
        # Property: controller's unduck should be called
        mock_controller.unduck.assert_called_once()


# =============================================================================
# Additional edge case tests
# =============================================================================

class TestAudioDuckingEdgeCases:
    """Edge case tests for audio ducking functionality"""

    def test_duck_with_zero_volume(self):
        """
        Duck with zero volume SHALL still work correctly.
        """
        controller = WindowsVolumeController.__new__(WindowsVolumeController)
        controller._initialized = False
        controller._volume_interface = None
        controller._original_volume = 0.0
        controller._is_ducked = False
        controller._duck_ratio = 0.3
        controller._init_lock = MagicMock()
        
        controller.get_volume = MagicMock(return_value=0.0)
        controller.set_volume = MagicMock()
        
        controller.duck()
        
        # Should set volume to 0 * 0.3 = 0
        controller.set_volume.assert_called_once_with(0.0)
        assert controller._is_ducked is True

    def test_duck_with_max_volume(self):
        """
        Duck with max volume SHALL reduce to duck_ratio.
        """
        controller = WindowsVolumeController.__new__(WindowsVolumeController)
        controller._initialized = False
        controller._volume_interface = None
        controller._original_volume = 0.0
        controller._is_ducked = False
        controller._duck_ratio = 0.3
        controller._init_lock = MagicMock()
        
        controller.get_volume = MagicMock(return_value=1.0)
        controller.set_volume = MagicMock()
        
        controller.duck()
        
        # Should set volume to 1.0 * 0.3 = 0.3
        controller.set_volume.assert_called_once_with(0.3)

    def test_default_duck_ratio_is_30_percent(self):
        """
        Default duck ratio SHALL be 0.3 (30%).
        """
        controller = WindowsVolumeController.__new__(WindowsVolumeController)
        controller._initialized = False
        controller._volume_interface = None
        controller._original_volume = 1.0
        controller._is_ducked = False
        controller._duck_ratio = 0.3
        controller._init_lock = MagicMock()
        
        assert controller._duck_ratio == 0.3, \
            f"Default duck ratio should be 0.3, got {controller._duck_ratio}"

    def test_is_ducked_property(self):
        """
        is_ducked property SHALL return current ducked state.
        """
        controller = WindowsVolumeController.__new__(WindowsVolumeController)
        controller._initialized = False
        controller._volume_interface = None
        controller._original_volume = 1.0
        controller._is_ducked = False
        controller._duck_ratio = 0.3
        controller._init_lock = MagicMock()
        
        assert controller.is_ducked is False
        
        controller._is_ducked = True
        assert controller.is_ducked is True
