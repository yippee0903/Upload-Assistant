# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
#
# V3X (v3x.club) — French private tracker with a custom (non-UNIT3D) API.
#
# API surface (api.v3x.club):
#   GET  /torrents?q=…&page=…           public listing (torrents/total/page/perPage);
#     the filter param is q — "search" and the like are silently ignored
#   GET  /torrents/{uuid}               detail: tmdbId, infoHash, description, nfo, files…
#   GET  /categories                    public category tree (id/name/children)
#   POST /api/torrents                  upload — multipart, Authorization: Bearer <api key>
#     required: file (.torrent), name, categoryId (subcategory number), rightsDeclared
#     accepted: description, nfo, tmdbId, anonymous, language

import contextlib
import re
from typing import Any, Optional

import aiofiles
import httpx

from src.console import console
from src.get_desc import DescriptionBuilder
from src.tmdb import TmdbManager
from src.trackers.COMMON import COMMON
from src.trackers.FRENCH import FrenchTrackerMixin

Meta = dict[str, Any]


class V3X(FrenchTrackerMixin):
    WEB_LABEL: str = "WEB"
    notag_label: str = "NOTAG"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.common = COMMON(config)
        self.tracker = "V3X"
        self.source_flag = "V3X"
        self.base_url = "https://v3x.club"
        self.api_base = "https://api.v3x.club"
        self.upload_url = f"{self.api_base}/api/torrents"
        self.search_url = f"{self.api_base}/torrents"
        self.torrent_url = f"{self.base_url}/torrents/"
        self.api_key = str(self.config["TRACKERS"].get(self.tracker, {}).get("api_key", "") or "").strip()
        self.tmdb_manager = TmdbManager(config)
        self.banned_groups: list[Any] = []

    async def get_name(self, meta: Meta) -> dict[str, str]:
        result = await super().get_name(meta)
        result["name"] = self._enforce_web_codec_convention(meta, result["name"])
        return result

    def _format_name(self, raw_name: str) -> dict[str, str]:
        result = super()._format_name(raw_name)
        result["name"] = self._normalize_audio_name_tokens(result["name"])
        return result

    async def get_category_id(self, meta: Meta) -> str:
        # Subcategory ids: Film=8, Animation=2, Documentaire=5,
        # Série TV=9, Animation Série=3, Série Documentaire=6.
        genres = str(meta.get("genres", "")).lower()
        keywords = str(meta.get("keywords", "")).lower()
        is_docu = "documentary" in genres or "documentary" in keywords
        # Explicit anime signals win; a genre-only "animation" yields to the
        # documentary category (animated documentaries).
        is_anime_explicit = bool(meta.get("anime") or meta.get("mal_id"))
        is_animation = "animation" in genres
        if meta.get("category") == "TV":
            if is_anime_explicit:
                return "3"
            if is_docu:
                return "6"
            return "3" if is_animation else "9"
        if is_anime_explicit:
            return "2"
        if is_docu:
            return "5"
        return "2" if is_animation else "8"

    @staticmethod
    def _get_language_tag(name: str) -> str:
        """Language field following the site convention: comma-separated
        tags from the release name, e.g. "MULTI,VFF", "FRENCH" or "VOSTFR".
        """
        tokens = set(name.upper().replace("-", ".").replace("_", ".").replace(" ", ".").split("."))
        parts: list[str] = []
        if "MULTI" in tokens:
            parts.append("MULTI")
        for tag in ("VF2", "VFF", "VFI", "VFQ", "VFB", "TRUEFRENCH", "FRENCH"):
            if tag in tokens:
                parts.append(tag)
                break
        if not parts and ("VOSTFR" in tokens or "SUBFRENCH" in tokens):
            return "VOSTFR"
        return ",".join(parts)

    async def search_existing(self, meta: Meta, _disctype: Any = None) -> list[dict[str, Any]]:
        dupes: list[dict[str, Any]] = []
        if not await self.get_additional_checks(meta):
            meta["skipping"] = self.tracker
            return dupes
        search_term = str(meta.get("title") or "")
        if not search_term:
            return dupes
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(self.search_url, params={"q": search_term, "perPage": 100})
                if response.status_code != 200:
                    console.print(f"[yellow]{self.tracker}: search returned HTTP {response.status_code}[/yellow]")
                    return dupes
                payload = response.json()
        except (httpx.RequestError, httpx.TimeoutException, ValueError) as e:
            console.print(f"[yellow]{self.tracker}: search failed: {type(e).__name__}[/yellow]")
            return dupes

        torrents = payload.get("torrents") if isinstance(payload, dict) else None
        if not isinstance(torrents, list):
            console.print(f"[yellow]{self.tracker}: unexpected search response shape[/yellow]")
            return dupes

        meta_tmdb = int(meta.get("tmdb_id") or 0)
        for torrent in torrents:
            if not isinstance(torrent, dict):
                continue
            # The listing has no tmdbId; keep every name match. The detail
            # endpoint has it, but one request per result is not worth it for
            # a dupe pre-filter.
            _ = meta_tmdb
            dupes.append({"name": torrent.get("name", ""), "size": torrent.get("size", 0), "link": f"{self.torrent_url}{torrent.get('slug') or torrent.get('id', '')}"})
        return await self._check_french_lang_dupes(dupes, meta)

    async def edit_desc(self, meta: Meta) -> None:
        # Manual-mode hook required by trackerhandle; the description is
        # built at upload time instead.
        return None

    async def _build_description(self, meta: Meta) -> str:
        """BBCode description in the C411/TORR9 presentation style: centered,
        section headers, language flags for audio/subtitles, clickable
        screenshot thumbnails. The MediaInfo report goes into the dedicated
        nfo upload field, not here."""
        C = "#3d85c6"  # accent colour
        parts: list[str] = []

        mi_text = await self._get_mediainfo_text(meta)

        fr_data: dict[str, Any] = {}
        with contextlib.suppress(Exception):
            fr_data = await self.tmdb_manager.get_tmdb_localized_data(meta, data_type="main", language="fr", append_to_response="") or {}

        parts.append("[center]")

        title = str(fr_data.get("title") or fr_data.get("name") or meta.get("title") or "").strip()
        year = str(meta.get("year") or "").strip()
        if title:
            heading = f"{title} ({year})" if year else title
            parts.append(f"[b][color={C}][size=200]{heading}[/size][/color][/b]")
            parts.append("")

        poster = str(meta.get("poster") or "")
        if "image.tmdb.org/t/p/" in poster:
            poster = re.sub(r"/t/p/[^/]+/", "/t/p/w500/", poster)
        if poster:
            parts.append(f"[img]{poster}[/img]")
            parts.append("")

        # ── Synopsis ──
        parts.append(f"[b][color={C}][size=130]━━━ Synopsis ━━━[/size][/color][/b]")
        synopsis = str(fr_data.get("overview", "")).strip() or str(meta.get("overview", "")).strip() or "Aucun synopsis disponible."
        parts.append(synopsis)
        parts.append("")

        # ── Informations techniques ──
        parts.append(f"[b][color={C}][size=130]━━━ Informations techniques ━━━[/size][/color][/b]")
        type_label = self._get_type_label(meta)
        if type_label:
            parts.append(f"[b][color={C}]Type :[/color][/b] {type_label}")
        source = str(meta.get("source") or meta.get("type") or "")
        if source:
            parts.append(f"[b][color={C}]Source :[/color][/b] {source}")
        resolution = str(meta.get("resolution") or "")
        if resolution:
            parts.append(f"[b][color={C}]Résolution :[/color][/b] {resolution}")
        container = self._format_container(mi_text)
        if container:
            parts.append(f"[b][color={C}]Format vidéo :[/color][/b] {container}")
        codec = str(meta.get("video_encode") or meta.get("video_codec") or "").strip()
        if codec:
            parts.append(f"[b][color={C}]Codec vidéo :[/color][/b] {codec}")
        hdr_badge = self._format_hdr_dv_bbcode(meta)
        if hdr_badge:
            parts.append(f"[b][color={C}]HDR :[/color][/b] {hdr_badge}")
        parts.append("")

        # ── Audio (language flags from the shared French mixin) ──
        parts.append(f"[b][color={C}][size=130]━━━ Audio(s) ━━━[/size][/color][/b]")
        audio_lines = self._format_audio_bbcode(mi_text, meta)
        if audio_lines:
            parts.extend(f" [i]{line}[/i]" for line in audio_lines)
        else:
            parts.append(" [i]Non spécifié[/i]")
        parts.append("")

        # ── Subtitles ──
        parts.append(f"[b][color={C}][size=130]━━━ Sous-titre(s) ━━━[/size][/color][/b]")
        sub_lines = self._format_subtitle_bbcode(mi_text, meta)
        if sub_lines:
            parts.extend(f" [i]{line}[/i]" for line in sub_lines)
        else:
            parts.append(" [i]Aucun[/i]")
        parts.append("")

        # ── Release ──
        parts.append(f"[b][color={C}][size=130]━━━ Release ━━━[/size][/color][/b]")
        parts.append(f"[b][color={C}]Titre :[/color][/b] {meta.get('uuid', '')}")
        note = await DescriptionBuilder(self.tracker, self.config).get_personal_note(meta)
        if note:
            parts.append(f"[b][color={C}]Note :[/color][/b] {note}")
        size_str = self._get_total_size(meta, mi_text)
        if size_str:
            parts.append(f"[b][color={C}]Taille totale :[/color][/b] {size_str}")
        file_count = self._count_files(meta)
        if file_count:
            parts.append(f"[b][color={C}]Nombre de fichiers :[/color][/b] {file_count}")
        group = self._get_release_group(meta)
        if group:
            parts.append(f"[b][color={C}]Groupe :[/color][/b] {group}")
        parts.append("")

        # ── Screenshots: clickable thumbnails, two per row. The V3X parser
        # only understands a bare [img] tag (no [img=N] sizing), so small
        # renderings depend on the image host providing a thumbnail img_url.
        image_list = meta.get("image_list") or []
        if image_list:
            parts.append(f"[b][color={C}][size=130]━━━ Captures d'écran ━━━[/size][/color][/b]")
            thumbs = [
                f"[url={img.get('web_url') or img.get('raw_url', '')}][img]{img.get('img_url') or img.get('raw_url', '')}[/img][/url]"
                for img in image_list
                if img.get("img_url") or img.get("raw_url")
            ]
            parts.extend(" ".join(thumbs[i : i + 2]) for i in range(0, len(thumbs), 2))

        parts.append("[/center]")
        ua_sig = meta.get("ua_signature", "Created by Upload Assistant")
        parts.append(f"[right][url=https://github.com/yippee0903/Upload-Assistant][size=75]{ua_sig}[/size][/url][/right]")

        return "\n".join(parts).strip()

    async def _read_tmp_file(self, meta: Meta, filename: str) -> Optional[bytes]:
        path = f"{meta['base_dir']}/tmp/{meta['uuid']}/{filename}"
        try:
            async with aiofiles.open(path, "rb") as f:
                return await f.read()
        except OSError:
            return None

    async def upload(self, meta: Meta, _disctype: str) -> bool:
        # Embed the release NFO in the .torrent when one exists (cheap
        # patch/clone paths before a full rehash), like the other French trackers.
        if self._get_nfo_files(meta):
            await self._recreated_torrent_if_nfo(meta, self.common, self.config, self.tracker, self.source_flag)
        else:
            await self.common.create_torrent_for_upload(meta, self.tracker, self.source_flag)

        name_result = await self.get_name(meta)
        name = name_result.get("name", "") if isinstance(name_result, dict) else str(name_result)

        torrent_bytes = await self._read_tmp_file(meta, f"[{self.tracker}].torrent")
        if not torrent_bytes:
            meta["tracker_status"][self.tracker]["status_message"] = "data error: torrent file missing"
            return False

        description = await self._build_description(meta)
        # The site rules keep the ORIGINAL release NFO (shipped untouched);
        # otherwise fall back to MediaInfo / a generated scene NFO, with the
        # "Complete name" line patched to the tracker release name.
        nfo_text = ""
        is_scene_nfo = bool(self._get_nfo_files(meta))
        nfo_path = await self._get_or_generate_nfo(meta)
        if nfo_path:
            try:
                async with aiofiles.open(nfo_path, "rb") as f:
                    nfo_text = (await f.read()).decode("utf-8", errors="replace")
            except OSError:
                nfo_text = ""
        if nfo_text and not is_scene_nfo:
            nfo_text = self._patch_mi_filename(nfo_text, name)

        data: dict[str, Any] = {
            "name": name,
            "categoryId": await self.get_category_id(meta),
            "rightsDeclared": "true",
            "description": description,
            "anonymous": "true" if (meta.get("anon") or self.config["TRACKERS"].get(self.tracker, {}).get("anon", False)) else "false",
        }
        if nfo_text:
            data["nfo"] = nfo_text
        if int(meta.get("tmdb_id") or 0):
            data["tmdbId"] = str(meta["tmdb_id"])
        # MediaInfo-based tag first (knows VOF/VOQ/VFB/AD/MUET); fall back
        # to name tokens when MediaInfo is unavailable (e.g. discs).
        language = (await self._build_audio_string(meta)).replace(".", ",") or self._get_language_tag(name)
        if language:
            data["language"] = language

        files = {"file": (f"{name}.torrent", torrent_bytes, "application/x-bittorrent")}
        headers = {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}

        if meta.get("debug"):
            console.print(f"[cyan]{self.tracker} debug: would upload '{name}' with categoryId={data['categoryId']}[/cyan]")
            meta["tracker_status"][self.tracker]["status_message"] = "Debug mode, not uploaded."
            return True

        response = None
        for attempt, timeout in enumerate((60.0, 120.0)):
            try:
                async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                    response = await client.post(self.upload_url, files=files, data=data, headers=headers)
                break
            except (httpx.RequestError, httpx.TimeoutException) as e:
                if attempt == 0:
                    console.print(f"[yellow]{self.tracker}: upload attempt failed ({type(e).__name__}), retrying…[/yellow]")
                    continue
                meta["tracker_status"][self.tracker]["status_message"] = f"data error: upload failed: {type(e).__name__}"
                return False

        try:
            response_data = response.json()
        except ValueError:
            response_data = {"error": f"HTTP {response.status_code}"}

        if response.status_code in (200, 201) and isinstance(response_data, dict) and not response_data.get("error"):
            torrent_id = response_data.get("id") or (response_data.get("torrent") or {}).get("id")
            if torrent_id:
                meta["tracker_status"][self.tracker]["torrent_id"] = str(torrent_id)
            meta["tracker_status"][self.tracker]["status_message"] = response_data
            return True

        meta["tracker_status"][self.tracker]["status_message"] = f"data error: {response_data}"
        return False
