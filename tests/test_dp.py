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
    """Single-language releases."""

    def test_single_english_original_no_tag(self) -> None:
        """English original + English only → no dub tag."""
        dp = _dp()
        meta = _base_meta(audio_languages=["English"], original_language="en")
        result = _run(dp.get_audio(meta))
        assert result == ""

    def test_single_english_on_non_english_original_dubbed(self) -> None:
        """Non-English original + English only → Dubbed."""
        dp = _dp()
        meta = _base_meta(audio_languages=["English"], original_language="ja")
        result = _run(dp.get_audio(meta))
        assert result == "Dubbed"

    def test_single_french_on_english_original_no_tag(self) -> None:
        """English original + single non-English track → no tag (not covered by guide)."""
        dp = _dp()
        meta = _base_meta(audio_languages=["French"], original_language="en")
        result = _run(dp.get_audio(meta))
        assert result == ""

    def test_single_nordic_on_non_english_original_language_dubbed(self) -> None:
        """Non-English/non-Nordic original + Nordic only → Language Dubbed."""
        dp = _dp()
        meta = _base_meta(audio_languages=["Swedish"], original_language="ja")
        result = _run(dp.get_audio(meta))
        assert result == "Swedish Dubbed"

    def test_single_nordic_on_nordic_original_no_tag(self) -> None:
        """Nordic original + Nordic only → original-language-only, no tag."""
        dp = _dp()
        meta = _base_meta(audio_languages=["Swedish"], original_language="sv")
        result = _run(dp.get_audio(meta))
        assert result == ""

    def test_deduplication_single(self) -> None:
        """Duplicate entries in the list should collapse to one language."""
        dp = _dp()
        meta = _base_meta(audio_languages=["Danish", "Danish"], original_language="en")
        result = _run(dp.get_audio(meta))
        assert result == ""  # English original + Danish only → no rule covers this


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

    def test_non_english_orig_plus_english_returns_dual_audio(self) -> None:
        """Non-English original + [original, English] → Dual-Audio per DP naming guide."""
        dp = _dp()
        meta = _base_meta(
            audio_languages=["German", "English"],
            original_language="de",
        )
        result = _run(dp.get_audio(meta))
        assert result == "Dual-Audio"

    def test_japanese_orig_plus_english_returns_dual_audio(self) -> None:
        """Regression: Your Name. AKA Kimi no Na wa. — Japanese+English should be Dual-Audio, not English MULTi."""
        dp = _dp()
        meta = _base_meta(
            audio_languages=["Japanese", "English"],
            original_language="ja",
        )
        result = _run(dp.get_audio(meta))
        assert result == "Dual-Audio"

    def test_non_english_orig_plus_non_english_returns_language_multi(self) -> None:
        """Non-English original + [original, non-English non-original] → Language MULTi."""
        dp = _dp()
        meta = _base_meta(
            audio_languages=["Japanese", "German"],
            original_language="ja",
        )
        result = _run(dp.get_audio(meta))
        assert result == "German MULTi"

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
        # No original language known; English is treated as anchor, Danish is label.
        assert result == "Danish MULTi"

    def test_french_original_plus_english_returns_dual_audio(self) -> None:
        """French original + [French, English] → Dual-Audio, not French MULTi."""
        dp = _dp()
        meta = _base_meta(
            audio_languages=["French", "English"],
            original_language="fr",
        )
        result = _run(dp.get_audio(meta))
        assert result == "Dual-Audio"

    def test_french_original_plus_german_returns_german_multi(self) -> None:
        """French original + [French, German] → German MULTi, not French MULTi."""
        dp = _dp()
        meta = _base_meta(
            audio_languages=["French", "German"],
            original_language="fr",
        )
        result = _run(dp.get_audio(meta))
        assert result == "German MULTi"

    def test_no_original_track_english_plus_swedish_returns_swedish_multi(self) -> None:
        """Japanese original absent from tracks; [English, Swedish] → Swedish MULTi."""
        dp = _dp()
        meta = _base_meta(
            audio_languages=["English", "Swedish"],
            original_language="ja",
        )
        result = _run(dp.get_audio(meta))
        assert result == "Swedish MULTi"

    def test_disc_release_no_tag(self) -> None:
        """Disc releases must return no dub tag regardless of languages."""
        dp = _dp()
        meta = _base_meta(
            audio_languages=["Japanese", "English"],
            original_language="ja",
            is_disc="BDMV",
        )
        result = _run(dp.get_audio(meta))
        assert result == ""


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

    def test_multi_replaced_by_swedish_multi(self) -> None:
        """When audio resolves to 'Swedish MULTi', existing 'MULTi' is replaced."""
        dp = _dp()
        meta = _base_meta(
            name="Movie 2024 MULTi 1080p WEB-DL H.264-TAG",
            audio_languages=["English", "Swedish"],
            original_language="en",
        )
        result = _run(dp.get_name(meta))
        assert "Swedish MULTi" in result["name"]
        assert result["name"].count("MULTi") == 1

    def test_name_unchanged_when_single_language(self) -> None:
        """Single language: no Dual-Audio or MULTi token, name is returned as-is."""
        dp = _dp()
        original_name = "Movie 2024 1080p WEB-DL DD+ 5.1 H.264-TAG"
        meta = _base_meta(name=original_name, audio_languages=["English"])
        result = _run(dp.get_name(meta))
        assert result["name"] == original_name

    def test_no_duplicate_when_name_already_has_french_multi(self) -> None:
        """Regression: if name already contains 'French MULTi', do not insert it again."""
        dp = _dp()
        original_name = "Movie 2024 French MULTi 1080p WEB-DL H.264-TAG"
        meta = _base_meta(
            name=original_name,
            audio_languages=["English", "French"],
            original_language="en",
        )
        result = _run(dp.get_name(meta))
        assert result["name"] == original_name
        assert result["name"].count("French MULTi") == 1

    def test_dual_audio_preserved_for_non_english_orig_with_english(self) -> None:
        """Regression: non-English original + [orig, English] must keep 'Dual-Audio' in the name."""
        dp = _dp()
        meta = _base_meta(
            name="Your Name. AKA Kimi no Na wa. 2016 1080p BluRay Dual-Audio Opus 5.1 Hi10P x264-BlackRose",
            audio_languages=["Japanese", "English"],
            original_language="ja",
        )
        result = _run(dp.get_name(meta))
        assert "Dual-Audio" in result["name"]
        assert "MULTi" not in result["name"]

    def test_dual_audio_replaced_by_language_multi_for_non_english_pair(self) -> None:
        """Non-English original + [orig, non-English] replaces Dual-Audio with Language MULTi."""
        dp = _dp()
        meta = _base_meta(
            name="Anime 2020 1080p BluRay Dual-Audio AAC 2.0 x264-GRP",
            audio_languages=["Japanese", "German"],
            original_language="ja",
        )
        result = _run(dp.get_name(meta))
        assert "Dual-Audio" not in result["name"]
        assert "German MULTi" in result["name"]

    def test_dubbed_replaced_by_swedish_dubbed(self) -> None:
        """If name has 'Dubbed' but audio resolves to 'Swedish Dubbed', replace it."""
        dp = _dp()
        meta = _base_meta(
            name="Anime 2020 1080p BluRay Dubbed AAC 2.0 x264-GRP",
            audio=["AAC 2.0"],
            audio_languages=["Swedish"],
            original_language="ja",
        )
        result = _run(dp.get_name(meta))
        assert "Swedish Dubbed" in result["name"]
        assert result["name"].count("Dubbed") == 1

    def test_nordic_dubbed_inserted_when_no_dub_token(self) -> None:
        """When no dub token exists in the name, insert 'Swedish Dubbed' before the codec."""
        dp = _dp()
        meta = _base_meta(
            name="Anime 2020 1080p BluRay AAC 2.0 x264-GRP",
            audio="AAC 2.0",
            audio_languages=["Swedish"],
            original_language="ja",
        )
        result = _run(dp.get_name(meta))
        assert "Swedish Dubbed" in result["name"]
        assert result["name"].index("Swedish Dubbed") < result["name"].index("AAC 2.0")


