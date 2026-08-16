"""The domain → image-host mapping is defined once in src/rehostimages.py;
every host a tracker approves must be recognizable through it."""

import asyncio
import glob
import re

from src.rehostimages import URL_HOST_MAPPING, validate_reused_image_hosts


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


class TestValidateReusedImageHosts:
    """Behavioral coverage of validate_reused_image_hosts with tracker doubles."""

    class _FakeTracker:
        instances: list["TestValidateReusedImageHosts._FakeTracker"] = []

        def __init__(self, config: object) -> None:
            self.calls: list[dict] = []
            type(self).instances.append(self)

        async def check_image_hosts(self, meta: dict) -> None:
            self.calls.append(meta)
            meta["V3X_images_key"] = [{"img_url": "https://approved.example/a.png"}]

    def _map(self):
        self._FakeTracker.instances = []
        return {"V3X": self._FakeTracker, "LST": self._FakeTracker}

    def test_relevant_tracker_is_validated(self):
        meta = {"trackers": ["V3X", "LST"], "image_list": [{"img_url": "x"}]}
        validated = asyncio.run(validate_reused_image_hosts(meta, {}, self._map()))
        # LST has no host requirements — only V3X is validated
        assert validated == ["V3X"]
        assert len(self._FakeTracker.instances) == 1
        assert self._FakeTracker.instances[0].calls == [meta]
        assert meta["V3X_images_key"]

    def test_skip_imghost_upload_bypasses_validation(self):
        meta = {"trackers": ["V3X"], "image_list": [{"img_url": "x"}], "skip_imghost_upload": True}
        assert asyncio.run(validate_reused_image_hosts(meta, {}, self._map())) == []
        assert self._FakeTracker.instances == []

    def test_no_relevant_trackers_is_a_noop(self):
        meta = {"trackers": ["LST"], "image_list": [{"img_url": "x"}]}
        assert asyncio.run(validate_reused_image_hosts(meta, {}, self._map())) == []
        assert self._FakeTracker.instances == []

    def test_empty_image_list_is_a_noop(self):
        meta = {"trackers": ["V3X"], "image_list": []}
        assert asyncio.run(validate_reused_image_hosts(meta, {}, self._map())) == []
        assert self._FakeTracker.instances == []


def test_upload_wires_the_reused_images_validation():
    # Wiring guard only — the behavior itself is covered above.
    source = open("upload.py", encoding="utf-8").read()
    assert "await validate_reused_image_hosts(meta, config, tracker_class_map)" in source
