"""Per-tracker rehost must be able to reach any configured host slot, and a
tracker left without enough images on an approved host must be skipped."""

import asyncio
import pathlib
from typing import Any

import pytest

from src.rehostimages import _handle_image_upload, trackers_lacking_images


class _Uploader:
    def __init__(self) -> None:
        self.hosts: list[str] = []

    async def upload_screens(self, meta: dict[str, Any], *args: Any, **kwargs: Any) -> Any:
        self.hosts.append(meta["imghost"])
        img = {"img_url": "https://img.ptscreens.com/a.md.png", "raw_url": "https://img.ptscreens.com/a.png", "web_url": "https://ptscreens.com/a"}
        return [img], 1


class _Screens:
    async def screenshots(self, *args: Any, **kwargs: Any) -> None:
        return None


def test_rehost_reaches_an_approved_host_beyond_the_approved_list_size(tmp_path: pathlib.Path):
    # 4 configured slots, 2 approved hosts: the approved one sits in slot 4.
    uuid = "Movie.2024.1080p.WEB-GRP"
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
        "imghost": "lostimg",
        "title": "Movie",
        "video": "/x/movie.mkv",
    }
    default_config = {"img_host_1": "lostimg", "img_host_2": "pixhost", "img_host_3": "postimg", "img_host_4": "ptscreens", "screens": "1"}
    uploader = _Uploader()

    result, retry_mode, _ = asyncio.run(
        _handle_image_upload(
            meta,
            "STC",
            approved_image_hosts=["imgbox", "ptscreens"],
            img_host_index=1,
            default_config=default_config,
            takescreens_manager=_Screens(),
            uploadscreens_manager=uploader,
        )
    )

    assert uploader.hosts == ["ptscreens"]
    assert retry_mode is False
    assert result and result[0]["raw_url"].startswith("https://img.ptscreens.com/")


@pytest.mark.parametrize(
    ("meta", "expected"),
    [
        ({"STC_images_key": [{}] * 4, "C411_images_key": [{}] * 2}, ["C411"]),
        ({"STC_images_key": [{}] * 4}, ["C411"]),
        ({"STC_images_key": [{}] * 4, "C411_images_key": [{}] * 4}, []),
    ],
)
def test_trackers_lacking_images(meta: dict[str, Any], expected: list[str]):
    assert trackers_lacking_images(meta, ["STC", "C411"], minimum=4) == expected
