"""
Property-Based Tests for Audio Recording Functionality

Tests Property 17: Audio Recording Format

Validates: Requirements 9.1
"""

import logging
from typing import Optional
from unittest.mock import MagicMock, patch
import struct

import numpy as np
import pytest
from hypothesis import given, strategies as st, settings, assume

# Import the audio recorder module
from src.voice.audio_recorder import AudioRecorder


# =============================================================================
# Strategies for generating test data
# =============================================================================

# Strategy for generating audio samples (float32, range -1.0 to 1.0)
audio_sample_strategy = st.floats(min_value=-1.0, max_value=1.0, allow_nan=False)

# Strategy for generating audio arrays
audio_array_strategy = st.lists(
    audio_sample_strategy,
    min_size=1,
    max_size=2048
).map(lambda x: np.array(x, dtype=np.float32))

# Strategy for generating duration in seconds
duration_strategy = st.floats(min_value=0.01, max_value=1.0, allow_nan=False)


# =============================================================================
# Property 17: Audio Recording Format
# THE Windows_Client SHALL record audio at 16kHz mono PCM format for voice assistant
# Validates: Requirements 9.1
# =============================================================================

class TestAudioRecordingFormat:
    """
    Property 17: Audio Recording Format
    
    **Feature: ha-windows-client, Property 17: Audio Recording Format**
    **Validates: Requirements 9.1**
    """

    def test_sample_rate_is_16khz(self):
        """
        Property 17: Audio recording sample rate SHALL be 16kHz.
        
        **Feature: ha-windows-client, Property 17: Audio Recording Format**
        **Validates: Requirements 9.1**
        """
        assert AudioRecorder.SAMPLE_RATE == 16000, \
            f"Sample rate should be 16000 Hz, got {AudioRecorder.SAMPLE_RATE}"

    def test_channels_is_mono(self):
        """
        Property 17: Audio recording SHALL be mono (1 channel).
        
        **Feature: ha-windows-client, Property 17: Audio Recording Format**
        **Validates: Requirements 9.1**
        """
        assert AudioRecorder.CHANNELS == 1, \
            f"Channels should be 1 (mono), got {AudioRecorder.CHANNELS}"

    @given(audio_array=audio_array_strategy)
    @settings(max_examples=100, deadline=None)
    def test_pcm_conversion_produces_16bit_signed(self, audio_array: np.ndarray):
        """
        Property 17: For any audio array, PCM conversion SHALL produce
        16-bit signed little-endian format.
        
        **Feature: ha-windows-client, Property 17: Audio Recording Format**
        **Validates: Requirements 9.1**
        """
        recorder = AudioRecorder()
        
        # Convert to PCM
        pcm_data = recorder._array_to_pcm(audio_array)
        
        # Property: output should be bytes
        assert isinstance(pcm_data, bytes), \
            "PCM output should be bytes"
        
        # Property: length should be 2 bytes per sample (16-bit)
        expected_length = len(audio_array) * 2
        assert len(pcm_data) == expected_length, \
            f"PCM length should be {expected_length}, got {len(pcm_data)}"

    @given(audio_array=audio_array_strategy)
    @settings(max_examples=100, deadline=None)
    def test_pcm_values_in_valid_range(self, audio_array: np.ndarray):
        """
        Property 17: For any audio array, PCM values SHALL be in valid
        16-bit signed range (-32768 to 32767).
        
        **Feature: ha-windows-client, Property 17: Audio Recording Format**
        **Validates: Requirements 9.1**
        """
        recorder = AudioRecorder()
        
        # Convert to PCM
        pcm_data = recorder._array_to_pcm(audio_array)
        
        # Unpack as 16-bit signed integers (little-endian)
        num_samples = len(pcm_data) // 2
        values = struct.unpack(f'<{num_samples}h', pcm_data)
        
        # Property: all values should be in valid range
        for value in values:
            assert -32768 <= value <= 32767, \
                f"PCM value {value} out of valid range"

    @given(sample=st.floats(min_value=-10.0, max_value=10.0, allow_nan=False))
    @settings(max_examples=100, deadline=None)
    def test_pcm_clips_out_of_range_values(self, sample: float):
        """
        Property 17: For any out-of-range audio sample, PCM conversion
        SHALL clip to valid range.
        
        **Feature: ha-windows-client, Property 17: Audio Recording Format**
        **Validates: Requirements 9.1**
        """
        recorder = AudioRecorder()
        
        # Create array with single sample
        audio_array = np.array([sample], dtype=np.float32)
        
        # Convert to PCM
        pcm_data = recorder._array_to_pcm(audio_array)
        
        # Unpack value
        value = struct.unpack('<h', pcm_data)[0]
        
        # Property: value should be clipped to valid range
        assert -32768 <= value <= 32767, \
            f"PCM value {value} should be clipped to valid range"
        
        # Property: extreme values should be clipped
        # Note: -1.0 * 32767 = -32767, not -32768 (symmetric clipping)
        if sample > 1.0:
            assert value == 32767, \
                f"Sample {sample} > 1.0 should clip to 32767, got {value}"
        elif sample < -1.0:
            assert value == -32767, \
                f"Sample {sample} < -1.0 should clip to -32767, got {value}"

    @given(duration=duration_strategy)
    @settings(max_examples=100, deadline=None)
    def test_silence_generation_correct_length(self, duration: float):
        """
        Property 17: For any duration, silence generation SHALL produce
        correct number of samples at 16kHz.
        
        **Feature: ha-windows-client, Property 17: Audio Recording Format**
        **Validates: Requirements 9.1**
        """
        # Generate silence
        silence = AudioRecorder.create_silence(duration)
        
        # Expected samples
        expected_samples = int(AudioRecorder.SAMPLE_RATE * duration)
        expected_bytes = expected_samples * 2  # 16-bit = 2 bytes
        
        # Property: silence length should match expected
        assert len(silence) == expected_bytes, \
            f"Silence length should be {expected_bytes}, got {len(silence)}"

    @given(duration=duration_strategy)
    @settings(max_examples=100, deadline=None)
    def test_silence_is_all_zeros(self, duration: float):
        """
        Property 17: For any duration, silence SHALL contain all zero values.
        
        **Feature: ha-windows-client, Property 17: Audio Recording Format**
        **Validates: Requirements 9.1**
        """
        # Generate silence
        silence = AudioRecorder.create_silence(duration)
        
        # Unpack as 16-bit signed integers
        num_samples = len(silence) // 2
        if num_samples > 0:
            values = struct.unpack(f'<{num_samples}h', silence)
            
            # Property: all values should be zero
            for value in values:
                assert value == 0, \
                    f"Silence should contain all zeros, found {value}"

    def test_recorder_initialization_defaults(self):
        """
        Property 17: AudioRecorder SHALL initialize with correct defaults.
        
        **Feature: ha-windows-client, Property 17: Audio Recording Format**
        **Validates: Requirements 9.1**
        """
        recorder = AudioRecorder()
        
        assert recorder.device is None, "Default device should be None"
        assert recorder.is_recording is False, "Should not be recording initially"
        assert recorder.mic is None, "Mic should be None initially"

    @given(audio_array=audio_array_strategy)
    @settings(max_examples=100, deadline=None)
    def test_pcm_conversion_preserves_sample_count(self, audio_array: np.ndarray):
        """
        Property 17: For any audio array, PCM conversion SHALL preserve
        the number of samples.
        
        **Feature: ha-windows-client, Property 17: Audio Recording Format**
        **Validates: Requirements 9.1**
        """
        recorder = AudioRecorder()
        
        # Convert to PCM
        pcm_data = recorder._array_to_pcm(audio_array)
        
        # Calculate number of samples from PCM data
        pcm_samples = len(pcm_data) // 2
        
        # Property: sample count should be preserved
        assert pcm_samples == len(audio_array), \
            f"Sample count mismatch: input {len(audio_array)}, output {pcm_samples}"


