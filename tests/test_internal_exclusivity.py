# The internal-exclusivity guard: internal groups are exclusive to their
# origin tracker, whose rules forbid reposting elsewhere, permanently or for a
# time window. Verdicts: blocked (confirmed internal, window active), warn
# (group listed but origin unknowable), clear.

import asyncio
import ast
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import src.internal_exclusivity as ie

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = datetime(2026, 8, 14, tzinfo=timezone.utc)
CONFIG: dict[str, Any] = {"TRACKERS": {}}


class TestPureFunctions:
    def test_permanent_is_always_active(self):
        assert ie.exclusivity_active(None, NOW - timedelta(days=10_000), now=NOW)
        assert ie.exclusivity_active(None, None, now=NOW)

    def test_window_active(self):
        assert ie.exclusivity_active(365, NOW - timedelta(days=100), now=NOW)

    def test_window_expired(self):
        assert not ie.exclusivity_active(365, NOW - timedelta(days=400), now=NOW)

    def test_unparseable_date_with_window_is_conservative(self):
        assert ie.exclusivity_active(365, None, now=NOW)

    def test_parse_created_at(self):
        parsed = ie._parse_created_at("2026-01-01T00:00:00.000000Z")
        assert parsed == datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert ie._parse_created_at("garbage") is None
        assert ie._parse_created_at(None) is None

    def test_search_term(self):
        assert ie._search_term({"filelist": ["/media/x/Some.Movie.1962.1080p-GRP.mkv"], "uuid": "ignored"}) == "Some.Movie.1962.1080p-GRP.mkv"
        assert ie._search_term({"uuid": "Some.Show.S01.1080p-GRP"}) == "Some.Show.S01.1080p-GRP"
        assert ie._search_term({}) == ""

    def test_pick_search_result_prefers_matching_group(self):
        data = [
            {"attributes": {"name": "Show.S01E01.1080p.WEB-OTHER", "internal": False}},
            {"attributes": {"name": "Show.S01.1080p.WEB-zYz", "internal": True}},
        ]
        assert ie._pick_search_result(data, "-zYz")["internal"] is True
        assert ie._pick_search_result(data, "-KIMJI") is None  # wrong group: no blind first hit
        assert ie._pick_search_result(data, "")["name"].endswith("-OTHER")  # no tag: first hit
        assert ie._pick_search_result([], "-zYz") is None

    def test_lookup_internal_group(self):
        assert ie.lookup_internal_group("") == []
        assert ie.lookup_internal_group("-zYz") == [("TOS", 1)]  # TOS internals: 24h window
        assert ie.lookup_internal_group("-ZYZ") == [("TOS", 1)]  # case-insensitive
        assert ie.lookup_internal_group("-L0ST") == [("LST", 3)]  # LST internals: 3-day window
        assert ie.lookup_internal_group("-NTb") == []


def _run(meta: dict[str, Any]) -> tuple[str, str]:
    return asyncio.run(ie.check_internal_exclusivity(meta, CONFIG))


