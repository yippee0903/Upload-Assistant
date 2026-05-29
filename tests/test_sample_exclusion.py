"""Tests for sample-file exclusion in torrent creation.

torf include_globs take precedence over exclude_globs, so wildcard patterns like
``*.mkv`` in include_globs allow samples to slip in even when ``*sample.mkv``
appears in exclude_globs.  The fix uses explicit per-file relative-path patterns
derived from ``meta["filelist"]`` (which already excludes sample files).

Key scenarios tested:
  1. isdir, not keep_folder, single non-sample file → single-file torrent (no folder)
  2. isdir, not keep_folder, two non-sample files → folder torrent, samples excluded
  3. isdir, not keep_folder, keep_nfo=True → NFO included, sample excluded
  4. keep_folder=True, not keep_nfo → sample excluded (existing explicit-path logic)
  5. keep_folder=True, keep_nfo=True → NFO included, sample excluded
"""

import asyncio
import os
from pathlib import Path
from typing import Any

import pytest
import torf


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _make_meta(tmp_path: Path, **overrides: Any) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "base_dir": str(tmp_path),
        "uuid": "test-sample-uuid",
        "debug": False,
        "is_disc": False,
        "tv_pack": False,
        "keep_folder": False,
        "keep_nfo": False,
        "mkbrr": False,
        "max_piece_size": 0,
        "randomized": 0,
    }
    meta.update(overrides)
    # Ensure tmp dir exists
    torrent_dir = Path(meta["base_dir"]) / "tmp" / meta["uuid"]
    torrent_dir.mkdir(parents=True, exist_ok=True)
    return meta


def _torrent_files(torrent_path: str) -> list[str]:
    t = torf.Torrent.read(torrent_path)
    return [str(f) for f in t.files]


# ─────────────────────────────────────────────────────────────────────────────
#  1.  isdir, not keep_folder: single non-sample file → single-file torrent
# ─────────────────────────────────────────────────────────────────────────────


