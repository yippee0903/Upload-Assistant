"""The AKA is decided against an early, filename-derived title: it must not repeat the final one."""

import asyncio
from typing import Any

from src.get_name import NameManager


def _name(aka: str) -> str:
    meta: dict[str, Any] = {
        "debug": False, "category": "TV", "type": "WEBDL", "title": "Ranma ½", "aka": aka, "year": "2024",
        "season": "S01", "episode": "", "resolution": "1080p", "source": "WEB", "service": "NF",
        "audio": "AAC 2.0", "video_encode": "H.264", "video_codec": "H.264", "tag": "-GRP", "uuid": "x",
        "is_disc": None, "edition": "", "repack": "", "hdr": "", "uhd": "", "hybrid": "", "three_d": "",
        "part": "", "distributor": "", "region": "", "search_year": "",
    }
    return asyncio.run(NameManager({"DEFAULT": {}}).get_name(meta))[0]


def test_aka_identical_to_title_is_dropped() -> None:
    assert _name("AKA Ranma ½") == "Ranma ½ S01 1080p NF WEB-DL AAC 2.0 H.264"
    assert _name("aka ranma ½ ") == "Ranma ½ S01 1080p NF WEB-DL AAC 2.0 H.264"


def test_different_aka_is_kept() -> None:
    assert _name("AKA Something Else") == "Ranma ½ AKA Something Else S01 1080p NF WEB-DL AAC 2.0 H.264"
