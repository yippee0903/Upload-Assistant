# Tests for RF tracker — reelflix.cc
"""
Test suite for RF release naming.
Covers: nogroup WEB-DL passthrough (no suffix appended).
  - RF accepts releases without a group tag and does NOT append any suffix.
  - Invalid/placeholder tags are stripped from the name.
  - Real group tags are preserved unchanged.
"""

import asyncio
from typing import Any

import pytest

from src.trackers.RF import RF


# ─── Helpers ──────────────────────────────────────────────────


def _config() -> dict[str, Any]:
    return {
        "TRACKERS": {
            "RF": {
                "api_key": "fake-key",
                "announce_url": "https://reelflix.cc/announce/FAKE",
            }
        },
        "DEFAULT": {"tmdb_api": "fake-tmdb-key"},
    }


def _run(coro):
    return asyncio.run(coro)


def _rf() -> RF:
    return RF(config=_config())


# ═══════════════════════════════════════════════════════════════
#  Nogroup WEB-DL naming — regression for Cyclo-style filenames
# ═══════════════════════════════════════════════════════════════


class TestNogroupWebDL:
    """RF accepts releases without a group tag — no suffix should be appended.

    Regression: before the get_tag fix, Cyclo.1995.1080p.WEB-DL.AAC.2.0.H.264.mkv
    had '-DL.AAC.2.0.H.264' extracted as the group and RF appended '-NoGroup' on
    top of the already-broken name. After the fix:
      - tag='' → RF must NOT append '-NoGroup' (just pass the clean name through)
      - invalid placeholder tags are stripped without adding a new suffix
      - real group tags are left unchanged
    """

    def test_empty_tag_no_suffix_added(self):
        """tag='' → name passed through as-is, no '-NoGroup' appended."""
        meta = {"name": "Cyclo.1995.1080p.WEB.AAC.2.0.H264", "tag": ""}
        result = _run(_rf().get_name(meta))["name"]
        assert not result.endswith("-NoGroup"), (
            f"RF must NOT append -NoGroup for empty tag, got: {result!r}"
        )
        assert result == "Cyclo.1995.1080p.WEB.AAC.2.0.H264", (
            f"Name should be unchanged, got: {result!r}"
        )

    def test_nogrp_tag_stripped_no_suffix(self):
        """'-nogrp' placeholder tag is stripped; no '-NoGroup' appended."""
        meta = {"name": "Cyclo.1995.1080p.WEB.AAC.2.0.H264-nogrp", "tag": "-nogrp"}
        result = _run(_rf().get_name(meta))["name"]
        assert "nogrp" not in result.lower(), f"Invalid token not stripped: {result!r}"
        assert not result.endswith("-NoGroup"), f"Unexpected -NoGroup suffix: {result!r}"

    def test_nogroup_tag_stripped_no_suffix(self):
        """'-NOGROUP' placeholder tag is stripped; no '-NoGroup' appended."""
        meta = {"name": "Movie.2024.1080p.WEB.H264-NOGROUP", "tag": "-NOGROUP"}
        result = _run(_rf().get_name(meta))["name"]
        assert "nogroup" not in result.lower(), f"Invalid token not stripped: {result!r}"
        assert not result.endswith("-NoGroup"), f"Unexpected -NoGroup suffix: {result!r}"

    def test_unknown_tag_stripped_no_suffix(self):
        """'-unknown' placeholder tag is stripped; no '-NoGroup' appended."""
        meta = {"name": "Title.2024.1080p.H264-unknown", "tag": "-unknown"}
        result = _run(_rf().get_name(meta))["name"]
        assert "unknown" not in result.lower(), f"Invalid token not stripped: {result!r}"
        assert not result.endswith("-NoGroup"), f"Unexpected -NoGroup suffix: {result!r}"

    def test_unk_tag_stripped_no_suffix(self):
        """'-unk' placeholder tag is stripped; no '-NoGroup' appended."""
        meta = {"name": "Title.2024.1080p.H264-unk", "tag": "-unk"}
        result = _run(_rf().get_name(meta))["name"]
        assert "unk" not in result.lower(), f"Invalid token not stripped: {result!r}"
        assert not result.endswith("-NoGroup"), f"Unexpected -NoGroup suffix: {result!r}"

    def test_real_group_tag_unchanged(self):
        """A real release group tag must be preserved exactly."""
        meta = {"name": "Movie.2024.1080p.WEB.H264-FRiENDS", "tag": "-FRiENDS"}
        result = _run(_rf().get_name(meta))["name"]
        assert result == "Movie.2024.1080p.WEB.H264-FRiENDS", (
            f"Real group tag must not be modified, got: {result!r}"
        )