class TestOrchestrator:
    def _patch_fetch(self, monkeypatch: Any, attributes: Any, search_attributes: Any = None) -> list[tuple[str, str]]:
        calls: list[tuple[str, str]] = []

        async def fake_fetch(tracker: str, torrent_id: str, config: Any) -> Any:
            calls.append((tracker, torrent_id))
            return attributes

        async def fake_search(tracker: str, meta: Any, config: Any) -> Any:
            calls.append((tracker, "search"))
            return search_attributes

        monkeypatch.setattr(ie, "_fetch_origin_attributes", fake_fetch)
        monkeypatch.setattr(ie, "_search_origin_attributes", fake_search)
        return calls

    def test_blocked_on_confirmed_internal(self, monkeypatch: Any):
        fresh = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        self._patch_fetch(monkeypatch, {"internal": True, "created_at": fresh})
        verdict, reason = _run({"tag": "-zYz", "tos": "123"})
        assert verdict == "blocked"
        assert "zYz" in reason and "TOS" in reason

    def test_blocked_on_permanent_internal(self, monkeypatch: Any):
        monkeypatch.setitem(ie.INTERNAL_GROUPS, "TOS", {"zyz": None})
        self._patch_fetch(monkeypatch, {"internal": True, "created_at": "2020-01-01T00:00:00.000000Z"})
        verdict, reason = _run({"tag": "-zYz", "tos": "123"})
        assert verdict == "blocked"
        assert "permanent" in reason

    def test_clear_when_api_says_not_internal(self, monkeypatch: Any):
        self._patch_fetch(monkeypatch, {"internal": False})
        assert _run({"tag": "-zYz", "tos": "123"})[0] == "clear"

    def test_clear_when_window_expired(self, monkeypatch: Any):
        monkeypatch.setitem(ie.INTERNAL_GROUPS, "TOS", {"zyz": 30})
        self._patch_fetch(monkeypatch, {"internal": True, "created_at": "2020-01-01T00:00:00.000000Z"})
        assert _run({"tag": "-zYz", "tos": "123"})[0] == "clear"

    def test_no_origin_id_falls_back_to_search(self, monkeypatch: Any):
        fresh = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        calls = self._patch_fetch(monkeypatch, None, search_attributes={"internal": True, "created_at": fresh})
        verdict, _reason = _run({"tag": "-zYz"})
        assert verdict == "blocked"
        assert calls == [("TOS", "search")]

    def test_search_says_not_internal(self, monkeypatch: Any):
        self._patch_fetch(monkeypatch, None, search_attributes={"internal": False})
        assert _run({"tag": "-zYz"})[0] == "clear"

    def test_warn_when_origin_unfindable(self, monkeypatch: Any):
        calls = self._patch_fetch(monkeypatch, None, search_attributes=None)
        verdict, reason = _run({"tag": "-zYz"})
        assert verdict == "warn"
        assert "zYz" in reason
        assert calls == [("TOS", "search")]

    def test_warn_on_fetch_failure(self, monkeypatch: Any):
        self._patch_fetch(monkeypatch, None, search_attributes=None)
        assert _run({"tag": "-zYz", "tos": "123"})[0] == "warn"

    def test_clear_on_empty_or_unknown_tag(self, monkeypatch: Any):
        calls = self._patch_fetch(monkeypatch, {"internal": True})
        assert _run({"tag": ""})[0] == "clear"
        assert _run({"tag": "-NTb"})[0] == "clear"
        assert calls == []


def test_table_trackers_are_wired() -> None:
    from src.trackersetup import tracker_class_map

    with open(os.path.join(BASE, "src/prep.py"), encoding="utf-8") as f:
        prep_match = re.search(r"tracker_ids = (\[[^\]]*\])", f.read())
    assert prep_match
    prep_ids = set(ast.literal_eval(prep_match.group(1)))

    for tracker in ie.INTERNAL_GROUPS:
        assert tracker in tracker_class_map, f"{tracker} not in tracker_class_map"
        assert tracker.lower() in prep_ids, f"{tracker.lower()} missing from prep.py tracker_ids"


class TestDestinationBans:
    def _patch_fetch(self, monkeypatch: Any, attributes: Any, search_attributes: Any = None) -> list[tuple[str, str]]:
        calls: list[tuple[str, str]] = []

        async def fake_fetch(tracker: str, torrent_id: str, config: Any) -> Any:
            calls.append((tracker, torrent_id))
            return attributes

        async def fake_search(tracker: str, meta: Any, config: Any) -> Any:
            calls.append((tracker, "search"))
            return search_attributes

        monkeypatch.setattr(ie, "_fetch_origin_attributes", fake_fetch)
        monkeypatch.setattr(ie, "_search_origin_attributes", fake_search)
        return calls

    def _run(self, meta: dict[str, Any]) -> list[tuple[str, str]]:
        return asyncio.run(ie.check_internal_destination_bans(meta, CONFIG))

    def test_acm_internal_bans_tl(self, monkeypatch: Any):
        self._patch_fetch(monkeypatch, {"internal": 1})
        bans = self._run({"acm": "77", "trackers": ["TL", "LST"]})
        assert [d for d, _ in bans] == ["TL"]
        assert "ACM" in bans[0][1]

    def test_not_internal_no_ban(self, monkeypatch: Any):
        self._patch_fetch(monkeypatch, {"internal": False})
        assert self._run({"acm": "77", "trackers": ["TL"]}) == []

    def test_known_group_without_id_triggers_search(self, monkeypatch: Any):
        calls = self._patch_fetch(monkeypatch, None, search_attributes={"internal": 1})
        bans = self._run({"tag": "-iZON3", "trackers": ["TL"]})
        assert [d for d, _ in bans] == ["TL"]
        assert calls == [("ACM", "search")]

    def test_unknown_group_without_id_no_ban(self, monkeypatch: Any):
        calls = self._patch_fetch(monkeypatch, None, search_attributes={"internal": 1})
        assert self._run({"tag": "-NTb", "trackers": ["TL"]}) == []
        assert calls == []

    def test_banned_destination_not_targeted(self, monkeypatch: Any):
        calls = self._patch_fetch(monkeypatch, {"internal": 1})
        assert self._run({"acm": "77", "tag": "-iZON3", "trackers": ["LST"]}) == []
        assert calls == []  # no API call when no targeted destination is at risk
