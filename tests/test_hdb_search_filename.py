import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.trackers.HDB import HDB


def test_search_filename_returns_six_values_when_data_key_missing():
    hdb = HDB({"TRACKERS": {"HDB": {"username": "u", "passkey": "p"}}, "DEFAULT": {}})
    response = MagicMock(is_success=True)
    response.json.return_value = {"status": 5, "message": "nope"}
    client = AsyncMock()
    client.post.return_value = response
    client.__aenter__.return_value = client
    with patch("src.trackers.HDB.httpx.AsyncClient", return_value=client):
        result = asyncio.run(hdb.search_filename("/x/Anonymous.Release.2020.mkv", "file", {"is_disc": None}))
    assert result == (None, None, None, None, None, None)
