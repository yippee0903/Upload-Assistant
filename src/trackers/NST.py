# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import os
import re
from typing import Any

import aiofiles

from src.console import console
from src.rehostimages import RehostImagesManager
from src.trackers.COMMON import COMMON
from src.trackers.FRENCH import FrenchTrackerMixin
from src.trackers.UNIT3D import UNIT3D


class NST(FrenchTrackerMixin, UNIT3D):
    """Nostradamus (nostradamus.foo) — French private tracker with UNIT3D-compatible API."""

    # The upload-assistant wrapper uses two different category formats:
    #   - Upload (POST .../upload): sequential numeric IDs 1–5
    #   - Search (GET  .../filter): category slugs
    _SLUG_TO_NUM: dict[str, str] = {
        "film": "1",
        "serie-tv": "2",
        "animation": "3",
        "animation-serie": "4",
        "documentaire": "5",
    }

    def __init__(self, config):
        super().__init__(config, tracker_name="NST")
        self.config = config
        self.common = COMMON(config)
        self.tracker = "NST"
        self.base_url = "https://nostradamus.foo"
        # NST uses /api/upload-assistant/ prefix for UA compatibility
        self.id_url = f"{self.base_url}/api/upload-assistant/torrents/"
        self.upload_url = f"{self.base_url}/api/upload-assistant/torrents/upload"
        self.search_url = f"{self.base_url}/api/upload-assistant/torrents/filter"
        self.torrent_url = f"{self.base_url}/torrents/"
        self.rehost_images_manager = RehostImagesManager(config)
        self.approved_image_hosts = ["imgbox", "ptscreens", "onlyimage", "pixhost"]
        self.banned_groups: list[str] = []
        self.source_flag = "NST"

    # ── FrenchTrackerMixin overrides ──────────────────────────────────

    WEB_LABEL: str = "WEB"

    # NST uses original (English) titles
    PREFER_ORIGINAL_TITLE: bool = True

    # NST wants streaming service in name
    INCLUDE_SERVICE_IN_NAME: bool = True

    # ── Category helpers ──────────────────────────────────────────────

    def _resolve_category_slug(self, meta: dict[str, Any], cat: str = "") -> str:
        """Return the category slug for the given meta/category."""
        cat = cat or meta.get("category", "")
        genres = str(meta.get("genres", "")).lower()
        keywords = str(meta.get("keywords", "")).lower()
        is_anime = bool(meta.get("anime"))

        if cat == "MOVIE" or not cat:
            if "documentary" in genres or "documentary" in keywords:
                return "documentaire"
            if is_anime:
                return "animation"
            return "film"
        elif cat == "TV":
            if is_anime:
                return "animation-serie"
            if "documentary" in genres or "documentary" in keywords:
                return "documentaire"
            return "serie-tv"
        return "film"

    # ── Category / type / resolution ──────────────────────────────────
    # get_category_id returns **numeric** IDs for the upload endpoint.
    # search_existing is overridden to pass slugs to the filter endpoint.

    async def get_category_id(self, meta: dict[str, Any], category: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        category_id = {
            "MOVIE": "1",
            "TV": "2",
        }

        if mapping_only:
            return category_id
        if reverse:
            return {v: k for k, v in category_id.items()}

        slug = self._resolve_category_slug(meta, category)
        return {"category_id": self._SLUG_TO_NUM.get(slug, "1")}

    async def get_type_id(self, meta: dict[str, Any], type: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        type_id = {
            "DISC": "1",
            "REMUX": "2",
            "ENCODE": "3",
            "WEBDL": "4",
            "WEBRIP": "5",
            "HDTV": "6",
        }
        if mapping_only:
            return type_id
        if reverse:
            return {v: k for k, v in type_id.items()}
        t = type or meta.get("type", "")
        return {"type_id": type_id.get(t, "0")}

    async def get_resolution_id(self, meta: dict[str, Any], resolution: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        resolution_id = {
            "4320p": "1",
            "2160p": "2",
            "1080p": "3",
            "1080i": "4",
            "720p": "5",
            "576p": "6",
            "576i": "7",
            "480p": "8",
            "480i": "9",
        }
        if mapping_only:
            return resolution_id
        if reverse:
            return {v: k for k, v in resolution_id.items()}
        r = resolution or meta.get("resolution", "")
        return {"resolution_id": resolution_id.get(r, "10")}

    # ── Search override (filter needs slugs, not numeric IDs) ─────────

    async def search_existing(self, meta: dict[str, Any], _: Any) -> list[dict[str, Any]]:
        """Use category slugs for the filter endpoint, then delegate to UNIT3D."""
        # Temporarily stash the slug so the parent's search_existing sends it
        # instead of the numeric upload ID.
        original = self.get_category_id

        slug = self._resolve_category_slug(meta)

        async def _slug_category_id(_m: dict[str, Any], **_kw: Any) -> dict[str, str]:
            return {"category_id": slug}

        self.get_category_id = _slug_category_id  # type: ignore[assignment]
        try:
            return await super().search_existing(meta, _)
        finally:
            self.get_category_id = original  # type: ignore[assignment]

    async def get_additional_checks(self, meta: dict[str, Any]) -> bool:
        # NST requires at least one VF audio track (any variant: VFF, VFQ, VFB, …)
        french_languages = ["french", "fre", "fra", "fr", "français", "francais", "fr-fr", "fr-ca", "fr-be", "fr-ch", "fr-qc"]
        if not await self.common.check_language_requirements(
            meta,
            self.tracker,
            languages_to_check=french_languages,
            check_audio=True,
            check_subtitle=False,
        ):
            console.print(f"[bold red]{self.tracker} requiert au moins une piste audio VF.[/bold red]")
            return False
        return True

    # ── Image host gating ─────────────────────────────────────────────

    async def check_image_hosts(self, meta: dict[str, Any]) -> None:
        url_host_mapping = {
            "imgbox.com": "imgbox",
            "ptscreens.com": "ptscreens",
            "onlyimage.org": "onlyimage",
            "pixhost.to": "pixhost",
        }
        await self.rehost_images_manager.check_hosts(
            meta,
            self.tracker,
            url_host_mapping=url_host_mapping,
            img_host_index=1,
            approved_image_hosts=self.approved_image_hosts,
        )

    # ── Description fixup (strip unsupported BBCode extensions) ────

    @staticmethod
    def _sanitize_bbcode(text: str) -> str:
        """Rewrite BBCode tags that NST's upload-assistant doesn't render.

        NST processes standard BBCode ([img], [url], [center], [b], ...)
        but does NOT support the ``[img=N]`` size variant.  Without the
        size hint images render at their native resolution, so we also
        swap full-size URLs for smaller variants where possible.
        """
        # [img=300]url[/img] → [img]url[/img]  (drop size)
        s = re.sub(r"\[img=\d+\]", "[img]", text, flags=re.IGNORECASE)
        # TMDB poster: /original/ → /w300/  (keep poster small)
        s = re.sub(r"(image\.tmdb\.org/t/p/)original/", r"\1w300/", s)
        # imgbox screenshots: full-size _o.png → thumbnail _t.png
        s = re.sub(
            r"(\[img\]https?://)images(2\.imgbox\.com/.+?)_o\.png(\[/img\])",
            r"\1thumbs\2_t.png\3",
            s,
            flags=re.IGNORECASE,
        )
        # ptscreens / onlyimage (Chevereto): foo.png → foo.md.png (medium)
        s = re.sub(
            r"(\[img\]https?://(?:ptscreens\.com|onlyimage\.org)/images/.+?)(\.\w+)(\[/img\])",
            r"\1.md\2\3",
            s,
            flags=re.IGNORECASE,
        )
        # pixhost: img*.pixhost.to/images/ → t*.pixhost.to/thumbs/
        s = re.sub(
            r"(\[img\]https?://)img(\d+\.pixhost\.to)/images/",
            r"\1t\2/thumbs/",
            s,
            flags=re.IGNORECASE,
        )
        # [size=N]text[/size] → text  (strip, not supported)
        s = re.sub(r"\[/?size(?:=\d+)?\]", "", s, flags=re.IGNORECASE)
        # [color=X]text[/color] → text  (strip, not supported)
        s = re.sub(r"\[color=[^\]]*\]", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\[/color\]", "", s, flags=re.IGNORECASE)
        # [pre]text[/pre] → [code]text[/code]
        s = re.sub(r"\[pre\]", "[code]", s, flags=re.IGNORECASE)
        s = re.sub(r"\[/pre\]", "[/code]", s, flags=re.IGNORECASE)
        return s

    async def get_description(self, meta: dict[str, Any]) -> dict[str, str]:
        desc = await self._build_description(meta)
        return {"description": self._sanitize_bbcode(desc)}

    # ── Custom description (technical focus — NST header has synopsis) ─

    async def _build_description(self, meta: dict[str, Any]) -> str:
        """Build a concise BBCode description for NST.

        NST's torrent page already displays the poster, synopsis, genres,
        external links (IMDb/TMDB), and quality badge.  The description
        therefore focuses on technical details, audio/subtitle tracks,
        release metadata, and screenshots.
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
        personal_note = meta.get("personal_note", "")
        if personal_note:
            parts.append(f"[b]Note :[/b] {personal_note}")
        parts.append("")

        # ── Captures d'écran ──
        include_screens = self.config["TRACKERS"].get(self.tracker, {}).get("include_screenshots", False)
        image_list: list[dict[str, Any]] = meta.get("image_list", []) if include_screens else []
        if image_list:
            parts.append("[b]Captures d'écran[/b]")
            parts.append("")
            img_lines: list[str] = []
            for img in image_list:
                raw = img.get("raw_url", "")
                web = img.get("web_url", "")
                if raw:
                    img_lines.append(f"[url={web}][img]{raw}[/img][/url]" if web else f"[img]{raw}[/img]")
            if img_lines:
                parts.append("\n".join(img_lines))
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

    async def get_torrent_id(self, response_data: dict[str, Any]) -> str:
        """Extract UUID torrent ID from NST's upload-assistant download URL.

        NST returns URLs like:
            http://nostradamus.foo/api/upload-assistant/torrents/{uuid}/download
        """
        try:
            match = re.search(r"/torrents/([0-9a-f-]{36})", response_data.get("data", ""))
            if match:
                return match.group(1)
        except (TypeError, KeyError):
            pass
        console.print("[yellow]Could not parse torrent UUID from NST response.[/yellow]")
        return ""

    async def get_additional_data(self, meta: dict[str, Any]) -> dict[str, Any]:
        data: dict[str, Any] = {"description_format": "bbcode"}
        # Map the language tag already computed by FrenchTrackerMixin to
        # NST's fixed "langue" choices: Multi, Français, Anglais, VOSTFR,
        # VFSTFR, Muet.
        data["langue"] = self._detect_nst_langue(meta)
        return data

    @staticmethod
    def _detect_nst_langue(meta: dict[str, Any]) -> str:
        """Derive the NST langue tag from the release name / audio metadata."""
        name = meta.get("name", "")
        upper = name.upper()

        # FrenchTrackerMixin embeds MULTI.VFF / VOSTFR / etc. in the name
        if ".MULTI." in upper or upper.startswith("MULTI.") or upper.endswith(".MULTI"):
            return "Multi"
        if ".VOSTFR." in upper or upper.endswith(".VOSTFR"):
            return "VOSTFR"
        if ".SUBFRENCH." in upper or upper.endswith(".SUBFRENCH"):
            return "VOSTFR"

        # Fallback: inspect audio_languages when no tag in name
        fr_aliases = {"french", "français", "francais", "fra", "fre", "fr", "fr-fr", "fr-ca", "fr-be", "fr-ch", "fr-qc"}
        en_aliases = {"english", "eng", "en"}
        raw_audio = [lang.lower().strip() for lang in (meta.get("audio_languages") or [])]

        # Normalize region codes (e.g. "fr-fr" → "fr") for counting distinct languages
        normalized = {la.split("-")[0] if "-" in la else la for la in raw_audio}
        has_fr = any(la in fr_aliases for la in raw_audio)
        has_en = any(la in en_aliases for la in raw_audio)

        # "Multi" only when genuinely different languages are present
        non_fr = normalized - {"fr", "fra", "fre", "french", "français", "francais"}
        if has_fr and non_fr:
            return "Multi"
        if has_fr:
            return "Français"
        if has_en:
            return "Anglais"
        return ""
