# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any

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

    async def search_existing(self, meta: dict[str, Any], disctype: Any) -> list[dict[str, Any]]:
        """Use category slugs for the filter endpoint, then delegate to UNIT3D."""
        # Temporarily stash the slug so the parent's search_existing sends it
        # instead of the numeric upload ID.
        original = self.get_category_id

        slug = self._resolve_category_slug(meta)

        async def _slug_category_id(_m: dict[str, Any], **_kw: Any) -> dict[str, str]:
            return {"category_id": slug}

        self.get_category_id = _slug_category_id  # type: ignore[assignment]
        try:
            return await super().search_existing(meta, disctype)
        finally:
            self.get_category_id = original  # type: ignore[assignment]

    async def get_additional_checks(self, meta: dict[str, Any]) -> bool:
        french_languages = ["french", "fre", "fra", "fr", "français", "francais", "fr-fr", "fr-ca"]
        if not await self.common.check_language_requirements(
            meta,
            self.tracker,
            languages_to_check=french_languages,
            check_audio=True,
            check_subtitle=True,
            require_both=False,
        ):
            console.print(f"[bold red]Language requirements not met for {self.tracker}.[/bold red]")
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
        s = s.replace("images2.imgbox.com", "thumbs2.imgbox.com")
        s = s.replace("_o.png", "_t.png")
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
        # [pre]text[/pre] → [code]text[/code]
        s = re.sub(r"\[pre\]", "[code]", s, flags=re.IGNORECASE)
        s = re.sub(r"\[/pre\]", "[/code]", s, flags=re.IGNORECASE)
        return s

    async def get_description(self, meta: dict[str, Any]) -> dict[str, str]:
        desc = await super().get_description(meta)
        return {"description": self._sanitize_bbcode(desc["description"])}

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

    async def get_additional_data(self, _meta: dict[str, Any]) -> dict[str, str]:
        return {"description_format": "bbcode"}
