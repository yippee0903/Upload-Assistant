# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any, Optional

from src.console import console
from src.trackers.COMMON import COMMON
from src.trackers.UNIT3D import UNIT3D

Meta = dict[str, Any]
Config = dict[str, Any]


class LST(UNIT3D):
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

        # Block micro-encodes: check minimum video bitrate for ENCODE / WEBRIP / WEBDL
        if meta.get("type", "").upper() in ("ENCODE", "WEBRIP", "WEBDL"):
            video_encode = str(meta.get("video_encode", "")).strip().lower()
            resolution_text = str(meta.get("resolution", "")).lower().replace("p", "").replace("i", "")
            resolution = int(resolution_text) if resolution_text.isdigit() else 0

            MIN_BITRATE: dict[tuple[str, int], int] = {
                ("x265", 2160): 3_000_000,
                ("x265", 1080): 1_000_000,
                ("x265", 720): 600_000,
                ("x264", 2160): 8_000_000,
                ("x264", 1080): 2_000_000,
                ("x264", 720): 1_000_000,
            }

            codec_key = None
            if "x265" in video_encode or "h.265" in video_encode or "hevc" in video_encode:
                codec_key = "x265"
            elif "x264" in video_encode or "h.264" in video_encode or "avc" in video_encode:
                codec_key = "x264"

            # Fail-closed: block if codec or resolution is unrecognised
            if not codec_key or not resolution:
                if not meta.get("unattended", False):
                    console.print(f"[bold red]{self.tracker}: Cannot verify encode quality — unrecognised codec or resolution.[/bold red]")
                return False

            rule_key = (codec_key, resolution)
            min_bps = MIN_BITRATE.get(rule_key)

            # Fail-closed: block if no rule exists for this codec/resolution combination
            if not min_bps:
                if not meta.get("unattended", False):
                    console.print(f"[bold red]{self.tracker}: Cannot verify encode quality — no bitrate rule for {resolution}p {codec_key.upper()}.[/bold red]")
                return False

            mediainfo = meta.get("mediainfo", {})
            tracks = mediainfo.get("media", {}).get("track", [])
            video_bitrate = 0
            for track in tracks:
                if track.get("@type") == "Video":
                    br = track.get("BitRate")
                    if br and str(br).isdigit():
                        video_bitrate = int(br)
                    break

            # Fail-closed: block if bitrate is missing or unreadable
            if not video_bitrate:
                if not meta.get("unattended", False):
                    console.print(f"[bold red]{self.tracker}: Cannot verify encode quality — video bitrate missing from mediainfo.[/bold red]")
                return False

            if video_bitrate < min_bps:
                if not meta.get("unattended", False):
                    console.print(
                        f"[bold red]{self.tracker}: Micro-encode detected — video bitrate {video_bitrate // 1000} kb/s "
                        f"is below the minimum {min_bps // 1000} kb/s for {resolution}p {codec_key.upper()}.[/bold red]"
                    )
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
