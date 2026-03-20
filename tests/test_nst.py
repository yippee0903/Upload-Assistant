# Tests for NST tracker — nostradamus.foo (Nostradamus)
"""
Test suite for the NST tracker implementation.
Covers: category mapping, type mapping, resolution mapping,
        URL configuration, and French tracker mixin integration.
"""

import asyncio
from typing import Any

import pytest

from src.trackers.NST import NST

# ─── Helpers ──────────────────────────────────────────────────


def _config(extra_tracker: dict[str, Any] | None = None) -> dict[str, Any]:
    tracker_cfg: dict[str, Any] = {
        "api_key": "fake-token",
        "announce_url": "",
        "anon": False,
    }
    if extra_tracker:
        tracker_cfg.update(extra_tracker)
    return {
        "TRACKERS": {"NST": tracker_cfg},
        "DEFAULT": {"tmdb_api": "fake-tmdb-key"},
    }


def _meta_base(**overrides: Any) -> dict[str, Any]:
    m: dict[str, Any] = {
        "category": "MOVIE",
        "type": "WEBDL",
        "title": "War Machine",
        "year": "2026",
        "resolution": "1080p",
        "source": "WEB",
        "audio": "DDP5.1",
        "video_encode": "x264",
        "video_codec": "AVC",
        "service": "NF",
        "tag": "-FW",
        "edition": "",
        "repack": "",
        "3D": "",
        "uhd": "",
        "hdr": "",
        "season": "",
        "episode": "",
        "part": "",
        "genres": "",
        "keywords": "",
        "anime": False,
        "imdb_id": 1234567,
        "tmdb": 42,
        "debug": False,
        "mediainfo": {},
    }
    m.update(overrides)
    return m


# ═══════════════════════════════════════════════════════════════
#   URL Configuration
# ═══════════════════════════════════════════════════════════════


class TestURLs:
    def test_base_url(self):
        tracker = NST(_config())
        assert tracker.base_url == "https://nostradamus.foo"

    def test_upload_url(self):
        tracker = NST(_config())
        assert tracker.upload_url == "https://nostradamus.foo/api/upload-assistant/torrents/upload"

    def test_search_url(self):
        tracker = NST(_config())
        assert tracker.search_url == "https://nostradamus.foo/api/upload-assistant/torrents/filter"

    def test_torrent_url(self):
        tracker = NST(_config())
        assert tracker.torrent_url == "https://nostradamus.foo/torrents/"


# ═══════════════════════════════════════════════════════════════
#   Category mapping
# ═══════════════════════════════════════════════════════════════


class TestGetCategoryId:
    @pytest.mark.parametrize(
        "category,genres,keywords,anime,expected_id",
        [
            # Standard movie
            ("MOVIE", "", "", False, "2020"),
            # Standard TV
            ("TV", "", "", False, "5040"),
            # Documentary movie
            ("MOVIE", "Documentary", "", False, "2030"),
            # Documentary TV
            ("TV", "Documentary", "", False, "2030"),
            # Anime movie
            ("MOVIE", "", "", True, "2010"),
            # Anime TV
            ("TV", "", "", True, "5070"),
            # Concert
            ("MOVIE", "", "concert", False, "2060"),
            # Live
            ("MOVIE", "", "live", False, "2060"),
            # Sport TV
            ("TV", "", "sport", False, "5060"),
        ],
    )
    def test_category_mapping(
        self,
        category: str,
        genres: str,
        keywords: str,
        anime: bool,
        expected_id: str,
    ):
        tracker = NST(_config())
        meta = _meta_base(category=category, genres=genres, keywords=keywords, anime=anime)
        result = asyncio.run(tracker.get_category_id(meta))
        assert result == {"category_id": expected_id}

    def test_mapping_only(self):
        tracker = NST(_config())
        result = asyncio.run(tracker.get_category_id(_meta_base(), mapping_only=True))
        assert result == {"MOVIE": "2020", "TV": "5040"}

    def test_reverse(self):
        tracker = NST(_config())
        result = asyncio.run(tracker.get_category_id(_meta_base(), reverse=True))
        assert result == {"2020": "MOVIE", "5040": "TV"}


# ═══════════════════════════════════════════════════════════════
#   Type mapping
# ═══════════════════════════════════════════════════════════════


class TestGetTypeId:
    @pytest.mark.parametrize(
        "type_str,expected_id",
        [
            ("DISC", "1"),
            ("REMUX", "2"),
            ("ENCODE", "3"),
            ("WEBDL", "4"),
            ("WEBRIP", "5"),
            ("HDTV", "6"),
        ],
    )
    def test_type_mapping(self, type_str: str, expected_id: str):
        tracker = NST(_config())
        meta = _meta_base(type=type_str)
        result = asyncio.run(tracker.get_type_id(meta))
        assert result == {"type_id": expected_id}

    def test_unknown_type(self):
        tracker = NST(_config())
        meta = _meta_base(type="UNKNOWN")
        result = asyncio.run(tracker.get_type_id(meta))
        assert result == {"type_id": "0"}


# ═══════════════════════════════════════════════════════════════
#   Resolution mapping
# ═══════════════════════════════════════════════════════════════


class TestGetResolutionId:
    @pytest.mark.parametrize(
        "resolution,expected_id",
        [
            ("4320p", "1"),
            ("2160p", "2"),
            ("1080p", "3"),
            ("1080i", "4"),
            ("720p", "5"),
            ("576p", "6"),
            ("480p", "8"),
        ],
    )
    def test_resolution_mapping(self, resolution: str, expected_id: str):
        tracker = NST(_config())
        meta = _meta_base(resolution=resolution)
        result = asyncio.run(tracker.get_resolution_id(meta))
        assert result == {"resolution_id": expected_id}

    def test_unknown_resolution(self):
        tracker = NST(_config())
        meta = _meta_base(resolution="OTHER")
        result = asyncio.run(tracker.get_resolution_id(meta))
        assert result == {"resolution_id": "10"}


# ═══════════════════════════════════════════════════════════════
#   Tracker identity
# ═══════════════════════════════════════════════════════════════


class TestTrackerIdentity:
    def test_tracker_name(self):
        tracker = NST(_config())
        assert tracker.tracker == "NST"

    def test_source_flag(self):
        tracker = NST(_config())
        assert tracker.source_flag == "NST"

    def test_web_label(self):
        assert NST.WEB_LABEL == "WEB-DL"

    def test_prefer_original_title(self):
        assert NST.PREFER_ORIGINAL_TITLE is True

    def test_include_service_in_name(self):
        assert NST.INCLUDE_SERVICE_IN_NAME is True


# ═══════════════════════════════════════════════════════════════
#   Documentary via keywords
# ═══════════════════════════════════════════════════════════════


class TestDocumentaryKeywords:
    def test_documentary_keyword_movie(self):
        tracker = NST(_config())
        meta = _meta_base(category="MOVIE", keywords="documentary")
        result = asyncio.run(tracker.get_category_id(meta))
        assert result == {"category_id": "2030"}

    def test_sport_keyword_tv(self):
        tracker = NST(_config())
        meta = _meta_base(category="TV", keywords="sport")
        result = asyncio.run(tracker.get_category_id(meta))
        assert result == {"category_id": "5060"}
