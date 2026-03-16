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
