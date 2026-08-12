# Tests for G3MINI tracker — gemini-tracker.org
"""
Test suite for G3MINI release naming.
Covers: Hybrid + video codec positioning in release names.
"""

import asyncio
from typing import Any

import pytest

from src.trackers.G3MINI import G3MINI

# ─── Helpers ──────────────────────────────────────────────────


def _config() -> dict[str, Any]:
    return {
        'TRACKERS': {
            'G3MINI': {
                'api_key': 'test-api-key',
                'announce_url': 'https://gemini-tracker.org/announce/FAKE',
            },
        },
        'DEFAULT': {'tmdb_api': 'fake-tmdb-key'},
    }


def _meta_base(**overrides: Any) -> dict[str, Any]:
    m: dict[str, Any] = {
        'category': 'MOVIE',
        'type': 'REMUX',
        'title': 'Harry Potter and the Goblet of Fire',
        'year': '2005',
        'resolution': '2160p',
        'source': 'BluRay',
        'audio': 'DTS:X 7.1',
        'video_encode': '',
        'video_codec': 'HEVC',
        'service': '',
        'tag': '-SGF',
        'edition': '',
        'repack': '',
        '3D': '',
        'uhd': 'UHD',
        'hdr': 'DV HDR',
        'webdv': 'Hybrid',
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
        'tv_pack': 0,
        'path': '',
        'name': '',
        'uuid': 'test-uuid',
        'base_dir': '/tmp',
        'overview': '',
        'poster': '',
        'tmdb': 1234,
        'imdb_id': 1234567,
        'original_language': 'en',
        'image_list': [],
        'bdinfo': None,
        'region': '',
        'dvd_size': '',
        'has_audiodesc': False,
        'mediainfo': {
            'media': {
                'track': [
                    {'@type': 'Audio', 'Language': 'en'},
                    {'@type': 'Audio', 'Language': 'fr'},
                ],
            },
        },
        'tracker_status': {'G3MINI': {}},
    }
    m.update(overrides)
    return m


# ─── Tests ────────────────────────────────────────────────────


