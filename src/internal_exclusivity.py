# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
#
# Guard against re-uploading internal releases. Internal groups are exclusive
# to their ORIGIN tracker (the one the file was downloaded from), whose rules
# forbid reposting them elsewhere — permanently or for a time window. The
# check combines the hard-coded table below with the origin tracker's API
# `internal` flag when the source torrent ID is known from the client.

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from src.trackers.TOS import TOS

# Origin tracker -> {group (lowercase) -> exclusivity window in days, None = permanent}.
# This table is the single place where exclusivity durations are tuned; only
# groups whose rules are confirmed belong here. TOS internals are exclusive
# for 24 hours.
INTERNAL_GROUPS: dict[str, dict[str, Optional[int]]] = {
    "TOS": {group.lower(): 1 for group in TOS._TOS_INTERNAL_GROUPS},
    "LST": {group.lower(): 3 for group in ("L0ST", "KIMJI", "coffee", "SQS", "Yuki", "hallowed")},
    "HDT": {group.lower(): None for group in ("126811", "DownRev")},
    "IHD": {"flower": 1},
    "OE": {
        group.lower(): 3
        for group in (
            "BiNGUS",
            "Breeze",
            "DarQ",
            "DarQ HONE",
            "DBMS",
            "edge2020",
            "edwood",
            "Goki",
            "Goki(TAoE)",
            "GRiMM",
            "JBENT",
            "JBENT(TAoE)",
            "NOXXUS",
            "OnlyMux",
            "OnlyWeb",
            "PrimeX",
            "Ralphy",
            "sCOOTER",
            "Vialle",
            "WhiskeyJack",
        )
    },
}

# Origins without a queryable API (HDT marks internal releases only with a
# page icon, and its exclusives only with an uploader banner): a table match
# alone is authoritative — the tag blocks directly, without verification.
TABLE_ONLY_ORIGINS = frozenset({"HDT"})


# Origin tracker -> destinations its internal releases must never be uploaded
# to. Detection is API-flag only (no group table needed): when the origin
# torrent is identified (by client ID or by searching the origin tracker for
# a known internal group's release) and flagged internal, the destination is
# dropped from the upload targets.
INTERNAL_DESTINATION_BANS: dict[str, dict[str, frozenset[str]]] = {
    "ACM": {
        "destinations": frozenset({"TL"}),
        "groups": frozenset({"acm", "arin", "izon3", "kawairemux"}),
    },
}


def _parse_created_at(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def exclusivity_active(days: Optional[int], created_at: Optional[datetime], now: Optional[datetime] = None) -> bool:
    if days is None:
        return True
    if created_at is None:
        # Internal is confirmed but the window cannot be verified: stay safe.
        return True
    now = now or datetime.now(timezone.utc)
    return now - created_at < timedelta(days=days)


def _normalize_group(group: str) -> str:
    # Display names and file names write the same tag differently
    # ("DarQ HONE" vs "DarQ.HONE", "JBENT(TAoE)" vs "JBENT.TAoE"): compare on
    # alphanumerics only.
    return re.sub(r"[^a-z0-9]", "", group.lower())


def lookup_internal_group(tag: str) -> list[tuple[str, Optional[int]]]:
    group = _normalize_group(tag.lstrip("-"))
    if not group:
        return []
    return [(tracker, days) for tracker, groups in INTERNAL_GROUPS.items() for listed, days in groups.items() if _normalize_group(listed) == group]


async def _fetch_origin_attributes(tracker: str, torrent_id: str, config: dict[str, Any]) -> Optional[dict[str, Any]]:
    from src.trackersetup import tracker_class_map

    api_key = str(config.get("TRACKERS", {}).get(tracker, {}).get("api_key") or "").strip()
    if not api_key:
        return None
    try:
        instance = tracker_class_map[tracker](config=config)
        url = f"{instance.id_url}{torrent_id}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url=url, params={"api_token": api_key}, headers={"Authorization": f"Bearer {api_key}"})
            json_response = response.json()
    except (httpx.RequestError, httpx.TimeoutException, ValueError, KeyError):
        return None
    if not isinstance(json_response, dict):
        return None
    # By-id responses carry attributes at the root or nested under "data".
    data: Any = json_response.get("data", json_response)
    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict):
        return None
    attributes = data.get("attributes")
    return attributes if isinstance(attributes, dict) else None


def _search_term(meta: dict[str, Any]) -> str:
    filelist = meta.get("filelist") or []
    if filelist:
        return os.path.basename(str(filelist[0]))
    return str(meta.get("uuid") or "")


