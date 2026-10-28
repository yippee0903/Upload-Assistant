# DRAU (draupnirr.xyz) — custom-API French tracker. Covers the category
# slugs, the JSON catalogue dupe check, and the multipart upload contract:
# torrent + category + meta[...] fields, X-Api-Key auth, 422 fail-fast.

import asyncio
from typing import Any

import src.trackers.DRAU as drau_module
from src.trackers.DRAU import DRAU


def _config() -> dict[str, Any]:
    return {
        "TRACKERS": {"DRAU": {"api_key": "test-passkey"}},
        "DEFAULT": {"tmdb_api": "fake"},
    }


class _FakeResponse:
    def __init__(self, status_code: int, payload: Any):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        if isinstance(self._payload, str):
            raise ValueError("not json")
        return self._payload

    @property
    def text(self) -> str:
        return self._payload if isinstance(self._payload, str) else ""


class _FakeClient:
    response: _FakeResponse = _FakeResponse(200, [])
    captured: dict[str, Any] = {}
    calls: list[dict[str, Any]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass

    async def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        _FakeClient.captured = {"method": "GET", "url": url, **kwargs}
        _FakeClient.calls.append(_FakeClient.captured)
        return _FakeClient.response

    async def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        _FakeClient.captured = {"method": "POST", "url": url, **kwargs}
        _FakeClient.calls.append(_FakeClient.captured)
        return _FakeClient.response


def _posts() -> list[dict[str, Any]]:
    return [c for c in _FakeClient.calls if c.get("method") == "POST"]


def _entry(name: str, size: int = 1000, torrent_id: str = "Xk3Qm9") -> dict[str, Any]:
    return {
        "id": torrent_id,
        "infohash": "ab" * 20,
        "name": name,
        "category": "films-film",
        "size_bytes": size,
        "file_count": 1,
        "download_url": f"https://draupnirr.xyz/api/torrents/{torrent_id}/download",
    }


class TestCategoryMapping:
    def _cat(self, meta: dict[str, Any]) -> str:
        return asyncio.run(DRAU(_config()).get_category_id(meta))

    def test_movie_is_film(self):
        assert self._cat({"category": "MOVIE", "genres": "Drama"}) == "films-film"

    def test_tv_is_serie(self):
        assert self._cat({"category": "TV", "genres": "Drama"}) == "series-serie-tv"

    def test_animation_and_documentary(self):
        assert self._cat({"category": "MOVIE", "genres": "Animation"}) == "films-animation"
        assert self._cat({"category": "TV", "mal_id": 1}) == "series-serie-animee"
        assert self._cat({"category": "MOVIE", "genres": "Documentary"}) == "films-documentaire"
        assert self._cat({"category": "MOVIE", "genres": "Animation, Documentary"}) == "films-documentaire"


class TestSearchExisting:
    def _prep(self, monkeypatch: Any, tracker: DRAU, checks: bool = True, fr_title: str = "") -> None:
        async def fake_checks(meta: Any) -> bool:
            return checks

        async def fake_fr(meta: Any) -> str:
            return fr_title

        async def fake_audio(meta: Any) -> str:
            return "MULTI.VFF"

        monkeypatch.setattr(tracker, "get_additional_checks", fake_checks)
        monkeypatch.setattr(tracker, "_get_french_title", fake_fr)
        monkeypatch.setattr(tracker, "_build_audio_string", fake_audio)
        monkeypatch.setattr(drau_module.httpx, "AsyncClient", _FakeClient)
        _FakeClient.calls = []

    def _meta(self) -> dict[str, Any]:
        return {"title": "Some Movie", "year": "2024", "resolution": "1080p", "category": "MOVIE", "tag": "-GRP", "audio_languages": ["fr"]}

    def test_search_maps_catalogue_to_dupes(self, monkeypatch: Any):
        tracker = DRAU(_config())
        self._prep(monkeypatch, tracker)
        _FakeClient.response = _FakeResponse(200, [_entry("Some.Movie.2024.MULTi.1080p.WEB.x264-GRP", size=4321)])
        dupes = asyncio.run(tracker.search_existing(self._meta()))
        assert dupes == [
            {
                "name": "Some.Movie.2024.MULTi.1080p.WEB.x264-GRP",
                "size": 4321,
                "link": "https://draupnirr.xyz/torrents/Xk3Qm9",
                "id": "Xk3Qm9",
                "download": "https://draupnirr.xyz/api/torrents/Xk3Qm9/download",
                "file_count": 1,
            }
        ]
        sent = _FakeClient.captured
        assert sent["url"] == "https://draupnirr.xyz/api/torrents"
        assert sent["params"] == {"q": "Some Movie", "limit": 100, "offset": 0}
        assert sent["headers"]["X-Api-Key"] == "test-passkey"

    def test_search_filters_irrelevant_results(self, monkeypatch: Any):
        tracker = DRAU(_config())
        self._prep(monkeypatch, tracker)
        _FakeClient.response = _FakeResponse(
            200,
            [
                _entry("Some.Movie.2024.MULTi.1080p.WEB.x264-GRP"),
                _entry("Some.Movie.2024.MULTi.2160p.WEB.x265-GRP"),
                _entry("Some.Movie.2019.MULTi.1080p.WEB.x264-GRP"),
                _entry("Other.Movie.2024.MULTi.1080p.WEB.x264-GRP"),
                _entry("Some.Movie.2024.MULTi.1080p.WEB.x264-OTHER"),
            ],
        )
        dupes = asyncio.run(tracker.search_existing(self._meta()))
        assert [d["name"] for d in dupes] == ["Some.Movie.2024.MULTi.1080p.WEB.x264-GRP"]

    def test_search_http_error_fails_closed(self, monkeypatch: Any):
        tracker = DRAU(_config())
        self._prep(monkeypatch, tracker)
        _FakeClient.response = _FakeResponse(500, "boom")
        meta = self._meta()
        assert asyncio.run(tracker.search_existing(meta)) == []
        assert meta["skipping"] == "DRAU"

    def test_search_paginates_until_short_page(self, monkeypatch: Any):
        tracker = DRAU(_config())
        self._prep(monkeypatch, tracker)
        pages = [
            [_entry(f"Some.Movie.2024.MULTi.1080p.WEB.x264-GRP.{i}", torrent_id=str(i)) for i in range(100)],
            [_entry("Some.Movie.2024.MULTi.1080p.WEB.x264-GRP", torrent_id="last")],
        ]

        class _Paged(_FakeClient):
            async def get(self, url: str, **kwargs: Any) -> _FakeResponse:
                _FakeClient.calls.append({"url": url, **kwargs})
                return _FakeResponse(200, pages[kwargs["params"]["offset"] // 100])

        monkeypatch.setattr(drau_module.httpx, "AsyncClient", _Paged)
        dupes = asyncio.run(tracker.search_existing(self._meta()))
        assert len(dupes) == 101
        assert [c["params"]["offset"] for c in _FakeClient.calls] == [0, 100]

    def test_french_title_adds_second_query(self, monkeypatch: Any):
        tracker = DRAU(_config())
        self._prep(monkeypatch, tracker, fr_title="Un Film")
        _FakeClient.response = _FakeResponse(200, [])
        asyncio.run(tracker.search_existing(self._meta()))
        assert [c["params"]["q"] for c in _FakeClient.calls] == ["Some Movie", "Un Film"]

    def test_failed_language_check_skips_tracker(self, monkeypatch: Any):
        tracker = DRAU(_config())
        self._prep(monkeypatch, tracker, checks=False)
        meta = self._meta()
        assert asyncio.run(tracker.search_existing(meta)) == []
        assert meta["skipping"] == "DRAU"
        assert _FakeClient.calls == []


class TestUpload:
    def _meta(self, tmp_path: Any) -> dict[str, Any]:
        uuid = "Some.Movie.2024.1080p.WEB-GRP"
        (tmp_path / "tmp" / uuid).mkdir(parents=True)
        (tmp_path / "tmp" / uuid / "[DRAU].torrent").write_bytes(b"fake-torrent")
        (tmp_path / "tmp" / uuid / "MEDIAINFO_CLEANPATH.txt").write_text("General\nComplete name : x.mkv\nfake mediainfo")
        return {
            "base_dir": str(tmp_path),
            "uuid": uuid,
            "category": "MOVIE",
            "title": "Some Movie",
            "year": "2024",
            "tmdb_id": 693134,
            "type": "WEBDL",
            "tag": "-GRP",
            "edition": "EXTENDED",
            "poster": "https://image.tmdb.org/t/p/original/p.jpg",
            "debug": False,
            "tracker_status": {"DRAU": {}},
        }

    def _patch(self, monkeypatch: Any, tracker: DRAU, response: _FakeResponse) -> None:
        monkeypatch.setattr(drau_module.httpx, "AsyncClient", _FakeClient)
        _FakeClient.response = response
        _FakeClient.captured = {}
        _FakeClient.calls = []

        async def fake_create(meta: Any, tracker_name: Any, source_flag: Any, **kwargs: Any) -> None:
            _FakeClient.captured = {"create": {"source_flag": source_flag, **kwargs}}

        async def fake_get_name(meta: Any) -> dict[str, str]:
            return {"name": "Some.Movie.2024.1080p.WEB-GRP"}

        async def fake_desc(meta: Any) -> str:
            meta["fr_synopsis"] = "Un synopsis."
            return "desc"

        async def fake_fr_title(meta: Any) -> str:
            return "Un Film"

        class _FakeTorrent:
            infohash = "ab" * 20

        monkeypatch.setattr(tracker.common, "create_torrent_for_upload", fake_create)
        monkeypatch.setattr(tracker, "get_name", fake_get_name)
        monkeypatch.setattr(tracker, "_build_description", fake_desc)
        monkeypatch.setattr(tracker, "_get_french_title", fake_fr_title)
        monkeypatch.setattr(drau_module.Torrent, "read", staticmethod(lambda _path: _FakeTorrent()))

    def test_upload_sends_required_contract(self, monkeypatch: Any, tmp_path: Any):
        tracker = DRAU(_config())
        self._patch(monkeypatch, tracker, _FakeResponse(201, {"id": "Xk3Qm9", "infohash": "ab" * 20, "status": "approved", "awaiting_validation": True}))
        meta = self._meta(tmp_path)
        assert asyncio.run(tracker.upload(meta, "")) is True

        sent = _FakeClient.captured
        assert sent["url"] == "https://draupnirr.xyz/api/upload"
        assert sent["headers"]["X-Api-Key"] == "test-passkey"
        data = sent["data"]
        assert data["category"] == "films-film"
        assert data["description"] == "desc"
        assert data["description_format"] == "bbcode"
        assert "fake mediainfo" in data["mediainfo"]
        assert data["meta[work_title]"] == "Un Film"
        assert data["meta[year]"] == "2024"
        assert data["meta[tmdb_id]"] == "693134"
        assert data["meta[tmdb_type]"] == "movie"
        assert data["meta[poster_url]"] == "https://image.tmdb.org/t/p/original/p.jpg"
        assert data["meta[synopsis]"] == "Un synopsis."
        assert data["meta[facets][source]"] == "WEB.DL"
        assert data["meta[facets][group]"] == "GRP"
        assert data["meta[facets][edition]"] == "EXTENDED"
        assert "meta[episode]" not in data
        assert sent["files"]["torrent"][1] == b"fake-torrent"
        assert b"fake mediainfo" in sent["files"]["nfo"][1]
        assert meta["tracker_status"]["DRAU"]["torrent_id"] == "Xk3Qm9"

    def test_torrent_is_created_with_the_passkey_announce_and_source_tag(self, monkeypatch: Any, tmp_path: Any):
        config = _config()
        tracker = DRAU(config)
        self._patch(monkeypatch, tracker, _FakeResponse(201, {"id": "Xk3Qm9"}))
        captured: dict[str, Any] = {}

        async def fake_create(meta: Any, tracker_name: Any, source_flag: Any, **kwargs: Any) -> None:
            captured.update(source_flag=source_flag, announce_url=config["TRACKERS"]["DRAU"].get("announce_url"))

        monkeypatch.setattr(tracker.common, "create_torrent_for_upload", fake_create)
        asyncio.run(tracker.upload(self._meta(tmp_path), ""))
        # The NFO re-creation path reads the announce from the config block too.
        assert captured == {"source_flag": "DRAUPNIRR", "announce_url": "https://draupnirr.xyz/announce/test-passkey"}

    def test_tv_upload_sends_the_episode_field(self, monkeypatch: Any, tmp_path: Any):
        tracker = DRAU(_config())
        self._patch(monkeypatch, tracker, _FakeResponse(201, {"id": "Xk3Qm9"}))
        meta = self._meta(tmp_path)
        meta.update(category="TV", season="S01", episode="E03")
        asyncio.run(tracker.upload(meta, ""))
        data = _FakeClient.captured["data"]
        assert data["category"] == "series-serie-tv"
        assert data["meta[episode]"] == "S01E03"
        assert data["meta[tmdb_type]"] == "tv"

    def test_upload_saves_the_description(self, monkeypatch: Any, tmp_path: Any):
        tracker = DRAU(_config())
        self._patch(monkeypatch, tracker, _FakeResponse(201, {"id": "Xk3Qm9"}))
        meta = self._meta(tmp_path)
        asyncio.run(tracker.upload(meta, ""))
        assert (tmp_path / "tmp" / meta["uuid"] / "[DRAU]DESCRIPTION.txt").read_text(encoding="utf-8") == "desc"

    def test_upload_422_fails_fast_with_the_site_reason(self, monkeypatch: Any, tmp_path: Any):
        tracker = DRAU(_config())
        self._patch(monkeypatch, tracker, _FakeResponse(422, {"error": "doublon : la release existe déjà"}))
        meta = self._meta(tmp_path)
        assert asyncio.run(tracker.upload(meta, "")) is False
        assert "doublon" in str(meta["tracker_status"]["DRAU"]["status_message"])
        assert len(_posts()) == 1

    def test_upload_server_error_is_retried(self, monkeypatch: Any, tmp_path: Any):
        tracker = DRAU(_config())
        self._patch(monkeypatch, tracker, _FakeResponse(503, "<html>down</html>"))
        monkeypatch.setattr(drau_module, "RETRY_DELAY", 0.0)
        meta = self._meta(tmp_path)
        assert asyncio.run(tracker.upload(meta, "")) is False
        assert len(_posts()) == 3
        assert "HTTP 503" in str(meta["tracker_status"]["DRAU"]["status_message"])

    def test_422_duplicate_of_our_own_torrent_is_reconciled_as_success(self, monkeypatch: Any, tmp_path: Any):
        tracker = DRAU(_config())
        self._patch(monkeypatch, tracker, _FakeResponse(422, {"error": "doublon"}))

        class _Reconciling(_FakeClient):
            async def get(self, url: str, **kwargs: Any) -> _FakeResponse:
                _FakeClient.calls.append({"method": "GET", "url": url, **kwargs})
                return _FakeResponse(200, {"id": "Xk3Qm9", "infohash": "ab" * 20, "status": "approved"})

        monkeypatch.setattr(drau_module.httpx, "AsyncClient", _Reconciling)
        meta = self._meta(tmp_path)
        assert asyncio.run(tracker.upload(meta, "")) is True
        assert meta["tracker_status"]["DRAU"]["torrent_id"] == "Xk3Qm9"
        assert [c["url"] for c in _FakeClient.calls if c["method"] == "GET"] == ["https://draupnirr.xyz/api/torrents/" + "ab" * 20]

    def test_timed_out_post_that_went_through_is_reconciled_without_a_second_post(self, monkeypatch: Any, tmp_path: Any):
        tracker = DRAU(_config())
        self._patch(monkeypatch, tracker, _FakeResponse(500, {}))
        monkeypatch.setattr(drau_module, "RETRY_DELAY", 0.0)

        class _Flaky(_FakeClient):
            async def post(self, url: str, **kwargs: Any) -> _FakeResponse:
                _FakeClient.calls.append({"method": "POST", "url": url, **kwargs})
                raise drau_module.httpx.ReadTimeout("slow")

            async def get(self, url: str, **kwargs: Any) -> _FakeResponse:
                _FakeClient.calls.append({"method": "GET", "url": url, **kwargs})
                return _FakeResponse(200, {"id": "Xk3Qm9", "infohash": "ab" * 20, "status": "approved", "awaiting_validation": True})

        monkeypatch.setattr(drau_module.httpx, "AsyncClient", _Flaky)
        meta = self._meta(tmp_path)
        assert asyncio.run(tracker.upload(meta, "")) is True
        assert len(_posts()) == 1
        assert meta["tracker_status"]["DRAU"]["torrent_id"] == "Xk3Qm9"

    def test_debug_mode_does_not_post(self, monkeypatch: Any, tmp_path: Any):
        tracker = DRAU(_config())
        self._patch(monkeypatch, tracker, _FakeResponse(500, {}))
        meta = self._meta(tmp_path)
        meta["debug"] = True
        assert asyncio.run(tracker.upload(meta, "")) is True
        assert _FakeClient.calls == []


class TestFlattenSourceBbcode:
    def test_unit3d_only_tags_are_stripped(self):
        text = "[center][size=28][b]Title[/b][/size][/center]\n[comparison=a,b]x[/comparison]\n[h1]Notes[/h1]\n\n\n[font=Arial]ok[/font]"
        assert DRAU._flatten_source_bbcode(text) == "[b]Title[/b]\nNotes\n\nok"


def test_drau_is_registered() -> None:
    from src.trackersetup import nfo_auto_trackers, other_api_trackers, tracker_class_map

    assert tracker_class_map["DRAU"] is DRAU
    assert "DRAU" in other_api_trackers
    assert "DRAU" in nfo_auto_trackers


class TestCrossSeedHeaders:
    def test_key_only_for_the_https_site_origin(self):
        tracker = DRAU(_config())
        assert tracker.cross_seed_headers("https://draupnirr.xyz/api/torrents/abc/download") == {"X-Api-Key": _config()["TRACKERS"]["DRAU"]["api_key"]}
        assert tracker.cross_seed_headers("http://draupnirr.xyz/api/torrents/abc/download") is None
        assert tracker.cross_seed_headers("https://evil.example/api/torrents/abc/download") is None
        assert tracker.cross_seed_headers("https://draupnirr.xyz.evil.example/x") is None


# Trimmed copy of GET /api/slots, in the site's order.
_SLOTS: list[dict[str, Any]] = [
    {
        "code": "OPTI-1080-HDR",
        "criteria": {
            "resolution": "1080p",
            "source": ["Bluray", "UHD.Bluray", "BDRip", "HDLight"],
            "codec_family": ["HEVC"],
            "audio_class": "lossy",
            "hdr": True,
            "channels_max": "5.1",
            "bitrate_min": None,
            "bitrate_max": 3000,
        },
    },
    {
        "code": "OPTI-1080-SDR-BD",
        "criteria": {
            "resolution": "1080p",
            "source": ["Bluray", "UHD.Bluray", "BDRip"],
            "codec_family": ["HEVC"],
            "audio_class": "lossy",
            "hdr": False,
            "channels_max": "5.1",
            "bitrate_min": None,
            "bitrate_max": 3000,
        },
    },
    {
        "code": "OPTI-1080-SDR-WR",
        "criteria": {
            "resolution": "1080p",
            "source": ["HDLight", "WEBRip", "WEB.DL", "WEB"],
            "codec_family": ["HEVC"],
            "audio_class": "lossy",
            "hdr": False,
            "channels_max": "5.1",
            "bitrate_min": None,
            "bitrate_max": 3000,
        },
    },
    {
        "code": "OPTI-2160-HDR-4KL",
        "criteria": {
            "resolution": "2160p",
            "source": ["Bluray.4KLight"],
            "codec_family": ["HEVC"],
            "audio_class": "lossy",
            "hdr": True,
            "channels_max": "5.1",
            "bitrate_min": None,
            "bitrate_max": 10000,
        },
    },
    {
        "code": "HCOPT-1080-WEB",
        "criteria": {
            "resolution": "1080p",
            "source": ["WEB.DL", "WEB"],
            "codec_family": None,
            "audio_class": None,
            "hdr": None,
            "channels_max": None,
            "bitrate_min": None,
            "bitrate_max": None,
        },
    },
    {
        "code": "HCOPT-1080-BD-H265",
        "criteria": {
            "resolution": "1080p",
            "source": ["Bluray", "UHD.Bluray", "BDRip"],
            "codec_family": ["HEVC"],
            "audio_class": None,
            "hdr": None,
            "channels_max": None,
            "bitrate_min": 3000,
            "bitrate_max": None,
        },
    },
    {
        "code": "HCOPT-2160-4KL-H265",
        "criteria": {
            "resolution": "2160p",
            "source": ["Bluray.4KLight"],
            "codec_family": ["HEVC"],
            "audio_class": None,
            "hdr": None,
            "channels_max": None,
            "bitrate_min": 10000,
            "bitrate_max": None,
        },
    },
    {
        "code": "PURE-BD-VC1",
        "criteria": {
            "resolution": "1080p",
            "source": ["Bluray.Remux"],
            "codec_family": ["VC1"],
            "audio_class": None,
            "hdr": None,
            "channels_max": None,
            "bitrate_min": None,
            "bitrate_max": None,
        },
    },
    {
        "code": "PURE-BD-REMUX",
        "criteria": {
            "resolution": "1080p",
            "source": ["Bluray.Remux"],
            "codec_family": None,
            "audio_class": None,
            "hdr": None,
            "channels_max": None,
            "bitrate_min": None,
            "bitrate_max": None,
        },
    },
    {"code": "PURE-BD-BDMV", "criteria": {}},
]


def _slot_meta(**overrides: Any) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "category": "MOVIE",
        "tmdb_id": 123,
        "resolution": "1080p",
        "type": "ENCODE",
        "uuid": "Some.Movie.2024.1080p.Bluray.x265-GRP",
        "video_encode": "x265",
        "audio": "DD+ 5.1",
        "channels": "5.1",
        "hdr": "",
        "edition": "",
        "webdv": "",
        "mediainfo": {"media": {"track": [{"@type": "General", "OverallBitRate": "2500000"}]}},
        "tracker_status": {"DRAU": {}},
    }
    meta.update(overrides)
    return meta


class TestSlots:
    def test_source_facet(self):
        assert DRAU._source_facet({"type": "REMUX"}) == "Bluray.Remux"
        assert DRAU._source_facet({"type": "ENCODE", "uuid": "Some.Movie.2024.2160p.Bluray.4KLight.x265-GRP"}) == "Bluray.4KLight"
        assert DRAU._source_facet({"type": "ENCODE", "uuid": "Some.Movie.2024.1080p.HDLight.x264-GRP"}) == "HDLight"
        assert DRAU._source_facet({"type": "ENCODE", "uuid": "Some.Movie.2024.1080p.Bluray.x264-GRP"}) == "Bluray"
        assert DRAU._source_facet({"type": "WEBDL"}) == "WEB.DL"

    def test_find_slot_follows_the_criteria(self):
        find = DRAU(_config())._find_slot
        assert find(_slot_meta(), _SLOTS) == "OPTI-1080-SDR-BD"
        # Above the 3 000 kb/s threshold an HEVC Bluray encode is HC Optimisé.
        assert find(_slot_meta(mediainfo={"media": {"track": [{"@type": "General", "OverallBitRate": "9000000"}]}}), _SLOTS) == "HCOPT-1080-BD-H265"
        assert find(_slot_meta(type="WEBDL", video_encode="", video_codec="AVC", audio="TrueHD Atmos 7.1", channels="7.1"), _SLOTS) == "HCOPT-1080-WEB"
        assert find(_slot_meta(type="REMUX", video_encode="", video_codec="VC-1"), _SLOTS) == "PURE-BD-VC1"
        assert find(_slot_meta(type="REMUX", video_encode="", video_codec="AVC"), _SLOTS) == "PURE-BD-REMUX"
        assert find(_slot_meta(is_disc="BDMV", type="DISC"), _SLOTS) == "PURE-BD-BDMV"
        four_k_light = _slot_meta(resolution="2160p", hdr="HDR", uuid="Some.Movie.2024.2160p.Bluray.4KLight.HDR10.x265-GRP")
        assert find(four_k_light, _SLOTS) == "OPTI-2160-HDR-4KL"
        # No bitrate: neither side of the threshold can be decided.
        assert find(_slot_meta(mediainfo={}), _SLOTS) == ""

    @staticmethod
    def _tracker(monkeypatch: Any, slot: dict[str, Any], edition: str = "theatrical", code: str = "OPTI-1080-SDR-BD") -> DRAU:
        """A tracker whose API knows ``slot`` for ``edition`` and answers
        "free" for any other edition, like the site does."""
        tracker = DRAU(_config())
        free = {"state": "free", "occupant": None, "coexisting": [], "stack": []}

        async def fake_get_json(path: str, params: Any = None) -> Any:
            if path == "/api/slots":
                return _SLOTS
            assert path == f"/api/works/movie/123/slots/{code}"
            return slot if params["edition"] == edition else free

        async def fake_audio(meta: Any) -> str:
            return meta.get("_audio", "MULTI.VFF")

        monkeypatch.setattr(tracker, "_get_json", fake_get_json)
        monkeypatch.setattr(tracker, "_build_audio_string", fake_audio)
        return tracker

    def _check(self, monkeypatch: Any, meta: dict[str, Any], slot: dict[str, Any], edition: str = "theatrical", code: str = "OPTI-1080-SDR-BD") -> Any:
        return asyncio.run(self._tracker(monkeypatch, slot, edition, code)._check_slot(meta))

    @staticmethod
    def _held(name: str, *stacked: str) -> dict[str, Any]:
        occupant = {"id": "Xk3Qm9", "name": name, "size_bytes": 10, "download_url": "https://draupnirr.xyz/api/torrents/x/download"}
        stack = [{**occupant, "rank": 1, "slot_state": "occupant"}]
        stack += [{"id": f"s{i}", "name": n, "size_bytes": 10, "rank": i + 2, "slot_state": "stacked"} for i, n in enumerate(stacked)]
        return {"state": "occupied", "occupant": occupant, "coexisting": [], "stack": stack}

    def test_held_slot_is_flagged_and_returned_as_dupe(self, monkeypatch: Any):
        meta = _slot_meta()
        holders = self._check(monkeypatch, meta, self._held("Some.Movie.2024.MULTi.VFF.1080p.Bluray.AC3.5.1.x265-OTHER"))
        assert [h["name"] for h in holders] == ["Some.Movie.2024.MULTi.VFF.1080p.Bluray.AC3.5.1.x265-OTHER"]
        assert meta["_drau_slot_occupied"] is True

    def test_dupes_are_the_whole_stack(self, monkeypatch: Any):
        slot = self._held("Some.Movie.2024.MULTi.VFF.1080p.Bluray.AC3.5.1.x265-OTHER", "Some.Movie.2024.MULTi.1080p.Bluray.AC3.5.1.x265-THIRD")
        holders = self._check(monkeypatch, _slot_meta(), slot)
        assert [h["name"] for h in holders] == ["Some.Movie.2024.MULTi.VFF.1080p.Bluray.AC3.5.1.x265-OTHER", "Some.Movie.2024.MULTi.1080p.Bluray.AC3.5.1.x265-THIRD"]

    def test_search_existing_returns_the_stack_without_a_name_search(self, monkeypatch: Any):
        tracker = self._tracker(monkeypatch, self._held("Some.Movie.2024.MULTi.VFF.1080p.Bluray.AC3.5.1.x265-OTHER"))

        async def fake_checks(meta: Any) -> bool:
            return True

        async def no_name_search(query: str) -> Any:
            raise AssertionError("name search must not run once the slot is known")

        monkeypatch.setattr(tracker, "get_additional_checks", fake_checks)
        monkeypatch.setattr(tracker, "_search_catalogue", no_name_search)
        dupes = asyncio.run(tracker.search_existing(_slot_meta()))
        assert [d["name"] for d in dupes] == ["Some.Movie.2024.MULTi.VFF.1080p.Bluray.AC3.5.1.x265-OTHER"]

    def test_unplaceable_release_falls_back_to_the_name_search(self, monkeypatch: Any):
        # No bitrate: the slot cannot be determined.
        assert self._check(monkeypatch, _slot_meta(mediainfo={}), self._held("x")) is None

    def test_free_slot_and_other_edition_are_not_flagged(self, monkeypatch: Any):
        meta = _slot_meta()
        assert self._check(monkeypatch, meta, {"state": "free", "occupant": None, "coexisting": [], "stack": []}) == []
        meta = _slot_meta(edition="Extended")
        assert self._check(monkeypatch, meta, self._held("Some.Movie.2024.MULTi.1080p.Bluray.AC3.5.1.x265-OTHER")) == []
        assert "_drau_slot_occupied" not in meta

    def test_edition_key_matches_the_site(self, monkeypatch: Any):
        meta = _slot_meta(edition="Extended Remastered")
        assert self._check(monkeypatch, meta, self._held("Some.Movie.2024.EXTENDED.REMASTERED.MULTi.1080p.Bluray.x265-OTHER"), edition="EXTENDED.REMASTERED")
        assert meta["_drau_slot_occupied"] is True

    def test_vfq_coexists_with_a_vff_holder(self, monkeypatch: Any):
        meta = _slot_meta(_audio="VFQ")
        assert self._check(monkeypatch, meta, self._held("Some.Movie.2024.VFF.1080p.Bluray.AC3.5.1.x265-OTHER")) == []
        assert "_drau_slot_occupied" not in meta

    def test_dv_coexists_with_an_hdr10_holder(self, monkeypatch: Any):
        meta = _slot_meta(hdr="DV HDR")
        assert self._check(monkeypatch, meta, self._held("Some.Movie.2024.MULTi.VFF.1080p.Bluray.HDR10.x265-OTHER"), code="OPTI-1080-HDR") == []
        assert "_drau_slot_occupied" not in meta
        # Same DV axis as the holder: stacked.
        meta = _slot_meta(hdr="DV HDR")
        assert self._check(monkeypatch, meta, self._held("Some.Movie.2024.MULTi.VFF.1080p.Bluray.DV.HDR10.x265-OTHER"), code="OPTI-1080-HDR")
        assert meta["_drau_slot_occupied"] is True

    def test_unattended_upload_skips_a_held_slot(self, monkeypatch: Any):
        tracker = DRAU(_config())
        meta = _slot_meta(unattended=True, _drau_slot_occupied=True)
        assert asyncio.run(tracker.upload(meta, "")) is False
        assert meta["tracker_status"]["DRAU"]["status_message"] == "slot occupied — skipped in unattended mode"
