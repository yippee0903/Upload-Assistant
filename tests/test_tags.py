# Tests for src/tags.py — release-group extraction
"""
Regression tests for get_tag().

Key regression: filenames whose only hyphen is part of a source token
(WEB-DL, Blu-ray) must NOT produce a false group tag.

Before the fix the regex `(?<=-)` would match right after the hyphen in
"WEB-DL" and capture "DL.AAC.2.0.H.264" as the release group, causing
tracker naming to produce duplicated audio/codec tokens, e.g.:
    Cyclo.1995.1080p.WEB-DL.AAC.2.0.H.264.mkv
    → meta["tag"] = "-DL.AAC.2.0.H.264"      (wrong)
    → tracker name: …H264-DL.AAC.2.0.H.264   (malformed)

After the fix, both `(?<!WEB-)` and `(?<!Blu-)` lookbehinds prevent the
regex from firing right after the hyphens in those source tokens.
"""

import asyncio
from typing import Any

from src.tags import get_tag


# ─── Helpers ──────────────────────────────────────────────────


def _meta(**overrides: Any) -> dict[str, Any]:
    """Minimal meta dict required by get_tag."""
    m: dict[str, Any] = {
        "debug": False,
        "is_disc": None,
        "anime": False,
        "tv_pack": False,
        "keep_folder": False,
        "scene": False,
        "uuid": "test-uuid",
    }
    m.update(overrides)
    return m


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# ═══════════════════════════════════════════════════════════════
#  WEB-DL — hyphen must not be treated as group separator
# ═══════════════════════════════════════════════════════════════


class TestGetTagWebDL:
    """The hyphen in WEB-DL is a source token, not a group separator."""

    def test_webdl_h264_no_group_returns_empty(self):
        """Regression: Cyclo.1995.1080p.WEB-DL.AAC.2.0.H.264.mkv — no group."""
        tag = _run(get_tag("Cyclo.1995.1080p.WEB-DL.AAC.2.0.H.264.mkv", _meta()))
        assert tag == "", f"Expected empty tag, got {tag!r}"

    def test_webdl_h265_no_group_returns_empty(self):
        tag = _run(get_tag("Movie.2023.1080p.WEB-DL.DDP5.1.H.265.mkv", _meta()))
        assert tag == "", f"Expected empty tag, got {tag!r}"

    def test_webdl_4k_hdr_no_group_returns_empty(self):
        tag = _run(get_tag("Film.2022.2160p.WEB-DL.DV.HDR.DDP.5.1.H.265.mkv", _meta()))
        assert tag == "", f"Expected empty tag, got {tag!r}"

    def test_webdl_avc_no_group_returns_empty(self):
        tag = _run(get_tag("Series.S01E01.1080p.WEB-DL.AAC.2.0.AVC.mkv", _meta()))
        assert tag == "", f"Expected empty tag, got {tag!r}"

    def test_webdl_with_real_group_extracted(self):
        """Group after the codec, following a second hyphen, must be captured."""
        tag = _run(get_tag("Cyclo.1995.1080p.WEB-DL.AAC.2.0.H.264-GroupName.mkv", _meta()))
        assert tag == "-GroupName", f"Expected -GroupName, got {tag!r}"

    def test_webdl_h265_with_real_group_extracted(self):
        tag = _run(get_tag("Movie.2023.1080p.WEB-DL.DDP5.1.H.265-GROUPX.mkv", _meta()))
        assert tag == "-GROUPX", f"Expected -GROUPX, got {tag!r}"

    def test_webdl_false_tag_before_fix(self):
        """Document what the old regex would have matched (the DL.AAC… false tag).

        The key invariant after the fix: any tag extracted from a WEB-DL
        filename must NOT contain "DL" as a prefix.
        """
        tag = _run(get_tag("Cyclo.1995.1080p.WEB-DL.AAC.2.0.H.264.mkv", _meta()))
        assert not tag.startswith("-DL"), (
            f"False WEB-DL tag detected: {tag!r}. "
            "The hyphen in WEB-DL must not be used as a group separator."
        )


# ═══════════════════════════════════════════════════════════════
#  Blu-ray — same family of bug
# ═══════════════════════════════════════════════════════════════