class TestIsdirsingleFile:
    """Single main MKV inside a folder (possibly alongside a Sample/ dir)."""

    def test_root_sample_hyphen_suffix_triggers_single_file_mode(self, tmp_path: Path) -> None:
        """Real-world case: sample-rough.mkv does NOT end with 'sample.mkv'.

        The old no_sample_globs filter (endswith 'sample.mkv') would count it as
        a non-sample file → 2 globs → folder torrent with one real file inside.
        The fix uses filelist (already filtered by video.py) as the source of truth.
        """
        from src.torrentcreate import TorrentCreator

        release = tmp_path / "Touch.Of.Evil.1958.RECONSTRUCTED.MULTi.1080p.BluRay.x264-ROUGH"
        release.mkdir()

        mkv = release / "touch.of.evil.1958.reconstructed.multi.1080p.bluray.x264-rough.mkv"
        mkv.write_bytes(b"FAKE_MKV" * 512)
        # sample whose name does NOT end with 'sample.mkv'
        sample = release / "touch.of.evil.1958.reconstructed.multi.1080p.bluray.x264.sample-rough.mkv"
        sample.write_bytes(b"SAMPLE" * 64)

        meta = _make_meta(
            tmp_path,
            filelist=[str(mkv)],  # video.py already excluded the sample
            isdir=True,
        )
        out = _run(TorrentCreator.create_torrent(meta, release, "BASE"))
        assert out is not None
        files = _torrent_files(str(Path(meta["base_dir"]) / "tmp" / meta["uuid"] / "BASE.torrent"))
        # Must be single-file mode: no folder prefix, no sample
        assert files == ["touch.of.evil.1958.reconstructed.multi.1080p.bluray.x264-rough.mkv"], (
            f"Expected single-file torrent without folder prefix; got {files}"
        )

    def test_single_mkv_no_sample_creates_single_file_torrent(self, tmp_path: Path) -> None:
        from src.torrentcreate import TorrentCreator

        release = tmp_path / "Movie.2024.1080p.BluRay-GRP"
        release.mkdir()
        mkv = release / "Movie.2024.1080p.BluRay-GRP.mkv"
        mkv.write_bytes(b"FAKE_MKV" * 512)

        meta = _make_meta(
            tmp_path,
            filelist=[str(mkv)],
            isdir=True,
        )
        out = _run(TorrentCreator.create_torrent(meta, release, "BASE"))
        assert out is not None
        files = _torrent_files(str(Path(meta["base_dir"]) / "tmp" / meta["uuid"] / "BASE.torrent"))
        # Single-file torrent: just the bare filename, no folder prefix
        assert files == ["Movie.2024.1080p.BluRay-GRP.mkv"]

    def test_sample_in_subdir_excluded_single_root_mkv(self, tmp_path: Path) -> None:
        """Root has one MKV; Sample/ subdir also has an MKV → single-file torrent."""
        from src.torrentcreate import TorrentCreator

        release = tmp_path / "Movie.2024.1080p.BluRay-GRP"
        release.mkdir()
        sample_dir = release / "Sample"
        sample_dir.mkdir()

        mkv = release / "Movie.2024.1080p.BluRay-GRP.mkv"
        mkv.write_bytes(b"FAKE_MKV" * 512)
        sample_mkv = sample_dir / "Movie.2024.1080p.BluRay-GRP.sample.mkv"
        sample_mkv.write_bytes(b"FAKE_SAMPLE" * 64)

        meta = _make_meta(
            tmp_path,
            # filelist already excludes sample (as video.py does at runtime)
            filelist=[str(mkv)],
            isdir=True,
        )
        out = _run(TorrentCreator.create_torrent(meta, release, "BASE"))
        assert out is not None
        files = _torrent_files(str(Path(meta["base_dir"]) / "tmp" / meta["uuid"] / "BASE.torrent"))
        assert "Movie.2024.1080p.BluRay-GRP.mkv" in " ".join(files)
        assert not any("sample" in f.lower() for f in files), \
            f"Sample file must not appear in torrent; got {files}"

    def test_root_sample_mkv_excluded_single_root_mkv(self, tmp_path: Path) -> None:
        """Both main MKV and sample.mkv in root → single-file torrent for main."""
        from src.torrentcreate import TorrentCreator

        release = tmp_path / "Movie.2024.1080p.BluRay-GRP"
        release.mkdir()

        mkv = release / "Movie.2024.1080p.BluRay-GRP.mkv"
        mkv.write_bytes(b"FAKE_MKV" * 512)
        sample = release / "Movie.2024.1080p.BluRay-GRP.sample.mkv"
        sample.write_bytes(b"SAMPLE" * 64)
        nfo = release / "Movie.2024.1080p.BluRay-GRP.nfo"
        nfo.write_bytes(b"[NFO]")

        meta = _make_meta(
            tmp_path,
            filelist=[str(mkv)],  # sample filtered by video.py
            isdir=True,
        )
        out = _run(TorrentCreator.create_torrent(meta, release, "BASE"))
        assert out is not None
        files = _torrent_files(str(Path(meta["base_dir"]) / "tmp" / meta["uuid"] / "BASE.torrent"))
        assert not any("sample" in f.lower() for f in files), \
            f"Sample must be excluded; got {files}"
        assert not any(f.lower().endswith(".nfo") for f in files), \
            f"NFO must be excluded when keep_nfo is False; got {files}"


# ─────────────────────────────────────────────────────────────────────────────
#  2.  isdir, not keep_folder: multiple non-sample files → folder torrent
# ─────────────────────────────────────────────────────────────────────────────


