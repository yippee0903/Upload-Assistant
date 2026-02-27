# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
"""
c411.org — French private tracker (custom API, NOT UNIT3D)

Upload endpoint:  POST https://c411.org/api/torrents
Authentication:   Bearer token
Content-Type:     multipart/form-data

Required fields:  torrent, nfo, title, description, categoryId, subcategoryId
Optional fields:  options (JSON), uploaderNote, tmdbData, rawgData
"""

import asyncio
import contextlib
import json
import os
import re
from datetime import datetime
from typing import Any, Union

import aiofiles
import defusedxml.ElementTree as ET
import httpx
from unidecode import unidecode

from src.console import console
from src.nfo_generator import SceneNfoGenerator
from src.tmdb import TmdbManager
from src.trackers.COMMON import COMMON
from src.trackers.FRENCH import FrenchTrackerMixin

Meta = dict[str, Any]
Config = dict[str, Any]


class C411(FrenchTrackerMixin):
    """c411.org tracker — French private tracker with custom API."""

    def __init__(self, config: Config) -> None:
        self.config: Config = config
        self.tracker: str = "C411"
        self.source_flag: str = "C411"
        self.upload_url: str = "https://c411.org/api/torrents"
        self.torrent_url: str = "https://c411.org/torrents/"
        self.api_key: str = str(self.config["TRACKERS"].get(self.tracker, {}).get("api_key", "")).strip()
        self.tmdb_manager = TmdbManager(config)
        self.banned_groups: list[str] = [""]

    # ──────────────────────────────────────────────────────────
    #  Audio / naming / French title — inherited from FrenchTrackerMixin
    # ──────────────────────────────────────────────────────────
    # _build_audio_string, _get_french_dub_suffix, _get_audio_tracks,
    # _extract_audio_languages, _map_language, _has_french_subs,
    # _detect_truefrench, _detect_vfi, _get_french_title, get_name
    # ──────────────────────────────────────────────────────────

    # C411 does not want the streaming service (NF, AMZN, …) in release names;
    # it should appear in the description instead.
    INCLUDE_SERVICE_IN_NAME: bool = False

    # C411 wiki: UHD is only allowed when the release is REMUX/BDMV/ISO.
    UHD_ONLY_FOR_REMUX_DISC: bool = True

    def _format_name(self, raw_name: str) -> dict[str, str]:
        """C411 override: title-case only the movie/show title portion.

        C411 convention capitalises every word in the title while leaving
        technical tokens (codec, resolution, language, etc.) untouched.

        The title is everything before the first 4-digit year or season
        marker (S01…).  Everything after is left as-is.

        Also normalizes audio codecs to C411 conventions:
          DD → AC3, TrueHD → TRUEHD, DTS-HD MA → DTS.HD.MA, DTS:X → DTS.X

        Examples:
          ``L.Age.De.Glace``  instead of ``L.Age.de.glace``
          ``Hier.J.Arrete``   instead of ``Hier.J.arrete``
        """
        result = super()._format_name(raw_name)
        dot_name = result["name"]

        # ── C411 audio codec normalization ──
        # DD → AC3 (but not DDP which stays as-is)
        dot_name = re.sub(r"\.DD\.", ".AC3.", dot_name)
        # TrueHD → TRUEHD (case normalization)
        dot_name = re.sub(r"\.TrueHD\.", ".TRUEHD.", dot_name, flags=re.IGNORECASE)
        dot_name = re.sub(r"\.TrueHD$", ".TRUEHD", dot_name, flags=re.IGNORECASE)
        # DTS-HD.MA → DTS.HD.MA (dash to dot)
        dot_name = dot_name.replace(".DTS-HD.MA.", ".DTS.HD.MA.")
        dot_name = dot_name.replace(".DTS-HD.HRA.", ".DTS.HD.HRA.")
        # DTS:X → DTS.X (colon to dot)
        dot_name = dot_name.replace(".DTS:X.", ".DTS.X.")
        dot_name = dot_name.replace(".DTSX.", ".DTS.X.")
        # Atmos capitalization
        dot_name = re.sub(r"\.Atmos\.", ".ATMOS.", dot_name, flags=re.IGNORECASE)
        dot_name = re.sub(r"\.Atmos$", ".ATMOS", dot_name, flags=re.IGNORECASE)
        # ATMOS must appear BEFORE the audio codec entirely: DDP.5.1.ATMOS → ATMOS.DDP.5.1
        # Pattern 1: codec.channels.ATMOS → ATMOS.codec.channels
        dot_name = re.sub(r"\.(DDP|AC3|EAC3|DTS|TRUEHD|FLAC|AAC|LPCM|DTS\.HD\.MA|DTS\.HD\.HRA|DTS\.X)\.(\d\.\d)\.ATMOS([.-])", r".ATMOS.\1.\2\3", dot_name, flags=re.IGNORECASE)
        # Pattern 2: codec.ATMOS.channels → ATMOS.codec.channels (in case already partially moved)
        dot_name = re.sub(r"\.(DDP|AC3|EAC3|DTS|TRUEHD|FLAC|AAC|LPCM|DTS\.HD\.MA|DTS\.HD\.HRA|DTS\.X)\.ATMOS\.(\d\.\d)([.-])", r".ATMOS.\1.\2\3", dot_name, flags=re.IGNORECASE)

        # Find where the title ends: first 4-digit year or SXX pattern
        parts = dot_name.split(".")
        title_end = 0
        for j, part in enumerate(parts):
            if re.match(r"^\d{4}$", part) or re.match(r"^S\d{2}", part, re.IGNORECASE):
                title_end = j
                break
        else:
            # No year/season found — title-case everything except group tag
            title_end = len(parts)

        # Title-case only the title segments
        for k in range(title_end):
            parts[k] = parts[k].capitalize()

        result["name"] = ".".join(parts)
        return result

    # ──────────────────────────────────────────────────────────
    #  C411 slot system — 4 profiles, 25 slots per edition
    # ──────────────────────────────────────────────────────────
    #
    #  Compatibilité (2):    COMPAT-01, COMPAT-WR
    #  Home Cinéma Pure (4): PURE-UHD-REMUX, PURE-UHD-BDMV, PURE-BD-REMUX, PURE-BD-BDMV
    #  Home Cinéma Optimisé (12): HCOPT-{1080,2160}-{BD,WR,4KL}-{H265,AV1}[-HDR]
    #  Optimisation (7):     OPTI-{1080,2160}-{HDR,SDR}-{BD,WR,4KL}
    #
    #  Special versions (UNCUT, THEATRICAL, EXTENDED, DIRECTOR'S CUT,
    #  IMAX, Open Matte, Hybrid) each get an independent 25-slot set.
    #
    #  Corrective versions (PROPER, REAL PROPER, REPACK, FIX, RERIP, V2)
    #  are always allowed — they replace the uploader's own previous version.
    #

    # Special editions that get their own independent slot set
    _SPECIAL_EDITIONS = [
        "UNCUT",
        "THEATRICAL",
        "EXTENDED",
        "DIRECTOR'S CUT",
        "DIRECTORS CUT",
        "IMAX",
        "OPEN MATTE",
        "HYBRID",
    ]

    # Corrective version tags — uploads with these bypass dupe blocking
    _CORRECTIVE_TAGS = ["PROPER", "REAL.PROPER", "REPACK", "FIX", "RERIP", "V2"]

    # Audio codecs that are considered lossless
    _LOSSLESS_AUDIO = {"TrueHD", "TrueHD Atmos", "DTS-HD MA", "DTS-HD.MA", "FLAC", "PCM", "LPCM", "DTS:X", "DTS-X"}

    @staticmethod
    def _is_lossless_audio(audio: str) -> bool:
        """Return True if the audio codec string indicates lossless audio."""
        au = audio.upper()
        return any(tag in au for tag in ("TRUEHD", "DTS-HD MA", "DTS-HD.MA", "DTS.HD.MA", "DTSX", "DTS.X", "DTS:X", "DTS-X", "FLAC", "PCM", "LPCM"))

    @staticmethod
    def _is_h264_codec(codec: str) -> bool:
        """Return True if codec is H.264 / AVC."""
        c = codec.upper().replace(".", "").replace(" ", "")
        return c in ("H264", "X264", "AVC")

    @staticmethod
    def _is_av1_codec(codec: str) -> bool:
        """Return True if codec is AV1."""
        return codec.upper().replace(".", "").strip() in ("AV1",)

    @staticmethod
    def _has_hdr(hdr_str: str) -> bool:
        """Return True if HDR metadata is present (HDR10, HDR10+, DV, HLG, etc.)."""
        if not hdr_str:
            return False
        return hdr_str.upper() not in ("", "SDR", "NONE")

    @staticmethod
    def _has_dolby_vision(hdr_str: str) -> bool:
        """Return True if Dolby Vision is present."""
        return "DV" in hdr_str.upper() or "DOLBY VISION" in hdr_str.upper()

    @staticmethod
    def _has_dv_only(hdr_str: str) -> bool:
        """Return True if DV-only (no HDR10/HDR10+ combined)."""
        h = hdr_str.upper()
        has_dv = "DV" in h or "DOLBY VISION" in h
        if not has_dv:
            return False
        # Combined: DV HDR10, DV HDR10+, DV.HDR10, etc.
        return "HDR10" not in h and "HDR10+" not in h and "HDR10PLUS" not in h

    @staticmethod
    def _has_hdr_only(hdr_str: str) -> bool:
        """Return True if HDR-only (no Dolby Vision)."""
        h = hdr_str.upper()
        has_hdr = any(t in h for t in ("HDR10", "HDR", "HLG", "PQ10"))
        has_dv = "DV" in h or "DOLBY VISION" in h
        return has_hdr and not has_dv

    @classmethod
    def _detect_special_edition_from_meta(cls, meta: Meta) -> str:
        """Return normalised edition key from meta, or '' if standard release."""
        edition = str(meta.get("edition", "")).upper()
        if not edition:
            return ""
        for tag in cls._SPECIAL_EDITIONS:
            if tag in edition:
                return tag.replace("'", "").replace(" ", "-")
        return ""

    @classmethod
    def _detect_special_edition_from_name(cls, name: str) -> str:
        """Return normalised edition key parsed from a torrent name, or ''."""
        n = name.upper().replace(".", " ").replace("-", " ").replace("_", " ")
        for tag in cls._SPECIAL_EDITIONS:
            if tag in n:
                return tag.replace("'", "").replace(" ", "-")
        return ""

    @classmethod
    def _is_corrective_version_meta(cls, meta: Meta) -> bool:
        """Return True if the upload is a corrective version (PROPER/REPACK/…)."""
        repack = str(meta.get("repack", "")).upper().replace(" ", ".")
        if not repack:
            return False
        return any(tag in repack for tag in cls._CORRECTIVE_TAGS)

    @classmethod
    def _is_corrective_version_name(cls, name: str) -> bool:
        """Return True if the torrent name indicates a corrective version."""
        n = name.upper().replace("-", ".").replace(" ", ".")
        return any(f".{tag}." in f".{n}." for tag in cls._CORRECTIVE_TAGS)

    @staticmethod
    def _detect_lang_tag_from_name(name: str) -> str:
        """Extract the French language tag from a torrent name.

        Returns one of: MULTI.VF2, VF2, MULTI.VFF, MULTI.VFQ, VFF, VFQ, VOSTFR, ''
        """
        n = name.upper().replace("-", ".").replace(" ", ".")
        tokens = n.split(".")
        token_set = set(tokens)

        has_multi = "MULTI" in token_set
        has_vf2 = "VF2" in token_set
        has_vff = "VFF" in token_set
        has_vfq = "VFQ" in token_set
        has_vostfr = "VOSTFR" in token_set

        if has_multi and has_vf2:
            return "MULTI.VF2"
        if has_vf2:
            return "VF2"
        if has_multi and has_vff:
            return "MULTI.VFF"
        if has_multi and has_vfq:
            return "MULTI.VFQ"
        if has_multi:
            return "MULTI"
        if has_vff:
            return "VFF"
        if has_vfq:
            return "VFQ"
        if has_vostfr:
            return "VOSTFR"
        return ""

    @staticmethod
    def _detect_hdr_type_from_name(name: str) -> str:
        """Return HDR type from torrent name: 'DV+HDR', 'DV', 'HDR', or ''."""
        n = name.upper().replace("-", ".").replace(" ", ".")
        tokens = set(n.split("."))

        has_dv = "DV" in tokens or "DOLBY.VISION" in n or "DOVI" in tokens
        has_hdr = any(t in tokens for t in ("HDR", "HDR10", "HDR10+", "HDR10PLUS", "HLG", "PQ10"))

        if has_dv and has_hdr:
            return "DV+HDR"
        if has_dv:
            return "DV"
        if has_hdr:
            return "HDR"
        return ""

    def _determine_c411_slot(self, meta: Meta) -> str:
        """Determine the C411 slot for an upload based on meta attributes.

        Returns the slot code (e.g., 'PURE-UHD-REMUX', 'COMPAT-01', etc.).
        Special editions are prefixed: 'EXTENDED|PURE-UHD-REMUX'.
        """
        release_type = str(meta.get("type", "")).upper()
        resolution = str(meta.get("resolution", ""))
        is_4k = resolution == "2160p"
        audio = str(meta.get("audio", ""))
        video_codec = str(meta.get("video_codec", ""))
        video_encode = str(meta.get("video_encode", ""))
        codec = video_encode or video_codec
        hdr = str(meta.get("hdr", ""))
        uuid = str(meta.get("uuid", "")).lower()
        is_disc = str(meta.get("is_disc", ""))
        is_4klight = "4klight" in uuid
        # Source-based distinction: BluRay (encode from disc) vs WEB
        is_webrip = release_type == "WEBRIP"

        lossless = self._is_lossless_audio(audio)
        h264 = self._is_h264_codec(codec)
        av1 = self._is_av1_codec(codec)
        has_hdr = self._has_hdr(hdr)
        has_dv = self._has_dolby_vision(hdr)

        # Edition prefix (special versions get independent slot sets)
        edition = self._detect_special_edition_from_meta(meta)
        prefix = f"{edition}|" if edition else ""

        # ── PURE: REMUX / BDMV (lossless, no encoding) ──
        if release_type == "REMUX":
            return f"{prefix}PURE-UHD-REMUX" if is_4k else f"{prefix}PURE-BD-REMUX"
        if release_type == "DISC" or is_disc == "BDMV":
            return f"{prefix}PURE-UHD-BDMV" if is_4k else f"{prefix}PURE-BD-BDMV"

        # ── COMPAT: H.264, 1080p, SDR, Lossy ──
        if h264 and not is_4k and not has_hdr:
            if is_webrip:
                return f"{prefix}COMPAT-WR"
            return f"{prefix}COMPAT-01"

        # ── HCOPT: H.265/AV1, Lossless (fallback lossy), DV+HDR10+ ──
        if lossless or has_dv or av1:
            codec_suffix = "AV1" if av1 else "H265"
            if is_4k:
                if is_4klight:
                    return f"{prefix}HCOPT-2160-4KL-{codec_suffix}"
                if is_webrip:
                    if has_hdr:
                        return f"{prefix}HCOPT-2160-WR-{codec_suffix}-HDR"
                    return f"{prefix}HCOPT-2160-WR-{codec_suffix}"
                return f"{prefix}HCOPT-2160-BD-{codec_suffix}"
            else:
                if is_webrip:
                    return f"{prefix}HCOPT-1080-WR-{codec_suffix}"
                return f"{prefix}HCOPT-1080-BD-{codec_suffix}"

        # ── OPTI: H.265 (H.264 fallback), Lossy only, HDR10 (no DV), 5.1 max ──
        if is_4k:
            if is_4klight:
                return f"{prefix}OPTI-2160-HDR-4KL"
            if has_hdr:
                return f"{prefix}OPTI-2160-HDR"
            else:
                if is_webrip:
                    return f"{prefix}OPTI-2160-SDR-WR"
                return f"{prefix}OPTI-2160-SDR-BD"
        else:
            # 1080p
            if has_hdr:
                return f"{prefix}OPTI-1080-HDR"
            if is_webrip:
                return f"{prefix}OPTI-1080-SDR-WR"
            return f"{prefix}OPTI-1080-SDR-BD"

    @classmethod
    def _determine_c411_slot_from_name(cls, name: str) -> str:
        """Determine the C411 slot from a torrent name.

        Parses resolution, codec, HDR, audio type, source from the dot-separated name.
        Special editions are prefixed: 'EXTENDED|PURE-UHD-REMUX'.
        """
        n = name.upper().replace(" ", ".").replace("-", ".")

        # Edition prefix (special versions get independent slot sets)
        edition = cls._detect_special_edition_from_name(name)
        prefix = f"{edition}|" if edition else ""

        # Resolution
        is_4k = "2160P" in n or "4K" in n or "UHD" in n

        # Type
        is_remux = "REMUX" in n
        is_bdmv = "BDMV" in n or "BD.FULL" in n or "COMPLETE.BLURAY" in n
        is_webrip = "WEBRIP" in n or "WEB.RIP" in n
        is_4klight = "4KLIGHT" in n

        # Codec
        h264 = any(t in n for t in ("H264", "H.264", "X264", "AVC"))
        av1 = "AV1" in n
        # h265 is the default if not h264 and not av1

        # Audio lossless detection
        lossless = any(t in n for t in ("TRUEHD", "TRUE.HD", "DTS.HD.MA", "DTS.HD MA", "DTS-HD.MA", "DTSX", "DTS.X", "DTS-X", "FLAC", "LPCM", "PCM"))

        # HDR / DV
        has_dv = "DV" in n.split(".") or "DOLBY.VISION" in n or "DOVI" in n
        # Be careful: DV could be part of other words, check as token
        if not has_dv:
            tokens = set(n.replace("-", ".").split("."))
            has_dv = "DV" in tokens

        has_hdr = any(t in n for t in ("HDR", "HDR10", "HDR10+", "HDR10PLUS", "HLG", "PQ10"))
        has_hdr = has_hdr or has_dv  # DV implies HDR

        # ── PURE ──
        if is_remux:
            return f"{prefix}PURE-UHD-REMUX" if is_4k else f"{prefix}PURE-BD-REMUX"
        if is_bdmv:
            return f"{prefix}PURE-UHD-BDMV" if is_4k else f"{prefix}PURE-BD-BDMV"

        # ── COMPAT: H.264, 1080p, SDR ──
        if h264 and not is_4k and not has_hdr:
            return f"{prefix}COMPAT-WR" if is_webrip else f"{prefix}COMPAT-01"

        # ── HCOPT or OPTI ──
        if lossless or has_dv or av1:
            # HCOPT profile: lossless audio, DV, or AV1 codec
            codec_suffix = "AV1" if av1 else "H265"
            if is_4k:
                if is_4klight:
                    return f"{prefix}HCOPT-2160-4KL-{codec_suffix}"
                if is_webrip:
                    if has_hdr:
                        return f"{prefix}HCOPT-2160-WR-{codec_suffix}-HDR"
                    return f"{prefix}HCOPT-2160-WR-{codec_suffix}"
                return f"{prefix}HCOPT-2160-BD-{codec_suffix}"
            else:
                if is_webrip:
                    return f"{prefix}HCOPT-1080-WR-{codec_suffix}"
                return f"{prefix}HCOPT-1080-BD-{codec_suffix}"

        # ── OPTI: lossy, H.265 default ──
        if is_4k:
            if is_4klight:
                return f"{prefix}OPTI-2160-HDR-4KL"
            if has_hdr:
                return f"{prefix}OPTI-2160-HDR"
            else:
                if is_webrip:
                    return f"{prefix}OPTI-2160-SDR-WR"
                return f"{prefix}OPTI-2160-SDR-BD"
        else:
            if has_hdr:
                return f"{prefix}OPTI-1080-HDR"
            if is_webrip:
                return f"{prefix}OPTI-1080-SDR-WR"
            return f"{prefix}OPTI-1080-SDR-BD"

    # ──────────────────────────────────────────────────────────
    #  C411 API field mapping
    # ──────────────────────────────────────────────────────────

    def _get_category_subcategory(self, meta: Meta) -> tuple[int, int]:
        """Map meta category to C411 categoryId + subcategoryId.

        C411 categories (main):
          categoryId 1 (Vidéos) → subcategoryId 1=Anime Film, 2=Anime TV,
                                                   6=Films, 7=Séries TV
          categoryId 3 (Musique) → 18=Albums
          categoryId 5 (Jeux)    → 36=PC
        """
        # Detect animation: anime flag, mal_id, or animation genre
        is_anime = bool(meta.get("anime")) or bool(meta.get("mal_id"))
        genres = str(meta.get("genres", "")).lower()
        is_animation = is_anime or "animation" in genres

        if meta.get("category") == "TV":
            return (1, 2) if is_animation else (1, 7)
        return (1, 1) if is_animation else (1, 6)

    def _get_quality_option_id(self, meta: Meta) -> Union[int, None]:
        """Map resolution + source + type to C411 quality option (Type 2).

        C411 quality option IDs:
          DISC:    10=BluRay 4K Full  11=BluRay Full  14=DVD
          REMUX:   10=BluRay 4K Remux 12=BluRay Remux 15=DVD Remux
          ENCODE:  17=4K  16=1080p  18=720p
          WEBDL:   26=4K  25=1080p  27=720p  24=other
          WEBRIP:  30=4K  29=1080p  31=720p  28=other
          HDTV:    21=4K  20=1080p  22=720p  19=other
          DVDRIP:  15
          Special: 415=4KLight  413=HDLight 1080  414=HDLight other
        """
        type_val = meta.get("type", "").upper()
        res = meta.get("resolution", "")
        source = meta.get("source", "")
        is_4k = res == "2160p"
        uuid = meta.get("uuid", "").lower()

        # ── Special tags override (detected from filename) ──
        if "4klight" in uuid:
            return 415
        if "hdlight" in uuid:
            return 413 if "1080" in res else 414

        # ── DISC ──
        if type_val == "DISC":
            if meta.get("is_disc") == "DVD":
                return 14
            # BDMV / HDDVD
            return 10 if is_4k else 11

        # ── REMUX ──
        if type_val == "REMUX":
            if source in ("PAL DVD", "NTSC DVD", "DVD"):
                return 15
            return 10 if is_4k else 12

        # ── ENCODE ──
        if type_val == "ENCODE":
            if is_4k:
                return 17
            if "1080" in res:
                return 16
            if "720" in res:
                return 18
            return 16  # fallback

        # ── WEBDL ──
        if type_val == "WEBDL":
            if is_4k:
                return 26
            if "1080" in res:
                return 25
            if "720" in res:
                return 27
            return 24

        # ── WEBRIP ──
        if type_val == "WEBRIP":
            if is_4k:
                return 30
            if "1080" in res:
                return 29
            if "720" in res:
                return 31
            return 28

        # ── HDTV ──
        if type_val == "HDTV":
            if is_4k:
                return 21
            if "1080" in res:
                return 20
            if "720" in res:
                return 22
            return 19

        # ── DVDRIP ──
        if type_val == "DVDRIP":
            return 15

        return None

    def _get_language_option_id(self, language_tag: str) -> Union[int, None]:
        """Map C411 language tag to API option value (Type 1).

        1=Anglais  2=Français(VFF)  4=Multi(FR inclus)
        6=Québécois(VFQ)  8=VOSTFR  422=Multi VF2(FR+QC)
        """
        tag_map: dict[str, int] = {
            "MULTI.VF2": 422,
            "MULTI.VFF": 4,
            "MULTI.VFQ": 4,
            "MULTI.VOF": 4,
            "MULTI.TRUEFRENCH": 4,
            "MULTI": 4,
            "TRUEFRENCH": 2,
            "VOF": 2,
            "VFF": 2,
            "VFI": 2,
            "VFQ": 6,
            "VOSTFR": 8,
        }
        return tag_map.get(language_tag, 1)  # default: 1 (Anglais)

    def _get_season_episode_options(self, meta: Meta) -> dict[str, int]:
        """Map season/episode to C411 option types 7 and 6.

        Type 7 (Saison):   118=Intégrale, 121…150 → S01…S30
        Type 6 (Épisode):  96=Saison complète, 97…116 → E01…E20
        """
        opts: dict[str, int] = {}

        if meta.get("category") != "TV":
            return opts

        # Season option (Type 7)
        season_str = str(meta.get("season", "")).strip()
        if season_str:
            m = re.search(r"S(\d+)", season_str, re.IGNORECASE)
            if m:
                snum = int(m.group(1))
                if 1 <= snum <= 30:
                    opts["7"] = 120 + snum  # S01 → 121 … S30 → 150
                else:
                    opts["7"] = 118  # Intégrale (fallback)

        # Episode option (Type 6)
        episode_str = str(meta.get("episode", "")).strip()
        if episode_str:
            m = re.search(r"E(\d+)", episode_str, re.IGNORECASE)
            if m:
                enum_val = int(m.group(1))
                if 1 <= enum_val <= 20:
                    opts["6"] = 96 + enum_val  # E01 → 97 … E20 → 116
        elif season_str and not episode_str:
            # Season pack → "Saison complète"
            if meta.get("tv_pack", 0):
                opts["6"] = 96  # Saison complète

        return opts

    def _build_options(self, meta: Meta, language_tag: str) -> dict[str, Any]:
        """Build C411 options JSON: {"typeId": value_or_array, …}

        Type 1 (Langue)  → array   e.g. [4]
        Type 2 (Qualité) → scalar  e.g. 25
        Type 6 (Épisode) → scalar
        Type 7 (Saison)  → scalar
        """
        options: dict[str, Any] = {}

        # Type 1 — Language
        lang_id = self._get_language_option_id(language_tag)
        if lang_id is not None:
            options["1"] = [lang_id]

        # Type 2 — Quality
        quality_id = self._get_quality_option_id(meta)
        if quality_id is not None:
            options["2"] = quality_id

        # Types 6 & 7 — Episode & Season
        se_opts = self._get_season_episode_options(meta)
        options.update(se_opts)

        return options

    # ──────────────────────────────────────────────────────────
    #  Description builder   (BBCode — matches C411 site template)
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def _format_french_date(date_str: str) -> str:
        """Format YYYY-MM-DD to French full date, e.g. 'jeudi 15 juillet 2010'."""
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            days = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
            months = [
                "",
                "janvier",
                "février",
                "mars",
                "avril",
                "mai",
                "juin",
                "juillet",
                "août",
                "septembre",
                "octobre",
                "novembre",
                "décembre",
            ]
            return f"{days[dt.weekday()]} {dt.day} {months[dt.month]} {dt.year}"
        except (ValueError, IndexError):
            return date_str

    async def _build_description(self, meta: Meta) -> str:
        """Build C411-compliant BBCode description matching site template.

        Uses the C411 site template with [color=#3d85c6] section headers,
        [font=Verdana][size=14] content blocks, French date formatting,
        genre tag links, writers, and spectator rating with SVG badge.
        """
        C = "#3d85c6"  # C411 accent colour
        parts: list[str] = []

        # ── Fetch French TMDB data (with credits) ──
        fr_data: dict[str, Any] = {}
        with contextlib.suppress(Exception):
            fr_data = await self.tmdb_manager.get_tmdb_localized_data(meta, data_type="main", language="fr", append_to_response="credits") or {}

        fr_title = str(fr_data.get("title", "") or meta.get("title", "")).strip()
        fr_overview = str(fr_data.get("overview", "")).strip()
        year = meta.get("year", "")

        # ── Header: Title + Year + Poster (centered) ──
        poster = meta.get("poster", "") or ""
        poster_w500 = poster
        if "image.tmdb.org/t/p/" in poster:
            poster_w500 = re.sub(r"/t/p/[^/]+/", "/t/p/w500/", poster)

        parts.append(f"[center][b][font=Verdana][color={C}][size=28]{fr_title} ({year})[/size][/color][/font][/b]")
        if poster_w500:
            parts.append(f"[img]{poster_w500}[/img]")
        parts.append("[/center]")
        parts.append("")

        # ══════════════════════════════════════════════════════
        #  Informations
        # ══════════════════════════════════════════════════════
        parts.append(f"        [color={C}]Informations[/color]")

        info_lines: list[str] = []

        # Original title (when different from French title)
        original_title = str(meta.get("original_title", "") or meta.get("title", "")).strip()
        if original_title and original_title != fr_title:
            info_lines.append(f"[b][color={C}]Titre original :[/color][/b] [i]{original_title}[/i]")

        # Country
        countries = fr_data.get("production_countries", meta.get("production_countries", []))
        if countries and isinstance(countries, list):
            names = [c.get("name", "") for c in countries if isinstance(c, dict) and c.get("name")]
            if names:
                info_lines.append(f"[b][color={C}]Pays :[/color][/b] [i]{', '.join(names)}[/i]")

        # Genres (French names with tag links)
        genres_list = fr_data.get("genres", [])
        if genres_list and isinstance(genres_list, list):
            links = []
            for g in genres_list:
                if isinstance(g, dict) and g.get("name"):
                    gn = g["name"]
                    links.append(f"[url=/torrents?tags={gn}]{gn}[/url]")
            if links:
                info_lines.append(f"[b][color={C}]Genres :[/color][/b] [i]{', '.join(links)}[/i]")
        elif meta.get("genres"):
            info_lines.append(f"[b][color={C}]Genres :[/color][/b] [i]{meta['genres']}[/i]")

        # Release date (French full format)
        release_date = str(fr_data.get("release_date", "") or meta.get("release_date", "") or meta.get("first_air_date", "")).strip()
        if release_date:
            info_lines.append(f"[b][color={C}]Date de sortie :[/color][/b] [i]{self._format_french_date(release_date)}[/i]")
        elif year:
            info_lines.append(f"[b][color={C}]Date de sortie :[/color][/b] [i]{year}[/i]")

        # Runtime
        runtime = fr_data.get("runtime") or meta.get("runtime", 0)
        if runtime:
            h, m = divmod(int(runtime), 60)
            dur = f"{h}h{m:02d}" if h > 0 else f"{m}min"
            info_lines.append(f"[b][color={C}]Durée :[/color][/b] [i]{dur}[/i]")

        # blank line before crew block
        info_lines.append("")

        # Credits from TMDB
        credits = fr_data.get("credits", {})
        crew = credits.get("crew", []) if isinstance(credits, dict) else []
        cast = credits.get("cast", []) if isinstance(credits, dict) else []

        # Directors
        directors = [p["name"] for p in crew if isinstance(p, dict) and p.get("job") == "Director" and p.get("name")]
        if not directors:
            meta_dirs = meta.get("tmdb_directors", [])
            if isinstance(meta_dirs, list):
                directors = [d.get("name", d) if isinstance(d, dict) else str(d) for d in meta_dirs]
        if directors:
            label = "Réalisateur" if len(directors) == 1 else "Réalisateurs"
            info_lines.append(f"[b][color={C}]{label} :[/color][/b] [i]{', '.join(directors)}[/i]")

        # Writers / Scénaristes
        seen_w: set[str] = set()
        writers: list[str] = []
        for p in crew:
            if isinstance(p, dict) and p.get("job") in ("Screenplay", "Writer", "Story") and p.get("name") and p["name"] not in seen_w:
                writers.append(p["name"])
                seen_w.add(p["name"])
        if writers:
            label = "Scénariste" if len(writers) == 1 else "Scénaristes"
            info_lines.append(f"[b][color={C}]{label} :[/color][/b] [i]{', '.join(writers)}[/i]")

        # Actors (top 5)
        actors = [p["name"] for p in cast[:5] if isinstance(p, dict) and p.get("name")]
        if not actors:
            meta_cast = meta.get("tmdb_cast", [])
            if isinstance(meta_cast, list):
                actors = [a.get("name", "") if isinstance(a, dict) else str(a) for a in meta_cast[:5]]
                actors = [n for n in actors if n]
        if actors:
            info_lines.append(f"[b][color={C}]Acteurs :[/color][/b] [i]{', '.join(actors)}[/i]")

        # blank line before rating
        info_lines.append("")

        # Spectator rating
        vote_avg = fr_data.get("vote_average") or meta.get("vote_average")
        vote_count = fr_data.get("vote_count") or meta.get("vote_count")
        if vote_avg and vote_count:
            score = round(float(vote_avg) * 10)
            info_lines.append(f"[b][color={C}]Note des spectateurs :[/color][/b] [img]https://img.streetprez.com/note/{score}.svg[/img] [i]{vote_avg} ({vote_count})[/i]")

        # External links (IMDb, TMDB, TVDB, TVmaze, MAL)
        ext_links: list[str] = []
        imdb_id = meta.get("imdb_id", 0)
        if imdb_id and int(imdb_id) > 0:
            imdb_url = meta.get("imdb_info", {}).get("imdb_url", "") if isinstance(meta.get("imdb_info"), dict) else ""
            if not imdb_url:
                imdb_url = f"https://www.imdb.com/title/tt{str(imdb_id).zfill(7)}/"
            ext_links.append(f"[url={imdb_url}]IMDb[/url]")
        tmdb_id_val = meta.get("tmdb", "")
        if tmdb_id_val:
            tmdb_cat = "movie" if meta.get("category", "").upper() != "TV" else "tv"
            ext_links.append(f"[url=https://www.themoviedb.org/{tmdb_cat}/{tmdb_id_val}]TMDB[/url]")
        if meta.get("tvdb_id"):
            ext_links.append(f"[url=https://www.thetvdb.com/?id={meta['tvdb_id']}&tab=series]TVDB[/url]")
        if meta.get("tvmaze_id"):
            ext_links.append(f"[url=https://www.tvmaze.com/shows/{meta['tvmaze_id']}]TVmaze[/url]")
        if meta.get("mal_id"):
            ext_links.append(f"[url=https://myanimelist.net/anime/{meta['mal_id']}]MAL[/url]")
        if ext_links:
            info_lines.append("")
            info_lines.append(" | ".join(ext_links))

        # Wrap info block in [font=Verdana][size=14] … [/size][/font]
        if info_lines:
            parts.append(f"    [font=Verdana][size=14]{info_lines[0]}")
            parts.extend(info_lines[1:])
            parts.append("")
            parts.append("[/size][/font]")

        parts.append("")

        # ══════════════════════════════════════════════════════
        #  Synopsis
        # ══════════════════════════════════════════════════════
        parts.append(f"        [color={C}]Synopsis[/color]")
        synopsis = fr_overview or str(meta.get("overview", "")).strip() or "Aucun synopsis disponible."
        parts.append(f"    [font=Verdana][size=14]{synopsis}[/size][/font]")
        parts.append("")

        # ══════════════════════════════════════════════════════
        #  Informations techniques
        # ══════════════════════════════════════════════════════
        parts.append(f"        [color={C}]Informations techniques[/color]")

        mi_text = await self._get_mediainfo_text(meta)

        tech_lines: list[str] = []

        # Type (Remux, Encode, WEB-DL, …)
        type_label = self._get_type_label(meta)
        if type_label:
            tech_lines.append(f"[b][color={C}]Type :[/color][/b] {type_label}")

        # Source
        source = meta.get("source", "") or meta.get("type", "")
        tech_lines.append(f"[b][color={C}]Source :[/color][/b] {source}" if source else f"[b][color={C}]Source :[/color][/b]")

        # Streaming service (NF, AMZN, DSNP, …) — not in release name, shown here
        service = meta.get("service", "")
        if service:
            tech_lines.append(f"[b][color={C}]Service :[/color][/b] {service}")

        # Resolution
        resolution = meta.get("resolution", "")
        tech_lines.append(f"[b][color={C}]Résolution :[/color][/b] {resolution}" if resolution else f"[b][color={C}]Résolution :[/color][/b]")

        # Container format (MKV, AVI, …)
        container_display = self._format_container(mi_text)
        if container_display:
            tech_lines.append(f"[b][color={C}]Format vidéo :[/color][/b] {container_display}")

        # Video codec – prefer the encode label (H264/x264/…) which matches the release name,
        # falling back to the raw MediaInfo format (AVC/HEVC) for REMUX/DISC types.
        # When both exist and differ, append the raw format in parentheses: "H265 (HEVC)".
        video_codec = (meta.get("video_encode", "").strip() or meta.get("video_codec", "")).strip()
        video_codec = video_codec.replace("H.264", "H264").replace("H.265", "H265")
        raw_codec = meta.get("video_codec", "").strip()
        if video_codec and raw_codec and raw_codec != video_codec:
            video_codec = f"{video_codec} ({raw_codec})"
        tech_lines.append(f"[b][color={C}]Codec vidéo :[/color][/b] {video_codec}" if video_codec else f"[b][color={C}]Codec vidéo :[/color][/b]")

        # HDR / Dolby Vision
        hdr_dv_badge = self._format_hdr_dv_bbcode(meta)
        if hdr_dv_badge:
            tech_lines.append(f"[b][color={C}]HDR :[/color][/b] {hdr_dv_badge}")

        # Video bitrate
        vbr = ""
        if mi_text:
            vbr_match = re.search(r"(?:^|\n)Bit rate\s*:\s*(.+?)\s*(?:\n|$)", mi_text)
            if vbr_match:
                vbr = vbr_match.group(1).strip()
        tech_lines.append(f"[b][color={C}]Débit vidéo :[/color][/b] {vbr}" if vbr else f"[b][color={C}]Débit vidéo :[/color][/b]")

        # First line indented, rest flush
        parts.append(f"    {tech_lines[0]}")
        parts.extend(tech_lines[1:])

        parts.append("")

        # ══════════════════════════════════════════════════════
        #  Audio(s)
        # ══════════════════════════════════════════════════════
        parts.append(f"        [color={C}]Audio(s)[/color]")
        audio_lines = self._format_audio_bbcode(mi_text, meta)
        if audio_lines:
            parts.extend(f"    [i]{al}[/i]" for al in audio_lines)
        else:
            parts.append("    [i]Non spécifié[/i]")
        parts.append("")

        # ══════════════════════════════════════════════════════
        #  Sous-titre(s)
        # ══════════════════════════════════════════════════════
        parts.append(f"        [color={C}]Sous-titre(s)[/color]")
        sub_lines = self._format_subtitle_bbcode(mi_text, meta)
        if sub_lines:
            parts.extend(f"    [i]{sl}[/i]" for sl in sub_lines)
        else:
            parts.append("    [i]Aucun[/i]")
        parts.append("")

        # ══════════════════════════════════════════════════════
        #  Release
        # ══════════════════════════════════════════════════════
        parts.append(f"        [color={C}]Release[/color]")

        rel_lines: list[str] = []

        release_name = meta.get("uuid", "")
        rel_lines.append(f"[b][color={C}]Titre :[/color][/b] {release_name}" if release_name else f"[b][color={C}]Titre :[/color][/b]")

        # Total size
        size_str = self._get_total_size(meta, mi_text)
        rel_lines.append(f"[b][color={C}]Taille totale :[/color][/b] {size_str}" if size_str else f"[b][color={C}]Taille totale :[/color][/b]")

        # File count
        file_count = self._count_files(meta)
        rel_lines.append(f"[b][color={C}]Nombre de fichier(s) :[/color][/b] {file_count}" if file_count else f"[b][color={C}]Nombre de fichier(s) :[/color][/b]")

        # Release group
        group = self._get_release_group(meta)
        if group:
            rel_lines.append(f"[b][color={C}]Groupe :[/color][/b] {group}")

        parts.append(f"    {rel_lines[0]}")
        parts.extend(rel_lines[1:])

        parts.append("")

        # ── Captures d'écran  (opt-in via config: include_screenshots) ──
        include_screens = self.config["TRACKERS"].get(self.tracker, {}).get("include_screenshots", False)
        image_list: list[dict[str, Any]] = meta.get("image_list", []) if include_screens else []
        if image_list:
            parts.append(f"        [color={C}]Captures d'écran[/color]")
            parts.append("")
            img_lines: list[str] = []
            for img in image_list:
                raw = img.get("raw_url", "")
                web = img.get("web_url", "")
                if raw:
                    if web:
                        img_lines.append(f"[url={web}][img]{raw}[/img][/url]")
                    else:
                        img_lines.append(f"[img]{raw}[/img]")
            if img_lines:
                parts.append("[center]")
                parts.append("\n".join(img_lines))
                parts.append("[/center]")

        # ── UA Signature ──
        ua_sig = meta.get("ua_signature", "Created by Upload Assistant")
        parts.append("")
        parts.append(f"[right][url=https://github.com/yippee0903/Upload-Assistant][size=1]{ua_sig}[/size][/url][/right]")

        return "\n".join(parts)

    @staticmethod
    def _patch_mi_filename(mi_text: str, new_name: str) -> str:
        """Replace the ‘Complete name’ value in MediaInfo text with *new_name*.

        C411’s API validates that the filename inside the uploaded MediaInfo
        matches the release name.  Since we rename releases (language tags,
        -NOTAG label, French title…) the original filename no longer matches.
        This patches the ‘Complete name’ line while preserving the file extension.
        """
        if not mi_text or not new_name:
            return mi_text

        def _replace_complete_name(match: re.Match[str]) -> str:
            prefix = match.group(1)  # "Complete name    : "
            old_value = match.group(2)
            ext_match = re.search(r"(\.[a-zA-Z0-9]{2,4})$", old_value)
            ext = ext_match.group(1) if ext_match else ""
            return f"{prefix}{new_name}{ext}"

        return re.sub(
            r"^(Complete name\s*:\s*)(.+)$",
            _replace_complete_name,
            mi_text,
            count=1,
            flags=re.MULTILINE,
        )

    async def _get_mediainfo_text(self, meta: Meta) -> str:
        """Read MediaInfo text from temp files.

        The ‘Complete name’ line is patched to match the C411-generated
        release name so that the API filename-consistency check passes.
        """
        base = os.path.join(meta.get("base_dir", ""), "tmp", meta.get("uuid", ""))
        content = ""

        # Prefer clean-path, then standard mediainfo
        for fname in ("MEDIAINFO_CLEANPATH.txt", "MEDIAINFO.txt"):
            fpath = os.path.join(base, fname)
            if os.path.exists(fpath):
                async with aiofiles.open(fpath, encoding="utf-8") as f:
                    content = await f.read()
                    if content.strip():
                        break
                    content = ""

        # BDInfo for disc releases
        if not content and meta.get("bdinfo") is not None:
            bd_path = os.path.join(base, "BD_SUMMARY_00.txt")
            if os.path.exists(bd_path):
                async with aiofiles.open(bd_path, encoding="utf-8") as f:
                    return await f.read()

        if not content:
            return ""

        # Patch “Complete name” to match the tracker-generated release name
        try:
            name_result = await self.get_name(meta)
            tracker_release_name = name_result.get("name", "") if isinstance(name_result, dict) else str(name_result)
            if tracker_release_name:
                content = self._patch_mi_filename(content, tracker_release_name)
        except Exception:
            pass  # If naming fails, return unpatched MI

        return content

    async def _build_tmdb_data(self, meta: Meta) -> Union[str, None]:
        """Build tmdbData JSON string for C411.

        The format must match the C411 internal TMDB schema as returned
        by ``/api/tmdb/search``.  We fetch full details from TMDB API
        (with credits + keywords) in French to populate all fields.

        Required keys:  id, type, title, originalTitle, overview,
                        posterUrl, backdropUrl, releaseDate, year,
                        runtime, rating, ratingCount, genreIds, genres,
                        directors, writers, cast, countries, languages,
                        productionCompanies, keywords, status, tagline,
                        imdbId
        """
        tmdb_id = meta.get("tmdb")
        if not tmdb_id:
            return None

        media_type = "tv" if meta.get("category", "").upper() == "TV" else "movie"

        # Fetch full TMDB data with credits + keywords in French
        tmdb_full = await self._fetch_tmdb_full(meta, media_type)

        tmdb_data: dict[str, Any] = {
            "id": int(tmdb_id),
            "type": media_type,
        }

        # imdbId (tt-prefixed string)
        imdb_id = tmdb_full.get("imdb_id") or ""
        if imdb_id:
            tmdb_data["imdbId"] = str(imdb_id)
        elif meta.get("imdb_id"):
            raw = meta["imdb_id"]
            tmdb_data["imdbId"] = f"tt{raw}" if not str(raw).startswith("tt") else str(raw)

        # Title + original title
        tmdb_data["title"] = tmdb_full.get("title") or tmdb_full.get("name") or meta.get("title", "")
        tmdb_data["originalTitle"] = tmdb_full.get("original_title") or tmdb_full.get("original_name") or meta.get("original_title", tmdb_data["title"])

        # Overview (prefer French from API)
        tmdb_data["overview"] = tmdb_full.get("overview") or meta.get("overview", "")

        # Poster URL (w500 like C411 uses)
        poster_path = tmdb_full.get("poster_path") or ""
        if poster_path:
            tmdb_data["posterUrl"] = f"https://image.tmdb.org/t/p/w500{poster_path}"
        else:
            poster = meta.get("poster", "") or ""
            if poster.startswith("https://"):
                tmdb_data["posterUrl"] = poster
            elif poster:
                tmdb_data["posterUrl"] = f"https://image.tmdb.org/t/p/w500{poster}" if poster.startswith("/") else f"https://image.tmdb.org/t/p/w500/{poster}"

        # Backdrop URL (w1280 like C411 uses)
        backdrop_path = tmdb_full.get("backdrop_path") or ""
        if backdrop_path:
            tmdb_data["backdropUrl"] = f"https://image.tmdb.org/t/p/w1280{backdrop_path}"
        else:
            tmdb_data["backdropUrl"] = None

        # Release date + year
        release_date = tmdb_full.get("release_date") or tmdb_full.get("first_air_date") or meta.get("release_date") or ""
        if release_date:
            tmdb_data["releaseDate"] = str(release_date)
        elif meta.get("year"):
            tmdb_data["releaseDate"] = f"{meta['year']}-01-01"

        year = meta.get("year")
        if year:
            tmdb_data["year"] = int(year)
        elif release_date and len(release_date) >= 4:
            tmdb_data["year"] = int(release_date[:4])
        else:
            tmdb_data["year"] = None

        # Runtime
        runtime = tmdb_full.get("runtime") or meta.get("runtime", 0)
        tmdb_data["runtime"] = int(runtime) if runtime else None

        # Rating + ratingCount
        tmdb_data["rating"] = float(tmdb_full.get("vote_average", 0) or 0)
        tmdb_data["ratingCount"] = int(tmdb_full.get("vote_count", 0) or 0)

        # Genres (names as strings) + genreIds
        raw_genres = tmdb_full.get("genres", [])
        tmdb_data["genres"] = [g["name"] for g in raw_genres if isinstance(g, dict) and "name" in g]
        tmdb_data["genreIds"] = [g["id"] for g in raw_genres if isinstance(g, dict) and "id" in g]

        # Credits
        credits = tmdb_full.get("credits", {})
        crew = credits.get("crew", [])
        cast_list = credits.get("cast", [])

        tmdb_data["directors"] = [p["name"] for p in crew if p.get("job") == "Director"]
        tmdb_data["writers"] = [p["name"] for p in crew if p.get("department") == "Writing"][:5]
        tmdb_data["cast"] = [{"name": p["name"], "character": p.get("character", "")} for p in cast_list[:5]]

        # Countries
        countries = tmdb_full.get("production_countries", [])
        tmdb_data["countries"] = [c["name"] for c in countries if isinstance(c, dict) and "name" in c]

        # Languages
        languages = tmdb_full.get("spoken_languages", [])
        tmdb_data["languages"] = [lang.get("english_name") or lang.get("name", "") for lang in languages if isinstance(lang, dict)]

        # Production companies
        companies = tmdb_full.get("production_companies", [])
        tmdb_data["productionCompanies"] = [c["name"] for c in companies if isinstance(c, dict) and "name" in c]

        # Status + tagline
        tmdb_data["status"] = tmdb_full.get("status", "")
        tmdb_data["tagline"] = tmdb_full.get("tagline", "")

        # Keywords
        kw_container = tmdb_full.get("keywords", {})
        # Movies use 'keywords', TV shows use 'results'
        kw_list = kw_container.get("keywords", []) or kw_container.get("results", [])
        tmdb_data["keywords"] = [kw["name"] for kw in kw_list if isinstance(kw, dict) and "name" in kw]

        return json.dumps(tmdb_data, ensure_ascii=False)

    async def _fetch_tmdb_full(self, meta: Meta, media_type: str) -> dict[str, Any]:
        """Fetch full TMDB details with credits and keywords in French."""
        tmdb_id = meta.get("tmdb")
        if not tmdb_id:
            return {}

        endpoint = media_type  # 'movie' or 'tv'
        url = f"https://api.themoviedb.org/3/{endpoint}/{tmdb_id}"
        params = {
            "api_key": self.config.get("DEFAULT", {}).get("tmdb_api", ""),
            "language": "fr-FR",
            "append_to_response": "credits,keywords",
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, params=params)
                if response.status_code == 200:
                    return response.json()
                else:
                    console.print(f"[yellow]C411: TMDB API returned {response.status_code} for {endpoint}/{tmdb_id}[/yellow]")
        except httpx.RequestError as e:
            console.print(f"[yellow]C411: TMDB API request failed: {e}[/yellow]")

        return {}

    # ──────────────────────────────────────────────────────────
    #  NFO generation
    # ──────────────────────────────────────────────────────────

    async def _get_or_generate_nfo(self, meta: Meta) -> Union[str, None]:
        """Generate a MediaInfo-based NFO for the upload.

        C411 requires an NFO file for every upload.  The NFO field is the
        only way to send MediaInfo to C411, so we **always** generate one
        from MediaInfo — even when an original scene NFO is present.
        Scene NFOs are only relevant for trackers that explicitly require
        them (e.g. TOS).
        """
        nfo_gen = SceneNfoGenerator(self.config)
        return await nfo_gen.generate_nfo(meta, self.tracker)

    # ──────────────────────────────────────────────────────────
    #  Upload / Search interface
    # ──────────────────────────────────────────────────────────

    async def upload(self, meta: Meta, _disctype: str) -> bool:
        """Upload torrent to c411.org.

        POST https://c411.org/api/torrents
          Authorization: Bearer <api_key>
          Content-Type:  multipart/form-data

        Required fields: torrent, nfo, title, description, categoryId, subcategoryId
        Optional fields: options, uploaderNote, tmdbData, rawgData
        """
        common = COMMON(config=self.config)
        await common.create_torrent_for_upload(meta, self.tracker, self.source_flag)

        # ── Build release name ──
        name_result = await self.get_name(meta)
        title = name_result.get("name", "") if isinstance(name_result, dict) else str(name_result)

        # ── Language tag (for options) ──
        language_tag = await self._build_audio_string(meta)

        # ── Read torrent file ──
        torrent_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}].torrent"
        async with aiofiles.open(torrent_path, "rb") as f:
            torrent_bytes = await f.read()

        # ── NFO file (required by C411) ──
        nfo_path = await self._get_or_generate_nfo(meta)
        nfo_bytes = b""
        if nfo_path and os.path.exists(nfo_path):
            async with aiofiles.open(nfo_path, "rb") as f:
                nfo_bytes = await f.read()
            # Patch "Complete name" in NFO to match the tracker release name
            if title and nfo_bytes:
                try:
                    nfo_text = nfo_bytes.decode("utf-8", errors="replace")
                    nfo_text = self._patch_mi_filename(nfo_text, title)
                    nfo_bytes = nfo_text.encode("utf-8")
                except Exception:
                    pass  # If patching fails, upload unpatched NFO
        else:
            console.print("[yellow]C411: No NFO available — upload may be rejected[/yellow]")

        # ── Description ──
        description = await self._build_description(meta)

        # ── Category / Subcategory ──
        cat_id, subcat_id = self._get_category_subcategory(meta)

        # ── Options JSON ──
        options = self._build_options(meta, language_tag)
        options_json = json.dumps(options, ensure_ascii=False)

        # ── TMDB data ──
        tmdb_data = await self._build_tmdb_data(meta)

        # ── Multipart form ──
        files: dict[str, tuple[str, bytes, str]] = {
            "torrent": ("torrent.torrent", torrent_bytes, "application/x-bittorrent"),
            "nfo": ("release.nfo", nfo_bytes, "application/octet-stream"),
        }

        data: dict[str, Any] = {
            "title": title,
            "description": description,
            "categoryId": str(cat_id),
            "subcategoryId": str(subcat_id),
            "options": options_json,
        }

        if tmdb_data:
            data["tmdbData"] = tmdb_data

        headers: dict[str, str] = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
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
                                    console.print(f"[yellow]C411 upload failed: {error_msg}[/yellow]")
                                    return False

                                # Extract torrent_id for the standard URL output
                                torrent_id = None
                                if isinstance(response_data, dict):
                                    data_block = response_data.get("data", {})
                                    if isinstance(data_block, dict):
                                        torrent_id = data_block.get("id") or data_block.get("slug") or data_block.get("infoHash")
                                if torrent_id:
                                    meta["tracker_status"][self.tracker]["torrent_id"] = torrent_id
                                meta["tracker_status"][self.tracker]["status_message"] = response_data
                                return True
                            except json.JSONDecodeError:
                                meta["tracker_status"][self.tracker]["status_message"] = "data error: C411 JSON decode error"
                                return False

                        # ── Non-retriable HTTP errors ──
                        elif response.status_code in (400, 401, 403, 404, 422):
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
                                meta["tracker_status"][self.tracker]["status_message"] = f"C411: {api_message}"
                            else:
                                meta["tracker_status"][self.tracker]["status_message"] = {
                                    "error": f"HTTP {response.status_code}",
                                    "detail": error_detail,
                                }

                            # Pretty-print the error
                            if api_message:
                                console.print(f"[yellow]C411 — {api_message}[/yellow]")
                            else:
                                console.print(f"[red]C411 upload failed: HTTP {response.status_code}[/red]")
                                if error_detail:
                                    console.print(f"[dim]{error_detail}[/dim]")
                            return False

                        # ── Retriable HTTP errors ──
                        else:
                            if attempt < max_retries - 1:
                                console.print(f"[yellow]C411: HTTP {response.status_code}, retrying in {retry_delay}s… (attempt {attempt + 1}/{max_retries})[/yellow]")
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
                            console.print(f"[red]C411 upload failed after {max_retries} attempts: HTTP {response.status_code}[/red]")
                            return False

                    except httpx.TimeoutException:
                        if attempt < max_retries - 1:
                            timeout = timeout * 1.5
                            console.print(f"[yellow]C411: timeout, retrying in {retry_delay}s with {timeout:.0f}s timeout… (attempt {attempt + 1}/{max_retries})[/yellow]")
                            await asyncio.sleep(retry_delay)
                            continue
                        meta["tracker_status"][self.tracker]["status_message"] = "data error: Request timed out after multiple attempts"
                        return False

                    except httpx.RequestError as e:
                        if attempt < max_retries - 1:
                            console.print(f"[yellow]C411: request error, retrying in {retry_delay}s… (attempt {attempt + 1}/{max_retries})[/yellow]")
                            await asyncio.sleep(retry_delay)
                            continue
                        meta["tracker_status"][self.tracker]["status_message"] = f"data error: Upload failed: {e}"
                        console.print(f"[red]C411 upload error: {e}[/red]")
                        return False

                return False  # exhausted retries without explicit return
            else:
                # ── Debug mode — save description & show summary ──
                desc_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}]DESCRIPTION.txt"
                async with aiofiles.open(desc_path, "w", encoding="utf-8") as f:
                    await f.write(description)
                console.print(f"DEBUG: Saving final description to {desc_path}")
                console.print("[cyan]C411 Debug — Request data:[/cyan]")
                console.print(f"  Title:       {title}")
                console.print(f"  Category:    {cat_id} / Sub: {subcat_id}")
                console.print(f"  Language:    {language_tag}")
                console.print(f"  Options:     {options_json}")
                console.print(f"  Description: {description[:500]}…")
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
            console.print(f"[red]C411 upload error: {e}[/red]")
            return False

    async def search_existing(self, meta: Meta, _: Any = None) -> list[dict[str, Any]]:
        """Search for existing torrents on C411 via its Torznab API.

        Torznab endpoint: GET https://c411.org/api?t=search&q=QUERY&apikey=KEY
        Also supports:    ?t=search&tmdbid=ID
                          ?t=movie&imdbid=IMDBID
                          ?t=tvsearch&q=QUERY
        Response format:  RSS/XML with <item> elements.
        """
        dupes: list[dict[str, Any]] = []

        if not self.api_key:
            console.print("[yellow]C411: No API key configured, skipping dupe check.[/yellow]")
            return []

        # Build search queries — TMDB ID first, then IMDB, then text
        queries: list[dict[str, str]] = []

        tmdb_id = meta.get("tmdb", "")
        imdb_id = meta.get("imdb_id", 0)
        title = meta.get("title", "")
        year = meta.get("year", "")
        category = meta.get("category", "")

        # Primary: TMDB ID search (best match on C411)
        if tmdb_id:
            queries.append({"t": "search", "tmdbid": str(tmdb_id)})

        # Secondary: IMDB search for movies
        if imdb_id and int(imdb_id) > 0 and category == "MOVIE":
            imdb_str = f"tt{str(imdb_id).zfill(7)}"
            queries.append({"t": "movie", "imdbid": imdb_str})

        # Tertiary: text search with French title (accent-stripped) + year
        fr_title = meta.get("frtitle", "") or title
        search_term = unidecode(f"{fr_title} {year}".strip()).replace(" ", ".")
        if search_term:
            if category == "TV":
                queries.append({"t": "tvsearch", "q": search_term})
            else:
                queries.append({"t": "search", "q": search_term})

        if not queries:
            return []

        seen_guids: set[str] = set()

        for params in queries:
            try:
                url_params = {**params, "apikey": self.api_key}
                async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                    response = await client.get("https://c411.org/api", params=url_params)

                if response.status_code != 200:
                    if meta.get("debug"):
                        console.print(f"[yellow]C411 Torznab search returned HTTP {response.status_code}[/yellow]")
                    continue

                # Parse XML response
                items = self._parse_torznab_response(response.text)

                for item in items:
                    guid = item.get("guid", item.get("name", ""))
                    if guid in seen_guids:
                        continue
                    seen_guids.add(guid)
                    dupes.append(item)

            except Exception as e:
                if meta.get("debug"):
                    console.print(f"[yellow]C411 Torznab search error: {e}[/yellow]")
                continue

        if meta.get("debug"):
            console.print(f"[cyan]C411 dupe search found {len(dupes)} result(s)[/cyan]")

        # ── Corrective versions bypass dupe blocking ──
        # PROPER, REPACK, FIX, RERIP, V2 are always allowed
        if self._is_corrective_version_meta(meta):
            if meta.get("debug"):
                console.print("[cyan]C411: Corrective version detected (PROPER/REPACK/…) — skipping dupe check[/cyan]")
            return []

        # ── Filter dupes by C411 slot ──
        # Only show dupes that occupy the same slot as the upload
        upload_slot = self._determine_c411_slot(meta)
        if upload_slot and dupes:
            slot_dupes = []
            for dupe in dupes:
                dupe_name = dupe.get("name", "")
                dupe_slot = self._determine_c411_slot_from_name(dupe_name)
                if dupe_slot == upload_slot:
                    dupe["_c411_slot"] = dupe_slot
                    slot_dupes.append(dupe)
                elif meta.get("debug"):
                    console.print(
                        f"[dim]C411 slot filter: skipping [cyan]{dupe_name}[/cyan] (slot [yellow]{dupe_slot}[/yellow] ≠ upload slot [green]{upload_slot}[/green])[/dim]"
                    )
            if meta.get("debug"):
                console.print(f"[cyan]C411 slot: [green]{upload_slot}[/green] — {len(slot_dupes)}/{len(dupes)} result(s) in same slot[/cyan]")
            dupes = slot_dupes

        # ── Language coexistence ──
        # VFF and VFQ can coexist temporarily when no VF2/MULTI.VF2 exists.
        # So: if upload is VFF and only VFQ dupes exist (no VF2/MULTI.VF2) → not a dupe.
        if dupes:
            upload_audio = await self._build_audio_string(meta)
            upload_lang = self._detect_lang_tag_from_name(upload_audio)
            # Check if any existing dupe is VF2 or MULTI.VF2
            has_unified = any(self._detect_lang_tag_from_name(d.get("name", "")) in ("VF2", "MULTI.VF2") for d in dupes)
            if not has_unified and upload_lang in ("VFF", "MULTI.VFF"):
                # VFF upload: filter out VFQ-only dupes (they coexist)
                before = len(dupes)
                dupes = [d for d in dupes if self._detect_lang_tag_from_name(d.get("name", "")) not in ("VFQ", "MULTI.VFQ")]
                if meta.get("debug") and len(dupes) < before:
                    console.print(f"[cyan]C411 coexistence: VFF upload — {before - len(dupes)} VFQ dupe(s) removed (temporary coexistence, no VF2 found)[/cyan]")
            elif not has_unified and upload_lang in ("VFQ", "MULTI.VFQ"):
                # VFQ upload: filter out VFF-only dupes (they coexist)
                before = len(dupes)
                dupes = [d for d in dupes if self._detect_lang_tag_from_name(d.get("name", "")) not in ("VFF", "MULTI.VFF")]
                if meta.get("debug") and len(dupes) < before:
                    console.print(f"[cyan]C411 coexistence: VFQ upload — {before - len(dupes)} VFF dupe(s) removed (temporary coexistence, no VF2 found)[/cyan]")

        # ── HDR / DV coexistence ──
        # HDR-only and DV-only can coexist when no combined DV.HDR10 exists.
        if dupes:
            hdr = str(meta.get("hdr", ""))
            upload_dv_only = self._has_dv_only(hdr)
            upload_hdr_only = self._has_hdr_only(hdr)

            if upload_dv_only or upload_hdr_only:
                # Check if any dupe has combined DV+HDR
                has_combined = any(self._detect_hdr_type_from_name(d.get("name", "")) == "DV+HDR" for d in dupes)
                if not has_combined:
                    if upload_dv_only:
                        # DV-only upload: filter out HDR-only dupes (coexist)
                        before = len(dupes)
                        dupes = [d for d in dupes if self._detect_hdr_type_from_name(d.get("name", "")) != "HDR"]
                        if meta.get("debug") and len(dupes) < before:
                            console.print(
                                f"[cyan]C411 coexistence: DV-only upload — {before - len(dupes)} HDR-only dupe(s) removed (temporary coexistence, no DV.HDR10 found)[/cyan]"
                            )
                    elif upload_hdr_only:
                        # HDR-only upload: filter out DV-only dupes (coexist)
                        before = len(dupes)
                        dupes = [d for d in dupes if self._detect_hdr_type_from_name(d.get("name", "")) != "DV"]
                        if meta.get("debug") and len(dupes) < before:
                            console.print(
                                f"[cyan]C411 coexistence: HDR-only upload — {before - len(dupes)} DV-only dupe(s) removed (temporary coexistence, no DV.HDR10 found)[/cyan]"
                            )

        # ── Tag dupes with slot for display ──
        for dupe in dupes:
            dupe_name = dupe.get("name", "")
            slot = dupe.get("_c411_slot") or self._determine_c411_slot_from_name(dupe_name)
            dupe["name"] = f"[{slot}] {dupe_name}"

        return await self._check_french_lang_dupes(dupes, meta)

    @staticmethod
    def _parse_torznab_response(xml_text: str) -> list[dict[str, Any]]:
        """Parse a Torznab XML response into a list of DupeEntry-compatible dicts."""
        results: list[dict[str, Any]] = []

        try:
            root = ET.fromstring(xml_text)
        except Exception:
            return results

        # Torznab namespace for <torznab:attr>
        ns = {"torznab": "http://torznab.com/schemas/2015/feed"}

        # Items can be at /rss/channel/item or just /channel/item
        items = root.findall(".//item")

        for item in items:
            name = ""
            title_el = item.find("title")
            if title_el is not None and title_el.text:
                name = title_el.text.strip()

            size_val = 0
            size_el = item.find("size")
            if size_el is not None and size_el.text:
                with contextlib.suppress(ValueError, TypeError):
                    size_val = int(size_el.text)

            link = ""
            link_el = item.find("link")
            if link_el is not None and link_el.text:
                link = link_el.text.strip()
            # Fallback to comments or guid for URL
            if not link:
                comments_el = item.find("comments")
                if comments_el is not None and comments_el.text:
                    link = comments_el.text.strip()
            if not link:
                guid_el = item.find("guid")
                if guid_el is not None and guid_el.text:
                    link = guid_el.text.strip()

            guid = ""
            guid_el = item.find("guid")
            if guid_el is not None and guid_el.text:
                guid = guid_el.text.strip()

            # Extract torznab attributes (resolution, category, files, etc.)
            files_count = 0
            resolution = ""
            for attr in item.findall("torznab:attr", ns):
                attr_name = attr.get("name", "")
                attr_value = attr.get("value", "")
                if attr_name == "files":
                    with contextlib.suppress(ValueError, TypeError):
                        files_count = int(attr_value)
                elif attr_name == "resolution":
                    resolution = attr_value

            if name:
                results.append(
                    {
                        "name": name,
                        "size": size_val if size_val else None,
                        "link": link or None,
                        "id": guid or None,
                        "file_count": files_count,
                        "res": resolution or None,
                        "files": [],
                        "trumpable": False,
                        "internal": False,
                        "flags": [],
                        "type": None,
                        "bd_info": None,
                        "description": None,
                        "download": None,
                    }
                )

        return results

    async def edit_desc(self, _meta: Meta) -> None:
        """No-op — C411 descriptions are built in upload()."""
        return
