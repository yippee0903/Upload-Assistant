from src.audio import audio_track_fact, audio_track_facts
from src.trackers.FRENCH import FrenchTrackerMixin


def test_fact_keeps_region_and_flags():
    fact = audio_track_fact({"Language": "fr-CA", "Title": "VFQ 5.1", "Format": "E-AC-3", "Channels": "6", "Default": "Yes"})
    assert (fact["base_language"], fact["region"], fact["channels"], fact["default"]) == ("fr", "ca", 6, True)
    assert audio_track_fact({"Language": "en", "Title": "Director's commentary"})["commentary"] is True
    assert audio_track_fact({"Language": "fr", "Title": "Audio Description"})["audio_description"] is True
    assert audio_track_fact({})["language"] == "" and audio_track_fact({})["channels"] == 0


def test_facts_cover_audio_tracks_in_order():
    meta = {"mediainfo": {"media": {"track": [{"@type": "General"}, {"@type": "Audio", "Language": "fr-FR"}, {"@type": "Video"}, {"@type": "Audio", "Language": "en"}]}}}
    assert [f["language"] for f in audio_track_facts(meta)] == ["fr-fr", "en"]


def test_french_dub_suffix_from_region_subtags():
    suffix = FrenchTrackerMixin._get_french_dub_suffix
    assert suffix([{"Language": "fr-FR"}]) == "VFF"
    assert suffix([{"Language": "fr-CH"}]) == "VFF"
    assert suffix([{"Language": "fr-CA"}]) == "VFQ"
    assert suffix([{"Language": "fr-FR"}, {"Language": "fr-CA"}]) == "VF2"
    assert suffix([{"Language": "fr", "Title": "VFQ"}]) == "VFQ"
    assert suffix([{"Language": "fr"}]) is None
    assert suffix([{"Language": "en"}]) is None
