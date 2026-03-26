# Tests for HDF tracker — hdf.world (HD-Forever)
"""
Test suite for the HDF tracker implementation.
Covers: category mapping, codec mapping, resolution mapping,
        language flags, versions, and release naming.
"""

import asyncio
import re
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
            # Concerts via keyword
            ("MOVIE", "", "concert", False, 3),
            # Music genre alone → Film (not Concert)
            ("MOVIE", "Music", "", False, 0),
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

    def test_remastered_stripped_by_edition_py(self):
        """edition.py strips 'Remastered' from edition; uuid fallback catches it."""
        versions = HDF._get_versions(_meta_base(edition="", uuid="Movie.1999.REMASTERED.1080p.BluRay.x264-GRP"))
        assert "Remaster" in versions

    def test_extended(self):
        versions = HDF._get_versions(_meta_base(edition="Extended"))
        assert "Version Longue" in versions

    def test_version_longue_stripped_by_edition_py(self):
        """edition.py strips 'version' from edition; uuid fallback catches it."""
        versions = HDF._get_versions(_meta_base(edition="", uuid="Movie.2001.VERSION.LONGUE.1080p.BluRay.x264-GRP"))
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
        # webdv flag (normal path — edition is stripped by edition.py)
        versions = HDF._get_versions(_meta_base(webdv="Hybrid"))
        assert "Custom / HYBRiD" in versions

    def test_custom(self):
        versions = HDF._get_versions(_meta_base(webdv="Custom"))
        assert "Custom / HYBRiD" in versions

    def test_hybrid_fallback_edition(self):
        # Fallback: if "hybrid" still appears in edition somehow
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
#   Category — Spectacles (category 2)
# ═══════════════════════════════════════════════════════════════


class TestSpectaclesCategory:
    """Ensure spectacle-related genres/keywords return category 2 (Spectacle)."""

    @pytest.mark.parametrize(
        "genres,keywords",
        [
            ("humour", ""),
            ("stand-up", ""),
            ("", "spectacle"),
            ("", "one-man-show"),
        ],
    )
    def test_spectacles_returns_2(self, genres: str, keywords: str):
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

        # release_desc = MediaInfo (empty in test), album_desc = BBCode description
        assert data.get("album_desc")

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
        assert host == "themoviedb.org" or host.endswith(".themoviedb.org")

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
    def test_tv_season_in_tmdb_url(
        self,
        mock_mi: AsyncMock,
        mock_desc: AsyncMock,
        mock_title: AsyncMock,
    ):
        """TV content should include /season/N in the TMDB URL."""
        tracker = HDF(_config())
        meta = _meta_base(category="TV", service="", hdr="", edition="")
        meta["season_int"] = 3
        meta["mediainfo"] = {"media": {"track": [{"@type": "Audio", "Language": "fr"}]}}
        data = asyncio.run(tracker.get_data(meta))
        assert data["allocine_url"].endswith("/season/3")

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


# ═══════════════════════════════════════════════════════════════
#   Additional codec mappings
# ═══════════════════════════════════════════════════════════════


class TestGetCodecIdExtended:
    """Extra codec mapping cases."""

    @pytest.mark.parametrize(
        "video_codec,video_encode,expected",
        [
            ("VC-1", "", "VC-1"),
            ("VC1", "", "VC-1"),
            ("MPEG-2", "", "MPEG-2"),
            ("MPEG2", "", "MPEG-2"),
            ("HEVC", "", "HEVC"),
            ("AVC", "", "AVC"),
        ],
    )
    def test_codec(self, video_codec: str, video_encode: str, expected: str):
        result = HDF._get_codec_id(_meta_base(video_codec=video_codec, video_encode=video_encode))
        assert result == expected


# ═══════════════════════════════════════════════════════════════
#   3D resolution mapping
# ═══════════════════════════════════════════════════════════════


