# Tests for the NFO-torrent flow optimisation
"""
Verifies the three-step flow introduced to eliminate redundant rehashing
when uploading to a mixed tracker set (skip_nfo + auto_nfo):

  Step 1 — BASE.torrent hashed WITH NFO
            upload.py proactively sets keep_nfo=True because an auto_nfo
            tracker (C411/V3X/…) is confirmed for upload and a .nfo
            file is present on disk.

  Step 2 — BASE_NONFO.torrent derived by *stripping* the NFO from BASE
            (TorrentCreator.strip_nfo_from_torrent).  Only the one piece
            that straddles the video/NFO boundary needs to be read from
            disk — no full rehash.

  Step 3 — auto_nfo trackers (C411, V3X) call _recreated_torrent_if_nfo;
            because BASE already contains the NFO they clone it directly
            via create_torrent_for_upload — no additional hash.

Supporting attribute tests:
  • FrenchTrackerMixin.auto_nfo is True
  • nfo_auto_trackers frozenset is built correctly
"""

import asyncio
import hashlib
import os
import struct
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ─── helpers ─────────────────────────────────────────────────


def _run(coro):
    return asyncio.run(coro)


def _sha1(data: bytes) -> bytes:
    return hashlib.sha1(data, usedforsecurity=False).digest()


def _bencode(obj: Any) -> bytes:
    """Minimal bencoder sufficient for building test .torrent files."""
    if isinstance(obj, bytes):
        return f"{len(obj)}:".encode() + obj
    if isinstance(obj, str):
        enc = obj.encode()
        return f"{len(enc)}:".encode() + enc
    if isinstance(obj, int):
        return f"i{obj}e".encode()
    if isinstance(obj, list):
        return b"l" + b"".join(_bencode(i) for i in obj) + b"e"
    if isinstance(obj, dict):
        # keys must be sorted for valid bencoding
        return b"d" + b"".join(_bencode(k) + _bencode(v) for k, v in sorted(obj.items())) + b"e"
    raise TypeError(f"Cannot bencode {type(obj)}")


def _make_torrent_bytes(
    name: str,
    files: list[tuple[list[str] | str, bytes]],  # (path_components_or_filename, data)
    piece_length: int = 256 * 1024,
) -> bytes:
    """Build a minimal valid multi-file .torrent payload.

    Computes real SHA-1 piece hashes over the concatenated file data so that
    strip_nfo_from_torrent / _patch_torrent_with_nfo can verify boundary pieces.

    ``path`` may be a list of path components or a plain filename string.
    """
    # Concatenate all file data in order
    all_data = b"".join(data for _, data in files)

    # Compute piece hashes
    pieces = b""
    for i in range(0, max(len(all_data), 1), piece_length):
        pieces += _sha1(all_data[i : i + piece_length])

    file_list = [
        {"length": len(data), "path": [path_parts] if isinstance(path_parts, str) else list(path_parts)}
        for path_parts, data in files
    ]

    info: dict[str, Any] = {
        "name": name,
        "piece length": piece_length,
        "pieces": pieces,
        "private": 1,
        "files": file_list,
    }
    torrent: dict[str, Any] = {
        "announce": "https://fake.tracker",
        "info": info,
    }
    return _bencode(torrent)


# ═══════════════════════════════════════════════════════════════
#  1. Attribute / frozenset tests
# ═══════════════════════════════════════════════════════════════


class TestAutoNfoAttribute:
    """FrenchTrackerMixin carries auto_nfo=True; nfo_auto_trackers is built from it."""

    def test_french_tracker_mixin_auto_nfo(self):
        from src.trackers.FRENCH import FrenchTrackerMixin
        assert getattr(FrenchTrackerMixin, "auto_nfo", False) is True

    def test_c411_inherits_auto_nfo(self):
        from src.trackers.C411 import C411
        assert getattr(C411, "auto_nfo", False) is True

    def test_v3x_inherits_auto_nfo(self):
        from src.trackers.V3X import V3X
        assert getattr(V3X, "auto_nfo", False) is True

    def test_nxm_inherits_auto_nfo(self):
        from src.trackers.NXM import NXM
        assert getattr(NXM, "auto_nfo", False) is True

    def test_nfo_auto_trackers_frozenset_is_frozenset(self):
        from src.trackersetup import nfo_auto_trackers
        assert isinstance(nfo_auto_trackers, frozenset)

    def test_nfo_auto_trackers_contains_expected(self):
        from src.trackersetup import nfo_auto_trackers
        # All French-mixin trackers must appear
        for tracker in ("C411", "V3X", "NXM", "GF", "G3MINI", "NST", "TOS"):
            assert tracker in nfo_auto_trackers, f"{tracker} missing from nfo_auto_trackers"

    def test_skip_nfo_trackers_not_in_auto_nfo(self):
        """Trackers with skip_nfo=True must not also be in nfo_auto_trackers."""
        from src.trackersetup import nfo_auto_trackers, nfo_skip_trackers
        overlap = nfo_skip_trackers & nfo_auto_trackers
        assert not overlap, f"Trackers in both sets: {overlap}"

    def test_non_french_trackers_not_in_auto_nfo(self):
        from src.trackersetup import nfo_auto_trackers
        for tracker in ("BLU", "AITHER", "DP", "LUME", "HDB", "PTP"):
            assert tracker not in nfo_auto_trackers, f"{tracker} should not be in nfo_auto_trackers"


# ═══════════════════════════════════════════════════════════════
#  2. strip_nfo_from_torrent
# ═══════════════════════════════════════════════════════════════


