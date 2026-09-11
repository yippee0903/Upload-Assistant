# An incomplete season pack must abort in --unattended (no -uac) instead of
# warning and uploading anyway.

import asyncio
from typing import Any

import pytest

from src.getseasonep import SeasonEpisodeManager

FILES = [f"/media/Example.Release.S01E{e:02d}.2026.1080p.WEB-GRP.mkv" for e in (1, 2, 4)]


def _manager(monkeypatch: Any, complete: bool) -> SeasonEpisodeManager:
    mgr = SeasonEpisodeManager({"DEFAULT": {"tmdb_api": "fake-key"}})

    async def detail(meta: Any) -> dict[str, Any]:
        return {"complete": complete, "missing_episodes": [] if complete else [(1, 3)], "consistent_tags": True, "tags_found": {"GRP": FILES}}

    async def homogeneity(meta: Any) -> dict[str, Any]:
        return {"homogeneous": True, "issues": {}}

    monkeypatch.setattr(mgr, "check_season_pack_detail", detail)
    monkeypatch.setattr(mgr, "check_pack_homogeneity", homogeneity)
    return mgr


def test_incomplete_pack_aborts_in_unattended(monkeypatch: Any) -> None:
    mgr = _manager(monkeypatch, complete=False)
    with pytest.raises(SystemExit):
        asyncio.run(mgr.check_season_pack_completeness({"filelist": FILES, "tv_pack": 1, "debug": False, "unattended": True}))


def test_complete_pack_passes_in_unattended(monkeypatch: Any) -> None:
    mgr = _manager(monkeypatch, complete=True)
    asyncio.run(mgr.check_season_pack_completeness({"filelist": FILES, "tv_pack": 1, "debug": False, "unattended": True}))
