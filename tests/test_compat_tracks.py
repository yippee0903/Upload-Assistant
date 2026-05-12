# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Tests for compatibility-track detection and the ULCX gate.

Covers:
  1. check_disallowed_compat_tracks() — unit tests for every distinct case.
  2. ULCX.get_additional_checks() — integration tests for the compat-track gate.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.audio import check_disallowed_compat_tracks


# ─── helpers ────────────────────────────────────────────────────────────────


def _meta(**overrides: Any) -> dict[str, Any]:
    m: dict[str, Any] = {"debug": False}
    m.update(overrides)
    return m


def _track(fmt: str, lang: str = "zh") -> dict[str, Any]:
    return {"@type": "Audio", "Format": fmt, "Language": lang}


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _config() -> dict[str, Any]:
    return {
        "DEFAULT": {"tmdb_api": "fake"},
        "TRACKERS": {
            "ULCX": {
                "api_key": "FAKE",
                "announce_url": "https://upload.cx/announce/FAKE",
            }
        },
    }


def _base_ulcx_meta(**overrides: Any) -> dict[str, Any]:
    """Minimal meta that passes all earlier guards in get_additional_checks."""
    m: dict[str, Any] = {
        "keywords": "",
        "video_codec": "H.264",
        "resolution": "1080p",
        "type": "WEBDL",
        "is_disc": False,
        "valid_mi_settings": True,
        "personalrelease": False,
        "non_disc_has_pcm_audio_tracks": False,
        "discs_missing_certificate": [],
        "unattended": True,
        "unattended_confirm": False,
        "debug": False,
        "anime": False,
        "trackers": ["ULCX"],
    }
    m.update(overrides)
    return m


# ═══════════════════════════════════════════════════════════════════════════
#  1. Unit tests for check_disallowed_compat_tracks()
# ═══════════════════════════════════════════════════════════════════════════


class TestNoTracks:
    def test_empty_list_does_not_set_flag(self):
        meta = _meta()
        check_disallowed_compat_tracks(meta, [])
        assert not meta.get("has_disallowed_compat_track")

    def test_single_track_does_not_set_flag(self):
        meta = _meta()
        check_disallowed_compat_tracks(meta, [_track("E-AC-3")])
        assert not meta.get("has_disallowed_compat_track")


class TestAllowedCases:
    """Situations that must NOT trigger the flag."""

    def test_truehd_plus_ac3_same_lang_allowed(self):
        """TrueHD + AC-3 is the only allowed compat-track combo."""
        meta = _meta()
        tracks = [_track("MLP FBA", "en"), _track("AC-3", "en")]
        check_disallowed_compat_tracks(meta, tracks)
        assert not meta.get("has_disallowed_compat_track")

    def test_truehd_atmos_plus_ac3_same_lang_allowed(self):
        """Atmos embeds are still MLP FBA in MediaInfo — must remain allowed."""
        meta = _meta()
        tracks = [_track("MLP FBA", "en"), _track("AC-3", "en")]
        check_disallowed_compat_tracks(meta, tracks)
        assert not meta.get("has_disallowed_compat_track")

    def test_two_distinct_languages_no_compat_issue(self):
        """Two tracks in different languages are not a compat-track situation."""
        meta = _meta()
        tracks = [_track("E-AC-3", "zh"), _track("AAC", "en")]
        check_disallowed_compat_tracks(meta, tracks)
        assert not meta.get("has_disallowed_compat_track")

    def test_two_eac3_same_lang_no_compat_codec(self):
        """Two tracks with the same non-compat codec — nothing to flag."""
        meta = _meta()
        tracks = [_track("E-AC-3", "zh"), _track("E-AC-3", "zh")]
        check_disallowed_compat_tracks(meta, tracks)
        assert not meta.get("has_disallowed_compat_track")

    def test_two_aac_same_lang_all_compat_codecs(self):
        """Two compat-codec tracks for the same lang — edge case, not flagged."""
        meta = _meta()
        tracks = [_track("AAC", "zh"), _track("AAC", "zh")]
        check_disallowed_compat_tracks(meta, tracks)
        assert not meta.get("has_disallowed_compat_track")

    def test_single_aac_track(self):
        """A single AAC track has no companion — not a compat track."""
        meta = _meta()
        check_disallowed_compat_tracks(meta, [_track("AAC", "zh")])
        assert not meta.get("has_disallowed_compat_track")


