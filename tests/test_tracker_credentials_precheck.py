from src.trackersetup import TRACKER_SETUP


def _enabled(tracker_cfg, debug=False):
    setup = TRACKER_SETUP({"TRACKERS": {"default_trackers": "BHD", "BHD": tracker_cfg}, "DEFAULT": {}})
    return setup.trackers_enabled({"trackers": ["BHD"], "debug": debug})


def test_tracker_without_api_key_is_dropped_up_front():
    assert _enabled({"api_key": "", "announce_url": "https://x/announce"}) == []
    assert _enabled({"api_key": "k", "announce_url": ""}) == []
    assert _enabled({"api_key": "k", "announce_url": "https://x/announce"}) == ["BHD"]


def test_debug_keeps_the_tracker():
    assert _enabled({"api_key": ""}, debug=True) == ["BHD"]
