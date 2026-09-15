# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Tests for BLU tracker rule checks, naming and description."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.trackers.BLU import BLU


def _run(coro):
    return asyncio.run(coro)


def _config() -> dict[str, Any]:
    return {"TRACKERS": {"BLU": {"api_key": "fake", "announce_url": ""}}, "DEFAULT": {"tmdb_api": "fake"}}


def _audio(fmt: str, channels: int, lang: str = "en", commercial: str = "", lossless: bool = False, title: str = "") -> dict[str, Any]:
    track: dict[str, Any] = {"@type": "Audio", "Format": fmt, "Channels": str(channels), "Language": lang, "Format_Commercial_IfAny": commercial, "Title": title}
    if lossless:
        track["Compression_Mode"] = "Lossless"
    return track


def _mi(*tracks: dict[str, Any]) -> dict[str, Any]:
    return {"media": {"track": [{"@type": "General"}, *tracks]}}


def _meta(**overrides: Any) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "name": "Example Release 2026 1080p BluRay x264-GRP",
        "title": "Example Release",
        "year": "2026",
        "category": "MOVIE",
        "resolution": "1080p",
        "type": "ENCODE",
        "is_disc": None,
        "container": "mkv",
        "video_codec": "AVC",
        "video_encode": "x264",
        "hdr": "",
        "keywords": "",
        "tag": "-GRP",
        "unattended": True,
        "valid_mi_settings": True,
        "image_list": [{}, {}, {}],
        "mediainfo": _mi(_audio("E-AC-3", 6)),
        "tracker_status": {"BLU": {}},
        "imdb_info": {},
    }
    meta.update(overrides)
    return meta


