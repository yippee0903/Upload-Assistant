# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Tests for ACM (Asian Cinema) tracker."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.trackers.ACM import ACM


def _run(coro):
    return asyncio.run(coro)


def _config() -> dict[str, Any]:
    return {
        "DEFAULT": {"tmdb_api": "fake"},
        "TRACKERS": {
            "ACM": {
                "api_key": "FAKE_KEY",
                "announce_url": "https://eiga.moi/announce/FAKE_PASSKEY",
            },
        },
    }


def _meta(**overrides: Any) -> dict[str, Any]:
    m: dict[str, Any] = {
        "origin_country": [],
        "production_countries": [],
        "original_language": "en",
        "tracker_status": {"ACM": {}},
    }
    m.update(overrides)
    return m


class TestCheckAsianOrigin:
    """Verify check_asian_origin logic with origin_country vs production_countries."""

    def test_japanese_origin(self):
        """A purely Japanese show should pass."""
        acm = ACM(_config())
        meta = _meta(origin_country=["JP"])
        assert acm.check_asian_origin(meta) is True

    def test_korean_origin(self):
        """A Korean show should pass."""
        acm = ACM(_config())
        meta = _meta(origin_country=["KR"])
        assert acm.check_asian_origin(meta) is True

    def test_us_origin_only(self):
        """A purely US show should NOT pass."""
        acm = ACM(_config())
        meta = _meta(origin_country=["US"])
        assert acm.check_asian_origin(meta) is False

    def test_us_origin_with_jp_production(self):
        """US origin with Japanese co-production should NOT pass.

        This is the Monarch: Legacy of Monsters case — an American show
        co-produced with a Japanese studio. origin_country=['US'] takes
        priority over production_countries containing JP.
        """
        acm = ACM(_config())
        meta = _meta(
            origin_country=["US"],
            production_countries=[
                {"iso_3166_1": "JP", "name": "Japan"},
                {"iso_3166_1": "US", "name": "United States of America"},
            ],
        )
        assert acm.check_asian_origin(meta) is False

    def test_jp_origin_with_us_production(self):
        """Japanese origin with US co-production should pass."""
        acm = ACM(_config())
        meta = _meta(
            origin_country=["JP"],
            production_countries=[
                {"iso_3166_1": "US", "name": "United States of America"},
                {"iso_3166_1": "JP", "name": "Japan"},
            ],
        )
        assert acm.check_asian_origin(meta) is True

    def test_multi_asian_origin(self):
        """Multiple Asian origin countries should pass."""
        acm = ACM(_config())
        meta = _meta(origin_country=["JP", "KR"])
        assert acm.check_asian_origin(meta) is True

    def test_mixed_origin_with_asian(self):
        """US + KR origin — at least one Asian country means pass."""
        acm = ACM(_config())
        meta = _meta(origin_country=["US", "KR"])
        assert acm.check_asian_origin(meta) is True

    def test_fallback_to_production_countries(self):
        """When origin_country is empty, fall back to production_countries."""
        acm = ACM(_config())
        meta = _meta(
            origin_country=[],
            production_countries=[
                {"iso_3166_1": "IN", "name": "India"},
            ],
        )
        assert acm.check_asian_origin(meta) is True

    def test_fallback_non_asian_production(self):
        """When origin_country is empty and production is non-Asian, reject."""
        acm = ACM(_config())
        meta = _meta(
            origin_country=[],
            production_countries=[
                {"iso_3166_1": "FR", "name": "France"},
            ],
        )
        assert acm.check_asian_origin(meta) is False

    def test_no_country_data(self):
        """No origin or production data should reject."""
        acm = ACM(_config())
        meta = _meta(origin_country=[], production_countries=[])
        assert acm.check_asian_origin(meta) is False

    def test_none_origin_fallback(self):
        """origin_country=None should fall back to production_countries."""
        acm = ACM(_config())
        meta = _meta(
            origin_country=None,
            production_countries=[{"iso_3166_1": "TH", "name": "Thailand"}],
        )
        assert acm.check_asian_origin(meta) is True

    def test_case_insensitive(self):
        """Country codes should be matched case-insensitively."""
        acm = ACM(_config())
        meta = _meta(origin_country=["jp"])
        assert acm.check_asian_origin(meta) is True

    def test_empty_strings_in_origin_fallback(self):
        """origin_country with only empty/blank strings should fall back to production_countries."""
        acm = ACM(_config())
        meta = _meta(
            origin_country=["", "  ", None],
            production_countries=[{"iso_3166_1": "KR", "name": "South Korea"}],
        )
        assert acm.check_asian_origin(meta) is True

    def test_empty_strings_in_origin_no_fallback(self):
        """origin_country with only empty strings and no production data should reject."""
        acm = ACM(_config())
        meta = _meta(origin_country=["", None], production_countries=[])
        assert acm.check_asian_origin(meta) is False


