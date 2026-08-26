"""
Tests for src/update_checker.py - pure version-comparison logic.
"""

import pytest

from src.update_checker import _compare_versions


class TestCompareVersions:
    @pytest.mark.parametrize(
        "current,latest,expected",
        [
            # simple cases
            ("0.9.0", "0.10.0", True),
            ("0.9.0", "1.0.0", True),
            ("0.8.1", "0.9.0", True),
            # equal -> no update
            ("0.9.0", "0.9.0", False),
            # older latest
            ("1.2.3", "1.2.2", False),
            ("1.0.0", "0.99.99", False),
            # different lengths (zero padding)
            ("0.9", "0.9.1", True),
            ("0.9.0", "0.9", False),
            ("1", "1.0.1", True),
            # multi-digit segments must compare numerically, not lexically
            ("0.9.9", "0.10.0", True),
            ("0.2.0", "0.10.0", True),
        ],
    )
    def test_comparison(self, current, latest, expected):
        assert _compare_versions(current, latest) is expected

    def test_invalid_version_returns_false(self):
        assert _compare_versions("not-a-version", "1.0.0") is False

    def test_empty_version_returns_false(self):
        assert _compare_versions("", "1.0.0") is False