class TestBLUAdditionalChecks:
    @pytest.fixture
    def blu(self):
        tracker = BLU(config=_config())
        tracker.common.check_language_requirements = AsyncMock(return_value=True)
        return tracker

    def _passes(self, blu, **overrides: Any) -> bool:
        return _run(blu.get_additional_checks(_meta(**overrides)))

    def test_baseline_passes(self, blu):
        assert self._passes(blu) is True

    def test_container_rules(self, blu):
        assert self._passes(blu, container="mp4") is False
        assert self._passes(blu, container="ts", type="HDTV") is True
        assert self._passes(blu, container="mp4", type="WEBDL", hdr="DV") is True
        assert self._passes(blu, container="mp4", type="WEBDL", hdr="DV HDR") is False

    def test_encode_resolution_and_codec(self, blu):
        assert self._passes(blu, resolution="576p") is False
        assert self._passes(blu, resolution="576p", type="WEBDL") is True
        assert self._passes(blu, video_codec="AV1") is False
        assert self._passes(blu, video_codec="AV1", type="WEBDL") is True

    def test_sdr_hevc_live_action_is_asked(self, blu):
        assert self._passes(blu, video_codec="HEVC") is False
        assert self._passes(blu, video_codec="HEVC", hdr="HDR") is True
        assert self._passes(blu, video_codec="HEVC", keywords="animation") is True

    def test_hi10p_only_for_anime(self, blu):
        assert self._passes(blu, video_encode="Hi10P x264") is False
        assert self._passes(blu, video_encode="Hi10P x264", anime=True) is True

    def test_language_requirement_is_delegated(self, blu):
        blu.common.check_language_requirements = AsyncMock(return_value=False)
        assert self._passes(blu) is False
        assert self._passes(blu, is_disc="BDMV", container="") is True

    def test_pcm_and_compat_flags(self, blu):
        assert self._passes(blu, non_disc_has_pcm_audio_tracks=True) is False
        assert self._passes(blu, has_disallowed_compat_track=True) is False

    def test_opus_and_multichannel_flac_aac(self, blu):
        assert self._passes(blu, mediainfo=_mi(_audio("Opus", 2))) is False
        assert self._passes(blu, mediainfo=_mi(_audio("FLAC", 6))) is False
        assert self._passes(blu, mediainfo=_mi(_audio("FLAC", 6)), anime=True) is True
        assert self._passes(blu, mediainfo=_mi(_audio("FLAC", 2))) is True
        assert self._passes(blu, mediainfo=_mi(_audio("AAC", 6))) is False
        assert self._passes(blu, mediainfo=_mi(_audio("AAC", 6)), type="WEBDL") is True

    def test_truehd_needs_ac3_in_same_language(self, blu):
        truehd = _audio("MLP FBA", 8, commercial="Dolby TrueHD with Dolby Atmos")
        assert self._passes(blu, type="REMUX", mediainfo=_mi(truehd)) is False
        assert self._passes(blu, type="REMUX", mediainfo=_mi(truehd, _audio("AC-3", 6, lang="fr"))) is False
        assert self._passes(blu, type="REMUX", mediainfo=_mi(truehd, _audio("AC-3", 6))) is True

    def test_truehd_compat_track_is_not_a_commentary_nor_a_stereo_downmix(self, blu):
        truehd = _audio("MLP FBA", 8, commercial="Dolby TrueHD with Dolby Atmos")
        commentary = _audio("AC-3", 2, title="Commentary by the director")
        assert self._passes(blu, type="ENCODE", mediainfo=_mi(truehd, _audio("E-AC-3", 6), commentary)) is False
        assert self._passes(blu, type="ENCODE", mediainfo=_mi(truehd, _audio("AC-3", 2))) is False
        assert self._passes(blu, type="ENCODE", mediainfo=_mi(truehd, _audio("AC-3", 6), commentary)) is True
        assert self._passes(blu, type="ENCODE", mediainfo=_mi(_audio("MLP FBA", 2), _audio("AC-3", 2))) is True

    def test_2160p_encode_needs_lossless_main_audio(self, blu):
        assert self._passes(blu, resolution="2160p") is False
        assert self._passes(blu, resolution="2160p", mediainfo=_mi(_audio("FLAC", 2))) is True
        assert self._passes(blu, resolution="2160p", type="WEBRIP") is True

    def test_screenshots_required(self, blu):
        assert self._passes(blu, image_list=[{}, {}]) is False
        assert self._passes(blu, image_list=[], screens=4) is True

    def test_derived_dv_unattended_is_skipped_and_disc_dv_passes(self, blu):
        # Unattended is conservative: the DV layer must be proven to come from
        # the disc (a BLU full disc with DV for this title), else skip.
        blu.disc_has_dv = AsyncMock(return_value=True)
        meta = _meta(type="REMUX", hdr="DV HDR")
        assert _run(blu.get_additional_checks(meta)) is True
        assert meta["tracker_status"]["BLU"].get("other") is not True
        assert self._passes(blu, type="REMUX", hdr="DV HDR", webdv="Hybrid") is False
        blu.disc_has_dv = AsyncMock(return_value=False)
        assert self._passes(blu, type="REMUX", hdr="DV HDR") is False
        assert self._passes(blu, type="ENCODE", hdr="DV HDR") is False

    def test_derived_dv_is_known_from_the_source_description(self, blu):
        blu.disc_has_dv = AsyncMock(return_value=True)
        assert self._passes(blu, type="ENCODE", hdr="DV HDR", description="SOURCE: Example.2026.UHD.BluRay.DV.HYBRID.REMUX-GRP") is False
        blu.disc_has_dv.assert_not_called()

    def test_disc_dv_is_read_from_full_disc_names_only(self, blu):
        assert blu._discs_prove_dv([("Example 2026 2160p UHD Blu-ray DV HDR HEVC TrueHD 7.1-GRP", "Full Disc")]) is True
        assert blu._discs_prove_dv([("Example 2026 2160p UHD Blu-ray HDR HEVC TrueHD 7.1-GRP", "Full Disc"), ("Example 2026 1080p Blu-ray AVC DTS-HD MA 5.1-GRP", "Full Disc")]) is False
        # The site ignores the type filter: a DV WEB-DL or a hybrid remux proves nothing.
        assert blu._discs_prove_dv([("Example 2026 2160p DSNP WEB-DL DD+ 5.1 DV HDR H.265-GRP", "WEB-DL"), ("Example 2026 2160p UHD BluRay REMUX DVP8 HDR HEVC-GRP", "Remux")]) is False
        assert blu._discs_prove_dv([]) is False

    def test_derived_dv_interactive_sets_fanres(self, blu):
        meta = _meta(type="ENCODE", hdr="DV HDR", webdv="Hybrid", unattended=False)
        with patch("src.trackers.COMMON.cli_ui.ask_yes_no", return_value=True):
            assert _run(blu.get_additional_checks(meta)) is True
        assert meta["tracker_status"]["BLU"]["other"] is True
        assert _run(blu.get_category_id(meta)) == {"category_id": "3"}


