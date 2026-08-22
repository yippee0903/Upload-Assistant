# V3X (v3x.club) — custom-API French tracker. Covers category mapping, the
# public-search dupe check, and the multipart upload contract:
# file + name + categoryId + rightsDeclared, Bearer auth.

import asyncio
from typing import Any

import pytest

import src.trackers.V3X as v3x_module
from src.trackers.V3X import V3X


def _config() -> dict[str, Any]:
    return {
        "TRACKERS": {"V3X": {"api_key": "test-key", "announce_url": "https://api.v3x.club/announce/FAKE"}},
        "DEFAULT": {"tmdb_api": "fake"},
        "TORRENT_CLIENTS": {"qbt": {"torrent_client": "qbit", "linking": "hardlink"}},
    }


class _FakeResponse:
    def __init__(self, status_code: int, payload: Any):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload

    @property
    def text(self) -> str:
        return self._payload if isinstance(self._payload, str) else ""


def _rss(*torrents: dict[str, Any], size_as_attr: bool = False) -> str:
    """Torznab feed with one <item> per torrent ({id, name, size}).

    V3X emits both a plain <size> and the standard torznab:attr; the flag
    picks which one the fake feed carries.
    """

    def _size(t: dict[str, Any]) -> str:
        if size_as_attr:
            return f'<torznab:attr name="size" value="{t.get("size", 0)}" />'
        return f"<size>{t.get('size', 0)}</size>"

    items = "".join(f"<item><title>{t['name']}</title><guid isPermaLink=\"true\">https://v3x.club/torrents/{t['id']}</guid>{_size(t)}</item>" for t in torrents)
    return f'<?xml version="1.0"?><rss version="2.0" xmlns:torznab="http://torznab.com/schemas/2015/feed"><channel><title>V3X</title>{items}</channel></rss>'


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
    def _prep(self, monkeypatch: Any, tracker: V3X, checks: bool = True, fr_title: str = "") -> None:
        async def fake_checks(meta: Any) -> bool:
            return checks

        async def fake_fr(meta: Any) -> str:
            return fr_title

        async def fake_enrich(dupes: Any, *, debug: bool = False) -> None:
            return None

        async def fake_login() -> Any:
            return v3x_module.httpx.Cookies()

        monkeypatch.setattr(tracker, "get_additional_checks", fake_checks)
        monkeypatch.setattr(tracker, "_get_french_title", fake_fr)
        monkeypatch.setattr(tracker, "_enrich_with_files", fake_enrich)
        monkeypatch.setattr(tracker, "_login_session_cookies", fake_login)

    def test_search_maps_listing_to_dupes(self, monkeypatch: Any):
        monkeypatch.setattr(v3x_module.httpx, "AsyncClient", _FakeClient)
        _FakeClient.response = _FakeResponse(200, _rss({"id": "uuid-1", "name": "Some Movie (2024)", "size": 123}))
        tracker = V3X(_config())
        self._prep(monkeypatch, tracker)
        dupes = asyncio.run(tracker.search_existing({"title": "Some Movie"}))
        assert dupes == [{"name": "Some Movie (2024)", "size": 123, "link": "https://v3x.club/torrents/uuid-1", "id": "uuid-1"}]
        # Full cleaned title (the API matches ordered words, separator-agnostic)
        assert _FakeClient.captured["params"]["q"] == "Some Movie"
        # torznab only reads the key from the query string (Bearer is rejected there)
        assert _FakeClient.captured["params"]["apikey"] == "test-key"
        assert _FakeClient.captured["url"].endswith("/torznab/api")

    def test_size_read_from_torznab_attr(self):
        items = V3X._parse_torznab(_rss({"id": "u1", "name": "X", "size": 456}, size_as_attr=True))
        assert items == [{"title": "X", "size": 456, "link": "https://v3x.club/torrents/u1", "id": "u1"}]

    def test_search_still_full_at_the_offset_cap_fails_closed(self, monkeypatch: Any):
        full_page = _rss(*({"id": f"u{i}", "name": f"Some.Movie.2024.1080p.WEB-G{i}", "size": 1} for i in range(100)))

        class _EndlessClient(_FakeClient):
            async def get(self, url: str, **kwargs: Any) -> _FakeResponse:
                return _FakeResponse(200, full_page)

        monkeypatch.setattr(v3x_module.httpx, "AsyncClient", _EndlessClient)
        tracker = V3X(_config())
        self._prep(monkeypatch, tracker)
        meta: dict[str, Any] = {"title": "Some Movie"}
        assert asyncio.run(tracker.search_existing(meta)) == []
        assert meta["skipping"] == "V3X"

    def test_search_filters_irrelevant_results(self, monkeypatch: Any):
        monkeypatch.setattr(v3x_module.httpx, "AsyncClient", _FakeClient)
        _FakeClient.response = _FakeResponse(
            200,
            _rss(
                {"id": "u1", "name": "Some.Movie.2024.1080p.WEB-GRP", "size": 1},
                {"id": "u2", "name": "Other.Movie.2024.1080p.WEB-GRP", "size": 2},
                {"id": "u3", "name": "Some.Movie.2024.2160p.WEB-GRP", "size": 3},
            ),
        )
        tracker = V3X(_config())
        self._prep(monkeypatch, tracker)
        meta = {"title": "Some Movie", "year": 2024, "resolution": "1080p"}
        dupes = asyncio.run(tracker.search_existing(meta))
        assert [d["name"] for d in dupes] == ["Some.Movie.2024.1080p.WEB-GRP"]

    def test_search_http_error_fails_closed(self, monkeypatch: Any):
        monkeypatch.setattr(v3x_module.httpx, "AsyncClient", _FakeClient)
        _FakeClient.response = _FakeResponse(503, {})
        tracker = V3X(_config())
        self._prep(monkeypatch, tracker)
        meta: dict[str, Any] = {"title": "X"}
        assert asyncio.run(tracker.search_existing(meta)) == []
        assert meta["skipping"] == "V3X"

    def test_empty_title_skips_search(self, monkeypatch: Any):
        tracker = V3X(_config())
        self._prep(monkeypatch, tracker)
        assert asyncio.run(tracker.search_existing({})) == []

    def test_failed_language_check_skips_tracker(self, monkeypatch: Any):
        tracker = V3X(_config())
        self._prep(monkeypatch, tracker, checks=False)
        meta: dict[str, Any] = {"title": "X"}
        assert asyncio.run(tracker.search_existing(meta)) == []
        assert meta["skipping"] == "V3X"

    def test_search_paginates_until_short_page(self, monkeypatch: Any):
        # No total in the feed: a full page (100) means "maybe more", a short one ends the walk.
        full_page = [{"id": f"u{i}", "name": f"Some.Movie.2024.1080p.WEB-G{i}", "size": i} for i in range(100)]
        pages = {0: _rss(*full_page), 100: _rss({"id": "u100", "name": "Some.Movie.2024.1080p.WEB-BBB", "size": 2})}

        class _PagingClient(_FakeClient):
            async def get(self, url: str, **kwargs: Any) -> _FakeResponse:
                offset = kwargs.get("params", {}).get("offset", 0)
                return _FakeResponse(200, pages[offset])

        monkeypatch.setattr(v3x_module.httpx, "AsyncClient", _PagingClient)
        tracker = V3X(_config())
        self._prep(monkeypatch, tracker)
        dupes = asyncio.run(tracker.search_existing({"title": "Some Movie"}))
        assert len(dupes) == 101
        assert dupes[-1]["name"] == "Some.Movie.2024.1080p.WEB-BBB"

    def test_french_title_adds_second_query(self, monkeypatch: Any):
        seen_queries: list[str] = []

        class _RecordingClient(_FakeClient):
            async def get(self, url: str, **kwargs: Any) -> _FakeResponse:
                seen_queries.append(kwargs.get("params", {}).get("q", ""))
                return _FakeResponse(200, _rss())

        monkeypatch.setattr(v3x_module.httpx, "AsyncClient", _RecordingClient)
        tracker = V3X(_config())
        self._prep(monkeypatch, tracker, fr_title="Les Infiltrés")
        asyncio.run(tracker.search_existing({"title": "The Departed"}))
        assert seen_queries == ["The Departed", "Les Infiltres"]

    def test_enrichment_adds_file_lists(self, monkeypatch: Any):
        class _DetailClient(_FakeClient):
            async def get(self, url: str, **kwargs: Any) -> _FakeResponse:
                return _FakeResponse(200, {"files": [{"path": "a.mkv", "size": 1}, {"path": "b.srt", "size": 2}]})

        monkeypatch.setattr(v3x_module.httpx, "AsyncClient", _DetailClient)
        tracker = V3X(_config())

        async def fake_login() -> Any:
            return v3x_module.httpx.Cookies()

        monkeypatch.setattr(tracker, "_login_session_cookies", fake_login)
        dupes = [{"name": "X", "id": "uuid-1"}, {"name": "Y"}]
        asyncio.run(tracker._enrich_with_files(dupes))
        assert dupes[0]["files"] == ["a.mkv", "b.srt"]
        assert dupes[0]["file_count"] == 2
        assert "files" not in dupes[1]

    def test_login_without_cookie_is_treated_as_no_session(self, monkeypatch: Any):
        """2FA accounts get {twoFactorRequired, challenge} with no cookie: unusable unattended."""

        class _NoCookieResponse(_FakeResponse):
            cookies = v3x_module.httpx.Cookies()

        monkeypatch.setattr(v3x_module.httpx, "AsyncClient", _FakeClient)
        _FakeClient.response = _NoCookieResponse(200, {"twoFactorRequired": True, "challenge": "x"})
        cfg = _config()
        cfg["TRACKERS"]["V3X"].update({"username": "user", "password": "pass"})
        tracker = V3X(cfg)
        assert asyncio.run(tracker._login_session_cookies()) is None
        dupes = [{"name": "X", "id": "uuid-1"}]
        asyncio.run(tracker._enrich_with_files(dupes))
        assert "files" not in dupes[0]

    def test_enrichment_is_skipped_without_site_credentials(self, monkeypatch: Any):
        """The API key cannot read /torrents/{uuid}; without username/password the dupes stay name-only."""
        monkeypatch.setattr(v3x_module.httpx, "AsyncClient", _FakeClient)
        _FakeClient.captured = {}
        tracker = V3X(_config())  # no username/password in the config
        dupes = [{"name": "X", "id": "uuid-1"}]
        asyncio.run(tracker._enrich_with_files(dupes))
        assert "files" not in dupes[0]
        assert _FakeClient.captured == {}


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

        async def fake_fr_title(meta: Any) -> str:
            return ""

        monkeypatch.setattr(tracker.common, "create_torrent_for_upload", fake_create)
        monkeypatch.setattr(tracker, "get_name", fake_get_name)
        monkeypatch.setattr(tracker, "_build_description", fake_desc)
        monkeypatch.setattr(tracker, "_get_french_title", fake_fr_title)

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

    def test_upload_saves_the_description(self, monkeypatch: Any, tmp_path: Any):
        tracker = V3X(_config())
        self._patch(monkeypatch, tracker, _FakeResponse(201, {"id": "new-uuid"}))
        meta = self._meta(tmp_path)
        asyncio.run(tracker.upload(meta, ""))
        assert (tmp_path / "tmp" / meta["uuid"] / "[V3X]DESCRIPTION.txt").read_text(encoding="utf-8") == "desc"

    def test_upload_api_error_is_reported(self, monkeypatch: Any, tmp_path: Any):
        tracker = V3X(_config())
        self._patch(monkeypatch, tracker, _FakeResponse(400, {"error": "invalid_category"}))
        meta = self._meta(tmp_path)
        assert asyncio.run(tracker.upload(meta, "")) is False
        assert "invalid_category" in str(meta["tracker_status"]["V3X"]["status_message"])

    def test_upload_409_duplicate_fails_fast_with_existing_id(self, monkeypatch: Any, tmp_path: Any):
        tracker = V3X(_config())
        self._patch(monkeypatch, tracker, _FakeResponse(409, {"error": "duplicate_content", "id": "abc-123", "name": "Example.Release.2026.1080p-GRP"}))
        meta = self._meta(tmp_path)
        assert asyncio.run(tracker.upload(meta, "")) is False
        assert "already on V3X" in str(meta["tracker_status"]["V3X"]["status_message"])
        assert "abc-123" in str(meta["tracker_status"]["V3X"]["status_message"])

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
    def _tracker(self, monkeypatch: Any, localized: Any = None) -> V3X:
        tracker = V3X(_config())

        async def fake_localized(*args: Any, **kwargs: Any) -> dict[str, Any]:
            if localized is None:
                raise RuntimeError("tmdb down")
            return localized

        monkeypatch.setattr(tracker.tmdb_manager, "get_tmdb_localized_data", fake_localized)
        monkeypatch.setattr(tracker, "_format_audio_bbcode", lambda mi, meta: ["FLAG_FR Français — E-AC-3 5.1"])
        monkeypatch.setattr(tracker, "_format_subtitle_bbcode", lambda mi, meta: ["FLAG_FR Français (SRT)"])
        return tracker

    def test_description_is_centered_with_sections_and_flags(self, monkeypatch: Any, tmp_path: Any):
        tracker = self._tracker(monkeypatch, localized={"overview": "Un synopsis en français."})
        meta = {
            "base_dir": str(tmp_path),
            "uuid": "Some.Movie.2024.2160p.WEB-GRP",
            "poster": "https://image.tmdb.org/t/p/original/xyz.jpg",
            "overview": "English fallback.",
            "source": "WEB-DL",
            "resolution": "2160p",
            "video_encode": "x265",
            "type": "WEBDL",
            "hdr": "HDR",
            "tag": "-GRP",
            "image_list": [
                {"img_url": "https://img.example.invalid/1.md.png", "web_url": "https://img.example.invalid/v1"},
                {"img_url": "https://img.example.invalid/2.md.png", "web_url": "https://img.example.invalid/v2"},
                {"img_url": "https://img.example.invalid/3.md.png", "web_url": "https://img.example.invalid/v3"},
            ],
        }
        desc = asyncio.run(tracker._build_description(meta))
        assert desc.startswith("[center]")
        assert "/t/p/w500/xyz.jpg" in desc  # poster resized
        assert "Un synopsis en français." in desc  # French synopsis preferred
        assert "━━━ Informations techniques ━━━" in desc
        assert "Résolution :" in desc
        assert "FLAG_FR Français — E-AC-3 5.1" in desc  # mixin flag lines included
        assert "FLAG_FR Français (SRT)" in desc
        # clickable thumbnails, two per row (bare [img]: V3X has no sizing syntax)
        assert "[url=https://img.example.invalid/v1][img]https://img.example.invalid/1.md.png[/img][/url] [url=https://img.example.invalid/v2]" in desc
        assert "━━━ Release ━━━" in desc
        assert "Some.Movie.2024.2160p.WEB-GRP" in desc
        # C411 ordering: Release comes before the screenshots section
        assert desc.index("━━━ Release ━━━") < desc.index("━━━ Captures d'écran ━━━")
        assert "[url=https://github.com/yippee0903/Upload-Assistant]" in desc  # linked signature

    def test_description_survives_missing_data(self, monkeypatch: Any, tmp_path: Any):
        tracker = self._tracker(monkeypatch, localized=None)
        desc = asyncio.run(tracker._build_description({"base_dir": str(tmp_path), "uuid": "x", "overview": "Fallback only."}))
        assert "Fallback only." in desc
        assert desc.startswith("[center]")


