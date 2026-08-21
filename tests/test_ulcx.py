# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Tests for ULCX tracker."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

import pytest

from src.trackers.ULCX import ULCX


def _run(coro):
    return asyncio.run(coro)


def _config() -> dict[str, Any]:
    return {
        "TRACKERS": {"ULCX": {"api_key": "fake", "announce_url": ""}},
        "DEFAULT": {"tmdb_api": "fake"},
    }


# ═══════════════════════════════════════════════════════════════
#  get_additional_checks() — pre-upload validations
# ═══════════════════════════════════════════════════════════════


class TestULCXAdditionalChecks:
    """ULCX additional checks: service presence/absence for WEBDL and WEBRIP."""

    @pytest.fixture
    def ulcx(self):
        return ULCX(config=_config())

    def _base_meta(self) -> dict[str, Any]:
        return {
            "resolution": "1080p",
            "valid_mi_settings": True,
            "source": "BluRay",
            "type": "ENCODE",
            "service": "",
            "is_disc": None,
            "video_codec": "AVC",
            "keywords": [],
            "language_checked": True,
            "audio_languages": ["English"],
            "subtitle_languages": ["English"],
            "unattended": False,
            "debug": False,
            "personalrelease": False,
            "has_multiple_default_audio_tracks": False,
            "has_multiple_default_subtitle_tracks": False,
            "non_disc_has_pcm_audio_tracks": False,
            "has_disallowed_compat_track": False,
            "discs_missing_certificate": [],
            "combined_genres": "",
            "tmdb_id": 12345,
            "filelist": ["/r/a.mkv"],
            "image_list": [{}, {}, {}],
        }

    def test_valid_meta_passes(self, ulcx):
        """A well-formed BluRay encode with English audio must pass all checks."""
        meta = self._base_meta()
        assert _run(ulcx.get_additional_checks(meta)) is True

    def test_webdl_with_service_passes(self, ulcx):
        """A WEB-DL with a recognised streaming service must pass the source check."""
        meta = self._base_meta()
        meta["source"] = "Web"
        meta["type"] = "WEBDL"
        meta["service"] = "NF"
        assert _run(ulcx.get_additional_checks(meta)) is True

    def test_webdl_without_service_fails(self, ulcx):
        """A WEB-DL without a streaming service must be rejected."""
        meta = self._base_meta()
        meta["source"] = "Web"
        meta["type"] = "WEBDL"
        meta["service"] = ""
        assert _run(ulcx.get_additional_checks(meta)) is False

    def test_webrip_without_service_fails(self, ulcx):
        """A WEBRip without a streaming service must also be rejected."""
        meta = self._base_meta()
        meta["source"] = "Web"
        meta["type"] = "WEBRIP"
        meta["service"] = ""
        assert _run(ulcx.get_additional_checks(meta)) is False

    def test_webdl_missing_service_prints_red_message(self, ulcx, capsys):
        """When a WEB-DL has no service and not unattended, a red console message must be printed."""
        meta = self._base_meta()
        meta["source"] = "Web"
        meta["type"] = "WEBDL"
        meta["service"] = ""
        with patch("src.trackers.ULCX.console") as mock_console:
            result = _run(ulcx.get_additional_checks(meta))
        assert result is False
        mock_console.print.assert_any_call(
            f"[bold red]Streaming service is missing, skipping {ulcx.tracker} upload.[/bold red]"
        )

    def test_unattended_webdl_missing_service_no_print(self, ulcx):
        """In unattended mode, the service-missing message must be suppressed but upload still skipped."""
        meta = self._base_meta()
        meta["source"] = "Web"
        meta["type"] = "WEBDL"
        meta["service"] = ""
        meta["unattended"] = True
        with patch("src.trackers.ULCX.console") as mock_console:
            result = _run(ulcx.get_additional_checks(meta))
        assert result is False
        for call in mock_console.print.call_args_list:
            assert "Streaming service is missing" not in str(call)


# ═══════════════════════════════════════════════════════════════
#  get_additional_checks() — content, container, audio and subtitle rules
# ═══════════════════════════════════════════════════════════════


def _audio(fmt: str, channels: int, commercial: str = "", lossless: bool = False) -> dict[str, Any]:
    track: dict[str, Any] = {"@type": "Audio", "Format": fmt, "Channels": str(channels), "Format_Commercial_IfAny": commercial}
    if lossless:
        track["Compression_Mode"] = "Lossless"
    return track


def _text(lang: str, default: bool) -> dict[str, Any]:
    return {"@type": "Text", "Language": lang, "Default": "Yes" if default else "No"}


def _mi(*tracks: dict[str, Any], general: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"media": {"track": [{"@type": "General", **(general or {})}, *tracks]}}


