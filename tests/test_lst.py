# Tests for LST tracker — lst.gg
"""
Test suite for LST release naming.
Covers: TV year suppression based on TVDB series name.
  - Year is included in TV names only when TVDB has a year in the series name.
  - Movie names are never modified.
  - DVDRIP codec adjustments still apply.
  - TRUMP suffix still appended when trump_reason == "exact_match".
"""

import asyncio
from typing import Any

import pytest

from src.trackers.LST import LST


# ─── Helpers ──────────────────────────────────────────────────


def _config() -> dict[str, Any]:
    return {
        "TRACKERS": {
            "LST": {
                "api_key": "fake-key",
                "announce_url": "https://lst.gg/announce/FAKE",
            }
        },
        "DEFAULT": {"tmdb_api": "fake-tmdb-key"},
    }


def _run(coro):
    return asyncio.run(coro)


def _lst() -> LST:
    return LST(config=_config())


def _tv_meta(name: str, tvdb_series_name: Any = None, **overrides: Any) -> dict[str, Any]:
    m: dict[str, Any] = {
        "category": "TV",
        "type": "WEBDL",
        "name": name,
        "tvdb_series_name": tvdb_series_name,
        "trump_reason": None,
        "source": "WEB",
        "resolution": "1080p",
        "video_encode": "H.264",
        "video_codec": "H.264",
        "audio": "AAC 2.0",
        "debug": False,
    }
    m.update(overrides)
    return m


def _movie_meta(name: str, **overrides: Any) -> dict[str, Any]:
    m: dict[str, Any] = {
        "category": "MOVIE",
        "type": "WEBDL",
        "name": name,
        "tvdb_series_name": None,
        "trump_reason": None,
        "source": "WEB",
        "resolution": "1080p",
        "video_encode": "H.264",
        "video_codec": "H.264",
        "audio": "AAC 2.0",
        "debug": False,
    }
    m.update(overrides)
    return m


# ═══════════════════════════════════════════════════════════════
#  TV year suppression
# ═══════════════════════════════════════════════════════════════


class TestTVYearHandling:
    """Year in TV names follows the TVDB series name, not the filename."""

    def test_tvdb_no_year_strips_year_from_name(self):
        """TVDB name has no year → year must be removed."""
        meta = _tv_meta(
            name="Shameless 2011 S01E01 1080p WEB-DL AAC 2.0 H.264-GROUP",
            tvdb_series_name="Shameless",
        )
        result = _run(_lst().get_name(meta))["name"]
        assert "2011" not in result, f"Year should be stripped: {result}"
        assert "S01E01" in result

    def test_tvdb_with_year_in_parens_keeps_year(self):
        """TVDB name contains year → year must be kept."""
        meta = _tv_meta(
            name="Shameless 2011 S01E01 1080p WEB-DL AAC 2.0 H.264-GROUP",
            tvdb_series_name="Shameless (2011)",
        )
        result = _run(_lst().get_name(meta))["name"]
        assert "2011" in result, f"Year should be kept: {result}"

    def test_tvdb_with_bare_year_keeps_year(self):
        """TVDB name with a bare year (no parens) → year kept."""
        meta = _tv_meta(
            name="Doctor Who 2005 S01E01 1080p WEB-DL AAC 2.0 H.264-GROUP",
            tvdb_series_name="Doctor Who 2005",
        )
        result = _run(_lst().get_name(meta))["name"]
        assert "2005" in result, f"Year should be kept: {result}"

    def test_tvdb_series_name_none_strips_year(self):
        """tvdb_series_name is None (no TVDB data) → year must be stripped."""
        meta = _tv_meta(
            name="Fargo 2014 S01E01 1080p WEB-DL AAC 2.0 H.264-GROUP",
            tvdb_series_name=None,
        )
        result = _run(_lst().get_name(meta))["name"]
        assert "2014" not in result, f"Year should be stripped: {result}"

    def test_tvdb_empty_string_strips_year(self):
        """Empty tvdb_series_name → year stripped."""
        meta = _tv_meta(
            name="Fargo 2014 S01E01 1080p WEB-DL AAC 2.0 H.264-GROUP",
            tvdb_series_name="",
        )
        result = _run(_lst().get_name(meta))["name"]
        assert "2014" not in result, f"Year should be stripped: {result}"

    def test_no_year_in_name_unchanged(self):
        """Name already has no year → no change, no error."""
        meta = _tv_meta(
            name="Shameless S01E01 1080p WEB-DL AAC 2.0 H.264-GROUP",
            tvdb_series_name="Shameless",
        )
        result = _run(_lst().get_name(meta))["name"]
        assert result == "Shameless S01E01 1080p WEB-DL AAC 2.0 H.264-GROUP"

    def test_only_first_year_stripped(self):
        """Only the year immediately after the title is stripped, not embedded numbers."""
        meta = _tv_meta(
            name="24 2001 S01E01 1080p WEB-DL AAC 2.0 H.264-GROUP",
            tvdb_series_name="24",
        )
        result = _run(_lst().get_name(meta))["name"]
        assert "2001" not in result, f"Year should be stripped: {result}"
        # The title '24' should remain
        assert result.startswith("24 "), f"Title '24' should be intact: {result}"


