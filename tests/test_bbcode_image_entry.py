"""Images reused from an existing description carry a thumbnail/full-size pair when the host allows deriving it."""

from src.bbcode import BBCODE, image_entry

FULL = "https://img90.pixhost.to/images/376/1_file.png"
THUMB = "https://t90.pixhost.to/thumbs/376/1_file.png"
PAGE = "https://pixhost.to/show/376/1_file.png"


def test_pixhost_full_size_gets_its_thumbnail() -> None:
    assert image_entry(FULL, PAGE) == {"img_url": THUMB, "raw_url": FULL, "web_url": PAGE}


def test_pixhost_thumbnail_gets_its_full_size() -> None:
    assert image_entry(THUMB, PAGE) == {"img_url": THUMB, "raw_url": FULL, "web_url": PAGE}


def test_imgbox_thumbnail_gets_its_full_size() -> None:
    entry = image_entry("https://thumbs2.imgbox.com/ab/cd/XXXX_t.png", "https://imgbox.com/XXXX")
    assert entry["raw_url"] == "https://images2.imgbox.com/ab/cd/XXXX_o.png"


def test_unknown_host_is_left_alone() -> None:
    url = "https://example.org/shot.png"
    assert image_entry(url) == {"img_url": url, "raw_url": url, "web_url": url}


def test_unit3d_description_keeps_pixhost_pairs_and_drops_bare_thumbnails() -> None:
    desc = f"[url={PAGE}][img]{FULL}[/img][/url] [url=https://other.host/x][img]https://other.host/thumbs/x_t.png[/img][/url]"
    _, images = BBCODE().clean_unit3d_description(desc, "https://example-tracker.org")
    assert images == [{"img_url": THUMB, "raw_url": FULL, "web_url": PAGE}]
