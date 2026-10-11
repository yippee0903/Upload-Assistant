# A release from one of the configured personal groups gets the
# personal-release flag, and the anon flag too when the toggle is on.

from typing import Any

from src.prep import _apply_personal_release_group


def _run(tag: str, **default_config: Any) -> dict[str, Any]:
    meta: dict[str, Any] = {"tag": tag, "anon": False}
    _apply_personal_release_group(meta, {"personal_release_groups": ["GRP"], **default_config})
    return meta


def test_personal_group_sets_personalrelease_only_by_default() -> None:
    meta = _run("-grp")
    assert meta["personalrelease"] is True
    assert meta["anon"] is False


def test_personal_group_sets_anon_when_the_toggle_is_on() -> None:
    assert _run("-GRP", anon_personal_releases=True)["anon"] is True


def test_other_group_is_left_alone_even_with_the_toggle_on() -> None:
    meta = _run("-OTHER", anon_personal_releases=True)
    assert not meta.get("personalrelease")
    assert meta["anon"] is False


def test_no_tag_never_matches() -> None:
    meta: dict[str, Any] = {"tag": "", "anon": False}
    _apply_personal_release_group(meta, {"personal_release_groups": [""], "anon_personal_releases": True})
    assert not meta.get("personalrelease")
    assert meta["anon"] is False
