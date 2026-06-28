# Tests for DupeChecker.filter_dupes — filename match logic
"""
Regression tests for the dupe-detection behaviour in DupeChecker.filter_dupes:

  • A filename match alone (without a matching file count) must be enough to:
      1. Keep the entry as a dupe (process_exclusion returns False).
      2. Set meta["filename_match"].
  • When both filename AND count match, meta["file_count_match"] must also be set.
  • Cross-seed detection (line 248 in uphelper.py) intentionally still requires
    file_count_match, so we verify that flag is only present when counts agree.
"""
import asyncio
from typing import Any

import pytest

from src.dupe_checking import DupeChecker


def _run(coro):
    return asyncio.run(coro)


def _checker() -> DupeChecker:
    return DupeChecker(config={})


def _base_meta(**overrides) -> dict[str, Any]:
    """Minimal meta dict for a 1080p BluRay encode (movie)."""
    meta: dict[str, Any] = {
        "name": "Interstellar 2014 IMAX 1080p BluRay DTS-HD MA 5.1 x264-LEGi0N",
        "uuid": "Interstellar 2014 IMAX 1080p BluRay DTS-HD MA 5.1 x264-LEGi0N",
        "tmdb": "157336",
        "resolution": "1080p",
        "category": "MOVIE",
        "type": "ENCODE",
        "source": "Blu-ray",
        "is_disc": None,
        "sd": 0,
        "hdr": None,
        "season": None,
        "episode": None,
        "tag": "-LEGi0N",
        "video_encode": "x264",
        "unattended": True,
        "debug": False,
        "filelist": ["/path/to/Interstellar.2014.IMAX.1080p.BluRay.DTS-HD.MA.5.1.x264-LEGi0N.mkv"],
    }
    meta.update(overrides)
    return meta


def _rf_entry(files: list[str], file_count: int | None = None) -> dict[str, Any]:
    """Build a RF-style dupe entry with the given file list."""
    if file_count is None:
        file_count = len(files)
    return {
        "name": "Interstellar 2014 IMAX 1080p BluRay DTS-HD MA 5.1 x264-LEGi0N",
        "size": 17_996_567_700,
        "files": files,
        "file_count": file_count,
        "trumpable": False,
        "link": "https://reelflix.cc/torrents/12725",
        "download": "https://reelflix.cc/torrents/12725/download",
        "id": 12725,
        "type": "Encode",
        "res": "1080p",
        "internal": False,
    }


# ═══════════════════════════════════════════════════════════════
#  Filename match — with and without extra tracker files
# ═══════════════════════════════════════════════════════════════


