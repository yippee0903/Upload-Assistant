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
    # The tool-credit sentence is a bot signature too, dropped on its own.
    assert cleaned == ""


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


_MI_SPOILER = "[center][spoiler=Example.S01E0{n}.1080p.WEB-GRP]\n[b]General[/b]\n[b]Format:[/b] Matroska\n[/spoiler][/center]"


def test_generated_pack_mediainfo_spoilers_are_dropped() -> None:
    desc = "Intro.\n" + _MI_SPOILER.format(n=2) + "\n[center][spoiler=Other files]\n" + _MI_SPOILER.format(n=3) + "\n[/spoiler][/center]\n[center]Example.S01E01.1080p.WEB-GRP[/center]\nOutro."
    cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://example-tracker.org")
    assert "General" not in cleaned and "Other files" not in cleaned and "S01E01" not in cleaned
    assert "Intro." in cleaned and "Outro." in cleaned


def test_non_mediainfo_spoilers_are_kept() -> None:
    desc = "[center][spoiler=NFO][code]nfo[/code][/spoiler][/center]\n[spoiler=Notes]Source notes[/spoiler]"
    cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://example-tracker.org")
    assert "[spoiler=NFO]" in cleaned and "[spoiler=Notes]" in cleaned


_BOT_FICHE = (
    "[b][color=#2E86C1]Example Show (2024)[/color][/b]\n\n"
    "[b][color=#6C3483]Synopsis:[/color][/b]\nA paragraph about the plot.\n\n"
    "[tr]\n[td][/td]\n[td][/td]\n[/tr]\n\n"
    "[table]\n[tr]\n[td]Genre[/td]\n[td]Drama[/td]\n[/tr]\n[tr]\n[td]Rating[/td]\n[td]7.5/10[/td]\n[/tr]\n"
    "[tr]\n[td]Release Date[/td]\n[td]2024-07-10[/td]\n[/tr]\n[tr]\n[td]Language[/td]\n[td]EN[/td]\n[/tr]\n[/table]\n\n"
    "[b][color=#2E86C1]cast:[/color][/b]\nActor One, Actor Two\n\n"
    "[b][url=https://www.youtube.com/watch?v=abc][Trailer on YouTube][/url][/b]\n\n"
    "[b][color=#757575]Created with mkbrr, ffmpeg, and mediainfo.[/color][/b]"
)


def test_bot_generated_fiche_is_emptied() -> None:
    cleaned, _ = BBCODE().clean_unit3d_description(_BOT_FICHE, "https://example-tracker.org")
    assert cleaned == ""


_BOT_FICHE_QUOTED = (
    "[center][b][color=#ff00ff][size=18]This release is sourced from Netflix and is not transcoded, just remuxed from the direct Netflix stream[/size][/color][/b][/center]\n"
    "[center][center][b][size=18][color=#2E86C1]Example Movie (2026)[/color][/size][/b][/center]\n\n"
    "[center][b][size=16][color=#117A65]By:[/color][/size][/b] [i]Some Director[/i][/center]\n\n"
    "[b][size=15][color=#6C3483]Synopsis:[/color][/size][/b]\n[quote]A paragraph about the plot.[/quote]\n\n"
    "[center][tr]\n[td][/td]\n[td][/td]\n[/tr][/center]\n\n"
    "[b][size=15][color=#2E86C1]cast:[/color][/size][/b]\n[quote]Actor One, Actor Two[/quote]\n[/center]\n[center]\n"
)


def test_quoted_bot_fiche_variant_is_emptied() -> None:
    cleaned, _ = BBCODE().clean_unit3d_description(_BOT_FICHE_QUOTED, "https://example-tracker.org")
    assert cleaned == ""
    cleaned, _ = BBCODE().clean_unit3d_description("Encoded from UHD.\n\n" + _BOT_FICHE_QUOTED + "\nSeed please.", "https://example-tracker.org")
    assert cleaned.split() == ["Encoded", "from", "UHD.", "Seed", "please."]


def test_find_our_uploads_link_is_removed_but_source_notes_stay() -> None:
    desc = (
        "[h3][center][color=#F4AACA]Source 1[/color]: CR Video and Subtitles.\n"
        "[color=#F4AACA]Source 2[/color]: AMZN Audio.\n"
        "[center]Find our uploads [url=https://example-tracker.org/torrents?name=GRP]🐾 here 🐾[/url][/center][/h3]\n[center]\n"
    )
    cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://other-tracker.org")
    assert "Find our uploads" not in cleaned and "[url=" not in cleaned
    assert "Source 1" in cleaned and "AMZN Audio" in cleaned


def test_uploader_notes_survive_the_fiche_cleanup() -> None:
    cleaned, _ = BBCODE().clean_unit3d_description("Encoded from the UHD source.\n\n" + _BOT_FICHE + "\nSeed please.", "https://example-tracker.org")
    assert cleaned == "Encoded from the UHD source.\nSeed please."


def test_hand_written_table_and_text_are_kept() -> None:
    desc = "[table][tr][td]Source[/td][td]UHD BluRay[/td][/tr][/table]\nSynopsis: a hand-written one-liner."
    cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://example-tracker.org")
    assert cleaned == desc


def test_only_uploader_signature_is_removed() -> None:
    desc = "Kept.\n[center][b]Brought to you by Only-Uploader [/b][/center]\nAlso kept."
    cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://lst.gg")
    assert "Only-Uploader" not in cleaned
    assert "Kept." in cleaned and "Also kept." in cleaned


