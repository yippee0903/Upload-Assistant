# Descriptions reused from seedpool carry an ASCII-art signature block and a
# closing "Posted to this fine tracker with seedbrr." sentence; both must be
# stripped by the generic UNIT3D description cleaner.

from src.bbcode import BBCODE

SEEDPOOL_ART = """[code][center]..                                   ..
                                 .4HH                                 .4HH
                                   HH                                   HH
  ,pP"Yb.  .gP"Ya   .gP"Ya    ,H""bHH  .4HHpdHAo.  ,pW"Wq.   ,pW"Wq.    HH
  8I   `" ,H'   Yb ,H'   Yb ,AP    HH    HH   `Wb 6W'   `Wb 6W'   `Wb   HH
  `YHHHa. 8H\"\"\"\"\"\" 8H\"\"\"\"\"\" 8HI    HH    HH    H8 8H     H8 8H     H8   HH
  L.   I8 YH.    , YH.    , `Hb    HH    HH   ,AP YA.   ,A9 YA.   ,A9   HH
  `9hhhP'  `Hbmhd'  `Hbmhd'  `Wbhd"HHL.  HHbhhd'   `Ybhd9'   `Ybhd9'  .JHHL.
                                         HH
                                       .JHHL.[/center][/code]"""


def test_seedpool_art_block_is_removed() -> None:
    desc = f"{SEEDPOOL_ART}\nA plot summary that must stay."
    cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://seedpool.org")
    assert cleaned == "A plot summary that must stay."


def test_seedpool_art_mid_description_leaves_clean_spacing() -> None:
    desc = f"Summary line.\n\n{SEEDPOOL_ART}\n\nMore."
    cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://seedpool.org")
    assert cleaned == "Summary line.\n\nMore."


def test_seedbrr_sentence_is_removed() -> None:
    desc = "A plot summary that must stay. Posted to this fine tracker with seedbrr."
    cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://seedpool.org")
    assert "seedbrr" not in cleaned
    assert "A plot summary that must stay." in cleaned


def test_other_code_blocks_survive() -> None:
    desc = "[code][center]NFO contents worth keeping[/center][/code]\nSummary."
    cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://seedpool.org")
    assert "NFO contents worth keeping" in cleaned


def test_nfo_block_containing_art_strokes_is_preserved() -> None:
    # A genuine ASCII-art NFO can contain the same ".4HH" strokes as the
    # seedpool logo; one token alone must not wipe the block.
    nfo = "[code][center].4HH  release notes\nripped from a pristine source[/center][/code]"
    desc = f"{nfo}\nSummary line."
    cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://seedpool.org")
    assert cleaned == desc


def test_seedpool_sample_spoiler_is_removed() -> None:
    desc = (
        "A plot summary that must stay.\n\n"
        "[b][spoiler=Sample: xFAKESAMPLEIDx]https://img.example.invalid/xFAKESAMPLEIDx[/spoiler][/b]"
    )
    cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://seedpool.org")
    assert cleaned == "A plot summary that must stay."


def test_seedpool_sample_spoiler_mid_description_leaves_clean_spacing() -> None:
    block = "[b][spoiler=Sample: xFAKESAMPLEIDx]https://img.example.invalid/xFAKESAMPLEIDx[/spoiler][/b]"
    cleaned, _ = BBCODE().clean_unit3d_description(f"Summary.\n\n{block}\n\nMore.", "https://seedpool.org")
    assert cleaned == "Summary.\n\nMore."


def test_regular_spoiler_survives() -> None:
    desc = "Summary.\n\n[spoiler=Screens]some content[/spoiler]"
    cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://seedpool.org")
    assert "[spoiler=Screens]some content[/spoiler]" in cleaned


def test_seedpool_sentence_with_other_tool_name_is_removed():
    # The tool name after "with" varies per uploader (seedbrr, seed-tools, …)
    desc = "[b][size=12][color=#757575]Created with mkbrr, ffmpeg, and mediainfo. Posted to this fine tracker with seed-tools.[/color][/size][/b]"
    cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://seedpool.org")
    assert "Posted to this fine tracker" not in cleaned
    assert "Created with mkbrr, ffmpeg, and mediainfo." in cleaned


def test_seedpool_sentence_does_not_eat_following_text():
    desc = "Posted to this fine tracker with seed-tools. A plot summary that must stay."
    cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://seedpool.org")
    assert "A plot summary that must stay." in cleaned
    assert "Posted to this fine tracker" not in cleaned


def test_sponsored_sentence_is_removed() -> None:
    desc = "Summary kept.\nThis description is rendered for you via config.yaml and is sponsored by Shrek."
    cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://seedpool.org")
    assert "sponsored by" not in cleaned
    assert "rendered for you via config.yaml" not in cleaned
    assert "Summary kept." in cleaned


