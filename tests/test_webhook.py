# Tests for src/webhook.py — Discord-compatible webhook embed notifications
import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from src.webhook import EMBED_COLOR, MAX_FIELD_LENGTH, send_webhook_notification


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _mock_client(post_mock: AsyncMock) -> MagicMock:
    """Async-context-manager httpx.AsyncClient whose .post is post_mock."""
    client = MagicMock()
    client.post = post_mock
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


class TestSendWebhookNotification:
    def test_posts_embed_payload(self):
        post = AsyncMock(return_value=MagicMock(status_code=204))
        with patch("src.webhook.httpx.AsyncClient", return_value=_mock_client(post)):
            _run(send_webhook_notification("https://discord.test/webhook", "Uploadé", {"Title": "X", "Path": "/media/X"}))
        url_arg = post.await_args.args[0]
        payload = post.await_args.kwargs["json"]
        assert url_arg == "https://discord.test/webhook"
        embed = payload["embeds"][0]
        assert embed["title"] == "Uploadé"
        assert embed["color"] == EMBED_COLOR
        assert "timestamp" in embed
        assert embed["fields"] == [{"name": "Title", "value": "X"}, {"name": "Path", "value": "/media/X"}]

    def test_empty_fields_are_omitted(self):
        post = AsyncMock(return_value=MagicMock(status_code=204))
        with patch("src.webhook.httpx.AsyncClient", return_value=_mock_client(post)):
            _run(send_webhook_notification("https://discord.test/webhook", "Uploadé", {"Title": "X", "Size": ""}))
        fields = post.await_args.kwargs["json"]["embeds"][0]["fields"]
        assert fields == [{"name": "Title", "value": "X"}]

    def test_truncates_field_values_to_discord_limit(self):
        post = AsyncMock(return_value=MagicMock(status_code=204))
        with patch("src.webhook.httpx.AsyncClient", return_value=_mock_client(post)):
            _run(send_webhook_notification("https://discord.test/webhook", "Uploadé", {"Trackers": "x" * 5000}))
        sent = post.await_args.kwargs["json"]["embeds"][0]["fields"][0]["value"]
        assert len(sent) == MAX_FIELD_LENGTH

    def test_network_error_does_not_raise(self):
        post = AsyncMock(side_effect=ConnectionError("boom"))
        with patch("src.webhook.httpx.AsyncClient", return_value=_mock_client(post)):
            _run(send_webhook_notification("https://discord.test/webhook", "Uploadé", {"Title": "X"}))
