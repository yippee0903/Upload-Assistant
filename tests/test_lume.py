# Tests for LUME tracker — luminarr.me
"""
Test suite for LUME release naming.
Covers: nogroup WEB-DL → '-NOGROUP' suffix.
  - LUME requires a '-NOGROUP' suffix for releases without a group tag.
  - Invalid/placeholder tags are stripped and replaced with '-NOGROUP'.
  - Real group tags are preserved unchanged.
"""

import asyncio
from typing import Any

import pytest

from src.trackers.LUME import LUME


# ─── Helpers ──────────────────────────────────────────────────


def _config() -> dict[str, Any]:
    return {
        "TRACKERS": {
            "LUME": {
                "api_key": "fake-key",
                "announce_url": "https://luminarr.me/announce/FAKE",
            }
        },
        "DEFAULT": {"tmdb_api": "fake-tmdb-key"},
    }


def _run(coro):
    return asyncio.run(coro)


def _lume() -> LUME:
    return LUME(config=_config())


# ═══════════════════════════════════════════════════════════════
#  Nogroup WEB-DL naming — regression for Cyclo-style filenames
# ═══════════════════════════════════════════════════════════════


class TestNogroupWebDL:
    """LUME requires '-NOGROUP' suffix for releases without a group tag.

    Regression: before the get_tag fix, Cyclo.1995.1080p.WEB-DL.AAC.2.0.H.264.mkv
    had '-DL.AAC.2.0.H.264' extracted as the group and it was appended verbatim.
    After the fix, tag='' and LUME must substitute '-NOGROUP'.
    """

    def test_empty_tag_adds_nogroup_suffix(self):
        """tag='' → '-NOGROUP' appended."""
        meta = {"name": "Cyclo.1995.1080p.WEB.AAC.2.0.H264", "tag": ""}
        result = _run(_lume().get_name(meta))["name"]
        assert result.endswith("-NOGROUP"), (
            f"Expected -NOGROUP suffix, got: {result!r}"
        )

    def test_nogrp_replaced_with_nogroup(self):
        """'-nogrp' placeholder stripped and replaced with '-NOGROUP'."""
        meta = {"name": "Cyclo.1995.1080p.WEB.AAC.2.0.H264-nogrp", "tag": "-nogrp"}
        result = _run(_lume().get_name(meta))["name"]
        assert result.endswith("-NOGROUP"), f"Expected -NOGROUP suffix, got: {result!r}"
        assert "nogrp" not in result.lower().replace("nogroup", ""), (
            f"Invalid token should have been stripped: {result!r}"
        )

    def test_no_audio_duplication(self):
        """Audio token must appear exactly once — no duplication from a false tag."""
        meta = {"name": "Cyclo.1995.1080p.WEB.AAC.2.0.H264", "tag": ""}
        result = _run(_lume().get_name(meta))["name"]
        assert result.count("AAC") == 1, f"Audio token duplicated: {result!r}"
        assert result.count("H264") == 1, f"Codec token duplicated: {result!r}"

    def test_real_group_tag_unchanged(self):
        """A real release group tag must be preserved; '-NOGROUP' must NOT be added."""
        meta = {"name": "Movie.2024.1080p.WEB.H264-FRiENDS", "tag": "-FRiENDS"}
        result = _run(_lume().get_name(meta))["name"]
        assert result == "Movie.2024.1080p.WEB.H264-FRiENDS", (
            f"Real group tag must not be modified, got: {result!r}"
        )
        assert "NOGROUP" not in result, f"NOGROUP must not appear when tag is valid: {result!r}"
