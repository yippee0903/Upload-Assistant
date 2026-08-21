import asyncio

from src.get_desc import DescriptionBuilder


def _builder(default: dict, tracker: dict) -> DescriptionBuilder:
    return DescriptionBuilder("BLU", {"DEFAULT": default, "TRACKERS": {"BLU": tracker}})


def test_tag_override_beats_tracker_and_default():
    b = _builder(
        {"custom_signature": "default sig", "tag_overrides": {"GRP": {"custom_signature": "group sig"}}},
        {"custom_signature": "tracker sig", "tag_overrides": {"-grp": {"screenshot_header": "group shots"}}},
    )
    assert asyncio.run(b.get_custom_signature({"tag": "-GRP"})) == "group sig"
    assert asyncio.run(b.get_custom_signature({"tag": "-OTHER"})) == "tracker sig"
    assert asyncio.run(b.get_custom_signature()) == "tracker sig"
    assert asyncio.run(b.screenshot_header({"tag": "grp"})) == "group shots"


def test_no_overrides_falls_back_to_default():
    b = _builder({"custom_description_header": "hdr"}, {})
    assert asyncio.run(b.get_custom_header({"tag": "-GRP"})) == "hdr"
