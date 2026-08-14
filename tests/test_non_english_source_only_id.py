# Non-English trackers (French, Brazilian, Spanish, Italian, Polish, Nordic…)
# can carry descriptions written in their own language, which must not be
# reused on English-speaking destinations. When one of them is the metadata
# source, the fetch is forced to only_id: IDs and images are still reused
# (images are taken regardless of only_id), only the description text is not.

import asyncio
from typing import Any

import pytest

import src.trackermeta as trackermeta
from src.trackermeta import NON_ENGLISH_SOURCE_TRACKERS

EMPTY_TRACKER_DATA = (None, None, None, None, None, None, None, [], None)

EXPECTED_NON_ENGLISH = {
    "TOS",
    "G3MINI",
    "GF",
    "NST",  # French
    "CBR",
    "LCD",
    "SAM",
    "PT",  # Portuguese
    "EMUW",
    "LT",
    "TTR",  # Spanish
    "ITT",
    "SHRI",  # Italian
    "PTT",  # Polish
    "RAS",  # Nordic
}


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


def test_non_english_source_list_is_expected() -> None:
    assert set(NON_ENGLISH_SOURCE_TRACKERS) == EXPECTED_NON_ENGLISH


@pytest.mark.parametrize("tracker_name", sorted(EXPECTED_NON_ENGLISH))
def test_non_english_source_is_forced_to_only_id(monkeypatch: Any, tracker_name: str) -> None:
    assert _fetch_only_id(monkeypatch, tracker_name) is True


@pytest.mark.parametrize("tracker_name", ["LST", "SP", "ULCX"])
def test_english_source_keeps_descriptions(monkeypatch: Any, tracker_name: str) -> None:
    assert _fetch_only_id(monkeypatch, tracker_name) is False
