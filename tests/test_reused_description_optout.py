# A tracker can opt out of the description text reused from other trackers
# (include_reused_description: False in its config section); a description
# the user provided themselves is never affected.

import asyncio
from unittest.mock import AsyncMock, patch

from src.get_desc import DescriptionBuilder


def _config(include: bool) -> dict:
    return {
        "DEFAULT": {"screens": 0, "multiScreens": 0},
        "TRACKERS": {"TOS": {"include_reused_description": include}},
    }


def _meta(saved: bool) -> dict:
    return {
        "base_dir": "/tmp",
        "uuid": "x",
        "description": "An English plot summary grabbed elsewhere.",
        "saved_description": saved,
        "image_list": [],
        "language_checked": True,
        "subtitle_languages": [],
        "debug": False,
        "ua_signature": "sig",
    }


def _build(meta: dict, config: dict) -> str:
    builder = DescriptionBuilder("TOS", config)
    quiet = AsyncMock(return_value="")
    with (
        patch.object(DescriptionBuilder, "get_custom_header", quiet),
        patch.object(DescriptionBuilder, "get_logo_section", AsyncMock(return_value=("", ""))),
        patch.object(DescriptionBuilder, "get_bluray_section", AsyncMock(return_value=("", ""))),
        patch.object(DescriptionBuilder, "get_tv_info", AsyncMock(return_value=("", "", ""))),
        patch.object(DescriptionBuilder, "get_user_description", quiet),
        patch.object(DescriptionBuilder, "get_personal_note", quiet),
        patch.object(DescriptionBuilder, "menu_section", quiet),
        patch.object(DescriptionBuilder, "get_tonemapped_header", quiet),
        patch.object(DescriptionBuilder, "_handle_discs_and_screenshots", quiet),
        patch.object(DescriptionBuilder, "get_custom_signature", quiet),
    ):
        return asyncio.run(builder.unit3d_edit_desc(meta))


def test_reused_description_is_dropped_when_opted_out() -> None:
    assert "English plot summary" not in _build(_meta(saved=True), _config(include=False))


def test_reused_description_kept_by_default() -> None:
    assert "English plot summary" in _build(_meta(saved=True), _config(include=True))


def test_user_description_survives_the_optout() -> None:
    assert "English plot summary" in _build(_meta(saved=False), _config(include=False))
