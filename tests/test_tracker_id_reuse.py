# Tests for explicit-ID metadata reuse wiring.
#
# A tracker torrent found in the client carries its site URL in the torrent
# comment; the extracted ID must flow through prep.py's gate list and
# get_tracker_data's tracker_keys into trackermeta's UNIT3D branch. These tests
# cover the comment extractor and keep the four lists consistent.

import ast
import os
import re

from src.clients import Clients

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

NEW_TRACKERS = {
    "a4k": "aura4k.net",
    "hhd": "homiehelpdesk.net",
    "ihd": "infinityhd.net",
    "lume": "luminarr.me",
    "stc": "skipthecommercials.xyz",
    "g3mini": "gemini-tracker.org",
    "tos": "theoldschool.cc",
    "acm": "eiga.moi",
    # Remaining UNIT3D trackers with a standard id_url API (DT is excluded:
    # its /api/v1/ scheme has no id_url).
    "cbr": "capybarabr.com",
    "emuw": "emuwarez.com",
    "gf": "generation-free.org",
    "itt": "itatorrents.xyz",
    "lcd": "locadora.cc",
    "ldu": "theldu.to",
    "lt": "lat-team.com",
    "nst": "nostradamus.foo",
    "pt": "portugas.org",
    "ptt": "polishtorrent.top",
    "r4e": "racing4everyone.eu",
    "ras": "rastastugan.org",
    "sam": "samaritano.cc",
    "shri": "shareisland.org",
    "tik": "cinematik.net",
    "tlz": "tlzdigital.com",
    "ttr": "torrenteros.org",
    "utp": "utp.to",
}


def test_extractor_finds_new_unit3d_tracker_ids() -> None:
    for key, domain in NEW_TRACKERS.items():
        comment = f"https://{domain}/torrents/4567"
        assert Clients._extract_tracker_ids_from_comment(comment) == {key: "4567"}, key


def test_extractor_still_finds_existing_ids() -> None:
    assert Clients._extract_tracker_ids_from_comment("https://lst.gg/torrents/156060") == {"lst": "156060"}
    assert Clients._extract_tracker_ids_from_comment("no url here") == {}


def _source(path: str) -> str:
    with open(os.path.join(BASE, path), encoding="utf-8") as f:
        return f.read()


def test_id_keys_wired_through_prep_and_tracker_keys() -> None:
    prep_match = re.search(r"tracker_ids = (\[[^\]]*\])", _source("src/prep.py"))
    assert prep_match
    prep_ids = set(ast.literal_eval(prep_match.group(1)))

    tracker_keys_maps = re.findall(r"tracker_keys = (\{[^}]*\})", _source("src/get_tracker_data.py"))
    assert len(tracker_keys_maps) == 2

    unit3d_match = re.search(r'elif tracker_name in (\[[^\]]*\]):', _source("src/trackermeta.py"))
    assert unit3d_match
    unit3d_trackers = set(ast.literal_eval(unit3d_match.group(1)))

    for key, name in [(k, k.upper()) for k in NEW_TRACKERS]:
        assert key in prep_ids, f"{key} missing from prep.py tracker_ids"
        for i, keys_map in enumerate(tracker_keys_maps):
            assert ast.literal_eval(keys_map).get(key) == name, f"{key} missing from tracker_keys #{i + 1}"
        assert name in unit3d_trackers, f"{name} missing from trackermeta UNIT3D branch"


def test_metadata_reuse_consultation_order() -> None:
    # Deliberate local preference; dict order is the priority, first valid
    # answer wins. Guards against upstream merges reshuffling the dict.
    tracker_keys_maps = re.findall(r"tracker_keys = (\{[^}]*\})", _source("src/get_tracker_data.py"))
    order = list(ast.literal_eval(tracker_keys_maps[0]))
    preferred = [
        "aither", "blu", "lst", "ulcx", "oe", "huno", "ant", "btn", "bhd", "hdb", "sp", "rf",
        "otw", "yus", "dp", "lume", "hhd", "ihd", "a4k", "stc", "acm", "ptp", "tos", "g3mini",
    ]
    extra = sorted(k for k in NEW_TRACKERS if k not in preferred)
    assert order == preferred + extra


def test_qbit_auto_search_recognizes_new_trackers() -> None:
    source = _source("src/torrent_clients/qbittorrent.py")

    patterns_match = re.search(r"tracker_patterns = (\{.*?\n\s*\})\n", source, re.DOTALL)
    assert patterns_match
    tracker_patterns = ast.literal_eval(patterns_match.group(1))

    priority_match = re.search(r"tracker_priority = (\[[^\]]*\])", source)
    assert priority_match
    tracker_priority = ast.literal_eval(priority_match.group(1))

    for key, domain in NEW_TRACKERS.items():
        info = tracker_patterns.get(key)
        assert info, f"{key} missing from qbit tracker_patterns"
        assert domain in info["url"], f"{key} url does not point to {domain}"
        assert key in tracker_priority, f"{key} missing from qbit tracker_priority"

        # The pattern must extract the torrent id from a UNIT3D comment URL...
        comment = f"https://{domain}/torrents/4567"
        assert info["url"] in comment
        match = re.search(info["pattern"], comment)
        assert match and match.group(1) == "4567", f"{key} pattern failed on {comment}"
        # ...and not match when no trailing id is present.
        assert re.search(info["pattern"], f"https://{domain}/torrents") is None

    # PTP must stay last: the priority list prefers smaller trackers first.
    assert tracker_priority[-1] == "ptp"
