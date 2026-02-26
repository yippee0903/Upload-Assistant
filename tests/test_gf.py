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
    return asyncio.get_event_loop().run_until_complete(coro)


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


# ═══════════════════════════════════════════════════════════════
#  Release naming
# ═══════════════════════════════════════════════════════════════


class TestNaming:
    """Test space-separated release names following GF naming conventions."""

    def test_movie_webdl_french(self, gf):
        meta = _meta_base(
            type='WEBDL', title='Le Prenom', year='2012',
            resolution='1080p', video_encode='x264', tag='-GF',
            mediainfo=_mi([_audio_track('fr')]),
        )
        result = _run(gf.get_name(meta))
        name = result['name']
        assert 'Le Prenom' in name
        assert '2012' in name
        assert 'VOF' in name  # original_language='fr' → VOF
        assert '1080p' in name
        assert 'WEB' in name
        assert name.endswith('-GF')

    def test_movie_encode_multi(self, gf):
        meta = _meta_base(
            type='ENCODE', title='The Batman', year='2022',
            resolution='2160p', source='BluRay', video_encode='x265',
            audio='DTS-HD MA 5.1', hdr='HDR', uhd='UHD', tag='-TeamX',
            mediainfo=_mi([_audio_track('fr'), _audio_track('en')]),
        )
        result = _run(gf.get_name(meta))
        name = result['name']
        assert 'The Batman' in name
        assert '2022' in name
        assert 'MULTI' in name
        assert '2160p' in name
        assert '5.1' in name  # dot in audio channels preserved
        assert name.endswith('-TeamX')

    def test_tv_season_webdl(self, gf):
        meta = _meta_base(
            category='TV', type='WEBDL', title='Stranger Things',
            year='2016', search_year='2016', season='S03', episode='',
            resolution='2160p', video_encode='x265', audio='AAC',
            tag='-GF',
            mediainfo=_mi([_audio_track('fr')]),
        )
        result = _run(gf.get_name(meta))
        name = result['name']
        assert 'Stranger Things' in name
        assert '2016' in name
        assert 'S03' in name
        assert 'VOF' in name  # original_language='fr' → VOF
        assert name.endswith('-GF')

    def test_tv_episode(self, gf):
        meta = _meta_base(
            category='TV', type='WEBDL', title='The Last of Us',
            year='', search_year='', season='S01', episode='E01',
            resolution='1080p', video_encode='x265', audio='AC3',
            tag='-NoTag',
            mediainfo=_mi([_audio_track('fr'), _audio_track('en')]),
        )
        result = _run(gf.get_name(meta))
        name = result['name']
        # GF title-case: "Us" is last word → capitalised
        assert 'The Last of Us' in name
        assert 'S01E01' in name
        assert 'MULTI' in name
        assert name.endswith('-NoTag')

    def test_no_special_chars(self, gf):
        meta = _meta_base(
            type='WEBDL', title="L'Étoile du Nord",
            year='2020', resolution='1080p', video_encode='x264',
            tag='-GF',
            mediainfo=_mi([_audio_track('fr')]),
        )
        result = _run(gf.get_name(meta))
        name = result['name']
        # No accents or apostrophes should remain
        assert "'" not in name
        assert 'É' not in name
        # Spaces are used as separators (GF convention)
        assert ' ' in name

    def test_no_double_spaces(self, gf):
        meta = _meta_base(
            type='WEBDL', title='Test', year='2020',
            resolution='1080p', video_encode='x264', tag='-GF',
            edition='', repack='', service='',
            mediainfo=_mi([_audio_track('fr')]),
        )
        result = _run(gf.get_name(meta))
        assert '  ' not in result['name']

    def test_remux_naming(self, gf):
        meta = _meta_base(
            type='REMUX', title='Dune', year='2021',
            resolution='2160p', source='BluRay', uhd='UHD',
            video_codec='HEVC', audio='DTS-HD MA 7.1',
            hdr='HDR', tag='-HDTeam',
            mediainfo=_mi([_audio_track('fr'), _audio_track('en')]),
        )
        result = _run(gf.get_name(meta))
        name = result['name']
        assert 'Dune' in name
        assert 'REMUX' in name
        assert 'MULTI' in name
        # GF: Hybrid is suppressed for REMUX
        assert 'Hybrid' not in name

    def test_remux_no_hybrid(self, gf):
        """GF moderation rule: REMUX cannot be Hybrid."""
        meta = _meta_base(
            type='REMUX', title='Dune', year='2021',
            resolution='2160p', source='BluRay', uhd='UHD',
            video_codec='HEVC', audio='DTS-HD MA 7.1',
            hdr='HDR', webdv='Hybrid', tag='-GF',
            mediainfo=_mi([_audio_track('fr'), _audio_track('en')]),
        )
        result = _run(gf.get_name(meta))
        name = result['name']
        assert 'REMUX' in name
        assert 'Hybrid' not in name

    def test_movie_dvdrip(self, gf):
        meta = _meta_base(
            type='DVDRIP', title='La Chtite Famille', year='2018',
            resolution='480p', source='DVD', video_encode='x264',
            audio='AC3', tag='-GF',
            mediainfo=_mi([_audio_track('fr')]),
        )
        result = _run(gf.get_name(meta))
        name = result['name']
        assert 'DVDRip' in name

    def test_hybrid_flag(self, gf):
        meta = _meta_base(
            type='WEBDL', title='Avatar', year='2022',
            resolution='2160p', video_encode='x265',
            webdv='Hybrid', tag='-GF',
            mediainfo=_mi([_audio_track('fr')]),
        )
        result = _run(gf.get_name(meta))
        name = result['name']
        assert 'Hybrid' in name

    def test_ddplus_becomes_ddp(self, gf):
        """DD+ contains a special char (+), GF requires DDP instead."""
        meta = _meta_base(
            type='WEBDL', title='Test', year='2023',
            resolution='1080p', video_encode='x265',
            audio='DD+ 5.1', tag='-GF',
            mediainfo=_mi([_audio_track('fr')]),
        )
        result = _run(gf.get_name(meta))
        name = result['name']
        assert 'DD+' not in name
        assert 'DDP' in name

    def test_hdr10plus_becomes_hdr10plus(self, gf):
        """HDR10+ contains a special char (+), GF requires HDR10PLUS."""
        meta = _meta_base(
            type='ENCODE', title='Test', year='2023',
            resolution='2160p', video_encode='x265', source='BluRay',
            audio='DTS', hdr='HDR10+', tag='-GF',
            mediainfo=_mi([_audio_track('fr')]),
        )
        result = _run(gf.get_name(meta))
        name = result['name']
        assert 'HDR10+' not in name
        assert 'HDR10PLUS' in name
        assert '+' not in name


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
    """Verify release names match the examples from GF's naming guide."""

    def test_example_batman_4k(self, gf):
        """The Batman 2022 LiMiTED MULTI.VOF 2160p UHD BluRay HDR AC3 x265-GF"""
        meta = _meta_base(
            type='ENCODE', title='The Batman', year='2022',
            resolution='2160p', source='BluRay', video_encode='x265',
            audio='AC3', hdr='HDR', uhd='UHD', edition='LiMiTED',
            tag='-GF',
            mediainfo=_mi([_audio_track('fr'), _audio_track('en')]),
        )
        result = _run(gf.get_name(meta))
        name = result['name']
        assert name.startswith('The Batman 2022')
        assert 'MULTI' in name
        assert '2160p' in name
        assert name.endswith('-GF')

    def test_example_everything_everywhere(self, gf):
        """Everything Everywhere All at Once 2022 VOF 1080p WEB AAC x264-NoTag"""
        meta = _meta_base(
            type='WEBDL', title='Everything Everywhere All at Once', year='2022',
            resolution='1080p', video_encode='x264', audio='AAC',
            tag='-NoTag',
            mediainfo=_mi([_audio_track('fr')]),
        )
        result = _run(gf.get_name(meta))
        name = result['name']
        assert 'Everything Everywhere' in name
        assert 'VOF' in name  # original_language='fr' → VOF
        assert '1080p' in name
        assert 'WEB' in name
        assert name.endswith('-NoTag')

    def test_example_last_of_us_s01e01(self, gf):
        """The Last of us S01E01 MULTI.VOF HDR 1080p WEB AC3 x265-NoTag"""
        meta = _meta_base(
            category='TV', type='WEBDL',
            title='The Last of Us', year='', search_year='',
            season='S01', episode='E01',
            resolution='1080p', video_encode='x265', audio='AC3',
            hdr='HDR', tag='-NoTag',
            mediainfo=_mi([_audio_track('fr'), _audio_track('en')]),
        )
        result = _run(gf.get_name(meta))
        name = result['name']
        # GF title-case: "Us" is last word → capitalised
        assert 'The Last of Us' in name
        assert 'S01E01' in name
        assert 'MULTI' in name
        assert name.endswith('-NoTag')

    def test_example_stranger_things_s03(self, gf):
        """Stranger Things 2016 S03 VOF 2160p WEBRip AAC x265-GF"""
        meta = _meta_base(
            category='TV', type='WEBRIP',
            title='Stranger Things', year='2016', search_year='2016',
            season='S03', episode='',
            resolution='2160p', video_encode='x265', audio='AAC',
            tag='-GF',
            mediainfo=_mi([_audio_track('fr')]),
        )
        result = _run(gf.get_name(meta))
        name = result['name']
        assert 'Stranger Things' in name
        assert '2016' in name
        assert 'S03' in name
        assert 'VOF' in name  # original_language='fr' → VOF
        assert name.endswith('-GF')


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
        """GF overrides get_name for REMUX no-Hybrid, HDR-after-resolution, and French audio codec."""
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
