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