def _name_meta(base_name: str, **overrides: Any) -> dict[str, Any]:
    """Build a minimal meta dict for get_name() tests."""
    m: dict[str, Any] = {
        "name": base_name,
        "aka": "",
        "original_title": "",
        "title": base_name.split()[0],
        "audio": "",
        "source": "",
        "is_disc": None,
        "type": "WEBDL",
        "resolution": "1080p",
        "hdr": "",
        "category": "MOVIE",
        "year": "2019",
        "season": "",
        "mediainfo": {"media": {"track": []}},
        "bdinfo": None,
    }
    m.update(overrides)
    return m


class TestGetName:
    """Verify ACM-specific naming transformations in get_name()."""

    # ------------------------------------------------------------------ WEB-DL

    def test_webdl_aac_no_space(self):
        """AAC 2.0 → AAC2.0 for WEB-DL (stream = no space after audio codec)."""
        acm = ACM(_config())
        # UA base: "Title 1986 1080p WEB-DL AAC 2.0 H.264"
        meta = _name_meta(
            "Title 1986 1080p WEB-DL AAC 2.0 H.264",
            audio="AAC 2.0",
            type="WEBDL",
        )
        result = _run(acm.get_name(meta))
        assert "AAC2.0" in result
        assert "AAC 2.0" not in result

    def test_webdl_ddplus_no_space(self):
        """DD+ 5.1 → DD+5.1 for WEB-DL."""
        acm = ACM(_config())
        meta = _name_meta(
            "Title 2019 2160p WEB-DL DD+ 5.1 DoVi HEVC",
            audio="DD+ 5.1",
            hdr="DoVi",
            type="WEBDL",
        )
        result = _run(acm.get_name(meta))
        assert "DD+5.1" in result
        assert "DD+ 5.1" not in result

    def test_webdl_dd_no_space(self):
        """DD 5.1 → DD5.1 for streams (non-plus Dolby Digital)."""
        acm = ACM(_config())
        meta = _name_meta(
            "Title 2001 480p WEB-DL DD 5.1 H.264",
            audio="DD 5.1",
            type="WEBDL",
        )
        result = _run(acm.get_name(meta))
        assert "DD5.1" in result
        assert "DD 5.1" not in result

    def test_webdl_audio_before_video(self):
        """Audio codec must stay BEFORE video codec for WEB-DL (ACM stream rule)."""
        acm = ACM(_config())
        # UA base name already has audio before video: "WEB-DL AAC 2.0 H.264"
        meta = _name_meta(
            "To Sleep So As To Dream 1986 1080p WEB-DL AAC 2.0 H.264",
            audio="AAC 2.0",
            type="WEBDL",
        )
        result = _run(acm.get_name(meta))
        # Guide example: "1986 1080p WEB-DL AAC2.0 H.264"
        assert result.index("AAC2.0") < result.index("H.264")

    def test_webdl_audio_before_video_with_hdr(self):
        """For WEB-DL with HDR: audio → HDR → video (ACM stream order)."""
        acm = ACM(_config())
        # UA base: "Title 2019 2160p WEB-DL DD+ 5.1 DoVi HEVC"
        meta = _name_meta(
            "Hunt Down 2019 2160p WEB-DL DD+ 5.1 DoVi HEVC",
            audio="DD+ 5.1",
            hdr="DoVi",
            type="WEBDL",
        )
        result = _run(acm.get_name(meta))
        # Guide example: "2019 2160p WEB-DL DD+5.1 DoVi HEVC"
        assert result.index("DD+5.1") < result.index("DoVi") < result.index("HEVC")

    def test_webdl_service_tag_preserved(self):
        """Streaming service tag (NF) is preserved in output."""
        acm = ACM(_config())
        meta = _name_meta(
            "The Ghost Bride S01 2160p NF WEB-DL DD+ 5.1 DoVi HDR HEVC",
            audio="DD+ 5.1",
            hdr="DoVi HDR",
            type="WEBDL",
            category="TV",
            season="S01",
            year="2020",
        )
        result = _run(acm.get_name(meta))
        assert "NF" in result

    # ------------------------------------------------------------------ HDTV

    def test_hdtv_aac_no_space(self):
        """AAC 5.1 → AAC5.1 for HDTV (stream)."""
        acm = ACM(_config())
        meta = _name_meta(
            "Ramen Shop 2018 1080i HDTV AAC 5.1 H.264",
            audio="AAC 5.1",
            type="HDTV",
        )
        result = _run(acm.get_name(meta))
        assert "AAC5.1" in result

    def test_hdtv_dd_no_space(self):
        """DD 5.1 → DD5.1 for HDTV (stream)."""
        acm = ACM(_config())
        meta = _name_meta(
            "Loan Shark S01 1080i HDTV DD 5.1 H.264",
            audio="DD 5.1",
            type="HDTV",
            category="TV",
            season="S01",
        )
        result = _run(acm.get_name(meta))
        assert "DD5.1" in result

    # ------------------------------------------------------------------ REMUX

    def test_remux_bluray_prefix_removed(self):
        """'BluRay REMUX' → 'Remux' for remux releases."""
        acm = ACM(_config())
        meta = _name_meta(
            "Oldboy 2003 2160p BluRay REMUX HEVC DTS-HD MA 5.1",
            audio="DTS-HD MA 5.1",
            type="REMUX",
        )
        result = _run(acm.get_name(meta))
        assert "Remux" in result
        assert "BluRay REMUX" not in result

    def test_remux_uhd_bluray_prefix_removed(self):
        """'UHD BluRay REMUX' → 'Remux' for UHD remux releases."""
        acm = ACM(_config())
        meta = _name_meta(
            "Oldboy 2003 2160p UHD BluRay REMUX HEVC DTS-HD MA 5.1",
            audio="DTS-HD MA 5.1",
            type="REMUX",
        )
        result = _run(acm.get_name(meta))
        assert "Remux" in result
        assert "UHD BluRay REMUX" not in result

    def test_remux_audio_has_space(self):
        """Physical media (remux) keeps space after audio codec: 'DTS-HD MA 5.1'."""
        acm = ACM(_config())
        meta = _name_meta(
            "Title 2019 1080p BluRay REMUX AVC TrueHD 5.1",
            audio="TrueHD 5.1",
            type="REMUX",
        )
        result = _run(acm.get_name(meta))
        assert "TrueHD 5.1" in result

    # ------------------------------------------------------------------ H.265 → HEVC

    def test_h265_replaced_by_hevc(self):
        """H.265 is always replaced by HEVC."""
        acm = ACM(_config())
        meta = _name_meta(
            "Title 2019 2160p WEB-DL DD+ 5.1 H.265",
            audio="DD+ 5.1",
            type="WEBDL",
        )
        result = _run(acm.get_name(meta))
        assert "HEVC" in result
        assert "H.265" not in result

    # ------------------------------------------------------------------ Atmos

    def test_atmos_removed(self):
        """' Atmos' suffix is stripped from the name."""
        acm = ACM(_config())
        meta = _name_meta(
            "Title 2019 2160p WEB-DL DD+ 5.1 Atmos HEVC",
            audio="DD+ 5.1 Atmos",
            type="WEBDL",
        )
        result = _run(acm.get_name(meta))
        assert "Atmos" not in result

    # ------------------------------------------------------------------ Subtitle tags

    def test_no_subs_tag_appended(self):
        """[No subs] tag is appended when no subtitles are present."""
        acm = ACM(_config())
        meta = _name_meta(
            "Oldboy 2003 2160p KOR UHD Blu-ray HEVC DTS-HD MA 5.1",
            audio="DTS-HD MA 5.1",
            type="DISC",
            is_disc="BDMV",
            bdinfo={"subtitles": []},
        )
        result = _run(acm.get_name(meta))
        assert result.endswith("[No subs]")

    # ------------------------------------------------------------------ TV season/year

    def test_tv_year_removed(self):
        """Year is removed from TV names; only season remains."""
        acm = ACM(_config())
        meta = _name_meta(
            "Kingdom 2019 S02 2160p WEB-DL DD+ 5.1 HDR HEVC",
            audio="DD+ 5.1",
            hdr="HDR",
            type="WEBDL",
            category="TV",
            season="S02",
            year="2019",
        )
        result = _run(acm.get_name(meta))
        assert "S02" in result
        # year should be gone for TV
        assert "2019" not in result


