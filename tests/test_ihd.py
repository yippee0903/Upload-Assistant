# Tests for IHD tracker — iheartdrama.org
"""
Test suite for the IHD tracker implementation.
Covers: edition stripping for non-Full Disc types in get_name().
"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.trackers.IHD import IHD

# ─── Helpers ──────────────────────────────────────────────────


def _config() -> dict[str, Any]:
    return {
        "TRACKERS": {"IHD": {"api_key": "fake", "announce_url": ""}},
        "DEFAULT": {"tmdb_api": "fake"},
    }


def _run(coro):
    return asyncio.run(coro)


# ═══════════════════════════════════════════════════════════════
#  get_name() — edition stripping for non-Full Disc types
# ═══════════════════════════════════════════════════════════════


class TestIHDGetNameEdition:
    """IHD naming guide: Edition (Remastered, Anniversary…) is omitted for
    non-Full Disc types, but Cut (Director's Cut, Extended, Special Edition,
    Theatrical, Unrated, IMAX, Open Matte) is always kept."""

    @pytest.fixture
    def ihd(self):
        return IHD(config=_config())

    def _run_get_name(self, ihd, meta):
        with patch("src.trackers.IHD.languages_manager") as mock_lm:
            mock_lm.process_desc_language = AsyncMock()
            mock_lm.has_english_language = AsyncMock(return_value=True)
            return _run(ihd.get_name(meta))

    def test_encode_strips_edition(self, ihd):
        """Regression: RESTORED must be removed from an encode title (IHD staff rejection)."""
        meta = {
            "name": "Seven Samurai AKA Shichinin no samurai 1954 RESTORED REPACK 1080p BluRay AAC 1.0 x264-hallowed",
            "resolution": "1080p",
            "edition": "RESTORED",
            "is_disc": None,
            "type": "ENCODE",
            "language_checked": True,
            "audio_languages": ["Japanese"],
        }
        with patch("src.trackers.IHD.languages_manager") as mock_lm:
            mock_lm.process_desc_language = AsyncMock()
            mock_lm.has_english_language = AsyncMock(return_value=False)
            result = _run(ihd.get_name(meta))
        assert "RESTORED" not in result["name"]
        assert "Seven Samurai" in result["name"]
        assert "1080p" in result["name"]

    def test_webdl_strips_edition(self, ihd):
        """Edition must also be stripped for WEB-DL releases."""
        meta = {
            "name": "Some Film 2020 Remastered 1080p AMZN WEB-DL AAC 2.0 x264-GRP",
            "resolution": "1080p",
            "edition": "Remastered",
            "is_disc": None,
            "type": "WEBDL",
            "language_checked": True,
            "audio_languages": ["English"],
        }
        result = self._run_get_name(ihd, meta)
        assert "Remastered" not in result["name"]
        assert "Some Film" in result["name"]

    def test_remux_strips_edition(self, ihd):
        """Edition (Remastered) must be stripped for REMUX releases (non-Full Disc)."""
        meta = {
            "name": "Some Film 2020 Remastered 1080p BluRay REMUX DTS 5.1 AVC-GRP",
            "resolution": "1080p",
            "edition": "Remastered",
            "is_disc": None,
            "type": "REMUX",
            "language_checked": True,
            "audio_languages": ["English"],
        }
        result = self._run_get_name(ihd, meta)
        assert "Remastered" not in result["name"]
        assert "Some Film" in result["name"]

    def test_multiword_edition_stripped_leaves_no_double_spaces(self, ihd):
        """Stripping a multi-word Edition (e.g. 25TH ANNIVERSARY) must not leave double spaces."""
        meta = {
            "name": "Blade Runner 1982 25TH ANNIVERSARY 1080p BluRay DD+ 5.1 x264-GRP",
            "resolution": "1080p",
            "edition": "25TH ANNIVERSARY",
            "is_disc": None,
            "type": "ENCODE",
            "language_checked": True,
            "audio_languages": ["English"],
        }
        result = self._run_get_name(ihd, meta)
        assert "25TH ANNIVERSARY" not in result["name"]
        assert "  " not in result["name"], "double space found after edition removal"
        assert "1982 1080p" in result["name"]

    # ------------------------------------------------------------------ Cut preserved

    def test_cut_special_edition_kept_for_encode(self, ihd):
        """'Special Edition' is a Cut per IHD guide and must be kept for encodes."""
        meta = {
            "name": "Terminator 2: Judgment Day 1991 SPECIAL EDITION 1080p BluRay DD+ 5.1 x264-hallowed",
            "resolution": "1080p",
            "edition": "SPECIAL EDITION",
            "is_disc": None,
            "type": "ENCODE",
            "language_checked": True,
            "audio_languages": ["English"],
        }
        result = self._run_get_name(ihd, meta)
        assert "SPECIAL EDITION" in result["name"]

    def test_cut_extended_kept_for_encode(self, ihd):
        """'Extended' is a Cut per IHD guide and must be kept for encodes."""
        meta = {
            "name": "Some Film 2020 Extended 1080p BluRay REMUX DTS 5.1 AVC-GRP",
            "resolution": "1080p",
            "edition": "Extended",
            "is_disc": None,
            "type": "ENCODE",
            "language_checked": True,
            "audio_languages": ["English"],
        }
        result = self._run_get_name(ihd, meta)
        assert "Extended" in result["name"]

    def test_cut_directors_cut_kept_for_encode(self, ihd):
        """'Director's Cut' is a Cut per IHD guide and must be kept for encodes."""
        meta = {
            "name": "Aliens 1986 DIRECTOR'S CUT 1080p BluRay DTS 5.1 x264-GRP",
            "resolution": "1080p",
            "edition": "DIRECTOR'S CUT",
            "is_disc": None,
            "type": "ENCODE",
            "language_checked": True,
            "audio_languages": ["English"],
        }
        result = self._run_get_name(ihd, meta)
        assert "DIRECTOR'S CUT" in result["name"]

    def test_bdmv_keeps_edition(self, ihd):
        """Full Disc (BDMV) releases must keep their edition."""
        meta = {
            "name": "Some Film 2020 Collector Edition Blu-ray AVC DTS-HD MA 5.1-GRP",
            "resolution": "1080p",
            "edition": "Collector Edition",
            "is_disc": "BDMV",
            "type": "DISC",
            "language_checked": True,
            "audio_languages": ["English"],
        }
        result = self._run_get_name(ihd, meta)
        assert "Collector Edition" in result["name"]

    def test_dvd_keeps_edition(self, ihd):
        """Full Disc (DVD) releases must keep their edition."""
        meta = {
            "name": "Some Film 2020 Director's Cut DVD AC3 2.0-GRP",
            "resolution": "576p",
            "edition": "Director's Cut",
            "is_disc": "DVD",
            "type": "DISC",
            "language_checked": True,
            "audio_languages": ["English"],
        }
        result = self._run_get_name(ihd, meta)
        assert "Director's Cut" in result["name"]

    def test_no_edition_name_unchanged(self, ihd):
        """When edition is empty, name must not be altered."""
        original = "Some Film 2020 1080p BluRay AAC 2.0 x264-GRP"
        meta = {
            "name": original,
            "resolution": "1080p",
            "edition": "",
            "is_disc": None,
            "type": "ENCODE",
            "language_checked": True,
            "audio_languages": ["English"],
        }
        result = self._run_get_name(ihd, meta)
        assert result["name"] == original