class TestDisallowedCases:
    """Situations that MUST set has_disallowed_compat_track = True."""

    def test_aac_plus_eac3_same_lang(self):
        """Exact case from the IQIYI release: AAC LC + E-AC-3 in Chinese."""
        meta = _meta()
        # MediaInfo reports "AAC LC" or "AAC" for the compat track
        tracks = [_track("AAC", "zh"), _track("E-AC-3", "zh")]
        check_disallowed_compat_tracks(meta, tracks)
        assert meta.get("has_disallowed_compat_track") is True

    def test_ac3_plus_eac3_same_lang(self):
        """AC-3 used as compat alongside DD+ (not TrueHD) — disallowed."""
        meta = _meta()
        tracks = [_track("E-AC-3", "en"), _track("AC-3", "en")]
        check_disallowed_compat_tracks(meta, tracks)
        assert meta.get("has_disallowed_compat_track") is True

    def test_aac_plus_dts_same_lang(self):
        """AAC compat alongside DTS — disallowed."""
        meta = _meta()
        tracks = [_track("DTS", "en"), _track("AAC", "en")]
        check_disallowed_compat_tracks(meta, tracks)
        assert meta.get("has_disallowed_compat_track") is True

    def test_aac_plus_truehd_same_lang_disallowed(self):
        """TrueHD + AC-3 is allowed, but TrueHD + AAC is not."""
        meta = _meta()
        tracks = [_track("MLP FBA", "en"), _track("AAC", "en")]
        check_disallowed_compat_tracks(meta, tracks)
        assert meta.get("has_disallowed_compat_track") is True

    def test_ac3_plus_dts_hdma_same_lang(self):
        """AC-3 compat alongside DTS-HD MA — disallowed."""
        meta = _meta()
        tracks = [_track("DTS", "en"), _track("AC-3", "en")]
        check_disallowed_compat_tracks(meta, tracks)
        assert meta.get("has_disallowed_compat_track") is True

    def test_flag_not_reset_when_already_false(self):
        """Calling on clean tracks must not clobber an existing True flag."""
        meta = _meta(has_disallowed_compat_track=True)
        tracks = [_track("MLP FBA", "en"), _track("AC-3", "en")]
        check_disallowed_compat_tracks(meta, tracks)
        # Allowed combo — function should not touch the flag
        # But since a prior call already set it, it stays True
        assert meta.get("has_disallowed_compat_track") is True

    def test_only_disallowed_lang_group_triggers(self):
        """Flag fires even when another language group is perfectly clean."""
        meta = _meta()
        tracks = [
            _track("MLP FBA", "en"),  # clean English TrueHD
            _track("AC-3", "en"),  # allowed AC-3 compat for TrueHD
            _track("E-AC-3", "zh"),  # main Chinese track
            _track("AAC", "zh"),  # disallowed AAC compat alongside E-AC-3
        ]
        check_disallowed_compat_tracks(meta, tracks)
        assert meta.get("has_disallowed_compat_track") is True

    def test_missing_language_field_treated_as_group(self):
        """Tracks with no Language are grouped together as unknown."""
        meta = _meta()
        tracks = [
            {"@type": "Audio", "Format": "E-AC-3"},
            {"@type": "Audio", "Format": "AAC"},
        ]
        check_disallowed_compat_tracks(meta, tracks)
        assert meta.get("has_disallowed_compat_track") is True


# ═══════════════════════════════════════════════════════════════════════════
#  2. ULCX.get_additional_checks() — compat-track gate
# ═══════════════════════════════════════════════════════════════════════════


def _make_ulcx():
    from src.trackers.ULCX import ULCX

    ulcx = ULCX(_config())
    # Stub out the language-requirements check so it always passes
    ulcx.common = MagicMock()
    ulcx.common.check_language_requirements = AsyncMock(return_value=True)
    return ulcx


class TestUlcxCompatTrackGate:
    """get_additional_checks() must reject releases with disallowed compat tracks."""

    def test_no_compat_track_passes(self):
        ulcx = _make_ulcx()
        meta = _base_ulcx_meta(has_disallowed_compat_track=False)
        assert _run(ulcx.get_additional_checks(meta)) is True

    def test_compat_track_unattended_returns_false(self):
        """In unattended mode (no confirm), the upload is skipped."""
        ulcx = _make_ulcx()
        meta = _base_ulcx_meta(
            has_disallowed_compat_track=True,
            unattended=True,
            unattended_confirm=False,
        )
        assert _run(ulcx.get_additional_checks(meta)) is False

    def test_compat_track_unattended_confirm_asks_and_accepts(self):
        """unattended=True + unattended_confirm=True → asks; user says yes → continues."""
        ulcx = _make_ulcx()
        meta = _base_ulcx_meta(
            has_disallowed_compat_track=True,
            unattended=True,
            unattended_confirm=True,
        )
        with patch("cli_ui.ask_yes_no", return_value=True):
            assert _run(ulcx.get_additional_checks(meta)) is True

    def test_compat_track_unattended_confirm_asks_and_rejects(self):
        """unattended=True + unattended_confirm=True → asks; user says no → aborts."""
        ulcx = _make_ulcx()
        meta = _base_ulcx_meta(
            has_disallowed_compat_track=True,
            unattended=True,
            unattended_confirm=True,
        )
        with patch("cli_ui.ask_yes_no", return_value=False):
            assert _run(ulcx.get_additional_checks(meta)) is False

    def test_compat_track_attended_user_accepts(self):
        """Attended mode (unattended=False) → asks; user confirms → continues."""
        ulcx = _make_ulcx()
        meta = _base_ulcx_meta(
            has_disallowed_compat_track=True,
            unattended=False,
        )
        with patch("cli_ui.ask_yes_no", return_value=True):
            assert _run(ulcx.get_additional_checks(meta)) is True

    def test_compat_track_attended_user_rejects(self):
        """Attended mode → user says no → aborts."""
        ulcx = _make_ulcx()
        meta = _base_ulcx_meta(
            has_disallowed_compat_track=True,
            unattended=False,
        )
        with patch("cli_ui.ask_yes_no", return_value=False):
            assert _run(ulcx.get_additional_checks(meta)) is False

    def test_no_compat_flag_key_passes(self):
        """Absence of the key (not set at all) is treated as False — should pass."""
        ulcx = _make_ulcx()
        meta = _base_ulcx_meta()
        meta.pop("has_disallowed_compat_track", None)
        assert _run(ulcx.get_additional_checks(meta)) is True