class TestFilenameMatchLogic:
    """filter_dupes behaviour around filename/file-count matching."""

    def test_exact_filename_and_count_match_sets_both_flags(self):
        """
        When the tracker has exactly the same file list as the local copy,
        both filename_match and file_count_match must be set.
        """
        local_file = "Interstellar.2014.IMAX.1080p.BluRay.DTS-HD.MA.5.1.x264-LEGi0N.mkv"
        meta = _base_meta()
        entry = _rf_entry([local_file])  # 1 file — same as local

        dupes = _run(_checker().filter_dupes([entry], meta, "RF"))

        assert dupes, "entry must remain in the dupe list"
        assert meta.get("filename_match"), "filename_match must be set"
        assert meta.get("file_count_match"), "file_count_match must be set when counts agree"

    def test_filename_match_with_extra_tracker_files_sets_filename_match(self):
        """
        Regression: when the tracker torrent has extra files (NFO, sample) that
        the local copy doesn't have, filename_match must still be set and the
        entry must remain in the dupe list — even though file counts differ.
        """
        local_file = "Interstellar.2014.IMAX.1080p.BluRay.DTS-HD.MA.5.1.x264-LEGi0N.mkv"
        tracker_files = [
            local_file,
            "Interstellar.2014.IMAX.1080p.BluRay.DTS-HD.MA.5.1.x264-LEGi0N.nfo",
            "Interstellar.2014.IMAX.1080p.BluRay.DTS-HD.MA.5.1.x264-LEGi0N.sample.mkv",
        ]
        meta = _base_meta()
        entry = _rf_entry(tracker_files)  # 3 files on tracker, 1 locally

        dupes = _run(_checker().filter_dupes([entry], meta, "RF"))

        assert dupes, "entry must remain in the dupe list"
        assert meta.get("filename_match"), "filename_match must be set despite count mismatch"

    def test_filename_match_with_extra_tracker_files_does_not_set_count_match(self):
        """
        file_count_match must NOT be set when the file counts differ — this
        flag gates cross-seed eligibility, which requires an identical file set.
        """
        local_file = "Interstellar.2014.IMAX.1080p.BluRay.DTS-HD.MA.5.1.x264-LEGi0N.mkv"
        tracker_files = [
            local_file,
            "Interstellar.2014.IMAX.1080p.BluRay.DTS-HD.MA.5.1.x264-LEGi0N.nfo",
            "Interstellar.2014.IMAX.1080p.BluRay.DTS-HD.MA.5.1.x264-LEGi0N.sample.mkv",
        ]
        meta = _base_meta()
        entry = _rf_entry(tracker_files)

        _run(_checker().filter_dupes([entry], meta, "RF"))

        assert not meta.get("file_count_match"), (
            "file_count_match must NOT be set when local file count differs "
            "from tracker file count (cross-seed would fail)"
        )

    def test_tracker_files_with_folder_prefix_match_local_basename(self):
        """
        Regression: G3MINI stores files as "Folder/File.mkv".  The comparison
        against local basenames must strip the directory component first.
        """
        local_file = "Atlanta.S04E01.MULTi.1080p.AMZN.WEB-DL.DDP5.1.H264-FRATERNiTY.mkv"
        tracker_files = [
            "Atlanta.S04E01.MULTi.1080p.AMZN.WEB-DL.DDP5.1.H264-FRATERNiTY/Atlanta.S04E01.MULTi.1080p.AMZN.WEB-DL.DDP5.1.H264-FRATERNiTY.mkv",
            "Atlanta.S04E01.MULTi.1080p.AMZN.WEB-DL.DDP5.1.H264-FRATERNiTY/Atlanta.S04E01.MULTi.1080p.AMZN.WEB-DL.DDP5.1.H264-FRATERNiTY.nfo",
        ]
        meta = _base_meta(
            filelist=[f"/downloads/Atlanta.S04E01.MULTi.1080p.AMZN.WEB-DL.DDP5.1.H264-FRATERNiTY/{local_file}"],
        )
        entry = _rf_entry(tracker_files)
        entry["name"] = "Atlanta.S04.MULTi.VFF.1080p.WEB.DDP5.1.H.264-FRATERNiTY"

        dupes = _run(_checker().filter_dupes([entry], meta, "G3MINI"))

        assert dupes, "entry must remain in the dupe list"
        assert meta.get("filename_match"), (
            "filename_match must be set even when tracker stores 'Folder/File.mkv' paths"
        )

    def test_no_filename_overlap_does_not_set_filename_match(self):
        """When no local filename appears in the tracker file list, no match flags are set."""
        tracker_files = [
            "Interstellar.2014.1080p.BluRay.DD.5.1.x264-BHDStudio.mkv",
        ]
        meta = _base_meta()
        entry = _rf_entry(tracker_files)
        entry["name"] = "Interstellar 2014 1080p BluRay DD 5.1 x264-BHDStudio"

        _run(_checker().filter_dupes([entry], meta, "RF"))

        assert not meta.get("filename_match"), "filename_match must not be set for a different release"


# ═══════════════════════════════════════════════════════════════
#  Name-similarity fallback  (TORR9-style trackers with no files)
# ═══════════════════════════════════════════════════════════════


def _torr9_entry_no_files(**overrides) -> dict[str, Any]:
    """Build a TORR9-style dupe entry with *no* file list."""
    entry: dict[str, Any] = {
        "name": "Atlanta.S04.MULTI.1080p.AMZN.H264.DDP5.1-FRATERNiTY",
        "size": 20_000_000_000,
        "link": "https://torr9.net/torrents/50343",
        "id": 50343,
        # No "files" key at all — TORR9 custom API never returns it
    }
    entry.update(overrides)
    return entry


