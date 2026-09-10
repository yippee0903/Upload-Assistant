"""freeimage.host upload: Chevereto v1 API, key in the form body."""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from src import uploadscreens

IMAGE = {
    "url": "https://iili.io/abc.png",
    "url_viewer": "https://freeimage.host/i/abc",
    "medium": {"url": "https://iili.io/abc.md.png"},
}


def _upload(tmp_path: Any, payload: dict[str, Any], status_code: int = 200) -> tuple[dict[str, Any], MagicMock]:
    image = tmp_path / "shot-1.png"
    image.write_bytes(b"\x89PNG")
    response = MagicMock(status_code=status_code)
    response.json.return_value = payload
    client = MagicMock()
    client.post = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    config = {"DEFAULT": {"freeimage_api": "k"}}
    with patch("src.uploadscreens.httpx.AsyncClient", return_value=client):
        result = asyncio.run(uploadscreens.upload_image_task((str(image), "freeimage", config, {"debug": False})))
    return result, client


def test_freeimage_success_uses_medium_thumbnail(tmp_path: Any) -> None:
    result, client = _upload(tmp_path, {"status_code": 200, "image": IMAGE})
    assert result["status"] == "success"
    assert (result["img_url"], result["raw_url"], result["web_url"]) == (IMAGE["medium"]["url"], IMAGE["url"], IMAGE["url_viewer"])
    kwargs = client.post.call_args.kwargs
    assert client.post.call_args.args[0] == "https://freeimage.host/api/1/upload"
    assert kwargs["data"]["key"] == "k"
    assert "source" in kwargs["files"]


def test_freeimage_falls_back_to_full_image_without_medium(tmp_path: Any) -> None:
    image = {k: v for k, v in IMAGE.items() if k != "medium"}
    result, _ = _upload(tmp_path, {"status_code": 200, "image": image})
    assert result["status"] == "success"
    assert result["img_url"] == IMAGE["url"]


def test_freeimage_failures(tmp_path: Any) -> None:
    assert _upload(tmp_path, {"status_code": 400, "error": {"message": "bad key"}}, status_code=400)[0]["status"] == "failed"
    assert _upload(tmp_path, {"status_code": 200})[0]["status"] == "failed"
