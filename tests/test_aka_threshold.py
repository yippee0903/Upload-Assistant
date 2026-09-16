# The AKA is dropped when the TMDB title and the IMDb title look like the same
# title. The threshold must separate same-title variants (accents, articles)
# from real translations that happen to share letters.

from difflib import SequenceMatcher

from src.prep import AKA_SAME_TITLE_RATIO


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def test_same_title_variants_are_above_the_threshold() -> None:
    assert _ratio("amélie", "amelie") >= AKA_SAME_TITLE_RATIO
    assert _ratio("the intouchables", "intouchables") >= AKA_SAME_TITLE_RATIO


def test_a_translation_sharing_letters_is_below_the_threshold() -> None:
    assert _ratio("the adventures of philibert, captain virgin", "les aventures de philibert, capitaine puceau") < AKA_SAME_TITLE_RATIO
    assert _ratio("the wages of fear", "le salaire de la peur") < AKA_SAME_TITLE_RATIO
