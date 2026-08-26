"""
Tests for src/commands/media_commands.py - volume clamping logic.

The COM/pycaw side effects are mocked out so no real system volume changes.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.commands.media_commands import MediaCommands


@pytest.fixture
def media():
    return MediaCommands()


class TestSetVolumeClamping:
    def _set_volume_no_thread(self, media, value):
        """Call set_volume with threading.Thread patched out."""
        with patch("threading.Thread") as mock_thread:
            result = media.set_volume(value)
            mock_thread.assert_called_once()  # worker never actually runs
        return result

    def test_valid_volume(self, media):
        result = self._set_volume_no_thread(media, "50")
        assert media._volume == 50
        assert isinstance(result, dict)

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("150", 100),
            ("-20", 0),
            ("999", 100),
            ("0", 0),
            ("100", 100),
        ],
    )
    def test_clamping(self, media, raw, expected):
        self._set_volume_no_thread(media, raw)
        assert media._volume == expected

    def test_non_numeric_rejected_without_state_change(self, media):
        with patch("threading.Thread"):
            result = media.set_volume("abc")
        assert media._volume == 50  # unchanged
        assert result.get("success") is False


class TestVolumeStateTracking:
    def test_initial_state(self, media):
        assert media._volume == 50
        assert media._is_playing is False
        assert media._is_muted is False
