"""Each named French scenario must yield its tag through the real naming pipeline."""

import asyncio

import pytest
from french_fixtures import SCENARIOS, french_meta

from src.trackers.FRENCH import FrenchTrackerMixin


class _Host(FrenchTrackerMixin):
    tracker = "FAKE"


EXPECTED = {
    "VFF": "VFF",
    "VFQ": "VFQ",
    "VFB": "VFB",
    "VF2": "MULTI.VF2",  # two French dubs of a non-French original
    "VFQ_from_title": "VFQ",
    "MULTI_VFF": "MULTI.VFF",
    "VOSTFR": "VOSTFR",
    "MUET": "MUET",
    "VO_only": "",  # original audio, no French subs: no language tag
}


@pytest.mark.parametrize("scenario", sorted(SCENARIOS), ids=str)
def test_scenario_yields_its_tag(scenario):
    meta = french_meta(mediainfo=SCENARIOS[scenario], original_language="en")
    tag = asyncio.run(_Host()._build_audio_string(meta))
    assert tag == EXPECTED[scenario], f"{scenario}: got {tag!r}"