class TestGetTagBluray:
    """The hyphen in Blu-ray is a source token, not a group separator."""

    def test_bluray_no_group_returns_empty(self):
        tag = _run(get_tag("Film.2020.1080p.Blu-ray.DTS.x264.mkv", _meta()))
        assert tag == "", f"Expected empty tag, got {tag!r}"

    def test_bluray_with_real_group_extracted(self):
        tag = _run(get_tag("Film.2020.1080p.Blu-ray.DTS.x264-CREW.mkv", _meta()))
        assert tag == "-CREW", f"Expected -CREW, got {tag!r}"

    def test_bluray_false_tag_before_fix(self):
        """After the fix, 'ray' must not be extracted as the group from Blu-ray."""
        tag = _run(get_tag("Film.2020.1080p.Blu-ray.DTS.x264.mkv", _meta()))
        assert not tag.startswith("-ray"), (
            f"False Blu-ray tag detected: {tag!r}. "
            "The hyphen in Blu-ray must not be used as a group separator."
        )


# ═══════════════════════════════════════════════════════════════
#  Mixed-case WEB-DL — lookbehinds must be case-insensitive
# ═══════════════════════════════════════════════════════════════


class TestGetTagWebDLMixedCase:
    """Case variants of WEB-DL must be guarded the same way as the canonical form."""

    def test_web_dl_mixed_case_no_group_returns_empty(self):
        """Web-DL (mixed case) must not produce a false group tag."""
        tag = _run(get_tag("Cyclo.1995.1080p.Web-DL.AAC.2.0.H.264.mkv", _meta()))
        assert tag == "", f"Expected empty tag, got {tag!r}"
        assert not tag.startswith("-DL"), f"False Web-DL tag detected: {tag!r}"

    def test_web_dl_mixed_case_with_real_group(self):
        """Web-DL with a real group must still extract the group."""
        tag = _run(get_tag("Cyclo.1995.1080p.Web-DL.AAC.2.0.H.264-GroupName.mkv", _meta()))
        assert tag == "-GroupName", f"Expected -GroupName, got {tag!r}"


# ═══════════════════════════════════════════════════════════════
#  Mixed-case Blu-ray — lookbehinds must be case-insensitive
# ═══════════════════════════════════════════════════════════════


class TestGetTagBlurayMixedCase:
    """Case variants of Blu-ray must be guarded the same way as canonical."""

    def test_blu_ray_uppercase_no_group_returns_empty(self):
        """BLU-ray (uppercase BLU) must not produce a false group tag."""
        tag = _run(get_tag("Film.2020.1080p.BLU-ray.DTS.x264.mkv", _meta()))
        assert tag == "", f"Expected empty tag, got {tag!r}"
        assert not tag.startswith("-ray"), f"False BLU-ray tag detected: {tag!r}"

    def test_blu_ray_mixed_case_with_real_group(self):
        """Blu-Ray (capital R) with a real group must still extract the group."""
        tag = _run(get_tag("Film.2020.1080p.Blu-Ray.DTS.x264-CREW.mkv", _meta()))
        assert tag == "-CREW", f"Expected -CREW, got {tag!r}"


# ═══════════════════════════════════════════════════════════════
#  Standard releases — real group tags must still be extracted
# ═══════════════════════════════════════════════════════════════


class TestGetTagRealGroups:
    """Releases with genuine group tags must still work correctly."""

    def test_bluray_encode_group(self):
        tag = _run(get_tag("Show.S01E01.1080p.BluRay.x264-GRP.mkv", _meta()))
        assert tag == "-GRP", f"Expected -GRP, got {tag!r}"

    def test_webrip_group(self):
        tag = _run(get_tag("Movie.2024.720p.WEBRip.AAC.x264-NTG.mkv", _meta()))
        assert tag == "-NTG", f"Expected -NTG, got {tag!r}"

    def test_remux_group(self):
        tag = _run(get_tag("Movie.2020.1080p.BluRay.REMUX.DTS-HD.MA.5.1.H264-TEAM.mkv", _meta()))
        assert tag == "-TEAM", f"Expected -TEAM, got {tag!r}"

    def test_no_hyphen_no_group(self):
        tag = _run(get_tag("Standalone.2023.1080p.BluRay.x264.mkv", _meta()))
        assert tag == "", f"Expected empty tag, got {tag!r}"

    def test_web_no_hyphen_group(self):
        tag = _run(get_tag("Movie.2023.1080p.WEB.AAC.x264-FRGRP.mkv", _meta()))
        assert tag == "-FRGRP", f"Expected -FRGRP, got {tag!r}"


