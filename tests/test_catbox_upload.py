"""catbox.moe upload: plain-text URL response, userhash required, no thumbnail."""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from src import uploadscreens

URL = "https://files.catbox.moe/abc123.png"


def _upload(tmp_path: Any, body: str, status_code: int = 200, userhash: str = "h") -> tuple[dict[str, Any], MagicMock]:
    image = tmp_path / "shot-1.png"
    image.write_bytes(b"\x89PNG")
    response = MagicMock(status_code=status_code, text=body)
    client = MagicMock()
    client.post = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    config = {"DEFAULT": {"catbox_userhash": userhash}}
    with patch("src.uploadscreens.httpx.AsyncClient", return_value=client):
        result = asyncio.run(uploadscreens.upload_image_task((str(image), "catbox", config, {"debug": False})))
    return result, client


def test_catbox_success_uses_the_full_image_everywhere(tmp_path: Any) -> None:
    result, client = _upload(tmp_path, URL + "\n")
    assert result["status"] == "success"
    assert (result["img_url"], result["raw_url"], result["web_url"]) == (URL, URL, URL)
    args, kwargs = client.post.call_args
    assert args[0] == "https://catbox.moe/user/api.php"
    assert kwargs["data"] == {"reqtype": "fileupload", "userhash": "h"}
    assert "fileToUpload" in kwargs["files"]


def test_catbox_failures(tmp_path: Any) -> None:
    assert _upload(tmp_path, "Something went wrong.", status_code=412)[0]["status"] == "failed"
    assert _upload(tmp_path, "<html>maintenance</html>")[0]["status"] == "failed"


def test_catbox_refuses_anonymous_upload(tmp_path: Any) -> None:
    result, client = _upload(tmp_path, URL, userhash="")
    assert result["status"] == "failed"
    client.post.assert_not_called()