# ═══════════════════════════════════════════════════════════════
#  Movie names — year never touched
# ═══════════════════════════════════════════════════════════════


class TestMovieYearUnchanged:
    """Movies are always uploaded with their year regardless of TVDB."""

    def test_movie_year_never_stripped(self):
        meta = _movie_meta(name="Inception 2010 2160p BluRay REMUX DTS:X 7.1 HEVC-GROUP")
        result = _run(_lst().get_name(meta))["name"]
        assert "2010" in result, f"Movie year must not be stripped: {result}"

    def test_movie_no_tvdb_year_still_kept(self):
        meta = _movie_meta(
            name="The Dark Knight 2008 2160p BluRay REMUX TrueHD Atmos HEVC-GROUP",
            tvdb_series_name=None,
        )
        result = _run(_lst().get_name(meta))["name"]
        assert "2008" in result, f"Movie year must not be stripped: {result}"


# ═══════════════════════════════════════════════════════════════
#  TRUMP suffix
# ═══════════════════════════════════════════════════════════════


class TestTrumpSuffix:
    """trump_reason=exact_match appends ' - TRUMP' after year logic."""

    def test_trump_suffix_added_tv_no_tvdb_year(self):
        """Year stripped AND trump suffix added for TV with no TVDB year."""
        meta = _tv_meta(
            name="Shameless 2011 S01E01 1080p WEB-DL AAC 2.0 H.264-GROUP",
            tvdb_series_name="Shameless",
            trump_reason="exact_match",
        )
        result = _run(_lst().get_name(meta))["name"]
        assert result.endswith(" - TRUMP"), f"Trump suffix missing: {result}"
        assert "2011" not in result.replace(" - TRUMP", ""), f"Year not stripped: {result}"

    def test_trump_suffix_added_tv_with_tvdb_year(self):
        """Year kept AND trump suffix added for TV with TVDB year."""
        meta = _tv_meta(
            name="Shameless 2011 S01E01 1080p WEB-DL AAC 2.0 H.264-GROUP",
            tvdb_series_name="Shameless (2011)",
            trump_reason="exact_match",
        )
        result = _run(_lst().get_name(meta))["name"]
        assert result.endswith(" - TRUMP"), f"Trump suffix missing: {result}"
        assert "2011" in result, f"Year should be kept: {result}"

    def test_trump_suffix_added_movie(self):
        meta = _movie_meta(
            name="Inception 2010 2160p BluRay REMUX DTS:X 7.1 HEVC-GROUP",
            trump_reason="exact_match",
        )
        result = _run(_lst().get_name(meta))["name"]
        assert result.endswith(" - TRUMP"), f"Trump suffix missing: {result}"
        assert "2010" in result, f"Movie year must not be stripped: {result}"