class TestDocumentaryCategory:
    def _cat(self, meta: dict[str, Any]) -> str:
        return asyncio.run(V3X(_config()).get_category_id(meta))

    def test_documentary_movie_and_series(self):
        assert self._cat({"category": "MOVIE", "genres": "Documentary, History"}) == "5"
        assert self._cat({"category": "TV", "genres": "Documentary"}) == "6"

    def test_documentary_keyword_fallback(self):
        assert self._cat({"category": "MOVIE", "keywords": "documentary, mining"}) == "5"

    def test_explicit_anime_beats_documentary_both_categories(self):
        assert self._cat({"category": "TV", "anime": True, "genres": "Documentary"}) == "3"
        assert self._cat({"category": "MOVIE", "anime": True, "genres": "Documentary"}) == "2"


def test_scene_nfo_preferred_over_mediainfo(monkeypatch: Any, tmp_path: Any) -> None:
    tracker = V3X(_config())
    release = tmp_path / "release"
    release.mkdir()
    (release / "some.release.nfo").write_bytes(b"SCENE NFO ART")
    meta = {"path": str(release), "base_dir": str(tmp_path), "uuid": "x"}
    assert tracker._get_nfo_files(meta) == [str(release / "some.release.nfo")]


def test_v3x_bloat_is_allowed(monkeypatch: Any) -> None:
    # Behavioral: an English-original release with an extra German track is
    # bloat for trackers outside bloat_is_allowed (MTV even gets dropped),
    # but V3X must stay untouched and unwarned.
    import src.audio as audio_module

    printed: list[str] = []
    monkeypatch.setattr(audio_module.console, "print", lambda *a, **k: printed.append(str(a[0]) if a else ""))
    meta: dict[str, Any] = {"trackers": ["V3X", "MTV"], "debug": False}
    audio_module.bloated_check(meta, ["de"], is_eng_original_with_non_eng=True)
    assert "V3X" in meta["trackers"]
    assert "MTV" not in meta["trackers"]
    assert meta.get("bloated_trackers") == ["MTV"]
    assert not any("V3X" in line for line in printed)


