import asyncio

from src.trackers.UNIT3D import UNIT3D


def _keywords(value: str) -> str:
    tracker = UNIT3D.__new__(UNIT3D)
    return asyncio.run(UNIT3D.get_keywords(tracker, {"keywords": value}))["keywords"]


def test_keywords_cut_at_whole_words_under_255():
    words = [f"keyword{i:02d}" for i in range(40)]  # 9 chars each, ~440 with separators
    result = _keywords(", ".join(words))
    assert len(result) <= 255
    assert result.endswith(words[len(result.split(", ")) - 1])
    assert all(w in words for w in result.split(", "))


def test_keywords_short_and_empty_unchanged():
    assert _keywords("drama, thriller") == "drama, thriller"
    assert _keywords("") == ""
    assert len(_keywords("x" * 300)) == 255