# --------------------------------------------------------------------------- #
# Helpers for real-file integration tests                                      #
# --------------------------------------------------------------------------- #


def _text_tracks(*langs: str) -> dict[str, Any]:
    """Return a minimal mediainfo dict containing one Text track per language."""
    return {"media": {"track": [{"@type": "Text", "Language": lang} for lang in langs]}}


# --------------------------------------------------------------------------- #
# get_subtitles – BCP 47 regional code handling                               #
# --------------------------------------------------------------------------- #


class TestGetSubtitles:
    """Verify that BCP 47 regional language codes are recognised correctly."""

    def test_en_us_recognised_as_english(self):
        """'en-US' must map to 'Eng', not be silently dropped."""
        acm = ACM(_config())
        meta = _name_meta(
            "Title 2011 1080p WEB-DL DD+ 2.0 H.264",
            mediainfo=_text_tracks("en-US"),
        )
        subs = acm.get_subtitles(meta)
        assert "Eng" in subs

    def test_zh_hans_recognised_as_chinese(self):
        """'zh-Hans' must map to 'Chi'."""
        acm = ACM(_config())
        meta = _name_meta(
            "Title 2020 1080p WEB-DL AAC 2.0 H.264",
            mediainfo=_text_tracks("zh-Hans"),
        )
        subs = acm.get_subtitles(meta)
        assert "Chi" in subs

    def test_es_es_recognised_as_spanish(self):
        """'es-ES' must map to 'Spa'."""
        acm = ACM(_config())
        meta = _name_meta(
            "Title 2020 1080p WEB-DL AAC 2.0 H.264",
            mediainfo=_text_tracks("es-ES"),
        )
        subs = acm.get_subtitles(meta)
        assert "Spa" in subs

    def test_en_us_triggers_no_subs_tag_suppression(self):
        """A release with only en-US subs must NOT get a [No subs] or [No Eng subs] tag."""
        acm = ACM(_config())
        subs = acm.get_subtitles(
            _name_meta("T 2020 1080p WEB-DL AAC 2.0 H.264", mediainfo=_text_tracks("en-US"))
        )
        assert acm.get_subs_tag(subs) == ""


