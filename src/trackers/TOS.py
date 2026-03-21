# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
# import discord
import asyncio
from typing import Any, Optional

import cli_ui
import httpx

from src.console import console
from src.torrentcreate import TorrentCreator
from src.trackers.COMMON import COMMON
from src.trackers.FRENCH import FrenchTrackerMixin
from src.trackers.UNIT3D import UNIT3D, QueryValue


class TOS(FrenchTrackerMixin, UNIT3D):
    def __init__(self, config: dict[str, Any]):
        super().__init__(config, tracker_name="TOS")
        self.config = config
        self.common = COMMON(config)
        self.tracker = "TOS"
        self.source_flag = "TheOldSchool"
        self.base_url = "https://theoldschool.cc"
        self.id_url = f"{self.base_url}/api/torrents/"
        self.upload_url = f"{self.base_url}/api/torrents/upload"
        self.search_url = f"{self.base_url}/api/torrents/filter"
        self.torrent_url = f"{self.base_url}/torrents/"
        self.banned_groups = [
            "FL3ER",
            "SUNS3T",
            "WoLFHD",
            "EXTREME",
            "Slay3R",
            "3T3AM",
            "BARBiE",
            "Freek911",
            "k0RE",
        ]
        pass

    async def get_category_id(
        self,
        meta: dict[str, Any],
        category: Optional[str] = None,
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        _ = (category, reverse, mapping_only)
        language_tag = await self._build_audio_string(meta)
        while language_tag.startswith("AD."):
            language_tag = language_tag[3:]
        if language_tag == "VOSTFR":
            category_id = "9" if meta["category"] == "TV" and meta.get("tv_pack") else {"MOVIE": "6", "TV": "7"}.get(meta["category"], "0")
        else:
            category_id = "8" if meta["category"] == "TV" and meta.get("tv_pack") else {"MOVIE": "1", "TV": "2"}.get(meta["category"], "0")
        return {"category_id": category_id}

    async def get_type_id(
        self,
        meta: dict[str, Any],
        type: Optional[str] = None,
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        _ = (type, reverse, mapping_only)
        if meta["is_disc"] == "DVD":
            type_id = "7"
        elif meta.get("3D") == "3D":
            type_id = "8"
        else:
            type_id = {
                "DISC": "1",
                "REMUX": "2",
                "ENCODE": "3",
                "WEBDL": "4",
                "WEBRIP": "5",
                "HDTV": "6",
            }.get(meta["type"], "0")
        return {"type_id": type_id}

    async def search_existing(self, meta: dict[str, Any], _: Any = None) -> list[dict[str, Any]]:
        """Search for existing torrents on TOS.

        TOS uses separate categories for VOSTFR releases.  The default
        UNIT3D search filters by category, so a VOSTFR upload would miss
        MULTI releases in the normal category.  This override searches
        across both category sets so ``_check_french_lang_dupes`` can
        detect superior French-audio releases.
        """
        dupes: list[dict[str, Any]] = []

        meta.setdefault("tracker_status", {})
        meta["tracker_status"].setdefault(self.tracker, {})

        if not self.api_key:
            if not meta["debug"]:
                console.print(f"[bold red]{self.tracker}: Missing API key in config file. Skipping upload...[/bold red]")
            meta["skipping"] = f"{self.tracker}"
            return dupes

        should_continue = await self.get_additional_checks(meta)
        if not should_continue:
            meta["skipping"] = f"{self.tracker}"
            return dupes

        headers = {
            "authorization": f"Bearer {self.api_key}",
            "accept": "application/json",
        }

        # Determine all relevant category IDs
        # Normal: MOVIE=1, TV=2, TV pack=8
        # VOSTFR: MOVIE=6, TV=7, TV pack=9
        cat = meta.get("category", "MOVIE")
        is_pack = meta.get("tv_pack", False)
        if cat == "TV" and is_pack:
            category_ids = ["8", "9"]
        elif cat == "TV":
            category_ids = ["2", "7"]
        else:
            category_ids = ["1", "6"]

        params: list[tuple[str, QueryValue]] = [
            ("tmdbId", str(meta["tmdb"])),
            ("name", ""),
            ("perPage", "100"),
        ]
        params.extend(("categories[]", cid) for cid in category_ids)

        # Add resolution filter(s)
        resolutions = await self.get_resolution_id(meta)
        resolution_id = str(resolutions["resolution_id"])
        if resolution_id in ["3", "4"]:
            params.append(("resolutions[]", "3"))
            params.append(("resolutions[]", "4"))
        else:
            params.append(("resolutions[]", resolution_id))

        # Add type filter (types are format-based, not language-based)
        type_id = str((await self.get_type_id(meta))["type_id"])
        params.append(("types[]", type_id))

        if meta["category"] == "TV":
            params = [(k, (str(v) + f" {meta.get('season', '')}" if k == "name" else v)) for k, v in params]

        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                response = await client.get(url=self.search_url, headers=headers, params=params)
                response.raise_for_status()
                if response.status_code == 200:
                    data = response.json()
                    for each in data["data"]:
                        torrent_id = each.get("id", None)
                        attributes = each.get("attributes", {})
                        name = attributes.get("name", "")
                        size = attributes.get("size", 0)
                        result: dict[str, Any] = {
                            "name": name,
                            "size": size,
                            "files": ([f["name"] for f in attributes.get("files", []) if isinstance(f, dict) and "name" in f] if not meta["is_disc"] else []),
                            "file_count": len(attributes.get("files", [])) if isinstance(attributes.get("files"), list) else 0,
                            "trumpable": attributes.get("trumpable", False),
                            "link": attributes.get("details_link", None),
                            "download": attributes.get("download_link", None),
                            "id": torrent_id,
                            "type": attributes.get("type", None),
                            "res": attributes.get("resolution", None),
                            "internal": attributes.get("internal", False),
                        }
                        if meta["is_disc"]:
                            result["bd_info"] = attributes.get("bd_info", "")
                            result["description"] = attributes.get("description", "")
                        dupes.append(result)
                else:
                    console.print(f"[bold red]Failed to search torrents on {self.tracker}. HTTP Status: {response.status_code}")
        except httpx.HTTPStatusError as e:
            meta["tracker_status"][self.tracker]["status_message"] = f"data error: HTTP {e.response.status_code}"
        except Exception as e:
            console.print(f"[bold red]{self.tracker}: Error searching for existing torrents — {e}[/bold red]")

        return await self._check_french_lang_dupes(dupes, meta)

    async def get_name(self, meta: dict[str, Any]) -> dict[str, str]:
        """Build TOS-compliant dot-separated release name.

        Same layout as G3MINI but with video codec before audio codec:
            …LANGUE.Resolution.Source[.HDR.VideoCodec].AudioCodec.Channels[.Object]-TEAM
        """
        import re

        is_scene = meta.get("scene", False)
        if is_scene and not meta.get("tv_pack"):
            return {"name": str(meta.get("scene_name", ""))}
        if is_scene and meta.get("tv_pack"):
            # For scene packs, scene_name is the first episode name (e.g. S01E01);
            # use the folder basename which is the actual pack name (e.g. S01).
            import os

            return {"name": os.path.basename(str(meta.get("path", meta.get("scene_name", ""))))}

        type_val = meta.get("type", "").upper()
        title = meta.get("title", "")
        year = str(meta.get("year", ""))
        manual_year = meta.get("manual_year")
        if manual_year is not None and int(manual_year) > 0:
            year = str(manual_year)

        resolution = meta.get("resolution", "")
        if resolution == "OTHER":
            resolution = ""

        audio = meta.get("audio", "").replace("Dual-Audio", "").replace("Dubbed", "")  # Audio codec for the first track
        language = await self._build_audio_string(meta)
        service = meta.get("service", "")
        season = meta.get("season", "")
        episode = meta.get("episode", "")
        part = meta.get("part", "")
        repack = meta.get("repack", "")
        three_d = meta.get("3D", "")
        tag = meta.get("tag", "")
        source = meta.get("source", "")
        uhd = meta.get("uhd", "")
        hdr = meta.get("hdr", "")
        edition = self._format_edition(meta.get("edition", ""))
        hybrid = str(meta.get("webdv", "")) if meta.get("webdv", "") else ""
        if "hybrid" in edition.upper():
            edition = edition.replace("Hybrid", "").strip()

        video_codec = ""
        video_encode = ""
        region = ""
        dvd_size = ""

        if meta.get("is_disc") == "BDMV":
            video_codec = meta.get("video_codec", "")
            region = meta.get("region", "") or ""
        elif meta.get("is_disc") == "DVD":
            region = meta.get("region", "") or ""
            dvd_size = meta.get("dvd_size", "")
        else:
            video_codec = meta.get("video_codec", "")
            video_encode = meta.get("video_encode", "")

        if meta["category"] == "TV":
            year = meta["year"] if meta.get("search_year", "") != "" else ""
            if meta.get("manual_date"):
                season = ""
                episode = ""
        if meta.get("tv_pack"):
            episode = ""
        if meta.get("no_season", False) is True:
            season = ""
        if meta.get("no_year", False) is True:
            year = ""

        name = ""

        # ── MOVIE ──
        # G3MINI order with video/audio swapped:
        #   Disc/Remux: …Source HDR Audio VideoCodec
        #   Encode/WEB: …Source Audio HDR VideoEncode
        if meta["category"] == "MOVIE":
            if type_val == "DISC":
                if meta.get("is_disc") == "BDMV":
                    name = f"{title} {year} {three_d} {edition} {hybrid} {repack} {language} {resolution} {region} {uhd} {source} {hdr} {audio} {video_codec}"
                elif meta.get("is_disc") == "DVD":
                    name = f"{title} {year} {repack} {edition} {region} {source} {dvd_size} {audio}"
                elif meta.get("is_disc") == "HDDVD":
                    name = f"{title} {year} {edition} {repack} {language} {resolution} {source} {audio} {video_codec}"
            elif type_val == "REMUX" and source in ("BluRay", "HDDVD"):
                name = f"{title} {year} {three_d} {edition} {hybrid} {repack} {language} {resolution} {uhd} {source} REMUX {hdr} {audio} {video_codec}"
            elif type_val == "REMUX" and source in ("PAL DVD", "NTSC DVD", "DVD"):
                name = f"{title} {year} {edition} {repack} {source} REMUX {audio}"
            elif type_val == "ENCODE":
                name = f"{title} {year} {edition} {hybrid} {repack} {language} {resolution} {uhd} {source} {audio} {hdr} {video_encode}"
            elif type_val == "WEBDL":
                name = f"{title} {year} {edition} {hybrid} {repack} {language} {resolution} {uhd} {service} WEB-DL {audio} {hdr} {video_encode}"
            elif type_val == "WEBRIP":
                name = f"{title} {year} {edition} {hybrid} {repack} {language} {resolution} {uhd} {service} WEBRip {audio} {hdr} {video_encode}"
            elif type_val == "HDTV":
                name = f"{title} {year} {edition} {repack} {language} {resolution} {source} {audio} {video_encode}"
            elif type_val == "DVDRIP":
                name = f"{title} {year} {source} DVDRip {audio} {video_encode}"

        # ── TV ──
        elif meta["category"] == "TV":
            if type_val == "DISC":
                if meta.get("is_disc") == "BDMV":
                    name = f"{title} {year} {season}{episode} {three_d} {edition} {hybrid} {repack} {language} {resolution} {region} {uhd} {source} {hdr} {audio} {video_codec}"
                elif meta.get("is_disc") == "DVD":
                    name = f"{title} {year} {season}{episode} {repack} {edition} {region} {source} {dvd_size} {audio}"
                elif meta.get("is_disc") == "HDDVD":
                    name = f"{title} {year} {edition} {repack} {language} {resolution} {source} {audio} {video_codec}"
            elif type_val == "REMUX" and source in ("BluRay", "HDDVD"):
                name = f"{title} {year} {season}{episode} {part} {three_d} {edition} {hybrid} {repack} {language} {resolution} {uhd} {source} REMUX {hdr} {audio} {video_codec}"
            elif type_val == "REMUX" and source in ("PAL DVD", "NTSC DVD", "DVD"):
                name = f"{title} {year} {season}{episode} {part} {edition} {repack} {source} REMUX {audio}"
            elif type_val == "ENCODE":
                name = f"{title} {year} {season}{episode} {part} {edition} {hybrid} {repack} {language} {resolution} {uhd} {source} {audio} {hdr} {video_encode}"
            elif type_val == "WEBDL":
                name = f"{title} {year} {season}{episode} {part} {edition} {hybrid} {repack} {language} {resolution} {uhd} {service} WEB-DL {audio} {hdr} {video_encode}"
            elif type_val == "WEBRIP":
                name = f"{title} {year} {season}{episode} {part} {edition} {hybrid} {repack} {language} {resolution} {uhd} {service} WEBRip {audio} {hdr} {video_encode}"
            elif type_val == "HDTV":
                name = f"{title} {year} {season}{episode} {part} {edition} {repack} {language} {resolution} {source} {audio} {video_encode}"
            elif type_val == "DVDRIP":
                name = f"{title} {year} {season} {source} DVDRip {audio} {video_encode}"

        if not name:
            console.print("[bold red]TOS: Unable to generate release name.[/bold red]")
            console.print(f"  category={meta.get('category')}  type={meta.get('type')}  source={meta.get('source')}")
            return {"name": ""}

        # Collapse whitespace, append tag, dotify, clean
        name = " ".join(name.split()) + tag
        # Normalise special codec notations before stripping
        name = name.replace("DTS:X", "DTS-X")
        # Substitute known Unicode separators with ASCII hyphens
        # (e.g. WALL·E → WALL-E, Spider‑Man → Spider-Man)
        _TOS_CHAR_MAP = {**FrenchTrackerMixin._TITLE_CHAR_MAP, "\u00b7": "-", "\u2022": "-"}
        for char, repl in _TOS_CHAR_MAP.items():
            name = name.replace(char, repl)
        # Allow alphanumeric, spaces, dots, hyphens, colons, and + (for DD+, HDR10+)
        name = re.sub(r"[^a-zA-Z0-9 .+\-]", "", name)
        name = name.replace(" ", ".")
        name = re.sub(r"\.(-\.)+", ".", name)
        name = re.sub(r"\.{2,}", ".", name)
        name = name.strip(".")

        # Recreate torrent if keep_nfo is set
        if meta.get("keep_nfo", False):
            tracker_config = self.config["TRACKERS"].get(self.tracker, {})
            tracker_url = str(tracker_config.get("announce_url", "https://fake.tracker")).strip()
            torrent_create = f"[{self.tracker}]"
            try:
                cooldown = int(self.config.get("DEFAULT", {}).get("rehash_cooldown", 0) or 0)
            except (ValueError, TypeError):
                cooldown = 0
            if cooldown > 0:
                await asyncio.sleep(cooldown)
            await TorrentCreator.create_torrent(meta, str(meta["path"]), torrent_create, tracker_url=tracker_url)

        return {"name": name}

    async def get_additional_checks(self, meta: dict[str, Any]) -> bool:
        # Check language requirements: must be French audio OR original audio with French subtitles
        french_languages = ["french", "fre", "fra", "fr", "français", "francais"]
        if not await self.common.check_language_requirements(
            meta,
            self.tracker,
            languages_to_check=french_languages,
            check_audio=True,
            check_subtitle=True,
            require_both=False,
            original_language=True,
        ):
            console.print(f"[bold red]Language requirements not met for {self.tracker}.[/bold red]")
            return False

        # Check if it's a Scene release without NFO - TOS requires NFO for Scene releases
        is_scene = meta.get("scene", False)
        has_nfo = meta.get("nfo", False) or meta.get("auto_nfo", False)

        if is_scene and not has_nfo:
            console.print(f"[red]{self.tracker}: Scene release detected but no NFO file found. TOS requires NFO files for Scene releases.[/red]")
            return False

        # ── Minimum bitrate requirements (kbps) per codec / resolution / type ──
        # Anime has lower thresholds per TOS rules.
        is_anime = bool(meta.get("anime", False))

        bitrate_minimums: dict[str, dict[str, dict[str, int]]] = {
            "x264": {
                "720p": {"WEBDL": 3000, "ENCODE": 4000},
                "1080p": {"WEBDL": 5000, "ENCODE": 8000},
                "2160p": {"WEBDL": 10000, "ENCODE": 16000},
            },
            "x265": {
                "720p": {"WEBDL": 2000, "ENCODE": 3000},
                "1080p": {"WEBDL": 3500, "ENCODE": 6000},
                "2160p": {"WEBDL": 8000, "ENCODE": 12000},
            },
            "AV1": {
                "720p": {"WEBDL": 2000, "ENCODE": 2400},
                "1080p": {"WEBDL": 3000, "ENCODE": 4000},
                "2160p": {"WEBDL": 5000, "ENCODE": 8000},
            },
        }

        anime_minimums: dict[str, dict[str, dict[str, int]]] = {
            "x264": {
                "720p": {"WEBDL": 1800, "ENCODE": 2300},
                "1080p": {"WEBDL": 3000, "ENCODE": 5000},
                "2160p": {"WEBDL": 6000, "ENCODE": 10000},
            },
            "x265": {
                "720p": {"WEBDL": 1200, "ENCODE": 1800},
                "1080p": {"WEBDL": 2000, "ENCODE": 3500},
                "2160p": {"WEBDL": 4000, "ENCODE": 8000},
            },
            "AV1": {
                "720p": {"WEBDL": 1200, "ENCODE": 1500},
                "1080p": {"WEBDL": 1500, "ENCODE": 2000},
                "2160p": {"WEBDL": 3000, "ENCODE": 4000},
            },
        }

        # Map video_codec values to our table keys
        codec_map: dict[str, str] = {
            "H264": "x264",
            "x264": "x264",
            "AVC": "x264",
            "H265": "x265",
            "x265": "x265",
            "HEVC": "x265",
            "AV1": "AV1",
        }

        bitrate_error = False
        thresholds_table = anime_minimums if is_anime else bitrate_minimums

        if not meta.get("is_disc") and meta.get("type") in ("ENCODE", "WEBDL"):
            resolution = meta.get("resolution", "")
            release_type = meta.get("type", "")
            video_codec = meta.get("video_codec", "")
            codec_key = codec_map.get(video_codec)

            if not codec_key:
                if meta.get("debug"):
                    console.print(f"[dim]{self.tracker}: No bitrate rules for codec '{video_codec}' — skipping check.[/dim]")
            elif resolution not in thresholds_table.get(codec_key, {}):
                if meta.get("debug"):
                    console.print(f"[dim]{self.tracker}: No bitrate rules for {codec_key} at {resolution} — skipping check.[/dim]")
            else:
                min_kbps = thresholds_table[codec_key][resolution][release_type]
                tracks = meta.get("mediainfo", {}).get("media", {}).get("track", [])
                video_track = next((t for t in tracks if t.get("@type") == "Video"), None)
                if video_track is None:
                    console.print(f"[bold red]Could not determine video bitrate from mediainfo for {self.tracker} upload.[/bold red]")
                    bitrate_error = True
                else:
                    raw_br = video_track.get("BitRate")
                    try:
                        bit_rate_kbps = int(raw_br) / 1000 if raw_br else None
                    except (ValueError, TypeError):
                        bit_rate_kbps = None

                    if bit_rate_kbps is None:
                        console.print(f"[bold red]Could not determine video bitrate from mediainfo for {self.tracker} upload.[/bold red]")
                        bitrate_error = True
                    elif bit_rate_kbps < min_kbps:
                        label = f"{codec_key} (anime)" if is_anime else codec_key
                        console.print(f"[bold red]{self.tracker}: Video bitrate too low: {bit_rate_kbps:.0f} kbps for {label}.[/bold red]")
                        console.print(f"[bold yellow]Must be >= {min_kbps} kbps for {resolution}.[/bold yellow]")
                        bitrate_error = True

        if bitrate_error:
            if meta.get("unattended", False):
                return False
            return cli_ui.ask_yes_no("Do you want to upload anyway?", default=False)

        return True

    async def _build_audio_string(self, meta):
        """Build the language tag following French tracker conventions.

        Tags: MUTE, MULTi [VFF|VFQ|VF2|VFn], FRENCH [VFQ], VOSTFR, VO
        """
        # No mediainfo available - can't determine language
        if "mediainfo" not in meta or "media" not in meta.get("mediainfo", {}):
            return ""

        audio_tracks = self._get_audio_tracks(meta)

        # MUTE - mediainfo present but no audio tracks
        if not audio_tracks:
            return "MUTE"

        ad_audio_tracks = [track for track in audio_tracks if self._is_audio_desc_track(track)]
        main_audio_tracks = [track for track in audio_tracks if not self._is_audio_desc_track(track)]

        audio_langs = self._extract_audio_languages(main_audio_tracks, meta)
        if not audio_langs and not ad_audio_tracks:
            return ""

        has_french_audio = "FRA" in audio_langs
        has_french_subs = self._has_french_subs(meta)
        num_audio_tracks = len(main_audio_tracks)
        fr_suffix = self._get_french_dub_suffix(main_audio_tracks)
        ad_audio_langs = self._extract_audio_languages(ad_audio_tracks)
        has_non_french_ad = any(lang != "FRA" for lang in ad_audio_langs)
        has_audiodesc = bool(meta.get("has_audiodesc") or ad_audio_tracks)

        language = ""

        # MULTi - 2+ audio tracks with at least 1 French
        if has_french_audio and (num_audio_tracks >= 2 or has_non_french_ad):
            language = f"MULTi {fr_suffix}" if fr_suffix else "MULTi"

        # FRENCH - 1 audio track, it's French
        elif num_audio_tracks == 1 and has_french_audio:
            # Only append VFQ suffix; VFF or generic fr -> just FRENCH
            language = "FRENCH VFQ" if fr_suffix == "VFQ" else "FRENCH"

        # VOSTFR - No French audio but French subtitles present (or SUBFRENCH in filename)
        elif not has_french_audio and (has_french_subs or self._detect_subfrench(meta)):
            language = "VOSTFR"

        # VO - No French content at all
        elif not has_french_audio and not has_french_subs:
            language = "VO"

        if language and has_audiodesc:
            language = f"AD.{language}"

        return language

    # _get_french_dub_suffix, _get_audio_tracks, _extract_audio_languages,
    # _map_language, _has_french_subs — inherited from FrenchTrackerMixin
