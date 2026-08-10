# Regression test: when every upload to the current image host fails and the
# internal failover does not apply (the current host was remapped away from
# img_host_1, e.g. for tracker approval), _upload_screens must return an empty
# result so the multi-host loop in upload.py can try the next host — not raise
# and abort the whole upload.

import asyncio
import base64
from typing import Any

import pytest

import src.uploadscreens as uploadscreens

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==")


def _setup(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    uuid = "fake-release"
    shot_dir = tmp_path / "tmp" / uuid
    shot_dir.mkdir(parents=True)
    for n in range(3):
        (shot_dir / f"shot-{n}.png").write_bytes(PNG)

    async def failing_upload(args: Any) -> dict[str, Any]:
        return {"status": "failed", "reason": "host down"}

    monkeypatch.setattr(uploadscreens, "upload_image_task", failing_upload)

    return {
        "base_dir": str(tmp_path),
        "uuid": uuid,
        "debug": False,
        "screens": 3,
        "image_list": [],
        "cutoff": 3,
    }


def test_total_failure_on_remapped_host_returns_instead_of_raising(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    # imghost was remapped to img_host_2 (tracker approval), so the internal
    # failover (which requires imghost == img_host_1) is inactive.
    config = {"DEFAULT": {"img_host_1": "hostA", "img_host_2": "hostB"}}
    meta = _setup(tmp_path, monkeypatch)
    meta["imghost"] = "hostB"

    image_list, count = asyncio.run(uploadscreens._upload_screens(config, meta, 3, 1, 0, 3, [], {}, max_retries=0))
    assert image_list == []
    assert count == 0


def test_total_failure_with_custom_list_returns_empty(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    config = {"DEFAULT": {"img_host_1": "hostA"}}
    meta = _setup(tmp_path, monkeypatch)
    meta["imghost"] = "hostA"
    custom = [str(tmp_path / "tmp" / meta["uuid"] / f"shot-{n}.png") for n in range(3)]

    # Custom image lists disable the internal failover; a dead host must
    # surface as an empty result for the caller (e.g. PTP poster upload).
    image_list, count = asyncio.run(uploadscreens._upload_screens(config, meta, 3, 1, 0, 3, custom, {}, max_retries=0))
    assert image_list == []
    assert count == 0
