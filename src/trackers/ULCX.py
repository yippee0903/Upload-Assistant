# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any

import aiofiles

from src.console import console
from src.get_desc import DescriptionBuilder
from src.trackers.COMMON import ask_to_continue, is_adult, is_lossless, is_lossless_dts, mi_tracks
from src.trackers.UNIT3D import UNIT3D

Meta = dict[str, Any]
Config = dict[str, Any]


class ULCX(UNIT3D):
    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name="ULCX")
        self.config = config
        self.tracker = "ULCX"
        self.base_url = "https://upload.cx"
        self.id_url = f"{self.base_url}/api/torrents/"
        self.upload_url = f"{self.base_url}/api/torrents/upload"
        self.requests_url = f"{self.base_url}/api/requests/filter"
        self.search_url = f"{self.base_url}/api/torrents/filter"
        self.torrent_url = f"{self.base_url}/torrents/"
        self.banned_groups = [
            "4K4U",
            "AROMA",
            "d3g",
            ["EDGE2020", "Encodes"],
            "EMBER",
            "FGT",
            "FnP",
            "FRDS",
            "Grym",
            "Hi10",
            "iAHD",
            "INFINITY",
            "ION10",
            "iVy",
            "Judas",
            "LAMA",
            "MeGusta",
            "NAHOM",
            "Niblets",
            "nikt0",
            ["NuBz", "Encodes"],
            "OFT",
            "QxR",
            ["Ralphy", "Encodes"],
            "RARBG",
            "Sicario",
            "SM737",
            "SPDVD",
            "SWTYBLZ",
            "TAoE",
            "TGx",
            "Tigole",
            "TSP",
            "TSPxL",
            "VXT",
            "Vyndros",
            "Will1869",
            "x0r",
            "YIFY",
            "Alcaide_Kira",
            "PHOCiS",
            "HDT",
            "SPx",
            "seedpool",
        ]
        pass

    skip_nfo: bool = True

    async def get_additional_files(self, meta: Meta) -> dict[str, tuple[str, bytes, str]]:
        return {}

    async def get_additional_checks(self, meta: Meta) -> bool:
        should_continue = True
        is_animated = "animation" in meta["keywords"] or meta.get("anime", False) is True
        if "concert" in meta["keywords"] and not ask_to_continue(meta, f"Concerts are not allowed. ({self.tracker})"):
            return False
        if (
            meta["video_codec"] == "HEVC"
            and meta["resolution"] != "2160p"
            and not is_animated
            and not ask_to_continue(meta, f"This content might not fit the HEVC rules. ({self.tracker})")
        ):
            return False
        if meta["type"] in ["ENCODE", "HDTV"] and meta["resolution"] not in ["8640p", "4320p", "2160p", "1440p", "1080p", "1080i", "720p"]:
            if meta["type"] == "HDTV" and not ask_to_continue(
                meta, f"SD broadcasts are only accepted when the content was never released in HD or on disc/WEB. ({self.tracker})"
            ):
                return False
            if meta["type"] == "ENCODE":
                if not meta["unattended"]:
                    console.print(f"[bold red]Encodes must be at least 720p resolution for {self.tracker}.[/bold red]")
                return False

        if meta["type"] in ["DVDRIP"]:
            if not meta["unattended"]:
                console.print(f"[bold red]DVDRIPs are not allowed for {self.tracker}.[/bold red]")
            return False

        if meta["is_disc"] != "BDMV" and not await self.common.check_language_requirements(
            meta, self.tracker, languages_to_check=["english"], check_audio=True, check_subtitle=True
        ):
            return False

        if not meta["valid_mi_settings"]:
            console.print(f"[bold red]No encoding settings in mediainfo, skipping {self.tracker} upload.[/bold red]")
            return False

        if meta.get("personalrelease", False):
            if meta.get("has_multiple_default_audio_tracks", False):
                console.print(f"[bold red]Multiple default audio tracks detected, skipping {self.tracker} upload.[/bold red]")
                return False

            if meta.get("has_multiple_default_subtitle_tracks", False):
                console.print(f"[bold red]Multiple default subtitle tracks detected, skipping {self.tracker} upload.[/bold red]")
                return False

        if meta.get("non_disc_has_pcm_audio_tracks", False):
            console.print(f"[bold red]Non-disc source with PCM audio tracks detected, skipping {self.tracker} upload.[/bold red]")
            return False

        if meta.get("has_disallowed_compat_track", False) and not ask_to_continue(
            meta, f"This release contains a compatibility audio track which is not allowed. Only TrueHD audio tracks may include a compatibility track. ({self.tracker})"
        ):
            return False

        if meta.get("discs_missing_certificate", []):
            console.print(f"[bold red]Disc source(s) missing BD certificate, skipping {self.tracker} upload.[/bold red]")
            return False

        if meta.get("type") in ("WEBDL", "WEBRIP") and not meta.get("service", ""):
            if not meta["unattended"] or meta["debug"]:
                console.print(f"[bold red]Streaming service is missing, skipping {self.tracker} upload.[/bold red]")
            return False

        if not int(meta.get("tmdb_id") or 0):
            console.print(f"[bold red]No TMDB match, skipping {self.tracker} upload.[/bold red]")
            return False

        if meta["video_codec"] == "AV1" and not is_animated and not ask_to_continue(meta, f"AV1 is only accepted for animated content. ({self.tracker})"):
            return False

        if not meta["is_disc"]:
            bad_ext = [f for f in meta.get("filelist", []) if not f.lower().endswith(".mkv") and not (meta["type"] == "HDTV" and f.lower().endswith(".ts"))]
            if bad_ext:
                console.print(f"[bold red]Only .mkv files are accepted (.ts for HDTV), skipping {self.tracker} upload.[/bold red]")
                return False
            if not self._check_audio_tracks(meta):
                return False

        if len(meta.get("image_list", [])) < 3:
            console.print(f"[bold red]At least 3 screenshots are required, skipping {self.tracker} upload.[/bold red]")
            return False

        # Strong recommendations: mandatory for personal releases, a warning otherwise.
        for failed, msg in self._personal_release_checks(meta):
            if not failed:
                continue
            if meta.get("personalrelease", False):
                console.print(f"[bold red]{msg} Skipping {self.tracker} upload.[/bold red]")
                return False
            console.print(f"[yellow]{self.tracker}: {msg} A release that complies may trump this one.[/yellow]")

        return should_continue

    def _check_audio_tracks(self, meta: Meta) -> bool:
        for track in mi_tracks(meta, "Audio"):
            fmt = str(track.get("Format") or "")
            try:
                channels = int(track.get("Channels_Original") or track.get("Channels") or 0)
            except (TypeError, ValueError):
                channels = 0
            if fmt == "FLAC" and channels > 2:
                console.print(f"[bold red]FLAC is only accepted for mono or stereo audio, skipping {self.tracker} upload.[/bold red]")
                return False
            if not is_lossless(track):
                continue
            if meta["type"] == "ENCODE" and channels >= 3 and meta["resolution"] not in ("2160p", "4320p", "8640p"):
                console.print(f"[bold red]Lossless multi-channel audio is not accepted on 1080p or lower encodes, skipping {self.tracker} upload.[/bold red]")
                return False
            if meta["type"] == "REMUX":
                is_dtshd_ma = is_lossless_dts(track)
                if channels == 1 and fmt != "FLAC" and not is_dtshd_ma:
                    console.print(f"[bold red]Lossless mono audio must be FLAC or DTS-HD MA on remuxes, skipping {self.tracker} upload.[/bold red]")
                    return False
                if channels == 2 and fmt != "FLAC":
                    console.print(f"[bold red]Lossless stereo audio must be FLAC on remuxes, skipping {self.tracker} upload.[/bold red]")
                    return False
                if channels >= 3 and fmt != "MLP FBA" and not is_dtshd_ma:
                    console.print(f"[bold red]Lossless multi-channel audio must be DTS-HD MA or TrueHD on remuxes, skipping {self.tracker} upload.[/bold red]")
                    return False
            if meta["type"] == "WEBDL" and channels >= 3 and not meta["unattended"]:
                console.print(f"[yellow]{self.tracker}: a WEB-DL with lossless multi-channel audio needs video comparisons against the remux in its description.[/yellow]")
        return True

    def _personal_release_checks(self, meta: Meta) -> list[tuple[bool, str]]:
        general = mi_tracks(meta, "General")
        encoder = " ".join(f"{t.get('Encoded_Application') or ''} {t.get('Encoded_Library') or ''} {(t.get('extra') or {}).get('Writing_frontend') or ''}" for t in general)
        original_language = str(meta.get("original_language") or "").lower()
        foreign = bool(original_language) and not original_language.startswith("en")
        default_subs = [str(t.get("Language") or "").lower() for t in mi_tracks(meta, "Text") if t.get("Default") == "Yes"]
        return [
            (meta["type"] == "ENCODE" and "handbrake" in encoder.lower(), "HandBrake encodes are discouraged."),
            ("Dubbed" in meta.get("audio", ""), "Foreign content should keep the original audio track alongside the dub."),
            (foreign and bool(default_subs) and not any(lang.startswith("en") for lang in default_subs), "English subtitles should be the default track on foreign content."),
            (original_language.startswith("en") and bool(default_subs), "No subtitle track should be marked default on English content."),
        ]

    async def get_additional_data(self, meta: Meta) -> dict[str, Any]:
        data = {
            "mod_queue_opt_in": await self.get_flag(meta, "modq"),
        }

        return data

    async def get_description(self, meta: Meta) -> dict[str, str]:
        desc = await DescriptionBuilder(self.tracker, self.config).unit3d_edit_desc(meta, comparison=True)

        if is_adult(meta):
            pattern = r"(\[center\](?:(?!\[/center\]).)*\[/center\])"

            def wrap_in_spoiler(match: re.Match[str]) -> str:
                center_block = match.group(1)
                if "[img" not in center_block.lower():
                    return center_block
                return f"[center][spoiler=Screenshots]{center_block}[/spoiler][/center]"

            desc = re.sub(pattern, wrap_in_spoiler, desc, flags=re.DOTALL)
            async with aiofiles.open(f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}]DESCRIPTION.txt", "w", encoding="utf-8") as f:
                await f.write(desc)

        return {"description": desc}

    async def get_name(self, meta: Meta) -> dict[str, str]:
        ulcx_name = meta["name"]
        imdb_name = meta.get("imdb_info", {}).get("title", "")
        imdb_year = str(meta.get("imdb_info", {}).get("year", ""))
        imdb_aka = meta.get("imdb_info", {}).get("aka", "")
        year = str(meta.get("year", ""))
        aka = meta.get("aka", "")
        if imdb_name and imdb_name.strip():
            if aka:
                ulcx_name = ulcx_name.replace(f"{aka} ", "", 1)
            ulcx_name = ulcx_name.replace(f"{meta['title']}", imdb_name, 1)
            if imdb_aka and imdb_aka.strip() and imdb_aka.casefold() != imdb_name.casefold() and not meta.get("no_aka", False) and not meta.get("anime", False):
                ulcx_name = ulcx_name.replace(f"{imdb_name}", f"{imdb_name} AKA {imdb_aka}", 1)
        if ("Hybrid" in ulcx_name or "Custom" in ulcx_name) and meta.get("type") == "WEBDL":
            ulcx_name = ulcx_name.replace("Hybrid ", "", 1)
            ulcx_name = ulcx_name.replace("Custom ", "", 1)
        if meta.get("category") != "TV" and imdb_year and imdb_year.strip() and year and year.strip() and imdb_year != year:
            ulcx_name = ulcx_name.replace(f"{year}", imdb_year, 1)

        return {"name": ulcx_name}
