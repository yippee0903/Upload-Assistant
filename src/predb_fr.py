# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Optional cross-check of French uploads against the predb.fr database.

predb.fr (https://predb.fr) indexes French scene & P2P releases.  When a
``predb_fr_api_key`` is configured, French trackers cross-check the data they
are about to submit (TMDB id, release group, nuke status, NFO availability)
and print warnings on divergence.

This is purely informational: **no match is never a reason to abort an
upload** — the FR pre database is incomplete and your own encode may simply
not be indexed.
"""

from typing import Any, Optional

import httpx

from src.console import console

API_URL = "https://api.predb.fr/api/v1/releases"


def _tmdb_from_media_id(media_id: Optional[str]) -> Optional[int]:
    """``"movie:207"`` / ``"tv:72879"`` -> ``207`` / ``72879`` (or None)."""
    if not media_id or ":" not in str(media_id):
        return None
    try:
        return int(str(media_id).split(":", 1)[1])
    except ValueError:
        return None


def _norm_group(tag: Any) -> str:
    """Normalise a group tag for comparison: ``"-T4KT"`` -> ``"t4kt"``."""
    return str(tag or "").lstrip("-").strip().lower()


def analyze(
    releases: list[dict[str, Any]],
    *,
    tmdb_id: Any,
    group: Any,
    category: Any,
    have_nfo: bool,
) -> list[str]:
    """Compare predb candidates to our submission and return warning lines.

    Pure function (no network) so it can be unit-tested directly.
    Returns an empty list when nothing relevant is found — callers treat an
    empty list as "all good / not indexed", never as a failure.
    """
    want_categ = "Series" if str(category).upper() == "TV" else "Movies"
    cands = [r for r in releases if r.get("categ") in (want_categ, "Anime")]
    if not cands:
        return []

    warnings: list[str] = []
    group_n = _norm_group(group)
    ours = [r for r in cands if group_n and _norm_group(r.get("team_name")) == group_n]

    # TMDB sanity: if candidates converge on TMDB id(s) that exclude ours.
    tmdb_ids = {t for r in cands if (t := _tmdb_from_media_id(r.get("media_id"))) is not None}
    try:
        our_tmdb = int(tmdb_id) if tmdb_id else 0
    except (TypeError, ValueError):
        our_tmdb = 0
    if our_tmdb and tmdb_ids and our_tmdb not in tmdb_ids:
        warnings.append(f"TMDB possiblement erroné : tu soumets {our_tmdb}, predb.fr référence {sorted(tmdb_ids)} pour ce titre.")

    # Nuke / reputation / NFO only reported for same-group candidates to avoid noise.
    warnings.extend(f"Release nukée côté FR : {r['name']} — {r['nuke_reason']}" for r in ours if r.get("nuke_reason"))
    if ours and not any(r.get("team_profilarr_validated") for r in ours):
        warnings.append(f"Groupe {group} non validé profilarr sur predb.fr.")
    nfo_avail = next((r for r in ours if r.get("has_nfo")), None)
    if nfo_avail and not have_nfo:
        # ponytail: report availability only; downloading the canonical NFO
        # (GET /releases/nfo, like is_scene.py does for SRRDB) is the next step.
        warnings.append(f"NFO disponible sur predb.fr : {nfo_avail['name']}")

    return warnings


async def crosscheck(meta: dict[str, Any], config: dict[str, Any], tracker: str) -> None:
    """Query predb.fr for the current upload and print any divergence warnings.

    Opt-in: does nothing unless ``DEFAULT.predb_fr_api_key`` is set.  Never
    raises and never aborts the upload.
    """
    key = str(config.get("DEFAULT", {}).get("predb_fr_api_key", "")).strip()
    if not key:
        return

    title = str(meta.get("title", "")).strip()
    if not title:
        return
    year = meta.get("year") or ""
    query = ".".join(f"{title} {year}".split())

    # One request per title, shared across all French trackers in this upload.
    cache = meta.setdefault("_predb_fr_cache", {})
    if query in cache:
        releases = cache[query]
    else:
        releases = []
        try:
            async with httpx.AsyncClient() as client:
                # Key sent as a header (not a query param) so it never lands in
                # URLs, logs, or httpx exception messages.
                resp = await client.get(
                    API_URL,
                    params={"q": query, "limit": 50},
                    headers={"X-Api-Key": key},
                    timeout=15.0,
                )
            if resp.status_code == 200:
                releases = resp.json().get("releases", [])
            elif meta.get("debug"):
                console.print(f"[yellow]predb.fr: HTTP {resp.status_code} pour '{query}'")
        except Exception as e:
            if meta.get("debug"):
                console.print(f"[yellow]predb.fr: requête échouée: {type(e).__name__}")
        cache[query] = releases

    if not releases:
        return  # not indexed → stay silent, never block the upload

    warnings = analyze(
        releases,
        tmdb_id=meta.get("tmdb_id") or meta.get("tmdb"),
        group=meta.get("tag"),
        category=meta.get("category"),
        have_nfo=bool(meta.get("nfo")),
    )
    for w in warnings:
        console.print(f"[yellow]⚠️  predb.fr [{tracker}] : {w}")
