import asyncio
import json
import time
from unittest.mock import patch

import upload


def test_remote_check_is_cached(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "version.py").write_text('__version__ = "v1.0.0"\n')
    with (
        patch.dict(upload.config, {"DEFAULT": {"update_notification": True, "update_notification_cache_hours": 4}}),
        patch("upload.get_remote_version", return_value=("v1.0.1", "## v1.0.1")) as remote,
    ):
        assert asyncio.run(upload.update_notification(str(tmp_path))) == "v1.0.0"
        assert asyncio.run(upload.update_notification(str(tmp_path))) == "v1.0.0"
    assert remote.call_count == 1
    cached = json.loads((tmp_path / "data" / "update_check.json").read_text())
    assert cached["remote_version"] == "v1.0.1" and cached["checked_at"] <= time.time()


def test_stale_cache_is_refreshed(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "version.py").write_text('__version__ = "v1.0.0"\n')
    (tmp_path / "data" / "update_check.json").write_text(json.dumps({"checked_at": time.time() - 5 * 3600, "remote_version": "v0.9", "remote_content": ""}))
    with (
        patch.dict(upload.config, {"DEFAULT": {"update_notification": True}}),
        patch("upload.get_remote_version", return_value=("v1.0.1", "x")) as remote,
    ):
        asyncio.run(upload.update_notification(str(tmp_path)))
    assert remote.call_count == 1