class TestIsdirMultiFile:
    """Multiple main MKVs (e.g. extras disc) — folder torrent, samples excluded."""

    def test_two_mkvs_no_sample_in_folder_torrent(self, tmp_path: Path) -> None:
        from src.torrentcreate import TorrentCreator

        release = tmp_path / "Movie.2024.Extras-GRP"
        release.mkdir()

        mkv1 = release / "Movie.2024.Part1-GRP.mkv"
        mkv2 = release / "Movie.2024.Part2-GRP.mkv"
        mkv1.write_bytes(b"FAKE_MKV1" * 512)
        mkv2.write_bytes(b"FAKE_MKV2" * 512)

        meta = _make_meta(
            tmp_path,
            filelist=[str(mkv1), str(mkv2)],
            isdir=True,
        )
        out = _run(TorrentCreator.create_torrent(meta, release, "BASE"))
        assert out is not None
        files = _torrent_files(str(Path(meta["base_dir"]) / "tmp" / meta["uuid"] / "BASE.torrent"))
        # Both MKVs included
        basenames = {os.path.basename(f) for f in files}
        assert "Movie.2024.Part1-GRP.mkv" in basenames
        assert "Movie.2024.Part2-GRP.mkv" in basenames

    def test_sample_in_subdir_excluded_when_two_main_mkvs(self, tmp_path: Path) -> None:
        """Two root MKVs + Sample subdir → folder torrent, Sample excluded."""
        from src.torrentcreate import TorrentCreator

        release = tmp_path / "Movie.2024.Extras-GRP"
        release.mkdir()
        sample_dir = release / "Sample"
        sample_dir.mkdir()

        mkv1 = release / "Movie.2024.Part1-GRP.mkv"
        mkv2 = release / "Movie.2024.Part2-GRP.mkv"
        mkv1.write_bytes(b"FAKE_MKV1" * 512)
        mkv2.write_bytes(b"FAKE_MKV2" * 512)
        (sample_dir / "sample.mkv").write_bytes(b"SAMPLE" * 64)

        meta = _make_meta(
            tmp_path,
            filelist=[str(mkv1), str(mkv2)],
            isdir=True,
        )
        out = _run(TorrentCreator.create_torrent(meta, release, "BASE"))
        assert out is not None
        files = _torrent_files(str(Path(meta["base_dir"]) / "tmp" / meta["uuid"] / "BASE.torrent"))
        assert not any("sample" in f.lower() for f in files), \
            f"Sample must be excluded; got {files}"
        assert len([f for f in files if f.endswith(".mkv")]) == 2


# ─────────────────────────────────────────────────────────────────────────────
#  3.  isdir, keep_nfo=True: NFO included, samples excluded
# ─────────────────────────────────────────────────────────────────────────────


class TestIsdirKeepNfo:
    def test_nfo_included_sample_excluded(self, tmp_path: Path) -> None:
        from src.torrentcreate import TorrentCreator

        release = tmp_path / "Movie.2024.1080p.BluRay-GRP"
        release.mkdir()
        sample_dir = release / "Sample"
        sample_dir.mkdir()

        mkv = release / "Movie.2024.1080p.BluRay-GRP.mkv"
        mkv.write_bytes(b"FAKE_MKV" * 512)
        nfo = release / "Movie.2024.1080p.BluRay-GRP.nfo"
        nfo.write_bytes(b"[NFO]")
        (sample_dir / "sample.mkv").write_bytes(b"SAMPLE" * 64)

        meta = _make_meta(
            tmp_path,
            filelist=[str(mkv)],
            isdir=True,
            keep_nfo=True,
        )
        out = _run(TorrentCreator.create_torrent(meta, release, "BASE"))
        assert out is not None
        files = _torrent_files(str(Path(meta["base_dir"]) / "tmp" / meta["uuid"] / "BASE.torrent"))
        assert any(f.lower().endswith(".nfo") for f in files), \
            f"NFO must be included when keep_nfo=True; got {files}"
        assert not any("sample" in f.lower() for f in files), \
            f"Sample must be excluded even with keep_nfo=True; got {files}"


# ─────────────────────────────────────────────────────────────────────────────
#  4.  keep_folder=True, keep_nfo=True: NFO included, samples excluded
# ─────────────────────────────────────────────────────────────────────────────


class TestKeepFolderKeepNfo:
    def test_nfo_included_sample_excluded(self, tmp_path: Path) -> None:
        from src.torrentcreate import TorrentCreator

        release = tmp_path / "Movie.2024.1080p.BluRay-GRP"
        release.mkdir()
        sample_dir = release / "Sample"
        sample_dir.mkdir()

        mkv = release / "Movie.2024.1080p.BluRay-GRP.mkv"
        mkv.write_bytes(b"FAKE_MKV" * 512)
        nfo = release / "Movie.2024.1080p.BluRay-GRP.nfo"
        nfo.write_bytes(b"[NFO]")
        (sample_dir / "sample.mkv").write_bytes(b"SAMPLE" * 64)

        meta = _make_meta(
            tmp_path,
            filelist=[str(mkv)],
            isdir=True,
            keep_folder=True,
            keep_nfo=True,
        )
        out = _run(TorrentCreator.create_torrent(meta, release, "BASE"))
        assert out is not None
        files = _torrent_files(str(Path(meta["base_dir"]) / "tmp" / meta["uuid"] / "BASE.torrent"))
        assert any(f.lower().endswith(".nfo") for f in files), \
            f"NFO must be included when keep_nfo=True; got {files}"
        assert not any("sample" in f.lower() for f in files), \
            f"Sample must be excluded with keep_folder+keep_nfo; got {files}"
