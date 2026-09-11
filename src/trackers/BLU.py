# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import os
import re
from typing import Any, Optional

import cli_ui

from src.console import console
from src.trackers.COMMON import COMMON, ask_to_continue, is_lossless, mi_tracks
from src.trackers.UNIT3D import UNIT3D


class BLU(UNIT3D):
    REGION_IDS = {"CZE": "244", "SVK": "245", "FIN": "246", "SWE": "247", "BGR": "248", "DNK": "249"}

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config, tracker_name="BLU")
        self.config = config
        self.common = COMMON(config)
        self.tracker = "BLU"
        self.base_url = "https://blutopia.cc"
        self.id_url = f"{self.base_url}/api/torrents/"
        self.upload_url = f"{self.base_url}/api/torrents/upload"
        self.search_url = f"{self.base_url}/api/torrents/filter"
        self.requests_url = f"{self.base_url}/api/requests/filter"
        self.torrent_url = f"{self.base_url}/torrents/"
        self.banned_groups = [
            "[Oj]",
            "3LTON",
            "4yEo",
            "ADE",
            "AFG",
            "AniHLS",
            "AnimeRG",
            "AniURL",
            "AROMA",
            "ATM05",
            "aXXo",
            "B3LLUM",
            "BHDStudio",
            "BitHD",
            "Brrip",
            "CHD",
            "CM8",
            "CrEwSaDe",
            "d3g",
            "DeadFish",
            "D3US",
            "DNL",
            "DTLegacy",
            "ELiTE",
            "eSc",
            "EZTV",
            "EZTV.RE",
            "F13",
            "FaNGDiNG0",
            "FGT",
            "Flights",
            "flower",
            "FRDS",
            "FUM",
            "HAiKU",
            "hallowed",
            "HD2DVD",
            "HDS",
            "HDTime",
            "Hi10",
            "ION10",
            "iPlanet",
            "JIVE",
            "KiNGDOM",
            "LAMA",
            "Leffe",
            "LEGi0N",
            "LOAD",
            "mAck",
            "MeGusta",
            "mHD",
            "mSD",
            "NhaNc3",
            "nHD",
            "nikt0",
            "NOIVTC",
            "nSD",
            "OFT",
            "PAAI",
            "PHOCiS",
            "PiRaTeS",
            "playBD",
            "PlaySD",
            "playXD",
            "PMi",
            "PrimeFix",
            "PRODJi",
            "RAPiDCOWS",
            "RARBG",
            "RetroPeeps",
            "RDN",
            "REsuRRecTioN",
            "RMTeam",
            "SANTi",
            "SasukeducK",
            "SicFoI",
            "SPASM",
            "SPDVD",
            "STUTTERSHIT",
            "Telly",
            "TheFarm",
            "TM",
            "TRiToN",
            "UPiNSMOKE",
            "URANiME",
            "VN_Foxcore",
            "WAF",
            "WKS",
            "x0r",
            "XDMovies",
            "xRed",
            "XS",
            "YIFY",
            "ZKBL",
            "ZmN",
            "ZMNT",
        ]
        pass

    DERIVED_DV_ALERT = (
        "[alert]This release contains a Derived Dolby Vision layer. The WEB Dolby Vision layer was injected using dovi_tool. "
        "Mismatches between Blu-ray and WEB stream masters may occur.[/alert]\n\n"
    )

    # A file name marking bonus material, as a whole word between name separators.
    _EXTRA_MARKER = re.compile(r"(?:^|[.\s_-])(?:extras?|bonus|featurettes?|making[.\s_-]?of|deleted[.\s_-]?scenes?)(?=[.\s_-]|$)", re.IGNORECASE)

    @classmethod
    def _extras_in_pack(cls, meta: dict[str, Any]) -> list[str]:
        """Extras mixed with the main content of a multi-file upload. An extras-only upload is fine."""
        names = [os.path.basename(str(f)) for f in meta.get("filelist") or []]
        if len(names) < 2:
            return []
        extras = [n for n in names if cls._EXTRA_MARKER.search(os.path.splitext(n)[0])]
        return extras if len(extras) < len(names) else []

    async def get_additional_checks(self, meta: dict[str, Any]) -> bool:
        should_continue = True
        hdr = meta.get("hdr") or ""
        is_encode = meta["type"] in ["ENCODE", "WEBRIP"]
        is_animated = "animation" in meta.get("keywords", "") or meta.get("anime", False) is True

        if not meta.get("is_disc"):
            container = meta.get("container", "").lower()
            type_name = meta.get("type", "").upper()
            allowed = ["mkv"]
            if type_name == "HDTV":
                allowed.append("ts")
            if type_name in ["WEBDL", "HDTV"] and "DV" in hdr and "HDR" not in hdr:
                allowed.append("mp4")

            if container not in allowed:
                console.print(f"[bold red]For this release, {self.tracker} requires one of the following containers: {', '.join([a.upper() for a in allowed])}[/bold red]")
                return False

            if is_encode and meta["resolution"] not in ["720p", "1080p", "2160p"]:
                console.print(f"[bold red]Encodes must be 720p, 1080p or 2160p, skipping {self.tracker} upload.[/bold red]")
                return False

            if is_encode and meta["video_codec"] == "AV1":
                console.print(f"[bold red]Encodes must use x264 or x265, skipping {self.tracker} upload.[/bold red]")
                return False

            if (
                is_encode
                and meta["video_codec"] == "HEVC"
                and not hdr
                and not is_animated
                and not ask_to_continue(meta, f"SDR live-action encodes must use x264. ({self.tracker})")
            ):
                return False

            if "Hi10P" in meta.get("video_encode", "") and not is_animated and not ask_to_continue(meta, f"Hi10P is only allowed for anime. ({self.tracker})"):
                return False

            if not await self.common.check_language_requirements(
                meta, self.tracker, languages_to_check=["english"], check_audio=True, check_subtitle=True, original_language=True, original_required=True
            ):
                return False

            if meta.get("non_disc_has_pcm_audio_tracks", False):
                console.print(f"[bold red]PCM audio is not allowed outside discs, skipping {self.tracker} upload.[/bold red]")
                return False

            if meta.get("has_disallowed_compat_track", False) and not ask_to_continue(
                meta, f"This release contains a compatibility audio track which is not allowed. Only TrueHD audio tracks may include a compatibility track. ({self.tracker})"
            ):
                return False

            if not self._check_audio_tracks(meta):
                return False

        extras = self._extras_in_pack(meta)
        if extras and not ask_to_continue(meta, f"Extras must be their own upload, not mixed with the main content: {', '.join(extras)} ({self.tracker})"):
            return False

        if max(len(meta.get("image_list", [])), int(meta.get("screens", 0) or 0)) < 3:
            console.print(f"[bold red]At least 3 screenshots are required, skipping {self.tracker} upload.[/bold red]")
            return False

        if meta["type"] in ["ENCODE", "REMUX"] and "HDR" in hdr and "DV" in hdr:
            derived = bool(meta.get("webdv"))
            if not derived and (not meta["unattended"] or meta.get("unattended_confirm", False)):
                derived = bool(cli_ui.ask_yes_no("Is the Dolby Vision layer derived from a different source (WEB)?", default=False))
            if derived:
                if not ask_to_continue(
                    meta,
                    f"Derived Dolby Vision releases go to FANRES and the description must include the HDR grade check, DV plots, DV source, metafier log and dovi_tool summary. ({self.tracker})",
                ):
                    return False
                meta["tracker_status"][self.tracker]["other"] = True

        if (
            meta["type"] not in ["WEBDL"]
            and not meta["is_disc"]
            and str(meta.get("tag") or "").lstrip("-") in ["AOC", "CMRG", "EVO", "TERMiNAL", "ViSION"]
            and not ask_to_continue(meta, f"Group {meta['tag']} is only allowed for raw type content")
        ):
            return False

        if not meta["valid_mi_settings"]:
            console.print(f"[bold red]No encoding settings in mediainfo, skipping {self.tracker} upload.[/bold red]")
            return False

        return should_continue

    def _check_audio_tracks(self, meta: dict[str, Any]) -> bool:
        tracks = mi_tracks(meta, "Audio")
        ac3_langs = {str(t.get("Language") or "").lower() for t in tracks if t.get("Format") == "AC-3"}
        for i, track in enumerate(tracks):
            fmt = str(track.get("Format") or "")
            try:
                channels = int(track.get("Channels_Original") or track.get("Channels") or 0)
            except (TypeError, ValueError):
                channels = 0
            if fmt in ("Opus", "Vorbis"):
                console.print(f"[bold red]{fmt} audio is not allowed, skipping {self.tracker} upload.[/bold red]")
                return False
            if fmt == "FLAC" and channels > 2 and not (meta.get("anime", False) is True and channels <= 6):
                console.print(f"[bold red]FLAC is only accepted for mono or stereo audio, skipping {self.tracker} upload.[/bold red]")
                return False
            if fmt == "AAC" and channels > 2 and meta["type"] not in ("WEBDL", "HDTV"):
                console.print(f"[bold red]AAC is only accepted for mono or stereo audio unless untouched, skipping {self.tracker} upload.[/bold red]")
                return False
            if fmt == "MLP FBA" and str(track.get("Language") or "").lower() not in ac3_langs:
                console.print(f"[bold red]Every TrueHD track needs a standalone AC-3 compatibility track, skipping {self.tracker} upload.[/bold red]")
                return False
            if i == 0 and meta["type"] == "ENCODE" and meta["resolution"] == "2160p" and not is_lossless(track):
                console.print(f"[bold red]2160p encodes must have lossless main audio, skipping {self.tracker} upload.[/bold red]")
                return False
        return True

    async def get_description(self, meta: dict[str, Any]) -> dict[str, str]:
        desc = (await super().get_description(meta))["description"]
        if meta["tracker_status"][self.tracker].get("other", False):
            desc = self.DERIVED_DV_ALERT + desc
        return {"description": desc}

    async def get_name(self, meta: dict[str, Any]) -> dict[str, str]:
        blu_name = meta["name"]
        if meta["category"] == "TV" and meta.get("episode_title", "") != "":
            blu_name = blu_name.replace(f"{meta['episode_title']} {meta['resolution']}", f"{meta['resolution']}", 1)
        imdb_name = meta.get("imdb_info", {}).get("title", "")
        imdb_year = str(meta.get("imdb_info", {}).get("year", ""))
        imdb_aka = meta.get("imdb_info", {}).get("aka", "")
        year = str(meta.get("year", ""))
        aka = meta.get("aka", "")
        if imdb_name and imdb_name.strip():
            if aka:
                blu_name = blu_name.replace(f"{aka} ", "", 1)
            blu_name = blu_name.replace(f"{meta['title']}", imdb_name, 1)

            if imdb_aka and imdb_aka.strip() and imdb_aka != imdb_name and not meta.get("no_aka", False):
                blu_name = blu_name.replace(f"{imdb_name}", f"{imdb_name} AKA {imdb_aka}", 1)

        if meta.get("category") != "TV" and imdb_year and imdb_year.strip() and year and year.strip() and imdb_year != year:
            blu_name = blu_name.replace(f"{year}", imdb_year, 1)

        if meta["type"] == "WEBDL":
            blu_name = blu_name.replace("Hybrid ", "", 1)

        return {"name": blu_name}

    async def get_additional_data(self, meta: dict[str, Any]) -> dict[str, Any]:
        data = {
            "mod_queue_opt_in": await self.get_flag(meta, "modq"),
        }

        return data

    async def get_category_id(
        self,
        meta: dict[str, Any],
        category: Optional[str] = None,
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        edition = meta.get("edition", "")
        category_name = meta["category"]
        category_id = {"MOVIE": "1", "TV": "2", "FANRES": "3"}

        is_fanres = False

        if category_name == "MOVIE" and "FANRES" in edition:
            is_fanres = True

        if meta["tracker_status"][self.tracker].get("other", False):
            is_fanres = True

        if is_fanres:
            return {"category_id": "3"}

        if mapping_only:
            return category_id
        elif reverse:
            return {v: k for k, v in category_id.items()}
        elif category is not None:
            return {"category_id": category_id.get(category, "0")}
        else:
            meta_category = meta.get("category", "")
            resolved_id = category_id.get(meta_category, "0")
            return {"category_id": resolved_id}

    async def get_type_id(
        self,
        meta: dict[str, Any],
        type: Optional[str] = None,
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        type_id = {"DISC": "1", "REMUX": "3", "WEBDL": "4", "WEBRIP": "5", "HDTV": "6", "ENCODE": "12"}

        if mapping_only:
            return type_id
        elif reverse:
            return {v: k for k, v in type_id.items()}
        elif type is not None:
            return {"type_id": type_id.get(type, "0")}
        else:
            meta_type = meta.get("type", "")
            resolved_id = type_id.get(meta_type, "0")
            return {"type_id": resolved_id}

    async def get_resolution_id(
        self,
        meta: dict[str, Any],
        resolution: Optional[str] = None,
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        resolution_id = {"8640p": "10", "4320p": "11", "2160p": "1", "1440p": "2", "1080p": "2", "1080i": "3", "720p": "5", "576p": "6", "576i": "7", "480p": "8", "480i": "9"}
        if mapping_only:
            return resolution_id
        elif reverse:
            return {v: k for k, v in resolution_id.items()}
        elif resolution is not None:
            return {"resolution_id": resolution_id.get(resolution, "10")}
        else:
            meta_resolution = meta.get("resolution", "")
            resolved_id = resolution_id.get(meta_resolution, "10")
            return {"resolution_id": resolved_id}
