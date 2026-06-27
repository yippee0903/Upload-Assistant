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

import glob
import os
from pathlib import Path
from typing import Any, Optional

import httpx

from src.console import console

API_URL = "https://api.predb.fr/api/v1/releases"
NFO_URL = "https://api.predb.fr/api/v1/releases/nfo"


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


_VIDEO_EXTS = {".mkv", ".mp4", ".ts", ".m2ts", ".avi", ".vob"}


def _strip_video_ext(name: str) -> str:
    """Drop a trailing video extension predb sometimes keeps in the name."""
    root, ext = os.path.splitext(name)
    return root if ext.lower() in _VIDEO_EXTS else name


def analyze(
    releases: list[dict[str, Any]],
    *,
    tmdb_id: Any,
    group: Any,
    category: Any,
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

    # Nuke / reputation only reported for same-group candidates to avoid noise.
    warnings.extend(f"Release nukée côté FR : {r['name']} — {r['nuke_reason']}" for r in ours if r.get("nuke_reason"))
    if ours and not any(r.get("team_profilarr_validated") for r in ours):
        warnings.append(f"Groupe {group} non validé profilarr sur predb.fr.")

    return warnings


def pick_exact_nfo(releases: list[dict[str, Any]], our_name: str) -> Optional[dict[str, Any]]:
    """Return the predb release whose name *exactly* matches our release.

    Exact match (case-insensitive, ignoring a trailing video extension on
    either side) means it is literally the same release, so its canonical NFO
    legitimately describes our file.  Only returns candidates that have an NFO.
    Pure function — unit-testable without network.
    """
    if not our_name:
        return None
    want = _strip_video_ext(our_name).strip().lower()
    if not want:
        return None
    for r in releases:
        if r.get("has_nfo") and _strip_video_ext(str(r.get("name", ""))).strip().lower() == want:
            return r
    return None


def _safe_nfo_filename(name: str) -> str:
    """Map an (external) release name to a filename that cannot escape its
    directory. Returns '' for names that resolve to nothing usable."""
    base = os.path.basename(str(name).replace("\\", "/")).strip()
    return "" if base in ("", ".", "..") else f"{base}.nfo"


def _has_disk_nfo(path: str) -> bool:
    """True when a physical .nfo sits next to the content (same rule as the
    French trackers' on-disk NFO inclusion)."""
    if not path:
        return False
    if os.path.isdir(path):
        return bool(glob.glob(os.path.join(path, "*.nfo")) or glob.glob(os.path.join(path, "**", "*.nfo"), recursive=True))
    return os.path.isfile(f"{os.path.splitext(path)[0]}.nfo")


def _our_release_name(meta: dict[str, Any]) -> str:
    """The source release name to match against predb (folder/file basename)."""
    path = str(meta.get("path", "")).rstrip("/")
    base = os.path.basename(path)
    if base and not os.path.isdir(path):
        base = os.path.splitext(base)[0]
    return base or str(meta.get("uuid", ""))


async def _fetch_nfo(name: str, source: str, key: str) -> Optional[str]:
    """Download the raw NFO for an exact release. None on any failure."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                NFO_URL,
                params={"name": name, "source": source},
                headers={"X-Api-Key": key},
                timeout=15.0,
            )
        if resp.status_code == 200 and resp.text.strip():
            return resp.text
    except Exception:
        return None
    return None


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

    if meta.get("debug"):
        console.print(f"[cyan]predb.fr [{tracker}]: '{query}' → {len(releases)} release(s)[/cyan]")

    if not releases:
        return  # not indexed → stay silent, never block the upload

    warnings = analyze(
        releases,
        tmdb_id=meta.get("tmdb_id") or meta.get("tmdb"),
        group=meta.get("tag"),
        category=meta.get("category"),
    )
    for w in warnings:
        console.print(f"[yellow]⚠️  predb.fr [{tracker}] : {w}")

    await _maybe_download_nfo(meta, releases, key)


async def _maybe_download_nfo(meta: dict[str, Any], releases: list[dict[str, Any]], key: str) -> None:
    """Fetch the canonical NFO only when there is no physical NFO on disk and
    an *exact* predb match exists.

    A physical NFO next to the content always wins (handled by the trackers'
    ``_get_nfo_files``); otherwise an exact match means it is the same release,
    so we prefer its canonical NFO over a MediaInfo-generated one.  No exact
    match → trackers fall back to the generated NFO as before.
    """
    debug = meta.get("debug")
    if meta.get("predb_fr_nfo_file"):
        return  # already fetched this upload
    if _has_disk_nfo(str(meta.get("path", ""))):
        if debug:
            console.print("[cyan]predb.fr: NFO physique présent sur disque → conservé[/cyan]")
        return  # physical NFO wins, no debate

    match = pick_exact_nfo(releases, _our_release_name(meta))
    if not match:
        if debug:
            console.print(f"[cyan]predb.fr: aucun match exact pour '{_our_release_name(meta)}' → NFO généré[/cyan]")
        return

    nfo_text = await _fetch_nfo(str(match["name"]), str(match.get("source", "P2P")), key)
    if not nfo_text:
        if debug:
            console.print(f"[yellow]predb.fr: téléchargement NFO échoué pour '{match['name']}'[/yellow]")
        return

    # Derive a safe filename from the (external) release name so it can never
    # escape tmp/<uuid>/ via path separators or traversal segments.
    safe_name = _safe_nfo_filename(str(match["name"]))
    if not safe_name:
        return
    dest = os.path.join(str(meta.get("base_dir", "")), "tmp", str(meta.get("uuid", "")), safe_name)
    try:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        Path(dest).write_text(nfo_text, encoding="utf-8")
    except OSError as e:
        if meta.get("debug"):
            console.print(f"[yellow]predb.fr: écriture NFO échouée: {type(e).__name__}")
        return

    meta["predb_fr_nfo_file"] = dest
    console.print(f"[green]predb.fr : NFO canonique récupéré ({match['name']})[/green]")