# --------------------------------------------------------------------------- #
# Real-file integration tests (name verified against ACM staff uploads)       #
# --------------------------------------------------------------------------- #


class TestGetNameRealFiles:
    """End-to-end get_name() checks based on actual uploaded torrents.

    Audio / subtitle data was gathered by running ``mediainfo --Output=JSON``
    on the real files; the expected names were confirmed on the tracker.
    """

    def test_voice_s01_2160p_webdl(self):
        """Voice S01 2160p WEB-DL – Korean series, no English subs."""
        acm = ACM(_config())
        # Real subs from mediainfo: zh zh en id th ms vi → has 'en' → no subs tag
        meta = _name_meta(
            "Voice 2017 S01 2160p WEB-DL AAC 2.0 H.265-FLTTH",
            audio="AAC 2.0",
            original_title="보이스",
            title="Voice",
            type="WEBDL",
            category="TV",
            year="2017",
            season="S01",
            mediainfo=_text_tracks("zh", "zh", "en", "id", "th", "ms", "vi"),
        )
        assert _run(acm.get_name(meta)) == "Voice / 보이스 S01 2160p WEB-DL AAC2.0 HEVC-FLTTH"

    def test_atypical_family_s01_2160p_tving(self):
        """The Atypical Family S01 2160p TVING WEB-DL – Korean series, English subs present."""
        acm = ACM(_config())
        # Real subs include 'en' among many others → has Eng → no subs tag
        meta = _name_meta(
            "The Atypical Family 2024 S01 2160p TVING WEB-DL AAC 2.0 H.265-PandaMoon",
            audio="AAC 2.0",
            original_title="히어로는 아닙니다만",
            title="The Atypical Family",
            type="WEBDL",
            category="TV",
            year="2024",
            season="S01",
            mediainfo=_text_tracks(
                "ko", "ko", "ar", "cs", "da", "de", "el", "en",
                "es-ES", "es", "fi", "fr", "he", "hr", "hu", "id",
                "it", "ja", "ms", "nb", "nl", "pl", "pt-BR", "pt",
                "ro", "ru", "sv", "th", "tr", "uk", "vi", "zh-Hans", "zh-Hant",
            ),
        )
        assert (
            _run(acm.get_name(meta))
            == "The Atypical Family / 히어로는 아닙니다만 S01 2160p TVING WEB-DL AAC2.0 HEVC-PandaMoon"
        )

    def test_fangs_of_fortune_s01_1080p_iqiyi(self):
        """Fangs of Fortune S01 1080p iQIYI WEB-DL – Chinese series, English subs present."""
        acm = ACM(_config())
        # Real subs include 'en' → no subs tag
        meta = _name_meta(
            "Fangs of Fortune 2024 S01 1080p iQIYI WEB-DL AAC 2.0 H.264-ANDY",
            audio="AAC 2.0",
            original_title="大梦归离",
            title="Fangs of Fortune",
            type="WEBDL",
            category="TV",
            year="2024",
            season="S01",
            mediainfo=_text_tracks("ar", "id", "ms", "en", "ja", "ko", "pt", "zh", "es", "th", "zh", "vi"),
        )
        assert (
            _run(acm.get_name(meta))
            == "Fangs of Fortune / 大梦归离 S01 1080p iQIYI WEB-DL AAC2.0 H.264-ANDY"
        )

    def test_hunter_x_hunter_s01_repack_1080p_cr(self):
        """Hunter x Hunter S01 REPACK 1080p CR WEB-DL – en-US subs must count as English."""
        acm = ACM(_config())
        # Real subs: en-US (×2) + multi → with BCP-47 fix, 'en-US' → Eng → no subs tag
        meta = _name_meta(
            "Hunter x Hunter 2011 S01 REPACK 1080p CR WEB-DL DD+ 2.0 H.264-Kitsune",
            audio="DD+ 2.0",
            original_title="HUNTER×HUNTER",
            title="Hunter x Hunter",
            type="WEBDL",
            category="TV",
            year="2011",
            season="S01",
            mediainfo=_text_tracks(
                "en-US", "en-US", "ar", "es-419", "es-ES", "fr", "it",
                "ja", "ko", "pl", "pt-BR", "pt-PT", "ro", "ru-RU", "tr",
                "uk", "zh-Hans", "zh-Hant",
            ),
        )
        assert (
            _run(acm.get_name(meta))
            == "Hunter x Hunter / HUNTER×HUNTER S01 REPACK 1080p CR WEB-DL DD+2.0 H.264-Kitsune"
        )


