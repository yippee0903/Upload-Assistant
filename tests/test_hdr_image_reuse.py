# Tracker images are reused as-is, so for an HDR/DV release with tone_map on
# they must only be kept when the source declared them tonemapped; otherwise
# the tool captures (and tonemaps) its own screenshots.

from typing import Any

from src import takescreens

IMAGES = [{"img_url": "https://img.example/a.png", "raw_url": "https://img.example/a.png"}]


def _kept(meta: dict[str, Any], tone_map: bool) -> bool:
    takescreens._apply_config({"DEFAULT": {"tone_map": tone_map}})
    meta = {"image_list": list(IMAGES), **meta}
    takescreens.drop_untonemapped_reused_images(meta)
    return meta["image_list"] == IMAGES


def test_hdr_reuse_dropped_without_tonemapped_note() -> None:
    assert _kept({"hdr": "DV HDR"}, True) is False


def test_hdr_reuse_kept_when_source_declares_tonemapped() -> None:
    assert _kept({"hdr": "DV HDR", "tonemapped": True}, True) is True


def test_sdr_reuse_unaffected() -> None:
    assert _kept({"hdr": ""}, True) is True


def test_hdr_reuse_kept_when_tone_map_disabled() -> None:
    assert _kept({"hdr": "HDR"}, False) is True
