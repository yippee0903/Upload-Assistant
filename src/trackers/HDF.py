# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
"""
hdf.world — HD-Forever (French private tracker, cookie-based HTML form upload)

Upload endpoint:  POST https://hdf.world/upload.php
Authentication:   Session cookies (Netscape cookie file)
Content-Type:     multipart/form-data

The tracker uses a classic PHP upload form with TMDB integration.
"""

import contextlib
import os
import platform
import re
from datetime import datetime
from typing import Any, Optional, Union

import aiofiles
import httpx
from bs4 import BeautifulSoup

from src.console import console
from src.cookie_auth import CookieAuthUploader, CookieValidator
from src.get_desc import DescriptionBuilder
from src.nfo_generator import SceneNfoGenerator
from src.tmdb import TmdbManager
from src.trackers.FRENCH import LANG_MAP, LANG_NAMES_FR, FrenchTrackerMixin

Meta = dict[str, Any]
Config = dict[str, Any]

FRENCH_MONTHS: list[str] = [
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

# ── Banned groups (from HDF rules) ────────────────────────────────────
_BANNED_GROUPS: list[str] = [
    "EXTREME",
    "RARBG",
    "FGT",
    "HDMIDIMADRIDI",
    "Foxhound",
    "HDSpace",
    "FL3ER",
    "SUNS3T",
    "WoLFHD",
]


class HDF(FrenchTrackerMixin):
    """HD-Forever (hdf.world) — French private tracker with cookie-based auth."""

    secret_token: str = ""

    def __init__(self, config: Config) -> None:
        self.config: Config = config
        self.cookie_validator = CookieValidator(config)
        self.cookie_auth_uploader = CookieAuthUploader(config)
        self.tracker: str = "HDF"
        self.source_flag: str = "HDF"
        self.base_url: str = "https://hdf.world"
        self.upload_url: str = f"{self.base_url}/upload.php"
        self.torrent_url: str = f"{self.base_url}/torrents.php?torrentid="
        self.banned_groups: list[str] = _BANNED_GROUPS
        self.tmdb_manager = TmdbManager(config)
        self.session = httpx.AsyncClient(
            headers={"User-Agent": f"Upload Assistant/2.3 ({platform.system()} {platform.release()})"},
            timeout=30,
        )

    # ── FrenchTrackerMixin overrides ──────────────────────────────────

    # HDF naming examples: "The.Box.2009.MULTi.VFi.1080p.BluRay.REMUX.AVC.DTS-HD.MA.5.1-HDForever"
    # HDF wants streaming service in name: "The.Box.2009.MULTi.VFi.1080p.AMZN.WEB-DL.H264.DDP.5.1-HDForever"
    INCLUDE_SERVICE_IN_NAME: bool = True

    # HDF uses original (English) titles, not French translations
    PREFER_ORIGINAL_TITLE: bool = True

    # HDF uses "WEB" per their naming rules
    WEB_LABEL: str = "WEB"

    # ──────────────────────────────────────────────────────────
    #  Authentication
    # ──────────────────────────────────────────────────────────

    async def validate_credentials(self, meta: Meta) -> bool:
        cookies = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        self.session.cookies.clear()
        if cookies is not None:
            self.session.cookies.update(cookies)
        result = await self.cookie_validator.cookie_validation(
            meta=meta,
            tracker=self.tracker,
            test_url=self.upload_url,
            error_text="login.php",
            token_pattern=r'name="auth" value="([^"]+)"',  # nosec B106
        )
        if result:
            # Copy class-level token (set by cookie_auth) to instance
            self.secret_token = HDF.secret_token
        return result

    # ──────────────────────────────────────────────────────────
    #  Category mapping
    # ──────────────────────────────────────────────────────────

    # HDF categories (from upload form <select name="type">):
    # 0 = Film
    # 1 = Film d'animation
    # 2 = Spectacle
    # 3 = Concert
    # 4 = Série
    # 5 = Série d'animation
    # 6 = Documentaire

    async def get_category_id(self, meta: Meta) -> int:
        category = str(meta.get("category", "")).upper()
        genres = str(meta.get("genres", "")).lower()
        keywords = str(meta.get("keywords", "")).lower()
        is_anime = bool(meta.get("anime"))

        if "documentary" in genres or "documentary" in keywords:
            return 6  # Documentaire

        if "concert" in keywords or "live" in keywords:
            return 3  # Concert

        _SPECTACLE_TOKENS = {"spectacle", "spectacles", "show", "theatre", "theater", "stage", "performance", "one-man-show", "stand-up", "humour", "humor"}
        if _SPECTACLE_TOKENS & (set(genres.split(", ")) | set(keywords.split(", "))):
            return 2  # Spectacle

        if is_anime:
            if category == "TV":
                return 5  # Série d'animation
            return 1  # Film d'animation

        if category == "TV":
            return 4  # Série

        return 0  # Film (default)

    # ──────────────────────────────────────────────────────────
    #  Codec mapping
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def _get_codec_id(meta: Meta) -> str:
        """Map video codec to HDF form <select name="format"> value.

        Valid values: x264, x265, AVC, VC-1, MPEG-2, HEVC, AV1, H264, H265
        """
        codec = str(meta.get("video_codec", "")).upper()
        encode = str(meta.get("video_encode", "")).upper()

        if "AV1" in encode or "AV1" in codec:
            return "AV1"
        if "X265" in encode:
            return "x265"
        if "X264" in encode:
            return "x264"
        if "H265" in encode or "H.265" in encode:
            return "H265"
        if "H264" in encode or "H.264" in encode:
            return "H264"
        if "HEVC" in codec:
            return "HEVC"
        if "AVC" in codec:
            return "AVC"
        if "VC-1" in codec or "VC1" in codec:
            return "VC-1"
        if "MPEG-2" in codec or "MPEG2" in codec:
            return "MPEG-2"
        return ""

    # ──────────────────────────────────────────────────────────
    #  Resolution mapping
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def _get_resolution_id(meta: Meta) -> str:
        """Map resolution to HDF form <select name="bitrate"> value.

        Valid values: 720p, 1080p, 1080i, 2160p, 3D 1080p, 3D 720p
        """
        resolution = str(meta.get("resolution", ""))
        is_3d = bool(meta.get("3D"))
        if "2160" in resolution:
            return "2160p"
        if "1080i" in resolution:
            return "1080i"
        if "1080" in resolution:
            return "3D 1080p" if is_3d else "1080p"
        if "720" in resolution:
            return "3D 720p" if is_3d else "720p"
        return resolution

    # ──────────────────────────────────────────────────────────
    #  Type de fichier (file type) mapping
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def _get_file_type(meta: Meta) -> str:
        """Map release type to HDF form <select name="media"> value.

        Valid values: Blu-ray Original, Blu-ray Remux, Blu-ray Rip, mHD, HD-DVD, WEB-DL
        """
        release_type = str(meta.get("type", "")).upper()
        is_disc = str(meta.get("is_disc", ""))

        if is_disc == "BDMV" or release_type == "DISC":
            return "Blu-ray Original"
        if release_type == "REMUX":
            return "Blu-ray Remux"
        if release_type in ("WEBDL", "WEBRIP"):
            return "WEB-DL"
        if release_type == "ENCODE":
            return "Blu-ray Rip"
        return ""

    # ──────────────────────────────────────────────────────────
    #  Language checkboxes
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def _has_french_audio(meta: Meta) -> bool:
        """Check whether at least one French audio track is present in MediaInfo."""
        if "mediainfo" not in meta or "media" not in meta.get("mediainfo", {}):
            return False
        from src.trackers.FRENCH import FRENCH_LANG_VALUES

        for track in meta["mediainfo"]["media"].get("track", []):
            if track.get("@type") != "Audio":
                continue
            lang = str(track.get("Language", "")).lower().strip()
            if lang in FRENCH_LANG_VALUES or lang.startswith("fr"):
                return True
            title = str(track.get("Title", "")).lower()
            if "french" in title or "français" in title or "francais" in title:
                return True
        return False

    def _compute_language_flags(self, meta: Meta, audio_tag: str) -> dict[str, bool]:
        """Determine which language checkboxes to tick based on the audio tag."""
        flags: dict[str, bool] = {
            "VFI": False,
            "VFF": False,
            "VFQ": False,
            "VO": False,
            "VOF": False,
            "VOQ": False,
            "VF": False,
            "MULTi": False,
            "subtitles": False,
            "muet": False,
        }

        tag = audio_tag.upper()

        # MULTi variants
        if "MULTI" in tag:
            flags["MULTi"] = True
            if "VFF" in tag or "VF2" in tag:
                flags["VFF"] = True
            if "VFQ" in tag:
                flags["VFQ"] = True
            if "VFI" in tag:
                flags["VFI"] = True
            if "VOF" in tag:
                flags["VOF"] = True
            if "VOQ" in tag:
                flags["VOQ"] = True
            if not any(flags[k] for k in ("VFF", "VFQ", "VFI", "VOF", "VOQ")):
                flags["VF"] = True
        elif "VOF" in tag:
            flags["VOF"] = True
        elif "VFF" in tag or "TRUEFRENCH" in tag:
            flags["VFF"] = True
        elif "VFQ" in tag:
            flags["VFQ"] = True
        elif "VFI" in tag:
            flags["VFI"] = True
        elif "VOQ" in tag:
            flags["VOQ"] = True
        elif "VOSTFR" in tag:
            flags["VO"] = True
            flags["subtitles"] = True
        elif "VF" in tag:
            flags["VF"] = True
        elif "MUET" in tag:
            flags["muet"] = True
        elif "VO" in tag:
            flags["VO"] = True

        # Check for French subtitles presence
        if self._has_french_subs(meta):
            flags["subtitles"] = True

        return flags

    # ──────────────────────────────────────────────────────────
    #  Versions (editions / special flags)
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def _get_versions(meta: Meta) -> list[str]:
        """Determine version flags to tick on HDF form.

        HDF versions: Remaster, Director's Cut, Version Longue, UnCut,
        UnRated, 2in1, Source Netflix/Amazon/AppleTV/Canal+/Disney+,
        Criterion, Custom/HYBRiD, HDR, HDR10+, Dolby Vision, IMAX, Bonus
        """
        versions: list[str] = []
        edition = str(meta.get("edition", "")).lower()
        # edition.py strips some words ("remastered", "version") from
        # meta["edition"], so fall back to the original folder/file name
        # stored in meta["uuid"] for markers that may have been removed.
        uuid_upper = str(meta.get("uuid", "")).upper().replace(".", " ")

        if "remaster" in edition or "REMASTER" in uuid_upper:
            versions.append("Remaster")
        if "director" in edition:
            versions.append("Director's Cut")
        if "extended" in edition or "version longue" in edition or ("VERSION" in uuid_upper and "LONGUE" in uuid_upper):
            versions.append("Version Longue")
        if "uncut" in edition:
            versions.append("UnCut")
        if "unrated" in edition:
            versions.append("UnRated")
        if "2in1" in edition or "2 in 1" in edition:
            versions.append("2in1")
        if "criterion" in edition:
            versions.append("Criterion")
        webdv = str(meta.get("webdv", "")).lower()
        if webdv in ("hybrid", "custom") or "hybrid" in edition or "custom" in edition:
            versions.append("Custom / HYBRiD")
        if "imax" in edition:
            versions.append("IMAX")

        # Streaming source
        service = str(meta.get("service", "")).upper()
        service_map = {
            "NF": "Source Netflix",
            "NETFLIX": "Source Netflix",
            "AMZN": "Source Amazon",
            "AMAZON": "Source Amazon",
            "ATVP": "Source AppleTV",
            "APTV": "Source AppleTV",
            "CNLP": "Source Canal+",
            "CANAL+": "Source Canal+",
            "DSNP": "Source Disney+",
            "DISNEY+": "Source Disney+",
        }
        if service in service_map:
            versions.append(service_map[service])

        # HDR flags
        hdr = str(meta.get("hdr", "")).upper()
        if "HDR10+" in hdr:
            versions.append("HDR10+")
        elif "HDR" in hdr:
            versions.append("HDR")
        if "DV" in hdr:
            versions.append("Dolby Vision")

        return versions

    # ──────────────────────────────────────────────────────────
    #  Description builder
    # ──────────────────────────────────────────────────────────

    async def _build_description(self, meta: Meta) -> str:
        """Build BBCode description for HDF, matching the site's presentation style.

        Structure: [center] wrapped, French TMDB data (credits, overview),
        flag emojis for audio/subtitles, technical info.
        """
        C = "#3d85c6"  # accent colour
        TC = "#ea9999"  # tagline colour
        parts: list[str] = []

        # ── Fetch French TMDB data ──
        fr_data: dict[str, Any] = {}
        with contextlib.suppress(Exception):
            fr_data = await self.tmdb_manager.get_tmdb_localized_data(meta, data_type="main", language="fr", append_to_response="credits") or {}

        fr_title = str(fr_data.get("title", "") or meta.get("title", "")).strip()
        fr_overview = str(fr_data.get("overview", "")).strip()
        year = meta.get("year", "")
        tagline = str(fr_data.get("tagline", "")).strip()

        # Full-size poster (w500)
        poster = meta.get("poster", "") or ""
        if "image.tmdb.org/t/p/" in poster:
            poster = re.sub(r"/t/p/[^/]+/", "/t/p/w500/", poster)

        # MI text for technical parsing
        mi_text = await self._get_mediainfo_text(meta)

        # ── Open [center] ──
        parts.append("[center]")

        # ── Title block ──
        parts.append(f"[b][color={C}][size=28]{fr_title} ({year})[/size][/color][/b]")
        parts.append("")

        # ── Poster ──
        if poster:
            parts.append(f"[img]{poster}[/img]")
            parts.append("")

        # ── Tagline ──
        if tagline:
            parts.append(f'[color={TC}][i][b]"{tagline}"[/b][/i][/color]')
            parts.append("")

        # ══════════════════════════════════════════════════════
        #  Informations
        # ══════════════════════════════════════════════════════
        parts.append(f"[b][color={C}][size=18]━━━ Informations ━━━[/size][/color][/b]")

        # Original title
        original_title = str(meta.get("original_title", "") or meta.get("title", "")).strip()
        if original_title and original_title != fr_title:
            parts.append(f"[b][color={C}]Titre original :[/color][/b] [i]{original_title}[/i]")

        # Country
        countries = fr_data.get("production_countries", meta.get("production_countries", []))
        if countries and isinstance(countries, list):
            names = [c.get("name", "") for c in countries if isinstance(c, dict) and c.get("name")]
            if names:
                parts.append(f"[b][color={C}]Pays :[/color][/b] [i]{', '.join(names)}[/i]")

        # Genres
        genres_list = fr_data.get("genres", [])
        if genres_list and isinstance(genres_list, list):
            genre_names = [g["name"] for g in genres_list if isinstance(g, dict) and g.get("name")]
            if genre_names:
                parts.append(f"[b][color={C}]Genres :[/color][/b] [i]{', '.join(genre_names)}[/i]")

        # Release date (French formatted)
        release_date = str(fr_data.get("release_date", "") or meta.get("release_date", "") or meta.get("first_air_date", "")).strip()
        if release_date:
            parts.append(f"[b][color={C}]Date de sortie :[/color][/b] [i]{self._format_french_date(release_date)}[/i]")
        elif year:
            parts.append(f"[b][color={C}]Date de sortie :[/color][/b] [i]{year}[/i]")

        # Runtime
        runtime = fr_data.get("runtime") or meta.get("runtime", 0)
        if runtime:
            h, m = divmod(int(runtime), 60)
            dur = f"{h}h{m:02d}" if h > 0 else f"{m}min"
            parts.append(f"[b][color={C}]Durée :[/color][/b] [i]{dur}[/i]")

        # Credits
        credits = fr_data.get("credits", {})
        crew = credits.get("crew", []) if isinstance(credits, dict) else []
        cast = credits.get("cast", []) if isinstance(credits, dict) else []

        directors = [p["name"] for p in crew if isinstance(p, dict) and p.get("job") == "Director" and p.get("name")]
        if not directors:
            meta_dirs = meta.get("tmdb_directors", [])
            if isinstance(meta_dirs, list):
                directors = [d.get("name", d) if isinstance(d, dict) else str(d) for d in meta_dirs]
        if directors:
            label = "Réalisateur" if len(directors) == 1 else "Réalisateurs"
            parts.append(f"[b][color={C}]{label} :[/color][/b] [i]{', '.join(directors)}[/i]")

        actors = [p["name"] for p in cast[:5] if isinstance(p, dict) and p.get("name")]
        if actors:
            parts.append(f"[b][color={C}]Acteurs :[/color][/b] [i]{', '.join(actors)}[/i]")

        # Rating
        vote_avg = fr_data.get("vote_average") or meta.get("vote_average")
        vote_count = fr_data.get("vote_count") or meta.get("vote_count")
        if vote_avg and vote_count:
            parts.append(f"[b][color={C}]Note :[/color][/b] [i]{vote_avg}/10 ({vote_count} votes)[/i]")

        # External links
        ext_links: list[str] = []
        imdb_id = str(meta.get("imdb_id", "0")).lstrip("t")
        if imdb_id.isdigit() and int(imdb_id) > 0:
            ext_links.append(f"[url=https://www.imdb.com/title/tt{imdb_id.zfill(7)}/]IMDb[/url]")
        tmdb_id_val = meta.get("tmdb", "")
        if tmdb_id_val:
            tmdb_cat = "movie" if meta.get("category", "").upper() != "TV" else "tv"
            ext_links.append(f"[url=https://www.themoviedb.org/{tmdb_cat}/{tmdb_id_val}]TMDB[/url]")
        if ext_links:
            parts.append("")
            parts.append(" │ ".join(ext_links))

        parts.append("")

        # ══════════════════════════════════════════════════════
        #  Synopsis
        # ══════════════════════════════════════════════════════
        parts.append(f"[b][color={C}][size=18]━━━ Synopsis ━━━[/size][/color][/b]")
        synopsis = fr_overview or str(meta.get("overview", "")).strip() or "Aucun synopsis disponible."
        parts.append(synopsis)
        parts.append("")

        # ══════════════════════════════════════════════════════
        #  Informations techniques
        # ══════════════════════════════════════════════════════
        parts.append(f"[b][color={C}][size=18]━━━ Informations techniques ━━━[/size][/color][/b]")

        type_label = self._get_type_label(meta)
        if type_label:
            parts.append(f"[b][color={C}]Type :[/color][/b] [i]{type_label}[/i]")

        resolution = meta.get("resolution", "")
        if resolution:
            parts.append(f"[b][color={C}]Résolution :[/color][/b] [i]{resolution}[/i]")

        container_display = self._format_container(mi_text)
        if container_display:
            parts.append(f"[b][color={C}]Format vidéo :[/color][/b] [i]{container_display}[/i]")

        video_codec = (meta.get("video_encode", "").strip() or meta.get("video_codec", "")).strip()
        video_codec = video_codec.replace("H.264", "H264").replace("H.265", "H265")
        raw_codec = meta.get("video_codec", "").strip()
        if video_codec and raw_codec and raw_codec != video_codec:
            video_codec = f"{video_codec} ({raw_codec})"
        if video_codec:
            parts.append(f"[b][color={C}]Codec vidéo :[/color][/b] [i]{video_codec}[/i]")

        hdr_dv_badge = self._format_hdr_dv_bbcode(meta)
        if hdr_dv_badge:
            parts.append(f"[b][color={C}]HDR :[/color][/b] {hdr_dv_badge}")

        if mi_text:
            vbr_match = re.search(r"(?:^|\n)Bit rate\s*:\s*(.+?)\s*(?:\n|$)", mi_text)
            if vbr_match:
                parts.append(f"[b][color={C}]Débit vidéo :[/color][/b] [i]{vbr_match.group(1).strip()}[/i]")

        parts.append("")

        # ── Audio tracks ──
        parts.append(f"[b][color={C}][size=18]━━━ Audio(s) ━━━[/size][/color][/b]")
        audio_lines = self._format_audio_bbcode(mi_text, meta)
        if audio_lines:
            parts.extend(f" {al}" for al in audio_lines)
        else:
            parts.append(" [i]Non spécifié[/i]")
        parts.append("")

        # ── Subtitles ──
        parts.append(f"[b][color={C}][size=18]━━━ Sous-titre(s) ━━━[/size][/color][/b]")
        sub_lines = self._format_subtitle_bbcode(mi_text, meta)
        if sub_lines:
            parts.extend(f" {sl}" for sl in sub_lines)
        else:
            parts.append(" [i]Aucun[/i]")
        parts.append("")

        # ══════════════════════════════════════════════════════
        #  Release
        # ══════════════════════════════════════════════════════
        parts.append(f"[b][color={C}][size=18]━━━ Release ━━━[/size][/color][/b]")

        release_name = meta.get("name", "") or meta.get("title", "")
        parts.append(f"[b][color={C}]Titre :[/color][/b] [i]{release_name}[/i]")

        # Personal note with -n/--note
        personal_note = await DescriptionBuilder(self.tracker, self.config).get_personal_note(meta)
        if personal_note:
            parts.append(f"[b][color={C}]Note :[/color][/b] {personal_note}")

        size_str = self._get_total_size(meta, mi_text)
        if size_str:
            parts.append(f"[b][color={C}]Taille totale :[/color][/b] {size_str}")

        file_count = self._count_files(meta)
        if file_count:
            parts.append(f"[b][color={C}]Nombre de fichier(s) :[/color][/b] {file_count}")

        group = self._get_release_group(meta)
        if group:
            parts.append(f"[b][color={C}]Groupe :[/color][/b] [i]{group}[/i]")

        # ── Screenshots (opt-in) ──
        include_screens = self.config["TRACKERS"].get(self.tracker, {}).get("include_screenshots", False)
        image_list: list[dict[str, Any]] = meta.get("image_list", []) if include_screens else []
        if image_list:
            parts.append("")
            parts.append(f"[b][color={C}][size=18]━━━ Captures d'écran ━━━[/size][/color][/b]")
            for img in image_list:
                raw = img.get("raw_url", "")
                web = img.get("web_url", "")
                if raw:
                    if web:
                        parts.append(f"[url={web}][img]{raw}[/img][/url]")
                    else:
                        parts.append(f"[img]{raw}[/img]")

        # Close center
        parts.append("[/center]")

        return "\n".join(parts)

    # ──────────────────────────────────────────────────────────
    #  MediaInfo text helpers
    # ──────────────────────────────────────────────────────────

    async def _get_mediainfo_text(self, meta: Meta) -> str:
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

        fallback = str(meta.get("mediainfo_text") or "").strip()
        if fallback:
            return fallback

        return ""

    @staticmethod
    def _format_french_date(date_str: str) -> str:
        """Format YYYY-MM-DD to French full date, e.g. '24 octobre 2011'."""
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            day_str = "1er" if dt.day == 1 else str(dt.day)
            return f"{day_str} {FRENCH_MONTHS[dt.month]} {dt.year}"
        except (ValueError, IndexError):
            return date_str

    # ──────────────────────────────────────────────────────────
    #  NFO generation
    # ──────────────────────────────────────────────────────────

    async def _get_or_generate_nfo(self, meta: Meta) -> Optional[str]:
        """Generate a MediaInfo-based NFO for the upload."""
        nfo_gen = SceneNfoGenerator(self.config)
        return await nfo_gen.generate_nfo(meta, self.tracker)

    # ──────────────────────────────────────────────────────────
    #  Additional checks — language requirements & bloat detection
    # ──────────────────────────────────────────────────────────

    _BLOAT_CHECK_TYPES = frozenset({"REMUX", "ENCODE", "WEBDL", "WEBRIP"})

    async def get_additional_checks(self, meta: Meta) -> bool:
        """Check HDF rules: forbidden codecs, French audio, superfluous tracks, NFO."""
        # AAC audio is forbidden on HDF, except for commentary and audio description tracks
        mediainfo = meta.get("mediainfo") or {}
        media = mediainfo.get("media") if isinstance(mediainfo, dict) else {}
        all_tracks = (media.get("track") if isinstance(media, dict) else None) or []
        for track in all_tracks:
            if not isinstance(track, dict) or track.get("@type") != "Audio":
                continue
            fmt = str(track.get("Format", "")).strip().upper()
            if fmt == "AAC":
                title = str(track.get("Title", "")).lower()
                if any(kw in title for kw in ("comment", "audiodesc", "audio desc", "description")):
                    continue
                console.print(f"[bold red]{self.tracker}: Le codec AAC est interdit sur HD-Forever (sauf commentaires audio et audiodescription). Upload annulé.[/bold red]")
                meta["skipping"] = self.tracker
                return False

        # French audio (VF) is mandatory — warn if not detected
        has_french = self._has_french_audio(meta)
        audio_tracks = [t for t in all_tracks if isinstance(t, dict) and t.get("@type") == "Audio"]
        is_muet = len(audio_tracks) == 0
        if not has_french and not is_muet:
            console.print(
                f"[bold yellow]{self.tracker}: Aucune piste audio française détectée. "
                f"La VF est obligatoire sur HDF (sauf exceptions : film sans VF dispo, "
                f"concerts, films muets, certains WEB-DL).[/bold yellow]"
            )

        # Bloat detection (warning only — does not block upload)
        release_type = str(meta.get("type", "")).upper()
        if release_type in self._BLOAT_CHECK_TYPES:
            try:
                self._warn_superfluous_tracks(meta)
            except Exception as exc:
                console.print(f"[yellow]{self.tracker}: bloat check skipped ({exc})[/yellow]")

        # Auto-generate NFO if not provided
        if not meta.get("nfo") and not meta.get("auto_nfo"):
            try:
                nfo_path = await self._get_or_generate_nfo(meta)
                if nfo_path:
                    meta["nfo"] = nfo_path
                    meta["auto_nfo"] = True
            except Exception as exc:
                console.print(f"[yellow]{self.tracker}: NFO generation skipped ({exc})[/yellow]")

        return True

    def _warn_superfluous_tracks(self, meta: Meta) -> None:
        """Print a warning when audio/subtitle tracks are not VF or VO.

        Allowed languages:
        - French (any variant)
        - Original language (from TMDB)
        - English (tolerated when VO is not English — e.g. anime dubs)
        Commentary tracks are ignored.
        """
        orig_lang = (meta.get("original_language") or "").lower().strip()
        # Build the set of allowed 3-letter codes
        allowed: set[str] = {"FRA"}  # French always allowed
        if orig_lang:
            orig_mapped = LANG_MAP.get(orig_lang, orig_lang.upper()[:3])
            allowed.add(orig_mapped)
            # Tolerate English dub when VO is not English
            if orig_mapped != "ENG":
                allowed.add("ENG")

        # -- Audio tracks --
        audio_tracks = self._get_audio_tracks(meta, filter_commentary=True)
        extra_audio: list[str] = []
        for track in audio_tracks:
            raw = str(track.get("Language", "")).strip().lower()
            mapped = LANG_MAP.get(raw, raw.upper()[:3] if raw else "")
            if mapped and mapped not in allowed:
                fr_name = self._lang_display_name(raw, mapped)
                if fr_name not in extra_audio:
                    extra_audio.append(fr_name)

        # -- Subtitle tracks --
        mediainfo = meta.get("mediainfo") or {}
        media = mediainfo.get("media") if isinstance(mediainfo, dict) else {}
        all_tracks = (media.get("track") if isinstance(media, dict) else None) or []
        sub_tracks = [t for t in all_tracks if isinstance(t, dict) and t.get("@type") == "Text"]
        extra_subs: list[str] = []
        for track in sub_tracks:
            raw = str(track.get("Language", "")).strip().lower()
            mapped = LANG_MAP.get(raw, raw.upper()[:3] if raw else "")
            if mapped and mapped not in allowed:
                fr_name = self._lang_display_name(raw, mapped)
                if fr_name not in extra_subs:
                    extra_subs.append(fr_name)

        if extra_audio:
            console.print(
                f"[bold yellow]{self.tracker}: {len(extra_audio)} langue(s) audio non pertinente(s) "
                f"détectée(s) ({', '.join(extra_audio)}) — "
                f"seules VF et VO sont attendues.[/bold yellow]"
            )
        if extra_subs:
            console.print(f"[bold yellow]{self.tracker}: {len(extra_subs)} langue(s) de sous-titres non pertinente(s) détectée(s) ({', '.join(extra_subs)}).[/bold yellow]")

        if extra_audio or extra_subs:
            console.print(f"[bold red]{self.tracker}: Pistes audio et sous-titres surabondants formellement interdits sur HDF.[/bold red]")

    @staticmethod
    def _lang_display_name(raw_code: str, mapped_code: str) -> str:
        """Return a human-readable French name for a language code."""
        # Try the full raw code first (e.g. "spanish"), then 2-letter prefix
        name = LANG_NAMES_FR.get(raw_code)
        if name:
            return name
        # Try common long forms from LANG_NAMES_FR keys
        for key, val in LANG_NAMES_FR.items():
            code = LANG_MAP.get(key, "")
            if code == mapped_code:
                return val
        return mapped_code  # fallback to 3-letter code

    # ──────────────────────────────────────────────────────────
    #  Dupe search
    # ──────────────────────────────────────────────────────────

    async def search_existing(self, meta: Meta, _disctype: str) -> list[dict[str, Union[str, None]]]:
        cookies = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        self.session.cookies.clear()
        if cookies is not None:
            self.session.cookies.update(cookies)

        dupes: list[dict[str, Union[str, None]]] = []

        should_continue = await self.get_additional_checks(meta)
        if not should_continue:
            meta["skipping"] = self.tracker
            return dupes

        # Search by TMDB ID (preferred), fallback to title text search
        tmdb_id = meta.get("tmdb", "")
        if tmdb_id:
            params: dict[str, str] = {"tmdbid": str(tmdb_id)}
        else:
            title = str(meta.get("title", ""))
            if not title:
                console.print(f"[yellow]{self.tracker}: No TMDB ID or title for dupe search[/yellow]")
                return dupes
            params = {"search": title, "cat": "0"}

        search_url = f"{self.base_url}/torrents.php"

        try:
            response = await self.session.get(search_url, params=params, follow_redirects=True)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            # HDF is Gazelle-based: the group page shows each torrent's
            # file name in a <tr class="torrent_filename_row"> row.
            for row in soup.find_all("tr", class_="torrent_filename_row"):
                td = row.find("td")
                if td:
                    name = td.get_text(strip=True)
                    if name:
                        dupes.append({"name": name, "size": None, "link": None})

        except Exception as e:
            console.print(f"[bold red]{self.tracker}: Error searching for duplicates: {e}[/bold red]")

        return dupes

    # ──────────────────────────────────────────────────────────
    #  Build form data
    # ──────────────────────────────────────────────────────────

    async def get_data(self, meta: Meta) -> dict[str, Any]:
        """Build the multipart form data dict for HDF upload.php.

        Real form field names (verified against hdf.world/upload.php):
          submit, auth          — hidden fields
          file_input            — .torrent file
          type                  — category (select 0-6)
          allocine_url          — allociné/TMDB URL
          title                 — movie title
          year                  — release year
          format                — video codec (select)
          bitrate               — resolution (select)
          media                 — file type (select)
          team                  — release group
          scene                 — scene checkbox
          VFI..MUET             — language checkboxes (direct names)
          releaseVersion[]      — version checkboxes (array)
          release_desc          — release description (BBCode)
          album_desc            — movie/album description (BBCode)
          image                 — poster URL
          artists[]             — actor/director names (at least one actor required)
          importance[]          — role type per artist (1=Acteur, 2=Producteur, 4=Réalisateur)
        """
        name_result = await self.get_name(meta)
        # get_name populates meta["name"]; the torrent name is embedded in the .torrent file
        if isinstance(name_result, dict) and name_result.get("name"):
            meta.setdefault("name", name_result["name"])

        # Build audio tag for language detection
        audio_tag = await self._build_audio_string(meta)

        # Language flags
        lang_flags = self._compute_language_flags(meta, audio_tag)

        # MediaInfo text
        mi_text = await self._get_mediainfo_text(meta)

        # Category
        category_id = await self.get_category_id(meta)

        # TMDB URL (form field is allocine_url but accepts any URL)
        tmdb_id = meta.get("tmdb", "")
        is_tv = str(meta.get("category", "")).upper() == "TV"
        tmdb_cat = "tv" if is_tv else "movie"
        tmdb_url = f"https://www.themoviedb.org/{tmdb_cat}/{tmdb_id}" if tmdb_id else ""
        # Append season path for TV so HDF can identify the correct season
        if is_tv and tmdb_url:
            season_int = meta.get("season_int", 0)
            if season_int and int(season_int) > 0:
                tmdb_url += f"/season/{int(season_int)}"

        # Team / release group
        team = self._get_release_group(meta)

        # Versions
        versions = self._get_versions(meta)

        # Poster
        poster = meta.get("poster", "") or ""

        # ── Fetch TMDB credits for artists[] fields ──
        artists_names: list[str] = []
        artists_roles: list[str] = []  # 1=Acteur, 4=Réalisateur
        with contextlib.suppress(Exception):
            fr_data = (
                await self.tmdb_manager.get_tmdb_localized_data(
                    meta,
                    data_type="main",
                    language="fr",
                    append_to_response="credits",
                )
                or {}
            )
            tmdb_credits = fr_data.get("credits", {})
            crew = tmdb_credits.get("crew", []) if isinstance(tmdb_credits, dict) else []
            cast = tmdb_credits.get("cast", []) if isinstance(tmdb_credits, dict) else []
            # Directors first (importance=4)
            for p in crew:
                if isinstance(p, dict) and p.get("job") == "Director" and p.get("name"):
                    artists_names.append(p["name"])
                    artists_roles.append("4")
            # Then actors (importance=1), up to 5
            for p in cast[:5]:
                if isinstance(p, dict) and p.get("name"):
                    artists_names.append(p["name"])
                    artists_roles.append("1")
        # Fallback to meta if TMDB fetch failed
        if not artists_names:
            for name in meta.get("tmdb_directors", [])[:2]:
                n = name.get("name", name) if isinstance(name, dict) else str(name)
                if n:
                    artists_names.append(n)
                    artists_roles.append("4")
            for name in meta.get("tmdb_cast", [])[:5]:
                n = name.get("name", name) if isinstance(name, dict) else str(name)
                if n:
                    artists_names.append(n)
                    artists_roles.append("1")

        data: dict[str, Any] = {
            "submit": "true",
            "auth": self.secret_token,
            "type": str(category_id),
            "allocine_url": tmdb_url,
            "title": str(meta.get("title", "")),
            "year": str(meta.get("year", "")),
            "format": self._get_codec_id(meta),
            "bitrate": self._get_resolution_id(meta),
            "media": self._get_file_type(meta),
            "team": team,
            "release_desc": mi_text,
            "image": poster,
        }

        # Artists (at least one actor is required by HDF)
        if artists_names and "1" not in artists_roles:
            artists_names.append("Unknown")
            artists_roles.append("1")
        if not artists_names:
            artists_names.append("Unknown")
            artists_roles.append("1")
        data["artists[]"] = artists_names
        data["importance[]"] = artists_roles

        # Season selector (TV only) — S00 = specials, S01, S02, …
        if is_tv:
            season_int = meta.get("season_int", 0)
            data["season"] = str(int(season_int)) if season_int else "0"

        # Scene checkbox
        if meta.get("scene", False):
            data["scene"] = "1"

        # Language checkboxes — form uses the tag name directly as field name
        _LANG_FIELDS = {
            "VFI": "VFI",
            "VFF": "VFF",
            "VFQ": "VFQ",
            "VO": "VO",
            "VOF": "VOF",
            "VOQ": "VOQ",
            "VF": "VF",
            "MULTi": "MULTI",
            "subtitles": "SRT",
            "muet": "MUET",
        }
        for flag_key, form_field in _LANG_FIELDS.items():
            if lang_flags.get(flag_key, False):
                data[form_field] = "1"

        # Version checkboxes — all share name="releaseVersion[]" with distinct values
        _VERSION_VALUES: dict[str, str] = {
            "Remaster": "RM",
            "Director's Cut": "DC",
            "Version Longue": "VL",
            "UnCut": "UC",
            "UnRated": "UR",
            "2in1": "2in1",
            "Source Netflix": "NF",
            "Source Amazon": "AMZN",
            "Source AppleTV": "ATVP",
            "Source Canal+": "CNLP",
            "Source Disney+": "DSNP",
            "Criterion": "Crit",
            "Custom / HYBRiD": "Cust",
            "HDR": "HDR",
            "HDR10+": "HDR10+",
            "Dolby Vision": "DV",
            "IMAX": "IMAX",
            "Bonus": "Bonus",
        }
        release_versions = [_VERSION_VALUES[ver] for ver in versions if ver in _VERSION_VALUES]
        if release_versions:
            data["releaseVersion[]"] = release_versions

        # Anonymous
        anon = meta.get("anon", False) or self.config["TRACKERS"].get(self.tracker, {}).get("anon", False)
        if anon:
            data["anonymous"] = "1"

        return data

    # ──────────────────────────────────────────────────────────
    #  Upload
    # ──────────────────────────────────────────────────────────

    async def upload(self, meta: Meta, _disctype: str) -> bool:
        """Upload torrent to HD-Forever (hdf.world)."""
        cookies = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        self.session.cookies.clear()
        if cookies is not None:
            self.session.cookies.update(cookies)

        data = await self.get_data(meta)

        is_uploaded = await self.cookie_auth_uploader.handle_upload(
            meta=meta,
            tracker=self.tracker,
            source_flag=self.source_flag,
            torrent_url=self.torrent_url,
            data=data,
            torrent_field_name="file_input",
            upload_cookies=self.session.cookies,
            upload_url=self.upload_url,
            id_pattern=r"torrentid=([a-fA-F0-9]+)",
            success_text="torrents.php?torrentid=",
        )

        return is_uploaded