# ═══════════════════════════════════════════════════════════════
#  get_additional_checks — dubbed WEB-DL on non-animation
# ═══════════════════════════════════════════════════════════════


def _checks_meta(**overrides: Any) -> dict[str, Any]:
    """Minimal meta for get_additional_checks() tests (Asian, non-encode WEB-DL)."""
    m: dict[str, Any] = {
        "origin_country": ["KR"],
        "production_countries": [],
        "original_language": "ko",
        "type": "WEBDL",
        "audio": "DD+ 5.1",
        "genres": "Action, Drama",
        "unattended": True,
        "tracker_status": {"ACM": {}},
    }
    m.update(overrides)
    return m


class TestAdditionalChecksDubbedWEBDL:
    """Non-original language audio on REMUX/WEB-DL is only permitted for animation."""

    def test_dubbed_webdl_non_animation_is_rejected(self):
        """A dubbed live-action WEB-DL must be blocked."""
        acm = ACM(_config())
        meta = _checks_meta(audio="Dubbed DD+ 5.1", genres="Action, Drama")
        assert _run(acm.get_additional_checks(meta)) is False

    def test_dual_audio_webdl_non_animation_is_rejected(self):
        """A dual-audio (original + foreign) live-action WEB-DL must be blocked."""
        acm = ACM(_config())
        meta = _checks_meta(audio="Dual-Audio DD+ 5.1", genres="Action, Drama")
        assert _run(acm.get_additional_checks(meta)) is False

    def test_dubbed_remux_non_animation_is_rejected(self):
        """A dubbed live-action REMUX must be blocked (rule covers REMUX too)."""
        acm = ACM(_config())
        meta = _checks_meta(audio="Dubbed DTS-HD MA 5.1", genres="Action, Drama", type="REMUX")
        assert _run(acm.get_additional_checks(meta)) is False

    def test_dual_audio_remux_non_animation_is_rejected(self):
        """A dual-audio live-action REMUX must be blocked."""
        acm = ACM(_config())
        meta = _checks_meta(audio="Dual-Audio TrueHD 7.1", genres="Action, Drama", type="REMUX")
        assert _run(acm.get_additional_checks(meta)) is False

    def test_dubbed_animation_webdl_is_allowed(self):
        """A dubbed WEB-DL is OK when the genre includes Animation."""
        acm = ACM(_config())
        meta = _checks_meta(audio="Dubbed DD+ 5.1", genres="Animation, Action")
        assert _run(acm.get_additional_checks(meta)) is True

    def test_dubbed_animation_remux_is_allowed(self):
        """A dubbed animation REMUX must also pass."""
        acm = ACM(_config())
        meta = _checks_meta(audio="Dubbed TrueHD 5.1", genres="Animation", type="REMUX",
                            subtitle_languages=["Japanese", "English"])
        assert _run(acm.get_additional_checks(meta)) is True

    def test_non_dubbed_non_animation_is_allowed(self):
        """An original-audio live-action WEB-DL must pass."""
        acm = ACM(_config())
        meta = _checks_meta(audio="DD+ 5.1", genres="Action, Drama")
        assert _run(acm.get_additional_checks(meta)) is True

    def test_dubbed_disc_type_is_not_blocked(self):
        """The non-original-audio restriction only applies to REMUX/WEB-DL;
        a full DISC upload with dubbed audio must not be caught by this check
        (the disc ISO check may still block it separately)."""
        acm = ACM(_config())
        # is_disc=None so the ISO check also won't fire
        meta = _checks_meta(audio="Dubbed DD+ 5.1", genres="Action, Drama", type="DISC")
        assert _run(acm.get_additional_checks(meta)) is True

    def test_dubbed_animation_single_genre(self):
        """Animation as the only genre with dubbed audio must still pass."""
        acm = ACM(_config())
        meta = _checks_meta(audio="Dubbed AAC 2.0", genres="Animation")
        assert _run(acm.get_additional_checks(meta)) is True


