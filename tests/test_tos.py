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

    def test_trailing_slash_path_is_still_checked(self):
        """A path ending with '/' must not bypass the basename check."""
        t = TOS(_config())
        self._patch_lang_ok(t)
        meta = _additional_checks_meta("/tmp/My.Movie.(2025).1080p.WEB-DL-GRP/")
        result = _run(t.get_additional_checks(meta))
        assert result is False

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


class TestTosLightReencodeRejection:
    """get_additional_checks must reject 4KLight / HDLight re-encodes (forbidden on TOS)."""

    def _patch_lang_ok(self, t: TOS) -> None:
        t.common.check_language_requirements = AsyncMock(return_value=True)  # type: ignore[assignment]

    def test_4klight_rejected(self):
        t = TOS(_config())
        self._patch_lang_ok(t)
        meta = _additional_checks_meta("/tmp/Solo.2018.2160p.4KLight.BluRay.x265-GRP")
        meta["uuid"] = "Solo.2018.2160p.4KLight.BluRay.x265-GRP.mkv"
        assert _run(t.get_additional_checks(meta)) is False

    def test_hdlight_rejected(self):
        t = TOS(_config())
        self._patch_lang_ok(t)
        meta = _additional_checks_meta("/tmp/Film.2020.1080p.HDLight.BluRay.x265-GRP")
        meta["uuid"] = "Film.2020.1080p.HDLight.BluRay.x265-GRP.mkv"
        assert _run(t.get_additional_checks(meta)) is False

    def test_normal_encode_not_rejected_by_light_gate(self):
        t = TOS(_config())
        self._patch_lang_ok(t)
        meta = _additional_checks_meta("/tmp/Film.2020.1080p.BluRay.x265-GRP")
        meta["uuid"] = "Film.2020.1080p.BluRay.x265-GRP.mkv"
        # No light tag → gate passes; clean filename + stubbed language → True
        assert _run(t.get_additional_checks(meta)) is True


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

    def test_internal_group_with_hyphen_in_tag_is_detected(self):
        """Group tags containing hyphens (e.g. Tsundere-Raws) must be detected."""
        t = self._t()
        d = _dupe("Serie.S01.2025.MULTI.VFF.1080p.WEB-Tsundere-Raws")
        result = t._check_tos_specific_dupes([d], [], _season_meta())
        assert d in result
        assert "tos_internal" in d.get("flags", [])

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


# ═══════════════════════════════════════════════════════════════
#  Nogroup WEB-DL naming — regression for Cyclo-style filenames
# ═══════════════════════════════════════════════════════════════


def _meta_nogroup(**overrides: Any) -> dict[str, Any]:
    """Full meta for TOS get_name tests."""
    m: dict[str, Any] = {
        'category': 'MOVIE',
        'type': 'WEBDL',
        'title': 'Cyclo',
        'year': '1995',
        'resolution': '1080p',
        'source': 'WEB',
        'audio': 'AAC 2.0',
        'video_encode': 'H.264',
        'video_codec': 'H.264',
        'service': '',
        'tag': '',
        'edition': '',
        'repack': '',
        '3D': '',
        'uhd': '',
        'hdr': '',
        'webdv': '',
        'part': '',
        'season': '',
        'episode': '',
        'is_disc': None,
        'search_year': '',
        'manual_year': None,
        'manual_date': None,
        'no_season': False,
        'no_year': False,
        'no_aka': False,
        'debug': False,
        'tv_pack': False,
        'scene': False,
        'scene_name': '',
        'path': '',
        'original_language': 'vi',
        'audio_languages': [],
        'subtitle_languages': [],
        'mediainfo': {'media': {'track': []}},
    }
    m.update(overrides)
    return m


class TestNogroupWebDL:
    """WEB-DL releases without a group tag must use TOS's notag_label.

    TOS uses notag_label='NOTAG'.
    Regression: Cyclo.1995.1080p.WEB-DL.AAC.2.0.H.264.mkv had a false
    group '-DL.AAC.2.0.H.264' extracted, producing duplicated tokens.
    """

    def _get_name(self, meta: dict) -> str:
        return _run(TOS(_config()).get_name(meta))['name']

    def test_empty_tag_uses_notag_label(self):
        """tag='' (nogroup) must produce a name ending with '-NOTAG'."""
        name = self._get_name(_meta_nogroup())
        assert name.endswith('-NOTAG'), f"Expected -NOTAG suffix, got: {name!r}"

    def test_no_audio_duplication(self):
        """Audio token must appear exactly once — no duplication from a false tag."""
        name = self._get_name(_meta_nogroup())
        assert name.count('AAC') == 1, (
            f"Audio token 'AAC' duplicated in name: {name!r}."
        )

    def test_real_group_preserved(self):
        """A real group tag must not be replaced by the notag label."""
        name = self._get_name(_meta_nogroup(tag='-FRiENDS'))
        assert name.endswith('-FRiENDS'), f"Expected -FRiENDS suffix, got: {name!r}"


# ---------------------------------------------------------------------------
# Tests – Scene release NFO requirement
# ---------------------------------------------------------------------------


class TestTosSceneNfoRequirement:
    """TOS requires a NFO file for Scene releases.

    get_additional_checks must return False when meta['scene'] is True and
    neither meta['nfo'] nor meta['auto_nfo'] is set.
    """

    def _patch_lang_ok(self, t: TOS) -> None:
        t.common.check_language_requirements = AsyncMock(return_value=True)  # type: ignore[assignment]

    def test_scene_without_nfo_rejected(self):
        """Scene release with no NFO must be rejected."""
        t = TOS(_config())
        self._patch_lang_ok(t)
        meta = _additional_checks_meta("/tmp/Some.Movie.2025.1080p.BluRay.x264-GRP")
        meta["scene"] = True
        meta["nfo"] = False
        meta["auto_nfo"] = False
        result = _run(t.get_additional_checks(meta))
        assert result is False

    def test_scene_with_nfo_accepted(self):
        """Scene release with a NFO file must pass the NFO check."""
        t = TOS(_config())
        self._patch_lang_ok(t)
        meta = _additional_checks_meta("/tmp/Some.Movie.2025.1080p.BluRay.x264-GRP")
        meta["scene"] = True
        meta["nfo"] = True
        meta["auto_nfo"] = False
        result = _run(t.get_additional_checks(meta))
        assert result is True

    def test_scene_with_auto_nfo_accepted(self):
        """Scene release with auto-generated NFO must also pass."""
        t = TOS(_config())
        self._patch_lang_ok(t)
        meta = _additional_checks_meta("/tmp/Some.Movie.2025.1080p.BluRay.x264-GRP")
        meta["scene"] = True
        meta["nfo"] = False
        meta["auto_nfo"] = True
        result = _run(t.get_additional_checks(meta))
        assert result is True

    def test_non_scene_without_nfo_accepted(self):
        """Non-scene release without NFO must not be rejected by the NFO check."""
        t = TOS(_config())
        self._patch_lang_ok(t)
        meta = _additional_checks_meta("/tmp/Some.Movie.2025.1080p.BluRay.x264-GRP")
        meta["scene"] = False
        meta["nfo"] = False
        meta["auto_nfo"] = False
        result = _run(t.get_additional_checks(meta))
        assert result is True
