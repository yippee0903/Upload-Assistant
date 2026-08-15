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
            fr_data = await self.tmdb_manager.get_tmdb_localized_data(meta, data_type="main", language="fr", append_to_response="credits") or {}

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

        # ── Informations (TMDB metadata, C411-style, values in italics) ──
        info_lines: list[str] = []
        original_title = str(meta.get("original_title") or meta.get("title") or "").strip()
        if original_title and original_title != title:
            info_lines.append(f"[b][color={C}]Titre original :[/color][/b] [i]{original_title}[/i]")
        countries = fr_data.get("production_countries", meta.get("production_countries", []))
        if isinstance(countries, list):
            names = [c.get("name", "") for c in countries if isinstance(c, dict) and c.get("name")]
            if names:
                info_lines.append(f"[b][color={C}]Pays :[/color][/b] [i]{', '.join(names)}[/i]")
        genres_list = fr_data.get("genres", [])
        genre_names = [g["name"] for g in genres_list if isinstance(g, dict) and g.get("name")] if isinstance(genres_list, list) else []
        if genre_names:
            info_lines.append(f"[b][color={C}]Genres :[/color][/b] [i]{', '.join(genre_names)}[/i]")
        elif meta.get("genres"):
            info_lines.append(f"[b][color={C}]Genres :[/color][/b] [i]{meta['genres']}[/i]")
        release_date = str(fr_data.get("release_date") or fr_data.get("first_air_date") or meta.get("release_date") or meta.get("first_air_date") or "").strip()
        if release_date:
            info_lines.append(f"[b][color={C}]Date de sortie :[/color][/b] [i]{self._format_french_date(release_date)}[/i]")
        elif year:
            info_lines.append(f"[b][color={C}]Date de sortie :[/color][/b] [i]{year}[/i]")
        runtime = fr_data.get("runtime") or meta.get("runtime", 0)
        if runtime:
            h, m = divmod(int(runtime), 60)
            info_lines.append(f"[b][color={C}]Durée :[/color][/b] [i]{f'{h}h{m:02d}' if h else f'{m}min'}[/i]")

        credits = fr_data.get("credits", {})
        crew = credits.get("crew", []) if isinstance(credits, dict) else []
        cast = credits.get("cast", []) if isinstance(credits, dict) else []
        directors = [p["name"] for p in crew if isinstance(p, dict) and p.get("job") == "Director" and p.get("name")]
        if directors:
            label = "Réalisateur" if len(directors) == 1 else "Réalisateurs"
            info_lines.append(f"[b][color={C}]{label} :[/color][/b] [i]{', '.join(directors)}[/i]")
        seen_w: set[str] = set()
        writers: list[str] = []
        for p in crew:
            if isinstance(p, dict) and p.get("job") in ("Screenplay", "Writer", "Story") and p.get("name") and p["name"] not in seen_w:
                writers.append(p["name"])
                seen_w.add(p["name"])
        if writers:
            label = "Scénariste" if len(writers) == 1 else "Scénaristes"
            info_lines.append(f"[b][color={C}]{label} :[/color][/b] [i]{', '.join(writers)}[/i]")
        actors = [p["name"] for p in cast[:5] if isinstance(p, dict) and p.get("name")]
        if actors:
            info_lines.append(f"[b][color={C}]Acteurs :[/color][/b] [i]{', '.join(actors)}[/i]")
        vote_avg = fr_data.get("vote_average") or meta.get("vote_average")
        vote_count = fr_data.get("vote_count") or meta.get("vote_count")
        if vote_avg and vote_count:
            info_lines.append(f"[b][color={C}]Note des spectateurs :[/color][/b] [i]{vote_avg} ({vote_count} votes)[/i]")

        ext_links: list[str] = []
        imdb_id = meta.get("imdb_id", 0)
        if imdb_id and int(imdb_id) > 0:
            imdb_url = meta.get("imdb_info", {}).get("imdb_url", "") if isinstance(meta.get("imdb_info"), dict) else ""
            ext_links.append(f"[url={imdb_url or f'https://www.imdb.com/title/tt{str(imdb_id).zfill(7)}/'}]IMDb[/url]")
        if int(meta.get("tmdb_id") or 0):
            tmdb_cat = "tv" if str(meta.get("category", "")).upper() == "TV" else "movie"
            ext_links.append(f"[url=https://www.themoviedb.org/{tmdb_cat}/{meta['tmdb_id']}]TMDB[/url]")
        if meta.get("tvdb_id"):
            ext_links.append(f"[url=https://www.thetvdb.com/?id={meta['tvdb_id']}&tab=series]TVDB[/url]")
        if meta.get("mal_id"):
            ext_links.append(f"[url=https://myanimelist.net/anime/{meta['mal_id']}]MAL[/url]")

        if info_lines or ext_links:
            parts.append(f"[b][color={C}][size=130]━━━ Informations ━━━[/size][/color][/b]")
            parts.extend(info_lines)
            if ext_links:
                parts.append(" | ".join(ext_links))
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
        service = str(meta.get("service") or "")
        if service:
            parts.append(f"[b][color={C}]Service :[/color][/b] {service}")
        resolution = str(meta.get("resolution") or "")
        if resolution:
            parts.append(f"[b][color={C}]Résolution :[/color][/b] {resolution}")
        container = self._format_container(mi_text)
        if container:
            parts.append(f"[b][color={C}]Format vidéo :[/color][/b] {container}")
        # Prefer the encode label matching the release name; append the raw
        # MediaInfo format in parentheses when it differs: "H265 (HEVC)".
        codec = str(meta.get("video_encode") or meta.get("video_codec") or "").strip().replace("H.264", "H264").replace("H.265", "H265")
        raw_codec = str(meta.get("video_codec") or "").strip()
        if codec and raw_codec and raw_codec != codec:
            codec = f"{codec} ({raw_codec})"
        if codec:
            parts.append(f"[b][color={C}]Codec vidéo :[/color][/b] {codec}")
        hdr_badge = self._format_hdr_dv_bbcode(meta)
        if hdr_badge:
            parts.append(f"[b][color={C}]HDR :[/color][/b] {hdr_badge}")
        if mi_text:
            vbr_match = re.search(r"(?:^|\n)Bit rate\s*:\s*(.+?)\s*(?:\n|$)", mi_text)
            if vbr_match:
                parts.append(f"[b][color={C}]Débit vidéo :[/color][/b] {vbr_match.group(1).strip()}")
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
