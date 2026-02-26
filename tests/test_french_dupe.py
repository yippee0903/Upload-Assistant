# Tests for French language hierarchy dupe checking
"""
Test suite for the French language hierarchy dupe checking feature.

Covers:
  · _extract_french_lang_tag — tag extraction from release names
  · _check_french_lang_dupes — flagging logic for dupe entries
  · filter_dupes integration — french_lang_supersede flag handling
"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.trackers.FRENCH import (
    FRENCH_LANG_HIERARCHY,
    FrenchTrackerMixin,
    _FRENCH_AUDIO_THRESHOLD,
)
from src.trackers.C411 import C411


def _config() -> dict[str, Any]:
    """Minimal config for C411 (used by shared mixin tests)."""
    return {
        'TRACKERS': {'C411': {'api_key': 'test-key'}},
        'DEFAULT': {'tmdb_api': 'fake'},
    }


# ─── Helpers ──────────────────────────────────────────────────


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


def _meta_base(**overrides: Any) -> dict[str, Any]:
    """Build a base meta dict suitable for French tracker tests."""
    m: dict[str, Any] = {
        'category': 'MOVIE',
        'type': 'WEBDL',
        'title': 'Chainsaw Man The Movie Reze Arc',
        'year': '2025',
        'resolution': '2160p',
        'source': 'WEB',
        'audio': 'DDP5.1',
        'video_encode': 'H265',
        'service': 'NF',
        'tag': '-GROUP',
        'edition': '',
        'repack': '',
        '3D': '',
        'uhd': '',
        'hdr': 'DV HDR10+',
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
        'path': '',
        'name': '',
        'uuid': 'test-uuid',
        'original_language': 'ja',
        'mediainfo': {'media': {'track': []}},
    }
    m.update(overrides)
    return m


def _dupe(name: str, **kw: Any) -> dict[str, Any]:
    """Build a minimal dupe entry."""
    d: dict[str, Any] = {
        'name': name,
        'size': 5_000_000_000,
        'link': f'https://tracker.example/{name}',
        'id': hash(name),
    }
    d.update(kw)
    return d


class _MixinHost(FrenchTrackerMixin):
    """Concrete host class for testing the mixin."""
    WEB_LABEL = 'WEB'


def _mixin() -> _MixinHost:
    return _MixinHost()


# ═══════════════════════════════════════════════════════════════
#   _extract_french_lang_tag
# ═══════════════════════════════════════════════════════════════


class TestExtractFrenchLangTag:
    """Test _extract_french_lang_tag static method."""

    # ── Direct tag names ──

    @pytest.mark.parametrize('name,expected_tag,expected_level', [
        # Standard dot-separated release names
        ('Movie.2025.MULTI.VFF.2160p.WEB.DV.HDR10PLUS.EAC3.5.1.H265-GROUP', 'MULTI', 7),
        ('Movie.2025.MULTi.VFF.1080p.BluRay.x264-GROUP', 'MULTI', 7),
        ('Movie.2025.MULTI.VFQ.2160p.WEB.H265-GROUP', 'MULTI', 7),
        ('Movie.2025.MULTI.VF2.2160p.WEB.H265-GROUP', 'MULTI', 7),
        ('Movie.2025.VFF.1080p.WEB.H264-GROUP', 'VFF', 6),
        ('Movie.2025.VFQ.720p.WEB.H264-GROUP', 'VFQ', 6),
        ('Movie.2025.VF2.1080p.BluRay.x264-GROUP', 'VF2', 6),
        ('Movie.2025.VOF.1080p.WEB.H264-GROUP', 'VOF', 5),
        ('Movie.2025.TRUEFRENCH.1080p.WEB.H264-GROUP', 'TRUEFRENCH', 4),
        ('Movie.2025.FRENCH.1080p.WEB.H264-GROUP', 'FRENCH', 3),
        ('Movie.2025.VOSTFR.2160p.WEB.H265-GROUP', 'VOSTFR', 2),
        ('Movie.2025.VO.2160p.WEB.H265-GROUP', 'VO', 1),
    ])
    def test_standard_release_names(self, name: str, expected_tag: str, expected_level: int):
        tag, level = FrenchTrackerMixin._extract_french_lang_tag(name)
        assert tag == expected_tag
        assert level == expected_level

    # ── MULTI wins over sub-tags ──

    def test_multi_wins_over_vff(self):
        """MULTI.VFF should return MULTI (level 7), not VFF (level 6)."""
        tag, level = FrenchTrackerMixin._extract_french_lang_tag(
            'Movie.2025.MULTI.VFF.2160p.WEB.DV.HDR10PLUS.EAC3.5.1.H265-GROUP'
        )
        assert tag == 'MULTI'
        assert level == 7

    def test_multi_wins_over_vfq(self):
        tag, level = FrenchTrackerMixin._extract_french_lang_tag(
            'Movie.2025.MULTI.VFQ.1080p.WEB.H264-GROUP'
        )
        assert tag == 'MULTI'
        assert level == 7

    def test_multi_wins_over_truefrench(self):
        tag, level = FrenchTrackerMixin._extract_french_lang_tag(
            'Movie.2025.MULTI.TRUEFRENCH.1080p.WEB.H264-GROUP'
        )
        assert tag == 'MULTI'
        assert level == 7

    # ── Boundary matching: no partial matches ──

    def test_vo_not_in_vostfr(self):
        """VO should NOT match inside VOSTFR."""
        tag, level = FrenchTrackerMixin._extract_french_lang_tag(
            'Movie.2025.VOSTFR.2160p.WEB.H265-GROUP'
        )
        assert tag == 'VOSTFR'
        assert level == 2

    def test_vo_not_in_vof(self):
        """VO should NOT match inside VOF."""
        tag, level = FrenchTrackerMixin._extract_french_lang_tag(
            'Movie.2025.VOF.1080p.WEB.H264-GROUP'
        )
        assert tag == 'VOF'
        assert level == 5

    def test_french_not_in_truefrench(self):
        """FRENCH should NOT match inside TRUEFRENCH."""
        tag, level = FrenchTrackerMixin._extract_french_lang_tag(
            'Movie.2025.TRUEFRENCH.1080p.WEB.H264-GROUP'
        )
        assert tag == 'TRUEFRENCH'
        assert level == 4

    # ── No tag detected ──

    def test_no_tag(self):
        """Should return empty tag and level 0 for names without French tags."""
        tag, level = FrenchTrackerMixin._extract_french_lang_tag(
            'Movie.2025.2160p.WEB.DV.HDR10.DDP5.1.H265-GROUP'
        )
        assert tag == ''
        assert level == 0

    # ── Case insensitivity ──

    def test_case_insensitive_multi(self):
        tag, level = FrenchTrackerMixin._extract_french_lang_tag(
            'Movie.2025.MULTi.VFF.1080p.WEB.H264-GROUP'
        )
        assert tag == 'MULTI'
        assert level == 7

    def test_case_insensitive_vostfr(self):
        tag, level = FrenchTrackerMixin._extract_french_lang_tag(
            'Movie.2025.Vostfr.1080p.WEB.H264-GROUP'
        )
        assert tag == 'VOSTFR'
        assert level == 2

    # ── Tags with different separators ──

    def test_space_separated(self):
        tag, level = FrenchTrackerMixin._extract_french_lang_tag(
            'Movie 2025 MULTI VFF 2160p WEB DV HDR10PLUS'
        )
        assert tag == 'MULTI'
        assert level == 7

    def test_hyphen_separated(self):
        tag, level = FrenchTrackerMixin._extract_french_lang_tag(
            'Movie-2025-VOSTFR-2160p-WEB'
        )
        assert tag == 'VOSTFR'
        assert level == 2

    def test_underscore_separated(self):
        tag, level = FrenchTrackerMixin._extract_french_lang_tag(
            'Movie_2025_FRENCH_1080p_WEB'
        )
        assert tag == 'FRENCH'
        assert level == 3

    # ── Tag at boundaries ──

    def test_tag_at_start(self):
        tag, level = FrenchTrackerMixin._extract_french_lang_tag(
            'MULTI.VFF.Movie.2025.2160p'
        )
        assert tag == 'MULTI'
        assert level == 7

    def test_tag_at_end(self):
        tag, level = FrenchTrackerMixin._extract_french_lang_tag(
            'Movie.2025.2160p.WEB.VO'
        )
        assert tag == 'VO'
        assert level == 1

    # ── Hierarchy constant ──

    def test_hierarchy_thresholds(self):
        """All tags with French audio should be >= _FRENCH_AUDIO_THRESHOLD."""
        french_audio_tags = {'MULTI', 'VFF', 'VFQ', 'VF2', 'VOF', 'TRUEFRENCH', 'FRENCH'}
        for t in french_audio_tags:
            assert FRENCH_LANG_HIERARCHY[t] >= _FRENCH_AUDIO_THRESHOLD, f'{t} should be >= threshold'

        no_french_audio_tags = {'VOSTFR', 'VO'}
        for t in no_french_audio_tags:
            assert FRENCH_LANG_HIERARCHY[t] < _FRENCH_AUDIO_THRESHOLD, f'{t} should be < threshold'


# ═══════════════════════════════════════════════════════════════
#   _check_french_lang_dupes
# ═══════════════════════════════════════════════════════════════


class TestCheckFrenchLangDupes:
    """Test the _check_french_lang_dupes async method."""

    # ── Upload has NO French audio (VOSTFR) ──

    def test_vostfr_upload_multi_exists(self):
        """VOSTFR upload + MULTI existing → flag."""
        mixin = _mixin()
        meta = _meta_base(
            mediainfo=_mi([_audio_track('ja')], [_sub_track('fr')]),
            original_language='ja',
        )
        dupes = [
            _dupe('Chainsaw.Man.2025.MULTI.VFF.2160p.WEB.DV.HDR10PLUS.EAC3.5.1.H265-BOUC'),
        ]
        result = asyncio.get_event_loop().run_until_complete(
            mixin._check_french_lang_dupes(dupes, meta)
        )
        assert len(result) == 1
        assert 'french_lang_supersede' in result[0].get('flags', [])

    def test_vostfr_upload_vff_exists(self):
        """VOSTFR upload + VFF existing → flag."""
        mixin = _mixin()
        meta = _meta_base(
            mediainfo=_mi([_audio_track('ja')], [_sub_track('fr')]),
            original_language='ja',
        )
        dupes = [_dupe('Movie.2025.VFF.2160p.WEB.H265-GROUP')]
        result = asyncio.get_event_loop().run_until_complete(
            mixin._check_french_lang_dupes(dupes, meta)
        )
        assert 'french_lang_supersede' in result[0].get('flags', [])

    def test_vostfr_upload_french_exists(self):
        """VOSTFR upload + FRENCH existing → flag (FRENCH has audio)."""
        mixin = _mixin()
        meta = _meta_base(
            mediainfo=_mi([_audio_track('ja')], [_sub_track('fr')]),
            original_language='ja',
        )
        dupes = [_dupe('Movie.2025.FRENCH.1080p.WEB.H264-GROUP')]
        result = asyncio.get_event_loop().run_until_complete(
            mixin._check_french_lang_dupes(dupes, meta)
        )
        assert 'french_lang_supersede' in result[0].get('flags', [])

    def test_vostfr_upload_truefrench_exists(self):
        """VOSTFR upload + TRUEFRENCH existing → flag."""
        mixin = _mixin()
        meta = _meta_base(
            mediainfo=_mi([_audio_track('ja')], [_sub_track('fr')]),
            original_language='ja',
        )
        dupes = [_dupe('Movie.2025.TRUEFRENCH.1080p.WEB.H264-GROUP')]
        result = asyncio.get_event_loop().run_until_complete(
            mixin._check_french_lang_dupes(dupes, meta)
        )
        assert 'french_lang_supersede' in result[0].get('flags', [])

    # ── Upload has NO French audio (VO — empty from _build_audio_string) ──

    def test_vo_upload_multi_exists(self):
        """VO upload (no French subs, no French audio) + MULTI existing → flag."""
        mixin = _mixin()
        meta = _meta_base(
            mediainfo=_mi([_audio_track('en')]),  # English only, no French subs
            original_language='en',
        )
        dupes = [_dupe('Movie.2025.MULTI.VFF.2160p.WEB.H265-GROUP')]
        result = asyncio.get_event_loop().run_until_complete(
            mixin._check_french_lang_dupes(dupes, meta)
        )
        assert 'french_lang_supersede' in result[0].get('flags', [])

    # ── Upload HAS French audio → inferior dupes should be DROPPED ──

    def test_multi_upload_drops_vostfr(self):
        """MULTI upload → VOSTFR dupes should be filtered out, MULTI dupes kept."""
        mixin = _mixin()
        meta = _meta_base(
            mediainfo=_mi([_audio_track('fr-fr'), _audio_track('en')]),
            original_language='en',
        )
        dupes = [
            _dupe('Movie.2025.MULTI.VFF.2160p.WEB.H265-OTHGRP'),
            _dupe('Movie.2025.VOSTFR.2160p.WEB.H265-YETANOTHER'),
        ]
        result = asyncio.get_event_loop().run_until_complete(
            mixin._check_french_lang_dupes(dupes, meta)
        )
        # VOSTFR should be dropped, only MULTI kept
        assert len(result) == 1
        assert result[0]['name'] == 'Movie.2025.MULTI.VFF.2160p.WEB.H265-OTHGRP'

    def test_multi_upload_drops_vo(self):
        """MULTI upload → VO dupes should be filtered out."""
        mixin = _mixin()
        meta = _meta_base(
            mediainfo=_mi([_audio_track('fr-fr'), _audio_track('en')]),
            original_language='en',
        )
        dupes = [
            _dupe('Movie.2025.VO.2160p.WEB.H265-OTHGRP'),
        ]
        result = asyncio.get_event_loop().run_until_complete(
            mixin._check_french_lang_dupes(dupes, meta)
        )
        assert len(result) == 0

    def test_multi_upload_keeps_multi(self):
        """MULTI upload → other MULTI dupes should be kept as real dupes."""
        mixin = _mixin()
        meta = _meta_base(
            mediainfo=_mi([_audio_track('fr-fr'), _audio_track('en')]),
            original_language='en',
        )
        dupes = [
            _dupe('Movie.2025.MULTI.VFF.2160p.WEB.H265-GROUP1'),
            _dupe('Movie.2025.MULTI.VFQ.1080p.WEB.H264-GROUP2'),
        ]
        result = asyncio.get_event_loop().run_until_complete(
            mixin._check_french_lang_dupes(dupes, meta)
        )
        assert len(result) == 2

    def test_multi_upload_keeps_no_tag(self):
        """MULTI upload → dupes with no French tag should be kept (can't determine)."""
        mixin = _mixin()
        meta = _meta_base(
            mediainfo=_mi([_audio_track('fr-fr'), _audio_track('en')]),
            original_language='en',
        )
        dupes = [
            _dupe('Movie.2025.2160p.WEB.DV.HDR10.DDP5.1.H265-GROUP'),
        ]
        result = asyncio.get_event_loop().run_until_complete(
            mixin._check_french_lang_dupes(dupes, meta)
        )
        assert len(result) == 1

    def test_vff_upload_drops_vostfr(self):
        """VFF upload → VOSTFR dupes should be dropped."""
        mixin = _mixin()
        meta = _meta_base(
            mediainfo=_mi([_audio_track('fr-fr')]),
            original_language='en',
        )
        dupes = [
            _dupe('Movie.2025.VOSTFR.1080p.WEB.H264-GROUP'),
            _dupe('Movie.2025.MULTI.VFF.2160p.WEB.H265-GROUP'),
        ]
        result = asyncio.get_event_loop().run_until_complete(
            mixin._check_french_lang_dupes(dupes, meta)
        )
        assert len(result) == 1
        assert 'MULTI' in result[0]['name']

    def test_truefrench_upload_no_flag(self):
        """TRUEFRENCH upload → should NOT flag."""
        mixin = _mixin()
        meta = _meta_base(
            mediainfo=_mi([_audio_track('fr')]),
            original_language='en',
            uuid='Movie.2025.TRUEFRENCH.1080p',
        )
        dupes = [_dupe('Movie.2025.MULTI.VFF.2160p.WEB.H265-GROUP')]
        result = asyncio.get_event_loop().run_until_complete(
            mixin._check_french_lang_dupes(dupes, meta)
        )
        assert 'french_lang_supersede' not in result[0].get('flags', [])

    # ── Existing has no French audio → should NOT flag ──

    def test_vostfr_upload_vostfr_exists_no_flag(self):
        """Same level (both VOSTFR) → should NOT flag."""
        mixin = _mixin()
        meta = _meta_base(
            mediainfo=_mi([_audio_track('ja')], [_sub_track('fr')]),
            original_language='ja',
        )
        dupes = [_dupe('Movie.2025.VOSTFR.2160p.WEB.H265-OTHERGROUP')]
        result = asyncio.get_event_loop().run_until_complete(
            mixin._check_french_lang_dupes(dupes, meta)
        )
        assert 'french_lang_supersede' not in result[0].get('flags', [])

    def test_vostfr_upload_vo_exists_no_flag(self):
        """VOSTFR upload + VO existing → should NOT flag (VO is lower, not higher)."""
        mixin = _mixin()
        meta = _meta_base(
            mediainfo=_mi([_audio_track('ja')], [_sub_track('fr')]),
            original_language='ja',
        )
        dupes = [_dupe('Movie.2025.VO.2160p.WEB.H265-GROUP')]
        result = asyncio.get_event_loop().run_until_complete(
            mixin._check_french_lang_dupes(dupes, meta)
        )
        assert 'french_lang_supersede' not in result[0].get('flags', [])

    def test_vostfr_upload_no_tag_exists_no_flag(self):
        """VOSTFR upload + existing has no French tag → should NOT flag."""
        mixin = _mixin()
        meta = _meta_base(
            mediainfo=_mi([_audio_track('ja')], [_sub_track('fr')]),
            original_language='ja',
        )
        dupes = [_dupe('Movie.2025.2160p.WEB.DV.HDR10.DDP5.1.H265-GROUP')]
        result = asyncio.get_event_loop().run_until_complete(
            mixin._check_french_lang_dupes(dupes, meta)
        )
        assert 'french_lang_supersede' not in result[0].get('flags', [])

    # ── Multiple dupes: mixed flags ──

    def test_mixed_dupes_partial_flag(self):
        """Only dupes with French audio should be flagged."""
        mixin = _mixin()
        meta = _meta_base(
            mediainfo=_mi([_audio_track('ja')], [_sub_track('fr')]),
            original_language='ja',
        )
        dupes = [
            _dupe('Movie.2025.MULTI.VFF.2160p.WEB.H265-GRP1'),
            _dupe('Movie.2025.VOSTFR.1080p.WEB.H264-GRP2'),
            _dupe('Movie.2025.VFQ.2160p.WEB.H265-GRP3'),
        ]
        result = asyncio.get_event_loop().run_until_complete(
            mixin._check_french_lang_dupes(dupes, meta)
        )
        assert 'french_lang_supersede' in result[0].get('flags', [])  # MULTI → flagged
        assert 'french_lang_supersede' not in result[1].get('flags', [])  # VOSTFR → not flagged
        assert 'french_lang_supersede' in result[2].get('flags', [])  # VFQ → flagged

    # ── No dupes → empty return ──

    def test_empty_dupes(self):
        """Empty dupe list should be returned as-is."""
        mixin = _mixin()
        meta = _meta_base(
            mediainfo=_mi([_audio_track('ja')], [_sub_track('fr')]),
            original_language='ja',
        )
        result = asyncio.get_event_loop().run_until_complete(
            mixin._check_french_lang_dupes([], meta)
        )
        assert result == []

    # ── No MediaInfo → should not crash ──

    def test_no_mediainfo(self):
        """If no MediaInfo, _build_audio_string returns '' → treat as VO."""
        mixin = _mixin()
        meta = _meta_base()
        del meta['mediainfo']
        dupes = [_dupe('Movie.2025.MULTI.VFF.2160p.WEB.H265-GROUP')]
        result = asyncio.get_event_loop().run_until_complete(
            mixin._check_french_lang_dupes(dupes, meta)
        )
        # Empty string from _build_audio_string = VO, MULTI exists → flag
        assert 'french_lang_supersede' in result[0].get('flags', [])

    # ── Idempotent: calling twice should not double-add ──

    def test_idempotent(self):
        """Calling _check_french_lang_dupes twice should not duplicate the flag."""
        mixin = _mixin()
        meta = _meta_base(
            mediainfo=_mi([_audio_track('ja')], [_sub_track('fr')]),
            original_language='ja',
        )
        dupes = [_dupe('Movie.2025.MULTI.VFF.2160p.WEB.H265-GROUP')]
        asyncio.get_event_loop().run_until_complete(
            mixin._check_french_lang_dupes(dupes, meta)
        )
        asyncio.get_event_loop().run_until_complete(
            mixin._check_french_lang_dupes(dupes, meta)
        )
        flags = dupes[0].get('flags', [])
        assert flags.count('french_lang_supersede') == 1

    # ── MUET uploads (silent films) → should NOT flag ──

    def test_muet_upload_no_flag(self):
        """MUET upload → special case, should NOT trigger French dupe check."""
        mixin = _mixin()
        meta = _meta_base(
            mediainfo=_mi([]),  # No audio tracks → MUET
            original_language='en',
        )
        dupes = [_dupe('Movie.2025.MULTI.VFF.2160p.WEB.H265-GROUP')]
        result = asyncio.get_event_loop().run_until_complete(
            mixin._check_french_lang_dupes(dupes, meta)
        )
        # MUET films are a special category — don't flag
        assert 'french_lang_supersede' not in result[0].get('flags', [])

    # ── Existing flags preserved ──

    def test_existing_flags_preserved(self):
        """Pre-existing flags on the dupe entry should not be lost."""
        mixin = _mixin()
        meta = _meta_base(
            mediainfo=_mi([_audio_track('ja')], [_sub_track('fr')]),
            original_language='ja',
        )
        dupes = [_dupe('Movie.2025.MULTI.VFF.2160p.WEB.H265-GROUP', flags=['some_other_flag'])]
        result = asyncio.get_event_loop().run_until_complete(
            mixin._check_french_lang_dupes(dupes, meta)
        )
        flags = result[0].get('flags', [])
        assert 'some_other_flag' in flags
        assert 'french_lang_supersede' in flags


# ═══════════════════════════════════════════════════════════════
#   User scenario: Chainsaw Man example from conversation
# ═══════════════════════════════════════════════════════════════


class TestChainsawManScenario:
    """
    Replicate the exact scenario from the user's request:
    Existing:  Chainsaw.Man.The.Movie.Reze.Arc.2025.MULTI.VFF.2160p.WEB.DV.HDR10PLUS.EAC3.5.1.H265-BOUC
    Upload:    Chainsaw.Man.The.Movie.Reze.Arc.2025.REPACK.2160p.MA.WEB-DL.DUAL.DDP5.1.Atmos.DV.HDR10P.H.265-BYNDR.mkv
    Result:    Upload is VOSTFR (Japanese audio + French subs) → existing MULTI should be flagged.
    """

    def test_chainsaw_man_vostfr_vs_multi(self):
        mixin = _mixin()
        # Upload: Japanese audio + French subtitles → VOSTFR
        meta = _meta_base(
            title='Chainsaw Man The Movie Reze Arc',
            year='2025',
            resolution='2160p',
            hdr='DV HDR10+',
            audio='DDP5.1 Atmos',
            video_encode='H265',
            service='MA',
            tag='-BYNDR',
            original_language='ja',
            mediainfo=_mi(
                [_audio_track('ja')],
                [_sub_track('fr')],
            ),
        )

        dupes = [
            _dupe(
                'Chainsaw.Man.The.Movie.Reze.Arc.2025.MULTI.VFF.2160p.WEB.DV.HDR10PLUS.EAC3.5.1.H265-BOUC',
            ),
        ]

        result = asyncio.get_event_loop().run_until_complete(
            mixin._check_french_lang_dupes(dupes, meta)
        )
        assert 'french_lang_supersede' in result[0].get('flags', [])


# ═══════════════════════════════════════════════════════════════
#   filter_dupes integration: french_lang_supersede flag
# ═══════════════════════════════════════════════════════════════


class TestFilterDupesFrenchFlag:
    """Verify that filter_dupes respects the french_lang_supersede flag."""

    def _config(self) -> dict[str, Any]:
        return {
            'TRACKERS': {},
            'DEFAULT': {},
        }

    def test_flagged_dupe_kept_same_resolution(self):
        """A dupe with french_lang_supersede + matching resolution should be kept."""
        from src.dupe_checking import DupeChecker

        checker = DupeChecker(self._config())
        meta: dict[str, Any] = {
            'debug': False,
            'name': 'Chainsaw.Man.2025.VOSTFR.2160p.WEB.DV.HDR10PLUS.DDP5.1.H265-BYNDR',
            'resolution': '2160p',
            'hdr': 'DV HDR10+',
            'type': 'WEBDL',
            'source': 'WEB',
            'is_disc': None,
            'category': 'MOVIE',
            'season': '',
            'episode': '',
            'tag': '-BYNDR',
            'video_encode': 'H265',
            'sd': 0,
            'uuid': 'test-uuid',
            'trumpable_id': None,
            'filelist': [],
        }

        dupes = [
            {
                'name': 'Chainsaw.Man.2025.MULTI.VFF.2160p.WEB.DV.HDR10PLUS.EAC3.5.1.H265-BOUC',
                'size': 5_000_000_000,
                'flags': ['french_lang_supersede'],
                'link': 'https://example.com/123',
                'id': 123,
            },
        ]

        result = asyncio.get_event_loop().run_until_complete(
            checker.filter_dupes(dupes, meta, 'C411')
        )
        # Same resolution → kept as dupe
        assert len(result) == 1
        assert result[0]['name'] == dupes[0]['name']

    def test_unflagged_dupe_normal_processing(self):
        """A dupe WITHOUT french_lang_supersede goes through normal processing."""
        from src.dupe_checking import DupeChecker

        checker = DupeChecker(self._config())
        meta: dict[str, Any] = {
            'debug': False,
            'name': 'Movie.2025.VOSTFR.2160p.WEB.H265-GROUP',
            'resolution': '2160p',
            'hdr': '',
            'type': 'WEBDL',
            'source': 'WEB',
            'is_disc': None,
            'category': 'MOVIE',
            'season': '',
            'episode': '',
            'tag': '-GROUP',
            'video_encode': 'H265',
            'sd': 0,
            'uuid': 'test-uuid',
            'trumpable_id': None,
            'filelist': [],
        }

        # Different resolution, no flag → should be excluded
        dupes = [
            {
                'name': 'Movie.2025.MULTI.VFF.1080p.WEB.H264-OTHER',
                'size': 3_000_000_000,
                'link': 'https://example.com/456',
                'id': 456,
            },
        ]

        result = asyncio.get_event_loop().run_until_complete(
            checker.filter_dupes(dupes, meta, 'C411')
        )
        # Should be excluded (resolution mismatch, no flag to override)
        assert len(result) == 0

    def test_flagged_dupe_excluded_on_resolution_mismatch(self):
        """french_lang_supersede should NOT override a resolution mismatch."""
        from src.dupe_checking import DupeChecker

        checker = DupeChecker(self._config())
        meta: dict[str, Any] = {
            'debug': False,
            'name': 'Movie.2025.VOSTFR.2160p.WEB.H265-GROUP',
            'resolution': '2160p',
            'hdr': '',
            'type': 'WEBDL',
            'source': 'WEB',
            'is_disc': None,
            'category': 'MOVIE',
            'season': '',
            'episode': '',
            'tag': '-GROUP',
            'video_encode': 'H265',
            'sd': 0,
            'uuid': 'test-uuid',
            'trumpable_id': None,
            'filelist': [],
        }

        # Different resolution + french_lang_supersede → should be excluded
        dupes = [
            {
                'name': 'Movie.2025.MULTI.VFF.1080p.WEB.H264-OTHER',
                'size': 3_000_000_000,
                'flags': ['french_lang_supersede'],
                'link': 'https://example.com/789',
                'id': 789,
            },
        ]

        result = asyncio.get_event_loop().run_until_complete(
            checker.filter_dupes(dupes, meta, 'C411')
        )
        # Resolution mismatch → supersede is NOT applied, normal exclusion kicks in
        assert len(result) == 0

    def test_flagged_dupe_matched_reason(self):
        """filter_dupes should set matched_reason to french_lang_supersede."""
        from src.dupe_checking import DupeChecker

        checker = DupeChecker(self._config())
        meta: dict[str, Any] = {
            'debug': False,
            'name': 'Movie.2025.VOSTFR.2160p.WEB.H265-GROUP',
            'resolution': '2160p',
            'hdr': 'DV HDR10+',
            'type': 'WEBDL',
            'source': 'WEB',
            'is_disc': None,
            'category': 'MOVIE',
            'season': '',
            'episode': '',
            'tag': '-GROUP',
            'video_encode': 'H265',
            'sd': 0,
            'uuid': 'test-uuid',
            'trumpable_id': None,
            'filelist': [],
        }

        dupes = [
            {
                'name': 'Movie.2025.MULTI.VFF.2160p.WEB.DV.HDR10PLUS.DDP5.1.H265-BOUC',
                'size': 5_000_000_000,
                'flags': ['french_lang_supersede'],
                'link': 'https://example.com/111',
                'id': 111,
            },
        ]

        asyncio.get_event_loop().run_until_complete(
            checker.filter_dupes(dupes, meta, 'C411')
        )
        assert meta.get('C411_matched_reason') == 'french_lang_supersede'


    def test_flagged_dupe_excluded_on_season_mismatch(self):
        """french_lang_supersede should NOT override a season mismatch for TV."""
        from src.dupe_checking import DupeChecker

        checker = DupeChecker(self._config())
        meta: dict[str, Any] = {
            'debug': False,
            'name': 'The.Bear.2022.S04.VOSTFR.2160p.WEB.DV.HDR.DDP.5.1.H265-FLUX',
            'resolution': '2160p',
            'hdr': 'DV HDR',
            'type': 'WEBDL',
            'source': 'WEB',
            'is_disc': None,
            'category': 'TV',
            'season': 'S04',
            'episode': '',
            'tag': '-FLUX',
            'video_encode': 'H265',
            'sd': 0,
            'uuid': 'test-uuid',
            'trumpable_id': None,
            'filelist': [],
            'tv_pack': 1,
        }

        # Different seasons with french_lang_supersede → should be excluded
        dupes = [
            {
                'name': 'The.Bear.2022.S01.REPACK.MULTI.VFF.2160p.WEBRip.EAC3.5.1.x265-Amen',
                'size': 50_000_000_000,
                'flags': ['french_lang_supersede'],
                'link': 'https://c411.org/torrents/ba23a9a39f3e663f4a47167400cb6aecb75c8059',
                'id': 1001,
            },
            {
                'name': 'The.Bear.2022.S02.MULTI.VFF.2160p.WEBRip.EAC3.5.1.x265-Amen',
                'size': 50_000_000_000,
                'flags': ['french_lang_supersede'],
                'link': 'https://c411.org/torrents/ea436b25de386a03df59e0d906666735c68901c9',
                'id': 1002,
            },
            {
                'name': 'The.Bear.2022.S03.MULTI.VFF.2160p.WEBRip.DV.HDR10.EAC3.5.1.x265-Amen',
                'size': 50_000_000_000,
                'flags': ['french_lang_supersede'],
                'link': 'https://c411.org/torrents/811eebcc501b0780c690ba62f5d240c5ce2cf475',
                'id': 1003,
            },
        ]

        result = asyncio.get_event_loop().run_until_complete(
            checker.filter_dupes(dupes, meta, 'C411')
        )
        # S01/S02/S03 should NOT be dupes for an S04 upload
        assert len(result) == 0

    def test_flagged_dupe_kept_on_matching_season(self):
        """french_lang_supersede + matching season → kept as dupe for TV."""
        from src.dupe_checking import DupeChecker

        checker = DupeChecker(self._config())
        meta: dict[str, Any] = {
            'debug': False,
            'name': 'The.Bear.2022.S04.VOSTFR.2160p.WEB.DV.HDR.DDP.5.1.H265-FLUX',
            'resolution': '2160p',
            'hdr': 'DV HDR',
            'type': 'WEBDL',
            'source': 'WEB',
            'is_disc': None,
            'category': 'TV',
            'season': 'S04',
            'episode': '',
            'tag': '-FLUX',
            'video_encode': 'H265',
            'sd': 0,
            'uuid': 'test-uuid',
            'trumpable_id': None,
            'filelist': [],
            'tv_pack': 1,
        }

        # Same S04, same resolution, french_lang_supersede → should be kept
        dupes = [
            {
                'name': 'The.Bear.2022.S04.MULTI.VFF.2160p.WEBRip.DV.HDR10.EAC3.5.1.x265-Amen',
                'size': 50_000_000_000,
                'flags': ['french_lang_supersede'],
                'link': 'https://c411.org/torrents/794183dd9cfd5eb919f21d7c87ee76e8f949fc5c',
                'id': 2001,
            },
        ]

        result = asyncio.get_event_loop().run_until_complete(
            checker.filter_dupes(dupes, meta, 'C411')
        )
        assert len(result) == 1
        assert result[0]['name'] == dupes[0]['name']
        assert meta.get('C411_matched_reason') == 'french_lang_supersede'

    def test_flagged_dupe_excluded_resolution_and_season_mismatch(self):
        """french_lang_supersede — both resolution AND season differ."""
        from src.dupe_checking import DupeChecker

        checker = DupeChecker(self._config())
        meta: dict[str, Any] = {
            'debug': False,
            'name': 'The.Bear.2022.S04.VOSTFR.2160p.WEB.DV.HDR.DDP.5.1.H265-FLUX',
            'resolution': '2160p',
            'hdr': 'DV HDR',
            'type': 'WEBDL',
            'source': 'WEB',
            'is_disc': None,
            'category': 'TV',
            'season': 'S04',
            'episode': '',
            'tag': '-FLUX',
            'video_encode': 'H265',
            'sd': 0,
            'uuid': 'test-uuid',
            'trumpable_id': None,
            'filelist': [],
            'tv_pack': 1,
        }

        # Different season AND different resolution + flag → excluded
        dupes = [
            {
                'name': 'The.Bear.S03.MULTI.VFF.1080p.WEB.EAC3.5.1.H264-FW',
                'size': 15_000_000_000,
                'flags': ['french_lang_supersede'],
                'link': 'https://c411.org/torrents/1c4f07e508d66e350b8279b8e0bbae54adc7385c',
                'id': 3001,
            },
        ]

        result = asyncio.get_event_loop().run_until_complete(
            checker.filter_dupes(dupes, meta, 'C411')
        )
        assert len(result) == 0

    def test_full_bear_scenario(self):
        """Reproduce the exact C411 scenario from The Bear S04 VOSTFR upload.

        Uploading: The.Bear.2022.S04.VOSTFR.2160p.WEB.DV.HDR.DDP.5.1.H265-FLUX
        Only the matching-season + matching-resolution entry should remain.
        """
        from src.dupe_checking import DupeChecker

        checker = DupeChecker(self._config())
        meta: dict[str, Any] = {
            'debug': False,
            'name': 'The.Bear.2022.S04.VOSTFR.2160p.WEB.DV.HDR.DDP.5.1.H265-FLUX',
            'resolution': '2160p',
            'hdr': 'DV HDR',
            'type': 'WEBDL',
            'source': 'WEB',
            'is_disc': None,
            'category': 'TV',
            'season': 'S04',
            'episode': '',
            'tag': '-FLUX',
            'video_encode': 'H265',
            'sd': 0,
            'uuid': 'test-uuid',
            'trumpable_id': None,
            'filelist': [],
            'tv_pack': 1,
        }

        dupes = [
            # S04 2160p — same season + resolution → KEPT
            {
                'name': 'The.Bear.2022.S04.MULTI.VFF.2160p.WEBRip.DV.HDR10.EAC3.5.1.x265-Amen',
                'size': 50_000_000_000,
                'flags': ['french_lang_supersede'],
                'link': 'https://c411.org/torrents/794183dd9cfd5eb919f21d7c87ee76e8f949fc5c',
                'id': 4001,
            },
            # S03 2160p — wrong season → excluded
            {
                'name': 'The.Bear.2022.S03.MULTI.VFF.2160p.WEBRip.DV.HDR10.EAC3.5.1.x265-Amen',
                'size': 50_000_000_000,
                'flags': ['french_lang_supersede'],
                'link': 'https://c411.org/torrents/811eebcc501b0780c690ba62f5d240c5ce2cf475',
                'id': 4002,
            },
            # S02 2160p — wrong season → excluded
            {
                'name': 'The.Bear.2022.S02.MULTI.VFF.2160p.WEBRip.EAC3.5.1.x265-Amen',
                'size': 50_000_000_000,
                'flags': ['french_lang_supersede'],
                'link': 'https://c411.org/torrents/ea436b25de386a03df59e0d906666735c68901c9',
                'id': 4003,
            },
            # S01 2160p — wrong season → excluded
            {
                'name': 'The.Bear.2022.S01.REPACK.MULTI.VFF.2160p.WEBRip.EAC3.5.1.x265-Amen',
                'size': 50_000_000_000,
                'flags': ['french_lang_supersede'],
                'link': 'https://c411.org/torrents/ba23a9a39f3e663f4a47167400cb6aecb75c8059',
                'id': 4004,
            },
            # S04 1080p — wrong resolution → excluded
            {
                'name': 'The.Bear.S04.MULTI.VFF.1080p.WEB.EAC3.5.1.H264-TFA',
                'size': 15_000_000_000,
                'flags': ['french_lang_supersede'],
                'link': 'https://c411.org/torrents/3099b672cae19f1e075e224c6cf9e1bc3aea377c',
                'id': 4005,
            },
            # S03 1080p — wrong season + wrong resolution → excluded
            {
                'name': 'The.Bear.S03.MULTI.VFF.1080p.WEB.EAC3.5.1.H264-FW',
                'size': 15_000_000_000,
                'flags': ['french_lang_supersede'],
                'link': 'https://c411.org/torrents/1c4f07e508d66e350b8279b8e0bbae54adc7385c',
                'id': 4006,
            },
            # S02 1080p — wrong season + wrong resolution → excluded
            {
                'name': 'The.Bear.S02.MULTI.VFF.1080p.WEB.EAC3.5.1.H264-FW',
                'size': 15_000_000_000,
                'flags': ['french_lang_supersede'],
                'link': 'https://c411.org/torrents/544ae1cc80bde874e972c6bbc4312204937b844f',
                'id': 4007,
            },
            # S01 1080p — wrong season + wrong resolution → excluded
            {
                'name': 'The.Bear.S01.MULTI.VFF.1080p.WEB.EAC3.5.1.H264-FRATERNiTY',
                'size': 15_000_000_000,
                'flags': ['french_lang_supersede'],
                'link': 'https://c411.org/torrents/aca3ff260ebf99b413834d5f5136310453e959ba',
                'id': 4008,
            },
        ]

        result = asyncio.get_event_loop().run_until_complete(
            checker.filter_dupes(dupes, meta, 'C411')
        )
        # Only the S04 2160p entry should survive
        assert len(result) == 1
        assert 'S04' in result[0]['name']
        assert '2160p' in result[0]['name']
        assert meta.get('C411_matched_reason') == 'french_lang_supersede'


# ─── Shared MediaInfo formatting helpers (FrenchTrackerMixin) ─

class TestLangToFlag:
    """Test _lang_to_flag from the mixin."""

    def test_english(self):
        assert C411._lang_to_flag('English') == '\U0001f1fa\U0001f1f8'

    def test_french(self):
        assert C411._lang_to_flag('French') == '\U0001f1eb\U0001f1f7'

    def test_unknown(self):
        assert C411._lang_to_flag('Klingon') == '\U0001f3f3\ufe0f'

    def test_with_parenthetical(self):
        assert C411._lang_to_flag('Chinese (Mandarin)') == '\U0001f1e8\U0001f1f3'


class TestLangToFrenchName:
    """Test _lang_to_french_name from the mixin."""

    def test_english(self):
        assert C411._lang_to_french_name('English') == 'Anglais'

    def test_french(self):
        assert C411._lang_to_french_name('French') == 'Français'

    def test_unknown_passthrough(self):
        assert C411._lang_to_french_name('Esperanto') == 'Esperanto'

    def test_with_parenthetical(self):
        assert C411._lang_to_french_name('English (GB)') == 'Anglais'


class TestChannelsToLayout:
    """Test _channels_to_layout from the mixin."""

    def test_6_channels(self):
        assert C411._channels_to_layout('6 channels') == '5.1'

    def test_8_channels(self):
        assert C411._channels_to_layout('8 channels') == '7.1'

    def test_2_channels(self):
        assert C411._channels_to_layout('2 channels') == '2.0'

    def test_1_channel(self):
        assert C411._channels_to_layout('1 channel') == '1.0'

    def test_empty(self):
        assert C411._channels_to_layout('') == ''


class TestParseAudioTracks:
    """Test _parse_mi_audio_tracks from the mixin."""

    def test_single_track(self):
        mi = (
            "Audio\n"
            "Language                                 : French\n"
            "Format                                   : AC-3\n"
            "Commercial name                          : Dolby Digital\n"
            "Bit rate                                 : 384 kb/s\n"
            "Channel(s)                               : 6 channels\n"
        )
        tracks = C411._parse_mi_audio_tracks(mi)
        assert len(tracks) == 1
        assert tracks[0]['language'] == 'French'
        assert tracks[0]['channels'] == '6 channels'
        assert tracks[0]['bitrate'] == '384 kb/s'

    def test_multi_tracks(self):
        mi = (
            "Audio #1\n"
            "Language                                 : French\n"
            "Format                                   : E-AC-3\n"
            "Channel(s)                               : 6 channels\n"
            "\nAudio #2\n"
            "Language                                 : English\n"
            "Format                                   : AC-3\n"
            "Channel(s)                               : 6 channels\n"
        )
        tracks = C411._parse_mi_audio_tracks(mi)
        assert len(tracks) == 2
        assert tracks[0]['language'] == 'French'
        assert tracks[1]['language'] == 'English'

    def test_empty(self):
        assert C411._parse_mi_audio_tracks('') == []


class TestParseSubtitleTracks:
    """Test _parse_mi_subtitle_tracks from the mixin."""

    def test_single_sub(self):
        mi = (
            "Text\n"
            "Language                                 : French\n"
            "Format                                   : UTF-8\n"
            "Title                                    : Français\n"
            "Forced                                   : No\n"
        )
        tracks = C411._parse_mi_subtitle_tracks(mi)
        assert len(tracks) == 1
        assert tracks[0]['language'] == 'French'
        assert tracks[0]['forced'] == 'No'

    def test_forced_sub(self):
        mi = (
            "Text #1\n"
            "Language                                 : English\n"
            "Format                                   : UTF-8\n"
            "Title                                    : British | Forced\n"
            "Forced                                   : Yes\n"
        )
        tracks = C411._parse_mi_subtitle_tracks(mi)
        assert len(tracks) == 1
        assert tracks[0]['forced'] == 'Yes'
        assert 'Forced' in tracks[0]['title']

    def test_empty(self):
        assert C411._parse_mi_subtitle_tracks('') == []


class TestFormatAudioBbcode:
    """Test _format_audio_bbcode from the mixin."""

    def test_basic_audio(self):
        mi = (
            "Audio\n"
            "Language                                 : French\n"
            "Commercial name                          : AC3\n"
            "Bit rate                                 : 384 kb/s\n"
            "Channel(s)                               : 6 channels\n"
        )
        c = C411(_config())
        lines = c._format_audio_bbcode(mi)
        assert len(lines) == 1
        assert '🇫🇷' in lines[0]
        assert 'Français' in lines[0]
        assert '[5.1]' in lines[0]
        assert 'AC3' in lines[0]
        assert '384 kb/s' in lines[0]

    def test_multi_audio(self):
        mi = (
            "Audio #1\n"
            "Language                                 : French\n"
            "Commercial name                          : AC3\n"
            "Channel(s)                               : 6 channels\n"
            "Bit rate                                 : 384 kb/s\n"
            "\nAudio #2\n"
            "Language                                 : English\n"
            "Commercial name                          : AC3\n"
            "Channel(s)                               : 6 channels\n"
            "Bit rate                                 : 384 kb/s\n"
        )
        c = C411(_config())
        lines = c._format_audio_bbcode(mi)
        assert len(lines) == 2
        assert 'Français' in lines[0]
        assert 'Anglais' in lines[1]

    def test_empty_mi(self):
        c = C411(_config())
        assert c._format_audio_bbcode('') == []


class TestFormatSubtitleBbcode:
    """Test _format_subtitle_bbcode from the mixin."""

    def test_basic_sub(self):
        mi = (
            "Text\n"
            "Language                                 : French\n"
            "Format                                   : UTF-8\n"
            "Forced                                   : No\n"
        )
        c = C411(_config())
        lines = c._format_subtitle_bbcode(mi)
        assert len(lines) == 1
        assert '🇫🇷' in lines[0]
        assert 'Français' in lines[0]
        assert 'SRT' in lines[0]
        assert 'complets' in lines[0]

    def test_forced_sub(self):
        mi = (
            "Text\n"
            "Language                                 : English\n"
            "Format                                   : UTF-8\n"
            "Title                                    : British | Forced\n"
            "Forced                                   : Yes\n"
        )
        c = C411(_config())
        lines = c._format_subtitle_bbcode(mi)
        assert len(lines) == 1
        assert 'forcés' in lines[0]

    def test_sdh_sub(self):
        mi = (
            "Text\n"
            "Language                                 : English\n"
            "Format                                   : UTF-8\n"
            "Title                                    : SDH\n"
            "Forced                                   : No\n"
        )
        c = C411(_config())
        lines = c._format_subtitle_bbcode(mi)
        assert len(lines) == 1
        assert 'SDH' in lines[0]

    def test_pgs_format(self):
        mi = (
            "Text\n"
            "Language                                 : French\n"
            "Format                                   : PGS\n"
        )
        c = C411(_config())
        lines = c._format_subtitle_bbcode(mi)
        assert len(lines) == 1
        assert 'PGS' in lines[0]

    def test_empty_mi(self):
        c = C411(_config())
        assert c._format_subtitle_bbcode('') == []


class TestFormatHdrDvBbcode:
    """Test _format_hdr_dv_bbcode from the mixin."""

    def test_sdr_returns_none(self):
        c = C411(_config())
        assert c._format_hdr_dv_bbcode({'hdr': ''}) is None
        assert c._format_hdr_dv_bbcode({}) is None

    def test_hdr_only(self):
        c = C411(_config())
        result = c._format_hdr_dv_bbcode({'hdr': 'HDR'})
        assert result == 'HDR10'

    def test_hdr10plus(self):
        c = C411(_config())
        result = c._format_hdr_dv_bbcode({'hdr': 'HDR10+'})
        assert result == 'HDR10+'

    def test_dv_only(self):
        c = C411(_config())
        result = c._format_hdr_dv_bbcode({'hdr': 'DV'})
        assert result == 'Dolby Vision'

    def test_dv_hdr(self):
        c = C411(_config())
        result = c._format_hdr_dv_bbcode({'hdr': 'DV HDR'})
        assert result == 'Dolby Vision + HDR10'

    def test_dv_hdr10plus(self):
        c = C411(_config())
        result = c._format_hdr_dv_bbcode({'hdr': 'DV HDR10+'})
        assert result == 'HDR10+ + Dolby Vision'

    def test_hlg(self):
        c = C411(_config())
        assert c._format_hdr_dv_bbcode({'hdr': 'HLG'}) == 'HLG'

    def test_hdr_hlg(self):
        c = C411(_config())
        result = c._format_hdr_dv_bbcode({'hdr': 'HDR HLG'})
        assert result == 'HDR10 + HLG'

    def test_pq10(self):
        c = C411(_config())
        assert c._format_hdr_dv_bbcode({'hdr': 'PQ10'}) == 'PQ10'

    def test_wcg(self):
        c = C411(_config())
        assert c._format_hdr_dv_bbcode({'hdr': 'WCG'}) == 'WCG'
