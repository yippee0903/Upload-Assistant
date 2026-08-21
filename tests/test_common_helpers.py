from unittest.mock import patch

from src.trackers.COMMON import ask_to_continue, is_adult, is_lossless, mi_tracks


def test_ask_to_continue_unattended_gate():
    with patch("src.trackers.COMMON.cli_ui.ask_yes_no", return_value=True) as ask:
        assert ask_to_continue({"unattended": True}, "x") is False
        ask.assert_not_called()
        assert ask_to_continue({"unattended": True, "unattended_confirm": True}, "x") is True
        assert ask_to_continue({"unattended": False}, "x") is True
    with patch("src.trackers.COMMON.cli_ui.ask_yes_no", return_value=False):
        assert ask_to_continue({"unattended": False}, "x") is False


def test_is_adult_matches_whole_keywords_only():
    assert is_adult({"keywords": "xxx, drama", "combined_genres": "Drama"}) is True
    assert is_adult({"keywords": "drama", "combined_genres": "Erotic, Thriller"}) is True  # first genre
    assert is_adult({"keywords": "xxx", "combined_genres": ""}) is True  # lone keyword
    assert is_adult({"keywords": "adulthood", "combined_genres": "Drama"}) is False
    assert is_adult({"keywords": "", "combined_genres": "Drama, Hentai"}) is False
    assert is_adult({"keywords": "", "combined_genres": "Drama, Hentai"}, ("hentai",)) is True


def test_mi_tracks_and_lossless():
    meta = {
        "mediainfo": {
            "media": {
                "track": [
                    {"@type": "General"},
                    {"@type": "Audio", "Format": "FLAC"},
                    {"@type": "Audio", "Format": "DTS", "Format_AdditionalFeatures": "XLL"},
                    {"@type": "Audio", "Format": "AC-3"},
                ]
            }
        }
    }
    audio = mi_tracks(meta, "Audio")
    assert [is_lossless(t) for t in audio] == [True, True, False]
    assert mi_tracks({}, "Audio") == []
