# Tests for STC tracker — seriestelly.com
"""
Test suite for the STC tracker implementation.
Covers: English language requirement in get_additional_checks(),
        TV-only category enforcement.
"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.trackers.STC import STC

# ─── Helpers ──────────────────────────────────────────────────


def _config() -> dict[str, Any]:
    return {
        "TRACKERS": {"STC": {"api_key": "fake", "announce_url": ""}},
        "DEFAULT": {"tmdb_api": "fake"},
    }


def _run(coro):
    return asyncio.run(coro)


# ═══════════════════════════════════════════════════════════════
#  English language requirement — get_additional_checks()
# ═══════════════════════════════════════════════════════════════


class TestSTCEnglishLanguageCheck:
    """English language requirement and TV-only gate in STC.get_additional_checks()."""

    @pytest.fixture
    def stc(self):
        return STC(config=_config())

    def test_english_audio_passes(self, stc):
        meta = {
            "category": "TV",
            "audio_languages": ["English"],
            "subtitle_languages": [],
            "is_disc": None,
            "type": "WEBDL",
            "debug": False,
            "unattended": True,
            "keywords": "",
            "combined_genres": "",
        }
        with patch("src.trackers.COMMON.languages_manager") as mock_lm:
            mock_lm.process_desc_language = AsyncMock()
            assert _run(stc.get_additional_checks(meta)) is True

    def test_no_english_fails(self, stc):
        meta = {
            "category": "TV",
            "audio_languages": ["French"],
            "subtitle_languages": [],
            "is_disc": None,
            "type": "WEBDL",
            "debug": False,
            "unattended": True,
            "keywords": "",
            "combined_genres": "",
        }
        with patch("src.trackers.COMMON.languages_manager") as mock_lm:
            mock_lm.process_desc_language = AsyncMock()
            assert _run(stc.get_additional_checks(meta)) is False

    def test_disc_skips_language_check(self, stc):
        meta = {
            "category": "TV",
            "audio_languages": [],
            "subtitle_languages": [],
            "is_disc": "BDMV",
            "type": "DISC",
            "debug": False,
            "unattended": True,
            "keywords": "",
            "combined_genres": "",
        }
        assert _run(stc.get_additional_checks(meta)) is True

    def test_movie_rejected(self, stc):
        """STC only accepts TV uploads."""
        meta = {
            "category": "MOVIE",
            "audio_languages": ["English"],
            "subtitle_languages": [],
            "is_disc": None,
            "type": "WEBDL",
            "debug": False,
            "unattended": True,
            "keywords": "",
            "combined_genres": "",
        }
        assert _run(stc.get_additional_checks(meta)) is False

    def test_adult_animation_keyword_passes(self, stc):
        """TMDB tags mainstream adult cartoons 'adult animation'; only hentai/porn markers block."""
        meta = {
            "category": "TV",
            "audio_languages": ["English"],
            "subtitle_languages": [],
            "is_disc": None,
            "type": "WEBDL",
            "debug": False,
            "unattended": True,
            "keywords": "adult animation, satire",
            "combined_genres": "Animation, Comedy",
        }
        with patch("src.trackers.COMMON.languages_manager") as mock_lm:
            mock_lm.process_desc_language = AsyncMock()
            assert _run(stc.get_additional_checks(meta)) is True

    def test_hentai_keyword_fails(self, stc):
        meta = {
            "category": "TV",
            "audio_languages": ["English"],
            "subtitle_languages": [],
            "is_disc": None,
            "type": "WEBDL",
            "debug": False,
            "unattended": True,
            "keywords": "hentai, adult animation",
            "combined_genres": "Animation",
        }
        assert _run(stc.get_additional_checks(meta)) is False


def test_approved_image_hosts() -> None:
    # Rules only ask for lossless thumbnails linking to full-size images;
    # ptscreens keeps the PNG intact and is in use on the site (pixhost is not rendered).
    assert STC(config=_config()).approved_image_hosts == ["imgbox", "imgbb", "ptscreens"]
