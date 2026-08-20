"""Regression: reuploaded_images.json is shared by every tracker, so two
trackers rehosting to different hosts leave one screenshot set per host in
it. A tracker approving both hosts must still pick up a single set."""

import asyncio
import json
import pathlib
from typing import Any

from src.rehostimages import _check_hosts

MAPPING = {"pixhost.to": "pixhost", "ptscreens.com": "ptscreens"}


def _img(host: str, i: int) -> dict[str, str]:
    url = f"https://img.{host}/{i}.png"
    return {"img_url": url, "raw_url": url, "web_url": url}


def _run(tmp_path: pathlib.Path, stored: list[dict[str, str]]) -> list[dict[str, str]]:
    uuid = "Movie.2024.1080p.WEB-DL-GRP"
    shots = tmp_path / "tmp" / uuid
    shots.mkdir(parents=True)
    (shots / "reuploaded_images.json").write_text(json.dumps(stored), encoding="utf-8")
    meta: dict[str, Any] = {
        "base_dir": str(tmp_path),
        "uuid": uuid,
        "debug": False,
        "image_list": [_img("onlyimage.org", i) for i in range(6)],
    }
    result, _retry, _reup = asyncio.run(
        _check_hosts(
            meta,
            "V3X",
            MAPPING,
            approved_image_hosts=["pixhost", "ptscreens"],
            default_config={},
            takescreens_manager=object(),
            uploadscreens_manager=object(),
        )
    )
    return result


def test_only_one_host_set_is_used(tmp_path: pathlib.Path):
    stored = [_img("ptscreens.com", i) for i in range(6)] + [_img("pixhost.to", i) for i in range(6)]
    result = _run(tmp_path, stored)
    assert result == [_img("ptscreens.com", i) for i in range(6)]


def test_most_complete_set_wins(tmp_path: pathlib.Path):
    stored = [_img("ptscreens.com", i) for i in range(3)] + [_img("pixhost.to", i) for i in range(6)]
    assert _run(tmp_path, stored) == [_img("pixhost.to", i) for i in range(6)]
