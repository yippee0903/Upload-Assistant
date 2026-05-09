import asyncio
from typing import Any
from unittest.mock import AsyncMock

from src.trackers.DP import DP


def _config() -> dict[str, Any]:
    return {
        "TRACKERS": {
            "DP": {
                "api_key": "fake",
                "announce_url": "https://darkpeers.org/announce/FAKE",
            }
        },
        "DEFAULT": {"tmdb_api": "fake"},
    }


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _base_meta(**overrides: Any) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "name": "Some Movie 2024 1080p WEB-DL DD+ 5.1 H.264-TAG",
        "title": "Some Movie",
        "year": "2024",
        "category": "MOVIE",
        "type": "WEBDL",
        "audio": "DD+ 5.1",
        "resolution": "1080p",
        "original_language": "en",
        "language_checked": True,
        "audio_languages": ["English"],
        "debug": False,
    }
    meta.update(overrides)
    return meta


def _dp() -> DP:
    dp = DP(_config())
    # Skip the actual language processing – tests pre-populate audio_languages
    return dp


class TestDpGetAudioSingleLanguage:
    """Single-language releases: return the language name as-is."""

    def test_single_english(self) -> None:
        dp = _dp()
        meta = _base_meta(audio_languages=["English"])
        result = _run(dp.get_audio(meta))
        assert result == "English"

    def test_single_french(self) -> None:
        dp = _dp()
        meta = _base_meta(audio_languages=["French"])
        result = _run(dp.get_audio(meta))
        assert result == "French"

    def test_deduplication_single(self) -> None:
        """Duplicate entries in the list should collapse to one language."""
        dp = _dp()
        meta = _base_meta(audio_languages=["Danish", "Danish"])
        result = _run(dp.get_audio(meta))
        assert result == "Danish"


class TestDpGetAudioTwoLanguages:
    """Two distinct languages: French MULTi when French present, else <NonOrig> MULTi."""

    def test_french_plus_other_returns_french_multi(self) -> None:
        dp = _dp()
        meta = _base_meta(
            audio_languages=["English", "French"],
            original_language="en",
        )
        result = _run(dp.get_audio(meta))
        assert result == "French MULTi"

    def test_french_first_still_french_multi(self) -> None:
        """Order should not matter; French MULTi regardless of track order."""
        dp = _dp()
        meta = _base_meta(
            audio_languages=["French", "English"],
            original_language="en",
        )
        result = _run(dp.get_audio(meta))
        assert result == "French MULTi"

    def test_non_french_two_langs_uses_non_original(self) -> None:
        """German content dubbed in English → 'English MULTi'."""
        dp = _dp()
        meta = _base_meta(
            audio_languages=["German", "English"],
            original_language="de",
        )
        result = _run(dp.get_audio(meta))
        assert result == "English MULTi"

    def test_non_french_two_langs_original_is_english(self) -> None:
        """English original with Swedish dub → 'Swedish MULTi'."""
        dp = _dp()
        meta = _base_meta(
            audio_languages=["English", "Swedish"],
            original_language="en",
        )
        result = _run(dp.get_audio(meta))
        assert result == "Swedish MULTi"

    def test_non_french_fallback_when_no_original_language(self) -> None:
        """No original_language provided → falls back to second track."""
        dp = _dp()
        meta = _base_meta(
            audio_languages=["English", "Danish"],
            original_language="",
        )
        result = _run(dp.get_audio(meta))
        # With no orig_code, orig_name is empty so the generator finds nothing;
        # fallback is unique_languages[1].
        assert result == "Danish MULTi"


class TestDpGetAudioThreePlusLanguages:
    """Three or more distinct languages → plain 'MULTi'."""

    def test_three_langs_returns_multi(self) -> None:
        dp = _dp()
        meta = _base_meta(audio_languages=["English", "French", "German"])
        result = _run(dp.get_audio(meta))
        assert result == "MULTi"

    def test_three_langs_with_french_still_multi(self) -> None:
        """Even with French present, 3+ tracks → 'MULTi', not 'French MULTi'."""
        dp = _dp()
        meta = _base_meta(audio_languages=["English", "French", "Danish"])
        result = _run(dp.get_audio(meta))
        assert result == "MULTi"


class TestDpGetName:
    """get_name: replaces Dual-Audio / MULTi token in the base name."""

    def test_dual_audio_replaced_by_french_multi(self) -> None:
        dp = _dp()
        meta = _base_meta(
            name="Movie 2024 1080p WEB-DL Dual-Audio H.264-TAG",
            audio_languages=["English", "French"],
            original_language="en",
        )
        result = _run(dp.get_name(meta))
        assert "Dual-Audio" not in result["name"]
        assert "French MULTi" in result["name"]

    def test_dual_audio_replaced_by_swedish_multi(self) -> None:
        dp = _dp()
        meta = _base_meta(
            name="Movie 2024 1080p WEB-DL Dual-Audio H.264-TAG",
            audio_languages=["English", "Swedish"],
            original_language="en",
        )
        result = _run(dp.get_name(meta))
        assert "Dual-Audio" not in result["name"]
        assert "Swedish MULTi" in result["name"]

    def test_multi_replaced_by_french_multi(self) -> None:
        """When base name already has 'MULTi' and audio is French MULTi → replace."""
        dp = _dp()
        meta = _base_meta(
            name="Movie 2024 MULTi 1080p WEB-DL H.264-TAG",
            audio_languages=["English", "French"],
            original_language="en",
        )
        result = _run(dp.get_name(meta))
        assert "French MULTi" in result["name"]

    def test_multi_not_replaced_when_non_french_two_langs(self) -> None:
        """When audio resolves to e.g. 'Swedish MULTi', existing 'MULTi' is NOT replaced."""
        dp = _dp()
        meta = _base_meta(
            name="Movie 2024 MULTi 1080p WEB-DL H.264-TAG",
            audio_languages=["English", "Swedish"],
            original_language="en",
        )
        result = _run(dp.get_name(meta))
        # Only "French MULTi" triggers MULTi replacement
        assert result["name"] == meta["name"]

    def test_name_unchanged_when_single_language(self) -> None:
        """Single language: no Dual-Audio or MULTi token, name is returned as-is."""
        dp = _dp()
        original_name = "Movie 2024 1080p WEB-DL DD+ 5.1 H.264-TAG"
        meta = _base_meta(name=original_name, audio_languages=["English"])
        result = _run(dp.get_name(meta))
        assert result["name"] == original_name