def _atlanta_s04_meta(**overrides) -> dict[str, Any]:
    """Meta for Atlanta S04 WEB season pack — FRATERNiTY group."""
    meta: dict[str, Any] = {
        "name": "Atlanta.S04.MULTI.VFF.1080p.AMZN.WEB.DDP.5.1.H264-FRATERNiTY",
        "uuid": "Atlanta.S04.MULTI.VFF.1080p.AMZN.WEB.DDP.5.1.H264-FRATERNiTY",
        "tmdb": "61818",
        "resolution": "1080p",
        "category": "TV",
        "type": "WEBDL",
        "source": "Amazon Prime",
        "is_disc": None,
        "sd": 0,
        "hdr": None,
        "season": "S04",
        "episode": None,
        "tag": "-FRATERNiTY",
        "video_encode": "H.264",
        "unattended": True,
        "debug": False,
        "filelist": ["/downloads/Atlanta.S04.MULTI.VFF.1080p.AMZN.WEB.DDP.5.1.H264-FRATERNiTY/Atlanta.S04E01.MULTi.VFF.mkv"],
    }
    meta.update(overrides)
    return meta


class TestNameSimilarityFallback:
    """Name-similarity fallback for trackers that return no file lists (e.g. TORR9)."""

    def test_same_group_high_similarity_sets_filename_match(self):
        """
        Regression — TORR9 Atlanta S04 FRATERNiTY:
        Old naming omits VFF/WEB tokens. No file list is returned by the API.
        The name-similarity fallback must detect this as the same release and
        set filename_match (→ "Exact match found!" in the UI).
        """
        meta = _atlanta_s04_meta()
        entry = _torr9_entry_no_files()

        dupes = _run(_checker().filter_dupes([entry], meta, "TORR9"))

        assert dupes, "entry must remain in the dupe list"
        assert meta.get("filename_match"), (
            "filename_match must be set via name-similarity fallback "
            "when tracker returns no file list but names/tags are similar"
        )

    def test_same_group_low_similarity_does_not_set_filename_match(self):
        """
        Two releases by the same group but clearly different content (different show)
        must NOT trigger filename_match even if the tag matches.
        """
        meta = _atlanta_s04_meta()
        # Entry from a completely different show by the same group
        entry = _torr9_entry_no_files(
            name="Succession.S04.MULTI.1080p.AMZN.H264.DDP5.1-FRATERNiTY",
        )

        _run(_checker().filter_dupes([entry], meta, "TORR9"))

        assert not meta.get("filename_match"), (
            "filename_match must NOT be set when the names differ substantially "
            "despite sharing the same release group"
        )


# ═══════════════════════════════════════════════════════════════
#  french_lang_supersede + filename_match  (C411 Mandalorian regression)
# ═══════════════════════════════════════════════════════════════


class TestFrenchSupersedePlusFilenameMatch:
    """Regression — C411 Mandalorian S03:
    _check_french_lang_dupes adds french_lang_supersede when the upload's French
    audio cannot be detected via _build_audio_string (e.g. mediainfo absent).
    process_exclusion must still set filename_match via name-similarity when the
    dupe is clearly the same release (same group, high name similarity).
    """

    def _mandalorian_meta(self, **overrides) -> dict[str, Any]:
        meta: dict[str, Any] = {
            "name": "The Mandalorian S03 MULTI VFF 1080p WEB DDP 5.1 H264-FTMVHD",
            "uuid": "The.Mandalorian.S03.MULTI.VFF.1080p.WEB.DDP.5.1.H264-FTMVHD",
            "tmdb": "82856",
            "resolution": "1080p",
            "category": "TV",
            "type": "WEBDL",
            "source": "WEB-DL",
            "is_disc": None,
            "sd": 0,
            "hdr": None,
            "season": "S03",
            "episode": None,
            "tag": "-FTMVHD",
            "video_encode": "H.264",
            "unattended": True,
            "debug": False,
            "filelist": [],
        }
        meta.update(overrides)
        return meta

    def _c411_supersede_entry(self, **overrides) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "name": "[COMPAT-01] The.Mandalorian.S03.MULTI.VFF.1080p.WEB.EAC3.5.1.H264-FTMVHD",
            "size": 12_000_000_000,
            "link": "https://c411.org/torrents/ef79ff1455f54f94b93b1792e7c1af2ec8971671",
            "id": "ef79ff1455f54f94b93b1792e7c1af2ec8971671",
            "files": [],
            "file_count": 0,
            "flags": ["french_lang_supersede"],  # as added by _check_french_lang_dupes Case 2
        }
        entry.update(overrides)
        return entry

    def test_supersede_same_group_sets_filename_match(self):
        """
        When a dupe has french_lang_supersede AND is from the same group
        (high name similarity), filename_match must still be set so the UI
        shows "Exact match found!" instead of the generic dupe prompt.
        """
        meta = self._mandalorian_meta()
        entry = self._c411_supersede_entry()

        dupes = _run(_checker().filter_dupes([entry], meta, "C411"))

        assert dupes, "supersede dupe must remain in the dupe list"
        assert meta.get("filename_match"), (
            "filename_match must be set even when french_lang_supersede is present "
            "if the dupe is the same release (same group, high name similarity)"
        )

    def test_supersede_different_group_does_not_set_filename_match(self):
        """
        A dupe with french_lang_supersede from a DIFFERENT group must NOT
        trigger filename_match — it is a genuinely superior competing release.
        """
        meta = self._mandalorian_meta()
        entry = self._c411_supersede_entry(
            name="[COMPAT-01] The.Mandalorian.S03.MULTI.VFF.1080p.WEB.EAC3.5.1.H264-BATEAU",
            id="aabbccdd" * 5,
            flags=["french_lang_supersede"],
        )

        _run(_checker().filter_dupes([entry], meta, "C411"))

        assert not meta.get("filename_match"), (
            "filename_match must NOT be set when the competing release has a "
            "different group tag"
        )


