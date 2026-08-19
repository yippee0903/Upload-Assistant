# A TMDB id is only meaningful with its movie/tv namespace: ids collide
# between the two (the same number can be a movie and an unrelated TV show).
# These tests cover the three defenses against namespace/category desync:
# episode-numbered packs without a season token, tracker fiches with a
# category outside MOVIE/TV, and the IMDb<->TMDB corroboration cross-check.

import asyncio

import src.tmdb as tmdb
import src.trackermeta as trackermeta
from src.prep import Prep


def _get_cat(video, folder):
    meta = {"path": f"/x/{folder}", "uuid": folder}
    return asyncio.run(Prep.get_cat(object(), video, meta))


def test_get_cat_episode_numbered_pack_is_tv():
    folder = "Show.Name.MULTi.1080p.BluRay.x264-GRP"
    video = f"/x/{folder}/Show.Name.E01.MULTi.1080p.BluRay.x264-GRP.mkv"
    assert _get_cat(video, folder) == "TV"


def test_get_cat_movie_file_stays_movie():
    folder = "Movie.Name.2020.1080p.BluRay.x264-GRP"
    video = f"/x/{folder}/Movie.Name.2020.1080p.BluRay.x264-GRP.mkv"
    assert _get_cat(video, folder) == "MOVIE"


def test_resolve_namespace_prefers_imdb_cross_reference(monkeypatch):
    async def fake_find(imdb_id):
        assert imdb_id == 1910272
        return {"movie_results": [], "tv_results": [{"id": 42509}]}

    monkeypatch.setattr(tmdb, "_find_by_imdb_id", fake_find)
    assert asyncio.run(tmdb.resolve_tmdb_namespace(42509, 1910272)) == "TV"


def _tracker_data(category):
    # (tmdb, imdb, tvdb, mal, desc, category, infohash, imagelist, filename)
    return (42509, 1910272, 0, 0, None, category, None, None, None)


def test_unparsed_fiche_category_resolves_namespace(monkeypatch):
    async def fake_resolve(tmdb_id, imdb_id=0):
        assert (tmdb_id, imdb_id) == (42509, 1910272)
        return "TV"

    monkeypatch.setattr(trackermeta, "resolve_tmdb_namespace", fake_resolve)
    meta = {"debug": False, "unattended": True, "category": "MOVIE"}
    asyncio.run(trackermeta.update_meta_with_unit3d_data(meta, _tracker_data("Anime"), "XX"))
    assert meta["category"] == "TV"
    assert meta["tmdb_id"] == 42509


def test_parsed_fiche_category_skips_resolver(monkeypatch):
    async def boom(*_args, **_kwargs):
        raise AssertionError("resolver must not run for a MOVIE/TV fiche category")

    monkeypatch.setattr(trackermeta, "resolve_tmdb_namespace", boom)
    meta = {"debug": False, "unattended": True, "category": "MOVIE"}
    asyncio.run(trackermeta.update_meta_with_unit3d_data(meta, _tracker_data("TV"), "XX"))
    assert meta["category"] == "TV"


def test_manual_category_is_never_overridden(monkeypatch):
    async def boom(*_args, **_kwargs):
        raise AssertionError("resolver must not run with a manual category")

    monkeypatch.setattr(trackermeta, "resolve_tmdb_namespace", boom)
    meta = {"debug": False, "unattended": True, "category": "MOVIE", "manual_category": "MOVIE"}
    asyncio.run(trackermeta.update_meta_with_unit3d_data(meta, _tracker_data("Anime"), "XX"))
    assert meta["category"] == "MOVIE"


def test_agreement_check_adopts_corroborated_pair_unattended(monkeypatch):
    async def fake_find(_imdb_id):
        return {"movie_results": [], "tv_results": [{"id": 42509}]}

    monkeypatch.setattr(tmdb, "_find_by_imdb_id", fake_find)
    meta = {"category": "MOVIE", "tmdb_id": 760827, "imdb_id": 1910272}
    asyncio.run(tmdb.verify_tmdb_imdb_agreement(meta, unattended=True))
    assert (meta["category"], meta["tmdb_id"]) == ("TV", 42509)


def test_agreement_check_keeps_agreeing_pair(monkeypatch):
    async def fake_find(_imdb_id):
        return {"movie_results": [{"id": 555}], "tv_results": []}

    monkeypatch.setattr(tmdb, "_find_by_imdb_id", fake_find)
    meta = {"category": "MOVIE", "tmdb_id": 555, "imdb_id": 42}
    asyncio.run(tmdb.verify_tmdb_imdb_agreement(meta, unattended=True))
    assert (meta["category"], meta["tmdb_id"]) == ("MOVIE", 555)


def test_agreement_check_no_candidates_is_noop(monkeypatch):
    async def fake_find(_imdb_id):
        return {}

    monkeypatch.setattr(tmdb, "_find_by_imdb_id", fake_find)
    meta = {"category": "MOVIE", "tmdb_id": 555, "imdb_id": 42}
    asyncio.run(tmdb.verify_tmdb_imdb_agreement(meta, unattended=True))
    assert (meta["category"], meta["tmdb_id"]) == ("MOVIE", 555)


def test_agreement_check_skips_manual_ids(monkeypatch):
    async def boom(_imdb_id):
        raise AssertionError("find must not run for manual ids")

    monkeypatch.setattr(tmdb, "_find_by_imdb_id", boom)
    meta = {"category": "MOVIE", "tmdb_id": 555, "imdb_id": 42, "tmdb_manual": 555}
    asyncio.run(tmdb.verify_tmdb_imdb_agreement(meta, unattended=True))
    assert meta["tmdb_id"] == 555
