"""Size-backed cross-seed for trackers without file lists: name match + byte-identical size."""

from typing import Any

from src.uphelper import size_backed_cross_seed


def _meta(tmp_path: Any, **overrides: Any) -> dict[str, Any]:
    folder = tmp_path / "Example.Release.2026.1080p-GRP"
    folder.mkdir(exist_ok=True)
    (folder / "Example.Release.2026.1080p-GRP.mkv").write_bytes(b"x" * 10)
    (folder / "Example.Release.2026.1080p-GRP.nfo").write_bytes(b"y" * 3)
    meta = {"path": str(folder), "source_size": 10, "DRAU_matched_name": "Example.Release.2026.1080p-GRP"}
    meta.update(overrides)
    return meta


def test_matches_video_only_or_whole_folder_size(tmp_path: Any) -> None:
    dupes = [{"name": "Example.Release.2026.1080p-GRP", "size": 13}]
    assert size_backed_cross_seed(dupes, "DRAU", _meta(tmp_path))
    dupes[0]["size"] = 10
    assert size_backed_cross_seed(dupes, "DRAU", _meta(tmp_path))


def test_rejects_other_sizes_or_entries(tmp_path: Any) -> None:
    assert not size_backed_cross_seed([{"name": "Example.Release.2026.1080p-GRP", "size": 12}], "DRAU", _meta(tmp_path))
    assert not size_backed_cross_seed([{"name": "Other.Release.2026.1080p-GRP", "size": 13}], "DRAU", _meta(tmp_path))
    assert not size_backed_cross_seed([{"name": "Example.Release.2026.1080p-GRP"}], "DRAU", _meta(tmp_path))
    assert not size_backed_cross_seed([{"name": "Example.Release.2026.1080p-GRP", "size": 13}], "DRAU", _meta(tmp_path, DRAU_matched_name=None))