def test_dead_ptpimg_comparison_block_is_removed() -> None:
    desc = (
        "Summary kept.\n\n"
        "[b]Source Comparison[/b]\n"
        "[comparison=FRA BD, USA BD]\n"
        "https://ptpimg.me/xxfake1.png\n"
        "https://ptpimg.me/xxfake2.png\n"
        "[/comparison]\n\n"
        "[b]Screenshot Comparison[/b]\n"
        "[comparison=FRA BD, Encode]\n"
        "https://ptpimg.me/xxfake3.png\n"
        "[/comparison]\n\n"
        "Tail kept."
    )
    cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://blutopia.cc")
    assert "ptpimg.me" not in cleaned
    assert "comparison" not in cleaned.lower()
    assert "Summary kept." in cleaned
    assert "Tail kept." in cleaned


def test_live_host_comparison_block_survives() -> None:
    desc = "[b]Source Comparison[/b]\n[comparison=A, B]\nhttps://img.example.invalid/a.png\nhttps://img.example.invalid/b.png\n[/comparison]\nSummary."
    cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://blutopia.cc")
    assert "[comparison=A, B]" in cleaned
    assert "img.example.invalid/a.png" in cleaned


def test_comparison_without_header_is_also_removed() -> None:
    desc = "Intro.\n[comparison=A, B]\nhttps://ptpimg.me/xxfake9.png\n[/comparison]\nOutro."
    cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://blutopia.cc")
    assert "ptpimg" not in cleaned
    assert "Intro." in cleaned and "Outro." in cleaned


def test_orphan_screenshot_headers_are_removed() -> None:
    desc = (
        "Notes worth keeping.\n"
        "[center][b][color=#f7942d]SCREENSHOTS[/color][/b][/center]\n"
        "[url=https://img.example.invalid/w][img]https://img.example.invalid/a.png[/img][/url]\n"
    )
    cleaned, images = BBCODE().clean_unit3d_description(desc, "https://blutopia.cc")
    assert "SCREENSHOTS" not in cleaned
    assert "Notes worth keeping." in cleaned
    assert len(images) == 1


def test_orphan_header_variants_are_removed() -> None:
    variants = [
        "Screens",
        "Screenshots:",
        "[b]Screen shots[/b]",
        "Captures d'écran :",
        "[center]— Captures —[/center]",
    ]
    for line in variants:
        desc = f"Kept intro.\n{line}\n[img]https://img.example.invalid/a.png[/img]\nKept outro."
        cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://blutopia.cc")
        assert "Kept intro." in cleaned and "Kept outro." in cleaned
        assert cleaned.count("\n") <= 2, f"header not removed for: {line!r} → {cleaned!r}"


def test_sentence_containing_screenshots_is_kept() -> None:
    desc = "These screenshots show the HDR grading difference.\n[img]https://img.example.invalid/a.png[/img]"
    cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://blutopia.cc")
    assert "These screenshots show" in cleaned


def test_sized_img_inside_spoiler_is_fully_removed() -> None:
    # Regression: stripping only the [img=N] opener left "url[/img]" orphans
    desc = "[spoiler=Ep1]\n1. [img=18]https://ptpimg.me/fakeflag.png[/img] / E-AC-3 / 224 kb/s\n[/spoiler]\nKept."
    cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://lst.gg")
    assert "[/img]" not in cleaned
    assert "ptpimg.me" not in cleaned
    assert "/ E-AC-3 / 224 kb/s" in cleaned
    assert "Kept." in cleaned


def test_sized_img_outside_spoiler_is_still_extracted() -> None:
    desc = "[img=350]https://img.example.invalid/shot.png[/img]\nSummary."
    cleaned, images = BBCODE().clean_unit3d_description(desc, "https://lst.gg")
    assert images and images[0]["raw_url"] == "https://img.example.invalid/shot.png"
    assert "[img" not in cleaned


def test_dead_ptpimg_images_are_dropped_from_imagelist() -> None:
    desc = "[img]https://ptpimg.me/fakedead.png[/img]\n[img]https://img.example.invalid/live.png[/img]\nSummary."
    cleaned, images = BBCODE().clean_unit3d_description(desc, "https://lst.gg")
    assert [i["raw_url"] for i in images] == ["https://img.example.invalid/live.png"]


def test_tonemapped_boilerplate_is_removed() -> None:
    desc = "Encoder notes kept.\nScreenshots have been tonemapped for reference.\nMore kept."
    cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://lst.gg")
    assert "tonemapped" not in cleaned
    assert "Encoder notes kept." in cleaned
    assert "More kept." in cleaned


def test_bare_ua_signature_is_removed_but_warning_banner_kept() -> None:
    desc = (
        "Kept intro.\n"
        "[url=https://github.com/Audionut/Upload-Assistant][size=4]Created by Upload Assistant v6.2.3[/size][/url]\n"
        "[b][color=red]DO NOT UPLOAD TO PUBLIC TRACKERS[/color][/b]\n"
        "Kept outro."
    )
    cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://lst.gg")
    assert "Created by Upload Assistant" not in cleaned
    assert "DO NOT UPLOAD TO PUBLIC TRACKERS" in cleaned
    assert "Kept intro." in cleaned and "Kept outro." in cleaned


