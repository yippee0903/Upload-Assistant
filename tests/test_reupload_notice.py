# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Tests for the 'do not reupload' notice detection on fetched source descriptions."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.trackers.COMMON import COMMON, ReuploadForbidden, check_reupload_notice


@pytest.mark.parametrize(
    "text",
    [
        "Please do not reupload this release anywhere.",
        "DON'T RE-UPLOAD",
        "Internal release, no reupload without permission.",
        "This torrent is not to be cross-seeded.",
        "[b]Do not reupload[/b] to other sites",
        "Please do not cross seed this.",
        "No cross seeding allowed.",
        "Do not re upload.",
    ],
)
def test_forbidden_notice_aborts_unattended(text):
    with pytest.raises(ReuploadForbidden, match="Reupload forbidden by the SRC uploader"):
        check_reupload_notice({"unattended": True}, text, "SRC")


@pytest.mark.parametrize("text", ["", None, "Feel free to reupload.", "Reupload of the original release.", "Cross-seed friendly."])
def test_plain_descriptions_pass(text):
    check_reupload_notice({"unattended": True}, text, "SRC")


def test_interactive_can_override():
    meta = {"unattended": False}
    with patch("src.trackers.COMMON.cli_ui.ask_yes_no", return_value=True):
        check_reupload_notice(meta, "do not reupload", "SRC")
    with patch("src.trackers.COMMON.cli_ui.ask_yes_no", return_value=False), pytest.raises(ReuploadForbidden):
        check_reupload_notice(meta, "do not reupload", "SRC")


def _unit3d_info(payload: dict, **kwargs):
    response = MagicMock(status_code=200)
    response.json.return_value = payload
    client = AsyncMock()
    client.get.return_value = response
    client.__aenter__.return_value = client
    common = COMMON({"TRACKERS": {"SRC": {"api_key": "k"}}, "DEFAULT": {}})
    with patch("src.trackers.COMMON.httpx.AsyncClient", return_value=client):
        return asyncio.run(common.unit3d_torrent_info("SRC", "https://example.invalid/torrents/", "https://example.invalid/api", {"unattended": True}, **kwargs))


def test_unit3d_torrent_info_propagates_the_abort():
    notice = {"attributes": {"description": "Do not reupload.", "tmdb_id": "1"}}
    for kwargs in ({"file_name": "Example.Release.2026.1080p-GRP.mkv"}, {"id": "7"}):
        with pytest.raises(ReuploadForbidden):
            _unit3d_info({"data": [notice]} if "file_name" in kwargs else {"data": [], **notice}, **kwargs)
