# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any

from src.console import console
from src.trackers.COMMON import COMMON, ask_to_continue, is_adult
from src.trackers.UNIT3D import UNIT3D

Meta = dict[str, Any]


class LUME(UNIT3D):
    skip_nfo: bool = True

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config, tracker_name="LUME")
        self.config = config
        self.common = COMMON(config)
        self.tracker = "LUME"
        self.base_url = "https://luminarr.me"
        self.id_url = f"{self.base_url}/api/torrents/"
        self.upload_url = f"{self.base_url}/api/torrents/upload"
        self.requests_url = f"{self.base_url}/api/requests/filter"
        self.search_url = f"{self.base_url}/api/torrents/filter"
        self.torrent_url = f"{self.base_url}/torrents/"
        self.banned_groups: list[str] = []

    async def get_additional_data(self, meta: Meta) -> dict[str, Any]:
        data = {
            "mod_queue_opt_in": await self.get_flag(meta, "modq"),
        }

        return data

    async def get_additional_files(self, meta: Meta) -> dict[str, tuple[str, bytes, str]]:
        return {}

    async def get_additional_checks(self, meta: Meta) -> bool:
        should_continue = True

        if meta["is_disc"] not in ["BDMV", "DVD"] and not await self.common.check_language_requirements(
            meta, self.tracker, languages_to_check=["english"], check_audio=True, check_subtitle=True, original_language=True
        ):
            return False

        if (
            meta["is_disc"] not in ["BDMV", "DVD"]
            and meta["resolution"] not in ["8640p", "4320p", "2160p", "1440p", "1080p", "1080i", "720p"]
            and not ask_to_continue(meta, f"{self.tracker} only allows SD releases when the content does not have a higher resolution release.")
        ):
            return False

        if meta["is_disc"] not in ["BDMV", "DVD"] and meta.get("container", "") != "mkv":
            console.print(f"[bold red]{self.tracker} only allows MKV containers for non-disc uploads.[/bold red]")
            return False

        if not meta["valid_mi_settings"]:
            console.print(f"[bold red]No encoding settings in mediainfo, skipping {self.tracker} upload.[/bold red]")
            return False

        if is_adult(meta) and not ask_to_continue(meta, f"Pornography is not allowed at {self.tracker}."):
            return False

        return should_continue

    async def get_name(self, meta: Meta) -> dict[str, Any]:
        lume_name = str(meta.get("name", ""))
        tag_value = str(meta.get("tag", ""))
        normalized_tag = tag_value.strip("-").strip().lower()
        invalid_tag_set = {"nogrp", "nogroup", "unknown", "unk"}

        if tag_value == "" or normalized_tag in invalid_tag_set:
            lume_name = re.sub(r"-(?:nogrp|nogroup|unknown|unk)(?=$|-)", "", lume_name, flags=re.IGNORECASE)
            lume_name = f"{lume_name}-NOGROUP"

        return {"name": lume_name}