def test_note_tags_are_dropped_or_unwrapped() -> None:
    desc = "Before.\n[note][/note]\n[note]Important note kept[/note]\nAfter."
    cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://lst.gg")
    assert "[note]" not in cleaned and "[/note]" not in cleaned
    assert "Important note kept" in cleaned


def test_orphan_url_closer_from_bracketed_label_is_removed() -> None:
    # A stripped site link whose label contains brackets used to leave the
    # closing [/url] behind (Decision to Leave case)
    desc = "Source: Some.Remux-GRP | Publisher [GER 2023] [/url] (Thanks!)\nKept."
    cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://lst.gg")
    assert "[/url]" not in cleaned
    assert "Publisher [GER 2023]  (Thanks!)" in cleaned
    assert "Kept." in cleaned


def test_orphan_url_opener_is_removed_too() -> None:
    desc = "See [url=https://example.invalid/page]the page\nKept."
    cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://lst.gg")
    assert "[url" not in cleaned
    assert "the page" in cleaned


def test_balanced_url_tags_survive() -> None:
    desc = "See [url=https://example.invalid/page]the page[/url] here."
    cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://lst.gg")
    assert "[url=https://example.invalid/page]the page[/url]" in cleaned


def test_ggbot_signature_is_removed() -> None:
    desc = "Kept.\n[center]Powered by GG-BOT Upload Assistant[/center]\nAlso kept."
    cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://lst.gg")
    assert "GG-BOT" not in cleaned
    assert "Kept." in cleaned and "Also kept." in cleaned


def test_note_text_mentioning_tool_names_survives() -> None:
    desc = (
        "This release was NOT Created by Upload Assistant, everything manual.\n"
        "Comparison workflow inspired by the one Powered by GG-BOT Upload Assistant docs.\n"
        "[center][size=4]Created by Upload Assistant v6.2.3[/size][/center]\n"
        "[b]Powered by GG-BOT Upload Assistant[/b]"
    )
    cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://lst.gg")
    # Prose lines mentioning the tools stay; pure signature lines go
    assert "NOT Created by Upload Assistant, everything manual." in cleaned
    assert "workflow inspired by" in cleaned
    assert "v6.2.3" not in cleaned
    assert "[b]Powered by GG-BOT Upload Assistant[/b]" not in cleaned


def test_ornamented_screenshot_header_is_removed() -> None:
    desc = "Kept notes.\n        •❅───✧❅✦ [color=#F69047]Screenshots[/color] ✦❅✧───❅•\n[img]https://img.example.invalid/a.png[/img]\nKept tail."
    cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://lst.gg")
    assert "Screenshots" not in cleaned
    assert "❅" not in cleaned
    assert "Kept notes." in cleaned and "Kept tail." in cleaned


def test_hentai_bot_signature_is_removed() -> None:
    desc = "Kept.\n[center][size=4]Created by Hentai Bot[/size][/center]\nAlso kept."
    cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://lst.gg")
    assert "Hentai Bot" not in cleaned
    assert "Kept." in cleaned and "Also kept." in cleaned


def test_pm_uploader_reseed_line_is_removed() -> None:
    desc = "Kept.\n[center][b]Please PM some.uploader if you have any issues or need a reseed![/b][/center]\nAlso kept."
    cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://lst.gg")
    assert "Please PM" not in cleaned
    assert "Kept." in cleaned and "Also kept." in cleaned


def test_only_uploader_signature_is_removed() -> None:
    desc = "Kept.\n[center][b]Brought to you by Only-Uploader [/b][/center]\nAlso kept."
    cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://lst.gg")
    assert "Only-Uploader" not in cleaned
    assert "Kept." in cleaned and "Also kept." in cleaned


def test_h3_wrapped_ornament_header_and_leftover_close_are_removed() -> None:
    desc = (
        "[h3][center]•❅───✧❅✦ [color=#F69047]Screenshots[/color]"
        " ✦❅✧───❅•[/center]\n\n"
        "[center]Find our uploads [url=https://example.com/torrents?name=Group]here[/url][/center][/h3]"
    )
    cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://lst.gg")
    assert "Screenshots" not in cleaned
    assert "[/h3]" not in cleaned
    assert "Find our uploads" in cleaned
    matched = "[h3]intro[/h3]\nBody."
    cleaned2, _ = BBCODE().clean_unit3d_description(matched, "https://lst.gg")
    assert "[h3]intro[/h3]" in cleaned2


def test_shared_with_upload_assistant_signature_is_removed() -> None:
    desc = "Kept.\n[right][url=https://github.com/wastaken7/Upload-Assistant][size=4]Shared with Upload-Assistant v3.4 (fork)[/size][/url][/right]\nAlso kept."
    cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://lst.gg")
    assert "Upload-Assistant" not in cleaned
    assert "Kept." in cleaned and "Also kept." in cleaned
