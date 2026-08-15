# V3X (v3x.club) — custom-API French tracker. Covers category mapping, the
# public-search dupe check, and the multipart upload contract:
# file + name + categoryId + rightsDeclared, Bearer auth.

import asyncio
from typing import Any

import src.trackers.V3X as v3x_module
from src.trackers.V3X import V3X


def _config() -> dict[str, Any]:
    return {
        "TRACKERS": {"V3X": {"api_key": "test-key", "announce_url": "https://api.v3x.club/announce/FAKE"}},
        "DEFAULT": {"tmdb_api": "fake"},
    }


class _FakeResponse:
    def __init__(self, status_code: int, payload: Any):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload


class _FakeClient:
    response: _FakeResponse = _FakeResponse(200, {})
    captured: dict[str, Any] = {}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass

    async def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        _FakeClient.captured = {"url": url, **kwargs}
        return _FakeClient.response

    async def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        _FakeClient.captured = {"url": url, **kwargs}
        return _FakeClient.response


class TestCategoryMapping:
    def _cat(self, meta: dict[str, Any]) -> str:
        return asyncio.run(V3X(_config()).get_category_id(meta))

    def test_movie_is_film(self):
        assert self._cat({"category": "MOVIE"}) == "8"

    def test_tv_is_serie(self):
        assert self._cat({"category": "TV"}) == "9"

    def test_anime_movie_and_series(self):
        assert self._cat({"category": "MOVIE", "anime": True}) == "2"
        assert self._cat({"category": "TV", "anime": True}) == "3"


class TestSearchExisting:
    def test_search_maps_listing_to_dupes(self, monkeypatch: Any):
        monkeypatch.setattr(v3x_module.httpx, "AsyncClient", _FakeClient)
        _FakeClient.response = _FakeResponse(
            200,
            {"torrents": [{"id": "uuid-1", "slug": "some-slug", "name": "Some Movie (2024)", "size": 123}]},
        )
        dupes = asyncio.run(V3X(_config()).search_existing({"title": "Some Movie"}))
        assert dupes == [{"name": "Some Movie (2024)", "size": 123, "link": "https://v3x.club/torrents/some-slug"}]
        assert _FakeClient.captured["params"]["search"] == "Some Movie"

    def test_search_http_error_returns_empty(self, monkeypatch: Any):
        monkeypatch.setattr(v3x_module.httpx, "AsyncClient", _FakeClient)
        _FakeClient.response = _FakeResponse(503, {})
        assert asyncio.run(V3X(_config()).search_existing({"title": "X"})) == []

    def test_empty_title_skips_search(self):
        assert asyncio.run(V3X(_config()).search_existing({})) == []


