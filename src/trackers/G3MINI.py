# Upload Assistant © 2025 Audionut &amp; wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any

from src.console import console
from src.nfo_generator import SceneNfoGenerator
from src.trackers.COMMON import COMMON
from src.trackers.FRENCH import FrenchTrackerMixin
from src.trackers.UNIT3D import UNIT3D


class G3MINI(FrenchTrackerMixin, UNIT3D):
    def __init__(self, config):
        super().__init__(config, tracker_name="G3MINI")
        self.config = config
        self.common = COMMON(config)
        self.tracker = "G3MINI"
        self.base_url = "https://gemini-tracker.org"
        self.id_url = f"{self.base_url}/api/torrents/"
        self.upload_url = f"{self.base_url}/api/torrents/upload"
        self.requests_url = f"{self.base_url}/api/requests/filter"
        self.search_url = f"{self.base_url}/api/torrents/filter"
        self.torrent_url = f"{self.base_url}/torrents/"
        self.banned_groups = [""]
        self.source_flag = "G3MINI"
        pass

    WEB_LABEL: str = "WEB-DL"

    async def get_category_id(self, meta: dict[str, Any], category: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        category_id = {
            "MOVIE": "1",
            "TV": "2",
            # Film anim 7
            # anim 6
        }
        if mapping_only:
            return category_id
        elif reverse:
            return {v: k for k, v in category_id.items()}
        elif category:
            return {"category_id": category_id.get(category, "0")}
        else:
            meta_category = meta.get("category", "")
            resolved_id = category_id.get(meta_category, "0")
            return {"category_id": resolved_id}

    async def get_type_id(self, meta: dict[str, Any], type: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        type_id = {"DISC": "1", "REMUX": "2", "WEBDL": "4", "WEBRIP": "5", "HDTV": "6", "ENCODE": "3", "ISO": "7"}
        if mapping_only:
            return type_id
        elif reverse:
            return {v: k for k, v in type_id.items()}
        elif type:
            return {"type_id": type_id.get(type, "0")}
        else:
            meta_type = meta.get("type", "")
            resolved_id = type_id.get(meta_type, "0")
            return {"type_id": resolved_id}

    async def get_resolution_id(self, meta: dict[str, Any], resolution: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        resolution_id = {"4320p": "1", "2160p": "2", "1080p": "3", "1080i": "4", "720p": "5", "576p": "6", "576i": "7", "480p": "8", "480i": "9"}
        if mapping_only:
            return resolution_id
        elif reverse:
            return {v: k for k, v in resolution_id.items()}
        elif resolution:
            return {"resolution_id": resolution_id.get(resolution, "10")}
        else:
            meta_resolution = meta.get("resolution", "")
            resolved_id = resolution_id.get(meta_resolution, "10")
            return {"resolution_id": resolved_id}

    async def get_additional_checks(self, meta: dict[str, Any]) -> bool:
        french_languages = ["french", "fre", "fra", "fr", "français", "francais", "fr-fr", "fr-ca"]
        # check or ignore audio req config
        # self.config['TRACKERS'][self.tracker].get('check_for_rules', True):
        if not await self.common.check_language_requirements(
            meta,
            self.tracker,
            languages_to_check=french_languages,
            check_audio=True,
            check_subtitle=True,
            require_both=False,
            # original_language=True,   # Devlopement version
        ):
            console.print(f"[bold red]Language requirements not met for {self.tracker}.[/bold red]")
            return False

        # Always generate NFO for G3MINI
        if not meta.get("nfo") and not meta.get("auto_nfo"):
            generator = SceneNfoGenerator(self.config)
            nfo_path = await generator.generate_nfo(meta, self.tracker)
            if nfo_path:
                meta["nfo"] = nfo_path
                meta["auto_nfo"] = True

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

        audio_langs = self._extract_audio_languages(audio_tracks, meta)
        if not audio_langs:
            return ""

        has_french_audio = "FRA" in audio_langs
        has_french_subs = self._has_french_subs(meta)
        num_audio_tracks = len(audio_tracks)
        fr_suffix = self._get_french_dub_suffix(audio_tracks)

        # MULTi - 2+ audio tracks with at least 1 French
        if num_audio_tracks >= 2 and has_french_audio:
            if fr_suffix:
                return f"MULTi {fr_suffix}"
            return "MULTi"

        # FRENCH - 1 audio track, it's French
        if num_audio_tracks == 1 and has_french_audio:
            # Only append VFQ suffix; VFF or generic fr -> just FRENCH
            if fr_suffix == "VFQ":
                return "FRENCH VFQ"
            return "FRENCH"

        # VOSTFR - No French audio but French subtitles present
        if not has_french_audio and has_french_subs:
            return "VOSTFR"

        # VO - No French content at all
        if not has_french_audio and not has_french_subs:
            return "VO"

        return ""

    # _get_french_dub_suffix, _get_audio_tracks, _extract_audio_languages,
    # _map_language, _has_french_subs — inherited from FrenchTrackerMixin

    # https://gemini-tracker.org/pages/7
    async def get_name(self, meta):
        def replace_spaces_with_dots(text: str) -> str:
            return text.replace(" ", ".")

        def _clean_filename(name):
            # G3MINI keeps title-internal hyphens (WALL·E → WALL-E), so
            # middle dot / bullet map to hyphen instead of space.
            _g3_map = {**FrenchTrackerMixin._TITLE_CHAR_MAP, "\u00b7": "-", "\u2022": "-"}
            for char, repl in _g3_map.items():
                name = name.replace(char, repl)
            # Strip all non-alphanumeric chars except spaces, dots, hyphens, and + (for DD+, HDR10+)
            name = re.sub(r"[^a-zA-Z0-9 .+\-]", "", name)
            return name

        type = meta.get("type", "").upper()
        title = meta.get("title", "")
        year = meta.get("year", "")
        manual_year = meta.get("manual_year")
        if manual_year is not None and int(manual_year) > 0:
            year = manual_year
        resolution = meta.get("resolution", "")
        if resolution == "OTHER":
            resolution = ""
        audio = meta.get("audio", "").replace("Dual-Audio", "").replace("Dubbed", "")
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
        hybrid = str(meta.get("webdv", "")) if meta.get("webdv", "") else ""
        # Ensure the following variables are always defined
        name = ""
        video_codec = ""
        video_encode = ""
        region = ""
        dvd_size = ""
        if meta.get("is_disc", "") == "BDMV":  # Disk
            video_codec = meta.get("video_codec", "")
            region = meta.get("region", "") if meta.get("region", "") is not None else ""
        elif meta.get("is_disc", "") == "DVD":
            region = meta.get("region", "") if meta.get("region", "") is not None else ""
            dvd_size = meta.get("dvd_size", "")
        else:
            video_codec = meta.get("video_codec", "")
            video_encode = meta.get("video_encode", "")
        edition = meta.get("edition", "")
        if "hybrid" in edition.upper():
            edition = edition.replace("Hybrid", "").strip()

        if meta["category"] == "TV":
            year = meta["year"] if meta["search_year"] != "" else ""
            if meta.get("manual_date"):
                # Ignore season and year for --daily flagged shows, just use manual date stored in episode_name
                season = ""
                episode = ""
        if meta.get("no_season", False) is True:
            season = ""
        if meta.get("no_year", False) is True:
            year = ""
        if meta.get("no_aka", False) is True:
            pass
        if meta["debug"]:
            console.log("[cyan]get_name cat/type")
            console.log(f"CATEGORY: {meta['category']}")
            console.log(f"TYPE: {meta['type']}")
            console.log("[cyan]get_name meta:")
            # console.log(meta)

        if meta["category"] == "MOVIE":  # MOVIE SPECIFIC
            if type == "DISC":  # Disk
                if meta["is_disc"] == "BDMV":
                    name = f"{title} {year} {three_d} {edition} {hybrid} {repack} {language} {resolution} {region} {uhd} {source} {hdr} {video_codec} {audio}"
                elif meta["is_disc"] == "DVD":
                    name = f"{title} {year} {repack} {edition} {region} {source} {dvd_size} {audio}"
                elif meta["is_disc"] == "HDDVD":
                    name = f"{title} {year} {edition} {repack} {language} {resolution} {source} {video_codec} {audio}"
            elif type == "REMUX" and source in ("BluRay", "HDDVD"):  # BluRay/HDDVD Remux
                name = f"{title} {year} {three_d} {edition} {hybrid} {repack} {language} {resolution} {uhd} {source} REMUX {hdr} {video_codec} {audio}"
            elif type == "REMUX" and source in ("PAL DVD", "NTSC DVD", "DVD"):  # DVD Remux
                name = f"{title} {year} {edition} {repack} {source} REMUX  {audio}"
            elif type == "ENCODE":  # Encode
                name = f"{title} {year} {edition} {hybrid} {repack} {language} {resolution} {uhd} {source} {audio} {hdr} {video_encode}"
            elif type == "WEBDL":  # WEB-DL
                name = f"{title} {year} {edition} {hybrid} {repack} {language} {resolution} {uhd} {service} WEB-DL {audio} {hdr} {video_encode}"
            elif type == "WEBRIP":  # WEBRip
                name = f"{title} {year} {edition} {hybrid} {repack} {language} {resolution} {uhd} {service} WEBRip {audio} {hdr} {video_encode}"
            elif type == "HDTV":  # HDTV
                name = f"{title} {year} {edition} {repack} {language} {resolution} {source} {audio} {video_encode}"
            elif type == "DVDRIP":
                name = f"{title} {year} {source} {video_encode} DVDRip {audio}"

        elif meta["category"] == "TV":  # TV SPECIFIC
            if type == "DISC":  # Disk
                if meta["is_disc"] == "BDMV":
                    name = f"{title} {year} {season}{episode} {three_d} {edition} {hybrid} {repack} {language} {resolution} {region} {uhd} {source} {hdr} {video_codec} {audio}"
                if meta["is_disc"] == "DVD":
                    name = f"{title} {year} {season}{episode}{three_d} {repack} {edition} {region} {source} {dvd_size} {audio}"
                elif meta["is_disc"] == "HDDVD":
                    name = f"{title} {year} {edition} {repack} {language} {resolution} {source} {video_codec} {audio}"
            elif type == "REMUX" and source in ("BluRay", "HDDVD"):  # BluRay Remux
                name = f"{title} {year} {season}{episode} {part} {three_d} {edition} {hybrid} {repack} {language} {resolution} {uhd} {source} REMUX {hdr} {video_codec} {audio}"  # SOURCE
            elif type == "REMUX" and source in ("PAL DVD", "NTSC DVD", "DVD"):  # DVD Remux
                name = f"{title} {year} {season}{episode} {part} {edition} {repack} {source} REMUX {audio}"  # SOURCE
            elif type == "ENCODE":  # Encode
                name = f"{title} {year} {season}{episode} {part} {edition} {hybrid} {repack} {language} {resolution} {uhd} {source} {audio} {hdr} {video_encode}"  # SOURCE
            elif type == "WEBDL":  # WEB-DL
                name = f"{title} {year} {season}{episode} {part} {edition} {hybrid} {repack} {language} {resolution} {uhd} {service} WEB-DL {audio} {hdr} {video_encode}"
            elif type == "WEBRIP":  # WEBRip
                name = f"{title} {year} {season}{episode} {part} {edition} {hybrid} {repack} {language} {resolution} {uhd} {service} WEBRip {audio} {hdr} {video_encode}"
            elif type == "HDTV":  # HDTV
                name = f"{title} {year} {season}{episode} {part} {edition} {repack} {language} {resolution} {source} {audio} {video_encode}"
            elif type == "DVDRIP":
                name = f"{title} {year} {season} {source} DVDRip {audio} {video_encode}"

        try:
            name = " ".join(name.split())
        except Exception:
            console.print("[bold red]Unable to generate name. Please re-run and correct any of the following args if needed.")
            console.print(f"--category [yellow]{meta['category']}")
            console.print(f"--type [yellow]{meta['type']}")
            console.print(f"--source [yellow]{meta['source']}")
            console.print("[bold green]If you specified type, try also specifying source")

            exit()
        name_notag = name
        name = name_notag + tag
        clean_name = _clean_filename(name)
        dot_name = replace_spaces_with_dots(clean_name)
        # Remove isolated hyphens between dots (e.g. "Chainsaw.Man.-.The.Movie" → "Chainsaw.Man.The.Movie")
        dot_name = re.sub(r"\.(-\.)+", ".", dot_name)
        # Collapse consecutive dots and strip boundary dots
        dot_name = re.sub(r"\.{2,}", ".", dot_name)
        dot_name = dot_name.strip(".")
        return {"name": dot_name}
