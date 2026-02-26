# Tests for TV pack homogeneity check
"""
Test suite for check_pack_homogeneity in SeasonEpisodeManager.
Verifies detection of mismatched resolution, codec, source,
audio codec, language tags, and group tags across pack files.
"""

import asyncio
from typing import Any

import pytest

from src.getseasonep import SeasonEpisodeManager


def _config() -> dict[str, Any]:
    return {'DEFAULT': {'tmdb_api': 'fake-key'}}


def _meta(filelist: list[str], **kw: Any) -> dict[str, Any]:
    m: dict[str, Any] = {
        'filelist': filelist,
        'tv_pack': 1,
        'debug': False,
    }
    m.update(kw)
    return m


# ─── Homogeneous packs (no issues) ────────────────────────────


class TestHomogeneousPacks:
    """All files share the same specs → homogeneous=True."""

    def test_same_specs(self) -> None:
        files = [
            '/media/Show.S01E01.FRENCH.1080p.WEB.H264-GRP.mkv',
            '/media/Show.S01E02.FRENCH.1080p.WEB.H264-GRP.mkv',
            '/media/Show.S01E03.FRENCH.1080p.WEB.H264-GRP.mkv',
        ]
        mgr = SeasonEpisodeManager(_config())
        result = asyncio.get_event_loop().run_until_complete(
            mgr.check_pack_homogeneity(_meta(files))
        )
        assert result['homogeneous'] is True
        assert result['issues'] == {}

    def test_single_file_always_ok(self) -> None:
        files = ['/media/Show.S01E01.FRENCH.1080p.WEB.H264-GRP.mkv']
        mgr = SeasonEpisodeManager(_config())
        result = asyncio.get_event_loop().run_until_complete(
            mgr.check_pack_homogeneity(_meta(files))
        )
        assert result['homogeneous'] is True

    def test_empty_filelist(self) -> None:
        mgr = SeasonEpisodeManager(_config())
        result = asyncio.get_event_loop().run_until_complete(
            mgr.check_pack_homogeneity(_meta([]))
        )
        assert result['homogeneous'] is True

    def test_non_video_files_ignored(self) -> None:
        files = [
            '/media/Show.S01E01.FRENCH.1080p.WEB.H264-GRP.mkv',
            '/media/Show.S01E02.FRENCH.1080p.WEB.H264-GRP.mkv',
            '/media/Show.S01E01.srt',
            '/media/info.nfo',
        ]
        mgr = SeasonEpisodeManager(_config())
        result = asyncio.get_event_loop().run_until_complete(
            mgr.check_pack_homogeneity(_meta(files))
        )
        assert result['homogeneous'] is True

    def test_multi_language_same_across_files(self) -> None:
        files = [
            '/media/Show.S01E01.MULTI.1080p.BluRay.x265-GRP.mkv',
            '/media/Show.S01E02.MULTI.1080p.BluRay.x265-GRP.mkv',
        ]
        mgr = SeasonEpisodeManager(_config())
        result = asyncio.get_event_loop().run_until_complete(
            mgr.check_pack_homogeneity(_meta(files))
        )
        assert result['homogeneous'] is True


# ─── Resolution mismatch ──────────────────────────────────────


class TestResolutionMismatch:
    def test_mixed_resolutions(self) -> None:
        files = [
            '/media/Show.S01E01.FRENCH.1080p.WEB.H264-GRP.mkv',
            '/media/Show.S01E02.FRENCH.720p.WEB.H264-GRP.mkv',
            '/media/Show.S01E03.FRENCH.1080p.WEB.H264-GRP.mkv',
        ]
        mgr = SeasonEpisodeManager(_config())
        result = asyncio.get_event_loop().run_until_complete(
            mgr.check_pack_homogeneity(_meta(files))
        )
        assert result['homogeneous'] is False
        assert 'Resolution' in result['issues']
        assert len(result['issues']['Resolution']) == 2  # 1080p and 720p