# ═══════════════════════════════════════════════════════════════
#  get_additional_checks — adult content (hentai / porn / JAV)
# ═══════════════════════════════════════════════════════════════


class TestAdditionalChecksAdultContent:
    """Adult, hentai, and JAV content is prohibited at ACM."""

    def test_hentai_genre_is_rejected(self):
        acm = ACM(_config())
        meta = _checks_meta(combined_genres="Animation, Hentai", keywords="")
        assert _run(acm.get_additional_checks(meta)) is False

    def test_porn_keyword_is_rejected(self):
        acm = ACM(_config())
        meta = _checks_meta(combined_genres="", keywords="porn, explicit")
        assert _run(acm.get_additional_checks(meta)) is False

    def test_jav_keyword_is_rejected(self):
        acm = ACM(_config())
        meta = _checks_meta(combined_genres="Drama", keywords="jav")
        assert _run(acm.get_additional_checks(meta)) is False

    def test_normal_animation_is_not_rejected(self):
        """The word 'animation' alone must not trigger the adult-content check."""
        acm = ACM(_config())
        meta = _checks_meta(combined_genres="Animation, Action", keywords="school, magic")
        assert _run(acm.get_additional_checks(meta)) is True


# ═══════════════════════════════════════════════════════════════
#  get_additional_checks — full Blu-ray disc (ISO/BDMV)
# ═══════════════════════════════════════════════════════════════