class TestResolution3D:
    """3D resolution should prefix '3D '."""

    def test_3d_1080p(self):
        result = HDF._get_resolution_id(_meta_base(resolution="1080p", **{"3D": "3D"}))
        assert result == "3D 1080p"

    def test_3d_720p(self):
        result = HDF._get_resolution_id(_meta_base(resolution="720p", **{"3D": "3D"}))
        assert result == "3D 720p"


# ═══════════════════════════════════════════════════════════════
#   Language flags — extended
# ═══════════════════════════════════════════════════════════════


class TestLanguageFlagsExtended:
    """Extra language flag cases."""

    def _tracker(self) -> HDF:
        return HDF(_config())

    def test_truefrench(self):
        flags = self._tracker()._compute_language_flags(_meta_base(), "TRUEFRENCH")
        assert flags["VFF"] is True

    def test_vo_only(self):
        flags = self._tracker()._compute_language_flags(_meta_base(), "VO")
        assert flags["VO"] is True
        assert flags["MULTi"] is False

    def test_empty_tag(self):
        flags = self._tracker()._compute_language_flags(_meta_base(), "")
        assert not any(flags.values())

    def test_multi_vof_sets_both(self):
        flags = self._tracker()._compute_language_flags(_meta_base(), "MULTI.VOF")
        assert flags["MULTi"] is True
        assert flags["VOF"] is True
        assert flags["VFF"] is False

    def test_subtitles_from_mediainfo(self):
        """French subtitles in mediainfo should set subtitles flag."""
        meta = _meta_base(
            mediainfo={
                "media": {
                    "track": [
                        {"@type": "Text", "Language": "fr"},
                    ]
                }
            }
        )
        flags = self._tracker()._compute_language_flags(meta, "VO")
        assert flags["VO"] is True
        assert flags["subtitles"] is True

    def test_vf_generic(self):
        flags = self._tracker()._compute_language_flags(_meta_base(), "VF")
        assert flags["VF"] is True
        assert flags["VFF"] is False

    def test_voq(self):
        flags = self._tracker()._compute_language_flags(_meta_base(), "VOQ")
        assert flags["VOQ"] is True
        assert flags["VO"] is False

    def test_multi_without_specific_variant_sets_vf(self):
        flags = self._tracker()._compute_language_flags(_meta_base(), "MULTI")
        assert flags["MULTi"] is True
        assert flags["VF"] is True

    def test_multi_voq(self):
        flags = self._tracker()._compute_language_flags(_meta_base(), "MULTI.VOQ")
        assert flags["MULTi"] is True
        assert flags["VOQ"] is True
        assert flags["VF"] is False


# ═══════════════════════════════════════════════════════════════
#   Versions — extended
# ═══════════════════════════════════════════════════════════════


class TestGetVersionsExtended:
    """Additional edition/version flag tests."""

    def test_uncut(self):
        assert "UnCut" in HDF._get_versions(_meta_base(edition="Uncut"))

    def test_unrated(self):
        assert "UnRated" in HDF._get_versions(_meta_base(edition="Unrated"))

    def test_2in1(self):
        assert "2in1" in HDF._get_versions(_meta_base(edition="2in1"))

    def test_multiple_versions(self):
        """Edition with multiple flags should return all of them."""
        versions = HDF._get_versions(_meta_base(edition="Director's Cut Remaster", hdr="DV HDR10+", service="NF"))
        assert "Director's Cut" in versions
        assert "Remaster" in versions
        assert "HDR10+" in versions
        assert "Dolby Vision" in versions
        assert "Source Netflix" in versions


# ═══════════════════════════════════════════════════════════════
#   get_data payload — extended
# ═══════════════════════════════════════════════════════════════


