"""Synthetic fixtures for French tracker tests.

No real titles, groups or provider IDs (the same rule upbrr applies to its
fixtures). Scenarios are MediaInfo track lists named after the language tag
they must produce, so naming, rules and dupe tests share one vocabulary.
"""

from typing import Any

RELEASE_TITLE = "Example Release"
RELEASE_YEAR = "2026"
RELEASE_GROUP = "GRP"
RELEASE_NAME = f"Example.Release.{RELEASE_YEAR}.1080p.WEB.x264-{RELEASE_GROUP}"
TMDB_ID = 1234
IMDB_ID = 1234567


def audio_track(lang: str = "fr", **kw: Any) -> dict[str, Any]:
    """A minimal MediaInfo audio track; kw adds/overrides fields (Title, Format, Channels...)."""
    track: dict[str, Any] = {"@type": "Audio", "Language": lang}
    track.update(kw)
    return track


def sub_track(lang: str = "fr", **kw: Any) -> dict[str, Any]:
    """A minimal MediaInfo text (subtitle) track."""
    track: dict[str, Any] = {"@type": "Text", "Language": lang}
    track.update(kw)
    return track


def mediainfo(audio: list[dict[str, Any]], subs: list[dict[str, Any]] | None = None, video: dict[str, Any] | None = None) -> dict[str, Any]:
    """meta["mediainfo"] holding the given tracks (a General track is always present)."""
    tracks: list[dict[str, Any]] = [{"@type": "General", "FileExtension": "mkv"}]
    if video:
        tracks.append({"@type": "Video", **video})
    tracks.extend(audio)
    tracks.extend(subs or [])
    return {"media": {"track": tracks}}


# Named scenarios: the MediaInfo shape -> the French audio tag it must yield.
SCENARIOS: dict[str, dict[str, Any]] = {
    "VFF": mediainfo([audio_track("fr-FR")]),
    "VFQ": mediainfo([audio_track("fr-CA")]),
    "VFB": mediainfo([audio_track("fr-BE")]),
    "VF2": mediainfo([audio_track("fr-FR"), audio_track("fr-CA")]),
    "VFQ_from_title": mediainfo([audio_track("fr", Title="VFQ 5.1")]),
    "MULTI_VFF": mediainfo([audio_track("en"), audio_track("fr-FR")], [sub_track("fr")]),
    "VOSTFR": mediainfo([audio_track("en")], [sub_track("fr")]),
    "MUET": mediainfo([]),
    "VO_only": mediainfo([audio_track("en")]),
}


def french_meta(**overrides: Any) -> dict[str, Any]:
    """A synthetic French-release meta; override freely (tracker_status, mediainfo...)."""
    meta: dict[str, Any] = {
        "category": "MOVIE",
        "type": "WEBDL",
        "title": RELEASE_TITLE,
        "year": RELEASE_YEAR,
        "resolution": "1080p",
        "source": "WEB",
        "audio": "AC3",
        "video_encode": "x264",
        "video_codec": "H264",
        "service": "",
        "tag": f"-{RELEASE_GROUP}",
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
        "unattended": True,
        "tv_pack": 0,
        "path": f"/releases/{RELEASE_NAME}",
        "filelist": [f"/releases/{RELEASE_NAME}/{RELEASE_NAME}.mkv"],
        "name": RELEASE_NAME,
        "uuid": RELEASE_NAME,
        "base_dir": "/tmp",
        "overview": "Synthetic overview.",
        "poster": "https://images.example/poster.jpg",
        "tmdb": TMDB_ID,
        "imdb_id": IMDB_ID,
        "original_language": "fr",
        "image_list": [],
        "audio_languages": ["French"],
        "subtitle_languages": [],
        "bdinfo": None,
        "mediainfo": SCENARIOS["VFF"],
        "tracker_status": {},
        "has_encode_settings": False,
    }
    meta.update(overrides)
    return meta


# Response bodies in the shape the French APIs return (synthetic values).
C411_TORRENT = {
    "id": 1001,
    "title": RELEASE_NAME,
    "size": 4_500_000_000,
    "categoryId": 1,
    "subcategoryId": 7,
    "tmdbId": TMDB_ID,
    "files": [{"name": f"{RELEASE_NAME}.mkv", "size": 4_500_000_000}],
}

V3X_TORRENT = {
    "id": 2002,
    "name": RELEASE_NAME,
    "size": 4_500_000_000,
    "tmdb_id": TMDB_ID,
    "files": [f"{RELEASE_NAME}.mkv"],
}