# ═══════════════════════════════════════════════════════════════
#  get_name() — service token preservation (MGMP / MGM+)
# ═══════════════════════════════════════════════════════════════


class TestIHDGetNameService:
    """IHD naming: service tokens such as MGMP must be preserved in the output name."""

    @pytest.fixture
    def ihd(self):
        return IHD(config=_config())

    def test_mgmp_preserved_in_webdl_name(self, ihd):
        """Back to the Future (MGMP WEB-DL) must keep the MGMP service token."""
        meta = {
            "name": "Back to the Future 1985 1080p MGMP WEB-DL DD+ 5.1 H.264-PiRaTeS",
            "resolution": "1080p",
            "edition": "",
            "is_disc": None,
            "type": "WEBDL",
            "language_checked": True,
            "audio_languages": ["English"],
        }
        with patch("src.trackers.IHD.languages_manager") as mock_lm:
            mock_lm.process_desc_language = AsyncMock()
            mock_lm.has_english_language = AsyncMock(return_value=True)
            result = _run(ihd.get_name(meta))
        assert result["name"] == "Back to the Future 1985 1080p MGMP WEB-DL DD+ 5.1 H.264-PiRaTeS"


# ═══════════════════════════════════════════════════════════════
#  get_additional_checks() — pre-upload validations
# ═══════════════════════════════════════════════════════════════


