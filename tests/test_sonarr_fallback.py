# Sonarr's /api/v3/parse parses the path in priority. A folder carrying a
# non-Latin prefix (e.g. a CJK native title) yields a series title Sonarr
# cannot match. Retry once with the prefix stripped, title only.

import asyncio
from typing import Any

import src.sonarr as sonarr_module
from src.sonarr import SonarrManager

CONFIG = {"DEFAULT": {"sonarr_url": "http://sonarr", "sonarr_api_key": "sekrit"}}
FOLDER = "/data/tv/子夜归.Example.Release.S01.2026.2160p.WEB-DL.H265-GRP"
SERIES = {"title": "Example Release", "tvdbId": 444, "imdbId": "tt0000444", "tmdbId": 555, "genres": [], "year": 2026}


def _client(answers: dict[str, Any], calls: list[str]) -> type:
    class _Resp:
        status_code = 200

        def __init__(self, payload: Any) -> None:
            self._payload = payload

        def json(self) -> Any:
            return self._payload

    class _Client:
        def __init__(self, *a: Any, **k: Any) -> None:
            pass

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *a: Any) -> None:
            pass

        async def get(self, url: str, **k: Any) -> _Resp:
            calls.append(url)
            series = None if "子夜归" in url else answers.get("series", SERIES)
            return _Resp({"series": series, "parsedEpisodeInfo": {}})

    return _Client


def test_retries_without_non_latin_prefix(monkeypatch: Any) -> None:
    calls: list[str] = []
    monkeypatch.setattr(sonarr_module.httpx, "AsyncClient", _client({}, calls))
    result = asyncio.run(SonarrManager(CONFIG).get_sonarr_data(filename=FOLDER, title="子夜归 Example Release"))
    assert result is not None and result["tvdb_id"] == 444
    assert len(calls) == 2
    assert "title=Example.Release.S01.2026.2160p.WEB-DL.H265-GRP" in calls[1]
    assert "path=" not in calls[1]


def test_no_retry_when_folder_has_no_prefix(monkeypatch: Any) -> None:
    calls: list[str] = []
    monkeypatch.setattr(sonarr_module.httpx, "AsyncClient", _client({"series": None}, calls))
    result = asyncio.run(SonarrManager(CONFIG).get_sonarr_data(filename="/data/tv/Example.Release.S01.2026.2160p.WEB-DL.H265-GRP", title="Example Release"))
    assert result is None
    assert len(calls) == 1
