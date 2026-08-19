# The "source description" section reuses tmp DESCRIPTION.txt, which the
# description pipeline may prefix with its own NFO embed
# ([spoiler=Scene NFO:] blocks). French trackers already send the NFO
# through their API field, so that embed must not reach the description.

import asyncio

from src.trackers.FRENCH import FrenchTrackerMixin

NFO_BLOCK = "[center][spoiler=Scene NFO:][code]\nascii art here\n[/code][/spoiler][/center]"
PROSE = "Une description reprise d'une fiche source."


def _get_source_description(tmp_path, content):
    (tmp_path / "tmp" / "uuid").mkdir(parents=True)
    (tmp_path / "tmp" / "uuid" / "DESCRIPTION.txt").write_text(content, encoding="utf-8")
    obj = FrenchTrackerMixin.__new__(FrenchTrackerMixin)
    obj.config = {"TRACKERS": {"XX": {"include_source_description": True}}}
    obj.tracker = "XX"
    meta = {"base_dir": str(tmp_path), "uuid": "uuid"}
    return asyncio.run(obj._get_source_description(meta))


def test_scene_nfo_embed_is_stripped(tmp_path):
    assert _get_source_description(tmp_path, f"{NFO_BLOCK}\n{PROSE}") == PROSE


def test_nfo_only_description_becomes_empty(tmp_path):
    assert _get_source_description(tmp_path, NFO_BLOCK) == ""


def test_prose_is_kept_verbatim(tmp_path):
    assert _get_source_description(tmp_path, PROSE) == PROSE


def test_framestor_nfo_embed_is_stripped(tmp_path):
    block = NFO_BLOCK.replace("Scene NFO:", "FraMeSToR NFO:")
    assert _get_source_description(tmp_path, f"{PROSE}\n{block}") == PROSE