class TestGetName:
    """Tests for G3MINI release naming order."""

    @staticmethod
    def _run(meta: dict[str, Any]) -> str:
        g = G3MINI(_config())
        result = asyncio.run(g.get_name(meta))
        return result['name']

    def test_remux_hybrid_before_hdr_codec_after_audio(self):
        """Hybrid must sit next to HDR; video codec must come after audio."""
        meta = _meta_base()
        name = self._run(meta)
        # Hybrid.DV.HDR must appear together after REMUX
        assert 'REMUX.Hybrid.DV.HDR' in name, f"Hybrid not next to HDR: {name}"
        # Video codec (HEVC) must be after audio, right before group tag
        assert name.endswith('HEVC-SGF'), f"HEVC not at end: {name}"
        # Audio must come before HEVC
        idx_audio = name.find('DTSX.7.1')
        idx_codec = name.find('HEVC-SGF')
        assert idx_audio < idx_codec, f"Audio not before video codec: {name}"

    def test_remux_no_hybrid(self):
        """Without Hybrid, HDR sits directly after REMUX."""
        meta = _meta_base(webdv='')
        name = self._run(meta)
        assert 'REMUX.DV.HDR' in name, f"HDR not after REMUX: {name}"
        assert name.endswith('HEVC-SGF'), f"HEVC not at end: {name}"

    def test_disc_bdmv_hybrid_before_hdr_codec_after_audio(self):
        """BDMV disc: same ordering rules as REMUX."""
        meta = _meta_base(type='DISC', is_disc='BDMV')
        name = self._run(meta)
        assert 'Hybrid.DV.HDR' in name, f"Hybrid not next to HDR: {name}"
        idx_audio = name.find('DTSX.7.1')
        idx_codec = name.find('HEVC')
        assert idx_audio < idx_codec, f"Audio not before video codec: {name}"

    def test_encode_hybrid_before_hdr(self):
        """ENCODE: Hybrid must be right before HDR, video encode at end."""
        meta = _meta_base(
            type='ENCODE',
            video_encode='x265',
            video_codec='',
            source='BluRay',
        )
        name = self._run(meta)
        # Hybrid should be near HDR, not before language
        assert 'Hybrid.DV.HDR' in name, f"Hybrid not next to HDR: {name}"
        assert name.endswith('x265-SGF'), f"Video encode not at end: {name}"

    def test_webdl_hybrid_before_hdr(self):
        """WEB-DL: Hybrid must be right before HDR."""
        meta = _meta_base(
            type='WEBDL',
            source='WEB',
            video_encode='H265',
            video_codec='',
            service='NF',
        )
        name = self._run(meta)
        assert 'Hybrid.DV.HDR' in name, f"Hybrid not next to HDR: {name}"
        assert name.endswith('H265-SGF'), f"Video encode not at end: {name}"

    def test_tv_remux_hybrid_before_hdr_codec_after_audio(self):
        """TV REMUX: same ordering as MOVIE REMUX."""
        meta = _meta_base(
            category='TV',
            season='S01',
            episode='E01',
        )
        name = self._run(meta)
        assert 'REMUX.Hybrid.DV.HDR' in name, f"Hybrid not next to HDR: {name}"
        assert name.endswith('HEVC-SGF'), f"HEVC not at end: {name}"

    def test_harry_potter_exact_case(self):
        """Reproduce the exact rejection from G3MINI staff."""
        meta = _meta_base(
            has_audiodesc=True,
            mediainfo={
                'media': {
                    'track': [
                        {'@type': 'Audio', 'Language': 'en'},
                        {'@type': 'Audio', 'Language': 'fr', 'Format': 'DTS', 'Format_AdditionalFeatures': 'XLL X'},
                    ],
                },
            },
        )
        name = self._run(meta)
        # Must NOT have Hybrid before MULTi
        assert '.Hybrid.AD.' not in name and '.Hybrid.MULTi' not in name, f"Hybrid misplaced: {name}"
        # Hybrid.DV.HDR must appear together
        assert 'REMUX.Hybrid.DV.HDR' in name, f"Hybrid not next to HDR: {name}"
        # HEVC at end before tag
        assert name.endswith('HEVC-SGF'), f"HEVC not at end: {name}"
        # Audio before video codec
        assert 'DTSX.7.1' in name or 'DTS' in name, f"Audio missing: {name}"

    def test_tv_hddvd_includes_season_episode(self):
        """TV HDDVD DISC must include season/episode in the name."""
        meta = _meta_base(
            category='TV',
            type='DISC',
            is_disc='HDDVD',
            source='HDDVD',
            season='S02',
            episode='E05',
            webdv='',
            hdr='',
            uhd='',
        )
        name = self._run(meta)
        assert 'S02E05' in name, f"Season/episode missing: {name}"
        assert name.endswith('HEVC-SGF'), f"Video codec not at end: {name}"

    def test_webrip_type_handling(self):
        """WEBRIP: WEBRip tag present, Hybrid before HDR, encode at end."""
        meta = _meta_base(
            type='WEBRIP',
            source='WEB',
            video_encode='H265',
            video_codec='',
            service='AMZN',
        )
        name = self._run(meta)
        assert 'WEBRip' in name, f"WEBRip tag missing: {name}"
        assert 'Hybrid.DV.HDR' in name, f"Hybrid not next to HDR: {name}"
        assert name.endswith('H265-SGF'), f"Video encode not at end: {name}"

    def test_dvdrip_type_handling(self):
        """DVDRIP: language tag must be present in the name."""
        meta = _meta_base(
            type='DVDRIP',
            source='DVD',
            video_encode='x264',
            video_codec='',
            webdv='',
            hdr='',
            uhd='',
        )
        name = self._run(meta)
        assert 'DVDRip' in name, f"DVDRip tag missing: {name}"
        # Language tag (MULTi) must appear
        assert 'MULTi' in name, f"Language tag missing: {name}"
        assert name.endswith('x264-SGF'), f"Video encode not at end: {name}"

    def test_tv_dvdrip_includes_episode(self):
        """TV DVDRIP must include both season and episode in the name."""
        meta = _meta_base(
            category='TV',
            type='DVDRIP',
            source='DVD',
            video_encode='x264',
            video_codec='',
            season='S01',
            episode='E03',
            webdv='',
            hdr='',
            uhd='',
        )
        name = self._run(meta)
        assert 'S01E03' in name, f"Season+episode missing: {name}"
        assert 'DVDRip' in name, f"DVDRip tag missing: {name}"
        assert name.endswith('x264-SGF'), f"Video encode not at end: {name}"

    # ── Language suffix tests ────────────────────────────────

    def test_multi_includes_vff_suffix(self):
        """MULTi must always carry a precision suffix (e.g. MULTi.VFF)."""
        meta = _meta_base()  # en + fr audio → MULTI.VFF → MULTi.VFF
        name = self._run(meta)
        assert 'MULTi.VFF' in name, f"MULTi.VFF missing: {name}"

    def test_belgian_french_detected_as_vfb(self):
        """A fr-be audio track must produce MULTi.VFB."""
        meta = _meta_base(
            mediainfo={
                'media': {
                    'track': [
                        {'@type': 'Audio', 'Language': 'en'},
                        {'@type': 'Audio', 'Language': 'fr-be'},
                    ],
                },
            },
        )
        name = self._run(meta)
        assert 'MULTi.VFB' in name, f"MULTi.VFB missing: {name}"

    def test_vfi_replaced_by_vff(self):
        """VFI in the filename must be normalised to VFF for G3MINI."""
        meta = _meta_base(
            uuid='Some.Movie.VFI.1080p',
            name='Some.Movie.VFI.1080p',
        )
        name = self._run(meta)
        assert 'VFF' in name, f"VFF missing after VFI normalisation: {name}"
        assert 'VFI' not in name, f"VFI should not appear: {name}"

    # ── Season pack / COMPLETE ───────────────────────────────

    def test_tv_season_pack_includes_complete(self):
        """A full season pack (tv_pack=1, no episode) must include COMPLETE."""
        meta = _meta_base(
            category='TV',
            type='WEBDL',
            source='WEB',
            video_encode='H265',
            video_codec='',
            service='NF',
            season='S01',
            episode='',
            tv_pack=1,
            webdv='',
            hdr='',
            uhd='',
        )
        name = self._run(meta)
        assert 'S01.COMPLETE' in name, f"COMPLETE missing for season pack: {name}"

    def test_tv_episode_does_not_include_complete(self):
        """A single episode must NOT include COMPLETE."""
        meta = _meta_base(
            category='TV',
            type='WEBDL',
            source='WEB',
            video_encode='H265',
            video_codec='',
            service='NF',
            season='S01',
            episode='E03',
            tv_pack=0,
            webdv='',
            hdr='',
            uhd='',
        )
        name = self._run(meta)
        assert 'COMPLETE' not in name, f"COMPLETE must not appear for single episode: {name}"
        assert 'S01E03' in name, f"S01E03 missing: {name}"

    def test_tv_season_pack_remux_includes_complete(self):
        """Season pack also works for REMUX type."""
        meta = _meta_base(
            category='TV',
            type='REMUX',
            source='BluRay',
            season='S02',
            episode='',
            tv_pack=1,
        )
        name = self._run(meta)
        assert 'S02.COMPLETE' in name, f"COMPLETE missing for REMUX season pack: {name}"

    # ── H.264 / H.265 conversion ─────────────────────────────

    def test_webdl_h265_dot_converted(self):
        """H.265 from prep (with dot) must be normalised to H265 in the name."""
        meta = _meta_base(
            type='WEBDL',
            source='WEB',
            video_encode='H.265',
            video_codec='',
            service='NF',
            webdv='',
            hdr='',
            uhd='',
        )
        name = self._run(meta)
        assert 'H265' in name, f"H265 (no dot) expected: {name}"
        assert 'H.265' not in name, f"H.265 with dot must not appear: {name}"

    def test_webdl_h264_dot_converted(self):
        """H.264 from prep (with dot) must be normalised to H264 in the name."""
        meta = _meta_base(
            type='WEBDL',
            source='WEB',
            video_encode='H.264',
            video_codec='',
            service='NF',
            webdv='',
            hdr='',
            uhd='',
        )
        name = self._run(meta)
        assert 'H264' in name, f"H264 (no dot) expected: {name}"
        assert 'H.264' not in name, f"H.264 with dot must not appear: {name}"

    def test_encode_x265_unchanged(self):
        """x265 for encodes must pass through unchanged."""
        meta = _meta_base(
            type='ENCODE',
            source='BluRay',
            video_encode='x265',
            video_codec='',
            webdv='',
            hdr='',
            uhd='',
        )
        name = self._run(meta)
        assert name.endswith('x265-SGF'), f"x265 not at end: {name}"

    def test_tv_dvd_disc_3d_has_space_before(self):
        """DVD DISC season_ep and three_d must be separated (not concatenated as S01E013D)."""
        meta = _meta_base(
            category='TV',
            type='DISC',
            is_disc='DVD',
            source='DVD',
            season='S01',
            episode='E01',
            **{'3D': '3D'},
            video_encode='',
            video_codec='',
            webdv='',
            hdr='',
            uhd='',
            region='',
            dvd_size='',
        )
        name = self._run(meta)
        # Before the fix, season_ep+three_d were concatenated → 'S01E013D'
        assert 'S01E013D' not in name, f"season_ep and 3D must not be merged: {name}"
        assert 'S01E01' in name, f"season_ep missing: {name}"
        assert '3D' in name, f"3D tag missing: {name}"


