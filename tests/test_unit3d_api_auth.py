# Some UNIT3D sites reject the api_token query parameter and redirect the
# request to the login page; all of them accept the Authorization Bearer
# header. The API requests must send both.

import asyncio
from typing import Any

import src.trackers.COMMON as common_module
from src.trackers.COMMON import COMMON

CONFIG = {"TRACKERS": {"LST": {"api_key": "sekrit"}}, "DEFAULT": {}}


class _FakeResponse:
    status_code = 200

    def json(self) -> dict[str, Any]:
        return {}


class _FakeClient:
    captured: dict[str, Any] = {}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass

    async def get(self, **kwargs: Any) -> _FakeResponse:
        _FakeClient.captured = kwargs
        return _FakeResponse()


def test_torrent_info_sends_bearer_header_and_param(monkeypatch: Any) -> None:
    monkeypatch.setattr(common_module.httpx, "AsyncClient", _FakeClient)
    asyncio.run(
        COMMON(CONFIG).unit3d_torrent_info("LST", "https://x/api/torrents/", "https://x/api/torrents/filter", {"debug": False}, id="1")
    )
    assert _FakeClient.captured["headers"]["Authorization"] == "Bearer sekrit"
    assert _FakeClient.captured["params"]["api_token"] == "sekrit"


def test_region_distributor_sends_bearer_header(monkeypatch: Any) -> None:
    monkeypatch.setattr(common_module.httpx, "AsyncClient", _FakeClient)
    _FakeClient.captured = {}
    meta = {"debug": False, "is_disc": "BDMV", "region": None, "distributor": None}
    asyncio.run(COMMON(CONFIG).unit3d_region_distributor(meta, "LST", "https://x/api/torrents/", id="1"))
    assert _FakeClient.captured["headers"]["Authorization"] == "Bearer sekrit"
