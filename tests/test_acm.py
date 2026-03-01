# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Tests for ACM (Asian Cinema) tracker."""

from __future__ import annotations

from typing import Any

import pytest

from src.trackers.ACM import ACM


def _config() -> dict[str, Any]:
    return {
        "DEFAULT": {"tmdb_api": "fake"},
        "TRACKERS": {
            "ACM": {
                "api_key": "FAKE_KEY",
                "announce_url": "https://eiga.moi/announce/FAKE_PASSKEY",
            },
        },
    }


def _meta(**overrides: Any) -> dict[str, Any]:
    m: dict[str, Any] = {
        "origin_country": [],
        "production_countries": [],
        "original_language": "en",
        "tracker_status": {"ACM": {}},
    }
    m.update(overrides)
    return m


class TestCheckAsianOrigin:
    """Verify check_asian_origin logic with origin_country vs production_countries."""

    def test_japanese_origin(self):
        """A purely Japanese show should pass."""
        acm = ACM(_config())
        meta = _meta(origin_country=["JP"])
        assert acm.check_asian_origin(meta) is True

    def test_korean_origin(self):
        """A Korean show should pass."""
        acm = ACM(_config())
        meta = _meta(origin_country=["KR"])
        assert acm.check_asian_origin(meta) is True

    def test_us_origin_only(self):
        """A purely US show should NOT pass."""
        acm = ACM(_config())
        meta = _meta(origin_country=["US"])
        assert acm.check_asian_origin(meta) is False

    def test_us_origin_with_jp_production(self):
        """US origin with Japanese co-production should NOT pass.

        This is the Monarch: Legacy of Monsters case — an American show
        co-produced with a Japanese studio. origin_country=['US'] takes
        priority over production_countries containing JP.
        """
        acm = ACM(_config())
        meta = _meta(
            origin_country=["US"],
            production_countries=[
                {"iso_3166_1": "JP", "name": "Japan"},
                {"iso_3166_1": "US", "name": "United States of America"},
            ],
        )
        assert acm.check_asian_origin(meta) is False

    def test_jp_origin_with_us_production(self):
        """Japanese origin with US co-production should pass."""
        acm = ACM(_config())
        meta = _meta(
            origin_country=["JP"],
            production_countries=[
                {"iso_3166_1": "US", "name": "United States of America"},
                {"iso_3166_1": "JP", "name": "Japan"},
            ],
        )
        assert acm.check_asian_origin(meta) is True

    def test_multi_asian_origin(self):
        """Multiple Asian origin countries should pass."""
        acm = ACM(_config())
        meta = _meta(origin_country=["JP", "KR"])
        assert acm.check_asian_origin(meta) is True

    def test_mixed_origin_with_asian(self):
        """US + KR origin — at least one Asian country means pass."""
        acm = ACM(_config())
        meta = _meta(origin_country=["US", "KR"])
        assert acm.check_asian_origin(meta) is True

    def test_fallback_to_production_countries(self):
        """When origin_country is empty, fall back to production_countries."""
        acm = ACM(_config())
        meta = _meta(
            origin_country=[],
            production_countries=[
                {"iso_3166_1": "IN", "name": "India"},
            ],
        )
        assert acm.check_asian_origin(meta) is True

    def test_fallback_non_asian_production(self):
        """When origin_country is empty and production is non-Asian, reject."""
        acm = ACM(_config())
        meta = _meta(
            origin_country=[],
            production_countries=[
                {"iso_3166_1": "FR", "name": "France"},
            ],
        )
        assert acm.check_asian_origin(meta) is False

    def test_no_country_data(self):
        """No origin or production data should reject."""
        acm = ACM(_config())
        meta = _meta(origin_country=[], production_countries=[])
        assert acm.check_asian_origin(meta) is False

    def test_none_origin_fallback(self):
        """origin_country=None should fall back to production_countries."""
        acm = ACM(_config())
        meta = _meta(
            origin_country=None,
            production_countries=[{"iso_3166_1": "TH", "name": "Thailand"}],
        )
        assert acm.check_asian_origin(meta) is True

    def test_case_insensitive(self):
        """Country codes should be matched case-insensitively."""
        acm = ACM(_config())
        meta = _meta(origin_country=["jp"])
        assert acm.check_asian_origin(meta) is True

    def test_empty_strings_in_origin_fallback(self):
        """origin_country with only empty/blank strings should fall back to production_countries."""
        acm = ACM(_config())
        meta = _meta(
            origin_country=["", "  ", None],
            production_countries=[{"iso_3166_1": "KR", "name": "South Korea"}],
        )
        assert acm.check_asian_origin(meta) is True

    def test_empty_strings_in_origin_no_fallback(self):
        """origin_country with only empty strings and no production data should reject."""
        acm = ACM(_config())
        meta = _meta(origin_country=["", None], production_countries=[])
        assert acm.check_asian_origin(meta) is False