# ─── Integrale dupe check ─────────────────────────────────────


class TestG3MiniIntegraleDupes:
    """_check_g3mini_specific_dupes must re-inject integrale releases
    when uploading a season pack."""

    @staticmethod
    def _g3() -> G3MINI:
        return G3MINI(_config())

    def test_integrale_dupe_blocks_season_pack(self):
        """An existing 'integrale' release must be kept in the dupe list."""
        g = self._g3()
        meta = {'tv_pack': 1, 'category': 'TV'}
        all_dupes = [{'name': 'Breaking.Bad.iNTEGRALE.MULTi.1080p.BluRay.x264-GRP', 'flags': []}]
        filtered: list = []  # French filter dropped it
        result = g._check_g3mini_specific_dupes(all_dupes, filtered, meta)
        assert len(result) == 1
        assert 'integrale_supersede' in result[0]['flags']

    def test_integrale_flag_not_duplicated(self):
        """integrale_supersede should appear only once even if called twice."""
        g = self._g3()
        meta = {'tv_pack': 1, 'category': 'TV'}
        dupe = {'name': 'Show.iNTEGRALE.VFF.1080p-GRP', 'flags': ['integrale_supersede']}
        result = g._check_g3mini_specific_dupes([dupe], [dupe], meta)
        assert result[0]['flags'].count('integrale_supersede') == 1

    def test_non_integrale_dupe_not_reinjected(self):
        """A regular (non-integrale) dupe dropped by the French filter stays dropped."""
        g = self._g3()
        meta = {'tv_pack': 1, 'category': 'TV'}
        all_dupes = [{'name': 'Breaking.Bad.S01.MULTi.1080p.BluRay.x264-GRP', 'flags': []}]
        filtered: list = []
        result = g._check_g3mini_specific_dupes(all_dupes, filtered, meta)
        assert result == []

    def test_non_season_pack_ignored(self):
        """Integrale check must not fire for single-episode uploads."""
        g = self._g3()
        meta = {'tv_pack': 0, 'category': 'TV'}
        all_dupes = [{'name': 'Show.iNTEGRALE.VFF.1080p-GRP', 'flags': []}]
        filtered: list = []
        result = g._check_g3mini_specific_dupes(all_dupes, filtered, meta)
        assert result == []

    def test_movie_upload_ignored(self):
        """Integrale check must not fire for movie uploads."""
        g = self._g3()
        meta = {'tv_pack': 1, 'category': 'MOVIE'}
        all_dupes = [{'name': 'Movie.iNTEGRALE.1080p-GRP', 'flags': []}]
        filtered: list = []
        result = g._check_g3mini_specific_dupes(all_dupes, filtered, meta)
        assert result == []

    def test_integrale_case_insensitive(self):
        """Match must be case-insensitive: INTEGRALE, integrale, iNTEGRALE."""
        g = self._g3()
        meta = {'tv_pack': 1, 'category': 'TV'}
        for name_variant in ['Show.INTEGRALE.VFF-GRP', 'Show.integrale.VFF-GRP', 'Show.iNTEGRALE.VFF-GRP']:
            dupe = {'name': name_variant, 'flags': []}
            result = g._check_g3mini_specific_dupes([dupe], [], meta)
            assert len(result) == 1, f"integrale not matched in: {name_variant}"
            assert 'integrale_supersede' in result[0]['flags']

    def test_already_in_filtered_not_duplicated(self):
        """A dupe that's already in filtered must appear only once in result."""
        g = self._g3()
        meta = {'tv_pack': 1, 'category': 'TV'}
        dupe = {'name': 'Show.iNTEGRALE.VFF.1080p-GRP', 'flags': []}
        result = g._check_g3mini_specific_dupes([dupe], [dupe], meta)
        assert result.count(dupe) == 1

    def test_flag_set_on_stored_object_not_local_copy(self):
        """integrale_supersede must be set on the object stored in result,
        even when filtered holds an equal-but-distinct copy of the dupe."""
        g = self._g3()
        meta = {'tv_pack': 1, 'category': 'TV'}
        dupe_in_all = {'name': 'Show.iNTEGRALE.VFF.1080p-GRP', 'flags': []}
        # filtered holds a shallow copy — equal by value, distinct by identity
        dupe_in_filtered = dict(dupe_in_all)
        dupe_in_filtered['flags'] = []
        assert dupe_in_filtered is not dupe_in_all  # distinct objects
        result = g._check_g3mini_specific_dupes([dupe_in_all], [dupe_in_filtered], meta)
        # The entry in result must carry the flag
        assert len(result) == 1
        assert 'integrale_supersede' in result[0]['flags'], (
            "flag must be on the stored result object, not only on the local dupe"
        )


