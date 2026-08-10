# Regression tests for QueueManager._resolve_split_path.
#
# When a queued path no longer exists (e.g. a cross-seed dir cleaned up between
# queueing and processing), the greedy space-split used to stop at the longest
# existing *prefix* directory and queue it — which could enqueue an entire
# parent directory full of unrelated releases. Resolution must be
# all-or-nothing: any unresolved fragment discards the whole queue.

import asyncio
from typing import Any

from src.queuemanage import QueueManager


def _resolve(path: str) -> list[str]:
    return asyncio.run(QueueManager._resolve_split_path(path))


def test_vanished_path_with_existing_prefix_dir_returns_nothing(tmp_path: Any) -> None:
    (tmp_path / "seedpool").mkdir()
    gone = f"{tmp_path}/seedpool (API)/Some Movie (2001) (1080p WEB-DL - GRP).mkv"
    assert _resolve(gone) == []


def test_single_existing_path_with_spaces_resolves(tmp_path: Any) -> None:
    d = tmp_path / "dir with space"
    d.mkdir()
    f = d / "file.mkv"
    f.write_bytes(b"x")
    assert _resolve(str(f)) == [str(f)]


def test_two_existing_paths_split_on_space(tmp_path: Any) -> None:
    a = tmp_path / "a.mkv"
    b = tmp_path / "b.mkv"
    a.write_bytes(b"x")
    b.write_bytes(b"x")
    assert _resolve(f"{a} {b}") == [str(a), str(b)]


def test_existing_path_then_missing_path_returns_nothing(tmp_path: Any) -> None:
    a = tmp_path / "a.mkv"
    a.write_bytes(b"x")
    assert _resolve(f"{a} {tmp_path}/missing.mkv") == []
