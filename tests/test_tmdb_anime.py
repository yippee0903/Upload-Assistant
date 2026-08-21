import asyncio
from unittest.mock import AsyncMock, patch

from src.tmdb import get_anime

ROMAJI = ("Romaji Title", 123, "eng", "2020", 12, "Shounen", 456)


def _anime(response: dict, meta: dict) -> bool:
    with patch("src.tmdb.get_romaji", AsyncMock(return_value=ROMAJI)):
        return asyncio.run(get_anime(response, meta))[2]


def test_japanese_production_in_english_counts_as_anime():
    response = {"genres": [{"id": 16, "name": "Animation"}], "original_language": "en", "origin_country": ["JP"]}
    assert _anime(response, {"title": "T", "aka": "", "mal_id": 0}) is True


def test_non_japanese_animation_is_not_anime():
    response = {"genres": [{"id": 16}], "original_language": "en", "production_countries": [{"iso_3166_1": "US"}]}
    assert _anime(response, {"title": "T", "aka": "", "mal_id": 0}) is False


def test_known_mal_id_forces_anime():
    response = {"genres": [], "original_language": "en"}
    assert _anime(response, {"title": "T", "aka": "", "mal_id": 99}) is True
