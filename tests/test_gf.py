# Tests for GF tracker — generation-free.org
"""
Test suite for the GF tracker implementation.
Covers: category mapping, type mapping (language-aware), resolution mapping,
        audio string, release naming, and additional checks.
"""

import asyncio
import re
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.trackers.GF import GF

# ─── Helpers ──────────────────────────────────────────────────


def _config(extra_tracker: dict[str, Any] | None = None) -> dict[str, Any]:
    tracker_cfg: dict[str, Any] = {
        'api_key': 'test-api-key-gf',
        'announce_url': 'https://generation-free.org/announce/FAKE_PASSKEY',
    }
    if extra_tracker:
        tracker_cfg.update(extra_tracker)
    return {
        'TRACKERS': {'GF': tracker_cfg},
        'DEFAULT': {'tmdb_api': 'fake-tmdb-key'},
    }


def _meta_base(**overrides: Any) -> dict[str, Any]:
    m: dict[str, Any] = {
        'category': 'MOVIE',
        'type': 'WEBDL',
        'title': 'Le Prenom',
        'year': '2012',
        'resolution': '1080p',
        'source': 'WEB',
        'audio': 'AC3',
        'video_encode': 'x264',
        'video_codec': '',
        'service': '',
        'tag': '-GF',
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
        'tv_pack': 0,
        'path': '',
        'name': '',
        'uuid': 'test-uuid',
        'base_dir': '/tmp',
        'overview': 'Un diner entre amis.',
        'poster': '',
        'tmdb': 1234,
        'imdb_id': 1234567,
        'original_language': 'fr',
        'image_list': [],
        'bdinfo': None,
        'region': '',
        'dvd_size': '',
        'mediainfo': {
            'media': {
                'track': []
            }
        },
        'tracker_status': {'GF': {}},
    }
    m.update(overrides)
    return m


def _audio_track(lang: str = 'fr', **kw: Any) -> dict[str, Any]:
    t: dict[str, Any] = {'@type': 'Audio', 'Language': lang}
    t.update(kw)
    return t


def _sub_track(lang: str = 'fr') -> dict[str, Any]:
    return {'@type': 'Text', 'Language': lang}


