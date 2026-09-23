# A screener is a pre-release promotional copy; trackers refuse them, so the
# tool must too. The word is detected in the release's file names and in the
# MediaInfo fields, with one deliberate asymmetry: the bare "SCR" tag is read
# only from file names, because "scr" is also the legacy ISO code for Croatian
# and would otherwise reject any Croatian audio track.

import asyncio
from typing import Any

import pytest

from src.trackers.COMMON import COMMON


def _config() -> dict[str, Any]:
    return {"DEFAULT": {"tmdb_api": "fake"}, "TRACKERS": {}}


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _meta(filename: str = "Example.Movie.2026.1080p.BluRay.x264-GRP.mkv", **general: Any) -> dict[str, Any]:
    track: dict[str, Any] = {"@type": "General", "CompleteName": f"/media/library/{filename}"}
    track.update(general)
    return {
        "path": f"/media/library/{filename}",
        "filelist": [f"/media/library/{filename}"],
        "uuid": filename,
        "mediainfo": {"media": {"track": [track, {"@type": "Video", "Format": "AVC"}]}},
    }


def _check(meta: dict[str, Any]) -> bool:
    return _run(COMMON(config=_config()).check_screener(meta))


class TestScreenerInFilename:
    @pytest.mark.parametrize(
        "filename",
        [
            "Example.Movie.2026.Screener.x264-GRP.mkv",
            "Example.Movie.2026.DVDSCR.XviD-GRP.avi",
            "Example.Movie.2026.1080p.WEBSCR.x264-GRP.mkv",
            "Example.Movie.2026.BDSCR.x264-GRP.mkv",
            "Example.Movie.2026.SCR.x264-GRP.mkv",
            "Example.Movie.2026.screeners.x264-GRP.mkv",
        ],
    )
    def test_screener_tag_is_detected(self, filename: str) -> None:
        assert _check(_meta(filename)) is True

    @pytest.mark.parametrize(
        "filename",
        [
            "Example.Movie.2026.1080p.BluRay.x264-GRP.mkv",
            "Discreet.Charm.2026.1080p.BluRay.x264-GRP.mkv",
            "Example.Screenlife.Movie.2026.1080p.WEB-DL.H264-GRP.mkv",
            "Example.Movie.2026.1080p.DESCRAMBLED.x264-GRP.mkv",
        ],
    )
    def test_ordinary_release_is_not_flagged(self, filename: str) -> None:
        assert _check(_meta(filename)) is False

    def test_the_folder_name_of_a_pack_counts(self) -> None:
        meta = _meta()
        meta["path"] = "/media/library/Example.Series.S01.DVDSCR.x264-GRP"

        assert _check(meta) is True


class TestScreenerInMediaInfo:
    def test_a_title_tag_naming_a_screener_is_detected(self) -> None:
        assert _check(_meta(Title="Awards Screener - do not distribute")) is True

    def test_a_movie_name_tag_naming_a_screener_is_detected(self) -> None:
        assert _check(_meta(Movie="Example Movie (DVDSCR)")) is True

    def test_a_clean_mediainfo_is_not_flagged(self) -> None:
        assert _check(_meta(Title="Example Movie", Movie="Example Movie")) is False

    def test_a_croatian_language_code_is_not_a_screener(self) -> None:
        meta = _meta()
        meta["mediainfo"]["media"]["track"].append({"@type": "Audio", "Language": "scr", "Format": "AC-3"})

        assert _check(meta) is False

    def test_a_spelled_out_screener_still_wins_over_the_language_code(self) -> None:
        meta = _meta()
        meta["mediainfo"]["media"]["track"].append({"@type": "Audio", "Language": "scr", "Title": "Screener audio"})

        assert _check(meta) is True


class TestScreenerGuardEdges:
    def test_missing_mediainfo_does_not_raise(self) -> None:
        assert _check({"path": "/media/library/Example.Movie.2026.x264-GRP.mkv", "filelist": [], "uuid": "x"}) is False

    def test_empty_meta_does_not_raise(self) -> None:
        assert _check({}) is False