class _RaisingClient:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> "_RaisingClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass

    async def get(self, *args: Any, **kwargs: Any) -> Any:
        raise v3x_module.httpx.RequestError("boom")

    async def post(self, *args: Any, **kwargs: Any) -> Any:
        raise v3x_module.httpx.RequestError("boom")


def test_search_network_error_returns_empty(monkeypatch: Any) -> None:
    tracker = V3X(_config())

    async def ok(meta: Any) -> bool:
        return True

    monkeypatch.setattr(tracker, "get_additional_checks", ok)
    monkeypatch.setattr(v3x_module.httpx, "AsyncClient", _RaisingClient)
    assert asyncio.run(tracker.search_existing({"title": "X"})) == []


def test_search_bad_json_shape_returns_empty(monkeypatch: Any) -> None:
    tracker = V3X(_config())

    async def ok(meta: Any) -> bool:
        return True

    monkeypatch.setattr(tracker, "get_additional_checks", ok)
    monkeypatch.setattr(v3x_module.httpx, "AsyncClient", _FakeClient)
    for payload in (["not", "a", "dict"], {"torrents": "not-a-list"}):
        _FakeClient.response = _FakeResponse(200, payload)
        assert asyncio.run(tracker.search_existing({"title": "X"})) == []


def test_upload_network_error_reports_failure(monkeypatch: Any, tmp_path: Any) -> None:
    tracker = V3X(_config())
    uuid = "Some.Movie.2024.1080p.WEB-GRP"
    (tmp_path / "tmp" / uuid).mkdir(parents=True)
    (tmp_path / "tmp" / uuid / "[V3X].torrent").write_bytes(b"fake-torrent")

    async def fake_create(*args: Any) -> None:
        pass

    async def fake_get_name(meta: Any) -> dict[str, str]:
        return {"name": uuid}

    async def fake_desc(*args: Any, **kwargs: Any) -> str:
        return "desc"

    monkeypatch.setattr(tracker.common, "create_torrent_for_upload", fake_create)
    monkeypatch.setattr(tracker, "get_name", fake_get_name)
    monkeypatch.setattr(tracker, "_build_description", fake_desc)
    monkeypatch.setattr(v3x_module.httpx, "AsyncClient", _RaisingClient)
    monkeypatch.setattr(v3x_module, "RETRY_DELAY", 0)
    meta = {"base_dir": str(tmp_path), "uuid": uuid, "category": "MOVIE", "debug": False, "tracker_status": {"V3X": {}}}
    assert asyncio.run(tracker.upload(meta, "")) is False
    assert "upload failed" in str(meta["tracker_status"]["V3X"]["status_message"])


def test_config_anon_flag_makes_upload_anonymous(monkeypatch: Any, tmp_path: Any) -> None:
    config = _config()
    config["TRACKERS"]["V3X"]["anon"] = True
    tracker = V3X(config)
    uuid = "Some.Movie.2024.1080p.WEB-GRP"
    (tmp_path / "tmp" / uuid).mkdir(parents=True)
    (tmp_path / "tmp" / uuid / "[V3X].torrent").write_bytes(b"fake-torrent")

    async def fake_create(*args: Any) -> None:
        pass

    async def fake_get_name(meta: Any) -> dict[str, str]:
        return {"name": uuid}

    async def fake_desc(*args: Any, **kwargs: Any) -> str:
        return "desc"

    monkeypatch.setattr(tracker.common, "create_torrent_for_upload", fake_create)
    monkeypatch.setattr(tracker, "get_name", fake_get_name)
    monkeypatch.setattr(tracker, "_build_description", fake_desc)
    monkeypatch.setattr(v3x_module.httpx, "AsyncClient", _FakeClient)
    _FakeClient.response = _FakeResponse(201, {"id": "x"})
    meta = {"base_dir": str(tmp_path), "uuid": uuid, "category": "MOVIE", "anon": 0, "debug": False, "tracker_status": {"V3X": {}}}
    asyncio.run(tracker.upload(meta, ""))
    assert _FakeClient.captured["data"]["anonymous"] == "true"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Some.Movie.2024.MULTi.VFF.1080p.WEB-GRP", "MULTI,VFF"),
        ("Some.Movie.2024.MULTi.VF2.2160p.BluRay.REMUX-GRP", "MULTI,VF2"),
        ("Some.Movie.2024.MULTi.VFQ.1080p.WEB-GRP", "MULTI,VFQ"),
        ("Some Movie 2024 MULTi VFi 1080p BluRay-GRP", "MULTI,VFI"),
        ("Some.Show.S01.MULTi.1080p.WEB-GRP", "MULTI"),
        ("Some.Movie.2024.MULTi.TRUEFRENCH.2160p.WEB-GRP", "MULTI,TRUEFRENCH"),
        ("Some.Movie.2024.FRENCH.1080p.WEB-GRP", "FRENCH"),
        ("Some.Movie.2024.VFF.1080p.WEBRip-GRP", "VFF"),
        ("Some.Movie.2024.VOSTFR.1080p.WEB-GRP", "VOSTFR"),
        ("Some.Movie.2024.SUBFRENCH.1080p.WEB-GRP", "VOSTFR"),
        ("Some.Movie.2024.1080p.WEB-GRP", ""),
    ],
)
def test_language_tag_detection(name: str, expected: str):
    assert V3X._get_language_tag(name) == expected