class TestStripNfoFromTorrent:
    """Unit tests for TorrentCreator.strip_nfo_from_torrent / _strip_nfo_sync."""

    def _make_release_dir(self, tmp_path: Path) -> tuple[Path, bytes, bytes]:
        """Create a tiny release folder with one .mkv and one .nfo."""
        release = tmp_path / "Movie.2024.1080p"
        release.mkdir()

        mkv_data = b"FAKE_MKV_CONTENT_" + bytes(range(256))  # 273 bytes
        nfo_data = b"[NFO]\nRelease info here.\n"

        (release / "Movie.2024.1080p.mkv").write_bytes(mkv_data)
        (release / "Movie.2024.1080p.nfo").write_bytes(nfo_data)
        return release, mkv_data, nfo_data

    def _write_torrent(self, path: Path, torrent_bytes: bytes) -> None:
        path.write_bytes(torrent_bytes)

    # ── happy path: NFO at the tail ──

    def test_strip_produces_torrent_without_nfo(self, tmp_path):
        from src.torrentcreate import TorrentCreator
        from torf import Torrent

        release, mkv_data, nfo_data = self._make_release_dir(tmp_path)
        name = release.name

        src_bytes = _make_torrent_bytes(
            name,
            [
                (["Movie.2024.1080p.mkv"], mkv_data),
                (["Movie.2024.1080p.nfo"], nfo_data),
            ],
        )
        src_path = tmp_path / "BASE.torrent"
        out_path = tmp_path / "BASE_NONFO.torrent"
        self._write_torrent(src_path, src_bytes)

        ok = _run(TorrentCreator.strip_nfo_from_torrent(str(src_path), str(out_path), str(release)))
        assert ok is True
        assert out_path.exists()

        t = Torrent.read(str(out_path))
        file_names = [str(f) for f in t.files]
        assert not any(f.lower().endswith(".nfo") for f in file_names), \
            f"NFO must not be present in stripped torrent; got {file_names}"
        assert any(f.lower().endswith(".mkv") for f in file_names), \
            "MKV must still be present in stripped torrent"

    def test_strip_idempotent_no_nfo(self, tmp_path):
        """Torrent without any NFO: strip writes a clean copy and returns True."""
        from src.torrentcreate import TorrentCreator
        from torf import Torrent

        release = tmp_path / "Movie.2024.1080p"
        release.mkdir()
        mkv_data = b"FAKE_MKV"
        (release / "Movie.2024.1080p.mkv").write_bytes(mkv_data)

        name = release.name
        src_bytes = _make_torrent_bytes(name, [(["Movie.2024.1080p.mkv"], mkv_data)])
        src_path = tmp_path / "BASE.torrent"
        out_path = tmp_path / "BASE_NONFO.torrent"
        self._write_torrent(src_path, src_bytes)

        ok = _run(TorrentCreator.strip_nfo_from_torrent(str(src_path), str(out_path), str(release)))
        assert ok is True
        assert out_path.exists()
        t = Torrent.read(str(out_path))
        assert len(list(t.files)) == 1

    def test_strip_fails_for_non_tail_nfo(self, tmp_path):
        """NFO appears before MKV → strip must return False (unsafe)."""
        from src.torrentcreate import TorrentCreator

        release = tmp_path / "Movie.2024.1080p"
        release.mkdir()
        mkv_data = b"FAKE_MKV_DATA"
        nfo_data = b"[NFO]"
        (release / "Movie.2024.1080p.mkv").write_bytes(mkv_data)
        (release / "Movie.2024.1080p.nfo").write_bytes(nfo_data)

        name = release.name
        # NFO listed BEFORE MKV — not at tail
        src_bytes = _make_torrent_bytes(
            name,
            [
                (["Movie.2024.1080p.nfo"], nfo_data),  # NFO first
                (["Movie.2024.1080p.mkv"], mkv_data),  # MKV after
            ],
        )
        src_path = tmp_path / "BASE.torrent"
        out_path = tmp_path / "BASE_NONFO.torrent"
        self._write_torrent(src_path, src_bytes)

        ok = _run(TorrentCreator.strip_nfo_from_torrent(str(src_path), str(out_path), str(release)))
        assert ok is False
        assert not out_path.exists()

    def test_strip_boundary_piece_hash_valid(self, tmp_path):
        """Verify that the boundary piece hash in the stripped torrent is correct.

        Uses mkv_data that does NOT align to a piece boundary so that
        _strip_nfo_sync must recompute the boundary hash from disk.
        """
        from src.torrentcreate import TorrentCreator
        from torf import Torrent

        release = tmp_path / "Movie.2024"
        release.mkdir()

        piece_length = 16 * 1024  # 16 KiB — smallest valid torf piece size
        # mkv spans 1 full piece + a partial second piece
        mkv_data = bytes(range(256)) * 85  # 21 760 bytes: piece 0 full (16 384), piece 1 partial (5 376)
        nfo_data = b"[NFO] release notes"  # appended into piece 1 → boundary recompute needed

        (release / "movie.mkv").write_bytes(mkv_data)
        (release / "movie.nfo").write_bytes(nfo_data)

        name = release.name
        src_bytes = _make_torrent_bytes(
            name,
            [("movie.mkv", mkv_data), ("movie.nfo", nfo_data)],
            piece_length=piece_length,
        )
        src_path = tmp_path / "BASE.torrent"
        out_path = tmp_path / "BASE_NONFO.torrent"
        self._write_torrent(src_path, src_bytes)

        ok = _run(TorrentCreator.strip_nfo_from_torrent(str(src_path), str(out_path), str(release)))
        assert ok is True

        t = Torrent.read(str(out_path))
        raw_pieces: bytes = t.metainfo["info"]["pieces"]

        # Piece 0 covers bytes 0..(piece_length-1) of mkv_data — unchanged from src
        expected_piece0 = _sha1(mkv_data[:piece_length])
        assert raw_pieces[:20] == expected_piece0

        # Piece 1 covers the remaining mkv bytes only (NFO stripped)
        expected_piece1 = _sha1(mkv_data[piece_length:])
        assert raw_pieces[20:40] == expected_piece1

        # No more pieces (NFO data discarded)
        assert len(raw_pieces) == 40

    def test_strip_exact_boundary_no_disk_read(self, tmp_path):
        """NFO starts on an exact piece boundary: no disk read needed, all hashes kept."""
        from src.torrentcreate import TorrentCreator
        from torf import Torrent

        release = tmp_path / "Movie.2024"
        release.mkdir()

        piece_length = 16 * 1024  # 16 KiB — smallest valid torf piece size
        mkv_data = bytes(range(256)) * (piece_length // 256)  # exactly piece_length bytes
        nfo_data = b"NFO_CONTENT"  # sits entirely in the second piece

        (release / "movie.mkv").write_bytes(mkv_data)
        (release / "movie.nfo").write_bytes(nfo_data)

        name = release.name
        src_bytes = _make_torrent_bytes(
            name,
            [("movie.mkv", mkv_data), ("movie.nfo", nfo_data)],
            piece_length=piece_length,
        )
        src_path = tmp_path / "BASE.torrent"
        out_path = tmp_path / "BASE_NONFO.torrent"
        self._write_torrent(src_path, src_bytes)

        ok = _run(TorrentCreator.strip_nfo_from_torrent(str(src_path), str(out_path), str(release)))
        assert ok is True

        t = Torrent.read(str(out_path))
        raw_pieces: bytes = t.metainfo["info"]["pieces"]
        # Only the mkv piece remains; its hash must match
        assert raw_pieces == _sha1(mkv_data)

    def test_strip_returns_false_on_corrupt_torrent(self, tmp_path):
        """Corrupt torrent bytes → strip returns False without raising."""
        from src.torrentcreate import TorrentCreator

        src_path = tmp_path / "BASE.torrent"
        out_path = tmp_path / "BASE_NONFO.torrent"
        src_path.write_bytes(b"NOT_A_TORRENT")

        ok = _run(TorrentCreator.strip_nfo_from_torrent(str(src_path), str(out_path), "/tmp"))
        assert ok is False

    def test_strip_returns_false_for_single_file_torrent(self, tmp_path):
        """Single-file torrent (info.length present, no info.files) → strip returns False.

        _strip_nfo_sync only handles multi-file torrents; a single-file torrent
        has no NFO entry to strip so False is the safe/correct answer.
        """
        from src.torrentcreate import TorrentCreator

        release = tmp_path / "Movie.2024.1080p"
        release.mkdir()
        mkv_data = b"FAKE_MKV_CONTENT"
        (release / "Movie.2024.1080p.mkv").write_bytes(mkv_data)

        piece_length = 256 * 1024
        pieces = _sha1(mkv_data)
        info: dict = {
            "name": "Movie.2024.1080p.mkv",
            "piece length": piece_length,
            "pieces": pieces,
            "length": len(mkv_data),  # single-file: length, not files
        }
        torrent_bytes = _bencode({"info": info})

        src_path = tmp_path / "BASE.torrent"
        out_path = tmp_path / "BASE_NONFO.torrent"
        src_path.write_bytes(torrent_bytes)

        ok = _run(TorrentCreator.strip_nfo_from_torrent(str(src_path), str(out_path), str(release)))
        assert ok is False, "Single-file torrent must return False"
        assert not out_path.exists(), "No output file must be written for single-file torrent"

    def test_strip_returns_false_for_nfo_only_torrent(self, tmp_path):
        """Torrent whose only file is the .nfo → strip returns False.

        After removing all NFO entries there would be nothing left; _strip_nfo_sync
        must detect this (no non-NFO files) and return False rather than creating
        an empty torrent.
        """
        from src.torrentcreate import TorrentCreator

        release = tmp_path / "Release.2024"
        release.mkdir()
        nfo_data = b"[NFO content]"
        (release / "release.nfo").write_bytes(nfo_data)

        name = release.name
        src_bytes = _make_torrent_bytes(name, [("release.nfo", nfo_data)])

        src_path = tmp_path / "BASE.torrent"
        out_path = tmp_path / "BASE_NONFO.torrent"
        src_path.write_bytes(src_bytes)

        ok = _run(TorrentCreator.strip_nfo_from_torrent(str(src_path), str(out_path), str(release)))
        assert ok is False, "NFO-only torrent must return False (nothing left after strip)"
        assert not out_path.exists(), "No output file must be written for NFO-only torrent"


# ═══════════════════════════════════════════════════════════════
#  3. Step 1 — proactive keep_nfo in upload.py
# ═══════════════════════════════════════════════════════════════


class TestProactiveKeepNfo:
    """upload.py sets keep_nfo=True before BASE creation when an auto_nfo tracker
    is confirmed and a .nfo file exists on disk."""

    def _make_meta(
        self,
        tmp_path: Path,
        trackers: list[str],
        tracker_upload_flags: dict[str, bool],
        has_nfo_on_disk: bool,
        keep_nfo_initial: bool = False,
        is_disc: bool = False,
    ) -> dict[str, Any]:
        # Create content directory
        content_dir = tmp_path / "release"
        content_dir.mkdir()
        (content_dir / "movie.mkv").write_bytes(b"FAKE")
        if has_nfo_on_disk:
            (content_dir / "movie.nfo").write_bytes(b"[NFO]")

        tracker_status: dict[str, Any] = {
            t: {"upload": tracker_upload_flags.get(t, False)} for t in trackers
        }
        return {
            "trackers": trackers,
            "tracker_status": tracker_status,
            "keep_nfo": keep_nfo_initial,
            "is_disc": is_disc,
            "path": str(content_dir),
            "debug": False,
        }

    def _run_proactive_detection(self, meta: dict[str, Any]) -> dict[str, Any]:
        """Call the real determine_keep_nfo helper from src.trackersetup."""
        from src.trackersetup import determine_keep_nfo

        raw_trackers = meta.get("trackers")
        if isinstance(raw_trackers, str):
            target_trackers = [raw_trackers]
        elif isinstance(raw_trackers, list):
            target_trackers = [str(t) for t in raw_trackers if str(t).strip()]
        else:
            target_trackers = []

        tracker_status = meta.get("tracker_status", {})

        if determine_keep_nfo(meta, tracker_status, target_trackers):
            meta["keep_nfo"] = True

        return meta

    def test_auto_nfo_tracker_confirmed_nfo_on_disk_sets_keep_nfo(self, tmp_path):
        meta = self._make_meta(
            tmp_path,
            trackers=["C411", "DP"],
            tracker_upload_flags={"C411": True, "DP": True},
            has_nfo_on_disk=True,
        )
        result = self._run_proactive_detection(meta)
        assert result["keep_nfo"] is True

    def test_no_nfo_on_disk_keep_nfo_stays_false(self, tmp_path):
        meta = self._make_meta(
            tmp_path,
            trackers=["C411", "DP"],
            tracker_upload_flags={"C411": True, "DP": True},
            has_nfo_on_disk=False,
        )
        result = self._run_proactive_detection(meta)
        assert result["keep_nfo"] is False

    def test_only_skip_nfo_tracker_does_not_set_keep_nfo(self, tmp_path):
        """DP alone (skip_nfo tracker, not auto_nfo) must not set keep_nfo."""
        meta = self._make_meta(
            tmp_path,
            trackers=["DP", "LUME"],
            tracker_upload_flags={"DP": True, "LUME": True},
            has_nfo_on_disk=True,
        )
        result = self._run_proactive_detection(meta)
        assert result["keep_nfo"] is False

    def test_auto_nfo_tracker_not_confirmed_does_not_set_keep_nfo(self, tmp_path):
        """C411 in tracker list but upload=False — keep_nfo must not be set."""
        meta = self._make_meta(
            tmp_path,
            trackers=["C411", "DP"],
            tracker_upload_flags={"C411": False, "DP": True},
            has_nfo_on_disk=True,
        )
        result = self._run_proactive_detection(meta)
        assert result["keep_nfo"] is False

    def test_disc_release_skipped(self, tmp_path):
        """is_disc=True: proactive detection must not touch keep_nfo."""
        meta = self._make_meta(
            tmp_path,
            trackers=["C411"],
            tracker_upload_flags={"C411": True},
            has_nfo_on_disk=True,
            is_disc=True,
        )
        result = self._run_proactive_detection(meta)
        assert result["keep_nfo"] is False

    def test_already_set_keep_nfo_not_overwritten(self, tmp_path):
        """keep_nfo already True → block is skipped entirely (no regression)."""
        meta = self._make_meta(
            tmp_path,
            trackers=["C411"],
            tracker_upload_flags={"C411": True},
            has_nfo_on_disk=False,  # no nfo on disk — would normally stay False
            keep_nfo_initial=True,
        )
        result = self._run_proactive_detection(meta)
        assert result["keep_nfo"] is True  # preserved as-is

    def test_v3x_confirmed_sets_keep_nfo(self, tmp_path):
        meta = self._make_meta(
            tmp_path,
            trackers=["V3X", "LUME"],
            tracker_upload_flags={"V3X": True, "LUME": True},
            has_nfo_on_disk=True,
        )
        result = self._run_proactive_detection(meta)
        assert result["keep_nfo"] is True


# ═══════════════════════════════════════════════════════════════
#  4. Step 2 — BASE_NONFO created via strip, not full rehash
# ═══════════════════════════════════════════════════════════════


class TestBaseNonfoStrip:
    """upload.py tries strip_nfo_from_torrent before falling back to full rehash
    when building BASE_NONFO.torrent."""

    def _make_base_torrent(
        self, tmp_path: Path, with_nfo: bool = True, two_mkvs: bool = False
    ) -> tuple[Path, Path, str]:
        """Write a minimal BASE.torrent into tmp_path/tmp/<uuid>/.

        two_mkvs=True creates a second MKV so the torrent has 2 non-NFO files,
        which keeps the 'strip' code-path active under the new single-file guard.
        """
        uuid = "test-uuid-nonfo"
        torrent_dir = tmp_path / "tmp" / uuid
        torrent_dir.mkdir(parents=True)

        release = tmp_path / "Movie.2024.1080p"
        release.mkdir(exist_ok=True)
        mkv_data = b"FAKE_MKV" * 10
        nfo_data = b"[NFO] release"
        (release / "Movie.2024.1080p.mkv").write_bytes(mkv_data)
        if with_nfo:
            (release / "Movie.2024.1080p.nfo").write_bytes(nfo_data)

        files = [([release.name, "Movie.2024.1080p.mkv"], mkv_data)]
        if two_mkvs:
            mkv2_data = b"FAKE_MKV2" * 10
            (release / "Movie.2024.1080p.Extras.mkv").write_bytes(mkv2_data)
            files.append(([release.name, "Movie.2024.1080p.Extras.mkv"], mkv2_data))
        if with_nfo:
            files.append(([release.name, "Movie.2024.1080p.nfo"], nfo_data))

        torrent_bytes = _make_torrent_bytes(release.name, files)
        base_path = torrent_dir / "BASE.torrent"
        base_path.write_bytes(torrent_bytes)
        return base_path, release, uuid

    def test_single_video_nfo_calls_create_torrent_directly(self, tmp_path):
        """Single MKV + NFO in BASE: after stripping the NFO there would be only
        one file left.  The new logic must call create_torrent directly (single-
        file mode) rather than strip, so the tracker gets a proper single-file
        torrent (no folder wrapper)."""
        from src.torrentcreate import TorrentCreator

        # 1 MKV + 1 NFO
        base_path, release, uuid = self._make_base_torrent(tmp_path, with_nfo=True, two_mkvs=False)
        nonfo_path = base_path.parent / "BASE_NONFO.torrent"

        strip_calls = []
        create_torrent_calls = []

        async def fake_strip(src, out, content):
            strip_calls.append(src)
            return True

        async def fake_create_torrent(meta, path, output_filename, **kw):
            create_torrent_calls.append(output_filename)
            nonfo_path.write_bytes(b"FAKE_NONFO")

        with patch.object(TorrentCreator, "strip_nfo_from_torrent", side_effect=fake_strip), \
             patch.object(TorrentCreator, "create_torrent", side_effect=fake_create_torrent):
            _run(self._run_base_nonfo_block(base_path, nonfo_path, str(release)))

        assert strip_calls == [], "strip must NOT be called for single-video+NFO release"
        assert "BASE_NONFO" in create_torrent_calls, \
            "create_torrent must be called directly to produce a single-file torrent"

    def test_strip_called_before_create_torrent_when_base_has_nfo(self, tmp_path):
        """When BASE has NFO and multiple video files, strip_nfo_from_torrent is
        called and succeeds → create_torrent must NOT be called."""
        from src.torrentcreate import TorrentCreator

        # two_mkvs=True so the single-file guard does not fire
        base_path, release, uuid = self._make_base_torrent(tmp_path, with_nfo=True, two_mkvs=True)
        nonfo_path = base_path.parent / "BASE_NONFO.torrent"

        create_torrent_calls = []

        async def fake_strip(src, out, content):
            # Write a dummy output to simulate success
            Path(out).write_bytes(Path(src).read_bytes())
            return True

        async def fake_create_torrent(*a, **kw):
            create_torrent_calls.append((a, kw))

        with patch.object(TorrentCreator, "strip_nfo_from_torrent", side_effect=fake_strip), \
             patch.object(TorrentCreator, "create_torrent", side_effect=fake_create_torrent):
            # Simulate the BASE_NONFO creation block from upload.py
            _run(self._run_base_nonfo_block(base_path, nonfo_path, str(release)))

        assert nonfo_path.exists()
        assert create_torrent_calls == [], \
            "create_torrent must NOT be called when strip succeeds"

    def test_create_torrent_called_when_strip_fails(self, tmp_path):
        """When strip returns False, create_torrent is called as fallback."""
        from src.torrentcreate import TorrentCreator

        # two_mkvs=True so we reach the strip path (single-file guard skipped)
        base_path, release, uuid = self._make_base_torrent(tmp_path, with_nfo=True, two_mkvs=True)
        nonfo_path = base_path.parent / "BASE_NONFO.torrent"

        create_torrent_calls = []

        async def fake_strip(src, out, content):
            return False  # strip fails

        async def fake_create_torrent(meta, path, output_filename, **kw):
            create_torrent_calls.append(output_filename)
            # Write dummy file so the block sees it
            nonfo_path.write_bytes(b"FAKE_NONFO")

        with patch.object(TorrentCreator, "strip_nfo_from_torrent", side_effect=fake_strip), \
             patch.object(TorrentCreator, "create_torrent", side_effect=fake_create_torrent):
            _run(self._run_base_nonfo_block(base_path, nonfo_path, str(release)))

        assert "BASE_NONFO" in create_torrent_calls, \
            "create_torrent must be called with 'BASE_NONFO' as fallback"

    def test_strip_not_called_when_base_has_no_nfo(self, tmp_path):
        """BASE without NFO: strip must not be called, no BASE_NONFO created."""
        from src.torrentcreate import TorrentCreator

        base_path, release, uuid = self._make_base_torrent(tmp_path, with_nfo=False)
        nonfo_path = base_path.parent / "BASE_NONFO.torrent"

        strip_calls = []

        async def fake_strip(src, out, content):
            strip_calls.append(src)
            return True

        with patch.object(TorrentCreator, "strip_nfo_from_torrent", side_effect=fake_strip):
            _run(self._run_base_nonfo_block(base_path, nonfo_path, str(release), skip_nfo=True))

        assert strip_calls == [], "strip must not be called when BASE has no NFO"
        assert not nonfo_path.exists()

    @staticmethod
    async def _run_base_nonfo_block(
        base_path: Path,
        nonfo_path: Path,
        content_path: str,
        skip_nfo: bool = True,
        tv_pack: bool = False,
        is_disc: bool = False,
    ) -> None:
        """Reproduce the BASE_NONFO creation block from upload.py.

        NOTE: nonfo_path is defined BEFORE the try block (matching upload.py)
        so that tests catch any NameError regression if the definition drifts
        back inside the try.
        """
        import asyncio
        from torf import Torrent
        from src.torrentcreate import TorrentCreator

        if not base_path.exists() or not skip_nfo:
            return

        meta: dict[str, Any] = {"path": content_path, "debug": False, "tv_pack": tv_pack, "is_disc": is_disc}
        try:
            base_t = await asyncio.to_thread(Torrent.read, str(base_path))
            if not any(str(f).lower().endswith(".nfo") for f in base_t.files):
                return

            if nonfo_path.exists():
                return

            # If stripping the NFO would leave only one video file, create a proper
            # single-file torrent directly instead of a folder-wrapped single-file.
            non_nfo_files = [f for f in base_t.files if not str(f).lower().endswith(".nfo")]
            needs_single_file = (
                len(non_nfo_files) == 1
                and not meta.get("tv_pack", False)
                and not meta.get("is_disc", False)
            )
            if needs_single_file:
                await TorrentCreator.create_torrent(meta, Path(content_path), "BASE_NONFO")
            else:
                stripped = await TorrentCreator.strip_nfo_from_torrent(
                    str(base_path), str(nonfo_path), content_path
                )
                if not stripped:
                    await TorrentCreator.create_torrent(meta, Path(content_path), "BASE_NONFO")
            if nonfo_path.exists():
                meta["base_nonfo_path"] = str(nonfo_path)
        except Exception:
            await TorrentCreator.create_torrent(meta, Path(content_path), "BASE_NONFO")
            if nonfo_path.exists():
                meta["base_nonfo_path"] = str(nonfo_path)

    def test_torrent_read_raises_falls_back_to_full_rehash(self, tmp_path):
        """If Torrent.read raises, the except block must fall back to full rehash
        and set meta['base_nonfo_path'] when the output file is created."""
        from torf import Torrent
        from src.torrentcreate import TorrentCreator

        base_path, release, uuid = self._make_base_torrent(tmp_path, with_nfo=True)
        nonfo_path = base_path.parent / "BASE_NONFO.torrent"

        create_torrent_calls = []

        async def fake_create_torrent(meta, path, output_filename, **kw):
            create_torrent_calls.append(output_filename)
            nonfo_path.write_bytes(b"FAKE_NONFO")

        with patch.object(Torrent, "read", side_effect=OSError("disk error")), \
             patch.object(TorrentCreator, "create_torrent", side_effect=fake_create_torrent):
            _run(self._run_base_nonfo_block(base_path, nonfo_path, str(release)))

        assert "BASE_NONFO" in create_torrent_calls, \
            "Full rehash must be triggered when Torrent.read raises"
        assert nonfo_path.exists(), "BASE_NONFO.torrent must exist after fallback rehash"

    def test_strip_raises_falls_back_to_full_rehash(self, tmp_path):
        """If strip_nfo_from_torrent raises, the except block must fall back to
        full rehash and set meta['base_nonfo_path'] when the output file exists."""
        from src.torrentcreate import TorrentCreator

        # two_mkvs=True so we reach the strip path (single-file guard skipped)
        base_path, release, uuid = self._make_base_torrent(tmp_path, with_nfo=True, two_mkvs=True)
        nonfo_path = base_path.parent / "BASE_NONFO.torrent"

        create_torrent_calls = []

        async def fake_strip(*a, **kw):
            raise RuntimeError("strip exploded")

        async def fake_create_torrent(meta, path, output_filename, **kw):
            create_torrent_calls.append(output_filename)
            nonfo_path.write_bytes(b"FAKE_NONFO")

        with patch.object(TorrentCreator, "strip_nfo_from_torrent", side_effect=fake_strip), \
             patch.object(TorrentCreator, "create_torrent", side_effect=fake_create_torrent):
            _run(self._run_base_nonfo_block(base_path, nonfo_path, str(release)))

        assert "BASE_NONFO" in create_torrent_calls, \
            "Full rehash must be triggered when strip_nfo_from_torrent raises"
        assert nonfo_path.exists(), "BASE_NONFO.torrent must exist after fallback rehash"


# ═══════════════════════════════════════════════════════════════
#  5. Step 3 — _recreated_torrent_if_nfo clones BASE (no extra hash)
# ═══════════════════════════════════════════════════════════════


class TestRecreateTorrentIfNfoNoExtraHash:
    """_recreated_torrent_if_nfo: when BASE already has NFO it must call
    create_torrent_for_upload (clone) instead of TorrentCreator.create_torrent
    (full hash)."""

    def _setup(self, tmp_path: Path, tracker: str) -> tuple[dict[str, Any], Any]:
        from src.trackers.C411 import C411
        from src.trackers.V3X import V3X

        cls = C411 if tracker == "C411" else V3X
        config = {
            "TRACKERS": {tracker: {"api_key": "fake", "announce_url": "https://fake.tracker/announce"}},
            "DEFAULT": {"tmdb_api": "fake", "rehash_cooldown": 0},
        }
        tracker_obj = cls(config)

        # Build a release dir with MKV + NFO
        release_dir = tmp_path / f"Movie.2024.{tracker}"
        release_dir.mkdir()
        mkv_data = b"FAKE_MKV_DATA"
        nfo_data = b"[NFO]"
        (release_dir / "movie.mkv").write_bytes(mkv_data)
        nfo_path = release_dir / "movie.nfo"
        nfo_path.write_bytes(nfo_data)

        # Write BASE.torrent WITH NFO already embedded
        uuid = f"uuid-{tracker}"
        torrent_dir = tmp_path / "tmp" / uuid
        torrent_dir.mkdir(parents=True)
        name = release_dir.name
        torrent_bytes = _make_torrent_bytes(
            name,
            [([name, "movie.mkv"], mkv_data), ([name, "movie.nfo"], nfo_data)],
        )
        (torrent_dir / "BASE.torrent").write_bytes(torrent_bytes)

        meta = {
            "base_dir": str(tmp_path),
            "uuid": uuid,
            "path": str(release_dir),
            "debug": False,
            "tracker_status": {tracker: {}},
            "mkbrr": False,
        }
        return meta, tracker_obj

    @pytest.mark.parametrize("tracker", ["C411", "V3X"])
    def test_clone_used_when_base_has_nfo(self, tmp_path, tracker):
        """BASE has NFO → create_torrent_for_upload (clone) called, TorrentCreator.create_torrent NOT called."""
        from src.trackers.COMMON import COMMON
        from src.torrentcreate import TorrentCreator

        meta, tracker_obj = self._setup(tmp_path, tracker)
        source_flag = tracker_obj.source_flag

        clone_calls: list[str] = []
        full_hash_calls: list[str] = []

        async def fake_clone(m, trk, sflag, **kw):
            clone_calls.append(trk)
            # Write the tracker torrent file so the caller can proceed
            out = Path(m["base_dir"]) / "tmp" / m["uuid"] / f"[{trk}].torrent"
            out.write_bytes(b"FAKE_TRACKER_TORRENT")

        async def fake_create_torrent(*a, **kw):
            full_hash_calls.append(kw.get("output_filename", a[2] if len(a) > 2 else "?"))

        with patch.object(COMMON, "create_torrent_for_upload", side_effect=fake_clone), \
             patch.object(TorrentCreator, "create_torrent", side_effect=fake_create_torrent):

            nfo_files = tracker_obj._get_nfo_files(meta)
            assert nfo_files, "Test setup: NFO files must be detected"

            _run(tracker_obj._recreated_torrent_if_nfo(
                meta, tracker_obj.common, tracker_obj.config, tracker, source_flag
            ))

        assert clone_calls == [tracker], \
            f"create_torrent_for_upload must be called once with tracker={tracker!r}"
        assert full_hash_calls == [], \
            "TorrentCreator.create_torrent (full hash) must NOT be called"

    @pytest.mark.parametrize("tracker", ["C411", "V3X"])
    def test_full_hash_used_when_base_has_no_nfo(self, tmp_path, tracker):
        """BASE without NFO → _recreated_torrent_if_nfo falls back to full hash."""
        from src.trackers.COMMON import COMMON
        from src.torrentcreate import TorrentCreator

        meta, tracker_obj = self._setup(tmp_path, tracker)
        source_flag = tracker_obj.source_flag

        # Overwrite BASE.torrent with one that has NO NFO
        uuid = meta["uuid"]
        release_dir = Path(meta["path"])
        name = release_dir.name
        torrent_dir = Path(meta["base_dir"]) / "tmp" / uuid
        mkv_data = (release_dir / "movie.mkv").read_bytes()
        torrent_bytes = _make_torrent_bytes(name, [([name, "movie.mkv"], mkv_data)])
        (torrent_dir / "BASE.torrent").write_bytes(torrent_bytes)

        clone_calls: list[str] = []
        full_hash_calls: list[str] = []

        async def fake_clone(m, trk, sflag, **kw):
            clone_calls.append(trk)
            out = Path(m["base_dir"]) / "tmp" / m["uuid"] / f"[{trk}].torrent"
            out.write_bytes(b"FAKE_TRACKER_TORRENT")

        async def fake_create_torrent(m, path, output_filename, **kw):
            full_hash_calls.append(output_filename)
            out = Path(m["base_dir"]) / "tmp" / m["uuid"] / f"{output_filename}.torrent"
            out.write_bytes(b"FAKE_HASHED_TORRENT")

        with patch.object(COMMON, "create_torrent_for_upload", side_effect=fake_clone), \
             patch.object(TorrentCreator, "create_torrent", side_effect=fake_create_torrent):

            nfo_files = tracker_obj._get_nfo_files(meta)
            assert nfo_files, "Test setup: NFO files must be detected"

            _run(tracker_obj._recreated_torrent_if_nfo(
                meta, tracker_obj.common, tracker_obj.config, tracker, source_flag
            ))

        # BASE has no NFO → no existing-torrent-with-NFO shortcut → exactly 1 full hash
        assert len(full_hash_calls) == 1, \
            f"Expected exactly 1 create_torrent call when BASE has no NFO; got {full_hash_calls}"
        assert not (full_hash_calls and tracker in clone_calls), \
            "When a full rehash runs, create_torrent_for_upload (clone) must NOT also run"


# ═══════════════════════════════════════════════════════════════
#  6. qBittorrent injection: src/save_path for skip_nfo multi-file torrent
# ═══════════════════════════════════════════════════════════════


class TestResolveSrcAndSavePath:
    """_resolve_src_and_save_path: covers the LUME 'missing files' bug.

    Before the fix: single_file=True caused src=meta["filelist"][0] even when
    the tracker torrent was still multi-file after NFO stripping.  qBittorrent
    created save_path/ReleaseName/ (the directory) but found nothing inside
    because the file was linked directly as save_path/movie.mkv.

    After the fix: torrent_is_multi_file is detected and the directory is used
    as src so async_link_directory creates save_path/ReleaseName/movie.mkv.
    """

    def _make_torrent_obj(self, *, multi_file: bool):
        """Return a minimal Torrent-like mock with the right metainfo structure."""
        t = MagicMock()
        if multi_file:
            t.metainfo = {"info": {"files": [{"length": 1, "path": ["movie.mkv"]}]}}
        else:
            t.metainfo = {"info": {"length": 1}}
        return t

    def _make_meta(self, tmp_path: Path, *, keep_nfo: bool = False, keep_folder: bool = False):
        release_dir = tmp_path / "Double.Indemnity.1944.MULTi.1080p.BluRay.x264-FiDELiO"
        release_dir.mkdir()
        mkv = release_dir / "movie.mkv"
        mkv.write_bytes(b"FAKE")
        return {
            "path": str(release_dir),
            "filelist": [str(mkv)],
            "keep_nfo": keep_nfo,
            "keep_folder": keep_folder,
        }

    def test_lume_single_file_single_file_torrent_uses_file_src(self, tmp_path):
        """Classic case (no keep_nfo): single-file torrent → src = the mkv file."""
        from src.torrent_clients.qbittorrent import QbittorrentClientMixin as QbittorrentClient

        meta = self._make_meta(tmp_path, keep_nfo=False)
        torrent = self._make_torrent_obj(multi_file=False)
        path = meta["path"]  # release dir (save_path already adjusted by caller)

        src, _ = QbittorrentClient._resolve_src_and_save_path(path, torrent, meta, "LUME")

        assert src == meta["filelist"][0], "single-file torrent must use the mkv as src"

    def test_lume_single_file_multi_file_torrent_uses_dir_src(self, tmp_path):
        """Bug scenario (keep_nfo=True + skip_nfo tracker):
        torrent is still multi-file after NFO strip → src must be the release directory."""
        from src.torrent_clients.qbittorrent import QbittorrentClientMixin as QbittorrentClient

        meta = self._make_meta(tmp_path, keep_nfo=True)
        torrent = self._make_torrent_obj(multi_file=True)
        path = meta["path"]  # release dir (already normalised by caller)

        src, _ = QbittorrentClient._resolve_src_and_save_path(path, torrent, meta, "LUME")

        assert src == path, (
            "multi-file torrent (after NFO strip) must use the release directory as src"
        )

    def test_lume_multi_file_torrent_src_uses_path_not_meta_path(self, tmp_path):
        """Regression: when meta['path'] is a file but path (normalised by caller)
        is the release directory, src must be the directory, not the file."""
        from src.torrent_clients.qbittorrent import QbittorrentClientMixin as QbittorrentClient

        release_dir = tmp_path / "Double.Indemnity.1944.MULTi.1080p.BluRay.x264-FiDELiO"
        release_dir.mkdir()
        mkv = release_dir / "movie.mkv"
        mkv.write_bytes(b"FAKE")
        meta = {
            "path": str(mkv),          # file path — as seen in some caller contexts
            "filelist": [str(mkv)],
            "keep_nfo": True,
            "keep_folder": False,
        }
        torrent = self._make_torrent_obj(multi_file=True)
        path = str(release_dir)  # normalised to release dir by qbittorrent() caller

        src, save_path = QbittorrentClient._resolve_src_and_save_path(path, torrent, meta, "LUME")

        assert src == str(release_dir), (
            "src must be the release directory (path), not meta['path'] which is a file"
        )
        assert save_path == str(tmp_path), (
            "save_path must be the parent directory"
        )

    def test_lume_save_path_adjusted_to_parent_when_multi_file(self, tmp_path):
        """save_path (path) must be the *parent* of the release dir for multi-file
        so qBittorrent resolves save_path/ReleaseName/movie.mkv correctly."""
        from src.torrent_clients.qbittorrent import QbittorrentClientMixin as QbittorrentClient

        meta = self._make_meta(tmp_path, keep_nfo=True)
        torrent = self._make_torrent_obj(multi_file=True)
        path = meta["path"]  # release dir

        _, save_path = QbittorrentClient._resolve_src_and_save_path(path, torrent, meta, "LUME")

        assert save_path == str(tmp_path), (
            "save_path must be the parent directory so qBit appends ReleaseName itself"
        )

    def test_c411_single_file_multi_file_torrent_uses_dir_src(self, tmp_path):
        """auto_nfo tracker (C411, keep_nfo=True): src must also be the directory."""
        from src.torrent_clients.qbittorrent import QbittorrentClientMixin as QbittorrentClient

        meta = self._make_meta(tmp_path, keep_nfo=True)
        torrent = self._make_torrent_obj(multi_file=True)
        path = meta["path"]

        src, _ = QbittorrentClient._resolve_src_and_save_path(path, torrent, meta, "C411")

        assert src == path, "auto_nfo tracker with keep_nfo must use directory as src"

    def test_keep_folder_always_uses_dir_src(self, tmp_path):
        """keep_folder=True: must always use directory src regardless of torrent type."""
        from src.torrent_clients.qbittorrent import QbittorrentClientMixin as QbittorrentClient

        meta = self._make_meta(tmp_path, keep_folder=True)
        torrent = self._make_torrent_obj(multi_file=False)
        path = meta["path"]

        src, _ = QbittorrentClient._resolve_src_and_save_path(path, torrent, meta, "LUME")

        assert src == path, "keep_folder must force directory src"

    def test_season_pack_c411_src_is_release_dir_not_parent(self, tmp_path):
        """Regression: season pack (multi-file) with auto_nfo tracker (C411).

        qbittorrent() pre-adjusts path to os.path.dirname(release_dir) because
        len(filelist) != 1.  _resolve_src_and_save_path must still return src =
        release_dir (meta['path']), NOT the pre-adjusted parent.

        If src were the parent directory, os.path.basename(src) would be e.g.
        'tv-completed' and async_link_directory would create
        tracker_dir/tv-completed/Avatar.../ instead of tracker_dir/Avatar.../.
        """
        from src.torrent_clients.qbittorrent import QbittorrentClientMixin as QbittorrentClient

        # Season pack: multiple episode files
        category_dir = tmp_path / "tv-completed"
        category_dir.mkdir()
        release_dir = category_dir / "Avatar.The.Last.Airbender.S03.MULTI.1080p.BluRay.x264-FTMVHD"
        release_dir.mkdir()
        ep1 = release_dir / "ep01.mkv"
        ep2 = release_dir / "ep02.mkv"
        ep1.write_bytes(b"EP1")
        ep2.write_bytes(b"EP2")

        meta = {
            "path": str(release_dir),
            "filelist": [str(ep1), str(ep2)],  # multiple files → single_file=False
            "keep_nfo": True,
            "keep_folder": False,
        }
        torrent = self._make_torrent_obj(multi_file=True)

        # Simulate what qbittorrent() does: len(filelist) != 1 → path = parent dir
        path_after_normalization = str(category_dir)

        src, _ = QbittorrentClient._resolve_src_and_save_path(
            path_after_normalization, torrent, meta, "C411"
        )

        assert src == str(release_dir), (
            "Season pack src must be the release directory, not the pre-adjusted parent. "
            f"Got {src!r}, expected {str(release_dir)!r}. "
            "If src were the parent, os.path.basename(src) would be 'tv-completed' and "
            "the hardlink would create tracker_dir/tv-completed/ instead of tracker_dir/Avatar.../"
        )

    def test_nfo_tracker_single_file_torrent_uses_file_src(self, tmp_path):
        """Regression: G3MINI-style tracker (tracker_wants_nfo=True) that ends up
        with a single-file torrent (e.g. when meta['skip_nfo'] is True globally
        because another tracker in the same batch is skip_nfo).

        Before fix: not tracker_wants_nfo was False → elif branch → src=folder →
        whole folder hardlinked → save_path/FolderName/movie.mkv BUT torrent
        expects save_path/movie.mkv → missing file.

        After fix: torrent_is_multi_file is the ground truth → first condition
        fires → src = meta['filelist'][0] → file hardlinked correctly.
        """
        from src.torrent_clients.qbittorrent import QbittorrentClientMixin as QbittorrentClient

        meta = self._make_meta(tmp_path, keep_nfo=True, keep_folder=False)
        # The torrent is single-file even though tracker_wants_nfo=True
        torrent = self._make_torrent_obj(multi_file=False)
        path = meta["path"]  # release dir

        src, _ = QbittorrentClient._resolve_src_and_save_path(path, torrent, meta, "G3MINI")

        assert src == meta["filelist"][0], (
            "Single-file torrent must use the mkv as src regardless of tracker_wants_nfo. "
            "Linking the folder when the torrent expects a bare file causes missing-file errors."
        )
