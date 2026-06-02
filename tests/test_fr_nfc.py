# Tests for _fr_clean NFC normalization regression
"""
Regression for Bug: "Bon Appétit" → "Bon.Apptit" when TMDB provides the
title in NFD form (e.g. U+0065 + combining accent U+0301) instead of the
precomposed NFC form (U+00E9).

Before the fix, unidecode() would see the bare combining accent U+0301 and
return an empty string for it, silently dropping the following vowel:
    NFD: 'e' + U+0301 → unidecode(U+0301) == '' → 'App' + '' + 'tit'

After the fix, the first line of _fr_clean() normalises to NFC so that
both inputs produce the same "Appetit".
"""

import unicodedata


class TestFrCleanNFC:
    """_fr_clean must produce the same output for NFC and NFD input."""

    def test_bon_appetit_nfc(self):
        from src.trackers.FRENCH import FrenchTrackerMixin

        nfc = "Bon App\u00e9tit Your Majesty"
        result = FrenchTrackerMixin._fr_clean(nfc)
        assert "Appetit" in result, f"Expected 'Appetit' in {result!r}"
        assert "Apptit" not in result, f"Got broken 'Apptit' in {result!r}"

    def test_bon_appetit_nfd(self):
        """NFD form (combining accent) must produce the same result as NFC."""
        from src.trackers.FRENCH import FrenchTrackerMixin

        nfd = unicodedata.normalize("NFD", "Bon App\u00e9tit Your Majesty")
        result = FrenchTrackerMixin._fr_clean(nfd)
        assert "Appetit" in result, f"Expected 'Appetit' in {result!r} (NFD input)"
        assert "Apptit" not in result, f"Got broken 'Apptit' in {result!r} (NFD input)"

    def test_nfc_nfd_produce_same_output(self):
        """NFC and NFD forms of the same string must produce identical output."""
        from src.trackers.FRENCH import FrenchTrackerMixin

        title = "Naïve Café Résumé"
        nfc = unicodedata.normalize("NFC", title)
        nfd = unicodedata.normalize("NFD", title)
        assert FrenchTrackerMixin._fr_clean(nfc) == FrenchTrackerMixin._fr_clean(nfd)

    def test_plain_ascii_unchanged(self):
        """Pure ASCII input must still pass through without corruption."""
        from src.trackers.FRENCH import FrenchTrackerMixin

        result = FrenchTrackerMixin._fr_clean("The Dark Knight")
        assert result == "The Dark Knight", f"Got {result!r}"
