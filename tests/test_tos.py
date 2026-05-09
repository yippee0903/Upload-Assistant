import asyncio
import os
import tempfile
from typing import Any
from unittest.mock import AsyncMock, patch

from src.trackers.TOS import TOS


def _config() -> dict[str, Any]:
    return {
        "TRACKERS": {
            "TOS": {
                "api_key": "test-api-key",
                "announce_url": "https://theoldschool.cc/announce/FAKE",
            }
        },
        "DEFAULT": {"tmdb_api": "fake-key"},
    }


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _meta(category: str = "MOVIE", tv_pack: bool = False) -> dict[str, Any]:
    return {
        "category": category,
        "tv_pack": tv_pack,
    }


class TestTosCategoryIdAudioPrefix:
    def test_movie_ad_vostfr_maps_to_vostfr_category(self):
        t = TOS(_config())
        t._build_audio_string = AsyncMock(return_value="AD.VOSTFR")

        result = _run(t.get_category_id(_meta("MOVIE")))

        assert result == {"category_id": "6"}

    def test_tv_ad_vostfr_maps_to_vostfr_category(self):
        t = TOS(_config())
        t._build_audio_string = AsyncMock(return_value="AD.VOSTFR")

        result = _run(t.get_category_id(_meta("TV")))

        assert result == {"category_id": "7"}

    def test_tv_pack_ad_prefixed_vostfr_maps_to_vostfr_pack_category(self):
        t = TOS(_config())
        t._build_audio_string = AsyncMock(return_value="AD.AD.VOSTFR")

        result = _run(t.get_category_id(_meta("TV", tv_pack=True)))

        assert result == {"category_id": "9"}


# ---------------------------------------------------------------------------
# Tests – special-character filename rejection
# ---------------------------------------------------------------------------


def _additional_checks_meta(path: str, filelist: list[str] | None = None) -> dict[str, Any]:
    return {
        "path": path,
        "filelist": filelist or [],
        "category": "MOVIE",
        "scene": False,
        "nfo": False,
        "auto_nfo": False,
        "is_disc": False,
        "type": "WEBDL",
        "resolution": "1080p",
        "video_codec": "",
        "mediainfo": {"media": {"track": []}},
        "debug": False,
        "unattended": False,
        "anime": False,
    }


class TestTosSpecialCharRejection:
    """get_additional_checks must reject filenames containing special characters."""

    def _patch_lang_ok(self, t: TOS) -> None:
        """Stub language and bitrate checks so only filename check is exercised."""
        t.common.check_language_requirements = AsyncMock(return_value=True)  # type: ignore[assignment]

    def test_clean_path_passes(self):
        t = TOS(_config())
        self._patch_lang_ok(t)
        meta = _additional_checks_meta("/tmp/My.Movie.2025.1080p.WEB-DL-GRP")
        result = _run(t.get_additional_checks(meta))
        assert result is True

    def test_path_with_parentheses_is_rejected(self):
        t = TOS(_config())
        self._patch_lang_ok(t)
        meta = _additional_checks_meta("/tmp/My.Movie.(2025).1080p.WEB-DL-GRP")
        result = _run(t.get_additional_checks(meta))
        assert result is False

    def test_filelist_entry_with_parentheses_is_rejected(self):
        t = TOS(_config())
        self._patch_lang_ok(t)
        with tempfile.TemporaryDirectory() as tmp:
            bad_file = os.path.join(tmp, "Episode (1).mkv")
            open(bad_file, "w").close()
            meta = _additional_checks_meta(tmp, filelist=[bad_file])
        result = _run(t.get_additional_checks(meta))
        assert result is False

    def test_ampersand_in_path_is_rejected(self):
        t = TOS(_config())
        self._patch_lang_ok(t)
        meta = _additional_checks_meta("/tmp/Tom & Jerry.2025.1080p-GRP")
        result = _run(t.get_additional_checks(meta))
        assert result is False

    def test_brackets_in_path_are_allowed(self):
        """Square brackets are acceptable (e.g. [BluRay])."""
        t = TOS(_config())
        self._patch_lang_ok(t)
        meta = _additional_checks_meta("/tmp/My.Movie.2025.[BluRay].1080p-GRP")
        result = _run(t.get_additional_checks(meta))
        assert result is True


