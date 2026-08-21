"""postimages.org upload: form fields sent and XML links parsed."""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from src import uploadscreens

XML = """<?xml version="1.0" encoding="utf-8"?>
<data success="1" status="200">
  <links>
    <page>https://postimg.cc/abc123</page>
    <hotlink>https://i.postimg.cc/abc123/shot-1.png</hotlink>
    <thumbnail>https://i.postimg.cc/th/abc123.png</thumbnail>
  </links>
</data>"""


def _upload(tmp_path: Any, body: str, status: int = 200, key: str = "k") -> tuple[dict[str, Any], MagicMock]:
    image = tmp_path / "shot-1.png"
    image.write_bytes(b"\x89PNG")
    response = MagicMock(status_code=status, text=body)
    client = MagicMock()
    client.post = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    config = {"DEFAULT": {"postimg_api": key}}
    with patch("src.uploadscreens.httpx.AsyncClient", return_value=client):
        result = asyncio.run(uploadscreens.upload_image_task((str(image), "postimg", config, {"debug": False})))
    return result, client.post


def test_success_parses_links_and_sends_key(tmp_path):
    result, post = _upload(tmp_path, XML)
    assert result["status"] == "success"
    assert result["raw_url"] == "https://i.postimg.cc/abc123/shot-1.png"
    assert result["img_url"] == "https://i.postimg.cc/th/abc123.png"
    assert result["web_url"] == "https://postimg.cc/abc123"
    data = post.call_args.kwargs["data"]
    assert post.call_args.args[0] == "https://api.postimage.org/1/upload"
    assert data["key"] == "k" and data["type"] == "png" and data["image"] == "iVBORw=="


def test_missing_hotlink_fails(tmp_path):
    result, _ = _upload(tmp_path, "<data success='0'><error>bad key</error></data>")
    assert result["status"] == "failed"


def test_missing_key_fails_without_request(tmp_path):
    result, post = _upload(tmp_path, XML, key="")
    assert result["status"] == "failed"
    post.assert_not_awaited()
