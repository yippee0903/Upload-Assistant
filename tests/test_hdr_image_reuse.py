# Tracker images are reused as-is, so for an HDR/DV release with tone_map on
# they must only be kept when the source declared them tonemapped; otherwise
# the tool captures (and tonemaps) its own screenshots.

from typing import Any

from src import takescreens

IMAGES = [{"img_url": "https://img.example/a.png", "raw_url": "https://img.example/a.png"}]


def _kept(meta: dict[str, Any], tone_map: bool) -> bool:
    takescreens._apply_config({"DEFAULT": {"tone_map": tone_map}})
    meta = {"image_list": list(IMAGES), "image_list_from_tracker": True, **meta}
    takescreens.drop_untonemapped_reused_images(meta)
    return meta["image_list"] == IMAGES


def test_own_captures_are_never_dropped_even_without_a_tonemap() -> None:
    # DV-only source where the tonemap could not run: the tool's own captures
    # (not marked as coming from a tracker) must survive later screenshots() calls.
    assert _kept({"hdr": "DV", "image_list_from_tracker": False}, True) is True
    assert _kept({"hdr": "DV", "image_list_from_tracker": None}, True) is True


def test_tracker_images_are_dropped_only_once() -> None:
    takescreens._apply_config({"DEFAULT": {"tone_map": True}})
    meta: dict[str, Any] = {"hdr": "DV", "image_list": list(IMAGES), "image_list_from_tracker": True}
    takescreens.drop_untonemapped_reused_images(meta)
    assert meta["image_list"] == [] and meta["image_list_from_tracker"] is False
    meta["image_list"] = list(IMAGES)  # the tool's own uploads
    takescreens.drop_untonemapped_reused_images(meta)
    assert meta["image_list"] == IMAGES


def test_hdr_reuse_dropped_without_tonemapped_note() -> None:
    assert _kept({"hdr": "DV HDR"}, True) is False


def test_hdr_reuse_kept_when_source_declares_tonemapped() -> None:
    assert _kept({"hdr": "DV HDR", "tonemapped": True}, True) is True


def test_sdr_reuse_unaffected() -> None:
    assert _kept({"hdr": ""}, True) is True


def test_hdr_reuse_kept_when_tone_map_disabled() -> None:
    assert _kept({"hdr": "HDR"}, False) is True
