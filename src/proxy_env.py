import os
from typing import Any


def apply_proxy_env(config: dict[str, Any]) -> None:
    """Export the configured proxy as standard proxy environment variables.

    httpx, requests and aiohttp sessions created with trust_env pick these up,
    so every tracker/image-host request is routed through the proxy without
    per-callsite changes. Explicit environment variables set by the user win
    over the config values.
    """
    default = config.get("DEFAULT", {}) if isinstance(config.get("DEFAULT"), dict) else {}
    proxy_url = str(default.get("proxy_url") or "").strip()
    if not proxy_url:
        return
    for var in ("HTTP_PROXY", "HTTPS_PROXY"):
        os.environ.setdefault(var, proxy_url)
    proxy_bypass = str(default.get("proxy_bypass") or "").strip() or "localhost,127.0.0.1"
    os.environ.setdefault("NO_PROXY", proxy_bypass)
