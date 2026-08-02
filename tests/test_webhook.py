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

    def test_non_2xx_response_is_logged_as_failure(self):
        response = MagicMock(status_code=404)
        response.raise_for_status.side_effect = RuntimeError("404 for url https://discord.test/webhook/SECRET")
        post = AsyncMock(return_value=response)
        with patch("src.webhook.httpx.AsyncClient", return_value=_mock_client(post)), patch("src.webhook.console.print") as console_print:
            _run(send_webhook_notification("https://discord.test/webhook/SECRET", "Uploadé", {"Title": "X"}))
        logged = " ".join(str(c.args[0]) for c in console_print.call_args_list)
        assert "Failed to send webhook notification" in logged

    def test_error_log_never_leaks_webhook_url(self):
        """The webhook URL embeds a secret token: it must not reach the logs."""
        sentinel = "tok3n-s3cr3t"
        url = f"https://discord.test/webhook/{sentinel}"
        post = AsyncMock(side_effect=ConnectionError(f"cannot reach {url}"))
        with patch("src.webhook.httpx.AsyncClient", return_value=_mock_client(post)), patch("src.webhook.console.print") as console_print:
            _run(send_webhook_notification(url, "Uploadé", {"Title": "X"}))
        logged = " ".join(str(c.args[0]) for c in console_print.call_args_list)
        assert "ConnectionError" in logged
        assert sentinel not in logged
