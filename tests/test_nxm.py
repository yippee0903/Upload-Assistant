# Tests for NXM tracker — nexum-core.com (Nostradamus)
"""
Test suite for the NXM tracker implementation.
Covers: category mapping, URL configuration,
        and French tracker mixin integration.
"""

import asyncio
from typing import Any

import pytest

from src.trackers.NXM import NXM

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
        "TRACKERS": {"NXM": tracker_cfg},
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
        "audio_languages": ["French"],
        "subtitle_languages": [],
        "mediainfo": {},
    }
    m.update(overrides)
    return m


# ═══════════════════════════════════════════════════════════════
#   URL Configuration
# ═══════════════════════════════════════════════════════════════


class TestURLs:
    def test_base_url(self):
        tracker = NXM(_config())
        assert tracker.base_url == "https://nexum-core.com/"

    def test_upload_url(self):
        tracker = NXM(_config())
        assert tracker.upload_url == "https://nexum-core.com/api/v1/upload"

    def test_search_url(self):
        tracker = NXM(_config())
        assert tracker.search_url == "https://nexum-core.com/api/v1/torrents/"

    def test_torrent_url(self):
        tracker = NXM(_config())
        assert tracker.torrent_url == "https://nexum-core.com/torrents/"


# ═══════════════════════════════════════════════════════════════
#   Category mapping
# ═══════════════════════════════════════════════════════════════


class TestGetCategoryId:
    @pytest.mark.parametrize(
        "category,genres,keywords,anime,expected_id",
        [
            # Standard movie → numeric 1 (film)
            ("MOVIE", "", "", False, 1),
            # Standard TV → numeric 2 (serie-tv)
            ("TV", "", "", False, 2),
            # Documentary movie → numeric 3 (documentaire)
            ("MOVIE", "Documentary", "", False, 3),
            # Documentary TV → numeric 3 (documentaire)
            ("TV", "Documentary", "", False, 3),
            # Anime movie → numeric 4 (animation)
            ("MOVIE", "", "", True, 4),
            # Anime TV → numeric 4 (animation-serie)
            ("TV", "", "", True, 4),
            # Concerts → numeric 5 (concerts-spectacles)
            ("TV", "concert", "", False, 5),
            ("MOVIE", "concert", "", False, 5),
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
        tracker = NXM(_config())
        meta = _meta_base(category=category, genres=genres, keywords=keywords, anime=anime)
        result = asyncio.run(tracker._get_category(meta))
        assert result == expected_id

# ═══════════════════════════════════════════════════════════════
#   Tracker identity
# ═══════════════════════════════════════════════════════════════


class TestTrackerIdentity:
    def test_tracker_name(self):
        tracker = NXM(_config())
        assert tracker.tracker == "NXM"

    def test_source_flag(self):
        tracker = NXM(_config())
        assert tracker.source_flag == "NXM"

    def test_web_label(self):
        assert NXM.WEB_LABEL == "WEB"

    def test_prefer_original_title(self):
        assert NXM.PREFER_ORIGINAL_TITLE is True

    def test_include_service_in_name(self):
        assert NXM.INCLUDE_SERVICE_IN_NAME is True


# ═══════════════════════════════════════════════════════════════
#  Nogroup WEB-DL naming — regression for Cyclo-style filenames
# ═══════════════════════════════════════════════════════════════


class TestNogroupWebDL:
    """WEB-DL releases without a group tag must use NXM's notag_label.

    NXM uses WEB_LABEL='WEB' and notag_label='NoGrp'.
    Regression: Cyclo.1995.1080p.WEB-DL.AAC.2.0.H.264.mkv had a false
    group '-DL.AAC.2.0.H.264' extracted, producing duplicated tokens.
    """

    def _get_name(self, meta: dict) -> str:
        return asyncio.run(NXM(_config()).get_name(meta))['name']

    def test_empty_tag_uses_notag_label(self):
        """tag='' (nogroup) must produce a name ending with '-NoGrp'."""
        meta = _meta_base(
            title='Cyclo',
            year='1995',
            audio='AAC 2.0',
            video_encode='H.264',
            video_codec='H.264',
            service='',
            tag='',
        )
        name = self._get_name(meta)
        assert name.endswith('-NoGrp'), f"Expected -NoGrp suffix, got: {name!r}"

    def test_no_audio_duplication(self):
        """Audio token must appear exactly once — no duplication from a false tag."""
        meta = _meta_base(
            title='Cyclo',
            year='1995',
            audio='AAC 2.0',
            video_encode='H.264',
            video_codec='H.264',
            service='',
            tag='',
        )
        name = self._get_name(meta)
        assert name.count('AAC') == 1, (
            f"Audio token 'AAC' duplicated in name: {name!r}."
        )

    def test_real_group_preserved(self):
        """A real group tag must not be replaced by the notag label."""
        meta = _meta_base(
            title='Cyclo',
            year='1995',
            audio='AAC 2.0',
            video_encode='H.264',
            video_codec='H.264',
            service='',
            tag='-FRiENDS',
        )
        name = self._get_name(meta)
        assert name.endswith('-FRiENDS'), f"Expected -FRiENDS suffix, got: {name!r}"
