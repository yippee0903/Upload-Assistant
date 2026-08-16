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
        'audio_languages': ['French'],
        'subtitle_languages': [],
        'bdinfo': None,
        'mediainfo': {
            'media': {
                'track': []
            }
        },
        'tracker_status': {'C411': {}},
        'has_encode_settings': False,
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

    # ── SUBFRENCH filename fallback → VOSTFR ──

    def test_subfrench_in_uuid(self):
        """SUBFRENCH in uuid, no French subs in MediaInfo → VOSTFR."""
        meta = _meta_base(
            mediainfo=_mi([_audio_track('en')]),
            original_language='en',
            uuid='Movie.2025.SUBFRENCH.1080p.BluRay.x264-GROUP',
        )
        assert self._run(meta) == 'VOSTFR'

    def test_subfrench_in_path(self):
        """SUBFRENCH in path, no French subs in MediaInfo → VOSTFR."""
        meta = _meta_base(
            mediainfo=_mi([_audio_track('en')]),
            original_language='en',
            path='/media/Movie.SUBFRENCH.720p.mkv',
        )
        assert self._run(meta) == 'VOSTFR'

    def test_subfrench_in_name(self):
        """SUBFRENCH in name field, no French subs in MediaInfo → VOSTFR."""
        meta = _meta_base(
            mediainfo=_mi([_audio_track('en')]),
            original_language='en',
            name='Movie.2025.SUBFRENCH.1080p.BluRay.x264-GROUP',
        )
        assert self._run(meta) == 'VOSTFR'

    def test_subfrench_ignored_when_french_audio(self):
        """SUBFRENCH in filename but French audio present → use audio-based tag, not VOSTFR."""
        meta = _meta_base(
            mediainfo=_mi([_audio_track('fr'), _audio_track('en')]),
            original_language='en',
            uuid='Movie.2025.SUBFRENCH.1080p.BluRay.x264-GROUP',
        )
        # French audio detected → MULTI.VFF (not VOSTFR)
        assert self._run(meta) == 'MULTI.VFF'

    def test_vostfr_in_filename_fallback(self):
        """VOSTFR in filename, no French subs in MediaInfo → still VOSTFR."""
        meta = _meta_base(
            mediainfo=_mi([_audio_track('en')]),
            original_language='en',
            uuid='Movie.2025.VOSTFR.1080p.BluRay.x264-GROUP',
        )
        assert self._run(meta) == 'VOSTFR'


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
        """TrueHD Atmos must have ATMOS after TRUEHD for C411."""
        meta = _meta_base(
            type='REMUX',
            source='BluRay',
            audio='Atmos TrueHD 7.1',
            mediainfo=_mi([_audio_track('en')]),
            original_language='en',
        )
        name = self._run(meta)
        assert '.TRUEHD.ATMOS' in name or 'TRUEHD.ATMOS.7.1' in name

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

    def test_most_channel_track_audio_used(self):
        """When FR track exists, its codec/channels must appear in the name if it's the same channel number."""
        meta = _meta_base(
            title='Harry Potter Et La Coupe De Feu',
            year='2005',
            type='REMUX',
            source='BluRay',
            resolution='2160p',
            uhd='UHD',
            hdr='DV HDR',
            video_codec='HEVC',
            audio='DTS:X 7.1',
            tag='-SGF',
            mediainfo=_mi([
                _audio_track('en', Format='DTS',
                             Format_AdditionalFeatures='XLL X',
                             Channels='8'),
                _audio_track('fr', Format='MLP FBA',
                             Format_AdditionalFeatures='16-ch',
                             Channels='8'),
            ]),
            original_language='en',
        )
        name = self._run(meta)
        # FR track is DTS-HD MA 5.1, NOT the English DTS:X 7.1
        assert 'TRUEHD.ATMOS.7.1' in name, f"Expected FR track audio TRUEHD.ATMOS.7.1: {name}"
        assert 'DTS.X' not in name, f"English DTS:X leaked into name: {name}"

    def test_lossless_higher_channel(self):
        """When lossless tracks exists, the one with more channels must appear in the name."""
        meta = _meta_base(
            title='Harry Potter Et La Coupe De Feu',
            year='2005',
            type='REMUX',
            source='BluRay',
            resolution='2160p',
            uhd='UHD',
            hdr='DV HDR',
            video_codec='HEVC',
            audio='DTS:X 7.1',
            tag='-SGF',
            mediainfo=_mi([
                _audio_track('en', Format='DTS',
                             Format_AdditionalFeatures='XLL X',
                             Channels='8'),
                _audio_track('fr', Format='DTS',
                             Format_AdditionalFeatures='XLL',
                             Channels='6'),
            ]),
            original_language='en',
        )
        name = self._run(meta)
        # FR track is DTS-HD MA 5.1, NOT the English DTS:X 7.1
        assert 'DTS.X' in name, f"Expected EN track audio DTS:X: {name}"
        assert 'DTS.HD.MA.5.1' not in name, f"FR track audio with the least channels leaked into name: {name}"

    def test_french_track_ddp_vs_truehd(self):
        """EN track TrueHD Atmos must be used event if FR track DD+ 5.1 exist (Lossless and channels priority)."""
        meta = _meta_base(
            type='REMUX',
            source='BluRay',
            audio='TrueHD Atmos 7.1',
            mediainfo=_mi([
                _audio_track('en', Format='MLP FBA',
                             Format_AdditionalFeatures='16-ch',
                             Channels='8'),
                _audio_track('fr', Format='E-AC-3',
                             Channels='6'),
            ]),
            original_language='en',
        )
        name = self._run(meta)
        assert 'TRUEHD' in name, f"Expected EN track DDP.5.1: {name}"
        assert 'DDP.5.1' not in name, f"French DD+ 5.1 leaked: {name}"

    def test_no_french_track_keeps_meta_audio(self):
        """Without FR tracks, meta['audio'] (first track) is used."""
        meta = _meta_base(
            type='REMUX',
            source='BluRay',
            audio='DTS:X 7.1',
            mediainfo=_mi([_audio_track('en', Format='DTS',
                                        Format_AdditionalFeatures='XLL X',
                                        Channels='8')]),
            original_language='en',
        )
        name = self._run(meta)
        assert 'DTS.X.7.1' in name, f"Expected meta audio DTS.X.7.1: {name}"

    def test_french_only_release_uses_french_track(self):
        """Single FR track (no EN): codec is still derived from MediaInfo."""
        meta = _meta_base(
            type='REMUX',
            source='BluRay',
            audio='DTS-HD MA 5.1',
            mediainfo=_mi([
                _audio_track('fr', Format='DTS',
                             Format_AdditionalFeatures='XLL',
                             Channels='6'),
            ]),
            original_language='fr',
        )
        name = self._run(meta)
        assert 'DTS.HD.MA.5.1' in name, f"Expected DTS.HD.MA.5.1: {name}"

    def test_french_track_missing_format_uses_meta_audio(self):
        """FR track present but without Format key → fall back to meta['audio']."""
        meta = _meta_base(
            type='REMUX',
            source='BluRay',
            audio='DTS:X 7.1',
            mediainfo=_mi([
                _audio_track('en', Format='DTS',
                             Channels='6'),
                _audio_track('fr', Channels='6'),
            ]),
            original_language='en',
        )
        name = self._run(meta)
        # No Format on FR track → falls back to meta['audio'] which is DTS:X 7.1
        assert 'DTS.X.7.1' in name, f"Expected fallback to meta audio DTS.X.7.1: {name}"

    def test_lossy_audio_track_fr_priority(self):
        """For lossy tracks, must always pick FR track."""
        meta = _meta_base(
            type='REMUX',
            source='BluRay',
            audio='DDP 5.1',
            mediainfo=_mi([
                _audio_track('en', Format='E-AC-3',
                             Channels='6'),
                _audio_track('fr', Format='E-AC-3',
                             Channels='2'),
            ]),
            original_language='en',
        )
        name = self._run(meta)
        assert 'DDP.2.0' in name, f"Expected FR track DDP.2.0: {name}"
        assert 'DDP.5.1' not in name, f"English DD+ 5.1 leaked: {name}"

    def test_lossy_audio_track_fr_most_channels_priority(self):
        """For lossy tracks, must always pick FR track with most channels."""
        meta = _meta_base(
            type='REMUX',
            source='BluRay',
            audio='DDP 5.1',
            mediainfo=_mi([
                _audio_track('fr', Format='E-AC-3',
                             Channels='2'),
                _audio_track('fr', Format='E-AC-3',
                             Channels='6'),
            ]),
            original_language='en',
        )
        name = self._run(meta)
        assert 'DDP.5.1' in name, f"Expected FR track DDP.5.1: {name}"
        assert 'DDP.2.0' not in name, f"French DD+ 2.0 leaked: {name}"

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

    def test_hybrid_after_resolution(self):
        """C411 rule: Hybrid token must appear AFTER resolution, not before."""
        meta = _meta_base(
            title='X-Men Apocalypse',
            year='2016',
            resolution='2160p',
            uhd='UHD',
            source='BluRay',
            type='REMUX',
            webdv='Hybrid',
            hdr='DV HDR10+',
            video_codec='HEVC',
            video_encode='',
            audio='DTS 5.1',
            tag='-KENOBi3838',
            mediainfo=_mi([_audio_track('fr'), _audio_track('en')]),
            original_language='en',
        )
        name = self._run(meta)
        import re
        assert '.Hybrid.' in name, f"Hybrid not found: {name}"
        res_match = re.search(r'\.(2160p|1080p|720p)\.', name)
        hybrid_pos = name.find('.Hybrid.')
        assert res_match is not None, f"Resolution not found in name: {name}"
        assert hybrid_pos > res_match.start(), (
            f"Hybrid ({hybrid_pos}) must come after resolution ({res_match.start()}): {name}"
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

    def test_vc1_cleaned(self):
        """VC-1 must appear as VC1 (no hyphen, no dot)."""
        meta = _meta_base(
            title='Test', year='2024', type='REMUX', source='BluRay',
            resolution='1080p', video_codec='VC-1',
            mediainfo=_mi([_audio_track('fr')]), original_language='en',
        )
        name = self._run(meta)
        assert 'VC1' in name
        assert 'VC-1' not in name
        assert 'VC.1' not in name

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

    def test_webdl_no_encode_settings_keeps_h264(self):
        """WEB-DL without Encoded_Library_Settings must keep H264."""
        meta = _meta_base(
            title='Test', year='2024', type='WEBDL', source='WEB',
            resolution='1080p', video_encode='H.264',
            has_encode_settings=False,
            mediainfo=_mi([_audio_track('en')]), original_language='en',
        )
        name = self._run(meta)
        assert '.H264' in name, f"True WEB-DL should keep H264, got: {name}"
        assert '.x264' not in name

    def test_webdl_no_encode_settings_keeps_h265(self):
        """WEB-DL without Encoded_Library_Settings must keep H265."""
        meta = _meta_base(
            title='Test', year='2024', type='WEBDL', source='WEB',
            resolution='2160p', video_encode='H.265',
            has_encode_settings=False,
            mediainfo=_mi([_audio_track('en')]), original_language='en',
        )
        name = self._run(meta)
        assert '.H265' in name, f"True WEB-DL should keep H265, got: {name}"
        assert '.x265' not in name

    def test_webdl_with_encode_settings_becomes_x264(self):
        """WEB-DL with Encoded_Library_Settings must use x264 (re-encoded)."""
        meta = _meta_base(
            title='Test', year='2024', type='WEBDL', source='WEB',
            resolution='1080p', video_encode='H.264',
            has_encode_settings=True,
            mediainfo=_mi([_audio_track('en')]), original_language='en',
        )
        name = self._run(meta)
        assert '.x264' in name, f"Re-encoded WEB-DL should use x264, got: {name}"
        assert '.H264' not in name

    def test_webdl_with_encode_settings_becomes_x265(self):
        """WEB-DL with Encoded_Library_Settings must use x265 (re-encoded)."""
        meta = _meta_base(
            title='Test', year='2024', type='WEBDL', source='WEB',
            resolution='2160p', video_encode='H.265',
            has_encode_settings=True,
            mediainfo=_mi([_audio_track('en')]), original_language='en',
        )
        name = self._run(meta)
        assert '.x265' in name, f"Re-encoded WEB-DL should use x265, got: {name}"
        assert '.H265' not in name

    def test_webrip_with_encode_settings_uses_x264(self):
        """WEBRip (re-encoded) uses x264 — confirmed by encode settings."""
        meta = _meta_base(
            title='Test', year='2024', type='WEBRIP', source='WEB',
            resolution='1080p', video_encode='x264',
            has_encode_settings=True,
            mediainfo=_mi([_audio_track('en')]), original_language='en',
        )
        name = self._run(meta)
        assert '.x264' in name, f"WEBRip should have x264, got: {name}"
        assert '.H264' not in name

    def test_webrip_with_encode_settings_uses_x265(self):
        """WEBRip (re-encoded) uses x265 — confirmed by encode settings."""
        meta = _meta_base(
            title='Test', year='2024', type='WEBRIP', source='WEB',
            resolution='2160p', video_encode='x265',
            has_encode_settings=True,
            mediainfo=_mi([_audio_track('en')]), original_language='en',
        )
        name = self._run(meta)
        assert '.x265' in name, f"WEBRip should have x265, got: {name}"
        assert '.H265' not in name

    def test_webrip_no_encode_settings_normalises_to_h264(self):
        """WEBRip WITHOUT encode settings — C411 normalises to H264 (true stream)."""
        meta = _meta_base(
            title='Test', year='2024', type='WEBRIP', source='WEB',
            resolution='1080p', video_encode='x264',
            has_encode_settings=False,
            mediainfo=_mi([_audio_track('en')]), original_language='en',
        )
        name = self._run(meta)
        assert '.H264' in name, f"WEBRip without encode settings should be H264, got: {name}"
        assert '.x264' not in name

    def test_encode_h264_stays_h264(self):
        """BluRay encode should keep H264 (not convert to x264)."""
        meta = _meta_base(
            title='Test', year='2024', type='ENCODE', source='BluRay',
            resolution='1080p', video_encode='H.264',
            mediainfo=_mi([_audio_track('en')]), original_language='en',
        )
        name = self._run(meta)
        assert '.H264' in name, f"BluRay encode should keep H264, got: {name}"
        assert '.x264' not in name


# ─── 4KLight / HDLight token in name ─────────────────────────

class TestLightEncodeTag:
    """4KLight/HDLight (BluRay light re-encodes) must survive into the name,
    placed right after the source — they aren't a meta field, so they're read
    from the original filename (uuid)."""

    def _run(self, meta: dict[str, Any]) -> str:
        c = C411(_config())
        c._get_french_title = AsyncMock(return_value=meta.get('title', ''))
        c._build_audio_string = AsyncMock(return_value='')
        return asyncio.run(c.get_name(meta)).get('name', '')

    def test_4klight_after_source(self):
        meta = _meta_base(
            title='Solo', year='2018', type='ENCODE', source='BluRay',
            resolution='2160p', video_encode='x265', hdr='DV HDR',
            uuid='Solo.2018.2160p.4KLight.DV.HDR.BluRay.x265-QTZ.mkv',
            mediainfo=_mi([_audio_track('fr')]), original_language='en',
        )
        name = self._run(meta)
        assert '4KLight' in name, name
        # placed immediately after the source token
        assert 'BluRay.4KLight' in name, name

    def test_hdlight_token(self):
        meta = _meta_base(
            title='Film', year='2020', type='ENCODE', source='BluRay',
            resolution='1080p', video_encode='x265',
            uuid='Film.2020.1080p.HDLight.BluRay.x265-GRP.mkv',
            mediainfo=_mi([_audio_track('fr')]), original_language='en',
        )
        name = self._run(meta)
        assert 'HDLight' in name, name

    def test_no_light_tag_when_absent(self):
        meta = _meta_base(
            title='Film', year='2020', type='ENCODE', source='BluRay',
            resolution='2160p', video_encode='x265',
            uuid='Film.2020.2160p.BluRay.x265-GRP.mkv',
            mediainfo=_mi([_audio_track('fr')]), original_language='en',
        )
        name = self._run(meta)
        assert 'Light' not in name, name


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


# ─── _detect_lang_tag_from_name (dupe matching) ──────────────

class TestDetectLangTagFromName:
    """Test C411._detect_lang_tag_from_name recognises lang tags in existing torrent names."""

    def test_vostfr(self):
        assert C411._detect_lang_tag_from_name('Movie.2025.VOSTFR.1080p.WEB.H264-GROUP') == 'VOSTFR'

    def test_subfrench_normalised_to_vostfr(self):
        """SUBFRENCH in an existing torrent name should be treated as VOSTFR."""
        assert C411._detect_lang_tag_from_name('Movie.2025.SUBFRENCH.1080p.BluRay.x264-GROUP') == 'VOSTFR'

    def test_subfrench_space_separated(self):
        assert C411._detect_lang_tag_from_name('Movie 2025 SUBFRENCH 1080p BluRay x264-GROUP') == 'VOSTFR'

    def test_multi_vff(self):
        assert C411._detect_lang_tag_from_name('Movie.2025.MULTI.VFF.1080p.WEB.H264-GROUP') == 'MULTI.VFF'

    def test_no_tag(self):
        assert C411._detect_lang_tag_from_name('Movie.2025.1080p.WEB.H264-GROUP') == ''

    def test_subfrench_case_insensitive(self):
        """Lowercase subfrench must also be recognised."""
        assert C411._detect_lang_tag_from_name('Movie.2025.subfrench.1080p.BluRay.x264-GROUP') == 'VOSTFR'

    def test_subfrench_hyphen_separated(self):
        """Hyphen-separated name with SUBFRENCH."""
        assert C411._detect_lang_tag_from_name('Movie-2025-SUBFRENCH-1080p-BluRay-x264-GROUP') == 'VOSTFR'


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
            {'img_url': 'https://img.host/1.md.png', 'raw_url': 'https://img.host/1.png', 'web_url': 'https://img.host/view/1'},
            {'img_url': 'https://img.host/2.md.png', 'raw_url': 'https://img.host/2.png', 'web_url': ''},
        ])
        c = C411(_config({'include_screenshots': True}))
        desc = asyncio.run(c._build_description(meta))
        assert "[color=#3d85c6]Captures d'écran[/color]" in desc
        # Thumbnails are embedded, linked to the full-size image
        assert '[url=https://img.host/view/1][img]https://img.host/1.md.png[/img][/url]' in desc
        assert '[url=https://img.host/2.png][img]https://img.host/2.md.png[/img][/url]' in desc

    def test_with_screenshots_no_thumbnail(self):
        # Hosts without a separate thumbnail fall back to the full-size URL
        meta = _meta_base(image_list=[
            {'raw_url': 'https://img.host/1.png', 'web_url': 'https://img.host/view/1'},
            {'raw_url': 'https://img.host/2.png', 'web_url': ''},
        ])
        c = C411(_config({'include_screenshots': True}))
        desc = asyncio.run(c._build_description(meta))
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
        assert dupes[0]['name'] == '[COMPAT-WR] Le.Prenom.2012.FRENCH.1080p.WEB.x264-Troxy'

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

    @staticmethod
    def _torznab_page(count: int, start: int = 0) -> str:
        items = "".join(
            f"""<item>
      <title>Film.{start + i}.2012.FRENCH.1080p.WEB.x264-GRP</title>
      <guid>https://c411.org/torrents/{start + i}</guid>
      <link>https://c411.org/torrents/{start + i}/download</link>
      <size>4000000000</size>
    </item>"""
            for i in range(count)
        )
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:torznab="http://torznab.com/schemas/2015/feed">
  <channel>{items}</channel>
