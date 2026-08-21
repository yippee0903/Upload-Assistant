"""Regression: a host that uploads zero images must trigger rotation to the
next approved host instead of returning an empty result as success."""

import asyncio
import pathlib
from typing import Any

from src.rehostimages import _handle_image_upload


class _Uploader:
    async def upload_screens(self, *args: Any, **kwargs: Any) -> Any:
        return [], 0  # host accepts nothing (e.g. HTTP 413 on every file)


class _Screens:
    async def screenshots(self, *args: Any, **kwargs: Any) -> None:
        return None


def test_zero_uploads_marks_host_failed_and_requests_retry(tmp_path: pathlib.Path):
    uuid = "Movie.2024.2160p.Remux-GRP"
    shots = tmp_path / "tmp" / uuid
    shots.mkdir(parents=True)
    (shots / "abc123.png").write_bytes(b"x")
    meta = {
        "base_dir": str(tmp_path),
        "uuid": uuid,
        "debug": False,
        "is_disc": None,
        "filelist": ["/x/movie.mkv"],
        "image_list": [{"img_url": "https://lostimg.cc/abc123.png", "raw_url": "https://lostimg.cc/abc123.png", "web_url": "https://lostimg.cc/abc123.png"}],
        "imghost": "pixhost",
        "title": "Movie",
        "video": "/x/movie.mkv",
    }
    default_config = {"img_host_1": "pixhost", "img_host_2": "imgbb", "screens": "1"}

    result, retry_mode, _reup = asyncio.run(
        _handle_image_upload(
            meta,
            "V3X",
            approved_image_hosts=["pixhost", "imgbb"],
            img_host_index=1,
            default_config=default_config,
            takescreens_manager=_Screens(),
            uploadscreens_manager=_Uploader(),
        )
    )

    assert result == []
    assert retry_mode is True
    assert "pixhost" in meta.get("failed_image_hosts", [])