def test_onlyencodes_signature_is_removed() -> None:
    for sig in ("[center]OnlyEncodes Upload Assistant[/center]", "[center]OnlyEncodes Uploader - Powered by L4G's Upload Assistant[/center]"):
        cleaned, _ = BBCODE().clean_unit3d_description(f"Kept.\n{sig}\nAlso kept.", "https://example-tracker.org")
        assert "OnlyEncodes" not in cleaned and "Powered by" not in cleaned
        assert "Kept." in cleaned and "Also kept." in cleaned


def test_h3_wrapped_ornament_header_and_leftover_close_are_removed() -> None:
    desc = (
        "[h3][center]•❅───✧❅✦ [color=#F69047]Screenshots[/color]"
        " ✦❅✧───❅•[/center]\n\n"
        "[center]Encoded from the UHD source.[/center][/h3]"
    )
    cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://lst.gg")
    assert "Screenshots" not in cleaned
    assert "[/h3]" not in cleaned
    assert "Encoded from the UHD source." in cleaned
    matched = "[h3]intro[/h3]\nBody."
    cleaned2, _ = BBCODE().clean_unit3d_description(matched, "https://lst.gg")
    assert "[h3]intro[/h3]" in cleaned2


def test_shared_with_upload_assistant_signature_is_removed() -> None:
    signatures = [
        "[right][url=https://github.com/wastaken7/Upload-Assistant][size=4]Shared with Upload-Assistant v3.4 (fork)[/size][/url][/right]",
        "Shared with Upload-Assistant",
        "Shared with Upload-Assistant v3.4",
        "Shared with Upload-Assistant (fork)",
    ]
    for signature in signatures:
        desc = f"Kept.\n{signature}\nAlso kept."
        cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://lst.gg")
        assert cleaned == "Kept.\nAlso kept.", f"signature not fully removed: {signature!r} → {cleaned!r}"


def test_youtube_embed_is_removed() -> None:
    desc = "Kept.\n[youtube]xXxFAKEIDxXx[/youtube]\nAlso kept."
    cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://lst.gg")
    assert cleaned == "Kept.\nAlso kept."


def test_easy_uploader_signature_is_removed() -> None:
    desc = (
        "Kept.\n"
        "[color=#7760de]⚡ Uploaded using EASY UPLOAD3R ⚡[/color]\n"
        "[color=#5f5f5f]A UNIT3D plugin proudly developed by [b]SomeDev[/b][/color]\n"
        "Also kept."
    )
    cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://lst.gg")
    assert cleaned == "Kept.\nAlso kept."
    prose = "The release was uploaded using EASY UPLOAD3R before being fixed."
    cleaned2, _ = BBCODE().clean_unit3d_description(prose, "https://lst.gg")
    assert cleaned2 == prose


def test_empty_code_blocks_are_removed() -> None:
    cases = {
        "[center][code][/code][/center]\nKept.": "Kept.",
        "Kept.\n[code][/code]\nAlso kept.": "Kept.\nAlso kept.",
        "[center]Kept [code][/code][/center]": "[center]Kept[/center]",
        "[code]NFO worth keeping[/code]": "[code]NFO worth keeping[/code]",
    }
    for desc, expected in cases.items():
        cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://lst.gg")
        assert cleaned == expected, f"{desc!r} → {cleaned!r}"


def test_center_wrappers_emptied_by_removals_are_dropped() -> None:
    cases = [
        "Kept.\n[center][youtube]xXxFAKEIDxXx[/youtube][/center]\nAlso kept.",
        "Kept.\n[center][note][/note][/center]\nAlso kept.",
    ]
    for desc in cases:
        cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://lst.gg")
        assert cleaned == "Kept.\nAlso kept.", f"{desc!r} → {cleaned!r}"


def test_ggbot_heart_signature_is_removed() -> None:
    desc = "Kept.\nUploaded with [color=red]❤[/color] using GG-BOT Upload Assistant\nAlso kept."
    cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://lst.gg")
    assert cleaned == "Kept.\nAlso kept."


def test_upbrr_signature_is_removed() -> None:
    desc = "Kept.\n[right][url=https://github.com/autobrr/upbrr]Uploaded by upbrr[/url][/right]\nAlso kept."
    cleaned, _ = BBCODE().clean_unit3d_description(desc, "https://lst.gg")
    assert cleaned == "Kept.\nAlso kept."


def test_site_anonymisation_keeps_image_and_link_hosts_intact() -> None:
    desc = "[url=https://seedpool.org/torrents/1][img]https://cdn.seedpool.org/sp.png[/img][/url] [img]https://i.seedpool.org/abc[/img] Mirrored from seedpool.org."
    cleaned, images = BBCODE().clean_unit3d_description(desc, "https://seedpool.org")
    assert sorted((i["img_url"], i["web_url"]) for i in images) == [
        ("https://cdn.seedpool.org/sp.png", "https://seedpool.org/torrents/1"),
        ("https://i.seedpool.org/abc", "https://i.seedpool.org/abc"),
    ]
    assert "seedpool.org" not in cleaned and "from seedpool." in cleaned


def test_site_anonymisation_leaves_longer_hosts_alone() -> None:
    cleaned, _ = BBCODE().clean_unit3d_description("See seedpool.org.uk or seedpool.org-mirror, not seedpool.org!", "https://seedpool.org")
    assert cleaned == "See seedpool.org.uk or seedpool.org-mirror, not seedpool!"