# ---------------------------------------------------------------------------
# Tests – _check_tos_specific_dupes
# ---------------------------------------------------------------------------


def _dupe(name: str) -> dict[str, Any]:
    return {"name": name, "size": 0}


def _season_meta() -> dict[str, Any]:
    return {"category": "TV", "tv_pack": True}


def _movie_meta() -> dict[str, Any]:
    return {"category": "MOVIE", "tv_pack": False}


class TestTosSpecificDupes:
    """_check_tos_specific_dupes must keep internal-team and integrale dupes."""

    def _t(self) -> TOS:
        return TOS(_config())

    def test_internal_group_dupe_is_kept_even_if_filtered(self):
        t = self._t()
        d = _dupe("Serie.S01.2025.MULTI.VFF.1080p.WEB-BraD")
        # Simulate that French-lang filter has dropped it
        result = t._check_tos_specific_dupes([d], [], _season_meta())
        assert d in result

    def test_internal_group_dupe_gets_flag(self):
        t = self._t()
        d = _dupe("Serie.S01.2025.MULTI.VFF.1080p.WEB-SUPPLY")
        t._check_tos_specific_dupes([d], [], _season_meta())
        assert "tos_internal" in d.get("flags", [])

    def test_non_internal_group_not_re_injected(self):
        t = self._t()
        d = _dupe("Serie.S01.2025.MULTI.VFF.1080p.WEB-RANDOMGRP")
        result = t._check_tos_specific_dupes([d], [], _season_meta())
        assert d not in result

    def test_integrale_dupe_blocks_season_pack(self):
        t = self._t()
        d = _dupe("Serie.iNTEGRALE.2025.MULTI.VFF.1080p.WEB-GRP")
        result = t._check_tos_specific_dupes([d], [], _season_meta())
        assert d in result
        assert "integrale_supersede" in d.get("flags", [])

    def test_integrale_case_insensitive(self):
        t = self._t()
        d = _dupe("Serie.Integrale.2025.MULTI.VFF.1080p.WEB-GRP")
        result = t._check_tos_specific_dupes([d], [], _season_meta())
        assert d in result

    def test_integrale_does_not_block_movie(self):
        """An integrale dupe should not block a movie upload."""
        t = self._t()
        d = _dupe("Movie.iNTEGRALE.2025.MULTI.VFF.1080p.WEB-GRP")
        result = t._check_tos_specific_dupes([d], [], _movie_meta())
        # Not a season pack → should NOT be re-injected
        assert d not in result

    def test_already_present_dupe_not_duplicated(self):
        """If a dupe is already in filtered, it must not appear twice."""
        t = self._t()
        d = _dupe("Serie.S01.2025.MULTI.VFF.1080p.WEB-BraD")
        result = t._check_tos_specific_dupes([d], [d], _season_meta())
        assert result.count(d) == 1

    def test_internal_groups_all_present_in_class_attribute(self):
        t = self._t()
        expected = ["zYz", "ZKB", "UwU", "Tsundere-Raws", "THESYNDiCATE", "SUPPLY",
                    "SowHD", "SHADOW", "RiFiFi", "REBiRTH", "pERsO", "Oldschool",
                    "NoNE", "NLX5", "NEO", "HeavyWeight", "DELiRiUS", "COLL3CTiF",
                    "CHiLL", "BTT", "BraD", "A3L"]
        for grp in expected:
            assert grp in t._TOS_INTERNAL_GROUPS, f"{grp} missing from _TOS_INTERNAL_GROUPS"
            # Internal groups must NOT be in banned_groups (which blocks uploading *from* those
            # groups). They only block dupes via _check_tos_specific_dupes.
            assert grp not in t.banned_groups, f"{grp} should not be in banned_groups"
