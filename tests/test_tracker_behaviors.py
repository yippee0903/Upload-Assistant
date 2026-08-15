# Tests for tracker infrastructure — nfo_skip_trackers, notag_labels, COMMON helpers
"""
Test suite for per-tracker behavior attributes built at import time:
  1. nfo_skip_trackers  — frozenset built from skip_nfo class attrs
  2. notag_labels       — dict built from notag_label class attrs
  3. get_additional_files() — skip_nfo trackers return {}
"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.trackers.COMMON import COMMON


def _run(coro):
    return asyncio.run(coro)


# ═══════════════════════════════════════════════════════════════
#  1. skip_nfo — dynamic frozenset construction
# ═══════════════════════════════════════════════════════════════


class TestSkipNfoDynamicSet:
    """Verify nfo_skip_trackers is built correctly from class attrs."""

    def test_known_skip_nfo_members(self):
        from src.trackersetup import nfo_skip_trackers
        expected = {"DP", "HHD", "IHD", "LST", "LUME", "STC", "ULCX"}
        assert nfo_skip_trackers == expected

    def test_is_frozenset(self):
        from src.trackersetup import nfo_skip_trackers
        assert isinstance(nfo_skip_trackers, frozenset)

    def test_trackers_without_attr_excluded(self):
        """Trackers that don't define skip_nfo should not be in the set."""
        from src.trackersetup import nfo_skip_trackers, tracker_class_map
        assert "AITHER" not in nfo_skip_trackers
        assert not getattr(tracker_class_map["AITHER"], "skip_nfo", False)

    def test_skip_nfo_false_excluded(self):
        """A tracker with skip_nfo = False should not be in the set."""
        from src.trackersetup import tracker_class_map
        assert not getattr(tracker_class_map["BLU"], "skip_nfo", False)

    def test_getattr_robustness(self):
        """getattr(cls, 'skip_nfo', False) handles missing, False, 0, None, ''."""
        class NoAttr:
            pass

        class ExplicitFalse:
            skip_nfo = False

        class ExplicitZero:
            skip_nfo = 0

        class ExplicitNone:
            skip_nfo = None

        class ExplicitEmpty:
            skip_nfo = ""

        class ExplicitTrue:
            skip_nfo = True

        for cls in (NoAttr, ExplicitFalse, ExplicitZero, ExplicitNone, ExplicitEmpty):
            assert not getattr(cls, "skip_nfo", False), f"{cls.__name__} should be falsy"
        assert getattr(ExplicitTrue, "skip_nfo", False)


class TestGetAdditionalFilesSkipNfo:
    """Trackers with skip_nfo=True should return {} from get_additional_files."""

    @pytest.fixture
    def meta(self, tmp_path):
        return {
            "base_dir": str(tmp_path),
            "uuid": "test-uuid",
            "debug": False,
        }

    @pytest.mark.parametrize("tracker_name", ["DP", "HHD", "IHD", "LST", "LUME", "STC", "ULCX"])
    def test_get_additional_files_returns_empty(self, tracker_name, meta):
        """skip_nfo trackers that override get_additional_files must return {}."""
        from src.trackersetup import tracker_class_map
        cfg = {
            "TRACKERS": {tracker_name: {"api_key": "fake", "announce_url": ""}},
            "DEFAULT": {"tmdb_api": "fake"},
        }
        tracker = tracker_class_map[tracker_name](config=cfg)
        result = _run(tracker.get_additional_files(meta))
        assert result == {}


# ═══════════════════════════════════════════════════════════════
#  2. notag_label — dynamic dict construction
# ═══════════════════════════════════════════════════════════════


class TestNotagLabelsDynamicDict:
    """Verify notag_labels dict is built correctly from class attrs."""

    def test_known_notag_members(self):
        from src.trackersetup import notag_labels
        expected = {"C411": "NOTAG", "G3MINI": "NoGrP", "GF": "NoTag", "NST": "NoTag", "NXM": "NoGrp", "TORR9": "NoTag", "TOS": "NOTAG", "V3X": "NOTAG"}
        assert notag_labels == expected

    def test_empty_string_excluded(self):
        """notag_label = '' should not appear in the dict."""
        from src.trackersetup import notag_labels
        assert all(v for v in notag_labels.values()), "No empty labels allowed"

    def test_trackers_without_attr_excluded(self):
        """Trackers without notag_label attr should not be in the dict."""
        from src.trackersetup import notag_labels, tracker_class_map
        assert "BLU" not in notag_labels
        assert not getattr(tracker_class_map["BLU"], "notag_label", "")

    def test_getattr_robustness_notag(self):
        """getattr(cls, 'notag_label', '') handles missing, '', None, False."""
        class NoAttr:
            pass

        class EmptyStr:
            notag_label = ""

        class NoneVal:
            notag_label = None

        class FalseVal:
            notag_label = False

        class ValidLabel:
            notag_label = "TEST"

        for cls in (NoAttr, EmptyStr):
            assert not getattr(cls, "notag_label", ""), f"{cls.__name__} should be empty/falsy"
        assert getattr(NoneVal, "notag_label", "") is None
        assert getattr(FalseVal, "notag_label", "") is False
        assert getattr(ValidLabel, "notag_label", "") == "TEST"
