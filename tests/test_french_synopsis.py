"""French fiches: TMDB French overview, else the IMDb French plot, else TMDB English."""

import asyncio
from typing import Any

import src.imdb as imdb_module
from src.trackers.french.naming import FrenchNamingMixin


def _synopsis(monkeypatch: Any, fr_overview: str, imdb_plot: str, imdb_id: int = 33514933) -> str:
    async def fake_plot(imdb_id_arg: Any, language: str) -> str:
        assert language == "fr-FR"
        return imdb_plot

    monkeypatch.setattr(imdb_module.imdb_manager, "get_imdb_plot", fake_plot)
    meta: dict[str, Any] = {"imdb_id": imdb_id, "overview": "English overview."}
    return asyncio.run(FrenchNamingMixin().french_synopsis(meta, {"overview": fr_overview}))


def test_tmdb_french_overview_wins(monkeypatch: Any) -> None:
    assert _synopsis(monkeypatch, "Résumé TMDB.", "Résumé IMDb.") == "Résumé TMDB."


def test_imdb_french_plot_fills_the_gap(monkeypatch: Any) -> None:
    assert _synopsis(monkeypatch, "", "Résumé IMDb.") == "Résumé IMDb."


def test_english_overview_is_the_last_resort(monkeypatch: Any) -> None:
    assert _synopsis(monkeypatch, "", "") == "English overview."


def test_null_tmdb_overview_falls_through(monkeypatch: Any) -> None:
    async def fake_plot(imdb_id_arg: Any, language: str) -> str:
        return "Résumé IMDb."

    monkeypatch.setattr(imdb_module.imdb_manager, "get_imdb_plot", fake_plot)
    meta: dict[str, Any] = {"imdb_id": 1, "overview": "English overview."}
    assert asyncio.run(FrenchNamingMixin().french_synopsis(meta, {"overview": None})) == "Résumé IMDb."


def test_no_imdb_id_skips_the_lookup(monkeypatch: Any) -> None:
    async def boom(*args: Any, **kwargs: Any) -> str:
        raise AssertionError("must not be called")

    monkeypatch.setattr(imdb_module.imdb_manager, "get_imdb_plot", boom)
    meta: dict[str, Any] = {"imdb_id": 0, "overview": "English overview."}
    assert asyncio.run(FrenchNamingMixin().french_synopsis(meta, {})) == "English overview."