# ═══════════════════════════════════════════════════════════════
#  Notag — tag replacement in G3MINI.get_name()
# ═══════════════════════════════════════════════════════════════


class TestG3MININotagGetName:
    """Tag replacement in G3MINI.get_name()."""

    @pytest.fixture
    def g3mini(self):
        return G3MINI(config=_config())

    def _base_meta(self, **overrides):
        m = {
            "category": "MOVIE",
            "type": "WEBDL",
            "title": "Chainsaw Man",
            "year": "2024",
            "resolution": "1080p",
            "source": "WEB",
            "audio": "AAC",
            "video_encode": "x264",
            "video_codec": "",
            "service": "",
            "tag": "-GRP",
            "edition": "",
            "repack": "",
            "3D": "",
            "uhd": "",
            "hdr": "",
            "webdv": "",
            "part": "",
            "season": "",
            "episode": "",
            "is_disc": None,
            "search_year": "",
            "manual_year": None,
            "manual_date": None,
            "no_season": False,
            "no_year": False,
            "no_aka": False,
            "debug": False,
            "tv_pack": 0,
            "imdb_info": {"aka": "", "original_language": "ja"},
            "mediainfo": {},
            "audio_languages": ["French"],
            "subtitle_languages": [],
        }
        m.update(overrides)
        return m

    def test_valid_tag_unchanged(self, g3mini):
        meta = self._base_meta(tag="-GRP")
        result = asyncio.run(g3mini.get_name(meta))
        assert result["name"].endswith("-GRP")

    def test_empty_tag_uses_nogrp_label(self, g3mini):
        meta = self._base_meta(tag="")
        result = asyncio.run(g3mini.get_name(meta))
        assert result["name"].endswith("-NoGrP")

    def test_nogrp_tag_replaced(self, g3mini):
        meta = self._base_meta(tag="-NoGrp")
        result = asyncio.run(g3mini.get_name(meta))
        assert result["name"].endswith("-NoGrP")


