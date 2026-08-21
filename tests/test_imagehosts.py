from src.imagehosts import IMAGE_HOSTS, UPLOAD_HOSTS, URL_HOST_MAPPING, image_size_ok


def test_image_size_ok():
    assert image_size_ok("imgbb", 75_000) is False
    assert image_size_ok("imgbb", 31_000_000) is True
    assert image_size_ok("imgbb", 31_000_001) is False
    assert image_size_ok("imgbox", 10_000_001) is False
    assert image_size_ok("ptpimg", 10**9) is True
    assert image_size_ok("imgur", 100_000) is False  # recognised, not uploadable
    assert image_size_ok(None, 100_000) is False
    assert image_size_ok("nope", 100_000) is False


def test_registry_is_consistent():
    assert all(IMAGE_HOSTS[slug].uploadable for slug in UPLOAD_HOSTS)
    assert set(URL_HOST_MAPPING.values()) <= set(IMAGE_HOSTS)
    assert "zipline" in UPLOAD_HOSTS and "ziplinestudio" not in UPLOAD_HOSTS
