from src.rehostimages import choose_common_host, configured_image_hosts


def test_configured_hosts_in_priority_order_deduped():
    cfg = {"DEFAULT": {"img_host_1": "imgbox", "img_host_2": "ptpimg", "img_host_3": "imgbox", "img_host_5": "pixhost"}}
    assert configured_image_hosts(cfg) == ["imgbox", "ptpimg", "pixhost"]


def test_prefers_configured_common_host_in_config_order():
    approved = {"A": ["imgbox", "ptpimg", "pixhost"], "B": ["ptpimg", "pixhost"]}
    allowed, preferred = choose_common_host(approved, ["imgbox", "pixhost", "ptpimg"], "imgbox")
    assert allowed == ["pixhost", "ptpimg"]
    assert preferred == "pixhost"


def test_keeps_current_host_when_acceptable():
    approved = {"A": ["imgbox", "ptpimg"], "B": ["ptpimg"]}
    assert choose_common_host(approved, ["ptpimg"], "ptpimg") == (["ptpimg"], None)


def test_falls_back_to_sorted_common_when_none_configured():
    approved = {"A": ["zz", "aa"], "B": ["aa", "zz"]}
    assert choose_common_host(approved, ["imgbox"], "imgbox") == (["aa", "zz"], "aa")


def test_no_constraint_when_a_tracker_is_unknown_or_nothing_in_common():
    assert choose_common_host({"A": ["imgbox"], "B": None}, ["imgbox"], "imgbox") == (None, None)
    assert choose_common_host({"A": ["imgbox"], "B": ["ptpimg"]}, ["imgbox"], "imgbox") == (None, None)
    assert choose_common_host({}, ["imgbox"], "imgbox") == (None, None)
