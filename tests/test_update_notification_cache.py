import json
import time

from src.updatecheck import cached_remote_version


def test_remote_check_is_cached(tmp_path):
    cache = tmp_path / "update_check.json"
    calls = []

    def fetch():
        calls.append(1)
        return "v1.0.1", "## v1.0.1"

    assert cached_remote_version(str(cache), 4, fetch) == ("v1.0.1", "## v1.0.1")
    assert cached_remote_version(str(cache), 4, fetch) == ("v1.0.1", "## v1.0.1")
    assert len(calls) == 1
    assert json.loads(cache.read_text())["remote_version"] == "v1.0.1"


def test_stale_cache_is_refreshed_and_failed_fetch_not_cached(tmp_path):
    cache = tmp_path / "update_check.json"
    cache.write_text(json.dumps({"checked_at": time.time() - 5 * 3600, "remote_version": "v0.9", "remote_content": "x"}))
    assert cached_remote_version(str(cache), 4, lambda: ("v1.1", "y")) == ("v1.1", "y")
    assert cached_remote_version(str(cache), 0, lambda: (None, None)) == (None, None)
    assert json.loads(cache.read_text())["remote_version"] == "v1.1"