class TestUpload:
    def _meta(self, tmp_path: Any) -> dict[str, Any]:
        uuid = "Some.Movie.2024.1080p.WEB-GRP"
        (tmp_path / "tmp" / uuid).mkdir(parents=True)
        (tmp_path / "tmp" / uuid / "[V3X].torrent").write_bytes(b"fake-torrent")
        (tmp_path / "tmp" / uuid / "MEDIAINFO_CLEANPATH.txt").write_text("General\nfake mediainfo")
        return {
            "base_dir": str(tmp_path),
            "uuid": uuid,
            "category": "MOVIE",
            "tmdb_id": 693134,
            "anon": False,
            "debug": False,
            "tracker_status": {"V3X": {}},
        }

    def _patch(self, monkeypatch: Any, tracker: V3X, response: _FakeResponse) -> None:
        monkeypatch.setattr(v3x_module.httpx, "AsyncClient", _FakeClient)
        _FakeClient.response = response
        _FakeClient.captured = {}

        async def fake_create(meta: Any, tracker_name: Any, source_flag: Any) -> None:
            pass

        async def fake_get_name(meta: Any) -> dict[str, str]:
            return {"name": "Some.Movie.2024.1080p.WEB-GRP"}

        async def fake_desc(*args: Any, **kwargs: Any) -> str:
            return "desc"

        monkeypatch.setattr(tracker.common, "create_torrent_for_upload", fake_create)
        monkeypatch.setattr(tracker, "get_name", fake_get_name)
        monkeypatch.setattr(tracker, "_build_description", fake_desc)

    def test_upload_sends_required_contract(self, monkeypatch: Any, tmp_path: Any):
        tracker = V3X(_config())
        self._patch(monkeypatch, tracker, _FakeResponse(201, {"id": "new-uuid"}))
        meta = self._meta(tmp_path)
        assert asyncio.run(tracker.upload(meta, "")) is True

        sent = _FakeClient.captured
        assert sent["url"] == "https://api.v3x.club/api/torrents"
        assert sent["headers"]["Authorization"] == "Bearer test-key"
        assert sent["data"]["rightsDeclared"] == "true"
        assert sent["data"]["categoryId"] == "8"
        assert sent["data"]["tmdbId"] == "693134"
        assert "fake mediainfo" in sent["data"]["nfo"]
        assert sent["files"]["file"][1] == b"fake-torrent"
        assert meta["tracker_status"]["V3X"]["torrent_id"] == "new-uuid"

    def test_upload_api_error_is_reported(self, monkeypatch: Any, tmp_path: Any):
        tracker = V3X(_config())
        self._patch(monkeypatch, tracker, _FakeResponse(400, {"error": "invalid_category"}))
        meta = self._meta(tmp_path)
        assert asyncio.run(tracker.upload(meta, "")) is False
        assert "invalid_category" in str(meta["tracker_status"]["V3X"]["status_message"])

    def test_debug_mode_does_not_post(self, monkeypatch: Any, tmp_path: Any):
        tracker = V3X(_config())
        self._patch(monkeypatch, tracker, _FakeResponse(500, {}))
        meta = self._meta(tmp_path)
        meta["debug"] = True
        assert asyncio.run(tracker.upload(meta, "")) is True
        assert _FakeClient.captured == {}


def test_v3x_is_registered() -> None:
    from src.trackersetup import other_api_trackers, tracker_class_map

    assert tracker_class_map["V3X"] is V3X
    assert "V3X" in other_api_trackers


class TestDescription:
    def test_description_follows_tracker_template(self, monkeypatch: Any):
        tracker = V3X(_config())

        async def fake_localized(*args: Any, **kwargs: Any) -> dict[str, Any]:
            return {"overview": "Un synopsis en français."}

        async def fake_audio_string(meta: Any) -> str:
            return "MULTI.VFF"

        monkeypatch.setattr(tracker.tmdb_manager, "get_tmdb_localized_data", fake_localized)
        monkeypatch.setattr(tracker, "_build_audio_string", fake_audio_string)
        meta = {
            "poster": "https://image.tmdb.org/t/p/original/xyz.jpg",
            "overview": "English fallback.",
            "source": "BluRay",
            "resolution": "2160p",
            "video_encode": "x265",
            "audio": "DTS-HD MA 5.1",
            "subtitle_languages": ["French", "English"],
            "image_list": [{"img_url": "https://img.example.invalid/t.md.png", "web_url": "https://img.example.invalid/v"}],
        }
        desc = asyncio.run(tracker._build_description(meta))
        assert "/t/p/w500/xyz.jpg" in desc  # poster resized
        assert "Un synopsis en français." in desc  # French synopsis preferred
        assert "[b]Source :[/b] BluRay" in desc
        assert "[b]Qualité vidéo :[/b] 2160p" in desc
        assert "[b]Audio :[/b] MULTI.VFF — DTS-HD MA 5.1" in desc
        assert "[b]Sous-titres :[/b] French, English" in desc
        assert "[url=https://img.example.invalid/v][img]https://img.example.invalid/t.md.png[/img][/url]" in desc

    def test_description_survives_missing_data(self, monkeypatch: Any):
        tracker = V3X(_config())

        async def fake_localized(*args: Any, **kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("tmdb down")

        async def fake_audio_string(meta: Any) -> str:
            return ""

        monkeypatch.setattr(tracker.tmdb_manager, "get_tmdb_localized_data", fake_localized)
        monkeypatch.setattr(tracker, "_build_audio_string", fake_audio_string)
        desc = asyncio.run(tracker._build_description({"overview": "Fallback only."}))
        assert "Fallback only." in desc