async def _search_origin_attributes(tracker: str, meta: dict[str, Any], config: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Search the origin tracker by file name when no torrent ID is known."""
    from src.trackersetup import tracker_class_map

    api_key = str(config.get("TRACKERS", {}).get(tracker, {}).get("api_key") or "").strip()
    file_name = _search_term(meta)
    if not api_key or not file_name:
        return None
    try:
        instance = tracker_class_map[tracker](config=config)
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                url=instance.search_url,
                params={"api_token": api_key, "file_name": file_name},
                headers={"Authorization": f"Bearer {api_key}"},
            )
            json_response = response.json()
    except (httpx.RequestError, httpx.TimeoutException, ValueError, KeyError, AttributeError):
        return None
    data = json_response.get("data") if isinstance(json_response, dict) else None
    if not isinstance(data, list):
        return None
    return _pick_search_result(data, str(meta.get("tag") or ""))


def _pick_search_result(data: list[Any], tag: str) -> Optional[dict[str, Any]]:
    # A file-name search can match several torrents carrying the same file
    # (e.g. a single episode and a season pack): only trust a hit whose
    # release name ends with the group we are checking.
    group = tag.lstrip("-").lower()
    for item in data:
        attributes = item.get("attributes") if isinstance(item, dict) else None
        if not isinstance(attributes, dict):
            continue
        name = str(attributes.get("name") or "").lower()
        if not group or name.endswith(f"-{group}"):
            return attributes
    return None


async def _origin_attributes(tracker: str, meta: dict[str, Any], config: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Best effort: fetch by known torrent ID, else search by file name."""
    torrent_id = meta.get(tracker.lower())
    if torrent_id is not None:
        attributes = await _fetch_origin_attributes(tracker, str(torrent_id), config)
        if attributes is not None:
            return attributes
    return await _search_origin_attributes(tracker, meta, config)


async def check_internal_exclusivity(meta: dict[str, Any], config: dict[str, Any]) -> tuple[str, str]:
    """Returns (verdict, reason) with verdict in {"blocked", "warn", "clear"}."""
    tag = str(meta.get("tag") or "")
    candidates = lookup_internal_group(tag)
    if not candidates:
        return "clear", ""

    group = tag.lstrip("-")
    warn_trackers: list[str] = []
    for tracker, days in candidates:
        if tracker in TABLE_ONLY_ORIGINS:
            # No API to consult: the table itself is the evidence. With a
            # timed window the upload date is unknowable, so it stays active.
            if exclusivity_active(days, None):
                window = "permanent exclusivity" if days is None else f"{days}-day exclusivity"
                return "blocked", f"{group} is an exclusive group on {tracker} ({window})"
            continue
        attributes = await _origin_attributes(tracker, meta, config)
        if attributes is None:
            warn_trackers.append(tracker)
            continue
        if not attributes.get("internal"):
            # The origin tracker's API is authoritative for this torrent.
            continue
        created_at = _parse_created_at(attributes.get("created_at"))
        if exclusivity_active(days, created_at):
            window = "permanent exclusivity" if days is None else f"{days}-day exclusivity"
            uploaded = f", uploaded {created_at.date().isoformat()}" if created_at else ""
            return "blocked", f"{group} is an internal group on {tracker} ({window}{uploaded})"

    if warn_trackers:
        return "warn", f"{group} is listed as an internal group on {', '.join(warn_trackers)} but the origin could not be verified"
    return "clear", ""


async def check_internal_destination_bans(meta: dict[str, Any], config: dict[str, Any]) -> list[tuple[str, str]]:
    """Returns [(destination, reason)] for targeted destinations that must be dropped."""
    targets = {str(t).upper() for t in meta.get("trackers") or []}
    bans: list[tuple[str, str]] = []
    tag_group = str(meta.get("tag") or "").lstrip("-").lower()
    for origin, rule in INTERNAL_DESTINATION_BANS.items():
        at_risk = rule["destinations"] & targets
        if not at_risk:
            continue
        origin_id_known = meta.get(origin.lower()) is not None
        group_is_listed = _normalize_group(tag_group) in {_normalize_group(g) for g in rule["groups"]}
        if not origin_id_known and not group_is_listed:
            continue
        attributes = await _origin_attributes(origin, meta, config)
        if attributes and attributes.get("internal"):
            reason = f"internal release on {origin}, which forbids uploading its internals there"
            bans.extend((destination, reason) for destination in sorted(at_risk))
    return bans
