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

    def test_lookup_internal_group(self):
        assert ie.lookup_internal_group("") == []
        assert ie.lookup_internal_group("-zYz") == [("TOS", 1)]  # TOS internals: 24h window
        assert ie.lookup_internal_group("-ZYZ") == [("TOS", 1)]  # case-insensitive
        assert ie.lookup_internal_group("-L0ST") == [("LST", 3)]  # LST internals: 3-day window
        assert ie.lookup_internal_group("-NTb") == []


def _run(meta: dict[str, Any]) -> tuple[str, str]:
    return asyncio.run(ie.check_internal_exclusivity(meta, CONFIG))


class TestOrchestrator:
    def _patch_fetch(self, monkeypatch: Any, attributes: Any) -> list[tuple[str, str]]:
        calls: list[tuple[str, str]] = []

        async def fake_fetch(tracker: str, torrent_id: str, config: Any) -> Any:
            calls.append((tracker, torrent_id))
            return attributes

        monkeypatch.setattr(ie, "_fetch_origin_attributes", fake_fetch)
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

    def test_warn_without_origin_id(self, monkeypatch: Any):
        calls = self._patch_fetch(monkeypatch, {"internal": True})
        verdict, reason = _run({"tag": "-zYz"})
        assert verdict == "warn"
        assert "zYz" in reason
        assert calls == []

    def test_warn_on_fetch_failure(self, monkeypatch: Any):
        self._patch_fetch(monkeypatch, None)
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
