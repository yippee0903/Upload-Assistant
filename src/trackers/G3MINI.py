# Upload Assistant © 2025 Audionut &amp; wastaken7 — Licensed under UAPL v1.0
import os
import re
from typing import Any

from src.console import console
from src.tmdb import TmdbManager
from src.trackers.COMMON import COMMON, mi_tracks
from src.trackers.FRENCH import FrenchTrackerMixin
from src.trackers.french.rules import FRENCH_LANGUAGE_RULE, Rule
from src.trackers.UNIT3D import UNIT3D

_EXTERNAL_SUBS = (".srt", ".ass", ".ssa", ".sub", ".idx", ".vtt")
_ARCHIVES = (".rar", ".zip", ".7z")


def _preset_shortfalls(settings: str, minimums: tuple[tuple[str, int], ...], preset: str) -> tuple[str, ...]:
    """Parameters of an encoder settings string that are missing or below the given minimums."""
    shortfalls = []
    for param, minimum in minimums:
        match = re.search(rf"\b{param}\s*=\s*(\d+)", settings, re.IGNORECASE)
        value = int(match.group(1)) if match else None
        if value is None or value < minimum:
            shortfalls.append(f"{param}={value if value is not None else 'missing'} (minimum {minimum} for '{preset}')")
    return tuple(shortfalls)


