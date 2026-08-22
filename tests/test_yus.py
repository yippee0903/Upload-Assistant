# Tests for YUS tracker — yu-scene.net
"""
Test suite for YUS tracker pre-upload validation.
Covers: nogroup rejection in get_additional_checks().
  - YUS has no stated policy for untagged releases → reject them.
  - Known invalid placeholder tags (nogrp, nogroup, …) are also rejected.
  - Valid group tags pass through.
"""

import asyncio
from typing import Any

import pytest

from src.trackers.YUS import YUS


# ─── Helpers ──────────────────────────────────────────────────


def _config() -> dict[str, Any]:
    return {
        "TRACKERS": {
            "YUS": {
                "api_key": "fake-key",
                "announce_url": "https://yu-scene.net/announce/FAKE",
            }
        },
        "DEFAULT": {"tmdb_api": "fake-tmdb-key"},
    }


def _run(coro):
    return asyncio.run(coro)


def _meta(**overrides: Any) -> dict[str, Any]:
    m: dict[str, Any] = {
        "tag": "-FRiENDS",
        "keywords": "",
        "combined_genres": "",
        "unattended": True,
        "debug": False,
    }
    m.update(overrides)
    return m


# ═══════════════════════════════════════════════════════════════
#  Nogroup rejection — get_additional_checks()
# ═══════════════════════════════════════════════════════════════


class TestYUSAdultCheck:
    """TMDB tags mainstream adult cartoons 'adult animation'; only hentai/porn markers block."""

    def test_adult_animation_keyword_passes(self):
        meta = _meta(keywords="adult animation, satire", combined_genres="Animation, Comedy")
        assert _run(YUS(_config()).get_additional_checks(meta)) is True

    def test_hentai_keyword_is_rejected(self):
        meta = _meta(keywords="hentai, adult animation", combined_genres="Animation")
        assert _run(YUS(_config()).get_additional_checks(meta)) is False


class TestYUSNogroupRejection:
    """YUS has no policy for untagged releases — they must be rejected.

    Regression: before the get_tag fix the false tag '-DL.AAC.2.0.H.264' was
    accepted as a valid group. After the fix tag='' and YUS must refuse the upload.
    """

    def test_empty_tag_is_rejected(self):
        """tag='' → get_additional_checks returns False."""
        result = _run(YUS(_config()).get_additional_checks(_meta(tag="")))
        assert result is False, "YUS must reject releases with no group tag"

    def test_nogrp_tag_is_rejected(self):
        """'-nogrp' placeholder → rejected."""
        result = _run(YUS(_config()).get_additional_checks(_meta(tag="-nogrp")))
        assert result is False

    def test_nogroup_tag_is_rejected(self):
        """'-nogroup' placeholder → rejected."""
        result = _run(YUS(_config()).get_additional_checks(_meta(tag="-nogroup")))
        assert result is False

    def test_unknown_tag_is_rejected(self):
        """'-unknown' placeholder → rejected."""
        result = _run(YUS(_config()).get_additional_checks(_meta(tag="-unknown")))
        assert result is False

    def test_unk_tag_is_rejected(self):
        """'-unk' placeholder → rejected."""
        result = _run(YUS(_config()).get_additional_checks(_meta(tag="-unk")))
        assert result is False

    def test_valid_tag_passes(self):
        """A real group tag must not trigger rejection."""
        result = _run(YUS(_config()).get_additional_checks(_meta(tag="-FRiENDS")))
        assert result is True
