# Video files sitting in subfolders of the release root (one folder per
# episode, or a movie one level too deep) are rejected by most trackers:
# warn, list the folders, ask when interactive, abort when unattended.

import asyncio
import builtins
from pathlib import Path
from typing import Any

import pytest

from src.video import check_nested_folders

REL = "Example.Release.S01.2026.1080p.WEB-DL.H264-GRP"


def _release(tmp_path: Path, nested: bool) -> dict[str, Any]:
    root = tmp_path / REL
    files = []
    for ep in ("S01E01", "S01E02"):
        name = f"Example.Release.{ep}.2026.1080p.WEB-DL.H264-GRP.mkv"
        target = root / name.removesuffix(".mkv") / name if nested else root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"x")
        files.append(str(target))
    (root / "Subs").mkdir(exist_ok=True)  # non-video subfolder never counts
    return {"path": str(root), "isdir": True, "filelist": sorted(files), "unattended": False, "debug": False}


def _answer(monkeypatch: Any, text: str) -> list[str]:
    prompts: list[str] = []

    def fake_input(prompt: str = "") -> str:
        prompts.append(prompt)
        return text

    monkeypatch.setattr(builtins, "input", fake_input)
    return prompts


def test_flat_release_passes_silently(tmp_path: Path, monkeypatch: Any) -> None:
    prompts = _answer(monkeypatch, "n")
    asyncio.run(check_nested_folders(_release(tmp_path, nested=False)))
    assert prompts == []


def test_nested_unattended_aborts(tmp_path: Path) -> None:
    meta = _release(tmp_path, nested=True)
    meta["unattended"] = True
    with pytest.raises(SystemExit):
        asyncio.run(check_nested_folders(meta))


def test_nested_interactive_yes_continues(tmp_path: Path, monkeypatch: Any) -> None:
    prompts = _answer(monkeypatch, "y")
    asyncio.run(check_nested_folders(_release(tmp_path, nested=True)))
    assert len(prompts) == 1


def test_nested_interactive_default_aborts(tmp_path: Path, monkeypatch: Any) -> None:
    _answer(monkeypatch, "")
    with pytest.raises(SystemExit):
        asyncio.run(check_nested_folders(_release(tmp_path, nested=True)))


def test_disc_is_ignored(tmp_path: Path) -> None:
    meta = _release(tmp_path, nested=True)
    meta.update({"is_disc": "BDMV", "unattended": True})
    asyncio.run(check_nested_folders(meta))
