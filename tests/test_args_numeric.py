import pytest

from src.args import Args


def _args() -> Args:
    return Args({"DEFAULT": {"screens": 6, "default_torrent_client": "none"}, "TRACKERS": {"default_trackers": ""}})


def test_numeric_flags_are_ints():
    meta, _parser, _ = _args().parse(["-s", "4", "-fl", "50", "/x/a.mkv"], {})
    assert meta["screens"] == 4 and meta["freeleech"] == 50


def test_non_numeric_value_is_a_clean_usage_error():
    with pytest.raises(SystemExit) as exc:
        _args().parse(["-s", "abc", "/x/a.mkv"], {})
    assert exc.value.code == 2
