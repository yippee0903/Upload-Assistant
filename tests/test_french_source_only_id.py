# TOS and G3MINI descriptions can be written in French, which must not be
# reused on English-speaking destinations. When one of them is the metadata
# source, the fetch is forced to only_id: IDs and images are still reused
# (images are taken regardless of only_id), only the description text is not.

import asyncio
from typing import Any

import src.trackermeta as trackermeta

EMPTY_TRACKER_DATA = (None, None, None, None, None, None, None, [], None)


class _FakeCommon:
    captured: dict[str, Any] = {}

    def __init__(self, config: Any) -> None:
        pass

    async def unit3d_torrent_info(self, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
        _FakeCommon.captured = kwargs
        return EMPTY_TRACKER_DATA


class _FakeTracker:
    id_url = "https://example.invalid/torrents/"
    search_url = "https://example.invalid/api/torrents?name="


def _fetch_only_id(monkeypatch: Any, tracker_name: str) -> bool:
    monkeypatch.setattr(trackermeta, "COMMON", _FakeCommon)
    meta = {tracker_name.lower(): "4567", "debug": False}
    asyncio.run(trackermeta.update_metadata_from_tracker(tracker_name, _FakeTracker(), meta, "term", "file", only_id=False))
    return bool(_FakeCommon.captured["only_id"])


def test_g3mini_source_is_forced_to_only_id(monkeypatch: Any) -> None:
    assert _fetch_only_id(monkeypatch, "G3MINI") is True


def test_tos_source_is_forced_to_only_id(monkeypatch: Any) -> None:
    assert _fetch_only_id(monkeypatch, "TOS") is True


def test_other_unit3d_source_keeps_descriptions(monkeypatch: Any) -> None:
    assert _fetch_only_id(monkeypatch, "LST") is False
