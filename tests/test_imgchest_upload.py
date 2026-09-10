"""imgchest upload: one hidden post per screenshot, no thumbnail (the CDN one is a square crop)."""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from src import uploadscreens

POST = {"data": {"id": "p0st1d", "images": [{"id": "f1le1d", "link": "https://cdn.imgchest.com/files/f1le1d.png"}]}}


def _upload(tmp_path: Any, payload: dict[str, Any], status_code: int = 200) -> tuple[dict[str, Any], MagicMock]:
    image = tmp_path / "shot-1.png"
    image.write_bytes(b"\x89PNG")
    response = MagicMock(status_code=status_code)
    response.json.return_value = payload
    client = MagicMock()
    client.post = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    config = {"DEFAULT": {"imgchest_api": "k"}}
    with patch("src.uploadscreens.httpx.AsyncClient", return_value=client):
        result = asyncio.run(uploadscreens.upload_image_task((str(image), "imgchest", config, {"debug": False})))
    return result, client


def test_imgchest_success(tmp_path: Any) -> None:
    result, client = _upload(tmp_path, POST)
    assert result["status"] == "success"
    assert result["raw_url"] == "https://cdn.imgchest.com/files/f1le1d.png"
    assert result["img_url"] == result["raw_url"]
    assert result["web_url"] == "https://imgchest.com/p/p0st1d"
    args, kwargs = client.post.call_args
    assert args[0] == "https://api.imgchest.com/v1/post"
    assert kwargs["headers"]["Authorization"] == "Bearer k"
    assert kwargs["data"]["privacy"] == "hidden"
    assert "images[]" in kwargs["files"]


def test_imgchest_failures(tmp_path: Any) -> None:
    assert _upload(tmp_path, {"message": "Unauthenticated."}, status_code=401)[0]["status"] == "failed"
    assert _upload(tmp_path, {"data": {"id": "p0st1d", "images": []}})[0]["status"] == "failed"
