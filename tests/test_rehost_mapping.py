"""The domain → image-host mapping is defined once in src/rehostimages.py;
every host a tracker approves must be recognizable through it."""

import glob
import re

from src.rehostimages import URL_HOST_MAPPING


def _approved_lists() -> dict[str, list[str]]:
    lists: dict[str, list[str]] = {}
    for path in glob.glob("src/trackers/*.py"):
        source = open(path, encoding="utf-8").read()
        match = re.search(r"approved_image_hosts(?::[^=]+)? = \[([^\]]*)\]", source)
        if match:
            hosts = re.findall(r'"([^"]+)"', match.group(1))
            if hosts:
                lists[path] = hosts
    return lists


def test_trackers_no_longer_define_local_mappings():
    for path in glob.glob("src/trackers/*.py"):
        assert "url_host_mapping" not in open(path, encoding="utf-8").read(), path


def test_every_approved_host_has_a_domain_in_the_central_mapping():
    known_hosts = set(URL_HOST_MAPPING.values())
    lists = _approved_lists()
    assert lists, "no approved_image_hosts lists found"
    for path, hosts in lists.items():
        missing = [h for h in hosts if h not in known_hosts]
        assert not missing, f"{path}: approved hosts without a domain mapping: {missing}"


def test_mapping_uses_the_imagebam_slug():
    assert URL_HOST_MAPPING["imagebam.com"] == "imagebam"
    assert "bam" not in URL_HOST_MAPPING.values()