class TestGetDataPayloadExtended:
    """Extended payload regression tests."""

    @patch.object(HDF, "_get_french_title", new_callable=AsyncMock, return_value="")
    @patch.object(HDF, "_build_description", new_callable=AsyncMock, return_value="[center]Test[/center]")
    @patch.object(HDF, "_get_mediainfo_text", new_callable=AsyncMock, return_value="")
    def test_scene_flag(self, mock_mi: AsyncMock, mock_desc: AsyncMock, mock_title: AsyncMock):
        """Scene release should set scene=1 in payload."""
        tracker = HDF(_config())
        meta = _meta_base(scene=True, service="", hdr="", edition="")
        meta["mediainfo"] = {"media": {"track": [{"@type": "Audio", "Language": "en"}]}}
        data = asyncio.run(tracker.get_data(meta))
        assert data.get("scene") == "1"

    @patch.object(HDF, "_get_french_title", new_callable=AsyncMock, return_value="")
    @patch.object(HDF, "_build_description", new_callable=AsyncMock, return_value="[center]Test[/center]")
    @patch.object(HDF, "_get_mediainfo_text", new_callable=AsyncMock, return_value="")
    def test_anonymous_flag(self, mock_mi: AsyncMock, mock_desc: AsyncMock, mock_title: AsyncMock):
        """Anonymous upload should set anonymous=1."""
        tracker = HDF(_config())
        meta = _meta_base(anon=True, service="", hdr="", edition="")
        meta["mediainfo"] = {"media": {"track": [{"@type": "Audio", "Language": "en"}]}}
        data = asyncio.run(tracker.get_data(meta))
        assert data.get("anonymous") == "1"

    @patch.object(HDF, "_get_french_title", new_callable=AsyncMock, return_value="")
    @patch.object(HDF, "_build_description", new_callable=AsyncMock, return_value="[center]Test[/center]")
    @patch.object(HDF, "_get_mediainfo_text", new_callable=AsyncMock, return_value="")
    def test_vostfr_sets_srt_and_vo(self, mock_mi: AsyncMock, mock_desc: AsyncMock, mock_title: AsyncMock):
        """VOSTFR release should set VO=1 and SRT=1 in payload."""
        tracker = HDF(_config())
        meta = _meta_base(original_language="en", service="", hdr="", edition="")
        # No French audio → VOSTFR expected when French subs present
        meta["mediainfo"] = {
            "media": {
                "track": [
                    {"@type": "Audio", "Language": "en"},
                    {"@type": "Text", "Language": "fr"},
                ]
            }
        }
        data = asyncio.run(tracker.get_data(meta))
        assert data.get("VO") == "1"
        assert data.get("SRT") == "1"

    @patch.object(HDF, "_get_french_title", new_callable=AsyncMock, return_value="")
    @patch.object(HDF, "_build_description", new_callable=AsyncMock, return_value="[center]Test[/center]")
    @patch.object(HDF, "_get_mediainfo_text", new_callable=AsyncMock, return_value="")
    def test_version_form_values(self, mock_mi: AsyncMock, mock_desc: AsyncMock, mock_title: AsyncMock):
        """Versions should map to correct form values in releaseVersion[]."""
        tracker = HDF(_config())
        meta = _meta_base(edition="Director's Cut", hdr="HDR", service="NF")
        meta["mediainfo"] = {"media": {"track": [{"@type": "Audio", "Language": "en"}]}}
        data = asyncio.run(tracker.get_data(meta))
        versions = data.get("releaseVersion[]", [])
        assert "DC" in versions
        assert "HDR" in versions
        assert "NF" in versions


# ═══════════════════════════════════════════════════════════════
#   Category — TV documentary
# ═══════════════════════════════════════════════════════════════


class TestCategoryDocumentaryTV:
    """TV documentary should still map to 6 (Documentaire)."""

    def test_tv_documentary(self):
        tracker = HDF(_config())
        meta = _meta_base(category="TV", genres="Documentary")
        assert asyncio.run(tracker.get_category_id(meta)) == 6


# ═══════════════════════════════════════════════════════════════
#   IMDb ID — various formats
# ═══════════════════════════════════════════════════════════════


