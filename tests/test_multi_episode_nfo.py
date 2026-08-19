# A season pack sometimes ships one giant NFO concatenating the full
# MediaInfo dump of every episode. That file must stay in the .torrent
# (cross-seed integrity) but must not be sent as the tracker API NFO field,
# where the single-episode MediaInfo dump is preferred.

from src.nfo_generator import is_multi_episode_nfo

SINGLE_MI = """General
Unique ID                                : 123
Complete name                            : Show.S01E01.1080p.WEB-DL-GRP.mkv
Format                                   : Matroska
"""

MULTI_MI = SINGLE_MI + """
General
Unique ID                                : 456
Complete name                            : Show.S01E02.1080p.WEB-DL-GRP.mkv
Format                                   : Matroska
"""

SCENE_NFO = "ASCII art release notes, no mediainfo dump here."


def _write(tmp_path, content):
    path = tmp_path / "release.nfo"
    path.write_text(content, encoding="utf-8")
    return str(path)


def _is_multi(path):
    import asyncio

    return asyncio.run(is_multi_episode_nfo(path))


def test_single_mediainfo_dump_is_not_multi(tmp_path):
    assert _is_multi(_write(tmp_path, SINGLE_MI)) is False


def test_scene_nfo_is_not_multi(tmp_path):
    assert _is_multi(_write(tmp_path, SCENE_NFO)) is False


def test_concatenated_dumps_are_multi(tmp_path):
    assert _is_multi(_write(tmp_path, MULTI_MI)) is True


def test_missing_file_is_not_multi(tmp_path):
    assert _is_multi(str(tmp_path / "absent.nfo")) is False


def _unit3d(tmp_path, nfo_content):
    import asyncio

    from src.trackers.UNIT3D import UNIT3D

    tmp_dir = tmp_path / "tmp" / "uuid"
    tmp_dir.mkdir(parents=True)
    (tmp_dir / "release.nfo").write_text(nfo_content, encoding="utf-8")
    (tmp_dir / "MEDIAINFO_CLEANPATH.txt").write_text(SINGLE_MI, encoding="utf-8")
    tracker = UNIT3D({"TRACKERS": {"XX": {}}}, "XX")
    meta = {"base_dir": str(tmp_path), "uuid": "uuid", "path": str(tmp_path)}
    return asyncio.run(tracker.get_additional_files(meta))


def test_unit3d_api_field_uses_multi_nfo_replacement(tmp_path):
    files = _unit3d(tmp_path, MULTI_MI)
    assert files["nfo"][1].decode("utf-8") == SINGLE_MI


def test_unit3d_api_field_keeps_single_nfo(tmp_path):
    files = _unit3d(tmp_path, SCENE_NFO)
    assert files["nfo"][1].decode("utf-8") == SCENE_NFO