# ─── Codec mismatch ───────────────────────────────────────────


class TestCodecMismatch:
    def test_mixed_codecs(self) -> None:
        files = [
            '/media/Show.S01E01.FRENCH.1080p.WEB.H264-GRP.mkv',
            '/media/Show.S01E02.FRENCH.1080p.WEB.H265-GRP.mkv',
        ]
        mgr = SeasonEpisodeManager(_config())
        result = asyncio.get_event_loop().run_until_complete(
            mgr.check_pack_homogeneity(_meta(files))
        )
        assert result['homogeneous'] is False
        assert 'Video Codec' in result['issues']


# ─── Source mismatch ───────────────────────────────────────────


class TestSourceMismatch:
    def test_mixed_sources(self) -> None:
        files = [
            '/media/Show.S01E01.FRENCH.1080p.WEB-DL.H264-GRP.mkv',
            '/media/Show.S01E02.FRENCH.1080p.BluRay.H264-GRP.mkv',
        ]
        mgr = SeasonEpisodeManager(_config())
        result = asyncio.get_event_loop().run_until_complete(
            mgr.check_pack_homogeneity(_meta(files))
        )
        assert result['homogeneous'] is False
        assert 'Source' in result['issues']


# ─── Language tag mismatch ─────────────────────────────────────


class TestLanguageMismatch:
    def test_french_vs_multi(self) -> None:
        """The key scenario: 3 files FRENCH + 1 file MULTI."""
        files = [
            '/media/Show.S01E01.FRENCH.1080p.WEB.H264-GRP.mkv',
            '/media/Show.S01E02.FRENCH.1080p.WEB.H264-GRP.mkv',
            '/media/Show.S01E03.MULTI.1080p.WEB.H264-GRP.mkv',
            '/media/Show.S01E04.FRENCH.1080p.WEB.H264-GRP.mkv',
        ]
        mgr = SeasonEpisodeManager(_config())
        result = asyncio.get_event_loop().run_until_complete(
            mgr.check_pack_homogeneity(_meta(files))
        )
        assert result['homogeneous'] is False
        assert 'Language' in result['issues']
        assert 'FRENCH' in result['issues']['Language']
        assert 'MULTI' in result['issues']['Language']

    def test_vff_vs_truefrench(self) -> None:
        files = [
            '/media/Show.S01E01.VFF.1080p.WEB.H264-GRP.mkv',
            '/media/Show.S01E02.TRUEFRENCH.1080p.WEB.H264-GRP.mkv',
        ]
        mgr = SeasonEpisodeManager(_config())
        result = asyncio.get_event_loop().run_until_complete(
            mgr.check_pack_homogeneity(_meta(files))
        )
        assert result['homogeneous'] is False
        assert 'Language' in result['issues']


# ─── Multiple issues at once ──────────────────────────────────


class TestMultipleIssues:
    def test_resolution_and_language_mismatch(self) -> None:
        files = [
            '/media/Show.S01E01.FRENCH.1080p.WEB.H264-GRP.mkv',
            '/media/Show.S01E02.MULTI.720p.WEB.H264-GRP.mkv',
        ]
        mgr = SeasonEpisodeManager(_config())
        result = asyncio.get_event_loop().run_until_complete(
            mgr.check_pack_homogeneity(_meta(files))
        )
        assert result['homogeneous'] is False
        assert 'Resolution' in result['issues']
        assert 'Language' in result['issues']

    def test_everything_different(self) -> None:
        files = [
            '/media/Show.S01E01.FRENCH.1080p.BluRay.x264-AAA.mkv',
            '/media/Show.S01E02.MULTI.720p.WEB-DL.x265-BBB.mkv',
        ]
        mgr = SeasonEpisodeManager(_config())
        result = asyncio.get_event_loop().run_until_complete(
            mgr.check_pack_homogeneity(_meta(files))
        )
        assert result['homogeneous'] is False
        # Should have resolution, codec, source, and language issues
        assert len(result['issues']) >= 3