</rss>"""

    def test_search_paginates_past_first_page(self):
        """A full page must trigger a follow-up request with the next offset."""
        c = C411(_config())
        meta = _meta_base(tmdb='', imdb_id=0)  # only the text query remains

        pages = [MagicMock(status_code=200, text=self._torznab_page(100, start=i * 100)) for i in range(3)]

        with patch('httpx.AsyncClient') as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=pages)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            asyncio.run(c.search_existing(meta, 'nodisc'))

        offsets = [ca.kwargs['params'].get('offset') for ca in mock_client.get.call_args_list]
        assert offsets == ['0', '100', '200'], f"Expected three paginated calls capped at 300, got offsets {offsets}"
        assert all(ca.kwargs['params'].get('limit') == '100' for ca in mock_client.get.call_args_list)

    def test_search_short_page_stops_pagination(self):
        """A page smaller than the page size must not trigger another request."""
        c = C411(_config())
        meta = _meta_base(tmdb='', imdb_id=0)

        short_page = MagicMock(status_code=200, text=self._torznab_page(3))

        with patch('httpx.AsyncClient') as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=short_page)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            asyncio.run(c.search_existing(meta, 'nodisc'))

        assert mock_client.get.call_count == 1

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


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  _get_mediainfo_text fallback tests
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestC411GetMediainfoText:
    """Test _get_mediainfo_text with file-based and meta fallback."""

    def test_reads_cleanpath_file(self, tmp_path):
        """Prefers MEDIAINFO_CLEANPATH.txt when it exists."""
        c = C411(_config())
        tmpdir = tmp_path / "tmp" / "test-uuid"
        tmpdir.mkdir(parents=True)
        (tmpdir / "MEDIAINFO_CLEANPATH.txt").write_text("clean MI content")
        (tmpdir / "MEDIAINFO.txt").write_text("raw MI content")

        meta = _meta_base(base_dir=str(tmp_path), uuid="test-uuid")
        result = asyncio.run(c._get_mediainfo_text(meta))
        assert result == "clean MI content"

    def test_reads_mediainfo_file(self, tmp_path):
        """Falls back to MEDIAINFO.txt when CLEANPATH missing."""
        c = C411(_config())
        tmpdir = tmp_path / "tmp" / "test-uuid"
        tmpdir.mkdir(parents=True)
        (tmpdir / "MEDIAINFO.txt").write_text("raw MI content")

        meta = _meta_base(base_dir=str(tmp_path), uuid="test-uuid")
        result = asyncio.run(c._get_mediainfo_text(meta))
        assert result == "raw MI content"

    def test_reads_bdinfo_file(self, tmp_path):
        """Falls back to BD_SUMMARY_00.txt for disc releases."""
        c = C411(_config())
        tmpdir = tmp_path / "tmp" / "test-uuid"
        tmpdir.mkdir(parents=True)
        (tmpdir / "BD_SUMMARY_00.txt").write_text("BD summary content")

        meta = _meta_base(base_dir=str(tmp_path), uuid="test-uuid", bdinfo={"some": "data"})
        result = asyncio.run(c._get_mediainfo_text(meta))
        assert result == "BD summary content"

    def test_fallback_to_meta_mediainfo_text(self, tmp_path):
        """Falls back to meta['mediainfo_text'] when no files exist."""
        c = C411(_config())
        tmpdir = tmp_path / "tmp" / "test-uuid"
        tmpdir.mkdir(parents=True)

        meta = _meta_base(base_dir=str(tmp_path), uuid="test-uuid")
        meta["mediainfo_text"] = "in-memory MI from prep"
        result = asyncio.run(c._get_mediainfo_text(meta))
        assert result == "in-memory MI from prep"

    def test_returns_empty_when_nothing_available(self, tmp_path):
        """Returns empty string when no files and no meta fallback."""
        c = C411(_config())
        tmpdir = tmp_path / "tmp" / "test-uuid"
        tmpdir.mkdir(parents=True)

        meta = _meta_base(base_dir=str(tmp_path), uuid="test-uuid")
        result = asyncio.run(c._get_mediainfo_text(meta))
        assert result == ""

    def test_skips_empty_files(self, tmp_path):
        """Skips files that exist but are empty/whitespace-only."""
        c = C411(_config())
        tmpdir = tmp_path / "tmp" / "test-uuid"
        tmpdir.mkdir(parents=True)
        (tmpdir / "MEDIAINFO_CLEANPATH.txt").write_text("   \n  ")
        (tmpdir / "MEDIAINFO.txt").write_text("")

        meta = _meta_base(base_dir=str(tmp_path), uuid="test-uuid")
        meta["mediainfo_text"] = "fallback MI"
        result = asyncio.run(c._get_mediainfo_text(meta))
        assert result == "fallback MI"


# ─── Slot: ISO ────────────────────────────────────────────────


class TestSlotISO:
    """PURE-UHD-ISO and PURE-BD-ISO slots."""

    def test_iso_uhd_from_meta(self):
        c = C411(_config())
        meta = _meta_base(type='DISC', is_disc='ISO', resolution='2160p')
        meta['uhd'] = 'UHD'
        slot = c._determine_c411_slot(meta)
        assert slot == 'PURE-UHD-ISO'

    def test_iso_bd_from_meta(self):
        c = C411(_config())
        meta = _meta_base(type='DISC', is_disc='ISO', resolution='1080p')
        slot = c._determine_c411_slot(meta)
        assert slot == 'PURE-BD-ISO'

    def test_iso_uhd_from_name(self):
        slot = C411._determine_c411_slot_from_name('Movie.2024.2160p.UHD.BluRay.ISO.DTS-HD.MA.7.1-GRP')
        assert slot == 'PURE-UHD-ISO'

    def test_iso_bd_from_name(self):
        slot = C411._determine_c411_slot_from_name('Movie.2024.1080p.BluRay.ISO.DTS-HD.MA.5.1-GRP')
        assert slot == 'PURE-BD-ISO'

    def test_bdmv_not_matched_as_iso(self):
        slot = C411._determine_c411_slot_from_name('Movie.2024.2160p.UHD.BDMV.DTS-HD.MA.7.1-GRP')
        assert slot == 'PURE-UHD-BDMV'

    def test_iso_not_matched_in_word(self):
        """'ISO' embedded in another word (e.g. ISOLATION) should NOT match as ISO disc."""
        slot = C411._determine_c411_slot_from_name('Isolation.2024.1080p.WEB-DL.AAC.2.0.H.264-GRP')
        assert slot == 'COMPAT-WR'

    def test_iso_not_matched_mid_name(self):
        """'ISO' as a prefix inside a mid-name token (e.g. .Isolated.) must NOT match."""
        slot = C411._determine_c411_slot_from_name('Movie.Isolated.2024.2160p.UHD.WEB-DL.AAC.2.0.H.264-GRP')
        assert slot != 'PURE-UHD-ISO'

    def test_web_in_title_not_treated_as_web_source(self):
        """'WEB' appearing only in the movie title must not be confused with WEB source.
        Regression: '.WEB.' in 'Spider.s.Web.2018' was triggering is_web=True and
        producing a WR slot for what is actually a BluRay release.
        """
        slot = C411._determine_c411_slot_from_name(
            "The.Girl.in.the.Spider.s.Web.2018.1080p.BluRay.REMUX.AC3.5.1-GRP"
        )
        assert "WR" not in slot, f"WEB in title should not produce a WR slot, got: {slot}"
        assert slot == "PURE-BD-REMUX"


# ─── Slot: AD special edition ────────────────────────────────


class TestSlotADEdition:
    """AD (Audio Description) as a special edition with independent slot set."""

    def test_ad_from_meta(self):
        c = C411(_config())
        meta = _meta_base(edition='AD', resolution='1080p')
        slot = c._determine_c411_slot(meta)
        assert slot == 'AD|COMPAT-WR'

    def test_ad_from_name(self):
        # "AD" is intentionally skipped in name-based detection (too ambiguous as a token).
        # Only meta-based detection sets the AD edition prefix.
        slot = C411._determine_c411_slot_from_name('Movie.2024.AD.FRENCH.1080p.WEB.x264-GRP')
        assert slot == 'COMPAT-WR'

    def test_ad_not_in_word(self):
        """AD embedded in another word should NOT trigger special edition."""
        slot = C411._determine_c411_slot_from_name('Adrenaline.2024.FRENCH.1080p.WEB.x264-GRP')
        assert slot == 'COMPAT-WR'

    def test_ad_4k_remux(self):
        c = C411(_config())
        meta = _meta_base(edition='AD', type='REMUX', resolution='2160p')
        meta['uhd'] = 'UHD'
        slot = c._determine_c411_slot(meta)
        assert slot == 'AD|PURE-UHD-REMUX'


class TestSlotHybridEdition:
    """Hybrid lives in meta['webdv'], but the name parser sees a HYBRID token —
    both slot paths must agree, else a Hybrid release fails to match its dupe."""

    def test_hybrid_from_webdv_meta(self):
        c = C411(_config())
        meta = _meta_base(
            type='ENCODE', resolution='2160p', source='BluRay', video_encode='x265',
            hdr='DV HDR', audio='TrueHD Atmos 7.1',
            uuid='Solo.2018.2160p.4KLight.BluRay.x265-QTZ.mkv',
        )
        meta['webdv'] = 'Hybrid'
        assert c._detect_special_edition_from_meta(meta) == 'HYBRID'
        assert c._determine_c411_slot(meta).startswith('HYBRID|')

    def test_hybrid_meta_slot_matches_name_slot(self):
        c = C411(_config())
        meta = _meta_base(
            type='ENCODE', resolution='2160p', source='BluRay', video_encode='x265',
            hdr='DV HDR', audio='TrueHD Atmos 7.1',
            uuid='Solo.2018.2160p.4KLight.BluRay.x265-QTZ.mkv',
        )
        meta['webdv'] = 'Hybrid'
        dupe = 'Solo.A.Star.Wars.Story.2018.Hybrid.MULTI.VFF.2160p.BluRay.4KLight.DV.HDR10.TrueHD.Atmos.7.1.x265-QTZ'
        assert c._determine_c411_slot(meta) == c._determine_c411_slot_from_name(dupe)

    def test_no_webdv_no_hybrid_prefix(self):
        c = C411(_config())
        meta = _meta_base(
            type='ENCODE', resolution='2160p', source='BluRay', video_encode='x265',
            hdr='DV HDR', audio='TrueHD Atmos 7.1',
            uuid='Solo.2018.2160p.4KLight.BluRay.x265-QTZ.mkv',
        )
        assert not c._determine_c411_slot(meta).startswith('HYBRID|')


# ─── Lossy / Lossless coexistence ────────────────────────────


class TestLossyLosslessCoexistence:
    """Lossy and lossless versions permanently coexist in the same slot."""

    TORZNAB_LOSSLESS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:torznab="http://torznab.com/schemas/2015/feed">
  <channel>
    <item>
      <title>Movie.2024.FRENCH.2160p.UHD.BluRay.REMUX.DTS-HD.MA.7.1-GRP</title>
      <guid>https://c411.org/torrents/200</guid>
      <link>https://c411.org/torrents/200/download</link>
      <size>40000000000</size>
    </item>
  </channel>
</rss>"""

    TORZNAB_LOSSY = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:torznab="http://torznab.com/schemas/2015/feed">
  <channel>
    <item>
      <title>Movie.2024.FRENCH.2160p.UHD.BluRay.REMUX.AC3.5.1-GRP</title>
      <guid>https://c411.org/torrents/201</guid>
      <link>https://c411.org/torrents/201/download</link>
      <size>30000000000</size>
    </item>
  </channel>
