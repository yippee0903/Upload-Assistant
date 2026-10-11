# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any, Optional

from src.console import console
from src.trackers.COMMON import COMMON, ask_to_continue, min_video_bitrate
from src.trackers.UNIT3D import UNIT3D

Meta = dict[str, Any]
Config = dict[str, Any]


class LST(UNIT3D):
    REGION_IDS = {"CZE": "244", "FIN": "245", "SWE": "246"}

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name="LST")
        self.config: Config = config
        self.common = COMMON(config)
        self.tracker = "LST"
        self.base_url = "https://lst.gg"
        self.banned_url = f"{self.base_url}/api/bannedReleaseGroups"
        self.id_url = f"{self.base_url}/api/torrents/"
        self.upload_url = f"{self.base_url}/api/torrents/upload"
        self.search_url = f"{self.base_url}/api/torrents/filter"
        self.torrent_url = f"{self.base_url}/torrents/"
        self.trumping_url = f"{self.base_url}/api/reports/torrents/"
        self.banned_groups = []
        pass

    skip_nfo: bool = True

    async def get_additional_files(self, meta: Meta) -> dict[str, tuple[str, bytes, str]]:
        return {}

    async def get_additional_checks(self, meta: Meta) -> bool:
        should_continue = True
        if not meta["valid_mi_settings"]:
            console.print(f"[bold red]No encoding settings in mediainfo, skipping {self.tracker} upload.[/bold red]")
            return False

        if meta["is_disc"] not in ["BDMV", "DVD"] and not await self.common.check_language_requirements(
            meta, self.tracker, languages_to_check=["english"], check_audio=True, check_subtitle=True, original_language=True
        ):
            return False

        # Block micro-encodes: minimum video bitrate for ENCODE / WEBRIP, from the
        # table shared with TOS and BLU (no rule for the codec/resolution = no check).
        # WEB-DL is exempt: it's the service's untouched stream, whatever its
        # bitrate — never a micro-encode.
        rule = min_video_bitrate(meta, "ENCODE") if meta.get("type", "").upper() in ("ENCODE", "WEBRIP") else None
        if rule:
            label, min_kbps, kbps = rule
            if kbps is None and not ask_to_continue(meta, f"{self.tracker}: Cannot verify encode quality — video bitrate missing from mediainfo."):
                return False

            if (
                kbps is not None
                and kbps < min_kbps
                and not ask_to_continue(
                    meta,
                    f"{self.tracker}: Micro-encode detected — video bitrate {int(kbps)} kb/s is below the minimum {min_kbps} kb/s for {meta.get('resolution')} {label}.",
                )
            ):
                return False

        return should_continue

    async def get_type_id(self, meta: Meta, type: Optional[str] = None, reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        _ = (reverse, mapping_only)
        type = str(meta.get("type", "")).upper()
        type_id = {"DISC": "1", "REMUX": "2", "WEBDL": "4", "WEBRIP": "5", "HDTV": "6", "ENCODE": "3", "DVDRIP": "3"}.get(type, "0")
        return {"type_id": type_id}

    async def get_additional_data(self, meta: Meta) -> dict[str, Any]:
        data: dict[str, Any] = {
            "mod_queue_opt_in": await self.get_flag(meta, "modq"),
            "draft_queue_opt_in": await self.get_flag(meta, "draft"),
        }

        # Only add edition_id if we have a valid edition
        edition_id = await self.get_edition(meta)
        if edition_id is not None:
            data["edition_id"] = edition_id

        return data

    async def get_edition(self, meta: Meta) -> Optional[int]:
        edition_mapping = {
            "Alternative Cut": 12,
            "Collector's Edition": 1,
            "Director's Cut": 2,
            "Extended Cut": 3,
            "Extended Uncut": 4,
            "Extended Unrated": 5,
            "Limited Edition": 6,
            "Special Edition": 7,
            "Theatrical Cut": 8,
            "Uncut": 9,
            "Unrated": 10,
            "X Cut": 11,
            "Other": 0,  # Default value for "Other"
        }
        edition = meta.get("edition", "")
        if edition in edition_mapping:
            return edition_mapping[edition]
        else:
            return None

    async def get_name(self, meta: Meta) -> dict[str, str]:
        lst_name = str(meta.get("name", ""))
        resolution = str(meta.get("resolution", ""))
        video_encode = str(meta.get("video_encode", ""))
        name_type = meta.get("type", "")

        if name_type == "DVDRIP":
            if meta.get("category") == "MOVIE":
                lst_name = lst_name.replace(f"{meta.get('source', '')}{meta.get('video_encode', '')}", f"{resolution}", 1)
                lst_name = lst_name.replace(str(meta.get("audio", "")), f"{meta.get('audio', '')}{video_encode}", 1)
            else:
                lst_name = lst_name.replace(str(meta.get("source", "")), f"{resolution}", 1)
                lst_name = lst_name.replace(str(meta.get("video_codec", "")), f"{meta.get('audio', '')} {meta.get('video_codec', '')}", 1)

        # For TV: only keep the year if TVDB itself has a year in the series name.
        # e.g. TVDB "Shameless (2011)" → keep year; TVDB "Shameless" → strip year.
        if meta.get("category") == "TV":
            tvdb_series_name = str(meta.get("tvdb_series_name") or "")
            tvdb_has_year = bool(re.search(r"\b(19|20)\d{2}\b", tvdb_series_name))
            if not tvdb_has_year:
                lst_name = re.sub(r"\s+\b(19|20)\d{2}\b", "", lst_name, count=1)
                lst_name = re.sub(r"\s{2,}", " ", lst_name).strip()

        if meta.get("trump_reason") == "exact_match":
            lst_name = lst_name + " - TRUMP"

        return {"name": lst_name}