# ═══════════════════════════════════════════════════════════════
#  Season-pack upload vs individual-episode dupe guard
# ═══════════════════════════════════════════════════════════════


def _family_guy_s24_pack_meta(**overrides) -> dict[str, Any]:
    """Minimal meta for a Family Guy S24 season-pack upload."""
    meta: dict[str, Any] = {
        "name": "Family Guy S24 1080p DSNP WEB-DL DD+ 5.1 H.264-FLUX",
        "uuid": "Family.Guy.S24.1080p.DSNP.WEB-DL.DD+.5.1.H.264-FLUX",
        "tmdb": "4057",
        "resolution": "1080p",
        "category": "TV",
        "type": "WEBDL",
        "source": "Disney+",
        "is_disc": None,
        "sd": 0,
        "hdr": None,
        "season": "S24",
        "episode": None,
        "tv_pack": 1,
        "tag": "-FLUX",
        "video_encode": "H.264",
        "unattended": True,
        "debug": False,
        "filelist": [
            "/dl/Family.Guy.S24E01.1080p.DSNP.WEB-DL.DD+.5.1.H.264-FLUX.mkv",
            "/dl/Family.Guy.S24E02.1080p.DSNP.WEB-DL.DD+.5.1.H.264-FLUX.mkv",
            "/dl/Family.Guy.S24E13.1080p.DSNP.WEB-DL.DD+.5.1.H.264-FLUX.mkv",
        ],
    }
    meta.update(overrides)
    return meta


def _episode_entry(ep: str, with_files: bool = True) -> dict[str, Any]:
    """Build a dupe entry for a single Family Guy episode."""
    name = f"Family Guy S24{ep} 1080p DSNP WEB-DL DD+ 5.1 H.264-FLUX"
    files = (
        [f"Family.Guy.S24{ep}.1080p.DSNP.WEB-DL.DD+.5.1.H.264-FLUX.mkv"]
        if with_files
        else []
    )
    return {
        "name": name,
        "size": 1_500_000_000,
        "files": files,
        "file_count": len(files),
        "trumpable": False,
        "link": f"https://tracker.example/torrents/100",
        "id": 100,
        "type": "WEB-DL",
        "res": "1080p",
        "internal": False,
    }