def _prep_upload(monkeypatch: Any, tmp_path: Any, name: str, *, mediainfo: str = "General\nfake mediainfo", client: Any = _FakeClient) -> tuple[V3X, dict[str, Any]]:
    """Shared upload-test scaffolding: tmp files, stubs, fake HTTP client."""
    (tmp_path / "tmp" / name).mkdir(parents=True)
    (tmp_path / "tmp" / name / "[V3X].torrent").write_bytes(b"fake-torrent")
    (tmp_path / "tmp" / name / "MEDIAINFO_CLEANPATH.txt").write_text(mediainfo)
    tracker = V3X(_config())

    async def fake_create(*args: Any, **kwargs: Any) -> None:
        pass

    async def fake_get_name(meta: Any) -> dict[str, str]:
        return {"name": name}

    async def fake_desc(*args: Any, **kwargs: Any) -> str:
        return "desc"

    async def fake_fr_title(meta: Any) -> str:
        return ""

    monkeypatch.setattr(tracker.common, "create_torrent_for_upload", fake_create)
    monkeypatch.setattr(tracker, "get_name", fake_get_name)
    monkeypatch.setattr(tracker, "_build_description", fake_desc)
    monkeypatch.setattr(tracker, "_get_nfo_files", lambda meta: [])
    monkeypatch.setattr(tracker, "_get_french_title", fake_fr_title)
    monkeypatch.setattr(v3x_module.httpx, "AsyncClient", client)
    monkeypatch.setattr(v3x_module, "RETRY_DELAY", 0)
    _FakeClient.response = _FakeResponse(201, {"id": "x"})
    _FakeClient.captured = {}
    meta = {"base_dir": str(tmp_path), "uuid": name, "category": "MOVIE", "anon": 0, "debug": False, "tracker_status": {"V3X": {}}}
    return tracker, meta


def _run_upload_with_name(monkeypatch: Any, tmp_path: Any, name: str) -> dict[str, Any]:
    tracker, meta = _prep_upload(monkeypatch, tmp_path, name)
    asyncio.run(tracker.upload(meta, ""))
    return _FakeClient.captured["data"]


def test_upload_sends_language_field(monkeypatch: Any, tmp_path: Any):
    data = _run_upload_with_name(monkeypatch, tmp_path, "Some.Show.S01.MULTi.VFF.1080p.WEB.H264-GRP")
    assert data["language"] == "MULTI,VFF"


def test_upload_omits_language_when_undetected(monkeypatch: Any, tmp_path: Any):
    data = _run_upload_with_name(monkeypatch, tmp_path, "Some.Movie.2024.1080p.WEB-GRP")
    assert "language" not in data


def test_search_existing_routes_dupes_through_french_lang_filter(monkeypatch: Any):
    monkeypatch.setattr(v3x_module.httpx, "AsyncClient", _FakeClient)
    _FakeClient.response = _FakeResponse(200, _rss({"id": "u1", "name": "Some.Movie.2024.VOSTFR.1080p.WEB-GRP", "size": 1}))
    tracker = V3X(_config())

    async def fake_checks(meta: Any) -> bool:
        return True

    seen: dict[str, Any] = {}

    async def fake_filter(dupes: Any, meta: Any) -> Any:
        seen["dupes"] = list(dupes)
        return [{**d, "flags": ["filtered"]} for d in dupes]

    async def fake_fr(meta: Any) -> str:
        return ""

    async def fake_enrich(dupes: Any, *, debug: bool = False) -> None:
        return None

    async def fake_login() -> Any:
        return v3x_module.httpx.Cookies()

    monkeypatch.setattr(tracker, "get_additional_checks", fake_checks)
    monkeypatch.setattr(tracker, "_get_french_title", fake_fr)
    monkeypatch.setattr(tracker, "_enrich_with_files", fake_enrich)
    monkeypatch.setattr(tracker, "_check_french_lang_dupes", fake_filter)
    monkeypatch.setattr(tracker, "_login_session_cookies", fake_login)
    dupes = asyncio.run(tracker.search_existing({"title": "Some Movie"}))
    assert seen["dupes"][0]["name"] == "Some.Movie.2024.VOSTFR.1080p.WEB-GRP"
    assert dupes[0]["flags"] == ["filtered"]


def test_edit_desc_is_a_noop():
    assert asyncio.run(V3X(_config()).edit_desc({})) is None


class TestNamingConventions:
    def test_audio_tokens_are_normalized(self):
        tracker = V3X(_config())
        result = tracker._format_name("Some Movie 2024 MULTi VFF 1080p WEB DD 5.1 Atmos H264-GRP")
        assert ".AC3." in result["name"]
        assert ".ATMOS." in result["name"]

    def test_atmos_moves_between_codec_and_channels(self):
        tracker = V3X(_config())
        result = tracker._format_name("Some Movie 2024 MULTi 2160p WEB DDP 5.1 Atmos H265-GRP")
        assert ".DDP.ATMOS.5.1." in result["name"]

    def test_web_codec_h_form_without_encode_settings(self):
        meta = {"type": "WEBDL", "has_encode_settings": False}
        assert V3X._enforce_web_codec_convention(meta, "Movie.2024.WEB.x265-GRP") == "Movie.2024.WEB.H265-GRP"

    def test_web_codec_x_form_with_encode_settings(self):
        meta = {"type": "WEBRIP", "has_encode_settings": True}
        assert V3X._enforce_web_codec_convention(meta, "Movie.2024.WEB.H264-GRP") == "Movie.2024.WEB.x264-GRP"

    def test_notag_label_registered(self):
        from src.trackersetup import notag_labels

        assert notag_labels["V3X"] == "NOTAG"


def test_upload_language_prefers_mediainfo_analysis(monkeypatch: Any, tmp_path: Any):
    async def fake_audio_string(self: Any, meta: Any) -> str:
        return "MULTI.VOF"

    monkeypatch.setattr(V3X, "_build_audio_string", fake_audio_string)
    data = _run_upload_with_name(monkeypatch, tmp_path, "Some.Movie.2024.MULTi.VFF.1080p.WEB-GRP")
    assert data["language"] == "MULTI,VOF"


class TestAnimeDetection:
    def _cat(self, meta: dict[str, Any]) -> str:
        return asyncio.run(V3X(_config()).get_category_id(meta))

    def test_mal_id_marks_anime(self):
        assert self._cat({"category": "TV", "mal_id": 123}) == "3"
        assert self._cat({"category": "MOVIE", "mal_id": 123}) == "2"

    def test_animation_genre_marks_anime(self):
        assert self._cat({"category": "MOVIE", "genres": "Animation, Comedy"}) == "2"
        assert self._cat({"category": "TV", "genres": "Animation"}) == "3"

    def test_animated_documentary_goes_to_documentary(self):
        assert self._cat({"category": "MOVIE", "genres": "Animation, Documentary"}) == "5"
        assert self._cat({"category": "TV", "genres": "Animation, Documentary"}) == "6"