class TestULCXRules:
    @pytest.fixture
    def ulcx(self):
        return ULCX(config=_config())

    def _meta(self, **overrides: Any) -> dict[str, Any]:
        meta = TestULCXAdditionalChecks()._base_meta()
        meta.update({"unattended": True, "audio": "DD 5.1", "original_language": "en", "mediainfo": _mi()})
        meta.update(overrides)
        return meta

    def _passes(self, ulcx, **overrides: Any) -> bool:
        with patch.object(ulcx.common, "check_language_requirements", return_value=True):
            return _run(ulcx.get_additional_checks(self._meta(**overrides)))

    def test_baseline_passes(self, ulcx):
        assert self._passes(ulcx) is True

    def test_no_tmdb_match_is_rejected(self, ulcx):
        assert self._passes(ulcx, tmdb_id=0) is False

    def test_av1_live_action_rejected_unattended_but_allowed_for_animation(self, ulcx):
        assert self._passes(ulcx, video_codec="AV1") is False
        assert self._passes(ulcx, video_codec="AV1", keywords="animation") is True

    def test_sd_hdtv_is_asked_not_rejected(self, ulcx):
        with patch("src.trackers.COMMON.cli_ui.ask_yes_no", return_value=True):
            assert self._passes(ulcx, type="HDTV", resolution="576p", unattended=False) is True
        assert self._passes(ulcx, type="ENCODE", resolution="576p", unattended=False) is False

    def test_non_mkv_container_is_rejected(self, ulcx):
        assert self._passes(ulcx, filelist=["/r/a.mp4"]) is False
        assert self._passes(ulcx, filelist=["/r/a.ts"], type="HDTV") is True
        assert self._passes(ulcx, filelist=["/r/a.ts"]) is False

    def test_fewer_than_three_screenshots_is_rejected(self, ulcx):
        assert self._passes(ulcx, image_list=[{}, {}]) is False

    def test_flac_multichannel_is_rejected(self, ulcx):
        assert self._passes(ulcx, mediainfo=_mi(_audio("FLAC", 6))) is False
        assert self._passes(ulcx, mediainfo=_mi(_audio("FLAC", 2))) is True

    def test_lossless_multichannel_on_1080p_encode_is_rejected(self, ulcx):
        dtshd = _audio("DTS", 6, commercial="DTS-HD Master Audio")
        assert self._passes(ulcx, mediainfo=_mi(dtshd)) is False
        assert self._passes(ulcx, mediainfo=_mi(dtshd), resolution="2160p") is True
        assert self._passes(ulcx, mediainfo=_mi(dtshd), resolution="4320p") is True
        assert self._passes(ulcx, mediainfo=_mi(dtshd), resolution="8640p") is True
        assert self._passes(ulcx, mediainfo=_mi(_audio("DTS", 6, commercial="DTS"))) is True

    def test_remux_lossless_audio_conversions(self, ulcx):
        def remux(track: dict[str, Any]) -> bool:
            return self._passes(ulcx, type="REMUX", mediainfo=_mi(track))

        assert remux(_audio("DTS", 2, commercial="DTS-HD Master Audio")) is False
        assert remux(_audio("FLAC", 2)) is True
        assert remux(_audio("MLP FBA", 1, commercial="Dolby TrueHD")) is False
        assert remux(_audio("DTS", 1, commercial="DTS-HD Master Audio")) is True
        assert remux(_audio("FLAC", 1)) is True
        assert remux(_audio("DTS", 6, commercial="DTS-HD Master Audio")) is True
        assert remux(_audio("MLP FBA", 8, commercial="Dolby TrueHD with Dolby Atmos")) is True
        assert remux(_audio("DTS", 6, commercial="DTS")) is True
        assert remux({"@type": "Audio", "Format": "DTS", "Channels": "8", "Format_Commercial_IfAny": "DTS:X", "Format_AdditionalFeatures": "XLL X"}) is True

    def test_recommendations_block_only_personal_releases(self, ulcx):
        handbrake = _mi(general={"Encoded_Application": "HandBrake 1.7.0"})
        assert self._passes(ulcx, mediainfo=handbrake) is True
        assert self._passes(ulcx, mediainfo=handbrake, personalrelease=True) is False
        assert self._passes(ulcx, audio="Dubbed DD 5.1", personalrelease=True) is False

    def test_default_subtitle_rules_for_personal_releases(self, ulcx):
        foreign_fr_default = _mi(_text("fr", True), _text("en", False))
        assert self._passes(ulcx, original_language="fr", mediainfo=foreign_fr_default, personalrelease=True) is False
        assert self._passes(ulcx, original_language="fr", mediainfo=_mi(_text("en", True)), personalrelease=True) is True
        assert self._passes(ulcx, original_language="en", mediainfo=_mi(_text("en", True)), personalrelease=True) is False
        assert self._passes(ulcx, original_language="en", mediainfo=_mi(_text("en", False)), personalrelease=True) is True
        assert self._passes(ulcx, original_language="", mediainfo=_mi(_text("en", True)), personalrelease=True) is True
