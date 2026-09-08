# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Tests for the 'do not reupload' notice detection on fetched source descriptions."""

from unittest.mock import patch

import pytest

from src.trackers.COMMON import check_reupload_notice


@pytest.mark.parametrize(
    "text",
    [
        "Please do not reupload this release anywhere.",
        "DON'T RE-UPLOAD",
        "Internal release, no reupload without permission.",
        "This torrent is not to be cross-seeded.",
        "[b]Do not reupload[/b] to other sites",
    ],
)
def test_forbidden_notice_aborts_unattended(text):
    with pytest.raises(Exception, match="Reupload forbidden by the SRC uploader"):
        check_reupload_notice({"unattended": True}, text, "SRC")


@pytest.mark.parametrize("text", ["", None, "Feel free to reupload.", "Reupload of the original release.", "Cross-seed friendly."])
def test_plain_descriptions_pass(text):
    check_reupload_notice({"unattended": True}, text, "SRC")


def test_interactive_can_override():
    meta = {"unattended": False}
    with patch("src.trackers.COMMON.cli_ui.ask_yes_no", return_value=True):
        check_reupload_notice(meta, "do not reupload", "SRC")
    with patch("src.trackers.COMMON.cli_ui.ask_yes_no", return_value=False), pytest.raises(Exception, match="Reupload forbidden"):
        check_reupload_notice(meta, "do not reupload", "SRC")
