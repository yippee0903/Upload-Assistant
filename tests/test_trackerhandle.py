import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from src.trackerhandle import process_trackers


def _run(meta_extra: dict[str, Any], tracker_cls: type) -> tuple[dict[str, Any], AsyncMock]:
    meta: dict[str, Any] = {
        "trackers": ["BLU"],
        "tracker_status": {"BLU": {"upload": True}},
        "filelist": ["/x/a.mkv"],
        "unattended": True,
        "name": "Anonymous.Release.2020",
        **meta_extra,
    }
    config = {"DEFAULT": {"multiScreens": 2}, "TRACKERS": {"default_trackers": "BLU"}}
    client = AsyncMock()
    with patch("src.trackerhandle.asyncio.sleep", new_callable=AsyncMock) as sleep:
        asyncio.run(process_trackers(meta, config, client, MagicMock(), [], {"BLU": tracker_cls}))
    client.sleep = sleep
    return meta, client


class _Ok:
    tracker = "BLU"
    post_upload_delay = 7

    def __init__(self, config: Any) -> None:
        pass

    async def upload(self, meta: dict[str, Any], _disctype: str) -> bool:
        meta["tracker_status"]["BLU"]["status_message"] = "ok"
        return True


class _ReturnsNone(_Ok):
    post_upload_delay = 0

    async def upload(self, meta: dict[str, Any], _disctype: str) -> None:
        meta["tracker_status"]["BLU"]["status_message"] = "ok"
        return None


def test_success_adds_to_client_and_honours_post_upload_delay():
    meta, client = _run({}, _Ok)
    client.add_to_client.assert_awaited_once_with(meta, "BLU")
    client.sleep.assert_awaited_once_with(7)
    assert "BLU_upload_duration" in meta


def test_upload_gate_and_none_result():
    _, client = _run({"tracker_status": {"BLU": {"upload": False}}}, _Ok)
    client.add_to_client.assert_not_awaited()
    _, client = _run({}, _ReturnsNone)
    client.add_to_client.assert_not_awaited()
