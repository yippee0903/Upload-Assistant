import asyncio

from src.clients import Clients


def test_skip_auto_torrent_short_circuits_client_search():
    clients = Clients({"DEFAULT": {"default_torrent_client": "none"}, "TRACKERS": {}})
    assert asyncio.run(clients.find_existing_torrent({"skip_auto_torrent": True})) is None