class TestSeasonPackVsEpisodeGuard:
    """
    A TV season-pack upload must NEVER be flagged as an exact match of an
    individual-episode entry on the tracker, regardless of whether the dupe
    comparison fires via file list or name-similarity fallback.
    """

    def test_file_match_does_not_flag_pack_as_episode_dupe(self):
        """
        The season pack contains S24E13.mkv.  The tracker has an S24E13
        episode entry whose file list includes that exact filename.
        The file-comparison guard must prevent filename_match from being set.
        """
        meta = _family_guy_s24_pack_meta()
        entry = _episode_entry("E13", with_files=True)

        dupes = _run(_checker().filter_dupes([entry], meta, "DP"))

        assert not dupes, "the episode entry must be filtered out — it is not a dupe of the season pack"
        assert not meta.get("filename_match"), (
            "filename_match must NOT be set when a season-pack upload matches "
            "an individual-episode file — they are not the same release"
        )
        assert not meta.get("exact_filename_match"), (
            "exact_filename_match must also not be set for pack-vs-episode"
        )

    def test_similarity_fallback_does_not_flag_pack_as_episode_dupe(self):
        """
        When the tracker returns no file list (e.g. LST) and names are near-
        identical (Family Guy S24 vs Family Guy S24E13), the name-similarity
        fallback must be skipped for season-pack vs episode pairs.
        """
        meta = _family_guy_s24_pack_meta()
        entry = _episode_entry("E13", with_files=False)

        dupes = _run(_checker().filter_dupes([entry], meta, "LST"))

        assert not dupes, "the episode entry must be filtered out — it is not a dupe of the season pack"
        assert not meta.get("filename_match"), (
            "filename_match must NOT be set via name-similarity fallback when "
            "a season-pack upload is compared against a single-episode entry"
        )

    def test_episode_upload_vs_same_episode_still_detected(self):
        """
        When uploading a *single episode* (not a pack) and the tracker has that
        exact episode, the file-comparison must still detect it as a dupe.
        """
        meta = _family_guy_s24_pack_meta(
            name="Family Guy S24E13 1080p DSNP WEB-DL DD+ 5.1 H.264-FLUX",
            season="S24",
            episode="E13",
            tv_pack=0,
            filelist=["/dl/Family.Guy.S24E13.1080p.DSNP.WEB-DL.DD+.5.1.H.264-FLUX.mkv"],
        )
        entry = _episode_entry("E13", with_files=True)

        dupes = _run(_checker().filter_dupes([entry], meta, "DP"))

        assert dupes, "identical episode upload must be detected as dupe"
        assert meta.get("filename_match"), (
            "filename_match must be set when episode upload matches episode dupe"
        )

    def test_pack_upload_vs_same_pack_still_detected(self):
        """
        When the tracker already has the same season pack, it must still be
        detected as a dupe (no false exclusion from the new guard).
        """
        meta = _family_guy_s24_pack_meta()
        # Season-pack entry whose name has no episode pattern
        pack_entry: dict[str, Any] = {
            "name": "Family Guy S24 1080p DSNP WEB-DL DD+ 5.1 H.264-FLUX",
            "size": 20_000_000_000,
            "files": [
                "Family.Guy.S24E01.1080p.DSNP.WEB-DL.DD+.5.1.H.264-FLUX.mkv",
                "Family.Guy.S24E02.1080p.DSNP.WEB-DL.DD+.5.1.H.264-FLUX.mkv",
                "Family.Guy.S24E13.1080p.DSNP.WEB-DL.DD+.5.1.H.264-FLUX.mkv",
            ],
            "file_count": 3,
            "trumpable": False,
            "link": "https://tracker.example/torrents/200",
            "id": 200,
            "type": "WEB-DL",
            "res": "1080p",
            "internal": False,
        }

        dupes = _run(_checker().filter_dupes([pack_entry], meta, "DP"))

        assert dupes, "season-pack upload vs same season-pack on tracker must be detected as dupe"
        assert meta.get("filename_match"), (
            "filename_match must be set when season-pack upload matches an "
            "existing season-pack entry on the tracker"
        )


class TestRefineHdrTerms:
    """refine_hdr_terms must recognise 'Dolby Vision' spelled out, not just 'DV'."""

    def test_dolby_vision_spelled_out_is_dv(self):
        # A release name carrying "DOLBY.VISION" (normalised to "dolby vision")
        # must yield DV — the bare "DV" substring never appears in it.
        terms = _run(DupeChecker.refine_hdr_terms("solo 2018 2160p 4klight dolby vision ddp 7 1 x265-qtz"))
        assert terms == {"DV"}

    def test_dv_token_still_works(self):
        assert _run(DupeChecker.refine_hdr_terms("movie 2160p dv hdr10 x265")) == {"DV", "HDR"}

    def test_plain_hdr(self):
        assert _run(DupeChecker.refine_hdr_terms("movie 2160p hdr10 x265")) == {"HDR"}

    def test_no_hdr(self):
        assert _run(DupeChecker.refine_hdr_terms("movie 1080p bluray x264")) == set()

    def test_dolby_vision_matches_dv_hdr_target(self):
        # The reported bug: a DV upload (hdr="DV HDR") vs a "Dolby Vision" dupe
        # must be considered the same HDR flavour, not excluded.
        file_hdr = _run(DupeChecker.refine_hdr_terms("solo 2018 2160p 4klight dolby vision ddp 7 1 x265-qtz"))
        target_hdr = _run(DupeChecker.refine_hdr_terms("DV HDR"))
        assert _run(DupeChecker.has_matching_hdr(file_hdr, target_hdr, {"type": "ENCODE"}, tracker="C411"))