# ═══════════════════════════════════════════════════════════════
#  get_additional_checks — x264 preset quality gate
# ═══════════════════════════════════════════════════════════════


class TestG3MINIAdditionalChecksX264Preset:
    """G3MINI rejects x264 encodes that cannot prove ≥ 'slow' preset quality."""

    @staticmethod
    def _g3() -> G3MINI:
        return G3MINI(_config())

    def _meta(self, encoding_settings: str | None, **overrides: Any) -> dict[str, Any]:
        video_track: dict[str, Any] = {"@type": "Video"}
        if encoding_settings is not None:
            video_track["Encoded_Library_Settings"] = encoding_settings
        m = _meta_base(
            type="ENCODE",
            video_codec="AVC",
            video_encode=" x264",
            source="BluRay",
            is_disc=None,
            mediainfo={
                "media": {
                    "track": [
                        video_track,
                        {"@type": "Audio", "Language": "fr"},
                    ]
                }
            },
            audio_languages=["French"],
            subtitle_languages=[],
        )
        m.update(overrides)
        return m

    def test_no_encoding_settings_is_rejected(self):
        """Scene releases without Encoded_Library_Settings must be blocked."""
        meta = self._meta(encoding_settings=None)
        result = asyncio.run(self._g3().get_additional_checks(meta))
        assert result is False

    def test_empty_encoding_settings_is_rejected(self):
        """Empty Encoded_Library_Settings string must be blocked."""
        meta = self._meta(encoding_settings="")
        result = asyncio.run(self._g3().get_additional_checks(meta))
        assert result is False

    def test_medium_preset_subme7_is_rejected(self):
        """subme=7 alone (trellis meets minimum) must be rejected."""
        meta = self._meta(encoding_settings="cabac=1 / ref=5 / subme=7 / trellis=2")
        result = asyncio.run(self._g3().get_additional_checks(meta))
        assert result is False

    def test_medium_preset_trellis1_is_rejected(self):
        """trellis=1 (medium) must be rejected."""
        meta = self._meta(encoding_settings="subme=8 / trellis=1")
        result = asyncio.run(self._g3().get_additional_checks(meta))
        assert result is False

    def test_slow_preset_passes(self):
        """subme=8, trellis=2 (slow) must pass."""
        meta = self._meta(encoding_settings="cabac=1 / ref=5 / subme=8 / trellis=2")
        result = asyncio.run(self._g3().get_additional_checks(meta))
        assert result is True

    def test_veryslow_preset_passes(self):
        """subme=10, trellis=2 (veryslow) must pass."""
        meta = self._meta(encoding_settings="subme=10 / trellis=2 / ref=8")
        result = asyncio.run(self._g3().get_additional_checks(meta))
        assert result is True

    def test_remux_skips_preset_check(self):
        """REMUX type must not be blocked by the preset check even with x264 video_encode."""
        meta = self._meta(encoding_settings=None, type="REMUX", video_codec="AVC", video_encode=" x264")
        result = asyncio.run(self._g3().get_additional_checks(meta))
        assert result is True

    def test_disc_skips_preset_check(self):
        """Full disc (is_disc=BDMV) must not be blocked by the preset check."""
        meta = self._meta(encoding_settings=None, is_disc="BDMV")
        result = asyncio.run(self._g3().get_additional_checks(meta))
        assert result is True


