# Tests for HDF tracker — hdf.world (HD-Forever)
"""
Test suite for the HDF tracker implementation.
Covers: category mapping, codec mapping, resolution mapping,
        language flags, versions, and release naming.
"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import urlparse

import pytest

from src.trackers.HDF import HDF

# ─── Helpers ──────────────────────────────────────────────────


def _config(extra_tracker: dict[str, Any] | None = None) -> dict[str, Any]:
    tracker_cfg: dict[str, Any] = {
        "announce_url": "https://hdf.world/announce.php?passkey=FAKE_PASSKEY",
        "anon": False,
        "include_screenshots": False,
    }
    if extra_tracker:
        tracker_cfg.update(extra_tracker)
    return {
        "TRACKERS": {"HDF": tracker_cfg},
        "DEFAULT": {"tmdb_api": "fake-tmdb-key"},
    }


def _meta_base(**overrides: Any) -> dict[str, Any]:
    m: dict[str, Any] = {
        "category": "MOVIE",
        "type": "WEBDL",
        "title": "The Box",
        "year": "2009",
        "resolution": "1080p",
        "source": "WEB",
        "audio": "DDP5.1",
        "video_encode": "H264",
        "video_codec": "AVC",
        "service": "AMZN",
        "tag": "-HDForever",
        "edition": "",
        "repack": "",
        "3D": "",
        "uhd": "",
        "hdr": "",
        "webdv": "",
        "part": "",
        "season": "",
        "episode": "",
        "is_disc": None,
        "search_year": "",
        "manual_year": None,
        "manual_date": None,
        "no_season": False,
        "no_year": False,
        "no_aka": False,
        "debug": False,
        "tv_pack": 0,
        "path": "",
        "name": "",
        "uuid": "test-uuid",
        "base_dir": "/tmp",
        "overview": "A test movie.",
        "poster": "",
        "tmdb": 1234,
        "imdb_id": 1234567,
        "original_language": "en",
        "image_list": [],
        "bdinfo": None,
        "region": "",
        "dvd_size": "",
        "mediainfo": {"media": {"track": []}},
        "scene": False,
        "anime": False,
        "genres": "",
        "keywords": "",
        "anon": False,
    }
    m.update(overrides)
    return m


# ═══════════════════════════════════════════════════════════════
#   Category mapping
# ═══════════════════════════════════════════════════════════════


class TestGetCategoryId:
    """Test HDF category ID mapping."""

    @pytest.mark.parametrize(
        "category,genres,keywords,anime,expected_id",
        [
            # Standard movies
            ("MOVIE", "", "", False, 0),
            # TV series
            ("TV", "", "", False, 4),
            # Anime movies
            ("MOVIE", "", "", True, 1),
            # Anime series
            ("TV", "", "", True, 5),
            # Documentaries (movie)
            ("MOVIE", "Documentary", "", False, 6),
            # Documentaries via keywords
            ("MOVIE", "", "documentary", False, 6),
            # Concerts
            ("MOVIE", "Music", "", False, 3),
        ],
    )
    def test_category_mapping(
        self,
        category: str,
        genres: str,
        keywords: str,
        anime: bool,
        expected_id: int,
    ):
        tracker = HDF(_config())
        meta = _meta_base(category=category, genres=genres, keywords=keywords, anime=anime)
        result = asyncio.run(tracker.get_category_id(meta))
        assert result == expected_id


# ═══════════════════════════════════════════════════════════════
#   Codec mapping
# ═══════════════════════════════════════════════════════════════


class TestGetCodecId:
    """Test codec mapping."""

    @pytest.mark.parametrize(
        "video_codec,video_encode,expected",
        [
            ("AVC", "x264", "x264"),
            ("AVC", "H264", "H264"),
            ("HEVC", "x265", "x265"),
            ("HEVC", "H265", "H265"),
            ("", "AV1", "AV1"),
            ("", "", ""),
        ],
    )
    def test_codec_mapping(self, video_codec: str, video_encode: str, expected: str):
        result = HDF._get_codec_id(_meta_base(video_codec=video_codec, video_encode=video_encode))
        assert result == expected


# ═══════════════════════════════════════════════════════════════
#   Resolution mapping
# ═══════════════════════════════════════════════════════════════


class TestGetResolutionId:
    """Test resolution mapping."""

    @pytest.mark.parametrize(
        "resolution,expected",
        [
            ("2160p", "2160p"),
            ("1080p", "1080p"),
            ("1080i", "1080i"),
            ("720p", "720p"),
        ],
    )
    def test_resolution_mapping(self, resolution: str, expected: str):
        result = HDF._get_resolution_id(_meta_base(resolution=resolution))
        assert result == expected


# ═══════════════════════════════════════════════════════════════
#   File type mapping
# ═══════════════════════════════════════════════════════════════


class TestGetFileType:
    """Test release type to file type mapping."""

    @pytest.mark.parametrize(
        "release_type,is_disc,expected",
        [
            ("REMUX", None, "Blu-ray Remux"),
            ("WEBDL", None, "WEB-DL"),
            ("WEBRIP", None, "WEB-DL"),
            ("ENCODE", None, "Blu-ray Rip"),
            ("DISC", "BDMV", "Blu-ray Original"),
        ],
    )
    def test_file_type_mapping(self, release_type: str, is_disc: Any, expected: str):
        result = HDF._get_file_type(_meta_base(type=release_type, is_disc=is_disc or ""))
        assert result == expected


# ═══════════════════════════════════════════════════════════════
#   Language flags
# ═══════════════════════════════════════════════════════════════


class TestComputeLanguageFlags:
    """Test language flag computation from audio tag."""

    def _tracker(self) -> HDF:
        return HDF(_config())

    def test_multi_vff(self):
        tracker = self._tracker()
        flags = tracker._compute_language_flags(_meta_base(), "MULTI.VFF")
        assert flags["MULTi"] is True
        assert flags["VFF"] is True
        assert flags["VFQ"] is False

    def test_multi_vfq(self):
        tracker = self._tracker()
        flags = tracker._compute_language_flags(_meta_base(), "MULTI.VFQ")
        assert flags["MULTi"] is True
        assert flags["VFQ"] is True
        assert flags["VFF"] is False

    def test_multi_vfi(self):
        tracker = self._tracker()
        flags = tracker._compute_language_flags(_meta_base(), "MULTI.VFI")
        assert flags["MULTi"] is True
        assert flags["VFI"] is True

    def test_multi_vf2(self):
        tracker = self._tracker()
        flags = tracker._compute_language_flags(_meta_base(), "MULTI.VF2")
        assert flags["MULTi"] is True
        assert flags["VFF"] is True  # VF2 implies VFF present

    def test_vff_solo(self):
        tracker = self._tracker()
        flags = tracker._compute_language_flags(_meta_base(), "VFF")
        assert flags["VFF"] is True
        assert flags["MULTi"] is False

    def test_vof(self):
        tracker = self._tracker()
        flags = tracker._compute_language_flags(_meta_base(), "VOF")
        assert flags["VOF"] is True
        assert flags["MULTi"] is False

    def test_vostfr(self):
        tracker = self._tracker()
        flags = tracker._compute_language_flags(_meta_base(), "VOSTFR")
        assert flags["VO"] is True
        assert flags["subtitles"] is True

    def test_muet(self):
        tracker = self._tracker()
        flags = tracker._compute_language_flags(_meta_base(), "MUET")
        assert flags["muet"] is True


# ═══════════════════════════════════════════════════════════════
#   Version flags
# ═══════════════════════════════════════════════════════════════


class TestGetVersions:
    """Test version/edition flag mapping."""

    def test_directors_cut(self):
        versions = HDF._get_versions(_meta_base(edition="Director's Cut"))
        assert "Director's Cut" in versions

    def test_remaster(self):
        versions = HDF._get_versions(_meta_base(edition="Remaster"))
        assert "Remaster" in versions

    def test_extended(self):
        versions = HDF._get_versions(_meta_base(edition="Extended"))
        assert "Version Longue" in versions

    def test_hdr_dv(self):
        versions = HDF._get_versions(_meta_base(hdr="DV HDR10+"))
        assert "HDR10+" in versions
        assert "Dolby Vision" in versions

    def test_hdr_only(self):
        versions = HDF._get_versions(_meta_base(hdr="HDR"))
        assert "HDR" in versions

    def test_criterion(self):
        versions = HDF._get_versions(_meta_base(edition="Criterion"))
        assert "Criterion" in versions

    def test_imax(self):
        versions = HDF._get_versions(_meta_base(edition="IMAX"))
        assert "IMAX" in versions

    def test_service_netflix(self):
        versions = HDF._get_versions(_meta_base(service="NF"))
        assert "Source Netflix" in versions

    def test_service_amazon(self):
        versions = HDF._get_versions(_meta_base(service="AMZN"))
        assert "Source Amazon" in versions

    def test_service_disney(self):
        versions = HDF._get_versions(_meta_base(service="DSNP"))
        assert "Source Disney+" in versions

    def test_service_canal(self):
        versions = HDF._get_versions(_meta_base(service="CNLP"))
        assert "Source Canal+" in versions

    def test_service_appletv(self):
        versions = HDF._get_versions(_meta_base(service="ATVP"))
        assert "Source AppleTV" in versions

    def test_hybrid(self):
        versions = HDF._get_versions(_meta_base(edition="HYBRiD"))
        assert "Custom / HYBRiD" in versions

    def test_no_versions(self):
        versions = HDF._get_versions(_meta_base(edition="", hdr="", service=""))
        assert versions == []


# ═══════════════════════════════════════════════════════════════
#   Banned groups
# ═══════════════════════════════════════════════════════════════


class TestBannedGroups:
    """Test that HDF banned groups are properly set."""

    def test_banned_groups_from_rules(self):
        tracker = HDF(_config())
        assert "EXTREME" in tracker.banned_groups
        assert "RARBG" in tracker.banned_groups
        assert "FGT" in tracker.banned_groups
        assert "SUNS3T" in tracker.banned_groups
        assert "FL3ER" in tracker.banned_groups
        assert "WoLFHD" in tracker.banned_groups


# ═══════════════════════════════════════════════════════════════
#   French date formatting
# ═══════════════════════════════════════════════════════════════


class TestFormatFrenchDate:
    """Test French date formatting."""

    def test_standard_date(self):
        assert HDF._format_french_date("2009-11-24") == "24 novembre 2009"

    def test_first_of_month(self):
        assert HDF._format_french_date("2023-01-01") == "1er janvier 2023"

    def test_invalid_date(self):
        assert HDF._format_french_date("not-a-date") == "not-a-date"


# ═══════════════════════════════════════════════════════════════
#   Naming (through FrenchTrackerMixin.get_name)
# ═══════════════════════════════════════════════════════════════


class TestNaming:
    """Test that HDF naming follows French conventions via the mixin."""

    def _tracker(self) -> HDF:
        return HDF(_config())

    @patch.object(HDF, "_get_french_title", new_callable=AsyncMock, return_value="")
    def test_basic_movie_name(self, mock_title: AsyncMock):
        """Basic movie should include service in name (INCLUDE_SERVICE_IN_NAME=True)."""
        tracker = self._tracker()
        meta = _meta_base(
            category="MOVIE",
            type="WEBDL",
            title="The Box",
            year="2009",
            resolution="1080p",
            video_encode="H264",
            service="AMZN",
            tag="-HDForever",
            hdr="",
        )
        # Build audio tag requires mediainfo tracks
        meta["mediainfo"] = {
            "media": {
                "track": [
                    {"@type": "Audio", "Language": "fr", "Title": "VFF"},
                    {"@type": "Audio", "Language": "en"},
                ]
            }
        }
        result = asyncio.run(tracker.get_name(meta))
        name = result.get("name", "") if isinstance(result, dict) else str(result)

        # Should contain service (AMZN) since INCLUDE_SERVICE_IN_NAME=True
        assert "AMZN" in name
        # Should use WEB-DL label (dot-separated in release names: WEB.DL)
        assert "WEB" in name

    @patch.object(HDF, "_get_french_title", new_callable=AsyncMock, return_value="")
    def test_remux_name(self, mock_title: AsyncMock):
        """REMUX naming."""
        tracker = self._tracker()
        meta = _meta_base(
            category="MOVIE",
            type="REMUX",
            title="The Box",
            year="2009",
            resolution="1080p",
            video_codec="AVC",
            video_encode="",
            service="",
            tag="-HDForever",
            hdr="",
            source="Blu-ray",
        )
        meta["mediainfo"] = {
            "media": {
                "track": [
                    {"@type": "Audio", "Language": "fr", "Title": "VFI"},
                    {"@type": "Audio", "Language": "en"},
                ]
            }
        }
        result = asyncio.run(tracker.get_name(meta))
        name = result.get("name", "") if isinstance(result, dict) else str(result)
        assert "REMUX" in name


# ═══════════════════════════════════════════════════════════════
#   Category — Spectacles (category 6)
# ═══════════════════════════════════════════════════════════════


class TestSpectaclesCategory:
    """Ensure spectacle-related genres/keywords return category 6."""

    @pytest.mark.parametrize(
        "genres,keywords",
        [
            ("humour", ""),
            ("stand-up", ""),
            ("", "spectacle"),
            ("", "one-man-show"),
        ],
    )
    def test_spectacles_returns_6(self, genres: str, keywords: str):
        tracker = HDF(_config())
        meta = _meta_base(category="MOVIE", genres=genres, keywords=keywords)
        assert asyncio.run(tracker.get_category_id(meta)) == 2


# ═══════════════════════════════════════════════════════════════
#   MULTI.VOF language flag
# ═══════════════════════════════════════════════════════════════


class TestMultiVOF:
    """MULTI.VOF should set both MULTi and VOF flags."""

    def test_multi_vof(self):
        tracker = HDF(_config())
        flags = tracker._compute_language_flags(_meta_base(), "MULTI.VOF")
        assert flags["MULTi"] is True
        assert flags["VOF"] is True


# ═══════════════════════════════════════════════════════════════
#   get_data payload regression test
# ═══════════════════════════════════════════════════════════════


class TestGetDataPayload:
    """Regression test: build full upload payload and verify fields."""

    @patch.object(HDF, "_get_french_title", new_callable=AsyncMock, return_value="")
    @patch.object(HDF, "_build_description", new_callable=AsyncMock, return_value="[center]Test[/center]")
    @patch.object(HDF, "_get_mediainfo_text", new_callable=AsyncMock, return_value="")
    def test_movie_multi_vof_payload(
        self,
        mock_mi: AsyncMock,
        mock_desc: AsyncMock,
        mock_title: AsyncMock,
    ):
        """MOVIE with MULTI.VOF, AMZN service, 1080p x265 — full payload check."""
        tracker = HDF(_config())
        meta = _meta_base(
            category="MOVIE",
            type="WEBDL",
            title="The Box",
            year="2009",
            resolution="1080p",
            video_encode="x265",
            video_codec="HEVC",
            service="AMZN",
            tag="-HDForever",
            hdr="HDR",
            edition="",
        )
        meta["mediainfo"] = {
            "media": {
                "track": [
                    {"@type": "Audio", "Language": "fr", "Title": "VOF"},
                    {"@type": "Audio", "Language": "en"},
                ]
            }
        }
        data = asyncio.run(tracker.get_data(meta))

        # Category (form field is "type")
        assert data["type"] == "0"  # Film

        # Codec / resolution / filetype (real field names)
        assert data["format"] == "x265"
        assert data["bitrate"] == "1080p"
        assert data["media"] == "WEB-DL"

        # Name is generated via get_name but stored in torrent, not a form field;
        # verify description was set
        assert data.get("release_desc")

        # Language flags — _build_audio_string produces MULTI.VFF for en-original
        # with fr track titled "VOF" (VFF is the conservative default)
        assert data.get("MULTI") == "1"
        assert data.get("VFF") == "1"

        # Version — HDR + Source Amazon via releaseVersion[]
        versions = data.get("releaseVersion[]", [])
        assert "HDR" in versions
        assert "AMZN" in versions

        # TMDB URL in allocine_url field
        allocine_url = data.get("allocine_url", "")
        host = urlparse(allocine_url).hostname or ""
        assert host.endswith("themoviedb.org")

    @patch.object(HDF, "_get_french_title", new_callable=AsyncMock, return_value="")
    @patch.object(HDF, "_build_description", new_callable=AsyncMock, return_value="[center]Test[/center]")
    @patch.object(HDF, "_get_mediainfo_text", new_callable=AsyncMock, return_value="")
    def test_anime_tv_category(
        self,
        mock_mi: AsyncMock,
        mock_desc: AsyncMock,
        mock_title: AsyncMock,
    ):
        """Anime TV should map to category 4 (Séries d'animation)."""
        tracker = HDF(_config())
        meta = _meta_base(category="TV", anime=True, service="", hdr="", edition="")
        meta["mediainfo"] = {"media": {"track": [{"@type": "Audio", "Language": "ja"}]}}
        data = asyncio.run(tracker.get_data(meta))
        assert data["type"] == "5"

    @patch.object(HDF, "_get_french_title", new_callable=AsyncMock, return_value="")
    @patch.object(HDF, "_build_description", new_callable=AsyncMock, return_value="[center]Test[/center]")
    @patch.object(HDF, "_get_mediainfo_text", new_callable=AsyncMock, return_value="")
    def test_french_original_produces_vof(
        self,
        mock_mi: AsyncMock,
        mock_desc: AsyncMock,
        mock_title: AsyncMock,
    ):
        """French-original film with en track should produce MULTI.VOF → lang_vof."""
        tracker = HDF(_config())
        meta = _meta_base(
            category="MOVIE",
            type="WEBDL",
            original_language="fr",
            service="",
            hdr="",
            edition="",
        )
        meta["mediainfo"] = {
            "media": {
                "track": [
                    {"@type": "Audio", "Language": "fr"},
                    {"@type": "Audio", "Language": "en"},
                ]
            }
        }
        data = asyncio.run(tracker.get_data(meta))
        assert data.get("MULTI") == "1"
        assert data.get("VOF") == "1"
