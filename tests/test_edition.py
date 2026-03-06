# Tests for edition detection — src/edition.py
"""
Test suite for the edition detection and normalisation logic.
Covers: 'Special Edition' preservation, 'Extended Edition' normalisation,
        guessit-based edition parsing, and edge cases.
"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.edition import get_edition


# ─── Helpers ──────────────────────────────────────────────────


def _meta_base(**overrides: Any) -> dict[str, Any]:
    """Return a minimal meta dict suitable for ``get_edition``."""
    m: dict[str, Any] = {
        'category': 'MOVIE',
        'type': 'BLURAY',
        'anime': False,
        'is_disc': None,
        'debug': False,
        'imdb_info': {},
        'mediainfo': {'media': {'track': []}},
        'webdv': False,
    }
    m.update(overrides)
    return m


def _run(coro: Any) -> Any:
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─── Special Edition — guessit path ──────────────────────────


class TestSpecialEditionGuessit:
    """When the filename contains 'Special.Edition', guessit returns bare
    'Special'.  The cleanup must expand it back to 'Special Edition'."""

    def test_special_edition_from_filename(self) -> None:
        video = 'Aliens.1986.Special.Edition.2160p.UHD.BluRay.TrueHD.7.1.DoVi.HDR10.x265-W4NK3R.mkv'
        meta = _meta_base()
        edition, repack, hybrid = _run(get_edition(video, None, [video], '', meta))
        assert edition == 'SPECIAL EDITION'

    def test_special_edition_lowercase_dots(self) -> None:
        video = 'movie.2020.special.edition.1080p.bluray.x264-group.mkv'
        meta = _meta_base()
        edition, _repack, _hybrid = _run(get_edition(video, None, [video], '', meta))
        assert edition == 'SPECIAL EDITION'

    def test_special_edition_mixed_case(self) -> None:
        video = 'Movie.2020.SPECIAL.EDITION.1080p.BluRay.x264-GROUP.mkv'
        meta = _meta_base()
        edition, _repack, _hybrid = _run(get_edition(video, None, [video], '', meta))
        assert edition == 'SPECIAL EDITION'


# ─── Special Edition — IMDB duration-match path ──────────────


class TestSpecialEditionIMDB:
    """When IMDB edition_details provide ['special', 'edition'] attributes,
    the edition must resolve to 'SPECIAL EDITION'."""

    def test_imdb_special_edition_preserved(self) -> None:
        """Simulate IMDB duration match returning 'Special Edition'."""
        meta = _meta_base(
            imdb_info={
                'edition_details': {
                    'v1': {
                        'seconds': 7200,
                        'attributes': ['special', 'edition'],
                    },
                },
            },
            mediainfo={
                'media': {
                    'track': [
                        {'@type': 'General', 'Duration': '7200'},
                    ],
                },
            },
        )
        video = 'Aliens.1986.2160p.UHD.BluRay.TrueHD.7.1.DoVi.HDR10.x265-W4NK3R.mkv'
        edition, _repack, _hybrid = _run(get_edition(video, None, [video], '', meta))
        assert edition == 'SPECIAL EDITION'


# ─── Extended Edition — must still normalise to 'EXTENDED' ───


class TestExtendedEdition:
    """'Extended Edition' must be normalised to just 'EXTENDED'."""

    def test_extended_edition_from_filename(self) -> None:
        video = 'The.Godfather.1972.Extended.Edition.1080p.BluRay.x264-GROUP.mkv'
        meta = _meta_base()
        edition, _repack, _hybrid = _run(get_edition(video, None, [video], '', meta))
        assert edition == 'EXTENDED'

    def test_extended_from_filename(self) -> None:
        """guessit returns bare 'Extended' — must stay 'EXTENDED'."""
        video = 'Movie.2020.Extended.1080p.BluRay.x264-GROUP.mkv'
        meta = _meta_base()
        edition, _repack, _hybrid = _run(get_edition(video, None, [video], '', meta))
        assert edition == 'EXTENDED'


# ─── Other editions are not affected ─────────────────────────


class TestOtherEditions:
    """Editions that are not 'Special' must be left unchanged (after uppercasing)."""

    def test_unrated_edition(self) -> None:
        video = 'Movie.2020.Unrated.1080p.BluRay.x264-GROUP.mkv'
        meta = _meta_base()
        edition, _repack, _hybrid = _run(get_edition(video, None, [video], '', meta))
        assert edition == 'UNRATED'

    def test_directors_cut(self) -> None:
        video = "Movie.2020.Director's.Cut.1080p.BluRay.x264-GROUP.mkv"
        meta = _meta_base()
        edition, _repack, _hybrid = _run(get_edition(video, None, [video], '', meta))
        assert edition == "DIRECTOR'S CUT"

    def test_no_edition(self) -> None:
        video = 'Movie.2020.1080p.BluRay.x264-GROUP.mkv'
        meta = _meta_base()
        edition, _repack, _hybrid = _run(get_edition(video, None, [video], '', meta))
        assert edition == ''


# ─── Manual edition override ─────────────────────────────────


class TestManualEdition:
    """Manual editions override all detection logic."""

    def test_manual_edition_overrides_special(self) -> None:
        video = 'Aliens.1986.Special.Edition.2160p.UHD.BluRay.x265-GROUP.mkv'
        meta = _meta_base()
        edition, _repack, _hybrid = _run(get_edition(video, None, [video], 'Theatrical', meta))
        assert edition == 'THEATRICAL'

    def test_manual_edition_list(self) -> None:
        video = 'Movie.2020.1080p.BluRay.x264-GROUP.mkv'
        meta = _meta_base()
        edition, _repack, _hybrid = _run(get_edition(video, None, [video], ['Special', 'Edition'], meta))
        assert edition == 'SPECIAL EDITION'


# ─── Hybrid / repack are separate from edition ───────────────


class TestHybridRepackSeparation:
    """Verify that hybrid/repack flags work alongside Special Edition."""

    def test_special_edition_with_repack(self) -> None:
        video = 'Aliens.1986.Special.Edition.REPACK.2160p.UHD.BluRay.x265-GROUP.mkv'
        meta = _meta_base()
        edition, repack, _hybrid = _run(get_edition(video, None, [video], '', meta))
        assert edition == 'SPECIAL EDITION'
        assert repack == 'REPACK'

    def test_special_edition_with_hybrid(self) -> None:
        video = 'Aliens.1986.Hybrid.Special.Edition.2160p.UHD.BluRay.x265-GROUP.mkv'
        meta = _meta_base()
        edition, _repack, hybrid = _run(get_edition(video, None, [video], '', meta))
        assert edition == 'SPECIAL EDITION'
        assert hybrid == 'Hybrid'


# ─── French tracker title-case formatting ─────────────────────


class TestFrenchEditionFormatting:
    """French trackers must display editions in title case, not ALL-CAPS."""

    @pytest.mark.parametrize(
        'uppercased, expected',
        [
            ('SPECIAL EDITION', 'Special Edition'),
            ('EXTENDED', 'Extended'),
            ('THEATRICAL', 'Theatrical'),
            ("DIRECTOR'S CUT", "Director's Cut"),
            ('UNRATED', 'Unrated'),
            ('OPEN MATTE', 'Open Matte'),
            ('LiMiTED', 'LiMiTED'),
            ('', ''),
        ],
    )
    def test_format_edition(self, uppercased: str, expected: str) -> None:
        from src.trackers.FRENCH import FrenchTrackerMixin  # noqa: WPS433
        assert FrenchTrackerMixin._format_edition(uppercased) == expected
