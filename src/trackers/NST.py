# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any

from src.console import console
from src.trackers.COMMON import COMMON
from src.trackers.FRENCH import FrenchTrackerMixin
from src.trackers.UNIT3D import UNIT3D


class NST(FrenchTrackerMixin, UNIT3D):
    """Nostradamus (nostradamus.foo) — French private tracker with UNIT3D-compatible API."""

    def __init__(self, config):
        super().__init__(config, tracker_name="NST")
        self.config = config
        self.common = COMMON(config)
        self.tracker = "NST"
        self.base_url = "https://nostradamus.foo"
        # NST uses /api/upload-assistant/ prefix for UA compatibility
        self.id_url = f"{self.base_url}/api/upload-assistant/torrents/"
        self.upload_url = f"{self.base_url}/api/upload-assistant/torrents/upload"
        self.search_url = f"{self.base_url}/api/upload-assistant/torrents/filter"
        self.torrent_url = f"{self.base_url}/torrents/"
        self.banned_groups: list[str] = []
        self.source_flag = "NST"

    # ── FrenchTrackerMixin overrides ──────────────────────────────────

    WEB_LABEL: str = "WEB-DL"

    # NST uses original (English) titles
    PREFER_ORIGINAL_TITLE: bool = True

    # NST wants streaming service in name
    INCLUDE_SERVICE_IN_NAME: bool = True

    # ── Category mapping ──────────────────────────────────────────────
    # From https://nostradamus.foo/api-access "Available Categories":
    # 2000 Films (parent)
    #   2010 Animation
    #   2020 Film
    #   2030 Documentaire
    #   2040 Spectacle
    #   2060 Concert
    # 5000 Séries TV (parent)
    #   5040 Série TV
    #   5060 Sport
    #   5070 Animation Série
    #   5080 Emission TV

    async def get_category_id(self, meta: dict[str, Any], category: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        cat = category or meta.get("category", "")
        genres = str(meta.get("genres", "")).lower()
        keywords = str(meta.get("keywords", "")).lower()
        is_anime = bool(meta.get("anime"))

        category_id = {
            "MOVIE": "2020",
            "TV": "5040",
        }

        if mapping_only:
            return category_id
        if reverse:
            return {v: k for k, v in category_id.items()}

        # Refined sub-category detection
        if cat == "MOVIE" or (not cat and not reverse):
            if "documentary" in genres or "documentary" in keywords:
                return {"category_id": "2030"}
            if is_anime:
                return {"category_id": "2010"}
            if "concert" in keywords or "live" in keywords:
                return {"category_id": "2060"}
            return {"category_id": category_id.get(cat, "2020")}
        elif cat == "TV":
            if is_anime:
                return {"category_id": "5070"}
            if "documentary" in genres or "documentary" in keywords:
                return {"category_id": "2030"}
            if "sport" in genres or "sport" in keywords:
                return {"category_id": "5060"}
            return {"category_id": "5040"}

        return {"category_id": category_id.get(cat, "2020")}

    async def get_type_id(self, meta: dict[str, Any], type: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        type_id = {
            "DISC": "1",
            "REMUX": "2",
            "ENCODE": "3",
            "WEBDL": "4",
            "WEBRIP": "5",
            "HDTV": "6",
        }
        if mapping_only:
            return type_id
        if reverse:
            return {v: k for k, v in type_id.items()}
        t = type or meta.get("type", "")
        return {"type_id": type_id.get(t, "0")}

    async def get_resolution_id(self, meta: dict[str, Any], resolution: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        resolution_id = {
            "4320p": "1",
            "2160p": "2",
            "1080p": "3",
            "1080i": "4",
            "720p": "5",
            "576p": "6",
            "576i": "7",
            "480p": "8",
            "480i": "9",
        }
        if mapping_only:
            return resolution_id
        if reverse:
            return {v: k for k, v in resolution_id.items()}
        r = resolution or meta.get("resolution", "")
        return {"resolution_id": resolution_id.get(r, "10")}

    async def get_additional_checks(self, meta: dict[str, Any]) -> bool:
        french_languages = ["french", "fre", "fra", "fr", "français", "francais", "fr-fr", "fr-ca"]
        if not await self.common.check_language_requirements(
            meta,
            self.tracker,
            languages_to_check=french_languages,
            check_audio=True,
            check_subtitle=True,
            require_both=False,
        ):
            console.print(f"[bold red]Language requirements not met for {self.tracker}.[/bold red]")
            return False
        return True
