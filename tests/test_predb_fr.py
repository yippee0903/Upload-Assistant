# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Unit tests for the predb.fr cross-check (pure matching, no network)."""

from src.predb_fr import _tmdb_from_media_id, analyze, pick_exact_nfo


def _rel(**kw):
    base = {
        "name": "Film.1989.MULTi.VFF.1080p.BluRay.x265-T4KT",
        "source": "P2P",
        "media_id": "movie:207",
        "categ": "Movies",
        "nuke_reason": None,
        "team_name": "T4KT",
        "team_profilarr_validated": True,
        "has_nfo": False,
    }
    base.update(kw)
    return base


def test_media_id_parsing():
    assert _tmdb_from_media_id("movie:207") == 207
    assert _tmdb_from_media_id("tv:72879") == 72879
    assert _tmdb_from_media_id(None) is None
    assert _tmdb_from_media_id("garbage") is None


def test_no_candidates_is_silent():
    # Only Ebooks/Other → nothing to compare against for a movie upload.
    rels = [_rel(categ="Ebooks"), _rel(categ="Other")]
    assert analyze(rels, tmdb_id=207, group="-T4KT", category="MOVIE") == []


def test_tmdb_mismatch_warns():
    rels = [_rel(media_id="movie:999"), _rel(media_id="movie:999", team_name="OTHER")]
    out = analyze(rels, tmdb_id=207, group="-T4KT", category="MOVIE")
    assert any("TMDB" in w and "999" in w for w in out)


def test_tmdb_match_no_warn():
    out = analyze([_rel(media_id="movie:207")], tmdb_id=207, group="-T4KT", category="MOVIE")
    assert not any("TMDB" in w for w in out)


def test_nuke_warns_for_our_group_only():
    rels = [
        _rel(nuke_reason="dupe", team_name="T4KT"),
        _rel(nuke_reason="badaudio", team_name="OTHER"),  # not our group → ignored
    ]
    out = analyze(rels, tmdb_id=207, group="-T4KT", category="MOVIE")
    nuke_lines = [w for w in out if "nukée" in w]
    assert len(nuke_lines) == 1 and "dupe" in nuke_lines[0]


def test_unvalidated_group_warns():
    out = analyze([_rel(team_profilarr_validated=False)], tmdb_id=207, group="-T4KT", category="MOVIE")
    assert any("non validé profilarr" in w for w in out)


def test_tv_category_matches_series():
    rels = [_rel(categ="Series", media_id="tv:999")]
    out = analyze(rels, tmdb_id=72879, group="-T4KT", category="TV")
    assert any("TMDB" in w for w in out)


# ── exact-match NFO selection ──────────────────────────────────────────────
_NAME = "Film.1989.MULTi.VFF.1080p.BluRay.x265-T4KT"


def test_exact_nfo_match_ignores_ext_and_case():
    rels = [_rel(name=_NAME, has_nfo=True)]
    # our source file carries a .mkv extension; predb name has none
    assert pick_exact_nfo(rels, _NAME + ".mkv") is rels[0]
    assert pick_exact_nfo(rels, _NAME.upper()) is rels[0]


def test_exact_nfo_requires_has_nfo():
    rels = [_rel(name=_NAME, has_nfo=False)]
    assert pick_exact_nfo(rels, _NAME) is None


def test_exact_nfo_no_partial_match():
    # A different release of the same title must NOT match.
    rels = [_rel(name="Film.1989.MULTi.VFF.1080p.BluRay.x264-OTHER", has_nfo=True)]
    assert pick_exact_nfo(rels, _NAME) is None
    assert pick_exact_nfo(rels, "") is None
