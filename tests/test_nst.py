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
            # Standard movie → numeric 1 (film)
            ("MOVIE", "", "", False, "1"),
            # Standard TV → numeric 2 (serie-tv)
            ("TV", "", "", False, "2"),
            # Documentary movie → numeric 5 (documentaire)
            ("MOVIE", "Documentary", "", False, "5"),
            # Documentary TV → numeric 5 (documentaire)
            ("TV", "Documentary", "", False, "5"),
            # Anime movie → numeric 3 (animation)
            ("MOVIE", "", "", True, "3"),
            # Anime TV → numeric 4 (animation-serie)
            ("TV", "", "", True, "4"),
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
        assert result == {"MOVIE": "1", "TV": "2"}

    def test_reverse(self):
        tracker = NST(_config())
        result = asyncio.run(tracker.get_category_id(_meta_base(), reverse=True))
        assert result == {"1": "MOVIE", "2": "TV"}


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
        assert NST.WEB_LABEL == "WEB"

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
        assert result == {"category_id": "5"}

    def test_documentary_keyword_tv(self):
        tracker = NST(_config())
        meta = _meta_base(category="TV", keywords="documentary")
        result = asyncio.run(tracker.get_category_id(meta))
        assert result == {"category_id": "5"}


# ═══════════════════════════════════════════════════════════════
#   Category slug resolution (used by search_existing)
# ═══════════════════════════════════════════════════════════════


class TestResolveCategorySlug:
    def test_movie_slug(self):
        tracker = NST(_config())
        assert tracker._resolve_category_slug(_meta_base(category="MOVIE")) == "film"

    def test_tv_slug(self):
        tracker = NST(_config())
        assert tracker._resolve_category_slug(_meta_base(category="TV")) == "serie-tv"

    def test_anime_movie_slug(self):
        tracker = NST(_config())
        assert tracker._resolve_category_slug(_meta_base(category="MOVIE", anime=True)) == "animation"

    def test_anime_tv_slug(self):
        tracker = NST(_config())
        assert tracker._resolve_category_slug(_meta_base(category="TV", anime=True)) == "animation-serie"

    def test_documentary_slug(self):
        tracker = NST(_config())
        assert tracker._resolve_category_slug(_meta_base(category="MOVIE", genres="Documentary")) == "documentaire"


# ═══════════════════════════════════════════════════════════════
#   Torrent ID extraction (UUID from upload-assistant response)
# ═══════════════════════════════════════════════════════════════


class TestGetTorrentId:
    def test_uuid_from_download_url(self):
        tracker = NST(_config())
        response_data = {"data": "http://nostradamus.foo/api/upload-assistant/torrents/580bb336-3a06-489a-b874-a0bfa01d396e/download"}
        result = asyncio.run(tracker.get_torrent_id(response_data))
        assert result == "580bb336-3a06-489a-b874-a0bfa01d396e"

    def test_uuid_from_https_url(self):
        tracker = NST(_config())
        response_data = {"data": "https://nostradamus.foo/api/upload-assistant/torrents/3f2c8893-2484-4f65-86c6-a79d9ac32aec/download"}
        result = asyncio.run(tracker.get_torrent_id(response_data))
        assert result == "3f2c8893-2484-4f65-86c6-a79d9ac32aec"

    def test_empty_on_missing_data(self):
        tracker = NST(_config())
        result = asyncio.run(tracker.get_torrent_id({}))
        assert result == ""

    def test_empty_on_no_uuid(self):
        tracker = NST(_config())
        response_data = {"data": "http://nostradamus.foo/some/other/path"}
        result = asyncio.run(tracker.get_torrent_id(response_data))
        assert result == ""


# ═══════════════════════════════════════════════════════════════
#   Additional data (description_format)
# ═══════════════════════════════════════════════════════════════


class TestGetAdditionalData:
    def test_returns_bbcode_format(self):
        tracker = NST(_config())
        result = asyncio.run(tracker.get_additional_data({}))
        assert result["description_format"] == "bbcode"