class TestAdditionalChecksISO:
    """Full BD ISO/BDMV uploads are only allowed for 3D Blu-rays and DVDs."""

    def test_bdmv_non_3d_is_rejected(self):
        """A non-3D Blu-ray DISC upload must be blocked."""
        acm = ACM(_config())
        meta = _checks_meta(type="DISC", is_disc="BDMV")
        assert _run(acm.get_additional_checks(meta)) is False

    def test_bdmv_3d_is_allowed(self):
        """A 3D Blu-ray DISC upload must be allowed."""
        acm = ACM(_config())
        meta = _checks_meta(type="DISC", is_disc="BDMV", **{"3D": True})
        assert _run(acm.get_additional_checks(meta)) is True

    def test_dvd_disc_is_always_allowed(self):
        """A DVD DISC upload is always allowed (DVDs are exempt)."""
        acm = ACM(_config())
        meta = _checks_meta(type="DISC", is_disc="DVD")
        assert _run(acm.get_additional_checks(meta)) is True

    def test_remux_from_bdmv_is_not_blocked(self):
        """A REMUX sourced from a BDMV is fine — only raw DISC type is restricted."""
        acm = ACM(_config())
        meta = _checks_meta(type="REMUX", is_disc="BDMV",
                            subtitle_languages=["Japanese", "English"])
        assert _run(acm.get_additional_checks(meta)) is True


# ═══════════════════════════════════════════════════════════════
#  get_additional_checks — R5 BDs, upscales, URL groups
# ═══════════════════════════════════════════════════════════════


class TestAdditionalChecksMiscProhibited:
    """R5 BDs, upscales, and URL-embedded group names are prohibited."""

    def test_r5_in_name_is_rejected(self):
        acm = ACM(_config())
        meta = _checks_meta(name="Show 2020 R5 1080p BluRay DD+ 5.1 H.264-GRP")
        assert _run(acm.get_additional_checks(meta)) is False

    def test_r5_in_source_is_rejected(self):
        acm = ACM(_config())
        meta = _checks_meta(name="Show 2020 1080p DD+ 5.1 H.264-GRP", source="R5")
        assert _run(acm.get_additional_checks(meta)) is False

    def test_regular_release_not_r5(self):
        """A name containing '5' in other contexts must not trigger R5 check."""
        acm = ACM(_config())
        meta = _checks_meta(name="Show 2020 1080p BluRay DTS-HD MA 5.1 H.264-GRP", source="Blu-ray")
        assert _run(acm.get_additional_checks(meta)) is True

    def test_upscale_in_name_is_rejected(self):
        acm = ACM(_config())
        meta = _checks_meta(name="Show 2020 Upscaled 4K WEB-DL DD+ 5.1 H.264-GRP")
        assert _run(acm.get_additional_checks(meta)) is False

    def test_url_dot_com_in_name_is_rejected(self):
        acm = ACM(_config())
        meta = _checks_meta(name="Show 2020 1080p WEB-DL HDWebMovies.com DD+ 5.1 H.264")
        assert _run(acm.get_additional_checks(meta)) is False

    def test_url_dot_net_in_tag_is_rejected(self):
        acm = ACM(_config())
        meta = _checks_meta(name="Show 2020 1080p WEB-DL DD+ 5.1 H.264-XDMovies.net",
                            tag="-XDMovies.net")
        assert _run(acm.get_additional_checks(meta)) is False

    def test_clean_group_tag_is_not_rejected(self):
        """A normal group tag without a URL must pass."""
        acm = ACM(_config())
        meta = _checks_meta(name="Show 2020 1080p WEB-DL DD+ 5.1 H.264-FLUX", tag="-FLUX")
        assert _run(acm.get_additional_checks(meta)) is True


# ═══════════════════════════════════════════════════════════════
#  get_additional_checks — REMUX English subtitle requirement
# ═══════════════════════════════════════════════════════════════


