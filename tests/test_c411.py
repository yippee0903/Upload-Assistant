# Tests for C411 tracker — c411.org
"""
Test suite for the C411 tracker implementation.
Covers: language detection, naming, category/quality mapping,
        options building, description, Torznab parsing, announce URL.
"""

import asyncio
import json
import re
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.trackers.C411 import C411

# ─── Helpers ──────────────────────────────────────────────────


def _config(extra_tracker: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a minimal config dict for C411."""
    tracker_cfg: dict[str, Any] = {
        'api_key': 'test-api-key-123',
        'announce_url': 'https://c411.org/announce/FAKE_PASSKEY',
    }
    if extra_tracker:
        tracker_cfg.update(extra_tracker)
    return {
        'TRACKERS': {'C411': tracker_cfg},
        'DEFAULT': {'tmdb_api': 'fake-tmdb-key-for-tests'},
    }


def _meta_base(**overrides: Any) -> dict[str, Any]:
    """Build a base meta dict with sensible defaults."""
    m: dict[str, Any] = {
        'category': 'MOVIE',
        'type': 'WEBDL',
        'title': 'Le Prénom',
        'year': '2012',
        'resolution': '1080p',
        'source': 'WEB',
        'audio': 'AC3',
        'video_encode': 'x264',
        'service': '',
        'tag': '-Troxy',
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
        'overview': 'Un dîner entre amis tourne mal.',
        'poster': 'https://image.tmdb.org/poster.jpg',
        'tmdb': 1234,
        'imdb_id': 1234567,
        'original_language': 'fr',
        'image_list': [],
        'bdinfo': None,
        'mediainfo': {
            'media': {
                'track': []
            }
        },
        'tracker_status': {'C411': {}},
    }
    m.update(overrides)
    return m


def _audio_track(lang: str = 'fr', **kw: Any) -> dict[str, Any]:
    """Build a minimal audio track."""
    t: dict[str, Any] = {'@type': 'Audio', 'Language': lang}
    t.update(kw)
    return t


def _sub_track(lang: str = 'fr') -> dict[str, Any]:
    """Build a minimal subtitle track."""
    return {'@type': 'Text', 'Language': lang}


def _mi(audio: list[dict[str, Any]], subs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Build mediainfo with given audio/sub tracks."""
    tracks = list(audio)
    if subs:
        tracks.extend(subs)
    return {'media': {'track': tracks}}


# ─── Constructor ─────────────────────────────────────────────

class TestC411Init:
    def test_basic_init(self):
        c = C411(_config())
        assert c.tracker == 'C411'
        assert c.source_flag == 'C411'
        assert c.api_key == 'test-api-key-123'
        assert c.upload_url == 'https://c411.org/api/torrents'

    def test_missing_api_key(self):
        c = C411({'TRACKERS': {}, 'DEFAULT': {'tmdb_api': 'fake'}})
        assert c.api_key == ''


# ─── Language detection ──────────────────────────────────────

class TestLanguageDetection:
    """Test _build_audio_string and its helpers."""

    def _run(self, meta: dict[str, Any]) -> str:
        c = C411(_config())
        return asyncio.run(c._build_audio_string(meta))

    def test_no_mediainfo(self):
        meta = _meta_base()
        del meta['mediainfo']
        assert self._run(meta) == ''

    def test_muet_no_audio_tracks(self):
        meta = _meta_base(mediainfo=_mi([]))
        assert self._run(meta) == 'MUET'

    def test_single_french_vof(self):
        """Single French audio + original_language=fr → VOF."""
        meta = _meta_base(
            mediainfo=_mi([_audio_track('fr')]),
            original_language='fr',
        )
        assert self._run(meta) == 'VOF'

    def test_single_french_vff(self):
        """Single fr-fr audio + original_language=en → VFF (not VOF)."""
        meta = _meta_base(
            mediainfo=_mi([_audio_track('fr-fr')]),
            original_language='en',
        )
        assert self._run(meta) == 'VFF'

    def test_single_french_vfq(self):
        """Single fr-ca audio → VFQ."""
        meta = _meta_base(
            mediainfo=_mi([_audio_track('fr-ca')]),
            original_language='en',
        )
        assert self._run(meta) == 'VFQ'

    def test_single_french_generic(self):
        """Single generic 'fr' + non-French origin → VFF."""
        meta = _meta_base(
            mediainfo=_mi([_audio_track('fr')]),
            original_language='en',
        )
        assert self._run(meta) == 'VFF'

    def test_truefrench_from_path(self):
        """TRUEFRENCH detected in path → outputs VFF (modern equivalent)."""
        meta = _meta_base(
            mediainfo=_mi([_audio_track('fr')]),
            original_language='en',
            path='/media/Movie.TRUEFRENCH.1080p.mkv',
        )
        assert self._run(meta) == 'VFF'

    def test_multi_fr_en(self):
        """French + English → MULTI.VFF (bare MULTI is never used)."""
        meta = _meta_base(
            mediainfo=_mi([_audio_track('fr'), _audio_track('en')]),
            original_language='en',
        )
        assert self._run(meta) == 'MULTI.VFF'

    def test_multi_vff(self):
        """fr-fr + English → MULTI.VFF."""
        meta = _meta_base(
            mediainfo=_mi([_audio_track('fr-fr'), _audio_track('en')]),
            original_language='en',
        )
        assert self._run(meta) == 'MULTI.VFF'

    def test_multi_vfq(self):
        """fr-ca + English → MULTI.VFQ."""
        meta = _meta_base(
            mediainfo=_mi([_audio_track('fr-ca'), _audio_track('en')]),
            original_language='en',
        )
        assert self._run(meta) == 'MULTI.VFQ'

    def test_multi_vf2(self):
        """fr-fr + fr-ca + English → MULTI.VF2."""
        meta = _meta_base(
            mediainfo=_mi([_audio_track('fr-fr'), _audio_track('fr-ca'), _audio_track('en')]),
            original_language='en',
        )
        assert self._run(meta) == 'MULTI.VF2'

    def test_multi_vof(self):
        """French + English + original_language=fr → MULTI.VOF."""
        meta = _meta_base(
            mediainfo=_mi([_audio_track('fr'), _audio_track('en')]),
            original_language='fr',
        )
        assert self._run(meta) == 'MULTI.VOF'

    def test_multi_truefrench(self):
        """French + English + TRUEFRENCH in path → MULTI.VFF."""
        meta = _meta_base(
            mediainfo=_mi([_audio_track('fr'), _audio_track('en')]),
            original_language='en',
            path='/media/Film.TRUEFRENCH.mkv',
        )
        assert self._run(meta) == 'MULTI.VFF'

    def test_vostfr(self):
        """No French audio but French subs → VOSTFR."""
        meta = _meta_base(
            mediainfo=_mi([_audio_track('en')], [_sub_track('fr')]),
            original_language='en',
        )
        assert self._run(meta) == 'VOSTFR'

    def test_vo_english_only(self):
        """English only, no French content → empty string (VO)."""
        meta = _meta_base(
            mediainfo=_mi([_audio_track('en')]),
            original_language='en',
        )
        assert self._run(meta) == ''

    def test_generic_fr_vfq_in_filename(self):
        """Generic 'fr' audio + VFQ in filename → VFQ (not default VFF)."""
        meta = _meta_base(
            mediainfo=_mi([_audio_track('fr')]),
            original_language='en',
            uuid='Now.You.See.Me.2025.VFQ.1080p.BluRay.REMUX.AVC-GROUP',
        )
        assert self._run(meta) == 'VFQ'

    def test_generic_fr_vfq_in_path(self):
        """Generic 'fr' audio + VFQ in path → VFQ."""
        meta = _meta_base(
            mediainfo=_mi([_audio_track('fr')]),
            original_language='en',
            path='/media/downloads/Movie.VFQ.1080p.mkv',
        )
        assert self._run(meta) == 'VFQ'

    def test_multi_generic_fr_vfq_in_filename(self):
        """Generic 'fr' + English audio + VFQ in filename → MULTI.VFQ."""
        meta = _meta_base(
            mediainfo=_mi([_audio_track('fr'), _audio_track('en')]),
            original_language='en',
            uuid='Movie.2025.VFQ.1080p.BluRay.REMUX.AVC-GROUP',
        )
        assert self._run(meta) == 'MULTI.VFQ'

    def test_generic_fr_vff_in_filename(self):
        """Generic 'fr' audio + VFF in filename → VFF (explicit, not just default)."""
        meta = _meta_base(
            mediainfo=_mi([_audio_track('fr')]),
            original_language='en',
            uuid='Movie.2025.VFF.1080p.BluRay.REMUX.AVC-GROUP',
        )
        assert self._run(meta) == 'VFF'

    def test_mediainfo_region_overrides_filename(self):
        """fr-fr in MediaInfo should prevail over VFQ in filename."""
        meta = _meta_base(
            mediainfo=_mi([_audio_track('fr-fr')]),
            original_language='en',
            uuid='Movie.2025.VFQ.1080p.BluRay.REMUX.AVC-GROUP',
        )
        # MediaInfo region code takes priority over filename
        assert self._run(meta) == 'VFF'

    def test_generic_fr_no_hint_defaults_vff(self):
        """Generic 'fr' audio with no VFQ/VFF hint anywhere → default VFF."""
        meta = _meta_base(
            mediainfo=_mi([_audio_track('fr')]),
            original_language='en',
            uuid='Movie.2025.1080p.BluRay.REMUX.AVC-GROUP',
        )
        assert self._run(meta) == 'VFF'


# ─── Release naming ──────────────────────────────────────────

class TestGetName:
    def _run(self, meta: dict[str, Any]) -> str:
        c = C411(_config())
        # Mock _get_french_title to return meta['title'] (avoids TMDB API call)
        c._get_french_title = AsyncMock(return_value=meta.get('title', ''))
        result = asyncio.run(c.get_name(meta))
        return result.get('name', '')

    def test_movie_webdl_french(self):
        """Standard French movie WEB-DL."""
        meta = _meta_base(
            mediainfo=_mi([_audio_track('fr')]),
            original_language='fr',
        )
        name = self._run(meta)
        # Should be dot-separated
        assert '.' in name
        assert ' ' not in name
        # Must contain key parts
        assert 'Le' in name
        assert '2012' in name
        assert 'VOF' in name
        assert '1080p' in name
        assert 'WEB' in name
        assert '-Troxy' in name

    def test_movie_webdl_multi(self):
        """Multi-language movie WEB-DL."""
        meta = _meta_base(
            mediainfo=_mi([_audio_track('fr-fr'), _audio_track('en')]),
            original_language='en',
            title='Avatar',
            year='2022',
            tag='-FCK',
        )
        name = self._run(meta)
        assert 'MULTI.VFF' in name
        assert 'WEB' in name
        assert '-FCK' in name

    def test_movie_remux_4k(self):
        """4K BluRay Remux."""
        meta = _meta_base(
            type='REMUX',
            resolution='2160p',
            source='BluRay',
            uhd='UHD',
            hdr='HDR',
            video_codec='HEVC',
            audio='TrueHD Atmos 7.1',
            tag='-FGT',
            mediainfo=_mi([_audio_track('en')]),
            original_language='en',
        )
        name = self._run(meta)
        assert '2160p' in name
        assert 'BluRay' in name
        assert 'REMUX' in name
        assert '-FGT' in name

    def test_tv_episode(self):
        """TV episode naming."""
        meta = _meta_base(
            category='TV',
            title='Lupin',
            year='2021',
            season='S01',
            episode='E03',
            search_year='2021',
            tag='-NTb',
            mediainfo=_mi([_audio_track('fr')]),
            original_language='fr',
        )
        name = self._run(meta)
        assert 'S01E03' in name
        assert 'Lupin' in name

    def test_tv_season_pack(self):
        """TV season pack naming — no episode number."""
        meta = _meta_base(
            category='TV',
            title='Lupin',
            year='2021',
            season='S01',
            episode='',
            search_year='2021',
            tv_pack=1,
            tag='-NTb',
            mediainfo=_mi([_audio_track('fr'), _audio_track('en')]),
            original_language='fr',
        )
        name = self._run(meta)
        assert 'S01' in name
        assert 'E0' not in name  # no episode
        assert 'MULTI.VOF' in name

    def test_dots_no_spaces(self):
        """Name must use dots, never spaces."""
        meta = _meta_base(
            mediainfo=_mi([_audio_track('en')]),
            original_language='en',
        )
        name = self._run(meta)
        assert ' ' not in name
        assert '.' in name

    def test_encode(self):
        """Encode naming."""
        meta = _meta_base(
            type='ENCODE',
            source='BluRay',
            video_encode='x265',
            mediainfo=_mi([_audio_track('en')]),
            original_language='en',
        )
        name = self._run(meta)
        assert 'BluRay' in name
        assert 'x265' in name

    def test_hdtv(self):
        """HDTV naming."""
        meta = _meta_base(
            type='HDTV',
            source='HDTV',
            resolution='720p',
            video_encode='x264',
            mediainfo=_mi([_audio_track('en')]),
            original_language='en',
        )
        name = self._run(meta)
        assert '720p' in name
        assert 'HDTV' in name

    def test_dd_converted_to_ac3(self):
        """DD audio must be converted to AC3 for C411."""
        meta = _meta_base(
            type='WEBDL',
            audio='DD 5.1',
            mediainfo=_mi([_audio_track('fr')]),
            original_language='fr',
        )
        name = self._run(meta)
        assert '.AC3.' in name
        assert '.DD.' not in name

    def test_ddp_not_converted(self):
        """DDP should remain as-is (not converted to AC3P)."""
        meta = _meta_base(
            type='WEBDL',
            audio='DDP 5.1',
            mediainfo=_mi([_audio_track('fr')]),
            original_language='fr',
        )
        name = self._run(meta)
        assert '.DDP.' in name
        assert '.AC3.' not in name

    def test_truehd_uppercased(self):
        """TrueHD must be TRUEHD for C411."""
        meta = _meta_base(
            type='REMUX',
            source='BluRay',
            audio='TrueHD 7.1',
            mediainfo=_mi([_audio_track('en')]),
            original_language='en',
        )
        name = self._run(meta)
        assert '.TRUEHD.' in name
        assert '.TrueHD.' not in name

    def test_truehd_atmos(self):
        """TrueHD Atmos must have ATMOS before TRUEHD for C411."""
        meta = _meta_base(
            type='REMUX',
            source='BluRay',
            audio='TrueHD Atmos 7.1',
            mediainfo=_mi([_audio_track('en')]),
            original_language='en',
        )
        name = self._run(meta)
        assert '.ATMOS.TRUEHD.' in name or 'ATMOS.TRUEHD.7.1' in name

    def test_dts_hd_ma_dots(self):
        """DTS-HD MA must become DTS.HD.MA for C411."""
        meta = _meta_base(
            type='REMUX',
            source='BluRay',
            audio='DTS-HD MA 7.1',
            mediainfo=_mi([_audio_track('en')]),
            original_language='en',
        )
        name = self._run(meta)
        assert '.DTS.HD.MA.' in name
        assert '.DTS-HD.' not in name

    def test_dtsx(self):
        """DTS:X must become DTS.X for C411."""
        meta = _meta_base(
            type='REMUX',
            source='BluRay',
            audio='DTS:X 7.1',
            mediainfo=_mi([_audio_track('en')]),
            original_language='en',
        )
        name = self._run(meta)
        assert '.DTS.X.' in name
        assert '.DTS:X.' not in name
        assert '.DTSX.' not in name

    def test_title_middle_dot_preserved_as_separator(self):
        """WALL·E (middle dot U+00B7) must become WALL.E (not WALLE)."""
        meta = _meta_base(
            title='WALL\u00b7E',
            year='2008',
            resolution='2160p',
            uhd='UHD',
            source='BluRay',
            type='ENCODE',
            hdr='HDR',
            video_encode='x265',
            audio='TrueHD Atmos 7.1',
            tag='-W4NK3R',
            mediainfo=_mi([_audio_track('en')]),
            original_language='en',
        )
        name = self._run(meta)
        # Middle dot → space → dot (standard dot-separated format)
        assert 'Wall.E' in name or 'WALL.E' in name, f"Expected Wall.E separator: {name}"
        # Regression guard: title must NOT start with concatenated "Walle."
        assert not name.lower().startswith('walle.'), f"Middle dot lost – got concatenated: {name}"

    def test_repack_before_language(self):
        """C411 rule: REPACK/PROPER must appear before the language tag."""
        meta = _meta_base(
            title='Le Silence Des Agneaux',
            year='1991',
            resolution='2160p',
            uhd='UHD',
            source='BluRay',
            type='ENCODE',
            repack='REPACK',
            hdr='DV HDR',
            video_encode='x265',
            audio='DTS-HD MA 5.1',
            tag='-W4NK3R',
            mediainfo=_mi([_audio_track('fr')]),
            original_language='en',
        )
        name = self._run(meta)
        # REPACK must come before language (VOSTFR/VFF/etc.)
        repack_pos = name.find('.REPACK.')
        assert repack_pos != -1, f"REPACK not found in name: {name}"
        # Find the language token (first occurrence of a known French tag after year)
        import re
        lang_match = re.search(r'\.(VOSTFR|VFF|VFQ|VF2|VFI|TRUEFRENCH|FRENCH|MULTI)\.', name)
        assert lang_match is not None, f"No language tag found in name: {name}"
        assert repack_pos < lang_match.start(), (
            f"REPACK ({repack_pos}) must come before language ({lang_match.start()}): {name}"
        )

    def test_uhd_stripped_for_encode(self):
        """C411 rule: UHD must NOT appear for ENCODE releases (only REMUX/DISC)."""
        meta = _meta_base(
            title='Retour Vers Le Futur',
            year='1985',
            resolution='2160p',
            uhd='UHD',
            source='BluRay',
            type='ENCODE',
            hdr='HDR',
            video_encode='x265',
            audio='TrueHD Atmos 7.1',
            tag='-W4NK3R',
            mediainfo=_mi([_audio_track('fr')]),
            original_language='en',
        )
        name = self._run(meta)
        assert '.UHD.' not in name, f"UHD must not appear in ENCODE: {name}"
        assert '.2160p.' in name, f"Resolution must still be present: {name}"

    def test_uhd_kept_for_remux(self):
        """C411 rule: UHD must be present for REMUX releases."""
        meta = _meta_base(
            title='Retour Vers Le Futur',
            year='1985',
            resolution='2160p',
            uhd='UHD',
            source='BluRay',
            type='REMUX',
            hdr='HDR',
            video_codec='H265',
            audio='TrueHD Atmos 7.1',
            tag='-W4NK3R',
            mediainfo=_mi([_audio_track('fr')]),
            original_language='en',
        )
        name = self._run(meta)
        assert '.UHD.' in name, f"UHD must be present in REMUX: {name}"

    def test_uhd_stripped_for_webdl(self):
        """C411 rule: UHD must NOT appear for WEB-DL releases."""
        meta = _meta_base(
            title='Retour Vers Le Futur',
            year='1985',
            resolution='2160p',
            uhd='UHD',
            type='WEBDL',
            hdr='DV HDR',
            video_encode='H265',
            audio='DDP Atmos 5.1',
            tag='-W4NK3R',
            mediainfo=_mi([_audio_track('fr')]),
            original_language='en',
        )
        name = self._run(meta)
        assert '.UHD.' not in name, f"UHD must not appear in WEBDL: {name}"
        assert '.2160p.' in name, f"Resolution must still be present: {name}"

    def test_uhd_kept_for_disc_bdmv(self):
        """C411 rule: UHD must be present for DISC/BDMV releases."""
        meta = _meta_base(
            title='Retour Vers Le Futur',
            year='1985',
            resolution='2160p',
            uhd='UHD',
            source='BluRay',
            type='DISC',
            is_disc='BDMV',
            hdr='HDR',
            video_codec='H265',
            audio='TrueHD Atmos 7.1',
            tag='-W4NK3R',
            mediainfo=_mi([_audio_track('fr')]),
            original_language='en',
        )
        name = self._run(meta)
        assert '.UHD.' in name, f"UHD must be present in DISC/BDMV: {name}"

    def test_uhd_stripped_for_webrip(self):
        """C411 rule: UHD must NOT appear for WEBRIP releases."""
        meta = _meta_base(
            title='Retour Vers Le Futur',
            year='1985',
            resolution='2160p',
            uhd='UHD',
            type='WEBRIP',
            hdr='HDR',
            video_encode='H265',
            audio='DDP 5.1',
            tag='-W4NK3R',
            mediainfo=_mi([_audio_track('fr')]),
            original_language='en',
        )
        name = self._run(meta)
        assert '.UHD.' not in name, f"UHD must not appear in WEBRIP: {name}"
        assert '.2160p.' in name, f"Resolution must still be present: {name}"


# ─── Commentary track filtering ──────────────────────────────

class TestCommentaryFiltering:
    """Test that commentary tracks are excluded from language detection."""

    def _run(self, meta: dict[str, Any]) -> str:
        c = C411(_config())
        return asyncio.run(c._build_audio_string(meta))

    def test_commentary_excluded(self):
        """Commentary tracks should not count as audio tracks for language."""
        meta = _meta_base(
            mediainfo=_mi([
                _audio_track('en'),
                {**_audio_track('fr'), 'Title': 'Commentary by Director'},
            ]),
            original_language='en',
        )
        # Only English audio (commentary French excluded) → no French audio
        assert self._run(meta) == ''

    def test_commentary_not_excluded_when_real_french_present(self):
        """Non-commentary French + commentary should still detect MULTI."""
        meta = _meta_base(
            mediainfo=_mi([
                _audio_track('en'),
                _audio_track('fr-fr'),
                {**_audio_track('fr-fr'), 'Title': 'Director commentary'},
            ]),
            original_language='en',
        )
        result = self._run(meta)
        assert result.startswith('MULTI')


# ─── Codec cleanup in naming ─────────────────────────────────

class TestCodecCleanup:
    """Test H.264→H264, H.265→H265, HDR10+→HDR10PLUS in get_name."""

    def _run(self, meta: dict[str, Any]) -> str:
        c = C411(_config())
        c._get_french_title = AsyncMock(return_value=meta.get('title', ''))
        c._build_audio_string = AsyncMock(return_value='')
        result = asyncio.run(c.get_name(meta))
        return result.get('name', '')

    def test_h264_cleaned(self):
        meta = _meta_base(
            title='Test', year='2024', type='ENCODE', source='BluRay',
            resolution='1080p', video_encode='H.264',
            mediainfo=_mi([_audio_track('en')]), original_language='en',
        )
        name = self._run(meta)
        assert 'H264' in name
        assert 'H.264' not in name

    def test_h265_cleaned(self):
        meta = _meta_base(
            title='Test', year='2024', type='ENCODE', source='BluRay',
            resolution='2160p', video_encode='H.265',
            mediainfo=_mi([_audio_track('en')]), original_language='en',
        )
        name = self._run(meta)
        assert 'H265' in name
        assert 'H.265' not in name

    def test_hdr10plus_cleaned(self):
        meta = _meta_base(
            title='Test', year='2024', type='WEBDL', source='WEB',
            resolution='2160p', video_encode='H265',
            mediainfo=_mi([_audio_track('en')]), original_language='en',
            hdr='HDR10+',
        )
        name = self._run(meta)
        assert 'HDR10PLUS' in name
        assert 'HDR10+' not in name


# ─── Category / Subcategory mapping ──────────────────────────

class TestCategoryMapping:
    def test_movie(self):
        c = C411(_config())
        cat, sub = c._get_category_subcategory({'category': 'MOVIE'})
        assert cat == 1
        assert sub == 6  # Films

    def test_tv(self):
        c = C411(_config())
        cat, sub = c._get_category_subcategory({'category': 'TV'})
        assert cat == 1
        assert sub == 7  # Séries TV

    def test_anime_movie(self):
        c = C411(_config())
        cat, sub = c._get_category_subcategory({'category': 'MOVIE', 'mal_id': 1234})
        assert cat == 1
        assert sub == 1  # Anime Film

    def test_anime_tv(self):
        c = C411(_config())
        cat, sub = c._get_category_subcategory({'category': 'TV', 'mal_id': 5678})
        assert cat == 1
        assert sub == 2  # Anime TV


# ─── Quality option mapping ──────────────────────────────────

class TestQualityMapping:
    def test_webdl_1080(self):
        c = C411(_config())
        assert c._get_quality_option_id({'type': 'WEBDL', 'resolution': '1080p'}) == 25

    def test_webdl_4k(self):
        c = C411(_config())
        assert c._get_quality_option_id({'type': 'WEBDL', 'resolution': '2160p'}) == 26

    def test_webdl_720(self):
        c = C411(_config())
        assert c._get_quality_option_id({'type': 'WEBDL', 'resolution': '720p'}) == 27

    def test_webdl_other(self):
        c = C411(_config())
        assert c._get_quality_option_id({'type': 'WEBDL', 'resolution': '480p'}) == 24

    def test_remux_4k(self):
        c = C411(_config())
        assert c._get_quality_option_id({'type': 'REMUX', 'resolution': '2160p', 'source': 'BluRay'}) == 10

    def test_remux_1080(self):
        c = C411(_config())
        assert c._get_quality_option_id({'type': 'REMUX', 'resolution': '1080p', 'source': 'BluRay'}) == 12

    def test_remux_dvd(self):
        c = C411(_config())
        assert c._get_quality_option_id({'type': 'REMUX', 'resolution': '', 'source': 'PAL DVD'}) == 15

    def test_bluray_disc_4k(self):
        c = C411(_config())
        assert c._get_quality_option_id({'type': 'DISC', 'resolution': '2160p', 'is_disc': 'BDMV'}) == 10

    def test_bluray_disc_1080(self):
        c = C411(_config())
        assert c._get_quality_option_id({'type': 'DISC', 'resolution': '1080p', 'is_disc': 'BDMV'}) == 11

    def test_dvd_disc(self):
        c = C411(_config())
        assert c._get_quality_option_id({'type': 'DISC', 'resolution': '', 'is_disc': 'DVD'}) == 14

    def test_encode_1080(self):
        c = C411(_config())
        assert c._get_quality_option_id({'type': 'ENCODE', 'resolution': '1080p'}) == 16

    def test_encode_4k(self):
        c = C411(_config())
        assert c._get_quality_option_id({'type': 'ENCODE', 'resolution': '2160p'}) == 17

    def test_encode_720(self):
        c = C411(_config())
        assert c._get_quality_option_id({'type': 'ENCODE', 'resolution': '720p'}) == 18

    def test_webrip_4k(self):
        c = C411(_config())
        assert c._get_quality_option_id({'type': 'WEBRIP', 'resolution': '2160p'}) == 30

    def test_webrip_1080(self):
        c = C411(_config())
        assert c._get_quality_option_id({'type': 'WEBRIP', 'resolution': '1080p'}) == 29

    def test_webrip_720(self):
        c = C411(_config())
        assert c._get_quality_option_id({'type': 'WEBRIP', 'resolution': '720p'}) == 31

    def test_hdtv_1080(self):
        c = C411(_config())
        assert c._get_quality_option_id({'type': 'HDTV', 'resolution': '1080p'}) == 20

    def test_hdtv_720(self):
        c = C411(_config())
        assert c._get_quality_option_id({'type': 'HDTV', 'resolution': '720p'}) == 22

    def test_hdtv_sd(self):
        c = C411(_config())
        assert c._get_quality_option_id({'type': 'HDTV', 'resolution': '480p'}) == 19

    def test_dvdrip(self):
        c = C411(_config())
        assert c._get_quality_option_id({'type': 'DVDRIP', 'resolution': ''}) == 15

    def test_4klight(self):
        c = C411(_config())
        assert c._get_quality_option_id({'type': 'ENCODE', 'resolution': '2160p', 'uuid': 'Some.4KLight.Release'}) == 415

    def test_hdlight_1080(self):
        c = C411(_config())
        assert c._get_quality_option_id({'type': 'ENCODE', 'resolution': '1080p', 'uuid': 'Some.HDLight.Release'}) == 413

    def test_hdlight_720(self):
        c = C411(_config())
        assert c._get_quality_option_id({'type': 'ENCODE', 'resolution': '720p', 'uuid': 'Some.HDLight.Release'}) == 414


# ─── Language option mapping ─────────────────────────────────

class TestLanguageOptionMapping:
    def test_multi_vf2(self):
        c = C411(_config())
        assert c._get_language_option_id('MULTI.VF2') == 422

    def test_multi(self):
        c = C411(_config())
        assert c._get_language_option_id('MULTI') == 4

    def test_vff(self):
        c = C411(_config())
        assert c._get_language_option_id('VFF') == 2

    def test_vfq(self):
        c = C411(_config())
        assert c._get_language_option_id('VFQ') == 6

    def test_vostfr(self):
        c = C411(_config())
        assert c._get_language_option_id('VOSTFR') == 8

    def test_unknown_defaults_anglais(self):
        c = C411(_config())
        assert c._get_language_option_id('') == 1
        assert c._get_language_option_id('UNKNOWN') == 1


# ─── Season / Episode option mapping ─────────────────────────

class TestSeasonEpisodeOptions:
    def test_movie_returns_empty(self):
        c = C411(_config())
        assert c._get_season_episode_options({'category': 'MOVIE'}) == {}

    def test_tv_s01e03(self):
        c = C411(_config())
        opts = c._get_season_episode_options({'category': 'TV', 'season': 'S01', 'episode': 'E03', 'tv_pack': 0})
        assert opts.get('7') == 121  # S01 → 121
        assert opts.get('6') == 99   # E03 → 96+3=99

    def test_tv_season_pack(self):
        c = C411(_config())
        opts = c._get_season_episode_options({'category': 'TV', 'season': 'S05', 'episode': '', 'tv_pack': 1})
        assert opts.get('7') == 125  # S05 → 120+5
        assert opts.get('6') == 96   # Saison complète

    def test_tv_s15(self):
        c = C411(_config())
        opts = c._get_season_episode_options({'category': 'TV', 'season': 'S15', 'episode': 'E01', 'tv_pack': 0})
        assert opts.get('7') == 135  # S15 → 120+15
        assert opts.get('6') == 97   # E01 → 96+1

    def test_tv_season_beyond_30(self):
        c = C411(_config())
        opts = c._get_season_episode_options({'category': 'TV', 'season': 'S35', 'episode': '', 'tv_pack': 0})
        assert opts.get('7') == 118  # Intégrale as fallback

    def test_tv_episode_beyond_20(self):
        """Episode > 20 should not be mapped (no ID available)."""
        c = C411(_config())
        opts = c._get_season_episode_options({'category': 'TV', 'season': 'S01', 'episode': 'E25', 'tv_pack': 0})
        assert '6' not in opts


# ─── Options builder ─────────────────────────────────────────

class TestBuildOptions:
    def test_movie_webdl_1080_multi(self):
        c = C411(_config())
        meta = _meta_base(type='WEBDL', resolution='1080p', category='MOVIE')
        opts = c._build_options(meta, 'MULTI.VFF')
        assert opts == {'1': [4], '2': 25}

    def test_tv_s01e03_vostfr(self):
        c = C411(_config())
        meta = _meta_base(category='TV', season='S01', episode='E03', type='WEBDL', resolution='1080p', tv_pack=0)
        opts = c._build_options(meta, 'VOSTFR')
        assert opts['1'] == [8]   # VOSTFR
        assert opts['2'] == 25    # WEB-DL 1080
        assert opts['7'] == 121   # S01
        assert opts['6'] == 99    # E03


# ─── Description builder ─────────────────────────────────────

class TestDescription:
    def _run(self, meta: dict[str, Any]) -> str:
        c = C411(_config())
        return asyncio.run(c._build_description(meta))

    def test_basic_structure(self):
        meta = _meta_base()
        desc = self._run(meta)
        assert '[color=#3d85c6]Synopsis[/color]' in desc
        assert 'Un dîner entre amis' in desc
        assert '[img]https://image.tmdb.org/poster.jpg[/img]' in desc

    def test_no_poster(self):
        meta = _meta_base(poster='')
        desc = self._run(meta)
        assert '[img]' not in desc or 'streetprez' in desc  # only rating SVG if any
        assert '[color=#3d85c6]Synopsis[/color]' in desc

    def test_with_screenshots(self):
        meta = _meta_base(image_list=[
            {'raw_url': 'https://img.host/1.png', 'web_url': 'https://img.host/view/1'},
            {'raw_url': 'https://img.host/2.png', 'web_url': ''},
        ])
        c = C411(_config({'include_screenshots': True}))
        desc = asyncio.run(c._build_description(meta))
        assert "[color=#3d85c6]Captures d'écran[/color]" in desc
        assert '[url=https://img.host/view/1][img]https://img.host/1.png[/img][/url]' in desc
        assert '[img]https://img.host/2.png[/img]' in desc

    def test_screenshots_excluded_by_default(self):
        meta = _meta_base(image_list=[
            {'raw_url': 'https://img.host/1.png', 'web_url': 'https://img.host/view/1'},
        ])
        desc = self._run(meta)
        assert 'https://img.host/1.png' not in desc
        assert "Captures d'écran" not in desc


# ─── TMDB data builder ───────────────────────────────────────

# Fake TMDB API response matching what /3/movie/{id} returns with append_to_response=credits,keywords
_FAKE_TMDB_RESPONSE: dict[str, Any] = {
    'id': 1234,
    'imdb_id': 'tt1234567',
    'title': 'Le Prénom',
    'original_title': 'Le Prénom',
    'overview': 'Un dîner entre amis tourne mal.',
    'poster_path': '/prenom_poster.jpg',
    'backdrop_path': '/prenom_backdrop.jpg',
    'release_date': '2012-04-25',
    'runtime': 109,
    'vote_average': 6.8,
    'vote_count': 1500,
    'status': 'Released',
    'tagline': 'Tout est dans le prénom.',
    'genres': [{'id': 35, 'name': 'Comédie'}, {'id': 18, 'name': 'Drame'}],
    'production_countries': [{'name': 'France'}],
    'spoken_languages': [{'name': 'Français', 'english_name': 'French'}],
    'production_companies': [{'name': 'Pathé'}, {'name': 'TF1 Films'}],
    'credits': {
        'crew': [
            {'name': 'Alexandre de La Patellière', 'job': 'Director', 'department': 'Directing'},
            {'name': 'Matthieu Delaporte', 'job': 'Director', 'department': 'Directing'},
            {'name': 'Alexandre de La Patellière', 'job': 'Writer', 'department': 'Writing'},
        ],
        'cast': [
            {'name': 'Patrick Bruel', 'character': 'Vincent'},
            {'name': 'Valérie Benguigui', 'character': 'Élisabeth'},
            {'name': 'Charles Berling', 'character': 'Pierre'},
        ],
    },
    'keywords': {
        'keywords': [
            {'id': 1, 'name': 'family dinner'},
            {'id': 2, 'name': 'comedy'},
        ],
    },
}


def _run_async(coro):
    return asyncio.run(coro)


class TestTmdbData:
    def _build(self, meta, tmdb_response=None):
        """Helper to call async _build_tmdb_data with mocked _fetch_tmdb_full."""
        c = C411(_config())
        resp = tmdb_response if tmdb_response is not None else _FAKE_TMDB_RESPONSE
        c._fetch_tmdb_full = AsyncMock(return_value=resp)
        return _run_async(c._build_tmdb_data(meta))

    def test_builds_full_json(self):
        meta = _meta_base()
        result = self._build(meta)
        assert result is not None
        data = json.loads(result)
        assert data['id'] == 1234
        assert data['type'] == 'movie'
        assert data['imdbId'] == 'tt1234567'
        assert data['title'] == 'Le Prénom'
        assert data['originalTitle'] == 'Le Prénom'
        assert data['overview'] == 'Un dîner entre amis tourne mal.'
        assert data['posterUrl'] == 'https://image.tmdb.org/t/p/w500/prenom_poster.jpg'
        assert data['backdropUrl'] == 'https://image.tmdb.org/t/p/w1280/prenom_backdrop.jpg'
        assert data['releaseDate'] == '2012-04-25'
        assert data['year'] == 2012
        assert data['runtime'] == 109
        assert data['rating'] == 6.8
        assert data['ratingCount'] == 1500
        assert data['status'] == 'Released'
        assert data['tagline'] == 'Tout est dans le prénom.'
        # Should NOT contain old-format keys
        assert 'media_type' not in data
        assert 'poster_path' not in data
        assert 'release_date' not in data
        assert 'original_language' not in data
        assert 'voteAverage' not in data

    def test_genres(self):
        data = json.loads(self._build(_meta_base()))
        assert data['genres'] == ['Comédie', 'Drame']
        assert data['genreIds'] == [35, 18]

    def test_credits(self):
        data = json.loads(self._build(_meta_base()))
        assert 'Alexandre de La Patellière' in data['directors']
        assert 'Matthieu Delaporte' in data['directors']
        assert data['writers'] == ['Alexandre de La Patellière']
        assert data['cast'][0] == {'name': 'Patrick Bruel', 'character': 'Vincent'}
        assert len(data['cast']) == 3

    def test_metadata_arrays(self):
        data = json.loads(self._build(_meta_base()))
        assert data['countries'] == ['France']
        assert data['languages'] == ['French']
        assert data['productionCompanies'] == ['Pathé', 'TF1 Films']
        assert data['keywords'] == ['family dinner', 'comedy']

    def test_tv_type(self):
        data = json.loads(self._build(_meta_base(category='TV')))
        assert data['type'] == 'tv'

    def test_empty_tmdb_response(self):
        """When TMDB API returns nothing, falls back to meta fields."""
        meta = _meta_base()
        result = self._build(meta, tmdb_response={})
        data = json.loads(result)
        assert data['id'] == 1234
        assert data['type'] == 'movie'
        assert data['title'] == 'Le Prénom'
        assert data['overview'] == 'Un dîner entre amis tourne mal.'
        assert data['genres'] == []
        assert data['directors'] == []

    def test_no_tmdb(self):
        c = C411(_config())
        meta = _meta_base(tmdb=None)
        assert _run_async(c._build_tmdb_data(meta)) is None


# ─── Torznab XML parsing ─────────────────────────────────────

class TestTorznabParser:
    SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:torznab="http://torznab.com/schemas/2015/feed">
  <channel>
    <title>C411</title>
    <item>
      <title>Le.Prenom.2012.FRENCH.1080p.WEB.x264.AC3-Troxy</title>
      <guid>https://c411.org/torrents/12345</guid>
      <link>https://c411.org/torrents/12345/download</link>
      <size>4831838208</size>
      <torznab:attr name="files" value="1" />
      <torznab:attr name="resolution" value="1080p" />
    </item>
    <item>
      <title>Le.Prenom.2012.MULTI.1080p.BluRay.x264-VENUE</title>
      <guid>https://c411.org/torrents/67890</guid>
      <comments>https://c411.org/torrents/67890</comments>
      <size>9663676416</size>
      <torznab:attr name="files" value="1" />
    </item>
  </channel>
</rss>"""

    def test_parses_two_items(self):
        results = C411._parse_torznab_response(self.SAMPLE_XML)
        assert len(results) == 2

    def test_first_item_fields(self):
        results = C411._parse_torznab_response(self.SAMPLE_XML)
        first = results[0]
        assert first['name'] == 'Le.Prenom.2012.FRENCH.1080p.WEB.x264.AC3-Troxy'
        assert first['size'] == 4831838208
        assert first['link'] == 'https://c411.org/torrents/12345/download'
        assert first['file_count'] == 1
        assert first['res'] == '1080p'

    def test_second_item_no_link_fallback_comments(self):
        results = C411._parse_torznab_response(self.SAMPLE_XML)
        second = results[1]
        assert second['name'] == 'Le.Prenom.2012.MULTI.1080p.BluRay.x264-VENUE'
        assert second['size'] == 9663676416

    def test_empty_xml(self):
        results = C411._parse_torznab_response('<rss><channel></channel></rss>')
        assert results == []

    def test_invalid_xml(self):
        results = C411._parse_torznab_response('this is not xml')
        assert results == []

    def test_missing_size(self):
        xml = """<?xml version="1.0"?>
<rss><channel><item><title>Test</title><guid>1</guid></item></channel></rss>"""
        results = C411._parse_torznab_response(xml)
        assert len(results) == 1
        assert results[0]['size'] is None


# ─── search_existing integration ──────────────────────────────

class TestSearchExisting:
    TORZNAB_RESPONSE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:torznab="http://torznab.com/schemas/2015/feed">
  <channel>
    <item>
      <title>Le.Prenom.2012.FRENCH.1080p.WEB.x264-Troxy</title>
      <guid>https://c411.org/torrents/111</guid>
      <link>https://c411.org/torrents/111/download</link>
      <size>4000000000</size>
    </item>
  </channel>
</rss>"""

    def test_search_with_imdb(self):
        c = C411(_config())
        meta = _meta_base()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = self.TORZNAB_RESPONSE

        with patch('httpx.AsyncClient') as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            dupes = asyncio.run(
                c.search_existing(meta, 'nodisc')
            )

        assert len(dupes) >= 1
        assert dupes[0]['name'] == '[COMPAT-01] Le.Prenom.2012.FRENCH.1080p.WEB.x264-Troxy'

        # Verify API was called with correct params
        call_args = mock_client.get.call_args_list
        assert any('c411.org/api' in str(ca) for ca in call_args)

    def test_search_no_api_key(self):
        c = C411({'TRACKERS': {'C411': {'api_key': ''}}, 'DEFAULT': {'tmdb_api': 'fake'}})
        meta = _meta_base()
        dupes = asyncio.run(
            c.search_existing(meta, 'nodisc')
        )
        assert dupes == []

    def test_search_http_error(self):
        c = C411(_config())
        meta = _meta_base(debug=True)

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = 'Internal Server Error'

        with patch('httpx.AsyncClient') as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            dupes = asyncio.run(
                c.search_existing(meta, 'nodisc')
            )

        assert dupes == []

    def test_search_deduplicates(self):
        """When IMDB + text search return the same torrent, it should appear only once."""
        c = C411(_config())
        meta = _meta_base()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = self.TORZNAB_RESPONSE

        with patch('httpx.AsyncClient') as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            dupes = asyncio.run(
                c.search_existing(meta, 'nodisc')
            )

        # Should be deduplicated by guid
        assert len(dupes) == 1


# ─── Announce URL / Config ────────────────────────────────────

class TestAnnounceUrl:
    def test_announce_url_in_config(self):
        """COMMON.create_torrent_for_upload() reads announce_url from config."""
        cfg = _config()
        assert cfg['TRACKERS']['C411']['announce_url'] == 'https://c411.org/announce/FAKE_PASSKEY'

    def test_notag_config(self):
        """Ensure notag config values are correct defaults."""
        cfg = _config({'accept_notag': True, 'notag_label': 'NOTAG'})
        assert cfg['TRACKERS']['C411']['accept_notag'] is True
        assert cfg['TRACKERS']['C411']['notag_label'] == 'NOTAG'


# ─── French subtitle detection ───────────────────────────────

class TestFrenchSubs:
    def test_french_sub_by_lang(self):
        c = C411(_config())
        meta = _meta_base(mediainfo=_mi([], [_sub_track('fr')]))
        assert c._has_french_subs(meta) is True

    def test_french_sub_by_lang_fre(self):
        c = C411(_config())
        meta = _meta_base(mediainfo=_mi([], [_sub_track('fre')]))
        assert c._has_french_subs(meta) is True

    def test_french_sub_by_title(self):
        c = C411(_config())
        meta = _meta_base(mediainfo={'media': {'track': [
            {'@type': 'Text', 'Language': 'und', 'Title': 'French (SDH)'},
        ]}})
        assert c._has_french_subs(meta) is True

    def test_no_french_sub(self):
        c = C411(_config())
        meta = _meta_base(mediainfo=_mi([], [_sub_track('en')]))
        assert c._has_french_subs(meta) is False


# ─── Language code mapping ───────────────────────────────────

class TestMapLanguage:
    def test_various_codes(self):
        c = C411(_config())
        assert c._map_language('fr') == 'FRA'
        assert c._map_language('fra') == 'FRA'
        assert c._map_language('fre') == 'FRA'
        assert c._map_language('french') == 'FRA'
        assert c._map_language('fr-fr') == 'FRA'
        assert c._map_language('fr-ca') == 'FRA'
        assert c._map_language('en') == 'ENG'
        assert c._map_language('eng') == 'ENG'
        assert c._map_language('de') == 'DEU'
        assert c._map_language('jpn') == 'JPN'
        assert c._map_language('') == ''

    def test_unknown_truncated(self):
        c = C411(_config())
        assert c._map_language('swahili') == 'SWA'
        assert c._map_language('ab') == 'AB'


# ─── French dub suffix detection ─────────────────────────────

class TestFrenchDubSuffix:
    def test_no_french(self):
        c = C411(_config())
        assert c._get_french_dub_suffix([_audio_track('en')]) is None

    def test_generic_french(self):
        c = C411(_config())
        assert c._get_french_dub_suffix([_audio_track('fr')]) is None

    def test_vff(self):
        c = C411(_config())
        assert c._get_french_dub_suffix([_audio_track('fr-fr')]) == 'VFF'

    def test_vfq(self):
        c = C411(_config())
        assert c._get_french_dub_suffix([_audio_track('fr-ca')]) == 'VFQ'

    def test_vf2(self):
        c = C411(_config())
        assert c._get_french_dub_suffix([_audio_track('fr-fr'), _audio_track('fr-ca')]) == 'VF2'


# ─── Service exclusion from names / inclusion in description ─

class TestServiceExclusion:
    """C411 wants the streaming service (NF, AMZN, …) OUT of release names
    but IN the description."""

    def _run_name(self, meta: dict[str, Any]) -> str:
        c = C411(_config())
        c._get_french_title = AsyncMock(return_value=meta.get('title', ''))
        result = asyncio.run(c.get_name(meta))
        return result.get('name', '')

    def _run_desc(self, meta: dict[str, Any]) -> str:
        c = C411(_config())
        return asyncio.run(c._build_description(meta))

    def test_webdl_no_service_in_name(self):
        """WEBDL release with service='NF' must NOT have 'NF' in the name."""
        meta = _meta_base(
            service='NF',
            mediainfo=_mi([_audio_track('fr')]),
            original_language='fr',
        )
        name = self._run_name(meta)
        assert 'NF' not in name
        assert 'WEB' in name

    def test_webrip_no_service_in_name(self):
        """WEBRip release with service='AMZN' must NOT have 'AMZN' in the name."""
        meta = _meta_base(
            type='WEBRIP',
            service='AMZN',
            mediainfo=_mi([_audio_track('fr')]),
            original_language='fr',
        )
        name = self._run_name(meta)
        assert 'AMZN' not in name
        assert 'WEBRip' in name

    def test_service_in_description(self):
        """Service should appear in the description under 'Informations techniques'."""
        meta = _meta_base(service='NF')
        desc = self._run_desc(meta)
        assert 'Service' in desc
        assert 'NF' in desc

    def test_no_service_line_when_empty(self):
        """When there's no service, no 'Service :' line in the description."""
        meta = _meta_base(service='')
        desc = self._run_desc(meta)
        assert 'Service :' not in desc

    def test_include_service_flag_false(self):
        """C411 must have INCLUDE_SERVICE_IN_NAME = False."""
        c = C411(_config())
        assert c.INCLUDE_SERVICE_IN_NAME is False


# ═══════════════════════════════════════════════════════════════
#  MediaInfo filename patching  (_patch_mi_filename)
# ═══════════════════════════════════════════════════════════════


class TestPatchMiFilename:
    """Unit tests for FrenchTrackerMixin._patch_mi_filename."""

    SAMPLE_MI = (
        "General\n"
        "Complete name                            : The.Bear.2022.S04E01.2160p.WEB-DL.DDP5.1.DV.H.265.mkv\n"
        "Format                                   : Matroska\n"
        "File size                                : 4.32 GiB\n"
        "Duration                                 : 42 min 3 s\n"
    )

    def test_basic_patch(self):
        """Complete name should be replaced, preserving extension."""
        result = C411._patch_mi_filename(
            self.SAMPLE_MI,
            "The.Bear.2022.S04E01.MULTI.VFF.2160p.WEB.DDP5.1.DV.H265-NOTAG",
        )
        assert "The.Bear.2022.S04E01.MULTI.VFF.2160p.WEB.DDP5.1.DV.H265-NOTAG.mkv" in result
        # Original filename must be gone
        assert "WEB-DL.DDP5.1.DV.H.265.mkv" not in result

    def test_preserves_extension(self):
        """The original .mkv extension should be kept."""
        mi = self.SAMPLE_MI.replace(".mkv", ".mp4")
        result = C411._patch_mi_filename(mi, "New.Name-TAG")
        assert "New.Name-TAG.mp4" in result

    def test_preserves_other_lines(self):
        """Lines other than 'Complete name' should be untouched."""
        result = C411._patch_mi_filename(self.SAMPLE_MI, "Patched-NOTAG")
        assert "Format                                   : Matroska" in result
        assert "File size                                : 4.32 GiB" in result

    def test_no_complete_name_line(self):
        """MI without a 'Complete name' line should be returned unchanged."""
        mi_no_cn = "General\nFormat : Matroska\n"
        result = C411._patch_mi_filename(mi_no_cn, "Anything-TAG")
        assert result == mi_no_cn

    def test_empty_inputs(self):
        """Empty MI text or empty name should return MI unchanged."""
        assert C411._patch_mi_filename("", "name") == ""
        assert C411._patch_mi_filename(self.SAMPLE_MI, "") == self.SAMPLE_MI

    def test_no_extension(self):
        """File without extension in MI should work (no extension appended)."""
        mi_no_ext = self.SAMPLE_MI.replace(
            "The.Bear.2022.S04E01.2160p.WEB-DL.DDP5.1.DV.H.265.mkv",
            "SomeFile",
        )
        result = C411._patch_mi_filename(mi_no_ext, "New.Name-TAG")
        assert "New.Name-TAG" in result
        # No .mkv should appear
        assert ".mkv" not in result

    def test_notag_scenario(self):
        """Simulate nogrp upload: original has no group, patched name adds -NOTAG."""
        mi = (
            "General\n"
            "Complete name                            : Some.Movie.2024.FRENCH.1080p.WEB.H264.mkv\n"
            "Format                                   : Matroska\n"
        )
        result = C411._patch_mi_filename(
            mi, "Some.Movie.2024.FRENCH.1080p.WEB.H264-NOTAG"
        )
        assert "Some.Movie.2024.FRENCH.1080p.WEB.H264-NOTAG.mkv" in result
        # Original without tag must be gone
        assert "Complete name" in result
        lines = [l for l in result.splitlines() if "Complete name" in l]
        assert len(lines) == 1
        assert "-NOTAG.mkv" in lines[0]

    def test_alignment_preserved(self):
        """The label + colon + spacing before the value should be preserved."""
        result = C411._patch_mi_filename(self.SAMPLE_MI, "X-TAG")
        cn_line = [l for l in result.splitlines() if "Complete name" in l][0]
        # The prefix "Complete name                            : " should remain
        assert cn_line.startswith("Complete name                            : ")


# ─── Corrective version (REPACK) dupe behaviour ──────────────

class TestCorrectiveVersionDupe:
    """REPACK / PROPER should NOT bypass dupe checking."""

    TORZNAB_RESPONSE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:torznab="http://torznab.com/schemas/2015/feed">
  <channel>
    <item>
      <title>Inglourious.Basterds.2009.VOSTFR.2160p.BluRay.HDR10PLUS.DTS.HD.MA.5.1.x265-GRP</title>
      <guid>https://c411.org/torrents/999</guid>
      <link>https://c411.org/torrents/999/download</link>
      <size>50000000000</size>
    </item>
  </channel>
</rss>"""

    def _make_mock_client(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = self.TORZNAB_RESPONSE

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        return mock_client

    def test_repack_still_shows_dupes(self):
        """A REPACK upload must still surface existing releases in the same slot."""
        c = C411(_config())
        meta = _meta_base(
            title='Inglourious Basterds',
            year='2009',
            repack='REPACK',
            resolution='2160p',
            type='ENCODE',
            video_encode='x265',
            audio='DTS-HD MA 5.1',
            hdr='HDR10+',
            source='BluRay',
        )

        with patch('httpx.AsyncClient') as mock_cls:
            mock_cls.return_value = self._make_mock_client()
            dupes = asyncio.run(c.search_existing(meta, 'nodisc'))

        # The slot-matching dupe must NOT be silently dropped
        assert len(dupes) >= 1, "REPACK should not suppress dupe results"
        assert any('Inglourious' in d.get('name', '') for d in dupes)
        # The corrective slot warning flag must be set for dupe_check() to display
        assert meta.get('_corrective_slot_warning') is True

    def test_non_repack_also_shows_dupes(self):
        """Sanity: a non-corrective upload in the same slot shows dupes too."""
        c = C411(_config())
        meta = _meta_base(
            title='Inglourious Basterds',
            year='2009',
            repack='',
            resolution='2160p',
            type='ENCODE',
            video_encode='x265',
            audio='DTS-HD MA 5.1',
            hdr='HDR10+',
            source='BluRay',
        )

        with patch('httpx.AsyncClient') as mock_cls:
            mock_cls.return_value = self._make_mock_client()
            dupes = asyncio.run(c.search_existing(meta, 'nodisc'))

        assert len(dupes) >= 1
        # Non-corrective should NOT have the warning flag
        assert meta.get('_corrective_slot_warning') is None
