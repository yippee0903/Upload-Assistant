"""Images reused from another tracker's description must look like screenshots."""

import asyncio
from io import BytesIO

from PIL import Image

import src.trackermeta as trackermeta


def _png(width: int, height: int) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (width, height)).save(buf, "PNG")
    return buf.getvalue()


IMAGES = {
    "https://img.example/poster.jpg": _png(675, 1000),  # IMDb-style poster
    "https://img.example/screen.png": _png(1920, 1080),
}


class _Response:
    def __init__(self, url: str) -> None:
        self.status = 200
        self._body = IMAGES[url]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def read(self) -> bytes:
        return self._body


class _Session:
    def __init__(self, *_, **__) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    def get(self, url: str, **_):
        return _Response(url)


def test_portrait_poster_is_not_kept_as_a_screenshot(monkeypatch, tmp_path):
    async def _link_ok(*_):
        return True

    monkeypatch.setattr(trackermeta, "check_image_link", _link_ok)
    monkeypatch.setattr(trackermeta.aiohttp, "ClientSession", _Session)
    monkeypatch.setattr(trackermeta, "expected_images", 6)
    meta = {"resolution": "1080p", "base_dir": str(tmp_path), "uuid": "x", "debug": False}
    images = [{"raw_url": url, "img_url": url, "web_url": url} for url in IMAGES]

    kept = asyncio.run(trackermeta.check_images_concurrently(images, meta))

    assert [img["raw_url"] for img in kept] == ["https://img.example/screen.png"]
