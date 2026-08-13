# Radarr/Sonarr results only carry database IDs; a tracker torrent found in
# the client also carries a description and hosted images. A known tracker ID
# must therefore still trigger the tracker-data fetch even when an Arr
# answered first.

from src.prep import _should_fetch_tracker_data

TRACKER_IDS = ["lst", "blu", "ptp"]


def test_no_arr_ids_fetches() -> None:
    assert _should_fetch_tracker_data({}, None, TRACKER_IDS)


def test_arr_ids_alone_skip_fetch() -> None:
    assert not _should_fetch_tracker_data({}, {"tmdb_id": 33324}, TRACKER_IDS)


def test_tracker_id_overrides_arr_ids() -> None:
    assert _should_fetch_tracker_data({"lst": 188090}, {"tmdb_id": 33324}, TRACKER_IDS)


def test_edit_mode_never_fetches() -> None:
    assert not _should_fetch_tracker_data({"edit": True, "lst": 188090}, None, TRACKER_IDS)
