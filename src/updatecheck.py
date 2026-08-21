"""Cache for the remote version check so every run doesn't pay a network round-trip."""

import contextlib
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Optional

RemoteVersion = tuple[Optional[str], Optional[str]]


def cached_remote_version(cache_path: str, cache_hours: float, fetch: Callable[[], RemoteVersion]) -> RemoteVersion:
    """Return (version, content) from cache_path when younger than cache_hours, else fetch() and cache it."""
    try:
        cached = json.loads(Path(cache_path).read_text(encoding="utf-8"))
        if time.time() - float(cached["checked_at"]) < cache_hours * 3600:
            return str(cached["remote_version"]), str(cached["remote_content"])
    except (OSError, ValueError, KeyError, TypeError):
        pass
    remote_version, remote_content = fetch()
    if remote_version and remote_content:
        with contextlib.suppress(OSError):
            Path(cache_path).write_text(json.dumps({"checked_at": time.time(), "remote_version": remote_version, "remote_content": remote_content}), encoding="utf-8")
    return remote_version, remote_content
