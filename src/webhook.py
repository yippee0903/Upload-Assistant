# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from datetime import datetime, timezone

import httpx

from src.console import console

EMBED_COLOR = 10613286
# Discord rejects embed field values over 1024 characters
MAX_FIELD_LENGTH = 1024


async def send_webhook_notification(url: str, title: str, fields: dict[str, str], debug: bool = False) -> None:
    """POST a Discord-compatible embed payload to a webhook URL. Never raises."""
    payload = {
        "embeds": [
            {
                "title": title,
                "color": EMBED_COLOR,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "fields": [{"name": name, "value": value[:MAX_FIELD_LENGTH]} for name, value in fields.items() if value],
            }
        ]
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            if debug:
                console.print(f"[cyan]Webhook notification response: {response.status_code}")
    except Exception as e:
        # Log only the exception type: the webhook URL embeds a secret token
        # and must never leak into logs via the exception message.
        console.print(f"[red]Failed to send webhook notification: {type(e).__name__}")
