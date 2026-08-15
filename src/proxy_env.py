import os
from typing import Any, Optional
from urllib.parse import urlsplit
from urllib.request import getproxies, proxy_bypass

from src.console import console

_ALLOWED_SCHEMES = ("http", "https")


def apply_proxy_env(config: dict[str, Any]) -> None:
    """Export the configured proxy as standard proxy environment variables.

    httpx and requests pick these up when creating clients, so every
    tracker/image-host request is routed through the proxy without
    per-callsite changes. Explicit environment variables set by the user win
    over the config values. Invalid proxy URLs are rejected with a warning
    instead of being exported.
    """
    default = config.get("DEFAULT", {}) if isinstance(config.get("DEFAULT"), dict) else {}
    proxy_url = str(default.get("proxy_url") or "").strip()
    if not proxy_url:
        return
    parts = urlsplit(proxy_url)
    if parts.scheme not in _ALLOWED_SCHEMES or not parts.hostname:
        console.print(f"[bold red]Ignoring invalid proxy_url {proxy_url!r}: expected http(s)://host[:port][/bold red]")
        return
    for var in ("HTTP_PROXY", "HTTPS_PROXY"):
        os.environ.setdefault(var, proxy_url)
    no_proxy = str(default.get("proxy_bypass") or "").strip() or "localhost,127.0.0.1"
    os.environ.setdefault("NO_PROXY", no_proxy)


def proxy_for(url: str) -> Optional[str]:
    """Proxy to use for ``url`` per HTTP(S)_PROXY/NO_PROXY, or None for direct.

    For aiohttp call sites: pass the result as the request's ``proxy=`` so
    proxy routing works without ``trust_env`` (which would also enable
    automatic .netrc credential lookup for arbitrary target hosts).
    """
    parts = urlsplit(url)
    if not parts.hostname or proxy_bypass(parts.hostname):
        return None
    return getproxies().get(parts.scheme or "https")