# ═══════════════════════════════════════════════════════════════
#  Nogroup WEB-DL naming — regression for Cyclo-style filenames
# ═══════════════════════════════════════════════════════════════


class TestNogroupWebDL:
    """WEB-DL releases without a group tag must use G3MINI's notag_label.

    G3MINI uses WEB_LABEL='WEB-DL' and notag_label='NoGrP'.
    Regression: Cyclo.1995.1080p.WEB-DL.AAC.2.0.H.264.mkv had a false
    group '-DL.AAC.2.0.H.264' extracted, producing duplicated tokens.
    """

    def _get_name(self, meta: dict) -> str:
        return asyncio.run(G3MINI(_config()).get_name(meta))['name']

    def test_empty_tag_uses_notag_label(self):
        """tag='' (nogroup) must produce a name ending with '-NoGrP'."""
        meta = _meta_base(
            type='WEBDL',
            source='WEB',
            audio='AAC 2.0',
            video_encode='H.264',
            video_codec='H.264',
            tag='',
        )
        name = self._get_name(meta)
        assert name.endswith('-NoGrP'), f"Expected -NoGrP suffix, got: {name!r}"

    def test_no_audio_duplication(self):
        """Audio token must appear exactly once — no duplication from a false tag."""
        meta = _meta_base(
            type='WEBDL',
            source='WEB',
            audio='AAC 2.0',
            video_encode='H.264',
            video_codec='H.264',
            tag='',
        )
        name = self._get_name(meta)
        assert name.count('AAC') == 1, (
            f"Audio token 'AAC' duplicated in name: {name!r}."
        )

    def test_real_group_preserved(self):
        """A real group tag must not be replaced by the notag label."""
        meta = _meta_base(
            type='WEBDL',
            source='WEB',
            audio='AAC 2.0',
            video_encode='H.264',
            video_codec='H.264',
            tag='-GROUP',
        )
        name = self._get_name(meta)
        assert name.endswith('-GROUP'), f"Expected -GROUP suffix, got: {name!r}"


