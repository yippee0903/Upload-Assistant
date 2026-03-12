import asyncio
from typing import Any

import pytest

from src.trackers.C411 import C411
from src.trackers.G3MINI import G3MINI
from src.trackers.GF import GF
from src.trackers.TORR9 import TORR9
from src.trackers.TOS import TOS


def _config() -> dict[str, Any]:
    return {
        "TRACKERS": {
            "C411": {"api_key": "test-key"},
            "GF": {"api_key": "test-key", "announce_url": "https://generation-free.org/announce/FAKE_PASSKEY"},
            "TORR9": {"api_key": "test-key", "username": "user", "password": "pass"},
            "TOS": {"api_key": "test-key", "announce_url": "https://theoldschool.cc/announce/FAKE_PASSKEY"},
            "G3MINI": {"api_key": "test-key", "announce_url": "https://gemini-tracker.org/announce/FAKE_PASSKEY"},
        },
        "DEFAULT": {"tmdb_api": "fake-tmdb-key"},
    }


def _audio_track(lang: str = "fr", **kw: Any) -> dict[str, Any]:
    track: dict[str, Any] = {"@type": "Audio", "Language": lang}
    track.update(kw)
    return track


def _sub_track(lang: str = "fr") -> dict[str, Any]:
    return {"@type": "Text", "Language": lang}


def _mi(audio: list[dict[str, Any]], subs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    tracks: list[dict[str, Any]] = [{"@type": "General"}]
    tracks.extend(audio)
    if subs:
        tracks.extend(subs)
    return {"media": {"track": tracks}}


def _meta_base(**overrides: Any) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "category": "MOVIE",
        "type": "WEBDL",
        "title": "Le Prenom",
        "year": "2012",
        "resolution": "1080p",
        "source": "WEB",
        "audio": "AC3",
        "video_encode": "H264",
        "video_codec": "",
        "service": "",
        "tag": "-TEST",
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
        "path": "",
        "name": "",
        "uuid": "test-uuid",
        "base_dir": "/tmp",
        "overview": "Un diner entre amis.",
        "poster": "",
        "tmdb": 1234,
        "imdb_id": 1234567,
        "original_language": "en",
        "image_list": [],
        "bdinfo": None,
        "region": "",
        "dvd_size": "",
        "tracker_status": {},
        "mediainfo": {"media": {"track": []}},
    }
    meta.update(overrides)
    return meta


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


@pytest.fixture(params=[C411, GF, TORR9, TOS, G3MINI], ids=["C411", "GF", "TORR9", "TOS", "G3MINI"])
def tracker(request: pytest.FixtureRequest):
    return request.param(_config())


def _expected_single(tracker: Any) -> str:
    return "AD.FRENCH" if tracker.tracker in {"TOS", "G3MINI"} else "AD.VFF"


def _expected_multi(tracker: Any) -> str:
    return "AD.MULTi" if tracker.tracker in {"TOS", "G3MINI"} else "AD.MULTI.VFF"


def _normalize_name(value: str) -> str:
    return " ".join(value.replace(".", " ").split()).upper()


class TestFrenchAudioDescriptionAcrossTrackers:
    def test_single_french_with_french_ad_is_not_multi(self, tracker: Any):
        meta = _meta_base(
            mediainfo=_mi([
                _audio_track("fr", Title="Main Audio"),
                _audio_track("fr", Title="Audio Description"),
            ]),
        )
        assert _run(tracker._build_audio_string(meta)) == _expected_single(tracker)

    def test_single_french_with_foreign_ad_becomes_multi(self, tracker: Any):
        meta = _meta_base(
            mediainfo=_mi([
                _audio_track("fr", Title="Main Audio"),
                _audio_track("en", Title="Audio Description"),
            ]),
        )
        assert _run(tracker._build_audio_string(meta)) == _expected_multi(tracker)

    def test_french_ad_only_does_not_count_as_french_audio(self, tracker: Any):
        meta = _meta_base(
            mediainfo=_mi([
                _audio_track("en", Title="Main Audio"),
                _audio_track("fr", Title="Audio Description"),
            ], [_sub_track("fr")]),
        )
        assert _run(tracker._build_audio_string(meta)) == "AD.VOSTFR"

    def test_get_name_keeps_ad_prefix_before_multi(self, tracker: Any):
        meta = _meta_base(
            mediainfo=_mi([
                _audio_track("fr", Title="Main Audio"),
                _audio_track("en", Title="Audio Description"),
            ]),
        )
        result = _run(tracker.get_name(meta))["name"]
        assert _normalize_name(_expected_multi(tracker)) in _normalize_name(result)

    def test_audio_description_bbcode_marks_only_matching_track(self, tracker: Any):
        mi = (
            "Audio #1\n"
            "Language                                 : French\n"
            "Title                                    : Audio Description\n"
            "Commercial name                          : AC3\n"
            "Channel(s)                               : 2 channels\n"
            "Bit rate                                 : 192 kb/s\n"
            "\nAudio #2\n"
            "Language                                 : English\n"
            "Commercial name                          : AC3\n"
            "Channel(s)                               : 6 channels\n"
            "Bit rate                                 : 384 kb/s\n"
        )
        lines = tracker._format_audio_bbcode(mi, {"has_audiodesc": True})
        assert " [AD]" in lines[0]
        assert " [AD]" not in lines[1]

    def test_audio_description_bbcode_detects_hyphenated_title(self, tracker: Any):
        mi = (
            "Audio\n"
            "Language                                 : French\n"
            "Title                                    : Audio-Description\n"
            "Commercial name                          : AC3\n"
            "Channel(s)                               : 2 channels\n"
            "Bit rate                                 : 192 kb/s\n"
        )
        lines = tracker._format_audio_bbcode(mi)
        assert " [AD]" in lines[0]