class TestDetectNstLangue:
    def test_vff_in_name(self):
        assert NST._detect_nst_langue({"name": "Movie.2026.VFF.1080p.WEB.H264-GRP"}) == "VFF"

    def test_vfq_in_name(self):
        assert NST._detect_nst_langue({"name": "Movie.2026.VFQ.1080p.WEB.H264-GRP"}) == "VFQ"

    def test_vfi_in_name(self):
        assert NST._detect_nst_langue({"name": "Movie.2026.VFI.1080p.WEB.H264-GRP"}) == "VFI"

    def test_vf2_maps_to_vf(self):
        assert NST._detect_nst_langue({"name": "Movie.2026.VF2.1080p.WEB.H264-GRP"}) == "VF"

    def test_plain_vf_maps_to_vf(self):
        assert NST._detect_nst_langue({"name": "Movie.2026.VF.1080p.WEB.H264-GRP"}) == "VF"

    def test_vf3_maps_to_vf(self):
        assert NST._detect_nst_langue({"name": "Movie.2026.VF3.1080p.WEB.H264-GRP"}) == "VF"

    def test_vf_at_end_of_name(self):
        assert NST._detect_nst_langue({"name": "Movie.2026.1080p.WEB.VF"}) == "VF"

    def test_vof_maps_to_francais(self):
        assert NST._detect_nst_langue({"name": "Movie.2026.VOF.1080p.WEB.H264-GRP"}) == "Français"

    def test_french_tag_maps_to_francais(self):
        assert NST._detect_nst_langue({"name": "Movie.2026.FRENCH.1080p.WEB-GRP"}) == "Français"

    def test_truefrench_maps_to_francais(self):
        assert NST._detect_nst_langue({"name": "Movie.2026.TRUEFRENCH.1080p.WEB-GRP"}) == "Français"

    def test_multi_vff_returns_vff(self):
        assert NST._detect_nst_langue({"name": "Movie.2026.MULTi.VFF.HDR.2160p.WEB.H265-GRP"}) == "VFF"

    def test_multi_vfq_returns_vfq(self):
        assert NST._detect_nst_langue({"name": "Movie.2026.MULTi.VFQ.1080p.WEB-GRP"}) == "VFQ"

    def test_multi_plain_returns_vf(self):
        assert NST._detect_nst_langue({"name": "Movie.2026.MULTi.HDR.2160p.WEB.H265-GRP"}) == "VF"

    def test_francais_from_audio_languages(self):
        meta = {"name": "Movie.2026.1080p.WEB-GRP", "audio_languages": ["French"]}
        assert NST._detect_nst_langue(meta) == "Français"

    def test_empty_when_no_data(self):
        assert NST._detect_nst_langue({}) == ""

    def test_region_coded_french_is_francais(self):
        """Region-coded French tracks (fr-fr, fr-ca) map to Français."""
        meta = {"name": "Movie.2026.1080p.WEB-GRP", "audio_languages": ["fr-fr", "fr-ca"]}
        assert NST._detect_nst_langue(meta) == "Français"

    def test_english_only_returns_empty(self):
        """English-only releases get empty langue (NST requires VF)."""
        meta = {"name": "Movie.2026.1080p.WEB-GRP", "audio_languages": ["English"]}
        assert NST._detect_nst_langue(meta) == ""

    def test_langue_sent_in_additional_data(self):
        tracker = NST(_config())
        meta = {"name": "Movie.2026.MULTi.VFF.HDR.2160p.WEB.H265-GRP"}
        result = asyncio.run(tracker.get_additional_data(meta))
        assert result["langue"] == "VFF"


# ═══════════════════════════════════════════════════════════════
#   BBCode sanitization (strip unsupported extensions)
# ═══════════════════════════════════════════════════════════════


class TestSanitizeBBCode:
    def test_strip_img_size(self):
        assert NST._sanitize_bbcode("[img=300]https://example.com/img.png[/img]") == "[img]https://example.com/img.png[/img]"

    def test_strip_img_size_350(self):
        assert NST._sanitize_bbcode("[img=350]https://example.com/img.png[/img]") == "[img]https://example.com/img.png[/img]"

    def test_plain_img_unchanged(self):
        assert NST._sanitize_bbcode("[img]https://example.com/img.png[/img]") == "[img]https://example.com/img.png[/img]"

    def test_tmdb_poster_downscaled(self):
        result = NST._sanitize_bbcode("[img]https://image.tmdb.org/t/p/original/abc.jpg[/img]")
        assert "image.tmdb.org/t/p/w300/abc.jpg" in result
        assert "/original/" not in result

    def test_imgbox_uses_thumbnails(self):
        result = NST._sanitize_bbcode("[img]https://images2.imgbox.com/64/45/ebZ94hUP_o.png[/img]")
        assert result == "[img]https://thumbs2.imgbox.com/64/45/ebZ94hUP_t.png[/img]"

    def test_strip_size_tags(self):
        assert NST._sanitize_bbcode("[size=4]big text[/size]") == "big text"

    def test_pre_to_code(self):
        assert NST._sanitize_bbcode("[pre]some text[/pre]") == "[code]some text[/code]"

    def test_center_unchanged(self):
        assert NST._sanitize_bbcode("[center]text[/center]") == "[center]text[/center]"

    def test_url_unchanged(self):
        assert NST._sanitize_bbcode("[url=https://example.com]link[/url]") == "[url=https://example.com]link[/url]"

    def test_ptscreens_uses_medium(self):
        result = NST._sanitize_bbcode("[img]https://ptscreens.com/images/2025/03/21/abc123.png[/img]")
        assert result == "[img]https://ptscreens.com/images/2025/03/21/abc123.md.png[/img]"

    def test_onlyimage_uses_medium(self):
        result = NST._sanitize_bbcode("[img]https://onlyimage.org/images/2025/03/21/xyz789.jpg[/img]")
        assert result == "[img]https://onlyimage.org/images/2025/03/21/xyz789.md.jpg[/img]"

    def test_pixhost_uses_thumbnails(self):
        result = NST._sanitize_bbcode("[img]https://img75.pixhost.to/images/123/456_abcdef.png[/img]")
        assert result == "[img]https://t75.pixhost.to/thumbs/123/456_abcdef.png[/img]"

    def test_typical_description(self):
        """Test a typical UA description fragment."""
        bbcode = (
            "[center][img=300]https://image.tmdb.org/t/p/original/poster.png[/img][/center]\n"
            "[center][url=https://imgbox.com/a][img=350]https://images2.imgbox.com/a/b/abc_o.png[/img][/url][/center]"
        )
        result = NST._sanitize_bbcode(bbcode)
        expected = (
            "[center][img]https://image.tmdb.org/t/p/w300/poster.png[/img][/center]\n"
            "[center][url=https://imgbox.com/a][img]https://thumbs2.imgbox.com/a/b/abc_t.png[/img][/url][/center]"
        )
        assert result == expected
