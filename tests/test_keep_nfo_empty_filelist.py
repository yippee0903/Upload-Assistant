# Tests for torrentcreate.py keep_nfo + empty filelist regression
"""
Regression for Bug: Chicago.Fire.S12 TV pack results in NFO-only torrent
when meta["filelist"] is empty.

Before the fix, the keep_nfo branch built:
    include = [] + ["*.nfo"]   →  only NFO included
    exclude = ["*.*"]          →  all other extensions excluded

After the fix, when filelist is empty the branch falls back to extension
globs so that all video files + NFO are included.
"""

import asyncio
import os
import tempfile
import uuid
from pathlib import Path

import pytest


def _run(coro):
    return asyncio.run(coro)


def _make_pack(tmpdir: str) -> tuple[str, list[str]]:
    """Create a minimal TV-pack directory with two MKVs and one NFO."""
    pack_dir = os.path.join(tmpdir, "Chicago.Fire.S12.MULTi.1080p.WEB.H264-FW")
    os.makedirs(pack_dir)
    files = []
    for name in ("Chicago.Fire.S12E01.mkv", "Chicago.Fire.S12E02.mkv"):
        fpath = os.path.join(pack_dir, name)
        with open(fpath, "wb") as fh:
            fh.write(b"x" * 1024)
        files.append(fpath)
    with open(os.path.join(pack_dir, "Chicago.Fire.S12.nfo"), "w") as fh:
        fh.write("NFO")
    return pack_dir, files


def _base_meta(tmpdir: str, pack_dir: str, filelist: list) -> dict:
    run_uuid = str(uuid.uuid4())
    tmp_dir = os.path.join(tmpdir, "tmp", run_uuid)
    os.makedirs(tmp_dir)
    return {
        "uuid": run_uuid,
        "base_dir": tmpdir,
        "tv_pack": 1,
        "isdir": True,
        "is_disc": False,
        "keep_folder": False,
        "keep_nfo": True,
        "path": pack_dir,
        "filelist": filelist,
        "mkbrr": False,
        "debug": False,
        "max_piece_size": 0,
        "bloated_trackers": [],
    }


class TestKeepNfoEmptyFilelist:
    """keep_nfo=True with empty filelist must fall back to extension globs."""

    def test_empty_filelist_includes_video_files(self):
        """Regression: empty filelist must NOT produce an NFO-only torrent."""
        from src.torrentcreate import TorrentCreator
        from torf import Torrent

        with tempfile.TemporaryDirectory() as tmpdir:
            pack_dir, _ = _make_pack(tmpdir)
            meta = _base_meta(tmpdir, pack_dir, filelist=[])
            _run(TorrentCreator.create_torrent(meta, Path(pack_dir), "BASE"))

            torrent_path = os.path.join(tmpdir, "tmp", meta["uuid"], "BASE.torrent")
            assert os.path.exists(torrent_path), "BASE.torrent was not created"

            t = Torrent.read(torrent_path)
            names = [str(f) for f in t.files]
            mkv_files = [n for n in names if n.endswith(".mkv")]
            nfo_files = [n for n in names if n.endswith(".nfo")]

            assert len(mkv_files) == 2, f"Expected 2 MKV files, got: {names}"
            assert len(nfo_files) == 1, f"Expected 1 NFO file, got: {names}"

    def test_populated_filelist_includes_video_files(self):
        """Sanity: populated filelist must still include all video files + NFO."""
        from src.torrentcreate import TorrentCreator
        from torf import Torrent

        with tempfile.TemporaryDirectory() as tmpdir:
            pack_dir, real_files = _make_pack(tmpdir)
            meta = _base_meta(tmpdir, pack_dir, filelist=real_files)
            _run(TorrentCreator.create_torrent(meta, Path(pack_dir), "BASE"))

            torrent_path = os.path.join(tmpdir, "tmp", meta["uuid"], "BASE.torrent")
            assert os.path.exists(torrent_path), "BASE.torrent was not created"

            t = Torrent.read(torrent_path)
            names = [str(f) for f in t.files]
            mkv_files = [n for n in names if n.endswith(".mkv")]
            nfo_files = [n for n in names if n.endswith(".nfo")]

            assert len(mkv_files) == 2, f"Expected 2 MKV files, got: {names}"
            assert len(nfo_files) == 1, f"Expected 1 NFO file, got: {names}"

    def test_empty_filelist_nested_episodes_included(self):
        """Regression: MKV files inside a Season sub-folder must be in the torrent.

        Before the recursive-walk fix, the flat extension glob ``*.mkv`` only
        matched top-level files, so episode files placed under a ``Season 01/``
        sub-directory were silently omitted from the torrent.
        """
        from src.torrentcreate import TorrentCreator
        from torf import Torrent

        with tempfile.TemporaryDirectory() as tmpdir:
            pack_name = "Show.S01.1080p.WEB.H264-GRP"
            pack_dir = os.path.join(tmpdir, pack_name)
            season_dir = os.path.join(pack_dir, "Season 01")
            os.makedirs(season_dir)

            for name in ("Show.S01E01.mkv", "Show.S01E02.mkv"):
                with open(os.path.join(season_dir, name), "wb") as fh:
                    fh.write(b"x" * 512)

            with open(os.path.join(pack_dir, f"{pack_name}.nfo"), "w") as fh:
                fh.write("NFO")

            run_uuid = str(uuid.uuid4())
            tmp_dir = os.path.join(tmpdir, "tmp", run_uuid)
            os.makedirs(tmp_dir)
            meta = {
                "uuid": run_uuid,
                "base_dir": tmpdir,
                "tv_pack": 1,
                "isdir": True,
                "is_disc": False,
                "keep_folder": False,
                "keep_nfo": True,
                "path": pack_dir,
                "filelist": [],
                "mkbrr": False,
                "debug": False,
                "max_piece_size": 0,
                "bloated_trackers": [],
            }

            _run(TorrentCreator.create_torrent(meta, Path(pack_dir), "BASE"))

            torrent_path = os.path.join(tmp_dir, "BASE.torrent")
            assert os.path.exists(torrent_path), "BASE.torrent was not created"

            t = Torrent.read(torrent_path)
            names = [str(f) for f in t.files]
            mkv_files = [n for n in names if n.endswith(".mkv")]
            nfo_files = [n for n in names if n.endswith(".nfo")]

            assert len(mkv_files) == 2, f"Expected 2 nested MKV files, got: {names}"
            assert len(nfo_files) == 1, f"Expected 1 NFO file, got: {names}"