def test_generated_nfo_gets_complete_name_patched(monkeypatch: Any, tmp_path: Any):
    name = "Some.Movie.2024.MULTi.VFF.1080p.WEB-GRP"
    tracker, meta = _prep_upload(monkeypatch, tmp_path, name, mediainfo="General\nComplete name : /downloads/original.file.mkv\nfake mediainfo")
    asyncio.run(tracker.upload(meta, ""))
    assert f"Complete name : {name}.mkv" in _FakeClient.captured["data"]["nfo"]


def test_upload_retries_once_on_network_error(monkeypatch: Any, tmp_path: Any):
    class _FlakyClient(_FakeClient):
        calls = 0

        async def post(self, url: str, **kwargs: Any) -> _FakeResponse:
            _FlakyClient.calls += 1
            if _FlakyClient.calls == 1:
                raise v3x_module.httpx.ConnectError("boom")
            _FakeClient.captured = {"url": url, **kwargs}
            return _FakeClient.response

    tracker, meta = _prep_upload(monkeypatch, tmp_path, "Some.Movie.2024.1080p.WEB-GRP", client=_FlakyClient)
    assert asyncio.run(tracker.upload(meta, "")) is True
    assert _FlakyClient.calls == 2


def test_description_informations_section(monkeypatch: Any, tmp_path: Any):
    tracker = V3X(_config())

    async def fake_localized(*args: Any, **kwargs: Any) -> dict[str, Any]:
        assert kwargs.get("append_to_response") in ("credits", "")
        return {
            "title": "Un Film",
            "overview": "Synopsis fr.",
            "production_countries": [{"name": "France"}],
            "genres": [{"name": "Drame"}, {"name": "Thriller"}],
            "release_date": "2010-07-15",
            "runtime": 148,
            "vote_average": 8.4,
            "vote_count": 1234,
            "credits": {
                "crew": [
                    {"job": "Director", "name": "Alice Martin"},
                    {"job": "Screenplay", "name": "Bob Durand"},
                    {"job": "Writer", "name": "Bob Durand"},
                ],
                "cast": [{"name": "Actor One"}, {"name": "Actor Two"}],
            },
        }

    monkeypatch.setattr(tracker.tmdb_manager, "get_tmdb_localized_data", fake_localized)
    monkeypatch.setattr(tracker, "_format_audio_bbcode", lambda mi, meta: [])
    monkeypatch.setattr(tracker, "_format_subtitle_bbcode", lambda mi, meta: [])

    async def fake_mi(meta: Any) -> str:
        return "Video\nBit rate : 12.5 Mb/s\n"

    monkeypatch.setattr(tracker, "_get_mediainfo_text", fake_mi)
    meta = {
        "base_dir": str(tmp_path),
        "uuid": "X",
        "title": "Some Movie",
        "original_title": "Some Movie",
        "year": 2010,
        "category": "MOVIE",
        "tmdb_id": 27205,
        "imdb_id": 1375666,
        "service": "NF",
        "video_encode": "H265",
        "video_codec": "HEVC",
        "resolution": "1080p",
    }
    desc = asyncio.run(tracker._build_description(meta))

    assert "━━━ Informations ━━━" in desc
    assert "[b][color=#3d85c6]Titre original :[/color][/b] [i]Some Movie[/i]" in desc
    assert "[i]France[/i]" in desc
    assert "[i]Drame, Thriller[/i]" in desc
    assert "[i]jeudi 15 juillet 2010[/i]" in desc
    assert "[i]2h28[/i]" in desc
    assert "Réalisateur :[/color][/b] [i]Alice Martin[/i]" in desc
    assert "Scénariste :[/color][/b] [i]Bob Durand[/i]" in desc
    assert "[i]Actor One, Actor Two[/i]" in desc
    assert "[i]8.4 (1234 votes)[/i]" in desc
    assert "[url=https://www.imdb.com/title/tt1375666/]IMDb[/url]" in desc
    assert "[url=https://www.themoviedb.org/movie/27205]TMDB[/url]" in desc
    assert "Service :[/color][/b] NF" in desc
    assert "Codec vidéo :[/color][/b] H265 (HEVC)" in desc
    assert "Débit vidéo :[/color][/b] 12.5 Mb/s" in desc
    # Informations comes after the poster and before the Synopsis
    assert desc.index("━━━ Informations ━━━") < desc.index("━━━ Synopsis ━━━")


