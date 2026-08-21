import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from src.trackers.BLU import BLU


def _search(meta_extra: dict[str, Any]) -> dict[str, str]:
    tracker = BLU({"TRACKERS": {"BLU": {"api_key": "k", "announce_url": "http://a"}}, "DEFAULT": {}})
    meta = {"category": "MOVIE", "tmdb": 0, "debug": False, "type": "ENCODE", "resolution": "1080p", "uuid": "x", "base_dir": "/tmp", **meta_extra}
    response = MagicMock(status_code=200)
    response.json.return_value = {"data": []}
    client = AsyncMock()
    client.get.return_value = response
    client.__aenter__.return_value = client
    with (
        patch("src.trackers.UNIT3D.httpx.AsyncClient", return_value=client),
        patch.object(tracker, "get_additional_checks", AsyncMock(return_value=True)),
    ):
        asyncio.run(tracker.search_existing(meta, None))
    return dict(client.get.call_args.kwargs["params"])


def test_tmdb_id_search_does_not_filter_by_category():
    params = _search({"tmdb": 12345})
    assert params["tmdbId"] == "12345"
    assert "categories[]" not in params


def test_without_tmdb_falls_back_to_category():
    params = _search({})
    assert "tmdbId" not in params
    assert "categories[]" in params
