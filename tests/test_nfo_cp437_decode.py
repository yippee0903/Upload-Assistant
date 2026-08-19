# Scene NFOs are drawn in CP437 (the DOS codepage). Decoding them as
# latin-1 turns the box art into accented letters; utf-8 with
# errors="replace" turns it into replacement-character soup, which sites
# reject as non-textual content.

from src.nfo_generator import decode_nfo


def test_utf8_passes_through():
    assert decode_nfo("héllo █▓\n".encode()) == "héllo █▓\n"


def test_cp437_box_art_decodes_to_drawing_characters():
    assert decode_nfo(b"\xdc\xdb\xb2\xdf ULYSSE \xfe") == "▄█▓▀ ULYSSE ■"


def test_cp437_never_fails():
    assert len(decode_nfo(bytes(range(1, 256)))) == 255