# =============================================================================
# Additional edge case tests
# =============================================================================

class TestAudioRecordingEdgeCases:
    """Edge case tests for audio recording functionality"""

    def test_empty_array_conversion(self):
        """
        Empty audio array SHALL produce empty PCM output.
        """
        recorder = AudioRecorder()
        
        empty_array = np.array([], dtype=np.float32)
        pcm_data = recorder._array_to_pcm(empty_array)
        
        assert len(pcm_data) == 0, "Empty array should produce empty PCM"

    def test_single_sample_conversion(self):
        """
        Single sample SHALL be correctly converted to 2 bytes.
        """
        recorder = AudioRecorder()
        
        single_sample = np.array([0.5], dtype=np.float32)
        pcm_data = recorder._array_to_pcm(single_sample)
        
        assert len(pcm_data) == 2, "Single sample should produce 2 bytes"
        
        # Check value (0.5 * 32767 ≈ 16383)
        value = struct.unpack('<h', pcm_data)[0]
        assert 16380 <= value <= 16390, f"Expected ~16383, got {value}"

    def test_max_positive_sample(self):
        """
        Maximum positive sample (1.0) SHALL convert to 32767.
        """
        recorder = AudioRecorder()
        
        max_sample = np.array([1.0], dtype=np.float32)
        pcm_data = recorder._array_to_pcm(max_sample)
        
        value = struct.unpack('<h', pcm_data)[0]
        assert value == 32767, f"Max sample should be 32767, got {value}"

    def test_max_negative_sample(self):
        """
        Maximum negative sample (-1.0) SHALL convert to -32767.
        """
        recorder = AudioRecorder()
        
        min_sample = np.array([-1.0], dtype=np.float32)
        pcm_data = recorder._array_to_pcm(min_sample)
        
        value = struct.unpack('<h', pcm_data)[0]
        assert value == -32767, f"Min sample should be -32767, got {value}"

    def test_zero_sample(self):
        """
        Zero sample SHALL convert to 0.
        """
        recorder = AudioRecorder()
        
        zero_sample = np.array([0.0], dtype=np.float32)
        pcm_data = recorder._array_to_pcm(zero_sample)
        
        value = struct.unpack('<h', pcm_data)[0]
        assert value == 0, f"Zero sample should be 0, got {value}"

    def test_list_microphones_returns_list(self):
        """
        list_microphones() SHALL return a list.
        """
        mics = AudioRecorder.list_microphones()
        
        assert isinstance(mics, list), "list_microphones should return a list"

    def test_zero_duration_silence(self):
        """
        Zero duration silence SHALL produce empty bytes.
        """
        silence = AudioRecorder.create_silence(0.0)
        
        assert len(silence) == 0, "Zero duration should produce empty silence"