class TestImdbIdFormats:
    """_build_description should handle various imdb_id formats."""

    def _tracker(self):
        return HDF(_config())

    @pytest.mark.parametrize(
        "imdb_id,expected_in_output",
        [
            (1234567, "tt1234567"),
            ("1234567", "tt1234567"),
            ("tt1234567", "tt1234567"),
            (0, None),
            ("", None),
        ],
    )
    def test_imdb_link(self, imdb_id, expected_in_output):
        tracker = self._tracker()
        meta = _meta_base()
        meta["imdb_id"] = imdb_id
        desc = asyncio.run(tracker._build_description(meta))
        if expected_in_output:
            assert expected_in_output in desc
        else:
            assert "imdb.com" not in desc


# ═══════════════════════════════════════════════════════════════
#   Artists fallback — always at least one actor
# ═══════════════════════════════════════════════════════════════


class TestArtistsFallback:
    """get_data should always include at least one actor."""

    @patch.object(HDF, "_get_french_title", new_callable=AsyncMock, return_value="")
    @patch.object(HDF, "_build_description", new_callable=AsyncMock, return_value="[center]Test[/center]")
    @patch.object(HDF, "_get_mediainfo_text", new_callable=AsyncMock, return_value="")
    def test_empty_credits_still_has_actor(self, mock_mi: AsyncMock, mock_desc: AsyncMock, mock_title: AsyncMock):
        tracker = HDF(_config())
        meta = _meta_base()
        meta["tmdb_directors"] = []
        meta["tmdb_cast"] = []
        meta["mediainfo"] = {"media": {"track": [{"@type": "Audio", "Language": "en"}]}}
        data = asyncio.run(tracker.get_data(meta))
        assert "artists[]" in data
        assert "1" in data["importance[]"]


# ─── Upload configuration ────────────────────────────────────────────


class TestUploadConfig:
    """Verify upload method passes correct parameters."""

    def test_id_pattern_matches_hex_hashes(self):
        """id_pattern must capture full hex hashes, not just leading digits."""
        import re

        pattern = r"torrentid=([a-fA-F0-9]+)"
        # Hash starting with a letter
        url = "https://hdf.world/torrents.php?id=123&torrentid=ceb30e7c7aa019be65b5d18bbaf332384975df92"
        match = re.search(pattern, url)
        assert match is not None
        assert match.group(1) == "ceb30e7c7aa019be65b5d18bbaf332384975df92"

        # Hash starting with digits (should capture full hash, not just digits)
        url2 = "https://hdf.world/torrents.php?id=456&torrentid=114c638c3d93e32ff404ff769d172b6a4bf5ee7a"
        match2 = re.search(pattern, url2)
        assert match2 is not None
        assert match2.group(1) == "114c638c3d93e32ff404ff769d172b6a4bf5ee7a"


# ═══════════════════════════════════════════════════════════════
#   Additional checks — French audio & bloat detection
# ═══════════════════════════════════════════════════════════════


def _run(coro):
    return asyncio.run(coro)


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from Rich console output."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


