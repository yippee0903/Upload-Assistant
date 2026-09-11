# Screenshots living on a tracker's own image host (beyondhd.co, tracker CDNs)
# are unusable on any other site: rehost the whole reused list onto a host
# every destination of this upload accepts, before per-tracker validation.

import asyncio
from typing import Any

import src.rehostimages as rh
from src.imagehosts import SITE_BOUND_HOSTS, host_slug

CFG = {"DEFAULT": {"img_host_1": "imgbb", "img_host_2": "imgbox"}}


class _WithList:
    approved_image_hosts = ["imgbox", "imgbb", "bhd"]

    def __init__(self, config: Any) -> None:
        pass


class _NoList:
    def __init__(self, config: Any) -> None:
        pass


def _img(url: str) -> dict[str, str]:
    return {"img_url": url, "raw_url": url, "web_url": url}


def _run(monkeypatch: Any, images: list[dict[str, str]], trackers: list[str]) -> tuple[dict[str, Any], list[Any]]:
    calls: list[Any] = []

    async def fake_check_hosts(self: Any, meta: Any, tracker: str, img_host_index: int = 1, approved_image_hosts: Any = None) -> Any:
        calls.append((tracker, sorted(approved_image_hosts or [])))
        return [_img("https://i.ibb.co/new1.png"), _img("https://i.ibb.co/new2.png")], False, True

    monkeypatch.setattr(rh.RehostImagesManager, "check_hosts", fake_check_hosts)
    meta: dict[str, Any] = {"image_list": images, "trackers": trackers, "debug": False, "imghost": "imgbb"}
    asyncio.run(rh.rehost_site_bound_images(meta, CFG, {"AAA": _WithList, "BBB": _NoList}, trackers))
    return meta, calls


def test_tracker_owned_hosts_are_site_bound() -> None:
    assert host_slug("beyondhd.co") in SITE_BOUND_HOSTS
    assert host_slug("i.ibb.co") not in SITE_BOUND_HOSTS


def test_bound_images_are_rehosted_onto_hosts_common_to_all_destinations(monkeypatch: Any) -> None:
    meta, calls = _run(monkeypatch, [_img("https://beyondhd.co/images/a.png"), _img("https://beyondhd.co/images/b.png")], ["AAA", "BBB"])
    # BBB has no list, so it accepts public hosts only: bhd drops out of the common set
    assert calls == [("reused", ["imgbb", "imgbox"])]
    assert [i["raw_url"] for i in meta["image_list"]] == ["https://i.ibb.co/new1.png", "https://i.ibb.co/new2.png"]


def test_destination_owning_the_host_keeps_it_approved(monkeypatch: Any) -> None:
    _, calls = _run(monkeypatch, [_img("https://beyondhd.co/images/a.png")], ["AAA"])
    assert calls and "bhd" in calls[0][1]


def test_public_images_are_left_alone(monkeypatch: Any) -> None:
    meta, calls = _run(monkeypatch, [_img("https://i.ibb.co/x.png")], ["AAA", "BBB"])
    assert calls == [] and meta["image_list"][0]["raw_url"] == "https://i.ibb.co/x.png"
