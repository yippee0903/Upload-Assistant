# Tests for COMMON tracker base class
"""
Test suite for COMMON tracker base class utilities.
Covers: check_language_requirements() — coercion, matching, flags.
"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.trackers.COMMON import COMMON

# ─── Helpers ──────────────────────────────────────────────────


def _config() -> dict[str, Any]:
    return {"DEFAULT": {"tmdb_api": "fake"}, "TRACKERS": {}}


def _run(coro):
    return asyncio.run(coro)


# ═══════════════════════════════════════════════════════════════
#  check_language_requirements() — coercion and matching edge cases
# ═══════════════════════════════════════════════════════════════


class TestCheckLanguageRequirementsEdgeCases:
    """Direct tests of COMMON.check_language_requirements with edge-case inputs."""

    @pytest.fixture
    def common(self):
        return COMMON(config=_config())

    def test_audio_languages_is_string(self, common):
        """audio_languages as a string should be coerced to list."""
        meta = {
            "audio_languages": "French",
            "subtitle_languages": [],
            "debug": False,
            "unattended": True,
        }
        with patch("src.trackers.COMMON.languages_manager") as mock_lm:
            mock_lm.process_desc_language = AsyncMock()
            result = _run(common.check_language_requirements(
                meta, "TEST", languages_to_check=["french"], check_audio=True
            ))
        assert result is True

    def test_audio_languages_is_none(self, common):
        """audio_languages = None should be coerced to []."""
        meta = {
            "audio_languages": None,
            "subtitle_languages": [],
            "debug": False,
            "unattended": True,
        }
        with patch("src.trackers.COMMON.languages_manager") as mock_lm:
            mock_lm.process_desc_language = AsyncMock()
            result = _run(common.check_language_requirements(
                meta, "TEST", languages_to_check=["french"], check_audio=True
            ))
        assert result is False

    def test_subtitle_languages_is_none(self, common):
        """subtitle_languages = None should be coerced to []."""
        meta = {
            "audio_languages": [],
            "subtitle_languages": None,
            "debug": False,
            "unattended": True,
        }
        with patch("src.trackers.COMMON.languages_manager") as mock_lm:
            mock_lm.process_desc_language = AsyncMock()
            result = _run(common.check_language_requirements(
                meta, "TEST", languages_to_check=["french"], check_subtitle=True
            ))
        assert result is False

    def test_no_check_flags_returns_true(self, common):
        """If neither check_audio nor check_subtitle, should return True."""
        meta = {
            "audio_languages": [],
            "subtitle_languages": [],
            "debug": False,
            "unattended": True,
        }
        with patch("src.trackers.COMMON.languages_manager") as mock_lm:
            mock_lm.process_desc_language = AsyncMock()
            result = _run(common.check_language_requirements(
                meta, "TEST", languages_to_check=["french"]
            ))
        assert result is True

    def test_require_both_needs_audio_and_subtitle(self, common):
        """require_both=True: having only audio French should fail."""
        meta = {
            "audio_languages": ["French"],
            "subtitle_languages": ["English"],
            "debug": False,
            "unattended": True,
        }
        with patch("src.trackers.COMMON.languages_manager") as mock_lm:
            mock_lm.process_desc_language = AsyncMock()
            result = _run(common.check_language_requirements(
                meta, "TEST", languages_to_check=["french"],
                check_audio=True, check_subtitle=True, require_both=True
            ))
        assert result is False

    def test_require_both_passes_when_both_present(self, common):
        meta = {
            "audio_languages": ["French"],
            "subtitle_languages": ["French"],
            "debug": False,
            "unattended": True,
        }
        with patch("src.trackers.COMMON.languages_manager") as mock_lm:
            mock_lm.process_desc_language = AsyncMock()
            result = _run(common.check_language_requirements(
                meta, "TEST", languages_to_check=["french"],
                check_audio=True, check_subtitle=True, require_both=True
            ))
        assert result is True

    def test_case_insensitive_matching(self, common):
        """Language matching should be case-insensitive."""
        meta = {
            "audio_languages": ["FRENCH"],
            "subtitle_languages": [],
            "debug": False,
            "unattended": True,
        }
        with patch("src.trackers.COMMON.languages_manager") as mock_lm:
            mock_lm.process_desc_language = AsyncMock()
            result = _run(common.check_language_requirements(
                meta, "TEST", languages_to_check=["french"], check_audio=True
            ))
        assert result is True

    def test_mixed_list_with_non_strings(self, common):
        """Non-string elements in audio_languages should be filtered out."""
        meta = {
            "audio_languages": ["French", 42, None, "English"],
            "subtitle_languages": [],
            "debug": False,
            "unattended": True,
        }
        with patch("src.trackers.COMMON.languages_manager") as mock_lm:
            mock_lm.process_desc_language = AsyncMock()
            result = _run(common.check_language_requirements(
                meta, "TEST", languages_to_check=["french"], check_audio=True
            ))
        assert result is True


# ═══════════════════════════════════════════════════════════════
#  _is_renamed() and check_detag() rename detection
# ═══════════════════════════════════════════════════════════════


class TestRenameDetection:
    """The on-disk filename must match the name muxed in by the release group."""

    @pytest.fixture
    def common(self):
        return COMMON(config=_config())

    def test_not_renamed_extension_only(self, common):
        # On-disk name == embedded name apart from the extension → not renamed.
        assert common._is_renamed("Movie.2026.1080p.BluRay.x264-GRP.mkv", "Movie.2026.1080p.BluRay.x264-GRP") is False

    def test_renamed_dots_vs_spaces(self, common):
        # Even a separator change breaks cross-seeding → treated as a rename.
        assert common._is_renamed("Movie 2026 1080p BluRay x264-GRP.mkv", "Movie.2026.1080p.BluRay.x264-GRP") is True

    def test_not_renamed_exact_match(self, common):
        # Identical apart from the extension → not renamed.
        assert common._is_renamed("Movie.2026.1080p.BluRay.x264-GRP.mkv", "Movie.2026.1080p.BluRay.x264-GRP") is False

    def test_renamed_to_junk(self, common):
        assert common._is_renamed("movie.mkv", "Movie.2026.1080p.BluRay.x264-GRP") is True

    def test_renamed_faked_resolution(self, common):
        assert common._is_renamed("Movie.2026.2160p.BluRay.x264-GRP.mkv", "Movie.2026.1080p.BluRay.x264-GRP") is True

    def test_empty_names_never_renamed(self, common):
        assert common._is_renamed("", "Movie-GRP") is False
        assert common._is_renamed("Movie-GRP.mkv", "") is False

    def test_check_detag_flags_rename(self, common):
        # Group matches (not detag/notag) but the on-disk name was changed.
        meta = {"tag": "-GRP"}
        with patch.object(
            common, "_get_mediainfo_filename",
            AsyncMock(return_value=("Movie.2026.1080p.BluRay.x264-GRP", "Movie.2026.2160p.BluRay.x264-GRP.mkv")),
        ):
            result = _run(common.check_detag(meta, "TEST"))
        assert result is True
        assert meta["detag_info"]["type"] == "rename"
        assert meta["detag_info"]["disk_filename"] == "Movie.2026.2160p.BluRay.x264-GRP.mkv"

    def test_check_detag_no_rename_when_names_match(self, common):
        meta = {"tag": "-GRP"}
        with patch.object(
            common, "_get_mediainfo_filename",
            AsyncMock(return_value=("Movie.2026.1080p.BluRay.x264-GRP", "Movie.2026.1080p.BluRay.x264-GRP.mkv")),
        ):
            result = _run(common.check_detag(meta, "TEST"))
        assert result is False
        assert "detag_info" not in meta

    def test_not_renamed_m2ts_extension(self, common):
        # ".m2ts" must be dropped whole, not truncated to ".m2" by a ".ts" match.
        assert common._is_renamed("Movie.2026.1080p.BluRay.x264-GRP.m2ts", "Movie.2026.1080p.BluRay.x264-GRP") is False

    def test_check_detag_no_rename_without_group_tag(self, common):
        # Embedded name is a plain human title (no -GROUP suffix): we don't trust
        # its format, so a mismatch must NOT be flagged as a rename.
        meta = {"tag": "-GRP"}
        with patch.object(
            common, "_get_mediainfo_filename",
            AsyncMock(return_value=("The Movie 2026", "Movie.2026.1080p.BluRay.x264-GRP.mkv")),
        ):
            result = _run(common.check_detag(meta, "TEST"))
        assert result is False
        assert "detag_info" not in meta