# ═══════════════════════════════════════════════════════════════
#  get_additional_checks — micro-encode bitrate gate
# ═══════════════════════════════════════════════════════════════


def _bitrate_meta(
    video_bitrate: int,
    codec: str = "x265",
    resolution: str = "1080p",
    type: str = "WEBRIP",
    **overrides: Any,
) -> dict[str, Any]:
    """Minimal meta for get_additional_checks() bitrate tests.

    Language check is short-circuited via language_checked=True + English audio
    so tests stay fast and offline.
    """
    m: dict[str, Any] = {
        "is_disc": None,
        "valid_mi_settings": True,
        "type": type,
        "video_encode": codec,
        "resolution": resolution,
        "original_language": "en",
        "audio_languages": ["english"],
        "subtitle_languages": [],
        "language_checked": True,
        "tracker_status": {"LST": {}},
        "debug": False,
        "unattended": True,
        "mediainfo": {
            "media": {
                "track": [
                    {"@type": "Video", "BitRate": str(video_bitrate)},
                ]
            }
        },
    }
    m.update(overrides)
    return m


class TestAdditionalChecksMicroEncode:
    """Bitrate gate blocks micro-encodes for ENCODE / WEBRIP / WEBDL."""

    # ── x265 1080p (threshold: 1 000 000 bps) ──────────────────

    def test_x265_1080p_webrip_below_threshold_is_rejected(self):
        """JATT-style release at ~748 kb/s must be blocked."""
        meta = _bitrate_meta(video_bitrate=748_000, codec="x265", resolution="1080p", type="WEBRIP")
        assert _run(_lst().get_additional_checks(meta)) is False

    def test_x265_1080p_webdl_below_threshold_is_rejected(self):
        """Same codec/resolution, WEBDL type, must also be blocked."""
        meta = _bitrate_meta(video_bitrate=900_000, codec="x265", resolution="1080p", type="WEBDL")
        assert _run(_lst().get_additional_checks(meta)) is False

    def test_x265_1080p_encode_below_threshold_is_rejected(self):
        meta = _bitrate_meta(video_bitrate=500_000, codec="x265", resolution="1080p", type="ENCODE")
        assert _run(_lst().get_additional_checks(meta)) is False

    def test_x265_1080p_just_below_threshold_is_rejected(self):
        meta = _bitrate_meta(video_bitrate=999_999, codec="x265", resolution="1080p")
        assert _run(_lst().get_additional_checks(meta)) is False

    def test_x265_1080p_at_threshold_is_allowed(self):
        """Exactly at the minimum must pass (not strictly below)."""
        meta = _bitrate_meta(video_bitrate=1_000_000, codec="x265", resolution="1080p")
        assert _run(_lst().get_additional_checks(meta)) is True

    def test_x265_1080p_above_threshold_is_allowed(self):
        meta = _bitrate_meta(video_bitrate=2_000_000, codec="x265", resolution="1080p")
        assert _run(_lst().get_additional_checks(meta)) is True

    # ── x265 1080p — alternate codec labels ────────────────────

    def test_hevc_label_below_threshold_is_rejected(self):
        """'HEVC' codec label must map to x265 and be checked."""
        meta = _bitrate_meta(video_bitrate=500_000, codec="HEVC", resolution="1080p")
        assert _run(_lst().get_additional_checks(meta)) is False

    def test_h265_label_below_threshold_is_rejected(self):
        meta = _bitrate_meta(video_bitrate=500_000, codec="H.265", resolution="1080p")
        assert _run(_lst().get_additional_checks(meta)) is False

    # ── x265 720p (threshold: 600 000 bps) ─────────────────────

    def test_x265_720p_below_threshold_is_rejected(self):
        meta = _bitrate_meta(video_bitrate=400_000, codec="x265", resolution="720p")
        assert _run(_lst().get_additional_checks(meta)) is False

    def test_x265_720p_above_threshold_is_allowed(self):
        meta = _bitrate_meta(video_bitrate=800_000, codec="x265", resolution="720p")
        assert _run(_lst().get_additional_checks(meta)) is True

    # ── x265 2160p (threshold: 3 000 000 bps) ──────────────────

    def test_x265_2160p_below_threshold_is_rejected(self):
        meta = _bitrate_meta(video_bitrate=2_000_000, codec="x265", resolution="2160p")
        assert _run(_lst().get_additional_checks(meta)) is False

    def test_x265_2160p_above_threshold_is_allowed(self):
        meta = _bitrate_meta(video_bitrate=4_000_000, codec="x265", resolution="2160p")
        assert _run(_lst().get_additional_checks(meta)) is True

    # ── x264 1080p (threshold: 2 000 000 bps) ──────────────────

    def test_x264_1080p_below_threshold_is_rejected(self):
        meta = _bitrate_meta(video_bitrate=1_500_000, codec="x264", resolution="1080p")
        assert _run(_lst().get_additional_checks(meta)) is False

    def test_x264_1080p_above_threshold_is_allowed(self):
        meta = _bitrate_meta(video_bitrate=2_500_000, codec="x264", resolution="1080p")
        assert _run(_lst().get_additional_checks(meta)) is True

    def test_h264_label_below_threshold_is_rejected(self):
        """'H.264' codec label must map to x264 and be checked."""
        meta = _bitrate_meta(video_bitrate=1_000_000, codec="H.264", resolution="1080p")
        assert _run(_lst().get_additional_checks(meta)) is False

    def test_avc_label_below_threshold_is_rejected(self):
        meta = _bitrate_meta(video_bitrate=1_000_000, codec="AVC", resolution="1080p")
        assert _run(_lst().get_additional_checks(meta)) is False

    # ── edge cases ──────────────────────────────────────────────

    def test_no_bitrate_in_mediainfo_is_rejected(self):
        """Missing BitRate value must block the upload (fail-closed)."""
        meta = _bitrate_meta(video_bitrate=0, codec="x265", resolution="1080p")
        meta["mediainfo"] = {"media": {"track": [{"@type": "Video"}]}}
        assert _run(_lst().get_additional_checks(meta)) is False

    def test_unknown_codec_is_rejected(self):
        """Unrecognised codec (e.g. VP9) must block the upload (fail-closed)."""
        meta = _bitrate_meta(video_bitrate=5_000_000, codec="vp9", resolution="1080p")
        assert _run(_lst().get_additional_checks(meta)) is False

    def test_unmapped_resolution_is_rejected(self):
        """Resolution with no rule (e.g. 480p) must block the upload (fail-closed)."""
        meta = _bitrate_meta(video_bitrate=5_000_000, codec="x265", resolution="480p")
        assert _run(_lst().get_additional_checks(meta)) is False

    def test_remux_type_skips_bitrate_check(self):
        """REMUX type is not subject to the bitrate gate."""
        meta = _bitrate_meta(video_bitrate=100_000, codec="x265", resolution="1080p", type="REMUX")
        assert _run(_lst().get_additional_checks(meta)) is True

    def test_disc_type_skips_bitrate_check(self):
        """DISC type is not subject to the bitrate gate."""
        meta = _bitrate_meta(video_bitrate=100_000, codec="x265", resolution="1080p", type="DISC")
        assert _run(_lst().get_additional_checks(meta)) is True

    def test_invalid_mi_settings_is_rejected(self):
        """valid_mi_settings=False must return False before any bitrate check."""
        meta = _bitrate_meta(video_bitrate=5_000_000, codec="x265", resolution="1080p")
        meta["valid_mi_settings"] = False
        assert _run(_lst().get_additional_checks(meta)) is False

    def test_bdmv_disc_skips_bitrate_check(self):
        """Full BDMV disc upload bypasses the bitrate gate entirely."""
        meta = _bitrate_meta(video_bitrate=100_000, codec="x265", resolution="1080p", type="DISC")
        meta["is_disc"] = "BDMV"
        assert _run(_lst().get_additional_checks(meta)) is True
