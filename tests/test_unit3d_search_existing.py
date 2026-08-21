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


def test_without_tmdb_keeps_category_filter_and_zero_id():
    params = _search({})
    assert params["tmdbId"] == "0"  # never an unconstrained name="" query
    assert "categories[]" in params


def test_site_local_region_ids_override_the_shared_table():
    import asyncio as _asyncio

    from src.trackers.AITHER import AITHER
    from src.trackers.LST import LST

    cfg = {"TRACKERS": {"AITHER": {"api_key": "k", "announce_url": "a"}, "LST": {"api_key": "k", "announce_url": "a"}}, "DEFAULT": {}}
    assert _asyncio.run(AITHER(cfg).get_region_id({"region": "FIN"})) == {"region_id": "244"}
    assert _asyncio.run(LST(cfg).get_region_id({"region": "FIN"})) == {"region_id": "245"}
    assert _asyncio.run(LST(cfg).get_region_id({"region": "FRA"})) == {"region_id": "73"}  # shared table still applies


def _search_failing(exc: Exception) -> dict[str, Any]:
    import httpx

    tracker = BLU({"TRACKERS": {"BLU": {"api_key": "k", "announce_url": "http://a"}}, "DEFAULT": {}})
    meta: dict[str, Any] = {"category": "MOVIE", "tmdb": 1, "debug": False, "type": "ENCODE", "resolution": "1080p", "uuid": "x", "base_dir": "/tmp"}
    client = AsyncMock()
    client.get.side_effect = exc
    client.__aenter__.return_value = client
    with (
        patch("src.trackers.UNIT3D.httpx.AsyncClient", return_value=client),
        patch.object(tracker, "get_additional_checks", AsyncMock(return_value=True)),
        patch("src.trackers.UNIT3D.asyncio.sleep", AsyncMock()),
    ):
        assert asyncio.run(tracker.search_existing(meta, None)) == []
    del httpx
    return meta


def test_failed_dupe_search_skips_the_tracker():
    # A network failure is not "no dupes": fail closed like V3X does.
    import httpx

    for exc in (httpx.ConnectError("[SSL: WRONG_VERSION_NUMBER]"), httpx.ReadTimeout("t"), RuntimeError("boom")):
        meta = _search_failing(exc)
        assert meta["skipping"] == "BLU", exc
        assert "dupe search failed" in meta["tracker_status"]["BLU"]["status_message"]
