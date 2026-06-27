# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Unit tests for the predb.fr cross-check (pure matching, no network)."""

from src.predb_fr import _safe_nfo_filename, _tmdb_from_media_id, analyze, pick_exact_nfo, tmdb_debug_line


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
    assert analyze(rels, tmdb_id=207, group="-T4KT", category="MOVIE") == ([], [])


def test_tmdb_debug_line_confirmed():
    rels = [_rel(media_id="movie:207"), _rel(media_id="movie:207", team_name="OTHER")]
    line = tmdb_debug_line(rels, tmdb_id=207, category="MOVIE", tracker="C411")
    assert "confirmed by 2 release(s)" in line


def test_tmdb_debug_line_no_data():
    rels = [_rel(media_id=None), _rel(media_id="")]
    line = tmdb_debug_line(rels, tmdb_id=207, category="MOVIE", tracker="C411")
    assert "nothing to confirm" in line


def test_tmdb_debug_line_no_our_id():
    line = tmdb_debug_line([_rel()], tmdb_id=0, category="MOVIE", tracker="C411")
    assert "no TMDB id on our submission" in line


def test_malformed_entries_do_not_raise():
    # Non-dict items (None, str, int) from a bad API payload must be ignored.
    rels = [None, "garbage", 42, _rel(media_id="movie:999", nuke_reason="bad")]
    blocking, info = analyze(rels, tmdb_id=207, group="-T4KT", category="MOVIE")
    assert any("TMDB" in w for w in blocking)
    assert tmdb_debug_line(rels, tmdb_id=207, category="MOVIE", tracker="C411")


def test_tmdb_mismatch_is_blocking():
    rels = [_rel(media_id="movie:999"), _rel(media_id="movie:999", team_name="OTHER")]
    blocking, info = analyze(rels, tmdb_id=207, group="-T4KT", category="MOVIE")
    assert any("TMDB" in w and "999" in w for w in blocking)
    assert info == []


def test_tmdb_match_no_warn():
    blocking, info = analyze([_rel(media_id="movie:207")], tmdb_id=207, group="-T4KT", category="MOVIE")
    assert blocking == [] and info == []


def test_nuke_is_blocking_for_our_group_only():
    rels = [
        _rel(nuke_reason="dupe", team_name="T4KT"),
        _rel(nuke_reason="badaudio", team_name="OTHER"),  # not our group → ignored
    ]
    blocking, _ = analyze(rels, tmdb_id=207, group="-T4KT", category="MOVIE")
    nuke_lines = [w for w in blocking if "Nuked" in w]
    assert len(nuke_lines) == 1 and "dupe" in nuke_lines[0]


def test_unvalidated_group_is_advisory_not_blocking():
    blocking, info = analyze([_rel(team_profilarr_validated=False)], tmdb_id=207, group="-T4KT", category="MOVIE")
    assert blocking == []
    assert any("not profilarr-validated" in w for w in info)


def test_unvalidated_group_silent_without_fr_audio():
    # VOSTFR upload (English audio): the ENG group is legitimately unvalidated,
    # so the advisory must be suppressed.
    blocking, info = analyze(
        [_rel(team_profilarr_validated=False)], tmdb_id=207, group="-T4KT", category="MOVIE", has_fr_audio=False
    )
    assert blocking == []
    assert info == []


def test_has_fr_audio_detection():
    from src.predb_fr import _has_fr_audio

    assert _has_fr_audio({"audio_languages": ["English", "French"]})
    assert _has_fr_audio({"audio_languages": ["fr-FR"]})
    assert not _has_fr_audio({"audio_languages": ["English", "Japanese"]})
    assert not _has_fr_audio({})


def test_tv_category_matches_series():
    rels = [_rel(categ="Series", media_id="tv:999")]
    blocking, _ = analyze(rels, tmdb_id=72879, group="-T4KT", category="TV")
    assert any("TMDB" in w for w in blocking)


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


def test_safe_nfo_filename_blocks_traversal():
    assert _safe_nfo_filename(_NAME) == f"{_NAME}.nfo"
    # Path separators / traversal collapse to a basename, never escaping.
    assert _safe_nfo_filename("../../etc/passwd") == "passwd.nfo"
    assert _safe_nfo_filename("a/b/c") == "c.nfo"
    assert _safe_nfo_filename("..\\..\\win") == "win.nfo"
    for bad in ("", "..", ".", "/", "  "):
        out = _safe_nfo_filename(bad)
        assert out == "" or ("/" not in out and out not in ("..nfo",))