class TestAdditionalChecks:
    """get_additional_checks: always returns True (warning only, never blocks)."""

    @pytest.fixture()
    def hdf(self):
        return HDF(_config())

    def test_always_passes_even_without_french_audio(self, hdf):
        """HDF does NOT require French audio — check must not block."""
        meta = _meta_base(
            mediainfo={"media": {"track": [
                {"@type": "Audio", "Language": "en"},
            ]}},
        )
        assert _run(hdf.get_additional_checks(meta)) is True

    def test_passes_with_french_audio(self, hdf):
        """Normal case with French audio still passes."""
        meta = _meta_base(
            mediainfo={"media": {"track": [
                {"@type": "Audio", "Language": "fr"},
                {"@type": "Audio", "Language": "en"},
            ]}},
        )
        assert _run(hdf.get_additional_checks(meta)) is True

    def test_passes_with_empty_tracks(self, hdf):
        """No tracks at all → still passes (no blocking)."""
        meta = _meta_base(mediainfo={"media": {"track": []}})
        assert _run(hdf.get_additional_checks(meta)) is True

    def test_survives_warn_exception(self, hdf):
        """If _warn_superfluous_tracks raises, get_additional_checks still returns True."""
        meta = _meta_base(type="REMUX")
        with patch.object(hdf, "_warn_superfluous_tracks", side_effect=RuntimeError("boom")):
            assert _run(hdf.get_additional_checks(meta)) is True

    def test_survives_nfo_exception(self, hdf):
        """If _get_or_generate_nfo raises, meta is not mutated and returns True."""
        meta = _meta_base()
        with patch.object(hdf, "_get_or_generate_nfo", side_effect=RuntimeError("boom")):
            assert _run(hdf.get_additional_checks(meta)) is True
            assert "nfo" not in meta or not meta["nfo"]

    def test_nfo_generated_when_missing(self, hdf):
        """When meta has no NFO, _get_or_generate_nfo is called and meta is updated."""
        meta = _meta_base()
        with patch.object(hdf, "_get_or_generate_nfo", new_callable=AsyncMock, return_value="/tmp/test.nfo"):
            _run(hdf.get_additional_checks(meta))
        assert meta["nfo"] == "/tmp/test.nfo"
        assert meta["auto_nfo"] is True

    def test_nfo_not_regenerated_when_present(self, hdf):
        """When meta already has an NFO, _get_or_generate_nfo is not called."""
        meta = _meta_base(nfo="/existing/nfo.txt")
        with patch.object(hdf, "_get_or_generate_nfo") as mock_nfo:
            _run(hdf.get_additional_checks(meta))
            mock_nfo.assert_not_called()
        assert meta["nfo"] == "/existing/nfo.txt"

    def test_bloat_skipped_for_disc(self, hdf):
        """Bloat warning is not run for DISC releases."""
        meta = _meta_base(type="DISC")
        with patch.object(hdf, "_warn_superfluous_tracks") as mock_warn:
            _run(hdf.get_additional_checks(meta))
            mock_warn.assert_not_called()

    def test_bloat_runs_for_remux(self, hdf):
        """Bloat warning runs for REMUX releases."""
        meta = _meta_base(type="REMUX")
        with patch.object(hdf, "_warn_superfluous_tracks") as mock_warn:
            _run(hdf.get_additional_checks(meta))
            mock_warn.assert_called_once()