class TestAdditionalChecksRemuxEnglishSubs:
    """REMUX releases from non-English sources must include English subtitles."""

    def test_remux_non_english_no_subs_is_rejected(self):
        """A Korean REMUX with only Korean subs must be blocked."""
        acm = ACM(_config())
        meta = _checks_meta(
            type="REMUX",
            original_language="ko",
            subtitle_languages=["Korean"],
        )
        assert _run(acm.get_additional_checks(meta)) is False

    def test_remux_non_english_with_english_subs_is_allowed(self):
        """A Korean REMUX with English subtitles must pass."""
        acm = ACM(_config())
        meta = _checks_meta(
            type="REMUX",
            original_language="ko",
            subtitle_languages=["Korean", "English"],
        )
        assert _run(acm.get_additional_checks(meta)) is True

    def test_remux_english_original_no_subs_is_allowed(self):
        """A REMUX from an English-language source does not need English subs."""
        acm = ACM(_config())
        meta = _checks_meta(
            type="REMUX",
            original_language="en",
            subtitle_languages=["French"],
        )
        assert _run(acm.get_additional_checks(meta)) is True

    def test_remux_no_subtitle_data_is_permissive(self):
        """If subtitle_languages is empty/None we cannot determine — allow it."""
        acm = ACM(_config())
        meta = _checks_meta(
            type="REMUX",
            original_language="ja",
            subtitle_languages=[],
        )
        assert _run(acm.get_additional_checks(meta)) is True

    def test_webdl_non_english_no_subs_is_not_blocked_by_this_rule(self):
        """The English-subtitle requirement only applies to REMUX, not WEB-DL."""
        acm = ACM(_config())
        meta = _checks_meta(
            type="WEBDL",
            original_language="ko",
            subtitle_languages=["Korean"],
        )
        assert _run(acm.get_additional_checks(meta)) is True


# ═══════════════════════════════════════════════════════════════
#  get_additional_checks — FLAC multichannel on REMUX
# ═══════════════════════════════════════════════════════════════


class TestAdditionalChecksFlacMultichannel:
    """Multichannel FLAC on REMUX is prohibited; only mono/stereo FLAC is allowed."""

    def test_remux_flac_51_is_rejected(self):
        """A REMUX with FLAC 5.1 audio must be blocked."""
        acm = ACM(_config())
        meta = _checks_meta(type="REMUX", audio="FLAC 5.1", channels="5.1",
                            subtitle_languages=["Korean", "English"])
        assert _run(acm.get_additional_checks(meta)) is False

    def test_remux_flac_71_is_rejected(self):
        """A REMUX with FLAC 7.1 audio must be blocked."""
        acm = ACM(_config())
        meta = _checks_meta(type="REMUX", audio="FLAC 7.1", channels="7.1",
                            subtitle_languages=["Korean", "English"])
        assert _run(acm.get_additional_checks(meta)) is False

    def test_remux_flac_20_is_allowed(self):
        """A REMUX with FLAC 2.0 (stereo) must be allowed."""
        acm = ACM(_config())
        meta = _checks_meta(type="REMUX", audio="FLAC 2.0", channels="2.0",
                            subtitle_languages=["Korean", "English"])
        assert _run(acm.get_additional_checks(meta)) is True

    def test_remux_flac_10_is_allowed(self):
        """A REMUX with FLAC 1.0 (mono) must be allowed."""
        acm = ACM(_config())
        meta = _checks_meta(type="REMUX", audio="FLAC 1.0", channels="1.0",
                            subtitle_languages=["Korean", "English"])
        assert _run(acm.get_additional_checks(meta)) is True

    def test_remux_dtshd_51_is_allowed(self):
        """A REMUX with DTS-HD MA 5.1 is perfectly fine."""
        acm = ACM(_config())
        meta = _checks_meta(type="REMUX", audio="DTS-HD MA 5.1", channels="5.1",
                            subtitle_languages=["Korean", "English"])
        assert _run(acm.get_additional_checks(meta)) is True

    def test_remux_flac_no_channels_is_permissive(self):
        """If channels metadata is missing we cannot judge — allow it."""
        acm = ACM(_config())
        meta = _checks_meta(type="REMUX", audio="FLAC", channels="",
                            subtitle_languages=["Korean", "English"])
        assert _run(acm.get_additional_checks(meta)) is True
