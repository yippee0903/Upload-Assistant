"""Zipline upload: v3 returns URL strings, v4 returns {"url": ...} objects."""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src import uploadscreens


def _upload(tmp_path: Any, payload: dict[str, Any]) -> dict[str, Any]:
    image = tmp_path / "shot-1.png"
    image.write_bytes(b"\x89PNG")
    response = MagicMock(status_code=200)
    response.json.return_value = payload
    client = MagicMock()
    client.post = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    config = {"DEFAULT": {"zipline_url": "https://z.example/api/upload", "zipline_api_key": "k"}}
    with patch("src.uploadscreens.httpx.AsyncClient", return_value=client):
        return asyncio.run(uploadscreens.upload_image_task((str(image), "zipline", config, {"debug": False})))


@pytest.mark.parametrize("files", [["https://z.example/u/abc.png"], [{"url": "https://z.example/u/abc.png", "id": "x"}]])
def test_zipline_accepts_string_and_object_entries(tmp_path: Any, files: list[Any]) -> None:
    result = _upload(tmp_path, {"files": files})
    assert result["status"] == "success"
    assert result["raw_url"] == "https://z.example/r/abc.png"


def test_zipline_missing_url_is_a_failure(tmp_path: Any) -> None:
    assert _upload(tmp_path, {"files": [{"id": "x"}]})["status"] == "failed"
    assert _upload(tmp_path, {})["status"] == "failed"
