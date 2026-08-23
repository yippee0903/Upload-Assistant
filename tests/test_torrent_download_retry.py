"""The post-upload .torrent download survives a short network window instead of leaving an orphan upload."""

import asyncio
from typing import Any

import httpx
import pytest

import src.trackers.COMMON as common_module
from src.trackers.COMMON import COMMON


def _common(monkeypatch: Any, responses: list[Any]) -> tuple[COMMON, list[int]]:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        outcome = responses[len(calls) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    real_client = httpx.AsyncClient

    def client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs.pop("transport", None)
        return real_client(*args, transport=httpx.MockTransport(handler), **kwargs)

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(common_module.httpx, "AsyncClient", client)
    monkeypatch.setattr(common_module.asyncio, "sleep", no_sleep)
    return COMMON(config={"DEFAULT": {}, "TRACKERS": {}}), calls


def _meta(tmp_path: Any) -> dict[str, Any]:
    (tmp_path / "tmp" / "x").mkdir(parents=True)
    return {"base_dir": str(tmp_path), "uuid": "x"}


def test_transient_failure_is_retried(monkeypatch: Any, tmp_path: Any) -> None:
    ok = httpx.Response(200, content=b"d8:announce0:e", headers={"content-type": "application/x-bittorrent"})
    common, calls = _common(monkeypatch, [httpx.ConnectError("wrong version number"), httpx.ConnectError("wrong version number"), ok])
    asyncio.run(common.download_tracker_torrent(_meta(tmp_path), "GRP", downurl="https://example-tracker.org/download/1"))
    assert len(calls) == 3
    assert (tmp_path / "tmp" / "x" / "[GRP].torrent").read_bytes() == b"d8:announce0:e"


def test_persistent_failure_gives_up_after_four_attempts(monkeypatch: Any, tmp_path: Any) -> None:
    common, calls = _common(monkeypatch, [httpx.ConnectError("down")] * 4)
    assert asyncio.run(common.download_tracker_torrent(_meta(tmp_path), "GRP", downurl="https://example-tracker.org/download/1")) is None
    assert len(calls) == 4
    assert not (tmp_path / "tmp" / "x" / "[GRP].torrent").exists()


def test_html_answer_is_not_retried(monkeypatch: Any, tmp_path: Any) -> None:
    html = httpx.Response(200, content=b"<html>login</html>", headers={"content-type": "text/html"})
    common, calls = _common(monkeypatch, [html])
    assert asyncio.run(common.download_tracker_torrent(_meta(tmp_path), "GRP", downurl="https://example-tracker.org/download/1")) is None
    assert len(calls) == 1


@pytest.mark.parametrize("status", [500, 502])
def test_server_errors_are_retried(monkeypatch: Any, tmp_path: Any, status: int) -> None:
    ok = httpx.Response(200, content=b"d8:announce0:e", headers={"content-type": "application/x-bittorrent"})
    common, calls = _common(monkeypatch, [httpx.Response(status), ok])
    asyncio.run(common.download_tracker_torrent(_meta(tmp_path), "GRP", downurl="https://example-tracker.org/download/1"))
    assert len(calls) == 2