class TestIHDAdditionalChecks:
    """IHD additional checks: resolution, valid_mi_settings, source, language."""

    @pytest.fixture
    def ihd(self):
        return IHD(config=_config())

    def _base_meta(self) -> dict[str, Any]:
        return {
            "resolution": "1080p",
            "valid_mi_settings": True,
            "source": "BluRay",
            "type": "ENCODE",
            "service": "",
            "is_disc": None,
            "language_checked": True,
            "audio_languages": ["English"],
            "subtitle_languages": [],
            "unattended": False,
            "debug": False,
            "keywords": "",
            "combined_genres": "",
        }

    def test_valid_meta_passes(self, ihd):
        """A well-formed BluRay encode with English audio must pass all checks."""
        meta = self._base_meta()
        assert _run(ihd.get_additional_checks(meta)) is True

    def test_low_resolution_fails(self, ihd):
        """Releases below 1080 must be rejected."""
        meta = self._base_meta()
        meta["resolution"] = "720p"
        assert _run(ihd.get_additional_checks(meta)) is False

    def test_missing_mi_settings_fails(self, ihd):
        """Releases without encoding settings in mediainfo must be rejected."""
        meta = self._base_meta()
        meta["valid_mi_settings"] = False
        assert _run(ihd.get_additional_checks(meta)) is False

    def test_webdl_with_service_passes(self, ihd):
        """A WEB-DL with a recognised streaming service must pass the source check."""
        meta = self._base_meta()
        meta["source"] = "Web"
        meta["type"] = "WEBDL"
        meta["service"] = "NF"
        assert _run(ihd.get_additional_checks(meta)) is True

    def test_webdl_without_service_fails(self, ihd):
        """A WEB-DL without a streaming service (e.g. Father Ted S03) must be rejected."""
        meta = self._base_meta()
        meta["source"] = "Web"
        meta["type"] = "WEBDL"
        meta["service"] = ""
        assert _run(ihd.get_additional_checks(meta)) is False

    def test_webrip_without_service_fails(self, ihd):
        """A WEBRip without a streaming service must also be rejected."""
        meta = self._base_meta()
        meta["source"] = "Web"
        meta["type"] = "WEBRIP"
        meta["service"] = ""
        assert _run(ihd.get_additional_checks(meta)) is False

    def test_webdl_missing_service_prints_red_message(self, ihd, capsys):
        """When a WEB-DL has no service and not unattended, a red console message must be printed."""
        meta = self._base_meta()
        meta["source"] = "Web"
        meta["type"] = "WEBDL"
        meta["service"] = ""
        with patch("src.trackers.IHD.console") as mock_console:
            result = _run(ihd.get_additional_checks(meta))
        assert result is False
        mock_console.print.assert_any_call(
            f"[bold red]Service is missing, skipping {ihd.tracker} upload.[/bold red]"
        )

    def test_unattended_webdl_missing_service_no_print(self, ihd):
        """In unattended mode, the service-missing message must be suppressed but upload still skipped."""
        meta = self._base_meta()
        meta["source"] = "Web"
        meta["type"] = "WEBDL"
        meta["service"] = ""
        meta["unattended"] = True
        with patch("src.trackers.IHD.console") as mock_console:
            result = _run(ihd.get_additional_checks(meta))
        assert result is False
        for call in mock_console.print.call_args_list:
            assert "Service is missing" not in str(call)
