"""Unattended runs have no stdin: a missing TMDb match must not open an interactive prompt."""

import asyncio
from typing import Any

import pytest

import src.tmdb as tmdb


class _EmptyResponse:
    status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return {}


class _NoResultClient:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> "_NoResultClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def get(self, *args: Any, **kwargs: Any) -> _EmptyResponse:
        return _EmptyResponse()


def _stub_lookups(monkeypatch: Any) -> None:
    async def no_search(*args: Any, **kwargs: Any) -> tuple[int, str]:
        return 0, "MOVIE"

    def closed_stdin(*args: Any, **kwargs: Any) -> str:
        raise EOFError("EOF when reading a line")

    monkeypatch.setattr(tmdb.httpx, "AsyncClient", _NoResultClient)
    monkeypatch.setattr(tmdb, "get_tmdb_id", no_search)
    monkeypatch.setattr(tmdb.console, "input", closed_stdin)


def test_unattended_returns_no_id_instead_of_prompting(monkeypatch: Any) -> None:
    _stub_lookups(monkeypatch)
    category, tmdb_id, _, _ = asyncio.run(tmdb.get_tmdb_from_imdb("tt1234567", None, 2026, "Example.Release.2026.1080p-GRP", mode="cli", imdb_info={"title": "Example"}, unattended=True))
    assert (category, tmdb_id) == ("MOVIE", 0)


def test_interactive_still_prompts(monkeypatch: Any) -> None:
    _stub_lookups(monkeypatch)
    with pytest.raises(EOFError):
        asyncio.run(tmdb.get_tmdb_from_imdb("tt1234567", None, 2026, "Example.Release.2026.1080p-GRP", mode="cli", imdb_info={"title": "Example"}))
