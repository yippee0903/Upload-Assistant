import asyncio
from typing import Any
from unittest.mock import AsyncMock

from src.trackers.IHD import IHD


def _config() -> dict[str, Any]:
    return {
        "TRACKERS": {
            "IHD": {
                "api_key": "fake",
                "announce_url": "https://infinityhd.net/announce/FAKE",
            }
        },
        "DEFAULT": {"tmdb_api": "fake"},
    }


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _base_meta(**overrides: Any) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "title": "12th Fail",
        "alt_title": "",
        "year": "2023",
        "manual_year": None,
        "category": "MOVIE",
        "type": "WEBDL",
        "source": "WEB",
        "service": "AMZN",
        "resolution": "1080p",
        "uhd": "",
        "hdr": "",
        "season": "",
        "episode": "",
        "tv_pack": False,
        "repack": "",
        "3D": "",
        "edition": "",
        "region": "",
        "audio": "DD+ 5.1 Atmos",
        "video_encode": "H.264",
        "video_codec": "",
        "webdv": "",
        "is_disc": False,
        "tag": "-RAWR",
        "search_year": "2023",
        "no_season": False,
        "no_year": False,
        "manual_date": None,
        "language_checked": True,
        "audio_languages": ["Hindi"],
        "debug": False,
    }
    meta.update(overrides)
    return meta


def _ihd(meta: dict[str, Any]) -> IHD:
    t = IHD(_config())
    t._build_audio_string = AsyncMock(return_value="")
    return t


class TestIhdGetNameWebDl:
    """WEB-DL: … Resolution SERVICE WEB-DL Dub Audio Hi10P HDR VCodec-Tag"""

    def test_webdl_basic_name(self):
        meta = _base_meta()
        t = _ihd(meta)
        result = _run(t.get_name(meta))
        name = result["name"]
        # Service must appear before WEB-DL
        assert "AMZN WEB-DL" in name
        assert name.endswith("-RAWR")

    def test_webdl_service_before_type(self):
        """'12th Fail 2023 1080p AMZN WEB-DL DD+ 5.1 Atmos H.264-RAWR'"""
        meta = _base_meta()
        t = _ihd(meta)
        result = _run(t.get_name(meta))
        name = result["name"]
        idx_amzn = name.index("AMZN")
        idx_webdl = name.index("WEB-DL")
        assert idx_amzn < idx_webdl

    def test_webdl_hdr_after_audio(self):
        """HDR must come after audio, before video codec."""
        meta = _base_meta(hdr="HDR", video_encode="H.265")
        t = _ihd(meta)
        result = _run(t.get_name(meta))
        name = result["name"]
        idx_audio = name.index("DD+")
        idx_hdr = name.index("HDR")
        idx_codec = name.index("H.265")
        assert idx_audio < idx_hdr < idx_codec

    def test_webdl_hi10p_between_audio_and_hdr(self):
        """Hi10P must appear after audio and before HDR/codec for encode/web."""
        meta = _base_meta(video_encode="Hi10P x264", hdr="HDR")
        t = _ihd(meta)
        result = _run(t.get_name(meta))
        name = result["name"]
        assert "Hi10P" in name
        idx_audio = name.index("DD+")
        idx_hi10p = name.index("Hi10P")
        idx_hdr = name.index("HDR")
        assert idx_audio < idx_hi10p < idx_hdr

    def test_webdl_no_duplicate_whitespace(self):
        meta = _base_meta(repack="", edition="", hdr="", uhd="")
        t = _ihd(meta)
        result = _run(t.get_name(meta))
        assert "  " not in result["name"]


class TestIhdGetNameEncode:
    """Encode: … Resolution SOURCE Dub Audio Hi10P HDR VCodec-Tag (no TYPE token)"""

    def test_encode_no_webdl_token(self):
        meta = _base_meta(type="ENCODE", source="BluRay", service="")
        t = _ihd(meta)
        result = _run(t.get_name(meta))
        name = result["name"]
        assert "WEB-DL" not in name
        assert "BluRay" in name

    def test_encode_order(self):
        meta = _base_meta(type="ENCODE", source="BluRay", service="", hdr="HDR", video_encode="x264")
        t = _ihd(meta)
        result = _run(t.get_name(meta))
        name = result["name"]
        idx_bluray = name.index("BluRay")
        idx_audio = name.index("DD+")
        idx_hdr = name.index("HDR")
        idx_codec = name.index("x264")
        assert idx_bluray < idx_audio < idx_hdr < idx_codec


class TestIhdGetNameRemux:
    """REMUX: … Resolution SOURCE REMUX HDR VCodec Dub Audio-Tag"""

    def test_remux_token_present(self):
        meta = _base_meta(type="REMUX", source="BluRay", service="", video_encode="", video_codec="HEVC", is_disc=False)
        t = _ihd(meta)
        result = _run(t.get_name(meta))
        assert "REMUX" in result["name"]

    def test_remux_codec_before_audio(self):
        meta = _base_meta(type="REMUX", source="BluRay", service="", video_encode="", video_codec="HEVC", is_disc=False)
        t = _ihd(meta)
        result = _run(t.get_name(meta))
        name = result["name"]
        assert name.index("HEVC") < name.index("DD+")


class TestIhdGetNameTV:
    """TV: season pack drops episode, year dropped when no search_year."""

    def test_tv_pack_no_episode(self):
        meta = _base_meta(
            category="TV",
            type="WEBDL",
            service="NF",
            season="S01",
            episode="E01",
            tv_pack=True,
            search_year="2023",
        )
        t = _ihd(meta)
        result = _run(t.get_name(meta))
        name = result["name"]
        assert "S01" in name
        assert "E01" not in name

    def test_tv_no_year_when_no_search_year(self):
        meta = _base_meta(
            category="TV",
            type="WEBDL",
            service="NF",
            season="S01",
            episode="E01",
            tv_pack=False,
            search_year="",
        )
        t = _ihd(meta)
        result = _run(t.get_name(meta))
        name = result["name"]
        assert "2023" not in name


class TestIhdGetNameDub:
    """Dub tag (Multi/Dual-Audio/Dubbed) injected before audio string."""

    def test_multi_dub_when_two_audio_tracks(self):
        meta = _base_meta(audio_languages=["Hindi", "English"])
        t = _ihd(meta)
        result = _run(t.get_name(meta))
        assert "Multi" in result["name"]

    def test_no_dub_tag_for_single_language(self):
        meta = _base_meta(audio_languages=["Hindi"])
        t = _ihd(meta)
        result = _run(t.get_name(meta))
        assert "Multi" not in result["name"]
        assert "Dual-Audio" not in result["name"]


class TestIhdGetNameTag:
    def test_tag_at_end(self):
        meta = _base_meta(tag="-MYGRP")
        t = _ihd(meta)
        result = _run(t.get_name(meta))
        assert result["name"].endswith("-MYGRP")

    def test_nogroup_default_when_no_tag(self):
        meta = _base_meta(tag=None)
        t = _ihd(meta)
        result = _run(t.get_name(meta))
        assert result["name"].endswith("-NOGROUP")