# ---------------------------------------------------------------------------
# Tests – 1080p + UHD stripping
# ---------------------------------------------------------------------------


class TestG3MINIUhdStripping:
    """G3MINI never carries the UHD token.

    At 2160p it's redundant (2160p already denotes UHD); at any lower
    resolution it's invalid. Either way it must be stripped from the name
    even when meta['uhd'] is set.
    """

    def _get_name(self, meta: dict) -> str:
        return asyncio.run(G3MINI(_config()).get_name(meta))['name']

    def test_1080p_remux_uhd_stripped(self):
        """1080p BluRay REMUX with uhd='UHD' must not contain 'UHD' in the name."""
        meta = _meta_base(
            resolution='1080p',
            uhd='UHD',
            type='REMUX',
            source='BluRay',
        )
        name = self._get_name(meta)
        assert 'UHD' not in name, f"'UHD' must be stripped for 1080p, got: {name!r}"

    def test_1080p_encode_uhd_stripped(self):
        """1080p ENCODE with uhd='UHD' must not contain 'UHD' in the name."""
        meta = _meta_base(
            resolution='1080p',
            uhd='UHD',
            type='ENCODE',
            source='BluRay',
            video_encode='x265',
            video_codec='H.265',
        )
        name = self._get_name(meta)
        assert 'UHD' not in name, f"'UHD' must be stripped for 1080p ENCODE, got: {name!r}"

    def test_2160p_remux_uhd_stripped(self):
        """2160p BluRay REMUX must not repeat 'UHD' — it's redundant with 2160p."""
        meta = _meta_base(
            resolution='2160p',
            uhd='UHD',
            type='REMUX',
            source='BluRay',
        )
        name = self._get_name(meta)
        assert 'UHD' not in name, f"'UHD' must be stripped for 2160p, got: {name!r}"

    def test_1080p_without_uhd_unaffected(self):
        """1080p release with uhd='' must not have 'UHD' introduced."""
        meta = _meta_base(
            resolution='1080p',
            uhd='',
            type='REMUX',
            source='BluRay',
        )
        name = self._get_name(meta)
        assert 'UHD' not in name, f"'UHD' must not appear, got: {name!r}"


class TestG3MINIHdr10Plus:
    """G3MINI spells HDR10+ as HDR10P (no '+')."""

    def _get_name(self, meta: dict) -> str:
        return asyncio.run(G3MINI(_config()).get_name(meta))['name']

    def test_hdr10_plus_becomes_hdr10p(self):
        meta = _meta_base(
            resolution='2160p',
            type='REMUX',
            source='BluRay',
            hdr='HDR10+',
        )
        name = self._get_name(meta)
        assert 'HDR10P' in name, f"HDR10+ must render as HDR10P, got: {name!r}"
        assert 'HDR10+' not in name, f"'+' must be gone, got: {name!r}"