# ═══════════════════════════════════════════════════════════════
#  Generic "no group" tags — separator variants
#  Regression: "…DTS-HD MA 5.1.mkv" (space separators) produced the
#  false tag "-HD MA 5.1"; only the dotted "hd.ma.5.1" was filtered.
# ═══════════════════════════════════════════════════════════════


class TestGetTagGenericNoGroup:
    """False tags extracted from audio codecs must be dropped in all separator styles."""

    def test_dts_hd_ma_dotted_returns_empty(self):
        tag = _run(get_tag("Movie.1991.2160p.UHD.BluRay.REMUX.HDR10+.HEVC.DTS-HD.MA.5.1.mkv", _meta()))
        assert tag == "", f"Expected empty tag, got {tag!r}"

    def test_dts_hd_ma_spaced_returns_empty(self):
        """Regression: Terminator 2 … DTS-HD MA 5.1.mkv → tag was '-HD MA 5.1'."""
        tag = _run(get_tag("Terminator 2 Judgment Day 1991 Hybrid 2160p UHD BluRay REMUX HDR10+ HEVC DTS-HD MA 5.1.mkv", _meta()))
        assert tag == "", f"Expected empty tag, got {tag!r}"

    def test_dts_hd_hra_spaced_returns_empty(self):
        """The whole DTS-HD family is generic: HRA profile, any channel layout."""
        tag = _run(get_tag("Movie.2020.1080p.BluRay.DTS-HD HRA 7.1.mkv", _meta()))
        assert tag == "", f"Expected empty tag, got {tag!r}"

    def test_dts_hd_ma_stereo_returns_empty(self):
        tag = _run(get_tag("Movie.2020.1080p.BluRay.DTS-HD.MA.2.0.mkv", _meta()))
        assert tag == "", f"Expected empty tag, got {tag!r}"

    def test_real_group_after_dts_hd_ma_still_extracted(self):
        tag = _run(get_tag("Movie.1991.2160p.UHD.BluRay.REMUX.DTS-HD.MA.5.1-CiNEPHiLES.mkv", _meta()))
        assert tag == "-CiNEPHiLES", f"Expected -CiNEPHiLES, got {tag!r}"

    def test_real_group_directly_after_dts_still_extracted(self):
        """…DTS-WiKi is a legitimate pattern: the hyphen after DTS can be a real separator."""
        tag = _run(get_tag("Movie.2010.1080p.BluRay.x264.DTS-WiKi.mkv", _meta()))
        assert tag == "-WiKi", f"Expected -WiKi, got {tag!r}"


# ═══════════════════════════════════════════════════════════════
#  TV-pack tag: folder has no group tag but files do
#  Regression for the NOTAG bug where tv_pack path fell back to
#  meta["uuid"] instead of trying the episode filename.
# ═══════════════════════════════════════════════════════════════


class TestGetTagTVPackFallback:
    """TV packs: fall back to the episode filename when folder has no tag."""

    def test_folder_no_tag_file_has_group(self):
        """Bug: folder name has no tag → should extract group from episode file."""
        tag = _run(
            get_tag(
                "/downloads/Bon Appetit Your Majesty/S01E01.1080p.WEB-DL.AAC.2.0.H.264-FW.mkv",
                _meta(tv_pack=1),
            )
        )
        assert tag == "-FW", f"Expected -FW, got {tag!r}"

    def test_folder_has_tag_is_preferred(self):
        """When the folder itself carries the tag, that takes precedence."""
        tag = _run(
            get_tag(
                "/downloads/Chicago.Fire.S12.MULTi.1080p.WEB.H264-FW/E01.mkv",
                _meta(tv_pack=1),
            )
        )
        assert tag == "-FW", f"Expected -FW, got {tag!r}"

    def test_no_tag_on_folder_or_file_returns_empty(self):
        """No tag on either folder or file → empty tag."""
        tag = _run(
            get_tag(
                "/downloads/Show S01/Episode01.1080p.WEB.mkv",
                _meta(tv_pack=1),
            )
        )
        assert tag == "", f"Expected empty tag, got {tag!r}"

    def test_keep_folder_fallback(self):
        """Same fallback applies when keep_folder is set instead of tv_pack."""
        tag = _run(
            get_tag(
                "/downloads/Movie Collection/Movie.2024.1080p.BluRay.x264-CREW.mkv",
                _meta(keep_folder=True),
            )
        )
        assert tag == "-CREW", f"Expected -CREW, got {tag!r}"
