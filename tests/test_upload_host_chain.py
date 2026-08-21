"""upload_screens keeps walking img_host_N after the first fallback also fails."""

import asyncio
import os
import pathlib
from typing import Any
from unittest.mock import AsyncMock, patch

from src import uploadscreens


def test_fallback_chain_reaches_third_host(tmp_path: pathlib.Path) -> None:
    uuid = "Anonymous.Release.2020"
    shots = tmp_path / "tmp" / uuid
    shots.mkdir(parents=True)
    (shots / "shot-1.png").write_bytes(b"\x89PNG")
    attempted: list[str] = []

    async def fake_upload(args: Any) -> dict[str, Any]:
        image, host, _config, _meta = args
        attempted.append(host)
        if host != "pixhost":
            return {"status": "failed", "reason": "down"}
        return {"status": "success", "img_url": "https://p/i.png", "raw_url": "https://p/r.png", "web_url": "https://p/w.png"}

    config = {"DEFAULT": {"img_host_1": "imgbb", "img_host_2": "ptscreens", "img_host_3": "pixhost"}}
    meta: dict[str, Any] = {"base_dir": str(tmp_path), "uuid": uuid, "imghost": "imgbb", "debug": False, "cutoff": 1}
    cwd = os.getcwd()
    try:
        with patch("src.uploadscreens.upload_image_task", fake_upload), patch("src.uploadscreens.asyncio.sleep", AsyncMock()):
            images, count = asyncio.run(uploadscreens._upload_screens(config, meta, 1, 1, 0, 1, [], {}))
    finally:
        os.chdir(cwd)
    assert list(dict.fromkeys(attempted)) == ["imgbb", "ptscreens", "pixhost"]
    assert count == 1 and images[0]["raw_url"] == "https://p/r.png"
    assert meta["failed_image_hosts"] == ["imgbb", "ptscreens"]
