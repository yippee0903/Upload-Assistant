"""Pre-upload client probe: a qBittorrent that died mid-run must block the uploads."""

import asyncio
from typing import Any

from src.clients import Clients


def _config(**defaults: Any) -> dict[str, Any]:
    return {
        "DEFAULT": {"default_torrent_client": "qbt", **defaults},
        "TORRENT_CLIENTS": {
            "qbt": {"torrent_client": "qbit", "qbit_url": "http://127.0.0.1", "qbit_port": 8080},
            "rt": {"torrent_client": "rtorrent"},
        },
    }


def _probe(clients: Clients, meta: dict[str, Any], reachable: bool) -> tuple[bool, list[str]]:
    probed: list[str] = []

    async def fake_check(client: dict[str, Any], **kwargs: Any) -> bool:
        probed.append(client["torrent_client"])
        return reachable

    clients._check_qbit_reachable = fake_check  # type: ignore[method-assign]
    return asyncio.run(clients.injection_clients_online(meta)), probed


def test_inject_client_names_falls_back_to_default() -> None:
    assert Clients(_config())._inject_client_names({"debug": False}) == ["qbt"]
    assert Clients(_config(injecting_client_list=["rt", "qbt"]))._inject_client_names({"debug": False}) == ["rt", "qbt"]
    assert Clients(_config())._inject_client_names({"debug": False, "client": "rt"}) == ["rt"]
    assert Clients(_config())._inject_client_names({"debug": False, "client": "none"}) is None


def test_offline_qbit_blocks_the_upload() -> None:
    online, probed = _probe(Clients(_config()), {"debug": False}, reachable=False)
    assert online is False
    assert probed == ["qbit"]


def test_only_qbit_clients_are_probed() -> None:
    online, probed = _probe(Clients(_config(injecting_client_list=["rt"])), {"debug": False}, reachable=False)
    assert online is True
    assert probed == []


def test_no_seed_skips_the_probe() -> None:
    online, probed = _probe(Clients(_config()), {"debug": False, "no_seed": True}, reachable=False)
    assert online is True
    assert probed == []
