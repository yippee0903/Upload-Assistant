"""PTP poster host detection is derived from the shared URL_HOST_MAPPING."""

import pytest

from src.trackers.PTP import PTP


@pytest.fixture
def ptp():
    return PTP.__new__(PTP)


@pytest.mark.parametrize(
    ("url", "host", "expected"),
    [
        ("https://i.postimg.cc/abc/x.png", "postimg", True),
        ("https://i.ibb.co/abc/x.png", "imgbb", True),
        ("https://imgbb.com/abc", "imgbb", True),
        ("https://lostimg.cc/abc.png", "lostimg", True),
        ("https://cdn.seedpool.org/abc.png", "seedpool_cdn", True),
        ("https://pixhost.to/show/1/x.png", "imgbox", False),
        ("https://notpostimg.cc/x.png", "postimg", False),
        ("https://custom.example/x.png", "custom.example", True),
        ("https://custom.example/x.png", "", False),
    ],
)
def test_poster_already_on_selected_host(ptp, url, host, expected):
    assert ptp._poster_already_on_selected_host(url, host) is expected