class TestG3MINIFrenchTitle:
    """French-origin works must use the French title in the release name."""

    def _get_name(self, meta: dict) -> str:
        return asyncio.run(G3MINI(_config()).get_name(meta))['name']

    def test_french_origin_uses_french_title(self):
        meta = _meta_base(
            title='The Price of Peril',
            original_language='fr',
            frtitle='Le Prix du Danger',
            type='ENCODE',
            video_encode='x264',
            video_codec='',
            hdr='',
            webdv='',
            uhd='',
            resolution='1080p',
        )
        name = self._get_name(meta)
        assert name.startswith('Le.Prix.du.Danger'), f"French title expected, got: {name!r}"
        assert 'Price.of.Peril' not in name

    def test_accented_title_is_transliterated_not_stripped(self):
        """Accented letters must transliterate (é→e, à→a), never vanish."""
        meta = _meta_base(
            title='Cleo from 5 to 7',
            original_language='fr',
            frtitle='Cléo de 5 à 7',
            type='ENCODE',
            video_encode='x264',
            video_codec='',
            hdr='',
            webdv='',
            uhd='',
            resolution='1080p',
        )
        name = self._get_name(meta)
        assert name.startswith('Cleo.de.5.a.7'), f"Transliterated title expected, got: {name!r}"

    def test_elided_article_apostrophe_becomes_separator(self):
        """L'autre → L.autre (apostrophe expanded, not glued)."""
        meta = _meta_base(
            title="One Sings, the Other Doesn't",
            original_language='fr',
            frtitle="L'une chante, l'autre pas",
            type='ENCODE',
            video_encode='x264',
            video_codec='',
            hdr='',
            webdv='',
            uhd='',
            resolution='1080p',
        )
        name = self._get_name(meta)
        assert name.startswith('L.une.chante.l.autre.pas'), f"Expanded elision expected, got: {name!r}"

    def test_french_origin_fetches_title_when_uncached(self):
        """Without a cached frtitle, the title comes from the localized TMDB data."""
        meta = _meta_base(
            title='The Price of Peril',
            original_language='fr',
            type='ENCODE',
            video_encode='x264',
            video_codec='',
            hdr='',
            webdv='',
            uhd='',
            resolution='1080p',
        )
        g = G3MINI(_config())

        async def fake_localized(*args, **kwargs):
            return {'title': 'Le Prix du Danger', 'original_title': 'Le Prix du Danger', 'original_language': 'fr'}

        g.tmdb_manager.get_tmdb_localized_data = fake_localized
        name = asyncio.run(g.get_name(meta))['name']
        assert name.startswith('Le.Prix.du.Danger'), f"French title expected, got: {name!r}"
        assert 'Price.of.Peril' not in name

    def test_non_french_origin_keeps_main_title(self):
        meta = _meta_base(
            title='Some English Title',
            original_language='en',
            frtitle='Un Titre Français',
            type='ENCODE',
            video_encode='x264',
            video_codec='',
            hdr='',
            webdv='',
            uhd='',
            resolution='1080p',
        )
        name = self._get_name(meta)
        assert name.startswith('Some.English.Title'), f"Main title expected, got: {name!r}"


class TestG3MINIEncodeCodecLabel:
    """Encodes must be labeled x264/x265, never H264/H265."""

    def _get_name(self, meta: dict) -> str:
        return asyncio.run(G3MINI(_config()).get_name(meta))['name']

    def _web_meta(self, **overrides) -> dict:
        base = dict(
            type='WEBDL',
            video_encode='H.264',
            video_codec='',
            hdr='',
            webdv='',
            uhd='',
            resolution='1080p',
            source='Web',
        )
        base.update(overrides)
        return _meta_base(**base)

    def test_webdl_with_encode_settings_uses_x264(self):
        meta = self._web_meta(has_encode_settings=True)
        name = self._get_name(meta)
        assert 'x264' in name, f"x264 expected for an encode, got: {name!r}"
        assert 'H264' not in name

    def test_webdl_with_encode_settings_uses_x265(self):
        meta = self._web_meta(video_encode='H.265', has_encode_settings=True)
        name = self._get_name(meta)
        assert 'x265' in name, f"x265 expected for an encode, got: {name!r}"
        assert 'H265' not in name

    def test_true_webdl_keeps_h264(self):
        meta = self._web_meta(has_encode_settings=False)
        name = self._get_name(meta)
        assert 'H264' in name, f"Untouched WEB-DL keeps H264, got: {name!r}"
        assert 'x264' not in name, f"x264 must not appear for a true WEB-DL, got: {name!r}"

    def test_true_webdl_keeps_h265(self):
        meta = self._web_meta(video_encode='H.265', has_encode_settings=False)
        name = self._get_name(meta)
        assert 'H265' in name, f"Untouched WEB-DL keeps H265, got: {name!r}"
        assert 'x265' not in name, f"x265 must not appear for a true WEB-DL, got: {name!r}"
