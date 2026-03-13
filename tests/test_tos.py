import asyncio
from typing import Any
from unittest.mock import AsyncMock

from src.trackers.TOS import TOS


def _config() -> dict[str, Any]:
    return {
        "TRACKERS": {
            "TOS": {
                "api_key": "test-api-key",
                "announce_url": "https://theoldschool.cc/announce/FAKE",
            }
        },
        "DEFAULT": {"tmdb_api": "fake-key"},
    }


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _meta(category: str = "MOVIE", tv_pack: bool = False) -> dict[str, Any]:
    return {
        "category": category,
        "tv_pack": tv_pack,
    }


class TestTosCategoryIdAudioPrefix:
    def test_movie_ad_vostfr_maps_to_vostfr_category(self):
        t = TOS(_config())
        t._build_audio_string = AsyncMock(return_value="AD.VOSTFR")

        result = _run(t.get_category_id(_meta("MOVIE")))

        assert result == {"category_id": "6"}

    def test_tv_ad_vostfr_maps_to_vostfr_category(self):
        t = TOS(_config())
        t._build_audio_string = AsyncMock(return_value="AD.VOSTFR")

        result = _run(t.get_category_id(_meta("TV")))

        assert result == {"category_id": "7"}

    def test_tv_pack_ad_prefixed_vostfr_maps_to_vostfr_pack_category(self):
        t = TOS(_config())
        t._build_audio_string = AsyncMock(return_value="AD.AD.VOSTFR")

        result = _run(t.get_category_id(_meta("TV", tv_pack=True)))

        assert result == {"category_id": "9"}