class TestDpKeepFolderStrip:
    """Global keep_folder auto-strip via UploadHelper.strip_keep_folder_if_single_file.

    This logic now lives in uphelper.py, not in DP.get_additional_checks.
    These tests call the static helper directly to verify the contract.
    """

    from src.uphelper import UploadHelper

    def test_keep_folder_stripped_for_single_movie(self) -> None:
        """keep_folder=True on a non-disc non-tv_pack single-file release: must be set to False."""
        from src.uphelper import UploadHelper

        meta = _base_meta(keep_folder=True, is_disc=False, tv_pack=False, filelist=["/tmp/movie.mkv"])
        stripped = UploadHelper.strip_keep_folder_if_single_file(meta)
        assert stripped is True
        assert meta["keep_folder"] is False

    def test_keep_folder_unchanged_for_tv_pack(self) -> None:
        """keep_folder=True on a TV pack: must not be touched."""
        from src.uphelper import UploadHelper

        meta = _base_meta(keep_folder=True, tv_pack=True, is_disc=False, filelist=["/tmp/ep.mkv"])
        stripped = UploadHelper.strip_keep_folder_if_single_file(meta)
        assert stripped is False
        assert meta["keep_folder"] is True

    def test_keep_folder_unchanged_for_disc(self) -> None:
        """keep_folder=True on a disc release: must not be touched."""
        from src.uphelper import UploadHelper

        meta = _base_meta(keep_folder=True, is_disc=True, tv_pack=False, filelist=["/tmp/disc.mkv"])
        stripped = UploadHelper.strip_keep_folder_if_single_file(meta)
        assert stripped is False
        assert meta["keep_folder"] is True

    def test_keep_folder_unchanged_for_multi_file(self) -> None:
        """keep_folder=True with multiple files: must not be touched."""
        from src.uphelper import UploadHelper

        meta = _base_meta(keep_folder=True, is_disc=False, tv_pack=False, filelist=["/tmp/a.mkv", "/tmp/b.mkv"])
        stripped = UploadHelper.strip_keep_folder_if_single_file(meta)
        assert stripped is False
        assert meta["keep_folder"] is True

    def test_keep_folder_false_unchanged(self) -> None:
        """keep_folder=False: nothing changes, returns False."""
        from src.uphelper import UploadHelper

        meta = _base_meta(keep_folder=False, is_disc=False, tv_pack=False, filelist=["/tmp/movie.mkv"])
        stripped = UploadHelper.strip_keep_folder_if_single_file(meta)
        assert stripped is False
        assert meta["keep_folder"] is False


class TestDpAdditionalChecks:
    def _check(self, **overrides: Any) -> bool:
        dp = _dp()
        dp.common.check_language_requirements = AsyncMock(return_value=True)
        return _run(dp.get_additional_checks(_base_meta(unattended=True, **overrides)))

    def test_evo_only_as_webdl_with_hyphenated_tag(self) -> None:
        assert self._check(tag="-EVO", type="WEBDL") is True
        assert self._check(tag="-EVO", type="ENCODE") is False

    def test_hdt_only_as_remux(self) -> None:
        assert self._check(tag="-HDT", type="REMUX") is True
        assert self._check(tag="-HDT", type="ENCODE") is False

    def test_hardcoded_subs_rejected_even_unattended(self) -> None:
        assert self._check(hardcoded_subs=True) is False
