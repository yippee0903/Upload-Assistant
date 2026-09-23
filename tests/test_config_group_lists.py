# A global, config-driven release-group list, independent of any tracker's
# own settings: DEFAULT["banned_groups"] refuses the upload outright, and
# a second list can reuse the same helper. Both match the release tag case-insensitively and
# accept either a list or a comma-separated string, like the rest of DEFAULT.

from typing import Any

import pytest

from src.trackers.COMMON import group_listed_in, release_group


def _config(**default: Any) -> dict[str, Any]:
    return {"DEFAULT": {"tmdb_api": "fake", **default}, "TRACKERS": {}}


class TestReleaseGroup:
    def test_tag_is_normalised(self) -> None:
        assert release_group({"tag": "-FoX"}) == "fox"

    def test_untagged_release_has_no_group(self) -> None:
        assert release_group({"tag": ""}) == ""
        assert release_group({}) == ""


class TestGroupListedIn:
    @pytest.mark.parametrize("groups", [["FoX", "BadGrp"], "FoX, BadGrp", "fox,badgrp", ["-FoX"]])
    def test_listed_group_matches_whatever_the_config_shape(self, groups: Any) -> None:
        assert group_listed_in(_config(banned_groups=groups), "banned_groups", {"tag": "-FoX"}) is True

    def test_match_is_case_insensitive(self) -> None:
        assert group_listed_in(_config(banned_groups=["fox"]), "banned_groups", {"tag": "-FOX"}) is True

    def test_unlisted_group_does_not_match(self) -> None:
        assert group_listed_in(_config(banned_groups=["BadGrp"]), "banned_groups", {"tag": "-FoX"}) is False

    def test_partial_names_do_not_match(self) -> None:
        assert group_listed_in(_config(banned_groups=["Fo"]), "banned_groups", {"tag": "-FoX"}) is False
        assert group_listed_in(_config(banned_groups=["FoXy"]), "banned_groups", {"tag": "-FoX"}) is False

    def test_untagged_release_never_matches(self) -> None:
        assert group_listed_in(_config(banned_groups=["FoX"]), "banned_groups", {"tag": ""}) is False

    @pytest.mark.parametrize("groups", [None, "", [], "  ,  "])
    def test_missing_or_empty_list_never_matches(self, groups: Any) -> None:
        assert group_listed_in(_config(banned_groups=groups), "banned_groups", {"tag": "-FoX"}) is False

    def test_absent_key_never_matches(self) -> None:
        assert group_listed_in(_config(), "banned_groups", {"tag": "-FoX"}) is False

    def test_each_key_reads_its_own_list(self) -> None:
        config = _config(banned_groups=["BadGrp"], other_groups=["FoX"])

        assert group_listed_in(config, "banned_groups", {"tag": "-FoX"}) is False
        assert group_listed_in(config, "other_groups", {"tag": "-FoX"}) is True