def test_description_survives_non_numeric_ids(monkeypatch: Any, tmp_path: Any):
    tracker = V3X(_config())

    async def fake_localized(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(tracker.tmdb_manager, "get_tmdb_localized_data", fake_localized)
    monkeypatch.setattr(tracker, "_format_audio_bbcode", lambda mi, meta: [])
    monkeypatch.setattr(tracker, "_format_subtitle_bbcode", lambda mi, meta: [])

    async def fake_mi(meta: Any) -> str:
        return ""

    monkeypatch.setattr(tracker, "_get_mediainfo_text", fake_mi)
    meta = {"base_dir": str(tmp_path), "uuid": "X", "title": "Some Movie", "category": "MOVIE", "imdb_id": "tt1375666", "tmdb_id": "not-a-number"}
    desc = asyncio.run(tracker._build_description(meta))
    assert "[url=https://www.imdb.com/title/tt1375666/]IMDb[/url]" in desc
    assert "themoviedb.org" not in desc


class TestTorrentRootRename:
    """The site displays the .torrent internal name — V3X renames the root."""

    def _make_torrent(self, tmp_path: Any, uuid: str, single_file: bool = False) -> str:
        from torf import Torrent

        content = tmp_path / "content" / uuid
        if single_file:
            content.parent.mkdir(parents=True, exist_ok=True)
            content = content.parent / f"{uuid}.mkv"
            content.write_bytes(b"x" * 2048)
        else:
            content.mkdir(parents=True)
            (content / "movie.mkv").write_bytes(b"x" * 2048)
        t = Torrent(path=str(content), trackers=["https://tracker.example/announce"], piece_size=16384)
        t.generate()
        out_dir = tmp_path / "tmp" / uuid
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / "[V3X].torrent"
        t.write(str(out))
        return str(out)

    def test_folder_torrent_root_renamed_without_rehash(self, tmp_path: Any):
        from torf import Torrent

        uuid = "Some.Movie.2024.1080p.WEB-GRP"
        path = self._make_torrent(tmp_path, uuid)
        pieces_before = Torrent.read(path).metainfo["info"]["pieces"]
        tracker = V3X(_config())
        meta = {"base_dir": str(tmp_path), "uuid": uuid}
        tracker._rename_torrent_root(meta, "Un.Film.2024.VOSTFR.1080p.WEB-GRP")
        t = Torrent.read(path)
        assert t.name == "Un.Film.2024.VOSTFR.1080p.WEB-GRP"
        assert t.metainfo["info"]["pieces"] == pieces_before
        assert [str(f) for f in t.files] == ["Un.Film.2024.VOSTFR.1080p.WEB-GRP/movie.mkv"]

    def test_single_file_torrent_is_wrapped_in_a_folder(self, tmp_path: Any):
        from torf import Torrent

        uuid = "Some.Movie.2024.1080p.WEB-GRP"
        path = self._make_torrent(tmp_path, uuid, single_file=True)
        pieces_before = Torrent.read(path).metainfo["info"]["pieces"]
        tracker = V3X(_config())
        meta = {"base_dir": str(tmp_path), "uuid": uuid}
        tracker._rename_torrent_root(meta, "Un.Film.2024.VOSTFR.1080p.WEB-GRP")
        t = Torrent.read(path)
        # Root folder carries the release name; the inner file keeps its
        # original (cross-seedable) name; pieces are untouched.
        assert t.mode == "multifile"
        assert t.name == "Un.Film.2024.VOSTFR.1080p.WEB-GRP"
        assert [str(f) for f in t.files] == ["Un.Film.2024.VOSTFR.1080p.WEB-GRP/Some.Movie.2024.1080p.WEB-GRP.mkv"]
        assert t.metainfo["info"]["pieces"] == pieces_before

    def test_missing_torrent_is_tolerated(self, tmp_path: Any):
        tracker = V3X(_config())
        meta = {"base_dir": str(tmp_path), "uuid": "nope"}
        tracker._rename_torrent_root(meta, "Whatever")  # must not raise


def test_rename_skipped_without_qbit_linking(tmp_path: Any):
    from torf import Torrent

    uuid = "Some.Movie.2024.1080p.WEB-GRP"
    content = tmp_path / "content" / uuid
    content.mkdir(parents=True)
    (content / "movie.mkv").write_bytes(b"x" * 2048)
    t = Torrent(path=str(content), trackers=["https://tracker.example/announce"], piece_size=16384)
    t.generate()
    out = tmp_path / "tmp" / uuid
    out.mkdir(parents=True)
    t.write(str(out / "[V3X].torrent"))

    config = _config()
    config["TORRENT_CLIENTS"] = {"rt": {"torrent_client": "rtorrent"}}
    tracker = V3X(config)
    tracker._rename_torrent_root({"base_dir": str(tmp_path), "uuid": uuid}, "Un.Film.2024.VOSTFR.1080p.WEB-GRP")
    # No qbit+linking client: the root must stay untouched so seeding works
    assert Torrent.read(str(out / "[V3X].torrent")).name == uuid


def test_rename_allowed_with_rtorrent_linking(tmp_path: Any):
    from torf import Torrent

    uuid = "Some.Movie.2024.1080p.WEB-GRP"
    content = tmp_path / "content" / uuid
    content.mkdir(parents=True)
    (content / "movie.mkv").write_bytes(b"x" * 2048)
    t = Torrent(path=str(content), trackers=["https://tracker.example/announce"], piece_size=16384)
    t.generate()
    out = tmp_path / "tmp" / uuid
    out.mkdir(parents=True)
    t.write(str(out / "[V3X].torrent"))

    config = _config()
    config["TORRENT_CLIENTS"] = {"rt": {"torrent_client": "rtorrent", "linking": "symlink"}}
    tracker = V3X(config)
    tracker._rename_torrent_root({"base_dir": str(tmp_path), "uuid": uuid}, "Un.Film.2024.VOSTFR.1080p.WEB-GRP")
    assert Torrent.read(str(out / "[V3X].torrent")).name == "Un.Film.2024.VOSTFR.1080p.WEB-GRP"


def test_upload_sends_imdb_url_and_artwork_fields(monkeypatch: Any, tmp_path: Any):
    name = "Some.Movie.2024.MULTi.VFF.1080p.WEB-GRP"
    tracker, meta = _prep_upload(monkeypatch, tmp_path, name)
    meta["imdb_id"] = 47296
    meta["poster"] = "https://image.tmdb.org/t/p/original/poster.jpg"
    meta["backdrop"] = "https://image.tmdb.org/t/p/original/backdrop.jpg"
    asyncio.run(tracker.upload(meta, ""))
    data = _FakeClient.captured["data"]
    # No title field: the IMDb link auto-fills the fiche title site-side
    assert "title" not in data
    assert data["tmdbUrl"] == "https://www.imdb.com/title/tt0047296/"
    assert "tmdbId" not in data
    assert data["posterUrl"] == "https://image.tmdb.org/t/p/original/poster.jpg"
    assert data["backdropUrl"] == "https://image.tmdb.org/t/p/original/backdrop.jpg"


def test_upload_falls_back_to_tmdb_id_without_imdb(monkeypatch: Any, tmp_path: Any):
    tracker, meta = _prep_upload(monkeypatch, tmp_path, "Some.Movie.2024.1080p.WEB-GRP")
    meta["tmdb_id"] = 693134
    asyncio.run(tracker.upload(meta, ""))
    data = _FakeClient.captured["data"]
    assert data["tmdbId"] == "693134"
    assert "tmdbUrl" not in data
    assert "title" not in data


def test_upload_omits_artwork_when_absent(monkeypatch: Any, tmp_path: Any):
    tracker, meta = _prep_upload(monkeypatch, tmp_path, "Some.Movie.2024.1080p.WEB-GRP")
    asyncio.run(tracker.upload(meta, ""))
    data = _FakeClient.captured["data"]
    assert "title" not in data
    assert "posterUrl" not in data
    assert "backdropUrl" not in data


def test_search_skips_without_site_credentials(monkeypatch: Any):
    tracker = V3X(_config())

    async def fake_checks(meta: Any) -> bool:
        return True

    monkeypatch.setattr(tracker, "get_additional_checks", fake_checks)
    meta: dict[str, Any] = {"title": "X"}
    # No username/password in config → login returns None → fail-closed skip
    assert asyncio.run(tracker.search_existing(meta)) == []
    assert meta["skipping"] == "V3X"


def test_login_returns_cookies_and_caches(monkeypatch: Any):
    config = _config()
    config["TRACKERS"]["V3X"]["username"] = "user"
    config["TRACKERS"]["V3X"]["password"] = "pass"
    tracker = V3X(config)
    calls: list[str] = []

    class _LoginResponse:
        status_code = 200
        cookies = v3x_module.httpx.Cookies({"v3x_sid": "abc"})

    class _LoginClient(_FakeClient):
        async def post(self, url: str, **kwargs: Any) -> Any:
            calls.append(url)
            assert kwargs["json"] == {"login": "user", "password": "pass"}
            return _LoginResponse()

    monkeypatch.setattr(v3x_module.httpx, "AsyncClient", _LoginClient)
    cookies = asyncio.run(tracker._login_session_cookies())
    assert cookies is not None and cookies.get("v3x_sid") == "abc"
    # Second call hits the cache, no new request
    asyncio.run(tracker._login_session_cookies())
    assert len(calls) == 1


def test_prefers_original_title_in_names(monkeypatch: Any):
    # Original title in the release name (French title goes in the fiche's
    # title field); originally-French works keep their French title.
    tracker = V3X(_config())

    async def fake_fr(meta: Any) -> str:
        return "Les Infiltrés"

    monkeypatch.setattr(tracker, "_get_french_title", fake_fr)
    meta = {
        "title": "The Departed",
        "original_language": "en",
        "year": 2006,
        "resolution": "1080p",
        "type": "ENCODE",
        "source": "BluRay",
        "category": "MOVIE",
        "tag": "-GRP",
        "video_encode": "x264",
    }
    assert asyncio.run(tracker.get_name(meta))["name"] == "The.Departed.2006.1080p.BluRay.x264-GRP"
    assert asyncio.run(tracker.get_name(dict(meta, original_language="fr")))["name"] == "Les.Infiltres.2006.1080p.BluRay.x264-GRP"


def test_session_cookie_reaches_enrichment_only(monkeypatch: Any):
    constructed: list[Any] = []

    class _CookieClient(_FakeClient):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            constructed.append(kwargs.get("cookies"))

        async def get(self, url: str, **kwargs: Any) -> _FakeResponse:
            if url.endswith("/torznab/api"):
                return _FakeResponse(200, _rss({"id": "u1", "name": "Some.Movie.2024.1080p.WEB-GRP", "size": 1}))
            return _FakeResponse(200, {"files": [{"path": "a.mkv", "size": 1}]})

    monkeypatch.setattr(v3x_module.httpx, "AsyncClient", _CookieClient)
    tracker = V3X(_config())
    jar = v3x_module.httpx.Cookies({"v3x_sid": "abc"})
    tracker._session_cookies = jar

    async def fake_checks(meta: Any) -> bool:
        return True

    async def fake_fr(meta: Any) -> str:
        return ""

    monkeypatch.setattr(tracker, "get_additional_checks", fake_checks)
    monkeypatch.setattr(tracker, "_get_french_title", fake_fr)
    dupes = asyncio.run(tracker.search_existing({"title": "Some Movie"}))
    assert dupes and dupes[0]["file_count"] == 1
    # The torznab search is key-only; only the enrichment client carries the jar
    assert [c is not None and c.get("v3x_sid") == "abc" for c in constructed] == [False, True]


class TestFrenchLanguageSupersede:
    """VOSTFR uploads must be blocked by an equivalent French-audio release
    from ANY group; French-audio uploads drop inferior VOSTFR dupes."""

    def _search(self, monkeypatch: Any, upload_audio: str, listing_names: list[str]) -> list[dict[str, Any]]:
        monkeypatch.setattr(v3x_module.httpx, "AsyncClient", _FakeClient)
        _FakeClient.response = _FakeResponse(200, _rss(*({"id": f"u{i}", "name": n, "size": i + 1} for i, n in enumerate(listing_names))))
        tracker = V3X(_config())

        async def fake_checks(meta: Any) -> bool:
            return True

        async def fake_fr(meta: Any) -> str:
            return ""

        async def fake_enrich(dupes: Any, *, debug: bool = False) -> None:
            return None

        async def fake_login() -> Any:
            return v3x_module.httpx.Cookies()

        async def fake_audio(meta: Any) -> str:
            return upload_audio

        monkeypatch.setattr(tracker, "get_additional_checks", fake_checks)
        monkeypatch.setattr(tracker, "_get_french_title", fake_fr)
        monkeypatch.setattr(tracker, "_enrich_with_files", fake_enrich)
        monkeypatch.setattr(tracker, "_login_session_cookies", fake_login)
        monkeypatch.setattr(tracker, "_build_audio_string", fake_audio)
        meta = {"title": "Some Movie", "year": 2024, "resolution": "1080p", "tag": "-MYGRP"}
        return asyncio.run(tracker.search_existing(meta))

    def test_vostfr_upload_blocked_by_multi_from_another_group(self, monkeypatch: Any):
        dupes = self._search(
            monkeypatch,
            "VOSTFR",
            ["Some.Movie.2024.MULTi.VFF.1080p.WEB-OTHERGRP"],
        )
        assert len(dupes) == 1
        assert "french_lang_supersede" in dupes[0].get("flags", [])

    def test_vo_upload_blocked_by_multi_from_another_group(self, monkeypatch: Any):
        # Empty audio string = plain VO (no French audio, no French subs)
        dupes = self._search(
            monkeypatch,
            "",
            ["Some.Movie.2024.MULTi.VFF.1080p.WEB-OTHERGRP"],
        )
        assert len(dupes) == 1
        assert "french_lang_supersede" in dupes[0].get("flags", [])

    def test_vostfr_upload_not_blocked_by_other_group_vostfr(self, monkeypatch: Any):
        dupes = self._search(
            monkeypatch,
            "VOSTFR",
            ["Some.Movie.2024.VOSTFR.1080p.WEB-OTHERGRP"],
        )
        # Same-language release from another group: normal group filter applies
        assert dupes == []

    def test_multi_upload_drops_inferior_vostfr(self, monkeypatch: Any):
        dupes = self._search(
            monkeypatch,
            "MULTI.VFF",
            ["Some.Movie.2024.VOSTFR.1080p.WEB-MYGRP"],
        )
        assert dupes == []


class TestApprovedImageHosts:
    def test_check_image_hosts_delegates_with_approved_list(self, monkeypatch: Any):
        tracker = V3X(_config())
        seen: dict[str, Any] = {}

        async def fake_check_hosts(meta: Any, tracker_name: Any, img_host_index: int, approved_image_hosts: Any) -> Any:
            seen.update(tracker=tracker_name, hosts=approved_image_hosts)
            return [], False, False

        from src.rehostimages import RehostImagesManager, check_tracker_image_hosts

        monkeypatch.setattr(RehostImagesManager, "check_hosts", lambda self, *a, **kw: fake_check_hosts(*a, **kw))
        asyncio.run(check_tracker_image_hosts({}, _config(), tracker))
        assert seen["tracker"] == "V3X"
        assert seen["hosts"] == ["imgbox", "imgbb", "postimg", "pixhost", "ptscreens"]

    def test_description_prefers_rehosted_images(self, monkeypatch: Any, tmp_path: Any):
        tracker = V3X(_config())

        async def fake_localized(*args: Any, **kwargs: Any) -> dict[str, Any]:
            return {}

        async def fake_mi(meta: Any) -> str:
            return ""

        monkeypatch.setattr(tracker.tmdb_manager, "get_tmdb_localized_data", fake_localized)
        monkeypatch.setattr(tracker, "_format_audio_bbcode", lambda mi, meta: [])
        monkeypatch.setattr(tracker, "_format_subtitle_bbcode", lambda mi, meta: [])
        monkeypatch.setattr(tracker, "_get_mediainfo_text", fake_mi)
        meta = {
            "base_dir": str(tmp_path),
            "uuid": "X",
            "title": "Some Movie",
            "category": "MOVIE",
            "image_list": [{"img_url": "https://original.example/a.png", "web_url": "https://original.example/a"}],
            "V3X_images_key": [{"img_url": "https://rehosted.example/a.png", "web_url": "https://rehosted.example/a"}],
        }
        desc = asyncio.run(tracker._build_description(meta))
        assert "rehosted.example" in desc
        assert "original.example" not in desc

    def test_v3x_registered_for_image_host_requirements(self):
        from src.rehostimages import TRACKERS_WITH_IMAGE_HOST_REQUIREMENTS

        assert "V3X" in TRACKERS_WITH_IMAGE_HOST_REQUIREMENTS


def test_description_prefers_french_poster(monkeypatch: Any, tmp_path: Any):
    tracker = V3X(_config())

    async def fake_localized(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"poster_path": "/frposter.jpg"}

    async def fake_mi(meta: Any) -> str:
        return ""

    monkeypatch.setattr(tracker.tmdb_manager, "get_tmdb_localized_data", fake_localized)
    monkeypatch.setattr(tracker, "_format_audio_bbcode", lambda mi, meta: [])
    monkeypatch.setattr(tracker, "_format_subtitle_bbcode", lambda mi, meta: [])
    monkeypatch.setattr(tracker, "_get_mediainfo_text", fake_mi)
    meta = {"base_dir": str(tmp_path), "uuid": "X", "title": "Some Movie", "category": "MOVIE", "poster": "https://image.tmdb.org/t/p/original/default.jpg"}
    desc = asyncio.run(tracker._build_description(meta))
    assert "[img]https://image.tmdb.org/t/p/w500/frposter.jpg[/img]" in desc
    assert "default.jpg" not in desc
    # And the upload field will carry the FR poster too
    assert meta["fr_poster"] == "https://image.tmdb.org/t/p/original/frposter.jpg"


def test_description_falls_back_to_default_poster(monkeypatch: Any, tmp_path: Any):
    tracker = V3X(_config())

    async def fake_localized(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {}

    async def fake_mi(meta: Any) -> str:
        return ""

    monkeypatch.setattr(tracker.tmdb_manager, "get_tmdb_localized_data", fake_localized)
    monkeypatch.setattr(tracker, "_format_audio_bbcode", lambda mi, meta: [])
    monkeypatch.setattr(tracker, "_format_subtitle_bbcode", lambda mi, meta: [])
    monkeypatch.setattr(tracker, "_get_mediainfo_text", fake_mi)
    meta = {"base_dir": str(tmp_path), "uuid": "X", "title": "Some Movie", "category": "MOVIE", "poster": "https://image.tmdb.org/t/p/original/default.jpg"}
    desc = asyncio.run(tracker._build_description(meta))
    assert "[img]https://image.tmdb.org/t/p/w500/default.jpg[/img]" in desc
    assert "fr_poster" not in meta


class TestSourceDescriptionSection:
    """The reused/base description is appended as an optional fiche section."""

    def _desc(self, monkeypatch: Any, tmp_path: Any, *, flag: bool, content: str | None) -> str:
        config = _config()
        config["TRACKERS"]["V3X"]["include_source_description"] = flag
        tracker = V3X(config)

        async def fake_localized(*args: Any, **kwargs: Any) -> dict[str, Any]:
            return {}

        async def fake_mi(meta: Any) -> str:
            return ""

        monkeypatch.setattr(tracker.tmdb_manager, "get_tmdb_localized_data", fake_localized)
        monkeypatch.setattr(tracker, "_format_audio_bbcode", lambda mi, meta: [])
        monkeypatch.setattr(tracker, "_format_subtitle_bbcode", lambda mi, meta: [])
        monkeypatch.setattr(tracker, "_get_mediainfo_text", fake_mi)
        uuid = "X"
        if content is not None:
            (tmp_path / "tmp" / uuid).mkdir(parents=True, exist_ok=True)
            (tmp_path / "tmp" / uuid / "DESCRIPTION.txt").write_text(content, encoding="utf-8")
        meta = {"base_dir": str(tmp_path), "uuid": uuid, "title": "Some Movie", "category": "MOVIE"}
        return asyncio.run(tracker._build_description(meta))

    def test_section_included_when_enabled(self, monkeypatch: Any, tmp_path: Any):
        desc = self._desc(monkeypatch, tmp_path, flag=True, content="Encoder notes worth keeping.")
        assert "━━━ Notes de la release d'origine ━━━" in desc
        assert "Encoder notes worth keeping." in desc
        # Before the screenshots/end, after the Release section
        assert desc.index("━━━ Release ━━━") < desc.index("Notes de la release")

    def test_section_absent_by_default(self, monkeypatch: Any, tmp_path: Any):
        desc = self._desc(monkeypatch, tmp_path, flag=False, content="Encoder notes worth keeping.")
        assert "Notes de la release" not in desc

    def test_section_absent_without_content(self, monkeypatch: Any, tmp_path: Any):
        desc = self._desc(monkeypatch, tmp_path, flag=True, content=None)
        assert "Notes de la release" not in desc

    def test_section_absent_when_file_is_blank(self, monkeypatch: Any, tmp_path: Any):
        desc = self._desc(monkeypatch, tmp_path, flag=True, content="\n\n  \n")
        assert "Notes de la release" not in desc


class TestFlattenSourceBbcode:
    """The site parser supports neither nested spoilers nor inner centers."""

    def test_nested_spoilers_are_unwrapped_keeping_leaves(self):
        text = "[center][spoiler=Other files][center][spoiler=Ep3]info3[/spoiler][/center][center][spoiler=Ep4]info4[/spoiler][/center][/spoiler][/center]"
        out = V3X._flatten_source_bbcode(text)
        assert "[center]" not in out and "[/center]" not in out
        assert out.count("[spoiler=") == 2
        assert out.count("[/spoiler]") == 2
        assert "Other files" not in out
        assert "[spoiler=Ep3]info3[/spoiler]" in out

    def test_flat_spoilers_are_untouched(self):
        text = "[spoiler=Logs]x264 log[/spoiler]\nSummary."
        out = V3X._flatten_source_bbcode(text)
        assert out == "[spoiler=Logs]x264 log[/spoiler]\nSummary."

    def test_triple_nesting_keeps_only_leaves(self):
        text = "[spoiler=A][spoiler=B][spoiler=C]deep[/spoiler][/spoiler][/spoiler]"
        out = V3X._flatten_source_bbcode(text)
        assert out == "[spoiler=C]deep[/spoiler]"


def test_flatten_strips_quote_blocks():
    text = "[quote]\n[color=orange][spoiler=Release Notes][color=gray]Source #1: notes[/color][/spoiler][/color]\n[/quote]"
    out = V3X._flatten_source_bbcode(text)
    assert "[quote]" not in out and "[/quote]" not in out
    assert "[spoiler=Release Notes]" in out
    assert "Source #1: notes" in out


def test_flatten_strips_font_and_size_tags():
    text = "[font=Tahoma][size=28][b]Bloodhounds (2023)[/b][/size]\n[size=13]Genre: Drama[/size][/font]"
    out = V3X._flatten_source_bbcode(text)
    assert "[font" not in out and "[/font]" not in out
    assert "[size" not in out and "[/size]" not in out
    assert "[b]Bloodhounds (2023)[/b]" in out
    assert "Genre: Drama" in out


def test_heading_falls_back_to_romanized_title(monkeypatch: Any, tmp_path: Any):
    tracker = V3X(_config())

    async def fake_localized(*args: Any, **kwargs: Any) -> dict[str, Any]:
        # TMDB has no French translation: fr response carries the original name
        return {"name": "你敢不敢", "original_name": "你敢不敢"}

    async def fake_mi(meta: Any) -> str:
        return ""

    monkeypatch.setattr(tracker.tmdb_manager, "get_tmdb_localized_data", fake_localized)
    monkeypatch.setattr(tracker, "_format_audio_bbcode", lambda mi, meta: [])
    monkeypatch.setattr(tracker, "_format_subtitle_bbcode", lambda mi, meta: [])
    monkeypatch.setattr(tracker, "_get_mediainfo_text", fake_mi)
    meta = {"base_dir": str(tmp_path), "uuid": "X", "title": "How Dare You", "category": "TV", "original_language": "zh"}
    desc = asyncio.run(tracker._build_description(meta))
    assert "How Dare You" in desc
    assert "你敢不敢" not in desc.split("Synopsis")[0]


def test_flatten_strips_headings_and_comparison_blocks():
    text = "[h3][color=#F4AACA]Source 1[/color]: CR[/h3]\nREPACK: notes kept\n[comparison=SOURCE, ENCODE]\nhttps://img.example.invalid/a.png\nhttps://img.example.invalid/b.png\n[/comparison]\nTail kept."
    out = V3X._flatten_source_bbcode(text)
    assert "[h3]" not in out and "[/h3]" not in out
    assert "[comparison" not in out
    assert "img.example.invalid" not in out
    assert "Source 1" in out and "REPACK: notes kept" in out and "Tail kept." in out