</rss>"""

    TORZNAB_BOTH = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:torznab="http://torznab.com/schemas/2015/feed">
  <channel>
    <item>
      <title>Movie.2024.FRENCH.2160p.UHD.BluRay.REMUX.DTS-HD.MA.7.1-GRP</title>
      <guid>https://c411.org/torrents/200</guid>
      <link>https://c411.org/torrents/200/download</link>
      <size>40000000000</size>
    </item>
    <item>
      <title>Movie.2024.FRENCH.2160p.UHD.BluRay.REMUX.AC3.5.1-GRP2</title>
      <guid>https://c411.org/torrents/201</guid>
      <link>https://c411.org/torrents/201/download</link>
      <size>30000000000</size>
    </item>
  </channel>
</rss>"""

    def _make_mock(self, xml_text):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = xml_text
        return mock_response

    def test_lossy_upload_lossless_dupe_coexist(self):
        """A lossy upload should NOT be blocked by a lossless dupe in the same slot."""
        c = C411(_config())
        meta = _meta_base(
            type='REMUX', resolution='2160p', audio='AC3',
            video_encode='', hdr='',
        )
        meta['uhd'] = 'UHD'
        meta['is_disc'] = None

        with patch('httpx.AsyncClient') as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=self._make_mock(self.TORZNAB_LOSSLESS))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_cls.return_value = mock_client

            dupes = asyncio.run(c.search_existing(meta, 'nodisc'))

        assert dupes == [], "Lossy upload should coexist with lossless dupe"

    def test_lossless_upload_lossy_dupe_coexist(self):
        """A lossless upload should NOT be blocked by a lossy dupe in the same slot."""
        c = C411(_config())
        meta = _meta_base(
            type='REMUX', resolution='2160p', audio='DTS-HD MA',
            video_encode='', hdr='',
        )
        meta['uhd'] = 'UHD'
        meta['is_disc'] = None

        with patch('httpx.AsyncClient') as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=self._make_mock(self.TORZNAB_LOSSY))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_cls.return_value = mock_client

            dupes = asyncio.run(c.search_existing(meta, 'nodisc'))

        assert dupes == [], "Lossless upload should coexist with lossy dupe"

    def test_lossless_upload_lossless_dupe_blocks(self):
        """A lossless upload should be blocked by an existing lossless dupe."""
        c = C411(_config())
        meta = _meta_base(
            type='REMUX', resolution='2160p', audio='DTS-HD MA',
            video_encode='', hdr='',
        )
        meta['uhd'] = 'UHD'
        meta['is_disc'] = None

        with patch('httpx.AsyncClient') as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=self._make_mock(self.TORZNAB_LOSSLESS))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_cls.return_value = mock_client

            dupes = asyncio.run(c.search_existing(meta, 'nodisc'))

        assert len(dupes) == 1, "Lossless upload should be blocked by lossless dupe"

    def test_lossy_upload_lossy_dupe_blocks(self):
        """A lossy upload should be blocked by an existing lossy dupe."""
        c = C411(_config())
        meta = _meta_base(
            type='REMUX', resolution='2160p', audio='AC3',
            video_encode='', hdr='',
        )
        meta['uhd'] = 'UHD'
        meta['is_disc'] = None

        with patch('httpx.AsyncClient') as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=self._make_mock(self.TORZNAB_LOSSY))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_cls.return_value = mock_client

            dupes = asyncio.run(c.search_existing(meta, 'nodisc'))

        assert len(dupes) == 1, "Lossy upload should be blocked by lossy dupe"

    def test_lossy_upload_mixed_dupes_filters_lossless(self):
        """When both lossy and lossless dupes exist, only same-type blocks."""
        c = C411(_config())
        meta = _meta_base(
            type='REMUX', resolution='2160p', audio='AC3',
            video_encode='', hdr='',
        )
        meta['uhd'] = 'UHD'
        meta['is_disc'] = None

        with patch('httpx.AsyncClient') as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=self._make_mock(self.TORZNAB_BOTH))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_cls.return_value = mock_client

            dupes = asyncio.run(c.search_existing(meta, 'nodisc'))

        assert len(dupes) == 1, "Only same audio type should block"
        assert 'AC3' in dupes[0]['name']

    def test_is_lossless_from_name_truehd(self):
        assert C411._is_lossless_from_name('Movie.2024.1080p.BluRay.REMUX.TrueHD.7.1-GRP') is True

    def test_is_lossless_from_name_dtshd_ma(self):
        assert C411._is_lossless_from_name('Movie.2024.1080p.BluRay.REMUX.DTS-HD.MA.5.1-GRP') is True

    def test_is_lossless_from_name_flac(self):
        assert C411._is_lossless_from_name('Movie.2024.1080p.BluRay.REMUX.FLAC.2.0-GRP') is True

    def test_is_lossless_from_name_ac3_is_lossy(self):
        assert C411._is_lossless_from_name('Movie.2024.1080p.BluRay.REMUX.AC3.5.1-GRP') is False

    def test_is_lossless_from_name_aac_is_lossy(self):
        assert C411._is_lossless_from_name('Movie.2024.1080p.WEB-DL.AAC.2.0.H.264-GRP') is False

    def test_is_lossless_from_name_remux_no_audio_token(self):
        """A REMUX name with no explicit audio tag falls back to False (unknown).
        REMUX releases should always have audio in the name; BDMV/ISO are the ones
        that legitimately omit audio tokens and are treated as lossless.
        """
        assert C411._is_lossless_from_name('Movie.2024.2160p.UHD.BluRay.REMUX.H265-GRP') is False

    def test_is_lossless_from_name_bdmv_no_audio_token(self):
        """A BDMV name with no explicit audio tag is treated as lossless (PURE disc)."""
        assert C411._is_lossless_from_name('Movie.2024.2160p.UHD.BDMV-GRP') is True

    def test_is_lossless_from_name_iso_no_audio_token(self):
        """An ISO name with no explicit audio tag is treated as lossless (PURE disc)."""
        assert C411._is_lossless_from_name('Movie.2024.2160p.UHD.BluRay.ISO-GRP') is True

    def test_is_lossless_from_name_complete_bluray_no_audio_token(self):
        """A COMPLETE.BLURAY name with no explicit audio tag is treated as lossless."""
        assert C411._is_lossless_from_name('Movie.2024.Complete.Bluray-GRP') is True

    def test_pure_bdmv_dupe_not_filtered_when_upload_is_lossless(self):
        """A lossless BDMV upload must NOT silently drop a PURE-BD-BDMV dupe whose
        name has no explicit audio token (disc images rarely include audio in the name).
        Before the fix, _is_lossless_from_name returned False for such names, causing
        the dupe to be incorrectly filtered by the lossy/lossless coexistence check.
        """
        c = C411(_config())
        # Upload is a PURE-BD-BDMV (is_disc=BDMV, 1080p, lossless audio from meta)
        meta = _meta_base(
            type='DISC', resolution='1080p', audio='DTS-HD MA',
            video_encode='', hdr='',
        )
        meta['is_disc'] = 'BDMV'

        # Dupe is another BDMV in the same slot but without any audio token in the name
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:torznab="http://torznab.com/schemas/2015/feed">
  <channel>
    <item>
      <title>Movie.2024.FRENCH.1080p.BDMV-GRP</title>
      <guid>https://c411.org/torrents/300</guid>
      <link>https://c411.org/torrents/300/download</link>
      <size>50000000000</size>
    </item>
  </channel>
