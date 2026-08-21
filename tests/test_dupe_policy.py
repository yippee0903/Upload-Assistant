import asyncio
from unittest.mock import patch

from src.dupe_checking import EXACT_NAME_MATCH_TRACKERS, DupeChecker


class _Namer:
    def __init__(self, config):
        pass

    async def edit_name(self, meta):
        return meta["name"].replace("DD+", "DDP")


def test_exact_name_match_uses_tracker_formatting():
    checker = DupeChecker({"DEFAULT": {}})
    meta = {"name": "Anonymous.Release.2020.DD+5.1"}
    with patch("src.trackersetup.tracker_class_map", {"BHD": _Namer}):
        assert asyncio.run(checker._tracker_name("BHD", meta)) == "Anonymous.Release.2020.DDP5.1"
    assert "BHD" in EXACT_NAME_MATCH_TRACKERS