class G3MINI(FrenchTrackerMixin, UNIT3D):
    RULES = (
        FRENCH_LANGUAGE_RULE,
        Rule("x264_slow_preset", "strict", "x264 encodes use at least the 'slow' preset (subme >= 8, trellis >= 2)"),
        Rule("x265_medium_preset", "strict", "x265 encodes use at least the 'medium' preset (subme >= 2, rd >= 3)"),
        Rule("av1_preset_max_4", "strict", "AV1 encodes use preset 4 (slower) or better"),
        Rule("no_mp3_audio", "strict", "No MP3 audio on encodes"),
        Rule("flac_stereo_only", "strict", "FLAC only for mono/stereo tracks on encodes"),
        Rule("multi_needs_french_subs", "strict", "A MULTi release carries VO + VF + French subtitles"),
        Rule("no_external_subs", "strict", "Subtitles are muxed into the MKV, no external files", evidence="filesystem"),
        Rule("no_archives", "strict", "No archives in the release", evidence="filesystem"),
        Rule("pgs_only_as_additional", "strict", "PGS subtitles on encodes only alongside a text track of the same language"),
    )
    notag_label: str = "NoGrP"

    def __init__(self, config):
        super().__init__(config, tracker_name="G3MINI")
        self.config = config
        self.common = COMMON(config)
        self.tmdb_manager = TmdbManager(config)
        self.tracker = "G3MINI"
        self.base_url = "https://gemini-tracker.org"
        self.id_url = f"{self.base_url}/api/torrents/"
        self.upload_url = f"{self.base_url}/api/torrents/upload"
        self.requests_url = f"{self.base_url}/api/requests/filter"
        self.search_url = f"{self.base_url}/api/torrents/filter"
        self.torrent_url = f"{self.base_url}/torrents/"
        # Site "Teams Interdites" list
        self.banned_groups = ["k0RE", "Slay3R", "EXTREME", "ShadowKernel", "byPlex", "WebVision", "AgoraQc", "DELiRiUS", "MICKEY"]
        self.source_flag = "G3MINI"
        pass

    WEB_LABEL: str = "WEB"

    async def get_category_id(self, meta: dict[str, Any], category: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        category_id = {
            "MOVIE": "1",
            "TV": "2",
            "MOVIE_ANIM": "7",  # Film Animation
            "TV_ANIM": "6",  # Séries Animations
        }
        if mapping_only:
            return category_id
        elif reverse:
            return {v: k for k, v in category_id.items()}
        elif category:
            return {"category_id": category_id.get(category, "0")}
        else:
            meta_category = meta.get("category", "")
            is_anime = bool(meta.get("anime")) or bool(meta.get("mal_id"))
            genres = str(meta.get("genres", "")).lower()
            is_animation = is_anime or "animation" in genres
            if meta_category == "TV" and is_animation:
                resolved_id = category_id["TV_ANIM"]
            elif meta_category == "MOVIE" and is_animation:
                resolved_id = category_id["MOVIE_ANIM"]
            else:
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

    def _check_g3mini_specific_dupes(
        self,
        all_dupes: list[dict[str, Any]],
        filtered: list[dict[str, Any]],
        meta: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Re-inject integrale dupes that must always block a G3MINI season-pack upload.

        When uploading a season pack and an existing torrent's name contains
        "integrale" (case-insensitive), that torrent is kept as a blocking dupe
        regardless of language (same rule as TOS).
        """
        is_season_pack = meta.get("tv_pack", False) and meta.get("category") == "TV"
        if not is_season_pack:
            return filtered

        result = list(filtered)
        for dupe in all_dupes:
            if not isinstance(dupe, dict):
                continue
            if "integrale" in dupe.get("name", "").lower():
                if dupe not in result:
                    result.append(dupe)
                stored = next(x for x in result if x == dupe)
                flags: list[str] = stored.setdefault("flags", [])
                if "integrale_supersede" not in flags:
                    flags.append("integrale_supersede")
        return result

    async def search_existing(self, meta: dict[str, Any], _: Any = None) -> list[dict[str, Any]]:
        """Wrap the standard French dupe check with G3MINI's integrale rule."""
        from src.trackers.UNIT3D import UNIT3D as _UNIT3D

        raw_dupes = await _UNIT3D.search_existing(self, meta, _)
        filtered = await self._check_french_lang_dupes(raw_dupes, meta)
        return self._check_g3mini_specific_dupes(raw_dupes, filtered, meta)

    async def get_additional_checks(self, meta: dict[str, Any]) -> bool:
        if not await self._check_french_language(meta, languages_to_check=["french", "fre", "fra", "fr", "français", "francais", "fr-fr", "fr-ca"]):
            return False

        is_encode = not meta.get("is_disc") and meta.get("type") in {"ENCODE", "WEBRIP"}
        video_encode = str(meta.get("video_encode", "")).lower()
        video = next(iter(mi_tracks(meta, "Video")), {})
        settings = str(video.get("Encoded_Library_Settings", "") or "")
        if settings == "{}":
            settings = ""

        # Encoder preset minimums are inferred from the settings x264/x265/AV1 always dump;
        # a missing parameter means the settings are unverifiable and counts as below minimum.
        if is_encode and "x264" in video_encode:
            if not settings:
                return self._rule_failed(meta, "x264_slow_preset", "No encoding settings found in mediainfo — cannot verify x264 preset quality (minimum: 'slow').")
            details = _preset_shortfalls(settings, (("subme", 8), ("trellis", 2)), "slow")
            if details and not self._rule_failed(meta, "x264_slow_preset", "x264 encode quality is below the 'slow' preset minimum.", details):
                return False
        if is_encode and "x265" in video_encode:
            if not settings:
                return self._rule_failed(meta, "x265_medium_preset", "No encoding settings found in mediainfo — cannot verify x265 preset quality (minimum: 'medium').")
            details = _preset_shortfalls(settings, (("subme", 2), ("rd", 3)), "medium")
            if details and not self._rule_failed(meta, "x265_medium_preset", "x265 encode quality is below the 'medium' preset minimum.", details):
                return False
        if is_encode and "av1" in video_encode:
            preset_match = re.search(r"\bpreset\s*[=:]\s*(\d+)", settings, re.IGNORECASE)
            if not preset_match:
                return self._rule_failed(meta, "av1_preset_max_4", "No encoding settings found in mediainfo — cannot verify AV1 preset (maximum: 4).")
            if int(preset_match.group(1)) > 4 and not self._rule_failed(
                meta, "av1_preset_max_4", f"AV1 preset {preset_match.group(1)} is above the allowed maximum of 4 (slower)."
            ):
                return False

        if is_encode:
            for track in mi_tracks(meta, "Audio"):
                fmt = str(track.get("Format", "") or "").upper()
                channels = int(str(track.get("Channels", "0") or "0"))
                if fmt == "MP3" and not self._rule_failed(meta, "no_mp3_audio", "MP3 audio tracks are forbidden on encodes."):
                    return False
                if (
                    fmt == "FLAC"
                    and channels > 2
                    and not self._rule_failed(meta, "flac_stereo_only", f"FLAC audio is only allowed for mono/stereo tracks (found {channels} channels).")
                ):
                    return False

        audio_tag = await self._build_audio_string(meta)
        while audio_tag.startswith("AD."):
            audio_tag = audio_tag[3:]
        if (
            audio_tag.startswith("MULTI")
            and not self._has_french_subs(meta)
            and not self._rule_failed(meta, "multi_needs_french_subs", "A MULTi release requires French subtitles (VO + VF + subs FR).")
        ):
            return False

        for path in meta.get("filelist", []) or []:
            lower = str(path).lower()
            if lower.endswith(_EXTERNAL_SUBS) and not self._rule_failed(
                meta, "no_external_subs", f"External subtitle files are forbidden — subtitles must be muxed into the MKV ({os.path.basename(str(path))})."
            ):
                return False
            if lower.endswith(_ARCHIVES) and not self._rule_failed(meta, "no_archives", f"Archives are forbidden ({os.path.basename(str(path))})."):
                return False

        if is_encode:
            # PGS subtitles pass only when a text subtitle track of the same language exists alongside
            def _lang(track: dict[str, Any]) -> str:
                return str(track.get("Language", "") or "").lower().split("-")[0]

            text_tracks = mi_tracks(meta, "Text")
            text_sub_langs = {_lang(t) for t in text_tracks if "PGS" not in str(t.get("Format", "")).upper()} - {""}
            offending = sorted({_lang(t) or "?" for t in text_tracks if "PGS" in str(t.get("Format", "")).upper() and _lang(t) not in text_sub_langs})
            if offending and not self._rule_failed(
                meta,
                "pgs_only_as_additional",
                f"PGS subtitles are forbidden on encodes unless additional to a text subtitle track — offending language(s): {', '.join(offending)}.",
            ):
                return False

        return True

    # https://gemini-tracker.org/pages/7
    async def get_name(self, meta):
        def replace_spaces_with_dots(text: str) -> str:
            return text.replace(" ", ".")

        def _clean_filename(name):
            # G3MINI keeps title-internal hyphens (WALL·E → WALL-E), so
            # middle dot / bullet map to hyphen instead of space.
            name = name.replace("\u00b7", "-").replace("\u2022", "-")
            # The shared cleaning transliterates accents and expands elisions.
            return self._fr_clean(name)

        type = meta.get("type", "").upper()
        title = meta.get("title", "")
        # French-origin works must carry their French title in the release name.
        if str(meta.get("original_language", "")).lower() == "fr":
            title = await self._get_french_title(meta)
        year = meta.get("year", "")
        manual_year = meta.get("manual_year")
        if manual_year is not None and int(manual_year) > 0:
            year = manual_year
        resolution = meta.get("resolution", "")
        if resolution == "OTHER":
            resolution = ""
        audio = self._get_audio_for_name(meta)  # From G3MINI wiki "Primary audio codec and/or channels number"
        language = await self._build_audio_string(meta)
        language = language.replace("MULTI", "MULTi").replace("VFI", "VFF")
        service = meta.get("service", "")
        season = meta.get("season") or ""
        episode = meta.get("episode") or ""
        part = meta.get("part", "")
        repack = meta.get("repack", "")
        three_d = meta.get("3D", "")
        tag = meta.get("tag", "")
        source = meta.get("source", "")
        # G3MINI never carries the UHD token: it's redundant with 2160p (which
        # already denotes UHD) and invalid on any lower resolution.
        uhd = ""
        # G3MINI spells HDR10+ as HDR10P (no '+' in the tag).
        hdr = meta.get("hdr", "").replace("HDR10+", "HDR10P")
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
            video_encode = meta.get("video_encode", "").replace("H.264", "H264").replace("H.265", "H265")
            # Encodes are labeled by their encoder (x264/x265), never H264/H265.
            # A WEB release typed WEBDL from its filename but whose video track
            # carries x264/x265 encoding settings is really an encode.
            if meta.get("has_encode_settings"):
                video_encode = video_encode.replace("H264", "x264").replace("H265", "x265")
        edition = self._format_edition(meta.get("edition", ""))
        if "hybrid" in edition.upper():
            edition = edition.replace("Hybrid", "").strip()

        if meta["category"] == "TV":
            year = meta.get("year", "") or ""
            if meta.get("manual_date"):
                # Ignore season and year for --daily flagged shows, just use manual date stored in episode_name
                season = ""
                episode = ""
        if meta.get("no_season", False) is True:
            season = ""
        # Season pack: append COMPLETE when uploading a full season without an episode number
        season_ep = season + (" COMPLETE" if meta.get("tv_pack") and season and not episode else episode)
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
                    name = f"{title} {year} {three_d} {edition} {repack} {language} {resolution} {region} {uhd} {source} {hybrid} {hdr} {audio} {video_codec}"
                elif meta["is_disc"] == "DVD":
                    name = f"{title} {year} {repack} {edition} {region} {source} {dvd_size} {audio}"
                elif meta["is_disc"] == "HDDVD":
                    name = f"{title} {year} {edition} {repack} {language} {resolution} {source} {audio} {video_codec}"
            elif type == "REMUX" and source in ("BluRay", "HDDVD"):  # BluRay/HDDVD Remux
                name = f"{title} {year} {three_d} {edition} {repack} {language} {resolution} {uhd} {source} REMUX {hybrid} {hdr} {audio} {video_codec}"
            elif type == "REMUX" and source in ("PAL DVD", "NTSC DVD", "DVD"):  # DVD Remux
                name = f"{title} {year} {edition} {repack} {source} REMUX  {audio}"
            elif type == "ENCODE":  # Encode
                name = f"{title} {year} {edition} {repack} {language} {resolution} {uhd} {source} {hybrid} {hdr} {audio} {video_encode}"
            elif type == "WEBDL":  # WEB-DL
                name = f"{title} {year} {edition} {repack} {language} {resolution} {uhd} {service} {self.WEB_LABEL} {hybrid} {hdr} {audio} {video_encode}"
            elif type == "WEBRIP":  # WEBRip
                name = f"{title} {year} {edition} {repack} {language} {resolution} {uhd} {service} WEBRip {hybrid} {hdr} {audio} {video_encode}"
            elif type == "HDTV":  # HDTV
                name = f"{title} {year} {edition} {repack} {language} {resolution} {source} {audio} {video_encode}"
            elif type == "DVDRIP":
                name = f"{title} {year} {language} {source} DVDRip {audio} {video_encode}"

        elif meta["category"] == "TV":  # TV SPECIFIC
            if type == "DISC":  # Disk
                if meta["is_disc"] == "BDMV":
                    name = f"{title} {year} {season_ep} {three_d} {edition} {repack} {language} {resolution} {region} {uhd} {source} {hybrid} {hdr} {audio} {video_codec}"
                if meta["is_disc"] == "DVD":
                    name = f"{title} {year} {season_ep} {three_d} {repack} {edition} {region} {source} {dvd_size} {audio}"
                elif meta["is_disc"] == "HDDVD":
                    name = f"{title} {year} {season_ep} {three_d} {edition} {repack} {language} {resolution} {source} {audio} {video_codec}"
            elif type == "REMUX" and source in ("BluRay", "HDDVD"):  # BluRay Remux
                name = f"{title} {year} {season_ep} {part} {three_d} {edition} {repack} {language} {resolution} {uhd} {source} REMUX {hybrid} {hdr} {audio} {video_codec}"  # SOURCE
            elif type == "REMUX" and source in ("PAL DVD", "NTSC DVD", "DVD"):  # DVD Remux
                name = f"{title} {year} {season_ep} {part} {edition} {repack} {source} REMUX {audio}"  # SOURCE
            elif type == "ENCODE":  # Encode
                name = f"{title} {year} {season_ep} {part} {edition} {repack} {language} {resolution} {uhd} {source} {hybrid} {hdr} {audio} {video_encode}"  # SOURCE
            elif type == "WEBDL":  # WEB-DL
                name = f"{title} {year} {season_ep} {part} {edition} {repack} {language} {resolution} {uhd} {service} {self.WEB_LABEL} {hybrid} {hdr} {audio} {video_encode}"
            elif type == "WEBRIP":  # WEBRip
                name = f"{title} {year} {season_ep} {part} {edition} {repack} {language} {resolution} {uhd} {service} WEBRip {hybrid} {hdr} {audio} {video_encode}"
            elif type == "HDTV":  # HDTV
                name = f"{title} {year} {season_ep} {part} {edition} {repack} {language} {resolution} {source} {audio} {video_encode}"
            elif type == "DVDRIP":
                name = f"{title} {year} {season_ep} {language} {source} DVDRip {audio} {video_encode}"

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
        # Handle notag: if tag is empty/invalid, use tracker's notag label
        tag_group = tag.strip("-").strip().lower() if tag else ""
        invalid_tags = ["nogrp", "nogroup", "unknown", "unk"]
        if not tag_group or any(inv == tag_group for inv in invalid_tags):
            label = getattr(self, "notag_label", "")
            if label:
                for inv in invalid_tags:
                    name_notag = re.sub(rf"-?{re.escape(inv)}-?", "", name_notag, flags=re.IGNORECASE)
                tag = f"-{label}"
        name = name_notag + tag
        clean_name = _clean_filename(name)
        dot_name = replace_spaces_with_dots(clean_name)
        # Remove isolated hyphens between dots (e.g. "Chainsaw.Man.-.The.Movie" → "Chainsaw.Man.The.Movie")
        dot_name = re.sub(r"\.(-\.)+", ".", dot_name)
        # Collapse consecutive dots and strip boundary dots
        dot_name = re.sub(r"\.{2,}", ".", dot_name)
        # G3MINI convention: codec abbreviation directly concatenated with channel
        # layout — no dot separator.  "DDP.5.1" → "DDP5.1", "DTS.5.1" → "DTS5.1".
        # DTS-HD MA is unaffected: "DTS" is followed by "-" not ".", so \bDTS\. never
        # matches inside "DTS-HD.MA.5.1".
        dot_name = re.sub(r"\b(DDP|EAC3|DD|DTS|FLAC|AAC|MP3|Opus)\.(\d+\.\d+)", r"\1\2", dot_name, flags=re.IGNORECASE)
        dot_name = dot_name.strip(".")
        return {"name": dot_name}
