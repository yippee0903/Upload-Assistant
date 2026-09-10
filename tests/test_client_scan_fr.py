"""Client scan: French announce hosts are recognised, and a tool-linked upload whose root was renamed still counts."""

import asyncio
from types import SimpleNamespace
from typing import Any

from src.torrent_clients.qbittorrent import linked_size_match, local_content_sizes, match_tracker_url


def test_french_announce_hosts_flag_the_tracker_for_removal() -> None:
    for host, key in (("announce.v3x.club", "V3X"), ("draupnirr.xyz", "DRAU"), ("tk.c411.tw", "C411"), ("c411.org", "C411")):
        meta: dict[str, Any] = {"debug": False}
        asyncio.run(match_tracker_url([f"https://{host}/announce/passkey"], meta))
        assert meta["remove_trackers"] == [key], host


def test_linked_size_match(tmp_path: Any) -> None:
    folder = tmp_path / "Example.Release.2026.1080p-GRP"
    folder.mkdir()
    (folder / "Example.Release.2026.1080p-GRP.mkv").write_bytes(b"x" * 10)
    (folder / "Example.Release.2026.1080p-GRP.nfo").write_bytes(b"y" * 3)
    sizes = local_content_sizes({"path": str(folder), "source_size": 10})
    assert sizes == {10, 13}

    renamed = SimpleNamespace(content_path="/links/V3X/Renamed.Release.2026.VFF-GRP", total_size=13)
    assert linked_size_match(renamed, ["/links"], sizes)
    assert linked_size_match(SimpleNamespace(content_path="/links/V3X/Renamed.mkv", total_size=10), ["/links"], sizes)
    # outside the linked folders, or a different size: not ours
    assert not linked_size_match(SimpleNamespace(content_path="/elsewhere/Renamed.Release.2026.VFF-GRP", total_size=13), ["/links"], sizes)
    assert not linked_size_match(SimpleNamespace(content_path="/links/V3X/Renamed.Release.2026.VFF-GRP", total_size=12), ["/links"], sizes)
    assert not linked_size_match(SimpleNamespace(content_path="/links-other/x", total_size=13), ["/links"], sizes)
    assert not linked_size_match(renamed, [], sizes)
