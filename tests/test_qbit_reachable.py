# Tests for QbittorrentClientMixin._check_qbit_reachable — retry patience
"""
Regression: the health check used a single 5s probe whose negative result
was cached for the whole process, so a slow remote (waking tunnel, loaded
seedbox) aborted every qBittorrent operation of the run. The probe must
retry before declaring the client offline.
"""

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

from src.torrent_clients.qbittorrent import QbittorrentClientMixin


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _mixin() -> QbittorrentClientMixin:
    m = QbittorrentClientMixin()
    m.create_ssl_context_for_client = MagicMock(return_value=None)  # type: ignore[method-assign]
    return m


_CLIENT = {"qbit_url": "http://qbit.test", "qbit_port": 8080, "qui_proxy_url": ""}


def _session_factory(outcomes: list[Any]) -> Any:
    """aiohttp.ClientSession replacement: pops one outcome per instantiation.

    An Exception instance is raised on session.get(); an int becomes the
    response status.
    """

    def factory(*args: Any, **kwargs: Any) -> Any:
        outcome = outcomes.pop(0)
        session = MagicMock()
        session.__aenter__ = _async_return(session)
        session.__aexit__ = _async_return(False)
        if isinstance(outcome, Exception):
            session.get = MagicMock(side_effect=outcome)
        else:
            response = MagicMock(status=outcome)
            get_ctx = MagicMock()
            get_ctx.__aenter__ = _async_return(response)
            get_ctx.__aexit__ = _async_return(False)
            session.get = MagicMock(return_value=get_ctx)
        return session

    return factory


def _async_return(value: Any) -> Any:
    async def _inner(*args: Any, **kwargs: Any) -> Any:
        return value

    return _inner


class TestCheckQbitReachable:
    def test_succeeds_after_transient_failures(self):
        """Two failed probes then a 200 → reachable (the regression case)."""
        outcomes: list[Any] = [ConnectionError("slow"), ConnectionError("slow"), 200]
        with patch("src.torrent_clients.qbittorrent.aiohttp.ClientSession", side_effect=_session_factory(outcomes)), patch("src.torrent_clients.qbittorrent.asyncio.sleep", new=_async_return(None)):
            assert _run(_mixin()._check_qbit_reachable(_CLIENT)) is True
        assert not outcomes, "All three attempts should have been consumed"

    def test_all_attempts_fail_returns_false(self):
        outcomes: list[Any] = [ConnectionError("down")] * 3
        with patch("src.torrent_clients.qbittorrent.aiohttp.ClientSession", side_effect=_session_factory(outcomes)), patch("src.torrent_clients.qbittorrent.asyncio.sleep", new=_async_return(None)):
            assert _run(_mixin()._check_qbit_reachable(_CLIENT)) is False
        assert not outcomes, "All three probes should have been attempted"

    def test_first_probe_ok_no_retry(self):
        outcomes: list[Any] = [200]
        with patch("src.torrent_clients.qbittorrent.aiohttp.ClientSession", side_effect=_session_factory(outcomes)):
            assert _run(_mixin()._check_qbit_reachable(_CLIENT)) is True

    def test_gateway_error_retries(self):
        """502/503/504 from a proxy count as unreachable and must be retried."""
        for gateway_status in (502, 503, 504):
            outcomes: list[Any] = [gateway_status, 200]
            with patch("src.torrent_clients.qbittorrent.aiohttp.ClientSession", side_effect=_session_factory(outcomes)), patch("src.torrent_clients.qbittorrent.asyncio.sleep", new=_async_return(None)):
                assert _run(_mixin()._check_qbit_reachable(_CLIENT, attempts=2)) is True, f"{gateway_status} then 200 should be reachable"
            assert not outcomes, f"Both probes should have run for {gateway_status}"

    def test_http_500_is_unreachable(self):
        """A 500 from the API is not a healthy client: only 200/401/403 count."""
        outcomes: list[Any] = [500, 500]
        with patch("src.torrent_clients.qbittorrent.aiohttp.ClientSession", side_effect=_session_factory(outcomes)), patch("src.torrent_clients.qbittorrent.asyncio.sleep", new=_async_return(None)):
            assert _run(_mixin()._check_qbit_reachable(_CLIENT, attempts=2)) is False
        assert not outcomes

    def test_auth_statuses_are_reachable(self):
        """401/403 mean qBit is up but wants credentials → reachable."""
        for auth_status in (401, 403):
            outcomes: list[Any] = [auth_status]
            with patch("src.torrent_clients.qbittorrent.aiohttp.ClientSession", side_effect=_session_factory(outcomes)):
                assert _run(_mixin()._check_qbit_reachable(_CLIENT)) is True