def _mi(audio: list[dict[str, Any]], subs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    tracks: list[dict[str, Any]] = [{'@type': 'General'}]
    tracks.extend(audio)
    if subs:
        tracks.extend(subs)
    return {'media': {'track': tracks}}


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def gf():
    return GF(_config())


# ═══════════════════════════════════════════════════════════════
#  Init
# ═══════════════════════════════════════════════════════════════


class TestInit:
    def test_tracker_name(self, gf):
        assert gf.tracker == 'GF'

    def test_base_url(self, gf):
        assert gf.base_url == 'https://generation-free.org'

    def test_upload_url(self, gf):
        assert gf.upload_url == 'https://generation-free.org/api/torrents/upload'

    def test_search_url(self, gf):
        assert gf.search_url == 'https://generation-free.org/api/torrents/filter'

    def test_source_flag(self, gf):
        assert gf.source_flag == 'GF'

    def test_web_label(self, gf):
        assert gf.WEB_LABEL == 'WEB'


# ═══════════════════════════════════════════════════════════════
#  Category ID
# ═══════════════════════════════════════════════════════════════


class TestCategoryID:
    def test_movie(self, gf):
        meta = _meta_base(category='MOVIE')
        result = _run(gf.get_category_id(meta))
        assert result == {'category_id': '1'}

    def test_tv(self, gf):
        meta = _meta_base(category='TV')
        result = _run(gf.get_category_id(meta))
        assert result == {'category_id': '2'}

    def test_unknown(self, gf):
        meta = _meta_base(category='GAME')
        result = _run(gf.get_category_id(meta))
        assert result == {'category_id': '0'}

    def test_mapping_only(self, gf):
        result = _run(gf.get_category_id({}, mapping_only=True))
        assert result == {'MOVIE': '1', 'TV': '2'}

    def test_reverse(self, gf):
        result = _run(gf.get_category_id({}, reverse=True))
        assert result == {'1': 'MOVIE', '2': 'TV'}


# ═══════════════════════════════════════════════════════════════
#  Resolution ID
# ═══════════════════════════════════════════════════════════════


class TestResolutionID:
    @pytest.mark.parametrize('res, expected', [
        ('4320p', '1'),
        ('2160p', '2'),
        ('1080p', '3'),
        ('1080i', '4'),
        ('720p', '5'),
        ('576p', '10'),   # falls back to Other
        ('480p', '10'),
    ])
    def test_resolution(self, gf, res, expected):
        meta = _meta_base(resolution=res)
        result = _run(gf.get_resolution_id(meta))
        assert result == {'resolution_id': expected}

    def test_mapping_only(self, gf):
        result = _run(gf.get_resolution_id({}, mapping_only=True))
        assert '2160p' in result

    def test_reverse(self, gf):
        result = _run(gf.get_resolution_id({}, reverse=True))
        assert '3' in result


# ═══════════════════════════════════════════════════════════════
#  Type ID — GF's unique language/content-aware type system
# ═══════════════════════════════════════════════════════════════


class TestTypeID:
    """GF uses a non-standard type system where VOSTFR/VO releases
    get dedicated types, and encodes are split by resolution/codec."""

    # ── WEB releases ──

    def test_webdl_french(self, gf):
        meta = _meta_base(type='WEBDL', mediainfo=_mi([_audio_track('fr')]))
        result = _run(gf.get_type_id(meta))
        assert result == {'type_id': '16'}  # WEB

    def test_webrip_multi(self, gf):
        meta = _meta_base(type='WEBRIP', mediainfo=_mi([_audio_track('fr'), _audio_track('en')]))
        result = _run(gf.get_type_id(meta))
        assert result == {'type_id': '16'}  # WEB

    # ── VOSTFR → type 14 ──

    def test_vostfr_web(self, gf):
        meta = _meta_base(type='WEBDL', mediainfo=_mi([_audio_track('en')], [_sub_track('fr')]))
        result = _run(gf.get_type_id(meta))
        assert result == {'type_id': '14'}  # VOSTFR

    def test_vostfr_encode(self, gf):
        meta = _meta_base(type='ENCODE', mediainfo=_mi([_audio_track('en')], [_sub_track('fr')]))
        result = _run(gf.get_type_id(meta))
        assert result == {'type_id': '14'}

    # ── VO → type 15 ──

    def test_vo_web(self, gf):
        meta = _meta_base(type='WEBDL', mediainfo=_mi([_audio_track('en')]))
        result = _run(gf.get_type_id(meta))
        assert result == {'type_id': '15'}  # VO

    def test_vo_encode(self, gf):
        meta = _meta_base(type='ENCODE', mediainfo=_mi([_audio_track('ja')]))
        result = _run(gf.get_type_id(meta))
        assert result == {'type_id': '15'}

    # ── Encode by resolution ──

    def test_encode_1080p_hd(self, gf):
        meta = _meta_base(type='ENCODE', resolution='1080p',
                          mediainfo=_mi([_audio_track('fr')]))
        result = _run(gf.get_type_id(meta))
        assert result == {'type_id': '8'}  # HD

    def test_encode_720p_x264(self, gf):
        meta = _meta_base(type='ENCODE', resolution='720p', video_encode='x264',
                          mediainfo=_mi([_audio_track('fr')]))
        result = _run(gf.get_type_id(meta))
        assert result == {'type_id': '9'}  # HDlight X264

    def test_encode_720p_x265(self, gf):
        meta = _meta_base(type='ENCODE', resolution='720p', video_encode='x265',
                          mediainfo=_mi([_audio_track('fr')]))
        result = _run(gf.get_type_id(meta))
        assert result == {'type_id': '10'}  # HDlight X265

    def test_encode_720p_hevc(self, gf):
        meta = _meta_base(type='ENCODE', resolution='720p', video_encode='HEVC',
                          mediainfo=_mi([_audio_track('fr')]))
        result = _run(gf.get_type_id(meta))
        assert result == {'type_id': '10'}  # HDlight X265 (HEVC = x265)

    def test_encode_480p_sd(self, gf):
        meta = _meta_base(type='ENCODE', resolution='480p', video_encode='x264',
                          mediainfo=_mi([_audio_track('fr')]))
        result = _run(gf.get_type_id(meta))
        assert result == {'type_id': '12'}  # SD

    def test_encode_2160p_4klight(self, gf):
        meta = _meta_base(type='ENCODE', resolution='2160p', video_encode='x265',
                          mediainfo=_mi([_audio_track('fr')]))
        result = _run(gf.get_type_id(meta))
        assert result == {'type_id': '42'}  # 4KLight

    # ── AV1 ──

    def test_av1_encode(self, gf):
        meta = _meta_base(type='ENCODE', resolution='1080p', video_encode='AV1',
                          mediainfo=_mi([_audio_track('fr')]))
        result = _run(gf.get_type_id(meta))
        assert result == {'type_id': '41'}  # AV1

    # ── Remux ──

    def test_remux_1080p(self, gf):
        meta = _meta_base(type='REMUX', resolution='1080p',
                          mediainfo=_mi([_audio_track('fr')]))
        result = _run(gf.get_type_id(meta))
        assert result == {'type_id': '11'}  # Remux

    def test_remux_2160p_4k(self, gf):
        meta = _meta_base(type='REMUX', resolution='2160p',
                          mediainfo=_mi([_audio_track('fr')]))
        result = _run(gf.get_type_id(meta))
        assert result == {'type_id': '2'}  # 4K

    # ── DISC ──

    def test_disc_dvd_iso(self, gf):
        meta = _meta_base(type='DISC', is_disc='DVD', resolution='480p',
                          mediainfo=_mi([_audio_track('fr')]))
        result = _run(gf.get_type_id(meta))
        assert result == {'type_id': '6'}  # Film ISO

    def test_disc_bdmv_2160p(self, gf):
        meta = _meta_base(type='DISC', is_disc='BDMV', resolution='2160p',
                          mediainfo=_mi([_audio_track('fr')]))
        result = _run(gf.get_type_id(meta))
        assert result == {'type_id': '2'}  # 4K

    def test_disc_bdmv_1080p(self, gf):
        meta = _meta_base(type='DISC', is_disc='BDMV', resolution='1080p',
                          mediainfo=_mi([_audio_track('fr')]))
        result = _run(gf.get_type_id(meta))
        assert result == {'type_id': '11'}  # Remux

    # ── HDTV ──

    def test_hdtv_1080p(self, gf):
        meta = _meta_base(type='HDTV', resolution='1080p',
                          mediainfo=_mi([_audio_track('fr')]))
        result = _run(gf.get_type_id(meta))
        assert result == {'type_id': '8'}  # HD

    # ── VOSTFR override takes priority over format ──

    def test_vostfr_overrides_remux(self, gf):
        meta = _meta_base(type='REMUX', resolution='2160p',
                          mediainfo=_mi([_audio_track('en')], [_sub_track('fr')]))
        result = _run(gf.get_type_id(meta))
        assert result == {'type_id': '14'}  # VOSTFR, not 4K

    def test_vo_overrides_encode(self, gf):
        meta = _meta_base(type='ENCODE', resolution='1080p',
                          mediainfo=_mi([_audio_track('en')]))
        result = _run(gf.get_type_id(meta))
        assert result == {'type_id': '15'}  # VO, not HD


# ═══════════════════════════════════════════════════════════════
#  Language detection (_build_audio_string)
# ═══════════════════════════════════════════════════════════════


class TestLanguageDetection:
    def test_no_mediainfo(self, gf):
        meta = _meta_base()
        meta.pop('mediainfo', None)
        assert _run(gf._build_audio_string(meta)) == ''

    def test_muet(self, gf):
        """No audio tracks → mixin returns MUET."""
        meta = _meta_base(mediainfo={'media': {'track': [{'@type': 'General'}]}})
        assert _run(gf._build_audio_string(meta)) == 'MUET'

    def test_vof_single(self, gf):
        """Single French track, originally French film → VOF."""
        meta = _meta_base(mediainfo=_mi([_audio_track('fr')]))  # original_language='fr'
        assert _run(gf._build_audio_string(meta)) == 'VOF'

    def test_vff_single(self, gf):
        """Single French track, non-French original → VFF (default precision)."""
        meta = _meta_base(original_language='en', mediainfo=_mi([_audio_track('fr')]))
        assert _run(gf._build_audio_string(meta)) == 'VFF'

    def test_multi_vof(self, gf):
        """Multi tracks (fr+en), originally French → MULTI.VOF."""
        meta = _meta_base(mediainfo=_mi([_audio_track('fr'), _audio_track('en')]))
        assert _run(gf._build_audio_string(meta)) == 'MULTI.VOF'

    def test_vostfr(self, gf):
        meta = _meta_base(mediainfo=_mi([_audio_track('en')], [_sub_track('fr')]))
        assert _run(gf._build_audio_string(meta)) == 'VOSTFR'

    def test_vo_returns_empty(self, gf):
        """No French audio or subs → mixin returns '' (VO)."""
        meta = _meta_base(mediainfo=_mi([_audio_track('en')]))
        assert _run(gf._build_audio_string(meta)) == ''

    def test_muet_vostfr(self, gf):
        """No audio tracks but French subs → MUET.VOSTFR."""
        meta = _meta_base(mediainfo=_mi([], [_sub_track('fr')]))
        assert _run(gf._build_audio_string(meta)) == 'MUET.VOSTFR'

    def test_multi_vff(self, gf):
        meta = _meta_base(original_language='en', mediainfo=_mi([
            _audio_track('fr', Title='VFF'),
            _audio_track('en'),
        ]))
        assert _run(gf._build_audio_string(meta)) == 'MULTI.VFF'

    def test_multi_vfq(self, gf):
        meta = _meta_base(original_language='en', mediainfo=_mi([
            _audio_track('fr', Title='VFQ Doublage Québécois'),
            _audio_track('en'),
        ]))
        assert _run(gf._build_audio_string(meta)) == 'MULTI.VFQ'

    def test_single_vfq(self, gf):
        meta = _meta_base(original_language='en', mediainfo=_mi([_audio_track('fr', Title='VFQ')]))
        assert _run(gf._build_audio_string(meta)) == 'VFQ'

    def test_audio_description_non_french_ad_excluded(self, gf):
        """GF excludes AD when release has FR audio and AD is not French."""
        meta = _meta_base(
            original_language='en',
            has_audiodesc=True,
            mediainfo=_mi([_audio_track('fr')]),
        )
        assert _run(gf._build_audio_string(meta)) == 'VFF'

    def test_audio_description_non_french_ad_multi_excluded(self, gf):
        """GF excludes AD for MULTI when AD is not French."""
        meta = _meta_base(
            original_language='en',
            has_audiodesc=True,
            mediainfo=_mi([_audio_track('fr'), _audio_track('en')]),
        )
        assert _run(gf._build_audio_string(meta)) == 'MULTI.VFF'

    def test_audio_description_french_ad_kept(self, gf):
        """GF keeps AD when the AD track is French."""
        meta = _meta_base(
            original_language='en',
            mediainfo=_mi([
                _audio_track('fr', Title='Main Audio'),
                _audio_track('fr', Title='Audio Description'),
            ]),
        )
        assert _run(gf._build_audio_string(meta)) == 'AD.VFF'

    def test_audio_description_vostfr_kept(self, gf):
        """GF keeps AD on VOSTFR releases (no FR main audio)."""
        meta = _meta_base(
            original_language='en',
            mediainfo=_mi([
                _audio_track('en', Title='Main Audio'),
                _audio_track('fr', Title='Audio Description'),
            ], [_sub_track('fr')]),
        )
        assert _run(gf._build_audio_string(meta)) == 'AD.VOSTFR'

    # ── SUBFRENCH filename fallback ──

    def test_subfrench_in_uuid(self, gf):
        """SUBFRENCH in uuid, no French subs in MediaInfo → VOSTFR."""
        meta = _meta_base(
            original_language='en',
            mediainfo=_mi([_audio_track('en')]),
            uuid='Movie.2025.SUBFRENCH.1080p.BluRay.x264-GROUP',
        )
        assert _run(gf._build_audio_string(meta)) == 'VOSTFR'

    def test_subfrench_in_path(self, gf):
        """SUBFRENCH in path, no French subs in MediaInfo → VOSTFR."""
        meta = _meta_base(
            original_language='en',
            mediainfo=_mi([_audio_track('en')]),
            path='/media/Movie.SUBFRENCH.720p.mkv',
        )
        assert _run(gf._build_audio_string(meta)) == 'VOSTFR'

    def test_subfrench_ignored_when_french_audio(self, gf):
        """SUBFRENCH in filename but French audio present → honour audio-based tag."""
        meta = _meta_base(
            original_language='en',
            mediainfo=_mi([_audio_track('fr'), _audio_track('en')]),
            uuid='Movie.2025.SUBFRENCH.1080p.BluRay.x264-GROUP',
        )
        # French audio present → MULTI.VFF, not VOSTFR
        assert _run(gf._build_audio_string(meta)) == 'MULTI.VFF'

    def test_subfrench_in_name(self, gf):
        """SUBFRENCH in name field, no French subs in MediaInfo → VOSTFR."""
        meta = _meta_base(
            original_language='en',
            mediainfo=_mi([_audio_track('en')]),
            name='Movie.2025.SUBFRENCH.1080p.BluRay.x264-GROUP',
        )
        assert _run(gf._build_audio_string(meta)) == 'VOSTFR'


# ═══════════════════════════════════════════════════════════════
#  Release naming — GF uses the source filename as-is
# ═══════════════════════════════════════════════════════════════


class TestNaming:
    """GF get_name must faithfully reproduce the source filename (dots→spaces)."""

    def test_uuid_is_source(self, gf):
        """Release name comes from uuid, not from metadata fields."""
        meta = _meta_base(uuid='Birthday.Girl.2001.MULTi.1080p.WEB.x264-FW.mkv')
        result = _run(gf.get_name(meta))
        assert result['name'] == 'Birthday Girl 2001 MULTi 1080p WEB x264-FW'

    def test_strip_mkv_extension(self, gf):
        meta = _meta_base(uuid='Movie.2025.FRENCH.720p.WEB.H265-GRP.mkv')
        assert _run(gf.get_name(meta))['name'] == 'Movie 2025 FRENCH 720p WEB H265-GRP'

    def test_strip_mp4_extension(self, gf):
        meta = _meta_base(uuid='Movie.2025.FRENCH.720p.WEB.H265-GRP.mp4')
        assert _run(gf.get_name(meta))['name'] == 'Movie 2025 FRENCH 720p WEB H265-GRP'

    def test_strip_avi_extension(self, gf):
        meta = _meta_base(uuid='Movie.2025.FRENCH.DVDRip.XviD-GRP.avi')
        assert _run(gf.get_name(meta))['name'] == 'Movie 2025 FRENCH DVDRip XviD-GRP'

    def test_no_extension(self, gf):
        """Folder names (season packs) have no extension."""
        meta = _meta_base(uuid='Stranger.Things.S03.FRENCH.2160p.WEBRip.x265-GRP')
        assert _run(gf.get_name(meta))['name'] == 'Stranger Things S03 FRENCH 2160p WEBRip x265-GRP'

    def test_preserves_multi_without_suffix(self, gf):
        """MULTi in the source stays MULTi — nothing added or removed."""
        meta = _meta_base(uuid='Birthday.Girl.2001.MULTi.1080p.WEB.x264-FW')
        name = _run(gf.get_name(meta))['name']
        assert 'MULTi' in name
        assert 'VFF' not in name

    def test_no_audio_codec_added(self, gf):
        """Even if meta has audio info, it must NOT appear in the name."""
        meta = _meta_base(
            uuid='Jimmy.and.Stiggs.2025.VOSTFR.1080p.WEB.H265-TyHD',
            audio='DDP 5.1',
        )
        name = _run(gf.get_name(meta))['name']
        assert 'DDP' not in name
        assert '5.1' not in name
        assert name == 'Jimmy and Stiggs 2025 VOSTFR 1080p WEB H265-TyHD'

    def test_no_double_spaces(self, gf):
        meta = _meta_base(uuid='Movie.2025..FRENCH.1080p.WEB-GRP')
        assert '  ' not in _run(gf.get_name(meta))['name']

    def test_preserves_channel_dots(self, gf):
        """Dots between digits (5.1, 7.1) are preserved."""
        meta = _meta_base(uuid='Movie.2025.FRENCH.1080p.WEB.DDP.5.1.H265-GRP')
        name = _run(gf.get_name(meta))['name']
        assert '5.1' in name

    def test_preserves_title_hyphens(self, gf):
        """Title-internal hyphens (Spider-Man, WALL-E) are preserved."""
        meta = _meta_base(uuid='Spider-Man.2002.MULTi.1080p.BluRay.x264-GRP')
        name = _run(gf.get_name(meta))['name']
        assert 'Spider-Man' in name


# ═══════════════════════════════════════════════════════════════
#  Additional checks (language requirement)
# ═══════════════════════════════════════════════════════════════


class TestAdditionalChecks:
    def test_french_audio_passes(self, gf):
        meta = _meta_base(
            mediainfo=_mi([_audio_track('fr')]),
            tracker_status={'GF': {}},
        )
        with patch.object(gf.common, 'check_language_requirements', new_callable=AsyncMock, return_value=True):
            with patch('src.trackers.GF.SceneNfoGenerator') as mock_nfo:
                mock_nfo.return_value.generate_nfo = AsyncMock(return_value=None)
                assert _run(gf.get_additional_checks(meta)) is True

    def test_no_french_fails(self, gf):
        meta = _meta_base(
            mediainfo=_mi([_audio_track('en')]),
            tracker_status={'GF': {}},
        )
        with patch.object(gf.common, 'check_language_requirements', new_callable=AsyncMock, return_value=False):
            assert _run(gf.get_additional_checks(meta)) is False

    def test_auto_nfo_generated(self, gf):
        meta = _meta_base(
            mediainfo=_mi([_audio_track('fr')]),
            tracker_status={'GF': {}},
        )
        with patch.object(gf.common, 'check_language_requirements', new_callable=AsyncMock, return_value=True):
            with patch('src.trackers.GF.SceneNfoGenerator') as mock_nfo:
                mock_nfo.return_value.generate_nfo = AsyncMock(return_value='/tmp/test.nfo')
                result = _run(gf.get_additional_checks(meta))
                assert result is True
                assert meta['nfo'] == '/tmp/test.nfo'
                assert meta['auto_nfo'] is True


# ═══════════════════════════════════════════════════════════════
#  Integration — full naming examples from GF rules
# ═══════════════════════════════════════════════════════════════


class TestGFExamples:
    """Verify release names match the examples from GF's naming guide (issue #97).

    The name must exactly match the source filename (dots→spaces, extension stripped).
    """

    def test_jimmy_stiggs_vostfr(self, gf):
        """Jimmy and Stiggs 2025 VOSTFR 1080p WEB H265-TyHD"""
        meta = _meta_base(uuid='Jimmy.and.Stiggs.2025.VOSTFR.1080p.WEB.H265-TyHD.mkv')
        assert _run(gf.get_name(meta))['name'] == 'Jimmy and Stiggs 2025 VOSTFR 1080p WEB H265-TyHD'

    def test_bienvenue_chez_les_rozes(self, gf):
        """Bienvenue Chez les Rozes 2003 FRENCH 1080p WEB x264-FW"""
        meta = _meta_base(uuid='Bienvenue.Chez.les.Rozes.2003.FRENCH.1080p.WEB.x264-FW.mkv')
        assert _run(gf.get_name(meta))['name'] == 'Bienvenue Chez les Rozes 2003 FRENCH 1080p WEB x264-FW'

    def test_birthday_girl_multi(self, gf):
        """Birthday Girl 2001 MULTi 1080p WEB x264-FW — no VFF/audio codec added."""
        meta = _meta_base(uuid='Birthday.Girl.2001.MULTi.1080p.WEB.x264-FW.mkv')
        name = _run(gf.get_name(meta))['name']
        assert name == 'Birthday Girl 2001 MULTi 1080p WEB x264-FW'
        assert 'VFF' not in name
        assert 'DDP' not in name

    def test_danger_in_the_house_multi_no_extras(self, gf):
        """Danger in the House 2022 MULTI 1080p WEB H264-FW — no VFF or AAC added."""
        meta = _meta_base(uuid='Danger.in.the.House.2022.MULTI.1080p.WEB.H264-FW.mkv')
        name = _run(gf.get_name(meta))['name']
        assert name == 'Danger in the House 2022 MULTI 1080p WEB H264-FW'

    def test_conners_vostfr(self, gf):
        """The Conners S03E01 VOSTFR 1080p WEB H265-TyHD"""
        meta = _meta_base(uuid='The.Conners.S03E01.VOSTFR.1080p.WEB.H265-TyHD.mkv')
        assert _run(gf.get_name(meta))['name'] == 'The Conners S03E01 VOSTFR 1080p WEB H265-TyHD'


# ═══════════════════════════════════════════════════════════════
#  FrenchTrackerMixin integration (search_existing + dupe check)
# ═══════════════════════════════════════════════════════════════


class TestFrenchMixin:
    """Verify GF inherits FrenchTrackerMixin's search_existing wrapper."""

    def test_has_search_existing(self, gf):
        assert hasattr(gf, 'search_existing')

    def test_has_french_dupe_check(self, gf):
        assert hasattr(gf, '_check_french_lang_dupes')

    def test_has_extract_french_lang_tag(self, gf):
        assert hasattr(gf, '_extract_french_lang_tag')

    def test_mixin_mro(self, gf):
        """FrenchTrackerMixin should come before UNIT3D in MRO."""
        mro = type(gf).__mro__
        mixin_idx = next(i for i, c in enumerate(mro) if c.__name__ == 'FrenchTrackerMixin')
        unit3d_idx = next(i for i, c in enumerate(mro) if c.__name__ == 'UNIT3D')
        assert mixin_idx < unit3d_idx

    def test_get_name_overridden(self, gf):
        """GF overrides get_name to use the source filename as-is."""
        assert 'get_name' in GF.__dict__

    def test_build_audio_inherited(self, gf):
        """GF should NOT define its own _build_audio_string — uses the mixin's."""
        assert '_build_audio_string' not in GF.__dict__

    def test_fr_clean_overridden(self, gf):
        """GF overrides _fr_clean to strip + (unlike the mixin which keeps it)."""
        assert '_fr_clean' in GF.__dict__
        assert '+' not in gf._fr_clean('DD+ test HDR10+')
        assert 'DD' in gf._fr_clean('DD+ test HDR10+')

    def test_format_name_overridden(self, gf):
        """GF overrides _format_name to use spaces instead of dots."""
        assert '_format_name' in GF.__dict__
        result = gf._format_name('The Batman 2022 MULTI.VOF 1080p WEB AC3 x264-GF')
        name = result['name']
        assert 'The Batman' in name
        assert 'MULTI VOF' in name  # dot replaced by space
        assert name.endswith('-GF')

    def test_format_name_preserves_audio_dots(self, gf):
        """Dots in audio channel counts (5.1, 7.1) are preserved."""
        result = gf._format_name('Test 2023 MULTI.VFF 1080p DDP 5.1 x265-GF')
        name = result['name']
        assert '5.1' in name
        assert 'MULTI VFF' in name

    def test_fr_clean_strips_accents(self, gf):
        """GF _fr_clean uses unidecode to strip accents."""
        assert gf._fr_clean('Étoile résumé') == 'Etoile resume'