class TestBloatDetection:
    """_warn_superfluous_tracks: detect non-VF/VO audio and subtitle tracks."""

    @pytest.fixture()
    def hdf(self):
        return HDF(_config())

    def test_no_warning_vf_vo_only(self, hdf, capsys):
        """FR + EN (VO) on an English-original film → no warning."""
        meta = _meta_base(
            original_language="en",
            mediainfo={"media": {"track": [
                {"@type": "Audio", "Language": "fr"},
                {"@type": "Audio", "Language": "en"},
            ]}},
        )
        hdf._warn_superfluous_tracks(meta)
        assert capsys.readouterr().out == ""

    def test_warns_extra_audio_spanish_on_english_film(self, hdf, capsys):
        """Spanish audio on an English-original film → warning."""
        meta = _meta_base(
            original_language="en",
            mediainfo={"media": {"track": [
                {"@type": "Audio", "Language": "fr"},
                {"@type": "Audio", "Language": "en"},
                {"@type": "Audio", "Language": "es"},
            ]}},
        )
        hdf._warn_superfluous_tracks(meta)
        out = capsys.readouterr().out
        assert "Espagnol" in out or "SPA" in out

    def test_warns_multiple_extra_audio(self, hdf, capsys):
        """German + Italian on English-original → warning lists both."""
        meta = _meta_base(
            original_language="en",
            mediainfo={"media": {"track": [
                {"@type": "Audio", "Language": "fr"},
                {"@type": "Audio", "Language": "en"},
                {"@type": "Audio", "Language": "de"},
                {"@type": "Audio", "Language": "it"},
            ]}},
        )
        hdf._warn_superfluous_tracks(meta)
        out = _strip_ansi(capsys.readouterr().out)
        assert "2 langue(s) audio" in out

    def test_english_tolerated_on_non_english_original(self, hdf, capsys):
        """FR + EN + JA on a Japanese film → EN is tolerated, no extra audio."""
        meta = _meta_base(
            original_language="ja",
            mediainfo={"media": {"track": [
                {"@type": "Audio", "Language": "fr"},
                {"@type": "Audio", "Language": "en"},
                {"@type": "Audio", "Language": "ja"},
            ]}},
        )
        hdf._warn_superfluous_tracks(meta)
        assert capsys.readouterr().out == ""

    def test_warns_extra_on_non_english_original(self, hdf, capsys):
        """FR + EN + JA + DE on Japanese film → DE is extra."""
        meta = _meta_base(
            original_language="ja",
            mediainfo={"media": {"track": [
                {"@type": "Audio", "Language": "fr"},
                {"@type": "Audio", "Language": "en"},
                {"@type": "Audio", "Language": "ja"},
                {"@type": "Audio", "Language": "de"},
            ]}},
        )
        hdf._warn_superfluous_tracks(meta)
        out = capsys.readouterr().out
        assert "Allemand" in out or "DEU" in out

    def test_warns_extra_subtitles(self, hdf, capsys):
        """Extra subtitle languages trigger a separate warning."""
        meta = _meta_base(
            original_language="en",
            mediainfo={"media": {"track": [
                {"@type": "Audio", "Language": "fr"},
                {"@type": "Audio", "Language": "en"},
                {"@type": "Text", "Language": "fr"},
                {"@type": "Text", "Language": "en"},
                {"@type": "Text", "Language": "es"},
                {"@type": "Text", "Language": "de"},
            ]}},
        )
        hdf._warn_superfluous_tracks(meta)
        out = _strip_ansi(capsys.readouterr().out)
        assert "sous-titres" in out
        assert "2 langue(s)" in out

    def test_commentary_tracks_ignored(self, hdf, capsys):
        """Commentary audio tracks are ignored (not counted as bloat)."""
        meta = _meta_base(
            original_language="en",
            mediainfo={"media": {"track": [
                {"@type": "Audio", "Language": "fr"},
                {"@type": "Audio", "Language": "en"},
                {"@type": "Audio", "Language": "en", "Title": "Commentary"},
            ]}},
        )
        hdf._warn_superfluous_tracks(meta)
        assert capsys.readouterr().out == ""

    def test_no_original_language_only_french_allowed(self, hdf, capsys):
        """When original_language is empty, only French is allowed."""
        meta = _meta_base(
            original_language="",
            mediainfo={"media": {"track": [
                {"@type": "Audio", "Language": "fr"},
                {"@type": "Audio", "Language": "en"},
            ]}},
        )
        hdf._warn_superfluous_tracks(meta)
        out = capsys.readouterr().out
        assert "Anglais" in out or "ENG" in out

    def test_deduplicates_extra_languages(self, hdf, capsys):
        """Two Spanish audio tracks → only one 'Espagnol' in warning."""
        meta = _meta_base(
            original_language="en",
            mediainfo={"media": {"track": [
                {"@type": "Audio", "Language": "fr"},
                {"@type": "Audio", "Language": "en"},
                {"@type": "Audio", "Language": "es"},
                {"@type": "Audio", "Language": "es"},
            ]}},
        )
        hdf._warn_superfluous_tracks(meta)
        out = _strip_ansi(capsys.readouterr().out)
        assert "1 langue(s) audio" in out


class TestLangDisplayName:
    """_lang_display_name: French display names for language codes."""

    def test_known_raw_code(self):
        assert HDF._lang_display_name("spanish", "SPA") == "Espagnol"

    def test_reverse_lookup_by_mapped_code(self):
        assert HDF._lang_display_name("es", "SPA") == "Espagnol"

    def test_fallback_to_mapped_code(self):
        """Unknown language code returns the 3-letter mapped code."""
        assert HDF._lang_display_name("xx", "XXX") == "XXX"