</rss>"""

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = xml

        with patch('httpx.AsyncClient') as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_cls.return_value = mock_client

            dupes = asyncio.run(c.search_existing(meta, 'nodisc'))

        assert len(dupes) == 1, "PURE-BD-BDMV dupe must not be silently dropped by lossless filter"

    def test_vostfr_lossless_upload_sees_multi_lossy_dupe(self):
        """A lossless VOSTFR upload must NOT silently drop a lossy MULTI dupe.
        Regression: the lossless/lossy coexistence filter removed EAC3 releases before
        _check_french_lang_dupes could flag them as french_lang_supersede.
        """
        c = C411(_config())
        meta = _meta_base(
            type='WEBDL', resolution='2160p', audio='TrueHD Atmos 7.1',
            video_encode='H.265', hdr='DV HDR10+',
            mediainfo=_mi([_audio_track('en')], [_sub_track('fr')]),
            original_language='en',
        )
        meta['is_disc'] = None
        meta['uhd'] = ''

        # Existing release: MULTI (FR audio, level 3+), lossy EAC3, same WR+DV slot
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:torznab="http://torznab.com/schemas/2015/feed">
  <channel>
    <item>
      <title>Le.Prenom.2012.MULTI.VFF.2160p.WEB.ATMOS.DV.HDR10Plus.EAC3.5.1.H265-GRP</title>
      <guid>https://c411.org/torrents/999</guid>
      <link>https://c411.org/torrents/999/download</link>
      <size>15000000000</size>
    </item>
  </channel>
</rss>"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = xml

        with patch('httpx.AsyncClient') as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_cls.return_value = mock_client

            dupes = asyncio.run(c.search_existing(meta, 'nodisc'))

        assert len(dupes) == 1, "MULTI EAC3 dupe must survive lossless filter when upload is VOSTFR"
        assert 'french_lang_supersede' in (dupes[0].get('flags') or []), "Dupe must be flagged as french_lang_supersede"


# ─── AD false positive: Ad.Astra regression ──────────────────


class TestADFalsePositiveRegression:
    """'AD' in a title like 'Ad.Astra' must NOT be detected as the Audio Description edition."""

    def test_ad_astra_no_edition(self):
        edition = C411._detect_special_edition_from_name(
            'Ad.Astra.2019.2160p.UHD.BluRay.TrueHD.7.1.Atmos.HDR.H.265-GRP'
        )
        assert edition != 'AD', f"'Ad.Astra' must not trigger AD edition, got {edition!r}"

    def test_ad_astra_slot_has_no_prefix(self):
        slot = C411._determine_c411_slot_from_name(
            'Ad.Astra.2019.2160p.UHD.BluRay.TrueHD.7.1.Atmos.HDR.H.265-GRP'
        )
        assert not slot.startswith('AD|'), f"Ad.Astra slot must not start with 'AD|', got {slot!r}"

    def test_ad_from_meta_still_works(self):
        """meta-based AD detection must still work after the name-based guard."""
        c = C411(_config())
        meta = _meta_base(edition='AD', resolution='1080p')
        slot = c._determine_c411_slot(meta)
        assert slot == 'AD|COMPAT-WR'


# ═══════════════════════════════════════════════════════════════
#  Notag — tag replacement in FrenchTrackerMixin.get_name()
# ═══════════════════════════════════════════════════════════════


class TestFrenchMixinNotagGetName:
    """Tag replacement in FrenchTrackerMixin.get_name() (used by C411, V3X, etc.)."""

    @pytest.fixture
    def c411(self):
        return C411(config=_config())

    def _base_meta(self, **overrides):
        m = {
            "category": "MOVIE",
            "type": "WEBDL",
            "title": "Le Prenom",
            "year": "2012",
            "resolution": "1080p",
            "source": "WEB",
            "audio": "AC3",
            "video_encode": "x264",
            "service": "",
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
            "imdb_info": {"aka": "", "original_language": "fr"},
            "mediainfo": {},
            "audio_languages": ["French"],
            "subtitle_languages": [],
        }
        m.update(overrides)
        return m

    def test_valid_tag_unchanged(self, c411):
        """A valid tag like '-Troxy' should remain as-is."""
        meta = self._base_meta(tag="-Troxy")
        result = _run_async(c411.get_name(meta))
        assert result["name"].endswith("-Troxy")

    def test_empty_tag_replaced(self, c411):
        """Empty tag '' should be replaced with NOTAG."""
        meta = self._base_meta(tag="")
        result = _run_async(c411.get_name(meta))
        assert result["name"].endswith("-NOTAG")

    def test_dash_only_tag_replaced(self, c411):
        """Tag '-' (dash only, empty group) should be replaced with NOTAG."""
        meta = self._base_meta(tag="-")
        result = _run_async(c411.get_name(meta))
        assert result["name"].endswith("-NOTAG")

    def test_nogrp_tag_replaced(self, c411):
        """Tag '-NOGRP' should be replaced with NOTAG."""
        meta = self._base_meta(tag="-NOGRP")
        result = _run_async(c411.get_name(meta))
        assert "-NOGRP" not in result["name"]
        assert result["name"].endswith("-NOTAG")

    def test_nogroup_tag_replaced(self, c411):
        """Tag '-NOGROUP' should be replaced."""
        meta = self._base_meta(tag="-NOGROUP")
        result = _run_async(c411.get_name(meta))
        assert "-NOGROUP" not in result["name"]
        assert result["name"].endswith("-NOTAG")

    def test_unknown_tag_replaced(self, c411):
        """Tag '-Unknown' should be replaced."""
        meta = self._base_meta(tag="-Unknown")
        result = _run_async(c411.get_name(meta))
        assert "-Unknown" not in result["name"]
        assert result["name"].endswith("-NOTAG")


# ═══════════════════════════════════════════════════════════════
#  Language requirement — get_additional_checks()
# ═══════════════════════════════════════════════════════════════


class TestFrenchLanguageCheck:
    """French language requirement in FrenchTrackerMixin.get_additional_checks()."""

    @pytest.fixture
    def c411(self):
        return C411(config=_config())

    def test_french_audio_passes(self, c411):
        meta = {
            "audio_languages": ["French"],
            "subtitle_languages": [],
            "is_disc": None,
            "debug": False,
            "unattended": True,
        }
        with patch("src.trackers.COMMON.languages_manager") as mock_lm:
            mock_lm.process_desc_language = AsyncMock()
            assert _run_async(c411.get_additional_checks(meta)) is True

    def test_french_subtitle_passes(self, c411):
        meta = {
            "audio_languages": ["English"],
            "subtitle_languages": ["French"],
            "is_disc": None,
            "debug": False,
            "unattended": True,
        }
        with patch("src.trackers.COMMON.languages_manager") as mock_lm:
            mock_lm.process_desc_language = AsyncMock()
            assert _run_async(c411.get_additional_checks(meta)) is True

    def test_no_french_at_all_fails(self, c411):
        meta = {
            "audio_languages": ["English"],
            "subtitle_languages": ["English"],
            "is_disc": None,
            "debug": False,
            "unattended": True,
        }
        with patch("src.trackers.COMMON.languages_manager") as mock_lm:
            mock_lm.process_desc_language = AsyncMock()
            assert _run_async(c411.get_additional_checks(meta)) is False

    def test_empty_audio_languages_with_french_subs(self, c411):
        meta = {
            "audio_languages": [],
            "subtitle_languages": ["French"],
            "is_disc": None,
            "debug": False,
            "unattended": True,
        }
        with patch("src.trackers.COMMON.languages_manager") as mock_lm:
            mock_lm.process_desc_language = AsyncMock()
            assert _run_async(c411.get_additional_checks(meta)) is True

    def test_missing_audio_languages_key(self, c411):
        meta = {
            "subtitle_languages": ["French"],
            "is_disc": None,
            "debug": False,
            "unattended": True,
        }
        with patch("src.trackers.COMMON.languages_manager") as mock_lm:
            mock_lm.process_desc_language = AsyncMock()
            assert _run_async(c411.get_additional_checks(meta)) is True

    def test_missing_subtitle_languages_key(self, c411):
        meta = {
            "audio_languages": ["French"],
            "is_disc": None,
            "debug": False,
            "unattended": True,
        }
        with patch("src.trackers.COMMON.languages_manager") as mock_lm:
            mock_lm.process_desc_language = AsyncMock()
            assert _run_async(c411.get_additional_checks(meta)) is True

    def test_both_languages_missing_fails(self, c411):
        meta = {
            "is_disc": None,
            "debug": False,
            "unattended": True,
        }
        with patch("src.trackers.COMMON.languages_manager") as mock_lm:
            mock_lm.process_desc_language = AsyncMock()
            assert _run_async(c411.get_additional_checks(meta)) is False

    def test_french_variant_fra_passes(self, c411):
        meta = {
            "audio_languages": ["fra"],
            "subtitle_languages": [],
            "is_disc": None,
            "debug": False,
            "unattended": True,
        }
        with patch("src.trackers.COMMON.languages_manager") as mock_lm:
            mock_lm.process_desc_language = AsyncMock()
            assert _run_async(c411.get_additional_checks(meta)) is True

    def test_french_variant_fr_passes(self, c411):
        meta = {
            "audio_languages": ["fr"],
            "subtitle_languages": [],
            "is_disc": None,
            "debug": False,
            "unattended": True,
        }
        with patch("src.trackers.COMMON.languages_manager") as mock_lm:
            mock_lm.process_desc_language = AsyncMock()
            assert _run_async(c411.get_additional_checks(meta)) is True

    def test_empty_both_lists_fails(self, c411):
        meta = {
            "audio_languages": [],
            "subtitle_languages": [],
            "is_disc": None,
            "debug": False,
            "unattended": True,
        }
        with patch("src.trackers.COMMON.languages_manager") as mock_lm:
            mock_lm.process_desc_language = AsyncMock()
            assert _run_async(c411.get_additional_checks(meta)) is False


class TestC411SearchExistingLanguageGate:
    """search_existing() skips C411 when no French audio/subtitle."""

    def test_skips_when_no_french(self):
        c411 = C411(config=_config())
        meta = {
            "audio_languages": ["English"],
            "subtitle_languages": ["English"],
            "is_disc": None,
            "debug": False,
            "unattended": True,
            "tracker_status": {},
            "skipping": None,
            "imdb_id": "tt1234567",
        }
        with patch("src.trackers.COMMON.languages_manager") as mock_lm:
            mock_lm.process_desc_language = AsyncMock()
            dupes = _run_async(c411.search_existing(meta, ""))
        assert dupes == []
        assert meta["skipping"] == "C411"


# ═══════════════════════════════════════════════════════════════
#  Nogroup WEB-DL naming — regression for Cyclo-style filenames
# ═══════════════════════════════════════════════════════════════


class TestNogroupWebDL:
    """WEB-DL releases without a group tag must use C411's notag_label.

    C411 uses notag_label='NOTAG'.
    Regression: Cyclo.1995.1080p.WEB-DL.AAC.2.0.H.264.mkv had a false
    group '-DL.AAC.2.0.H.264' extracted, producing duplicated tokens.
    """

    def _get_name(self, meta: dict) -> str:
        from src.trackers.C411 import C411
        return _run_async(C411(_config()).get_name(meta))['name']

    def test_empty_tag_uses_notag_label(self):
        """tag='' (nogroup) must produce a name ending with '-NOTAG'."""
        meta = _meta_base(
            title='Cyclo',
            year='1995',
            audio='AAC 2.0',
            video_encode='H.264',
            video_codec='H.264',
            tag='',
            has_encode_settings=False,
        )
        name = self._get_name(meta)
        assert name.endswith('-NOTAG'), f"Expected -NOTAG suffix, got: {name!r}"

    def test_no_audio_duplication(self):
        """Audio token must appear exactly once — no duplication from a false tag."""
        meta = _meta_base(
            title='Cyclo',
            year='1995',
            audio='AAC 2.0',
            video_encode='H.264',
            video_codec='H.264',
            tag='',
            has_encode_settings=False,
        )
        name = self._get_name(meta)
        assert name.count('AAC') == 1, (
            f"Audio token 'AAC' duplicated in name: {name!r}."
        )

    def test_real_group_preserved(self):
        """A real group tag must not be replaced by the notag label."""
        meta = _meta_base(
            title='Cyclo',
            year='1995',
            audio='AAC 2.0',
            video_encode='H.264',
            video_codec='H.264',
            tag='-FRiENDS',
            has_encode_settings=False,
        )
        name = self._get_name(meta)
        assert name.endswith('-FRiENDS'), f"Expected -FRiENDS suffix, got: {name!r}"


# ═══════════════════════════════════════════════════════════════
#  Criterion Collection edition stripping
# ═══════════════════════════════════════════════════════════════


class TestC411CriterionStripping:
    """C411's server rejects 'CRITERION' as a banned streaming-platform token.

    Regression: L'argent.1983.Criterion.1080p.BluRay.FLAC.x264-BMF.mkv
    had edition='Criterion' which landed in the release name and caused a
    server-side upload rejection.  C411.get_name must strip it.
    """

    def _get_name(self, meta: dict) -> str:
        return _run_async(C411(_config()).get_name(meta))['name']

    def test_criterion_edition_stripped(self):
        """edition='Criterion' must be removed from the C411 release name."""
        meta = _meta_base(
            title="L'Argent",
            year='1983',
            type='ENCODE',
            source='BluRay',
            resolution='1080p',
            audio='FLAC',
            video_encode='x264',
            video_codec='H.264',
            edition='Criterion',
            tag='-BMF',
            has_encode_settings=True,
        )
        name = self._get_name(meta)
        assert 'Criterion' not in name, f"'Criterion' must be stripped, got: {name!r}"
        assert 'criterion' not in name.lower(), f"'criterion' must be stripped (case-insensitive), got: {name!r}"

    def test_criterion_collection_stripped(self):
        """edition='Criterion Collection' must also be stripped."""
        meta = _meta_base(
            title="L'Argent",
            year='1983',
            type='ENCODE',
            source='BluRay',
            resolution='1080p',
            audio='FLAC',
            video_encode='x264',
            video_codec='H.264',
            edition='Criterion Collection',
            tag='-BMF',
            has_encode_settings=True,
        )
        name = self._get_name(meta)
        assert 'criterion' not in name.lower(), f"'Criterion Collection' must be stripped, got: {name!r}"

    def test_real_edition_unaffected(self):
        """Other edition tokens (e.g. Director's Cut) must not be stripped."""
        meta = _meta_base(
            title='Blade Runner',
            year='1982',
            type='ENCODE',
            source='BluRay',
            resolution='1080p',
            audio='DTS-HD MA 5.1',
            video_encode='x264',
            video_codec='H.264',
            edition="Director's Cut",
            tag='-GRP',
            has_encode_settings=True,
        )
        name = self._get_name(meta)
        assert 'Director' in name or 'director' in name.lower(), (
            f"Edition token must be preserved, got: {name!r}"
        )

    def test_criterion_in_title_not_stripped(self):
        """A movie whose title contains 'Criterion' must not be mangled."""
        meta = _meta_base(
            title='Criterion Something',
            year='2000',
            type='ENCODE',
            source='BluRay',
            resolution='1080p',
            audio='FLAC',
            video_encode='x264',
            video_codec='H.264',
            edition='',
            tag='-GRP',
            has_encode_settings=True,
        )
        name = self._get_name(meta)
        assert 'criterion' in name.lower(), (
            f"Title word 'Criterion' must not be stripped, got: {name!r}"
        )


class TestC411ReservedGroups:
    """C411's internal groups may only be uploaded by the teams themselves:
    they sit in banned_groups so check_banned_group blocks them with the
    interactive continue-anyway bypass (and skips C411 when unattended)."""

    RESERVED = [
        "AMEN", "BOUBA", "GL0P", "ENIGMA", "BOUC", "HYPERION", "Xaxou", "J4CK",
        "SpK79", "D4RK", "ACKER", "TLC", "Dramas For Ever", "ZEKEY", "HazzAnim",
        "Archie", "GISMO65", "FIRESOUL64", "FANKAI", "R3DUCT0", "Katairi",
    ]

    def _names(self) -> list[str]:
        tracker = C411(config=_config())
        return [entry[0] if isinstance(entry, list) else entry for entry in tracker.banned_groups]

    def test_reserved_groups_are_listed(self):
        names = self._names()
        for group in self.RESERVED:
            assert group in names, f"{group} missing from C411 banned_groups"

    def test_existing_ban_is_kept(self):
        assert "k0RE" in self._names()

    def test_check_banned_group_blocks_reserved_tag_unattended(self):
        from src.trackersetup import TRACKER_SETUP

        tracker = C411(config=_config())
        setup = TRACKER_SETUP(config=_config())
        meta = {"tag": "-BOUBA", "unattended": True}
        assert asyncio.run(setup.check_banned_group("C411", tracker.banned_groups, meta)) is True

    def test_check_banned_group_matches_dotted_multiword_tag(self):
        from src.trackersetup import TRACKER_SETUP

        tracker = C411(config=_config())
        setup = TRACKER_SETUP(config=_config())
        meta = {"tag": "-Dramas.For.Ever", "unattended": True}
        assert asyncio.run(setup.check_banned_group("C411", tracker.banned_groups, meta)) is True


# ─── Same-infohash dupe detection ─────────────────────────────


class TestProspectiveInfohash:
    def _base_torrent(self, tmp_path):
        from torf import Torrent

        uuid = "Movie.2024.1080p.BluRay.REMUX.AVC-GRP"
        content = tmp_path / "content" / uuid
        content.mkdir(parents=True)
        (content / "movie.mkv").write_bytes(b"x" * 2048)
        t = Torrent(path=str(content), trackers=["https://fake.tracker/announce"], piece_size=16384)
        t.generate()
        out = tmp_path / "tmp" / uuid
        out.mkdir(parents=True)
        t.write(str(out / "BASE.torrent"))
        return uuid

    def test_matches_the_source_flagged_clone(self, tmp_path, monkeypatch):
        from torf import Torrent

        uuid = self._base_torrent(tmp_path)
        c = C411(_config())
        monkeypatch.setattr(c, "_get_nfo_files", lambda meta: [])
        meta = {"base_dir": str(tmp_path), "uuid": uuid}
        expected = Torrent.read(str(tmp_path / "tmp" / uuid / "BASE.torrent"))
        expected.metainfo["info"]["source"] = "C411"
        assert c._prospective_infohash(meta) == str(expected.infohash).lower()

    def test_empty_when_nfo_will_recreate_the_torrent(self, tmp_path, monkeypatch):
        uuid = self._base_torrent(tmp_path)
        c = C411(_config())
        monkeypatch.setattr(c, "_get_nfo_files", lambda meta: ["/release/movie.nfo"])
        assert c._prospective_infohash({"base_dir": str(tmp_path), "uuid": uuid}) == ""

    def test_empty_without_base_torrent(self, tmp_path):
        c = C411(_config())
        assert c._prospective_infohash({"base_dir": str(tmp_path), "uuid": "nope"}) == ""


class TestSameInfohashShortCircuit:
    XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:torznab="http://torznab.com/schemas/2015/feed">
  <channel>
    <item>
      <title>Totally.Different.Name.1954.MULTI.VFF.2160p.WEB.x265-OTHER</title>
      <guid>https://c411.org/torrents/222</guid>
      <link>https://c411.org/torrents/222</link>
      <size>25237757854</size>
      <torznab:attr name="infohash" value="AABBCCDDEEFF00112233445566778899AABBCCDD" />
    </item>
  </channel>
</rss>"""

    def test_parser_captures_infohash(self):
        results = C411._parse_torznab_response(self.XML)
        assert results[0]["infohash"] == "AABBCCDDEEFF00112233445566778899AABBCCDD"

    def test_same_infohash_is_a_definite_dupe_bypassing_filters(self, monkeypatch):
        c = C411(_config())
        meta = _meta_base()

        async def fake_hashless_filters_should_not_matter(*a, **k):
            raise AssertionError("filters must not run after an infohash match")

        monkeypatch.setattr(c, "_prospective_infohash", lambda m: "aabbccddeeff00112233445566778899aabbccdd")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = self.XML

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client
            dupes = asyncio.run(c.search_existing(meta, "nodisc"))

        # The name would fail every relevance/slot filter (different title,
        # resolution, group) — the identical infohash still makes it a dupe.
        assert len(dupes) == 1
        assert dupes[0]["infohash"] == "AABBCCDDEEFF00112233445566778899AABBCCDD"


class TestUploadLosslessClassification:
    def test_remux_with_lossless_track_is_classified_lossless(self):
        # Generic meta audio understates the file ("DD 2.0"); the track-based
        # C411 logic must classify it lossless like the fiche name it creates.
        c = C411(_config())
        meta = {
            "audio": "Dual-Audio DD 2.0",
            "mediainfo": {
                "media": {
                    "track": [
                        {"@type": "General"},
                        {"@type": "Audio", "Format": "DTS", "Format_AdditionalFeatures": "XLL X", "Channels": "6", "Language": "en"},
                        {"@type": "Audio", "Format": "AC-3", "Channels": "2", "Language": "fr"},
                    ]
                }
            },
        }
        audio_str = c._get_audio_for_name(meta)
        assert C411._is_lossless_audio(audio_str), audio_str


class TestCoexistenceUsesTrackAudio:
    """The lossy/lossless coexistence only applies in PURE slots, and must
    classify the upload from its MediaInfo tracks (like the C411 fiche name),
    not from the generic meta audio string."""

    PURE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:torznab="http://torznab.com/schemas/2015/feed">
  <channel>
    <item>
      <title>Le.Prenom.2012.MULTI.VFF.1080p.BluRay.Remux.DTS.HD.MA.5.1.AVC-Other</title>
      <guid>https://c411.org/torrents/301</guid>
      <link>https://c411.org/torrents/301</link>
      <size>25000000000</size>
    </item>
    <item>
      <title>Le.Prenom.2012.MULTI.VFF.1080p.BluRay.Remux.AC3.5.1.AVC-Other2</title>
      <guid>https://c411.org/torrents/302</guid>
      <link>https://c411.org/torrents/302</link>
      <size>18000000000</size>
    </item>
  </channel>
</rss>"""

    COMPAT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:torznab="http://torznab.com/schemas/2015/feed">
  <channel>
    <item>
      <title>Le.Prenom.2012.FRENCH.1080p.WEB.AC3.5.1.x264-Other</title>
      <guid>https://c411.org/torrents/303</guid>
      <link>https://c411.org/torrents/303</link>
      <size>4000000000</size>
    </item>
  </channel>
</rss>"""

    def _search(self, xml: str, **meta_overrides):
        c = C411(_config())
        meta = _meta_base(audio="Dual-Audio DD 2.0", tag="-Other", original_language="en", **meta_overrides)
        meta["mediainfo"] = {
            "media": {
                "track": [
                    {"@type": "General"},
                    {"@type": "Audio", "Format": "DTS", "Format_AdditionalFeatures": "XLL", "Channels": "6", "Language": "en"},
                    {"@type": "Audio", "Format": "AC-3", "Channels": "2", "Language": "fr"},
                ]
            }
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = xml

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client
            return asyncio.run(c.search_existing(meta, "nodisc"))

    def test_pure_slot_lossless_upload_keeps_lossless_dupe_only(self):
        dupes = self._search(self.PURE_XML, type="REMUX", source="BluRay")
        names = " ".join(d.get("name", "") for d in dupes)
        # Track-based classification: the upload is lossless, so the lossless
        # remux blocks it and the lossy remux is removed (PURE coexistence).
        assert "DTS.HD.MA" in names
        assert "AC3.5.1" not in names

    def test_compat_slot_has_no_lossy_lossless_coexistence(self):
        # COMPAT is single occupancy: a lossy occupant blocks even a
        # lossless-audio upload of the same slot.
        dupes = self._search(self.COMPAT_XML)
        names = " ".join(d.get("name", "") for d in dupes)
        assert "AC3.5.1.x264-Other" in names



class TestBonusReleasesAreExcluded:
    """BONUS releases carry only the film's bonus content: they never compete
    with a film upload, and a BONUS upload only competes with other BONUS."""

    XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:torznab="http://torznab.com/schemas/2015/feed">
  <channel>
    <item>
      <title>Le.Prenom.2012.BONUS.VOSTFR.1080p.WEB.AC3.2.0.x264-Other</title>
      <guid>https://c411.org/torrents/501</guid>
      <link>https://c411.org/torrents/501</link>
      <size>4000000000</size>
    </item>
    <item>
      <title>Le.Prenom.2012.FRENCH.1080p.WEB.AC3.5.1.x264-Other2</title>
      <guid>https://c411.org/torrents/502</guid>
      <link>https://c411.org/torrents/502</link>
      <size>8000000000</size>
    </item>
  </channel>
</rss>"""

    def _search(self, **meta_overrides):
        c = C411(_config())
        meta = _meta_base(tag="-Mine", original_language="en", **meta_overrides)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = self.XML

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client
            return asyncio.run(c.search_existing(meta, "nodisc"))

    def test_film_upload_ignores_bonus_releases(self):
        dupes = self._search()
        names = " ".join(d.get("name", "") for d in dupes)
        assert "BONUS" not in names
        assert "FRENCH.1080p" in names

    def test_bonus_upload_only_competes_with_bonus(self):
        dupes = self._search(uuid="Le.Prenom.2012.BONUS.VOSTFR.1080p.WEB.AC3.2.0.x264-Mine")
        names = " ".join(d.get("name", "") for d in dupes)
        assert "BONUS" in names
        assert "FRENCH.1080p.WEB.AC3.5.1" not in names


class TestFrenchPoster:
    def test_description_prefers_french_poster(self, monkeypatch: Any):
        c = C411(_config())

        async def fake_localized(*args: Any, **kwargs: Any) -> dict[str, Any]:
            return {"title": "Un Film", "poster_path": "/frposter.jpg"}

        monkeypatch.setattr(c.tmdb_manager, "get_tmdb_localized_data", fake_localized)
        meta = _meta_base()
        meta["poster"] = "https://image.tmdb.org/t/p/original/default.jpg"
        desc = asyncio.run(c._build_description(meta))
        assert "https://image.tmdb.org/t/p/w500/frposter.jpg" in desc
        assert "default.jpg" not in desc


class TestSourceDescriptionSection:
    """Optional 'Notes de la release d'origine' section from DESCRIPTION.txt."""

    def _desc(self, tmp_path: Any, *, flag: bool, content: str | None) -> str:
        config = _config()
        config["TRACKERS"]["C411"]["include_source_description"] = flag
        c = C411(config)
        uuid = "X"
        if content is not None:
            import pathlib

            d = pathlib.Path(tmp_path) / "tmp" / uuid
            d.mkdir(parents=True, exist_ok=True)
            (d / "DESCRIPTION.txt").write_text(content, encoding="utf-8")
        meta = _meta_base()
        meta.update({"base_dir": str(tmp_path), "uuid": uuid})
        return asyncio.run(c._build_description(meta))

    def test_section_included_when_enabled(self, tmp_path: Any):
        desc = self._desc(tmp_path, flag=True, content="Encoder notes worth keeping.")
        assert "Notes de la release d'origine" in desc
        assert "Encoder notes worth keeping." in desc

    def test_section_absent_by_default(self, tmp_path: Any):
        desc = self._desc(tmp_path, flag=False, content="Encoder notes worth keeping.")
        assert "Notes de la release" not in desc
