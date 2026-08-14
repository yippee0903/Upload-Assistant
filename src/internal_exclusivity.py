# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
#
# Guard against re-uploading internal releases. Internal groups are exclusive
# to their ORIGIN tracker (the one the file was downloaded from), whose rules
# forbid reposting them elsewhere — permanently or for a time window. The
# check combines the hard-coded table below with the origin tracker's API
# `internal` flag when the source torrent ID is known from the client.

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
    "LST": {group.lower(): 3 for group in ("L0ST", "KIMJI", "coffee", "SQS", "Yuki")},
}


# Origin tracker -> destinations its internal releases must never be uploaded
# to. Detection is API-flag only (no group table needed): when the origin
# torrent is known from the client and flagged internal, the destination is
# dropped from the upload targets.
INTERNAL_DESTINATION_BANS: dict[str, frozenset[str]] = {
    "ACM": frozenset({"TL"}),
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


def lookup_internal_group(tag: str) -> list[tuple[str, Optional[int]]]:
    group = tag.lstrip("-").lower()
    if not group:
        return []
    return [(tracker, groups[group]) for tracker, groups in INTERNAL_GROUPS.items() if group in groups]


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


async def check_internal_exclusivity(meta: dict[str, Any], config: dict[str, Any]) -> tuple[str, str]:
    """Returns (verdict, reason) with verdict in {"blocked", "warn", "clear"}."""
    tag = str(meta.get("tag") or "")
    candidates = lookup_internal_group(tag)
    if not candidates:
        return "clear", ""

    group = tag.lstrip("-")
    warn_trackers: list[str] = []
    for tracker, days in candidates:
        torrent_id = meta.get(tracker.lower())
        if torrent_id is None:
            warn_trackers.append(tracker)
            continue
        attributes = await _fetch_origin_attributes(tracker, str(torrent_id), config)
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
    for origin, destinations in INTERNAL_DESTINATION_BANS.items():
        at_risk = destinations & targets
        torrent_id = meta.get(origin.lower())
        if not at_risk or torrent_id is None:
            continue
        attributes = await _fetch_origin_attributes(origin, str(torrent_id), config)
        if attributes and attributes.get("internal"):
            reason = f"internal release on {origin}, which forbids uploading its internals there"
            bans.extend((destination, reason) for destination in sorted(at_risk))
    return bans
