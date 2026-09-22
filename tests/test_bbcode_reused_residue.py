# A description reused from another tracker carries two residues the cleaner
# missed: the uploading tool's own signature line, and the centred "Trailer on
# YouTube" link. Both are regenerated or unwanted here, so both must go, while
# ordinary prose that merely mentions a trailer or a tool has to survive.

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

    def test_prose_mentioning_the_tool_survives(self) -> None:
        note = "Remuxed by hand, not uploaded with ExampleTracker AutoUploader v0.15.4 as usual."

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

    def test_prose_mentioning_a_trailer_survives(self) -> None:
        note = "The trailer on YouTube shows a different colour grade than this encode."

        assert note in _clean(note)