class TestBLUNameAndDescription:
    @pytest.fixture
    def blu(self):
        return BLU(config=_config())

    def test_hybrid_is_dropped_only_for_webdl(self, blu):
        name = "Example Release 2026 Hybrid 2160p AMZN WEB-DL DV HDR H.265-GRP"
        assert _run(blu.get_name(_meta(name=name, type="WEBDL")))["name"] == name.replace("Hybrid ", "")
        assert _run(blu.get_name(_meta(name=name, type="REMUX", webdv="Hybrid")))["name"] == name

    def test_no_dvp_suffix_for_derived_dv(self, blu):
        meta = _meta(tracker_status={"BLU": {"other": True}})
        assert "DVP" not in _run(blu.get_name(meta))["name"]

    def test_derived_dv_alert_prefixes_description(self, blu):
        with patch("src.trackers.UNIT3D.DescriptionBuilder") as builder:
            builder.return_value.unit3d_edit_desc = AsyncMock(return_value="[center]body[/center]")
            plain = _run(blu.get_description(_meta()))["description"]
            derived = _run(blu.get_description(_meta(tracker_status={"BLU": {"other": True}})))["description"]
        assert plain == "[center]body[/center]"
        assert derived.startswith("[alert]This release contains a Derived Dolby Vision layer.")
        assert derived.endswith("[center]body[/center]")

    def test_banned_groups_match_site_list(self, blu):
        for group in ("ATM05", "BitHD", "D3US", "mAck", "PAAI", "PHOCiS", "PMi", "PrimeFix", "XDMovies"):
            assert group in blu.banned_groups


class TestBLUExtrasInPack:
    """BLU wants extras uploaded on their own: a pack mixing extras with the main content is refused."""

    EPISODES = [f"/data/Example.Show.S01E{e:02d}.1080p.WEB-DL.AAC.H.264-GRP.mkv" for e in (1, 2)]
    EXTRA = "/data/Example.Show.S01E02.Extra.1080p.WEB-DL.AAC.H.264-GRP.mkv"

    @pytest.fixture
    def blu(self):
        tracker = BLU(config=_config())
        tracker.common.check_language_requirements = AsyncMock(return_value=True)
        return tracker

    def test_mixed_pack_is_skipped_unattended(self, blu):
        assert _run(blu.get_additional_checks(_meta(filelist=[*self.EPISODES, self.EXTRA]))) is False

    def test_mixed_pack_can_be_forced_interactively(self, blu):
        with patch("src.trackers.COMMON.cli_ui.ask_yes_no", return_value=True):
            assert _run(blu.get_additional_checks(_meta(filelist=[*self.EPISODES, self.EXTRA], unattended=False))) is True

    def test_extras_only_upload_passes_without_asking(self, blu):
        with patch("src.trackers.COMMON.cli_ui.ask_yes_no", side_effect=AssertionError("must not prompt")):
            extras = [self.EXTRA, "/data/Example.Show.S01.Bonus.Making.of.1080p.WEB-DL-GRP.mkv"]
            assert _run(blu.get_additional_checks(_meta(filelist=extras, unattended=False))) is True

    def test_word_boundary_does_not_match_extraction(self, blu):
        assert _run(blu.get_additional_checks(_meta(filelist=[*self.EPISODES, "/data/Example.Show.S01E03.Extraction.Day.1080p.WEB-DL-GRP.mkv"]))) is True
