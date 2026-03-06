"""Tests for VideoManager.get_type – WEB-DL vs WEBRip detection."""

import asyncio
from typing import Any

import pytest

from src.video import video_manager


def _run(coro: Any) -> Any:
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestGetTypeWeb:
    """WEB-DL / WEBRip detection, including the folder-name fallback."""

    @pytest.mark.parametrize(
        "video, meta_path, expected",
        [
            # --- Explicit WEB-DL in filename → always WEBDL ---
            (
                "/media/S02/Malcolm.S02E01.1080p.WEB-DL.x265-Group.mkv",
                "/media/S02",
                "WEBDL",
            ),
            (
                "/media/S02/Malcolm.S02E01.1080p.WEBDL.x265-Group.mkv",
                "/media/S02",
                "WEBDL",
            ),
            # --- Explicit WEBRip in filename → always WEBRIP ---
            (
                "/media/S02/Malcolm.S02E01.1080p.WEBRip.x265-Group.mkv",
                "/media/S02",
                "WEBRIP",
            ),
            # --- Bare .WEB. + x265, folder says WEB-DL → WEBDL (the fix) ---
            (
                "/media/Malcolm S02 1080p WEB-DL x265-Group/Malcolm.S02E01.1080p.WEB.x265-Group.mkv",
                "/media/Malcolm S02 1080p WEB-DL x265-Group",
                "WEBDL",
            ),
            # --- Bare .WEB. + x265, meta path says WEB-DL → WEBDL ---
            (
                "/media/Season/Malcolm.S02E01.1080p.WEB.x265-Group.mkv",
                "/media/Malcolm S02 1080p WEB-DL x265-Group",
                "WEBDL",
            ),
            # --- Bare .WEB. + x265, folder says WEBRip → WEBRIP ---
            (
                "/media/Malcolm S02 1080p WEBRip x265-Group/Malcolm.S02E01.1080p.WEB.x265-Group.mkv",
                "/media/Malcolm S02 1080p WEBRip x265-Group",
                "WEBRIP",
            ),
            # --- Bare .WEB. + x265, no qualifier in folder → WEBRIP (heuristic) ---
            (
                "/media/Season/Malcolm.S02E01.1080p.WEB.x265-Group.mkv",
                "/media/Season",
                "WEBRIP",
            ),
            # --- Bare .WEB. without x265, no qualifier → WEBDL (heuristic) ---
            (
                "/media/Season/Malcolm.S02E01.1080p.WEB.H265-Group.mkv",
                "/media/Season",
                "WEBDL",
            ),
            # --- Bare .WEB. + x264, folder says WEBDL → trust folder ---
            (
                "/media/Show S01 WEB-DL/Show.S01E01.WEB.x264-Group.mkv",
                "/media/Show S01 WEB-DL",
                "WEBDL",
            ),
            # --- Space-delimited " web " + x265, folder says WEB-DL ---
            (
                "/media/Show S02 WEB-DL x265/Show S02E01 1080p WEB x265-Group.mkv",
                "/media/Show S02 WEB-DL x265",
                "WEBDL",
            ),
            # --- Ancestor dir named WEBRip must NOT leak into detection ---
            (
                "/downloads/WEBRip/Show S02/Show.S02E01.1080p.WEB.H265-Group.mkv",
                "/downloads/WEBRip/Show S02",
                "WEBDL",
            ),
            # --- Ancestor dir named WEB-DL must NOT leak into detection ---
            (
                "/downloads/WEB-DL/Show S02/Show.S02E01.1080p.WEB.x265-Group.mkv",
                "/downloads/WEB-DL/Show S02",
                "WEBRIP",
            ),
        ],
        ids=[
            "explicit-webdl-filename",
            "explicit-webdl-no-dash",
            "explicit-webrip-filename",
            "bare-web-x265-folder-webdl",
            "bare-web-x265-meta-path-webdl",
            "bare-web-x265-folder-webrip",
            "bare-web-x265-no-qualifier-heuristic",
            "bare-web-h265-no-qualifier-heuristic",
            "bare-web-x264-folder-webdl",
            "space-web-x265-folder-webdl",
            "ancestor-webrip-not-leaked",
            "ancestor-webdl-not-leaked",
        ],
    )
    def test_web_type_detection(self, video: str, meta_path: str, expected: str) -> None:
        meta: dict[str, Any] = {"path": meta_path}
        result = _run(video_manager.get_type(video, False, None, meta))
        assert result == expected

    def test_remux(self) -> None:
        meta: dict[str, Any] = {"path": "/media/Movie.Remux"}
        result = _run(video_manager.get_type("/media/Movie.Remux/movie.remux.mkv", False, None, meta))
        assert result == "REMUX"

    def test_manual_override(self) -> None:
        meta: dict[str, Any] = {"path": "/media/Season", "manual_type": "WEBDL"}
        result = _run(video_manager.get_type("/media/Season/ep.WEB.x265.mkv", False, None, meta))
        assert result == "WEBDL"

    def test_encode_fallback(self) -> None:
        meta: dict[str, Any] = {"path": "/media/Movie"}
        result = _run(video_manager.get_type("/media/Movie/movie.mkv", False, None, meta))
        assert result == "ENCODE"
