# A UNIT3D site whose file_name filter is broken answers with its newest
# torrents instead of matches. A result is only trusted when its file list
# actually contains the file we searched for.

import asyncio
from typing import Any

import src.trackers.COMMON as common_module
from src.trackers.COMMON import COMMON

CONFIG = {"TRACKERS": {"LST": {"api_key": "sekrit"}}, "DEFAULT": {}}
SEARCHED = "Example.Release.S01E01.2026.2160p.WEB-DL.H265-GRP.mkv"


def _torrent(tmdb: int, files: list[str]) -> dict[str, Any]:
    return {"attributes": {"tmdb_id": tmdb, "imdb_id": 0, "tvdb_id": 0, "mal_id": 0, "files": [{"name": f} for f in files]}}


def _client_returning(data: list[dict[str, Any]]) -> type:
    class _Resp:
        status_code = 200

        def json(self) -> dict[str, Any]:
            return {"data": data}

    class _Client:
        def __init__(self, *a: Any, **k: Any) -> None:
            pass

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *a: Any) -> None:
            pass

        async def get(self, **k: Any) -> _Resp:
            return _Resp()

    return _Client


def _search(monkeypatch: Any, data: list[dict[str, Any]]) -> Any:
    monkeypatch.setattr(common_module.httpx, "AsyncClient", _client_returning(data))
    meta = {"debug": False, "unattended": True}
    return asyncio.run(COMMON(CONFIG).unit3d_torrent_info("LST", "https://x/api/torrents/", "https://x/api/torrents/filter", meta, file_name=SEARCHED))


def test_unrelated_results_are_not_a_match(monkeypatch: Any) -> None:
    data = [_torrent(111, ["Other.Show.S01E03.1080p.WEB-DL-GRP.mkv"]), _torrent(222, ["Another.Show.S02E01.2160p.WEB-DL-GRP.mkv"])]
    tmdb, imdb, tvdb, *_ = _search(monkeypatch, data)
    assert (tmdb, imdb, tvdb) == (None, None, None)


def test_matching_result_is_picked_even_when_not_first(monkeypatch: Any) -> None:
    data = [_torrent(111, ["Other.Show.S01E03.1080p.WEB-DL-GRP.mkv"]), _torrent(222, [f"Example.Release.S01.2026.2160p.WEB-DL.H265-GRP/{SEARCHED}"])]
    tmdb, *_ = _search(monkeypatch, data)
    assert tmdb == 222


def test_result_without_file_list_is_still_trusted(monkeypatch: Any) -> None:
    # Older/other UNIT3D responses may omit files; keep today's behaviour there.
    data = [{"attributes": {"tmdb_id": 333, "imdb_id": 0, "tvdb_id": 0, "mal_id": 0}}]
    tmdb, *_ = _search(monkeypatch, data)
    assert tmdb == 333
