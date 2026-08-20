"""mkbrr matches --include against basenames only: nested include paths must be flattened."""

from src.torrentcreate import TorrentCreator


def test_nested_include_paths_are_reduced_to_basenames():
    include = ["Show.S01-GRP/Show.S01E01-GRP/Show.S01E01-GRP.mkv", "Show.S01-GRP/Show.S01E02-GRP/Show.S01E02-GRP.mkv", "*.nfo"]
    assert TorrentCreator.build_mkbrr_include_string(include) == "*.nfo,Show.S01E01-GRP.mkv,Show.S01E02-GRP.mkv"


def test_top_level_paths_and_globs_pass_through():
    assert TorrentCreator.build_mkbrr_include_string(["Release/a.mkv", "*.mkv"]) == "*.mkv,a.mkv"
