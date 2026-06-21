# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
"""
https://nexum-core.com/ — French private tracker (custom REST API)

Upload endpoint:  POST  https://nexum-core.com/api/v1/upload
Authentication:   Header X-API-Key
Content-Type:     multipart/form-data

Required fields:  torrent, nfo, name, category_id, tmdb_id, tmdb_type
Optional fields:  description

API docs from:
  https://nexum-core.com/api/docs
"""

import asyncio
import json
import os
import re
from typing import Any, Union

import aiofiles
import httpx
from unidecode import unidecode

from src.console import console
from src.get_desc import DescriptionBuilder
from src.nfo_generator import SceneNfoGenerator
from src.tmdb import TmdbManager
from src.trackers.COMMON import COMMON
from src.trackers.FRENCH import FrenchTrackerMixin

Meta = dict[str, Any]
Config = dict[str, Any]


class NXM(FrenchTrackerMixin):
    """nexum-core.com tracker — French private tracker with custom API."""

    notag_label: str = "NoGrp"

    # Overloading TORRENT_EXTENSIONS to add .nfo
    _TORRENT_EXTENSIONS: frozenset[str] = frozenset((".mkv", ".mp4", ".ts", ".m2ts", ".vob", ".avi", ".nfo"))

    def __init__(self, config: Config) -> None:
        self.config: Config = config
        self.common = COMMON(config)
        self.tracker: str = "NXM"
        self.source_flag: str = "NXM"
        self.base_url: str = "https://nexum-core.com/"
        self.upload_url: str = "https://nexum-core.com/api/v1/upload"
        self.torrent_url: str = "https://nexum-core.com/torrents/"
        self.search_url: str = "https://nexum-core.com/api/v1/torrents/"
        self.api_key: str = str(self.config["TRACKERS"].get(self.tracker, {}).get("api_key", "")).strip()
        self.tmdb_manager = TmdbManager(config)
        self.banned_groups: list[str] = [
            "ACOOL",
            "AKLHD",
            "ALIOZ",
            "ANONA",
            "ARKAS",
            "ARKRIL",
            "ASPHIXIAS",
            "AT",
            "AVITECH",
            "AZAZE",
            "BAGUETTE",
            "BALIBALO",
            "BANDIX",
            "BIGZT",
            "BLABLASTREAM",
            "BOHEME",
            "BOL",
            "BOSSBABY",
            "CHAMPION9",
            "CINEHD",
            "COPYCOMIC",
            "CORTEX91",
            "CPASBIEN",
            "CPB",
            "CR4ZYTIME",
            "CZ530",
            "D0LL4R",
            "DDLFRENCH",
            "DDLFRENCHORG",
            "DOLL4R",
            "DREADTEAM",
            "DROPSE",
            "EASPORTS",
            "ELITET",
            "EXTREME",
            "EZTV",
            "EZTVRE",
            "FGT",
            "FIRETOWN",
            "FLOP",
            "FLY3R",
            "FREEZER",
            "FUN",
            "FUNKKY",
            "FYR3N",
            "FZTEAM",
            "GAÏA",
            "GHOSTSPIRIT",
            "GHZ",
            "GLADOS",
            "GOBO2S",
            "GZR",
            "HD2",
            "HDMIDIMADRIDI",
            "HEVCBAY",
            "HMIDIMADRIDI",
            "HUSH",
            "JETANIME",
            "JIHEFF",
            "K0RE",
            "KATAIRI",
            "KILLERMIX",
            "KR4K3N",
            "L-O-L",
            "L-OL",
            "LIBERTAD",
            "LION",
            "LMPS",
            "LNA3D",
            "LO-L",
            "LOL",
            "LTATM",
            "LTTM",
            "LUCKY",
            "MACK4",
            "MATMATHA",
            "MEMYL",
            "METALLIKA",
            "MGD",
            "MKVXTEAM",
            "MONCHAT",
            "MONICO",
            "MOOREA81",
            "MOVIZ",
            "MUXMAN",
            "MYSTIC",
            "MZC",
            "MZISYS",
            "MZSYS",
            "N3TFL1X",
            "NEWCINE",
            "NEWZT",
            "NG",
            "NLX5",
            "NOELMAISON",
            "NOMAD",
            "NORRIS",
            "NUTELLA",
            "OMERTA",
            "PICKLES",
            "PIKACHU",
            "PREUMS",
            "PULSE",
            "Q7",
            "QCTIMB3RLANDQC",
            "R3Z",
            "RARBG",
            "REBOT",
            "RELIC",
            "ROLLED",
            "RPZ",
            "RZP",
            "SANCTUAIRE",
            "SCREEN",
            "SHARKS",
            "SHIFT",
            "SHOWFR",
            "SKRIN",
            "SKS",
            "SP3CTR",
            "SPOW",
            "STR4NGE",
            "STVFRV",
            "SUBZERO",
            "SUNS3T",
            "T9",
            "TEAMSUW",
            "TICADOW",
            "TIME2WATCH",
            "TIREXO",
            "TOKUSHI",
            "TONYK",
            "TORRENT9",
            "TORRID",
            "TOXIC",
            "TSN999",
            "TUTUTE",
            "TVPSLO",
            "UNIKORN",
            "UPMIX",
            "VATFER",
            "VERCLAM",
            "VIKI47",
            "WAKANIM",
            "WANEZT",
            "WAWA",
            "WAWA-CITY",
            "WAWA-MANIA",
            "WAWA-PORNO",
            "WAWACITY",
            "WAWAMANIA",
            "WAWAPORNO",
            "WEBANIME",
            "WINCHESTER",
            "WITA",
            "YIFY",
            "YTS",
            "ZOMBIE",
            "ZONE",
            "ZT",
            "ZW",
        ]

    # ── FrenchTrackerMixin overrides ──────────────────────────────────

    PREFER_ORIGINAL_TITLE: bool = True
    UHD_ONLY_FOR_REMUX_DISC: bool = True

    # ──────────────────────────────────────────────────────────
    #  Audio / naming / French title — inherited from FrenchTrackerMixin
    # ──────────────────────────────────────────────────────────
    # _get_category — overridden below
    # ──────────────────────────────────────────────────────────

    # Sources explicitly forbidden by NXM rules (§2 / §3.7)
    _FORBIDDEN_SOURCES: frozenset[str] = frozenset({"DCP", "Screener", "DVD Screener", "WEB Screener", "Workprint"})

    async def get_additional_checks(self, meta: Meta) -> bool:
        # French language requirement (inherited base check)
        if not await super().get_additional_checks(meta):
            return False

        # §3.7 — DCP, Screener, Workprint interdits
        source = meta.get("source", "")
        if source in self._FORBIDDEN_SOURCES:
            if not meta.get("unattended") or meta.get("debug"):
                console.print(f"[bold red]NXM: source '{source}' est interdite (DCP / Screener / Workprint).[/bold red]")
            return False

        # §3.6 — Paramètres d'encodage obligatoires pour les encodes
        if meta.get("type") == "ENCODE" and not meta.get("valid_mi_settings"):
            if not meta.get("unattended") or meta.get("debug"):
                console.print("[bold red]NXM: paramètres d'encodage absents du MediaInfo — upload ignoré.[/bold red]")
            return False

        # SRT séparés interdits — doivent être encapsulés dans le MKV
        if meta.get("is_disc") not in ("BDMV", "DVD"):
            video_path = meta.get("path", "")
            directory = video_path if os.path.isdir(video_path) else os.path.dirname(video_path)
            if directory and os.path.isdir(directory):
                subtitle_extensions = (".srt", ".sub", ".ass", ".ssa", ".idx", ".smi", ".psb")
                if any(f.lower().endswith(subtitle_extensions) for f in os.listdir(directory)):
                    if not meta.get("unattended") or meta.get("debug"):
                        console.print("[bold red]NXM: fichiers de sous-titres séparés détectés — ils doivent être encapsulés dans le MKV.[/bold red]")
                    return False

        # §6 — Animés : lien AniDB / AniList / MAL obligatoire
        is_anime = bool(meta.get("anime")) or bool(meta.get("mal_id"))
        category = await self._get_category(meta)
        if category == 4 or is_anime:
            if not meta.get("mal_id") and not meta.get("anidb_id") and not meta.get("anilist_id"):
                if not meta.get("unattended") or meta.get("debug"):
                    console.print("[bold red]NXM: les animés requièrent un lien AniDB, AniList ou MAL (--mal, --anidb, --anilist).[/bold red]")
                return False

        return True

    async def _get_category(self, meta: Meta) -> int:
        """Return category id for NXM upload.

        { "id": 1, "name": "Films", "slug": "films" },
        { "id": 2, "name": "Séries TV", "slug": "series" },
        { "id": 3, "name": "Documentaires", "slug": "documentaires" },
        { "id": 4, "name": "Animés", "slug": "animes" },
        { "id": 5, "name": "Concerts / Spectacles", "slug": "concerts-spectacles" },
        { "id": 7, "name": "Sports", "slug": "sports" }
        """
        # Detect animation: anime flag, mal_id, or animation genre
        is_anime = bool(meta.get("anime")) or bool(meta.get("mal_id"))
        genres = str(meta.get("genres", "")).lower()
        keywords = str(meta.get("keywords", ""))

        if "concert" in genres.lower() or "concert" in keywords.lower():
            return 5
        elif "documentary" in genres.lower() or "documentary" in keywords.lower():
            return 3
        elif meta.get("category") == "TV":
            return 4 if is_anime else 2
        return 4 if is_anime else 1

    # ──────────────────────────────────────────────────────────
    #  Description builder (BBCode)
    # ──────────────────────────────────────────────────────────

    async def _build_description(self, meta: dict[str, Any]) -> str:
        """Build a concise BBCode description for NXM.

        NXM's torrent page already displays the poster, synopsis, genres,
        and quality badge.  The description therefore focuses on technical
        details, audio/subtitle tracks, release metadata, and screenshots.
        """
        parts: list[str] = ["[center]"]
        mi_text = await self._get_mediainfo_text(meta)

        # ── Informations techniques ──
        parts.append("[b]Informations techniques[/b]")
        tech: list[str] = []
        type_label = self._get_type_label(meta)
        if type_label:
            tech.append(f"[b]Type :[/b] {type_label}")
        source = meta.get("source", "") or meta.get("type", "")
        if source:
            tech.append(f"[b]Source :[/b] {source}")
        service = meta.get("service", "")
        if service:
            tech.append(f"[b]Service :[/b] {service}")
        resolution = meta.get("resolution", "")
        if resolution:
            tech.append(f"[b]Résolution :[/b] {resolution}")
        container = self._format_container(mi_text)
        if container:
            tech.append(f"[b]Format vidéo :[/b] {container}")
        video_codec = (meta.get("video_encode", "").strip() or meta.get("video_codec", "")).strip()
        video_codec = video_codec.replace("H.264", "H264").replace("H.265", "H265")
        raw_codec = meta.get("video_codec", "").strip()
        if video_codec and raw_codec and raw_codec != video_codec:
            video_codec = f"{video_codec} ({raw_codec})"
        if video_codec:
            tech.append(f"[b]Codec vidéo :[/b] {video_codec}")
        hdr_dv = self._format_hdr_dv_bbcode(meta)
        if hdr_dv:
            tech.append(f"[b]HDR :[/b] {hdr_dv}")
        if mi_text:
            vbr_m = re.search(r"(?:^|\n)Bit rate\s*:\s*(.+?)\s*(?:\n|$)", mi_text)
            if vbr_m:
                tech.append(f"[b]Débit vidéo :[/b] {vbr_m.group(1).strip()}")
        parts.extend(tech)
        parts.append("")

        # ── Audio(s) ──
        parts.append("[b]Audio(s)[/b]")
        audio_lines = self._format_audio_bbcode(mi_text, meta)
        if audio_lines:
            parts.extend(f"[i]{al}[/i]" for al in audio_lines)
        else:
            parts.append("[i]Non spécifié[/i]")
        parts.append("")

        # ── Sous-titre(s) ──
        parts.append("[b]Sous-titre(s)[/b]")
        sub_lines = self._format_subtitle_bbcode(mi_text, meta)
        if sub_lines:
            parts.extend(f"[i]{sl}[/i]" for sl in sub_lines)
        else:
            parts.append("[i]Aucun[/i]")
        parts.append("")

        # ── Release ──
        parts.append("[b]Release[/b]")
        size_str = self._get_total_size(meta, mi_text)
        if size_str:
            parts.append(f"[b]Taille totale :[/b] {size_str}")
        file_count = self._count_files(meta)
        if file_count:
            parts.append(f"[b]Nombre de fichier(s) :[/b] {file_count}")
        group = self._get_release_group(meta)
        if group:
            parts.append(f"[b]Groupe :[/b] {group}")
        personal_note = await DescriptionBuilder(self.tracker, self.config).get_personal_note(meta)
        if personal_note:
            parts.append(f"[b]Note :[/b] {personal_note}")
        parts.append("")

        # ── Captures d'écran ──
        include_screens = self.config["TRACKERS"].get(self.tracker, {}).get("include_screenshots", False)
        image_list: list[dict[str, Any]] = meta.get("image_list", []) if include_screens else []
        if image_list:
            parts.append("[b]Captures d'écran[/b][spoiler]")
            parts.append("")
            img_lines: list[str] = []
            for img in image_list:
                raw = img.get("raw_url", "")
                web = img.get("web_url", "")
                if raw:
                    img_lines.append(f"[url={web}][img]{raw}[/img][/url]" if web else f"[img]{raw}[/img]")
            if img_lines:
                parts.append("\n".join(img_lines))
            parts.append("[/spoiler]")
            parts.append("")

        parts.append("[/center]")

        # ── Signature ──
        ua_sig = meta.get("ua_signature", "Created by Upload Assistant")
        parts.append(f"[right][url=https://github.com/yippee0903/Upload-Assistant]{ua_sig}[/url][/right]")

        return "\n".join(parts)

    async def _get_mediainfo_text(self, meta: dict[str, Any]) -> str:
        """Read MediaInfo text from temp files."""
        base = os.path.join(meta.get("base_dir", ""), "tmp", meta.get("uuid", ""))
        for fname in ("MEDIAINFO_CLEANPATH.txt", "MEDIAINFO.txt"):
            fpath = os.path.join(base, fname)
            if os.path.exists(fpath):
                async with aiofiles.open(fpath, encoding="utf-8") as f:
                    content = await f.read()
                    if content.strip():
                        return content
        if meta.get("bdinfo") is not None:
            bd_path = os.path.join(base, "BD_SUMMARY_00.txt")
            if os.path.exists(bd_path):
                async with aiofiles.open(bd_path, encoding="utf-8") as f:
                    return await f.read()
        return str(meta.get("mediainfo_text") or "")

    # ──────────────────────────────────────────────────────────
    #  NFO generation - Same as C411
    #  Use original NFO else use mediainfo
    # ──────────────────────────────────────────────────────────

    async def _get_or_generate_nfo(self, meta: Meta) -> Union[str, None]:
        """Generate a MediaInfo-based NFO for the upload.

        NXM requires an NFO file for every upload.
        Either an NFO file generated by MediaInfo,
        or an NFO file included with the release.
        """
        nfo_files = self._get_nfo_files(meta)
        if nfo_files:
            return nfo_files[0]
        else:
            return await self._get_or_generate_mediainfo_as_nfo(meta)

    async def _get_or_generate_mediainfo_as_nfo(self, meta: Meta) -> Union[str, None]:
        """Sub-function of _get_or_generate_nfo to get MI file if exists
        Else, generate a NFO
        """
        mi_dir = os.path.join(meta.get("base_dir", ""), "tmp", meta.get("uuid", ""))
        mi_clean = os.path.join(mi_dir, "MEDIAINFO_CLEANPATH.txt")
        mi = os.path.join(mi_dir, "MEDIAINFO.txt")
        if os.path.isfile(mi_clean):
            return mi_clean
        elif os.path.isfile(mi):
            return mi
        else:
            nfo_gen = SceneNfoGenerator(self.config)
            return await nfo_gen.generate_nfo(meta, self.tracker)

    # ──────────────────────────────────────────────────────────
    #  Upload / Search interface
    # ──────────────────────────────────────────────────────────

    async def upload(self, meta: Meta, _disctype: str) -> bool:
        """Upload torrent to NXM.org.

        POST https://nexum-core.com/api/v1/upload
          Authorization: Header : X-API-Key
          Content-Type:  multipart/form-data

        Required fields:  torrent, nfo, name, category_id, tmdb_id, tmdb_type
        Optional fields:  description
        """

        common = COMMON(config=self.config)

        # If NFO file exist, include it in torrent file by recreate .torrent
        nfo_files = self._get_nfo_files(meta)
        if nfo_files:
            await self._recreated_torrent_if_nfo(meta, self.common, self.config, self.tracker, self.source_flag)
        else:
            await common.create_torrent_for_upload(meta, self.tracker, self.source_flag)

        # ── Build release name ──
        name_result = await self.get_name(meta)
        title = name_result.get("name", "") if isinstance(name_result, dict) else str(name_result)

        # ── Read torrent file ──
        torrent_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}].torrent"
        async with aiofiles.open(torrent_path, "rb") as f:
            torrent_bytes = await f.read()

        # ── NFO file (required by NXM) ──
        nfo_path = await self._get_or_generate_nfo(meta)
        nfo_bytes = b""
        if nfo_files:
            async with aiofiles.open(nfo_files[0], "rb") as f:
                nfo_bytes = await f.read()
        elif nfo_path and os.path.exists(nfo_path):
            async with aiofiles.open(nfo_path, "rb") as f:
                nfo_bytes = await f.read()
            # Patch "Complete name" in NFO to match the tracker release name
            if title and nfo_bytes:
                try:
                    nfo_text = nfo_bytes.decode("utf-8", errors="replace")
                    nfo_bytes = nfo_text.encode("utf-8")
                except Exception:
                    pass  # If patching fails, upload unpatched NFO
        else:
            console.print("[yellow]NXM: No NFO available — upload may be rejected[/yellow]")
        if not nfo_bytes:
            meta["tracker_status"][self.tracker]["status_message"] = "NXM: missing required NFO file"
            return False
        # ── Description ──
        description = await self._build_description(meta)

        # ── Category / Subcategory ──
        category_id = await self._get_category(meta)

        # ── Multipart form ──

        tmdb_id = meta.get("tmdb_id", "")
        tmdb_type = meta.get("category", "").lower()

        files: dict[str, tuple[str, bytes, str]] = {
            "torrent": ("torrent.torrent", torrent_bytes, "application/x-bittorrent"),
            "nfo": ("release.nfo", nfo_bytes, "application/octet-stream"),
        }

        data: dict[str, Any] = {
            "name": title,
            "description": description,
            "category_id": category_id,
            "tmdb_id": tmdb_id,
            "tmdb_type": tmdb_type,
        }

        headers: dict[str, str] = {
            "X-API-Key": self.api_key,
            "Accept": "application/json,application/x-bittorrent",
        }

        try:
            if not meta["debug"]:
                max_retries = 2
                retry_delay = 5
                timeout = 40.0

                for attempt in range(max_retries):
                    try:
                        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                            response = await client.post(
                                url=self.upload_url,
                                files=files,
                                data=data,
                                headers=headers,
                            )

                        if response.status_code in (200, 201):
                            try:
                                response_data = response.json()

                                # Check API-level success flag
                                if isinstance(response_data, dict) and response_data.get("success") is False:
                                    error_msg = response_data.get("message", "Unknown error")
                                    meta["tracker_status"][self.tracker]["status_message"] = f"API error: {error_msg}"
                                    console.print(f"[yellow]NXM upload failed: {error_msg}[/yellow]")
                                    return False

                                # Extract torrent_id for the standard URL output
                                torrent_id = None
                                if isinstance(response_data, dict):
                                    data_block = response_data
                                    if isinstance(data_block, dict):
                                        torrent_id = data_block.get("torrent_id")
                                if torrent_id:
                                    meta["tracker_status"][self.tracker]["torrent_id"] = torrent_id
                                    await self.common.download_tracker_torrent(meta, self.tracker, headers=headers, downurl=f"{self.search_url}{torrent_id}/download")
                                meta["tracker_status"][self.tracker]["status_message"] = response_data
                                return True
                            except json.JSONDecodeError:
                                meta["tracker_status"][self.tracker]["status_message"] = "data error: NXM JSON decode error"
                                return False

                        # ── Non-retriable HTTP errors ──
                        elif response.status_code in (400, 401, 409, 404, 422):
                            error_detail: Any = ""
                            api_message: str = ""
                            try:
                                error_detail = response.json()
                                if isinstance(error_detail, dict):
                                    api_message = error_detail.get("message", "")
                            except Exception:
                                error_detail = response.text[:500]

                            # Build a clean status message for tracker_status
                            if api_message:
                                meta["tracker_status"][self.tracker]["status_message"] = f"NXM: {api_message}"
                            else:
                                meta["tracker_status"][self.tracker]["status_message"] = {
                                    "error": f"HTTP {response.status_code}",
                                    "detail": error_detail,
                                }

                            # Pretty-print the error
                            if api_message:
                                console.print(f"[yellow]NXM — {api_message}[/yellow]")
                            else:
                                console.print(f"[red]NXM upload failed: HTTP {response.status_code}[/red]")
                                if error_detail:
                                    console.print(f"[dim]{error_detail}[/dim]")
                            return False

                        # ── Retriable HTTP errors ──
                        else:
                            if attempt < max_retries - 1:
                                console.print(f"[yellow]NXM: HTTP {response.status_code}, retrying in {retry_delay}s… (attempt {attempt + 1}/{max_retries})[/yellow]")
                                await asyncio.sleep(retry_delay)
                                continue
                            error_detail = ""
                            try:
                                error_detail = response.json()
                            except Exception:
                                error_detail = response.text[:500]
                            meta["tracker_status"][self.tracker]["status_message"] = {
                                "error": f"HTTP {response.status_code}",
                                "detail": error_detail,
                            }
                            console.print(f"[red]NXM upload failed after {max_retries} attempts: HTTP {response.status_code}[/red]")
                            if error_detail:
                                console.print(f"[dim]{error_detail}[/dim]")
                            return False

                    except httpx.TimeoutException:
                        if attempt < max_retries - 1:
                            timeout = timeout * 1.5
                            console.print(f"[yellow]NXM: timeout, retrying in {retry_delay}s with {timeout:.0f}s timeout… (attempt {attempt + 1}/{max_retries})[/yellow]")
                            await asyncio.sleep(retry_delay)
                            continue
                        meta["tracker_status"][self.tracker]["status_message"] = "data error: Request timed out after multiple attempts"
                        return False

                    except httpx.RequestError as e:
                        if attempt < max_retries - 1:
                            console.print(f"[yellow]NXM: request error, retrying in {retry_delay}s… (attempt {attempt + 1}/{max_retries})[/yellow]")
                            await asyncio.sleep(retry_delay)
                            continue
                        meta["tracker_status"][self.tracker]["status_message"] = f"data error: Upload failed: {e}"
                        console.print(f"[red]NXM upload error: {e}[/red]")
                        return False

                return False  # exhausted retries without explicit return
            else:
                # ── Debug mode — save description & show summary ──
                desc_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}]DESCRIPTION.txt"
                async with aiofiles.open(desc_path, "w", encoding="utf-8") as f:
                    await f.write(description)
                console.print(f"DEBUG: Saving final description to {desc_path}")
                console.print("[cyan]NXM Debug — Request data:[/cyan]")
                console.print(f"  name:        {title}")
                console.print(f"  category_id: {category_id}")
                console.print(f"  tmdb_id:     {tmdb_id}")
                console.print(f"  tmdb_type:   {tmdb_type}")
                console.print(f"  description: {description[:500]}…")
                meta["tracker_status"][self.tracker]["status_message"] = "Debug mode, not uploaded."
                await common.create_torrent_for_upload(
                    meta,
                    f"{self.tracker}_DEBUG",
                    f"{self.tracker}_DEBUG",
                    announce_url="https://fake.tracker",
                )
                return True

        except Exception as e:
            meta["tracker_status"][self.tracker]["status_message"] = f"data error: Upload failed: {e}"
            console.print(f"[red]NXM upload error: {e}[/red]")
            return False

    async def search_existing(self, meta: Meta, _: Any = None) -> list[dict[str, Any]]:
        """Search for existing torrents on NXM via its API.

        API endpoint: GET https://nexum-core.com/api/v1/torrents
        Response format:  JSON.
        """
        dupes: list[dict[str, Any]] = []

        if not await self.get_additional_checks(meta):
            meta["skipping"] = self.tracker
            return dupes

        title = meta.get("title", "")
        # Ensure French title is resolved (may not be populated yet at dupe-check time)
        fr_title = meta.get("frtitle", "")
        if not fr_title:
            fr_title = await self._get_french_title(meta)
        year = meta.get("year", "")
        tag = meta.get("tag", "")

        # Normalize for relevance filtering
        def _normalize(s: str) -> str:
            return re.sub(r"[^a-z0-9]", "", unidecode(s).lower())

        # Build the list of search queries — original-language title first
        search_queries: list[str] = []
        is_original_french = str(meta.get("original_language", "")).lower() == "fr"

        if is_original_french:
            # Original is French → search FR first, then EN as complement
            if fr_title:
                search_queries.append(f"{fr_title} {tag}".strip())
            if title and _normalize(title) != _normalize(fr_title or ""):
                search_queries.append(f"{title} {tag}".strip())
        else:
            # Original is not French → search EN first, then FR as complement
            if title:
                search_queries.append(f"{title} {tag}".strip())
            if fr_title and _normalize(fr_title) != _normalize(title or ""):
                search_queries.append(f"{fr_title} {tag}".strip())

        if not search_queries:
            return []

        title_norm = _normalize(title)
        fr_title_norm = _normalize(fr_title) if fr_title else ""
        year_str = str(year).strip()
        seen_names: set[str] = set()

        try:
            headers = {
                "X-API-Key": self.api_key,
                "Accept": "application/json",
            }

            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                for search_term in search_queries:
                    try:
                        response = await client.get(
                            self.search_url,
                            headers=headers,
                            params={"q": search_term},
                        )
                    except Exception:  # noqa: BLE001
                        continue  # nosec B112 — skip failed search queries gracefully

                    if response.status_code != 200:
                        if meta.get("debug"):
                            console.print(f"[yellow]NXM search returned HTTP {response.status_code} for '{search_term}'[/yellow]")
                        continue

                    try:
                        data = response.json()
                    except json.JSONDecodeError:
                        continue

                    if not isinstance(data, dict):
                        continue

                    items = data.get("torrents", data.get("data", []))
                    if not items:
                        continue

                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        name = item.get("title", item.get("name", ""))
                        if not name:
                            continue

                        # De-duplicate across queries
                        name_norm = _normalize(name)
                        if name_norm in seen_names:
                            continue

                        # Filter: the result must contain the title (EN or FR) AND year to be relevant
                        title_match = title_norm and title_norm in name_norm
                        fr_title_match = fr_title_norm and fr_title_norm in name_norm
                        if not title_match and not fr_title_match:
                            if meta.get("debug"):
                                console.print(f"[dim]NXM dupe skip (title mismatch): {name}[/dim]")
                            continue
                        # TV torrents typically use S01E01 format and omit the year
                        if year_str and year_str not in name and meta.get("category") != "TV":
                            if meta.get("debug"):
                                console.print(f"[dim]NXM dupe skip (year mismatch): {name}[/dim]")
                            continue

                        seen_names.add(name_norm)
                        dupes.append(
                            {
                                "name": name,
                                "size": item.get("size", item.get("file_size_bytes")),
                                "link": (
                                    item.get("url")
                                    or item.get("link")
                                    or (f"{self.torrent_url}{item['slug']}" if item.get("slug") else None)
                                    or (f"{self.torrent_url}{item['id']}" if item.get("id") else None)
                                ),
                                "id": item.get("id", item.get("torrent_id")),
                            }
                        )

        except Exception as e:
            if meta.get("debug"):
                console.print(f"[yellow]NXM search error: {e}[/yellow]")

        if meta.get("debug"):
            console.print(f"[cyan]NXM dupe search found {len(dupes)} result(s)[/cyan]")

        return await self._check_french_lang_dupes(dupes, meta)

    async def edit_desc(self, _meta: Meta) -> None:
        """No-op — NXM descriptions are built in upload()."""
        return
