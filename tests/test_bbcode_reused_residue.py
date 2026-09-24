# A description reused from another tracker carries two residues the cleaner
# missed: the uploading tool's own signature line, and the centred "Trailer on
# YouTube" link. Both are regenerated or unwanted here, so both must go, while
# ordinary prose that merely mentions a trailer or a tool has to survive.

import pytest

from src.bbcode import BBCODE

SITE = "https://example-tracker.org"
PROSE = "Encode notes that must stay."


def _clean(desc: str) -> str:
    cleaned, _ = BBCODE().clean_unit3d_description(desc, SITE)
    return cleaned


class TestAutoUploaderSignature:
    def test_wrapped_signature_line_is_removed(self) -> None:
        sig = "[right][size=4]Uploaded with ExampleTracker AutoUploader v0.15.4[/size][/right]"

        assert _clean(f"{PROSE}\n{sig}") == PROSE

    def test_signature_without_version_is_removed(self) -> None:
        sig = "[right][size=4]Uploaded with ExampleTracker AutoUploader[/size][/right]"

        assert _clean(f"{PROSE}\n{sig}") == PROSE

    def test_bare_signature_line_is_removed(self) -> None:
        assert _clean(f"{PROSE}\nUploaded with ExampleTracker AutoUploader v1.2.3") == PROSE

    @pytest.mark.parametrize(
        "site",
        ["Example.Tracker", "Example-Tracker", "Example.Sub-Tracker"],
    )
    @pytest.mark.parametrize("spacing", ["AutoUploader", "Auto Uploader"])
    @pytest.mark.parametrize("version", ["", " v2.0.1", " 2.0.1"])
    def test_site_name_and_spacing_variants_are_removed(self, site: str, spacing: str, version: str) -> None:
        sig = f"[right][size=4]Uploaded with {site} {spacing}{version}[/size][/right]"

        assert _clean(f"{PROSE}\n{sig}") == PROSE

    def test_prose_mentioning_the_tool_survives(self) -> None:
        note = "Remuxed by hand, not uploaded with ExampleTracker AutoUploader v0.15.4 as usual."

        assert note in _clean(note)


class TestNfoForgeSignature:
    @pytest.mark.parametrize("version", ["", " v1.1.17", " 2.0"])
    def test_sized_linked_signature_line_is_removed(self, version: str) -> None:
        sig = f"[size=15]Shared with [url=https://github.com/example/NfoForge]NfoForge{version}[/url][/size]"

        assert _clean(f"{PROSE}\n{sig}") == PROSE

    def test_bare_signature_line_is_removed(self) -> None:
        assert _clean(f"{PROSE}\nShared with NfoForge v1.1.17") == PROSE

    def test_prose_mentioning_the_tool_survives(self) -> None:
        note = "The NFO was shared with NfoForge v1.1.17 before being trimmed by hand."

        assert note in _clean(note)


class TestTrailerLink:
    def test_centred_trailer_link_is_removed(self) -> None:
        trailer = "[center][b][url=https://www.youtube.com/watch?v=aaaaaaaaaaa][Trailer on YouTube][/url][/b][/center]"

        assert _clean(f"{PROSE}\n{trailer}") == PROSE

    def test_bold_only_trailer_link_is_still_removed(self) -> None:
        trailer = "[b][url=https://youtu.be/aaaaaaaaaaa]Trailer[/url][/b]"

        assert _clean(f"{PROSE}\n{trailer}") == PROSE

    def test_bare_trailer_link_is_removed(self) -> None:
        trailer = "[url=https://www.youtube.com/watch?v=aaaaaaaaaaa][Trailer on YouTube][/url]"

        assert _clean(f"{PROSE}\n{trailer}") == PROSE

    @pytest.mark.parametrize(
        ("opening", "closing"),
        [
            ("[i]", "[/i]"),
            ("[size=4]", "[/size]"),
            ("[color=#ff0000]", "[/color]"),
            ("[center][i][size=3]", "[/size][/i][/center]"),
        ],
    )
    def test_decorated_trailer_links_are_removed(self, opening: str, closing: str) -> None:
        link = "[url=https://www.youtube.com/watch?v=aaaaaaaaaaa][Trailer on YouTube][/url]"

        assert _clean(f"{PROSE}\n{opening}{link}{closing}") == PROSE

    def test_an_unclosed_trailer_link_does_not_swallow_the_next_lines(self) -> None:
        note = "A note line carrying no bracket at all."
        desc = f"[url=https://www.youtube.com/watch?v=aaaaaaaaaaa]Trailer\n{note}\n[/url]\n{PROSE}"

        cleaned = _clean(desc)

        assert note in cleaned
        assert PROSE in cleaned

    def test_prose_mentioning_a_trailer_survives(self) -> None:
        note = "The trailer on YouTube shows a different colour grade than this encode."

        assert note in _clean(note)
