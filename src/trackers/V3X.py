# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
#
# V3X (v3x.club) — French private tracker with a custom (non-UNIT3D) API.
#
# API surface (api.v3x.club):
#   GET  /torrents?q=…&page=…           public listing (torrents/total/page/perPage);
#     the filter param is q — "search" and the like are silently ignored
#   GET  /torrents/{uuid}               detail: tmdbId, infoHash, description, nfo, files…
#   GET  /categories                    public category tree (id/name/children)
#   GET  /api/categories                key-authenticated tree with subcategory ids
#   POST /api/torrents                  upload — multipart, Authorization: Bearer <api key>
#                                       (?apikey= also accepted; X-Api-Key is NOT)
#     required: file (.torrent), categoryId (SUBcategory id), rightsDeclared;
#               movies/series also require nfo and tmdbId (or tmdbUrl)
#     accepted: name, description, descriptionFormat, language, title,
#               posterUrl, backdropUrl, anonymous
#   Browse routes (/torrents listing & detail) require a web session cookie —
#   API keys are rejected there since the 2026-08 site update.

import asyncio
import contextlib
import os
import re
from typing import Any, Optional

import aiofiles
import httpx
from torf import Torrent
from unidecode import unidecode

from src.console import console
from src.get_desc import DescriptionBuilder
from src.rehostimages import RehostImagesManager
from src.tmdb import TmdbManager
from src.trackers.COMMON import COMMON
from src.trackers.FRENCH import _FRENCH_AUDIO_THRESHOLD as FRENCH_AUDIO_THRESHOLD
from src.trackers.FRENCH import FrenchTrackerMixin

Meta = dict[str, Any]

RETRY_DELAY = 5.0  # seconds between upload retries


class V3X(FrenchTrackerMixin):
    WEB_LABEL: str = "WEB"
    notag_label: str = "NOTAG"
    # Site catalog convention: original title in the release name (the French
    # title goes in the fiche's separate title field); originally-French
    # works keep their French title.
    PREFER_ORIGINAL_TITLE: bool = True

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
        self._session_cookies: Optional[httpx.Cookies] = None
        self.approved_image_hosts = ["imgbox", "imgbb", "postimg", "pixhost", "ptscreens"]
        self.rehost_images_manager = RehostImagesManager(config)

    async def check_image_hosts(self, meta: Meta) -> None:
        """Rehost screenshots to an approved host when needed; the result
        lands in meta["V3X_images_key"] and the description prefers it."""
        await self.rehost_images_manager.check_hosts(
            meta,
            self.tracker,
            img_host_index=1,
            approved_image_hosts=self.approved_image_hosts,
        )

    async def _login_session_cookies(self) -> Optional[httpx.Cookies]:
        """Log in with the site credentials and cache the session cookie.

        Browse routes (listing/detail) only accept a web session since the
        2026-08 site update — API keys are upload-only there.
        """
        if self._session_cookies is not None:
            return self._session_cookies
        cfg = self.config["TRACKERS"].get(self.tracker, {})
        login = str(cfg.get("username", "") or "").strip()
        password = str(cfg.get("password", "") or "")
        if not login or not password:
            return None
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(f"{self.api_base}/auth/login", json={"login": login, "password": password})
        except (httpx.RequestError, httpx.TimeoutException) as e:
            console.print(f"[yellow]{self.tracker}: login failed: {type(e).__name__}[/yellow]")
            return None
        if response.status_code != 200:
            console.print(f"[yellow]{self.tracker}: login failed (HTTP {response.status_code}) — check the username/password in your config.[/yellow]")
            return None
        self._session_cookies = response.cookies
        return self._session_cookies

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

        cookies = await self._login_session_cookies()
        if cookies is None:
            console.print(f"[yellow]{self.tracker}: the dupe search needs the site username/password in your config — skipping tracker to avoid a false negative.[/yellow]")
            meta["skipping"] = self.tracker
            return dupes

        title = str(meta.get("title") or "")
        fr_title = str(meta.get("frtitle") or "") or await self._get_french_title(meta)
        year_str = str(meta.get("year") or "").strip()
        resolution = str(meta.get("resolution") or "")
        group = self._get_release_group(meta)

        def _normalize(s: str) -> str:
            return re.sub(r"[^a-z0-9]", "", unidecode(s).lower())

        # The q filter matches ordered words against both the stored name and
        # the French title, separator- and accent-insensitive (improved since
        # the 2026-08 update). Query the full cleaned title — but never append
        # the year: TV names carry none and a year token yields zero matches.
        def _q(s: str) -> str:
            return " ".join(re.sub(r"[^a-zA-Z0-9 ]", " ", unidecode(s)).split())

        queries: list[str] = []
        ordered_titles = (fr_title, title) if str(meta.get("original_language", "")).lower() == "fr" else (title, fr_title)
        for t in ordered_titles:
            cleaned = _q(t)
            if cleaned and cleaned.lower() not in (q.lower() for q in queries):
                queries.append(cleaned)
        if not queries:
            return dupes

        title_norm = _normalize(title)
        fr_title_norm = _normalize(fr_title) if fr_title else ""
        resolution_norm = _normalize(resolution)
        group_norm = _normalize(group)
        seen_names: set[str] = set()
        debug = bool(meta.get("debug"))

        # A VOSTFR/VO upload must be blocked by an equivalent French-audio
        # release from ANY group, so the group filter below must not drop
        # those candidates before _check_french_lang_dupes can flag them.
        upload_audio = await self._build_audio_string(meta)
        upload_level = max((self._extract_french_lang_tag(part)[1] for part in upload_audio.split(".")), default=0)
        upload_lacks_french_audio = upload_level < FRENCH_AUDIO_THRESHOLD

        for search_term in queries:
            items: list[Any] = []
            page = 1
            incomplete = False
            total = None
            while page <= 50:  # hard cap so a misreported total can't loop forever
                try:
                    async with httpx.AsyncClient(timeout=30.0, cookies=cookies) as client:
                        response = await client.get(self.search_url, params={"q": search_term, "perPage": 100, "page": page})
                    if response.status_code != 200:
                        incomplete = True
                        break
                    payload = response.json()
                except (httpx.RequestError, httpx.TimeoutException, ValueError):
                    incomplete = True
                    break
                page_items = payload.get("torrents") if isinstance(payload, dict) else None
                if not isinstance(page_items, list):
                    incomplete = True
                    break
                items.extend(page_items)
                if not page_items:
                    break
                total = payload.get("total") if isinstance(payload.get("total"), int) else None
                if total is not None:
                    if len(items) >= total:
                        break
                elif len(page_items) < 100:
                    # No usable total: a short page means we reached the end;
                    # a full page means there may be more — keep going.
                    break
                page += 1

            # A failed page leaves a partial result set — a dupe could sit on
            # a page we never read. Fail closed: skip the tracker rather than
            # upload over a possible dupe.
            if incomplete:
                console.print(f"[yellow]{self.tracker}: incomplete dupe search for '{search_term}', skipping tracker to avoid a false negative.[/yellow]")
                meta["skipping"] = self.tracker
                return []

            for torrent in items:
                if not isinstance(torrent, dict):
                    continue
                name = str(torrent.get("name") or "")
                if not name:
                    continue
                name_norm = _normalize(name)
                if name_norm in seen_names:
                    continue
                # Relevance filters: title (EN or FR), year (movies), resolution, group
                if not ((title_norm and title_norm in name_norm) or (fr_title_norm and fr_title_norm in name_norm)):
                    if debug:
                        console.print(f"[dim]{self.tracker} dupe skip (title mismatch): {name}[/dim]")
                    continue
                if year_str and year_str not in name and meta.get("category") != "TV":
                    if debug:
                        console.print(f"[dim]{self.tracker} dupe skip (year mismatch): {name}[/dim]")
                    continue
                if resolution_norm and resolution_norm not in name_norm:
                    if debug:
                        console.print(f"[dim]{self.tracker} dupe skip (resolution mismatch): {name}[/dim]")
                    continue
                if group_norm and group_norm not in name_norm:
                    _, existing_level = self._extract_french_lang_tag(name)
                    if not (upload_lacks_french_audio and existing_level >= FRENCH_AUDIO_THRESHOLD):
                        if debug:
                            console.print(f"[dim]{self.tracker} dupe skip (group mismatch): {name}[/dim]")
                        continue
                    # Keep: superior French audio from another group — a
                    # potential language supersede for this VOSTFR/VO upload.
                seen_names.add(name_norm)
                dupes.append(
                    {
                        "name": name,
                        "size": torrent.get("size", 0),
                        "link": f"{self.torrent_url}{torrent.get('slug') or torrent.get('id', '')}",
                        "id": torrent.get("id"),
                    }
                )

        if debug:
            console.print(f"[cyan]{self.tracker} dupe search found {len(dupes)} result(s)[/cyan]")
        if dupes:
            await self._enrich_with_files(dupes, debug=debug)
        return await self._check_french_lang_dupes(dupes, meta)

    async def _enrich_with_files(self, dupes: list[dict[str, Any]], *, debug: bool = False) -> None:
        """Fetch each dupe's file list via GET /torrents/{uuid}.

        Enriches entries in-place with ``files``/``file_count`` so
        DupeChecker can compare filenames instead of falling back to name
        similarity. Failures leave the entry unchanged.
        """
        enrich_limit = 25  # one request per dupe — bound the sequential cost
        if len(dupes) > enrich_limit:
            console.print(f"[yellow]{self.tracker}: enriching only the first {enrich_limit} of {len(dupes)} dupes; the rest fall back to name similarity.[/yellow]")
        async with httpx.AsyncClient(timeout=20.0, cookies=self._session_cookies) as client:
            for entry in dupes[:enrich_limit]:
                torrent_id = entry.get("id")
                if not torrent_id:
                    continue
                try:
                    response = await client.get(f"{self.search_url}/{torrent_id}")
                    if response.status_code != 200:
                        continue
                    detail = response.json()
                except (httpx.RequestError, httpx.TimeoutException, ValueError):
                    continue
                files = detail.get("files") if isinstance(detail, dict) else None
                if isinstance(files, list):
                    paths = [f["path"] for f in files if isinstance(f, dict) and f.get("path")]
                    if paths:
                        entry["files"] = paths
                        entry["file_count"] = len(paths)
                        if debug:
                            console.print(f"[cyan]{self.tracker} enriched {entry.get('name')!r} with {len(paths)} file(s)[/cyan]")

    async def edit_desc(self, meta: Meta) -> None:
        # Manual-mode hook required by trackerhandle; the description is
        # built at upload time instead.
        return None

    async def _build_description(self, meta: Meta) -> str:
        """BBCode description in the C411 presentation style: centered,
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
        if not directors and isinstance(meta.get("tmdb_directors"), list):
            directors = [d.get("name", d) if isinstance(d, dict) else str(d) for d in meta["tmdb_directors"]]
            directors = [d for d in directors if d]
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
        imdb_digits = re.sub(r"^tt", "", str(meta.get("imdb_id") or ""), flags=re.IGNORECASE)
        if imdb_digits.isdigit() and int(imdb_digits) > 0:
            imdb_url = meta.get("imdb_info", {}).get("imdb_url", "") if isinstance(meta.get("imdb_info"), dict) else ""
            ext_links.append(f"[url={imdb_url or f'https://www.imdb.com/title/tt{imdb_digits.zfill(7)}/'}]IMDb[/url]")
        tmdb_digits = str(meta.get("tmdb_id") or "")
        if tmdb_digits.isdigit() and int(tmdb_digits) > 0:
            tmdb_cat = "tv" if str(meta.get("category", "")).upper() == "TV" else "movie"
            ext_links.append(f"[url=https://www.themoviedb.org/{tmdb_cat}/{tmdb_digits}]TMDB[/url]")
        if meta.get("tvdb_id"):
            ext_links.append(f"[url=https://www.thetvdb.com/?id={meta['tvdb_id']}&tab=series]TVDB[/url]")
        if meta.get("tvmaze_id"):
            ext_links.append(f"[url=https://www.tvmaze.com/shows/{meta['tvmaze_id']}]TVmaze[/url]")
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
        image_list = meta.get(f"{self.tracker}_images_key") or meta.get("image_list") or []
        if image_list and self.config["TRACKERS"].get(self.tracker, {}).get("include_screenshots", True):
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

    def _rename_torrent_root(self, meta: Meta, name: str) -> None:
        """Set the [V3X].torrent internal root name to the generated release name.

        Only metadata outside the piece hashes changes, so no rehash happens —
        but the infohash does change, letting the client seed this torrent
        separately through the tracker link directory (which the qBittorrent
        injection names after the torrent root).
        """
        if not name:
            return
        # Seeding a renamed torrent relies on the client's link directory
        # taking the torrent's root name (supported for qBittorrent and
        # rTorrent). Without such a client, keep the original root so the
        # upload stays seedable — the fiche will show the on-disk name.
        clients_cfg = self.config.get("TORRENT_CLIENTS", {})
        has_link_client = any(
            isinstance(c, dict) and str(c.get("torrent_client", "")).lower() in ("qbit", "rtorrent") and str(c.get("linking", "") or "").strip() for c in clients_cfg.values()
        )
        if not has_link_client:
            console.print(
                f"[yellow]{self.tracker}: no qBittorrent/rTorrent client with linking configured — keeping the original torrent name so seeding still works.[/yellow]"
            )
            return
        torrent_path = os.path.join(meta["base_dir"], "tmp", meta["uuid"], f"[{self.tracker}].torrent")
        try:
            torrent = Torrent.read(torrent_path)
            if torrent.mode == "singlefile":
                # Wrap the file in a folder named after the release instead of
                # renaming the file itself: the fiche shows the folder name
                # while the inner file keeps its original (cross-seedable)
                # name. Pieces cover the same byte stream either way — no
                # rehash needed.
                info = torrent.metainfo["info"]
                original_file = str(info["name"])
                if original_file == name:
                    return
                info["files"] = [{"length": info.pop("length"), "path": [original_file]}]
                info.pop("md5sum", None)
                info["name"] = name
            else:
                if torrent.name == name:
                    return
                torrent.name = name
            torrent.write(torrent_path, overwrite=True)
        except Exception as e:
            console.print(f"[yellow]{self.tracker}: could not rename torrent root ({e}); the fiche will show the original name.[/yellow]")

    async def _read_tmp_file(self, meta: Meta, filename: str) -> Optional[bytes]:
        path = f"{meta['base_dir']}/tmp/{meta['uuid']}/{filename}"
        try:
            async with aiofiles.open(path, "rb") as f:
                return await f.read()
        except OSError:
            return None

    async def upload(self, meta: Meta, _disctype: str) -> bool:
        try:
            return await self._upload(meta, _disctype)
        except Exception as e:
            meta["tracker_status"][self.tracker]["status_message"] = f"data error: upload failed: {e}"
            console.print(f"[red]{self.tracker} upload error: {e}[/red]")
            return False

    async def _upload(self, meta: Meta, _disctype: str) -> bool:
        # Embed the release NFO in the .torrent when one exists (cheap
        # patch/clone paths before a full rehash), like the other French trackers.
        nfo_files = self._get_nfo_files(meta)
        if nfo_files:
            await self._recreated_torrent_if_nfo(meta, self.common, self.config, self.tracker, self.source_flag)
        else:
            await self.common.create_torrent_for_upload(meta, self.tracker, self.source_flag)

        name_result = await self.get_name(meta)
        name = name_result.get("name", "") if isinstance(name_result, dict) else str(name_result)

        # The site displays the .torrent's internal name, not the name field:
        # rewrite the root so the fiche carries the generated release name.
        await asyncio.to_thread(self._rename_torrent_root, meta, name)

        torrent_bytes = await self._read_tmp_file(meta, f"[{self.tracker}].torrent")
        if not torrent_bytes:
            meta["tracker_status"][self.tracker]["status_message"] = "data error: torrent file missing"
            return False

        description = await self._build_description(meta)
        # The site rules keep the ORIGINAL release NFO (shipped untouched);
        # otherwise fall back to MediaInfo / a generated scene NFO, with the
        # "Complete name" line patched to the tracker release name.
        nfo_text = ""
        is_scene_nfo = bool(nfo_files)
        nfo_path = nfo_files[0] if nfo_files else await self._get_or_generate_mediainfo_as_nfo(meta)
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
        fr_title = str(meta.get("frtitle") or "") or await self._get_french_title(meta)
        if fr_title:
            data["title"] = fr_title
        if meta.get("poster"):
            data["posterUrl"] = str(meta["poster"])
        if meta.get("backdrop"):
            data["backdropUrl"] = str(meta["backdrop"])
        # MediaInfo-based tag first (knows VOF/VOQ/VFB/AD/MUET); fall back
        # to name tokens when MediaInfo is unavailable (e.g. discs).
        language = (await self._build_audio_string(meta)).replace(".", ",") or self._get_language_tag(name)
        if language:
            data["language"] = language

        files = {"file": (f"{name}.torrent", torrent_bytes, "application/x-bittorrent")}
        headers = {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}

        if meta.get("debug"):
            desc_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}]DESCRIPTION.txt"
            async with aiofiles.open(desc_path, "w", encoding="utf-8") as f:
                await f.write(description)
            console.print(f"[cyan]{self.tracker} Debug — request data (description saved to {desc_path}):[/cyan]")
            console.print(f"  Name:        {name}")
            console.print(f"  Category:    {data['categoryId']}")
            console.print(f"  Language:    {data.get('language', '—')}")
            console.print(f"  Anonymous:   {data['anonymous']}")
            console.print(f"  NFO:         {'yes' if 'nfo' in data else 'no'}")
            meta["tracker_status"][self.tracker]["status_message"] = "Debug mode, not uploaded."
            return True

        def _error_detail(resp: Any) -> Any:
            try:
                return resp.json()
            except ValueError:
                return str(getattr(resp, "text", ""))[:500]

        response: Any = None
        timeout = 60.0
        max_retries = 3
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                    response = await client.post(self.upload_url, files=files, data=data, headers=headers)
            except (httpx.RequestError, httpx.TimeoutException) as e:
                if attempt < max_retries - 1:
                    timeout *= 1.5
                    console.print(f"[yellow]{self.tracker}: upload attempt failed ({type(e).__name__}), retrying in {RETRY_DELAY:.0f}s…[/yellow]")
                    await asyncio.sleep(RETRY_DELAY)
                    continue
                meta["tracker_status"][self.tracker]["status_message"] = f"data error: upload failed: {type(e).__name__}"
                return False
            if response.status_code in (200, 201):
                break
            if response.status_code in (400, 401, 403, 404, 422):
                # Client error — a retry cannot succeed, fail fast with the server's own message
                detail = _error_detail(response)
                meta["tracker_status"][self.tracker]["status_message"] = {"error": f"HTTP {response.status_code}", "detail": detail}
                console.print(f"[red]{self.tracker} upload failed: HTTP {response.status_code}[/red]")
                if detail:
                    console.print(f"[dim]{detail}[/dim]")
                return False
            if attempt < max_retries - 1:
                console.print(f"[yellow]{self.tracker}: HTTP {response.status_code}, retrying in {RETRY_DELAY:.0f}s… (attempt {attempt + 1}/{max_retries})[/yellow]")
                await asyncio.sleep(RETRY_DELAY)
                continue
            detail = _error_detail(response)
            meta["tracker_status"][self.tracker]["status_message"] = {"error": f"HTTP {response.status_code}", "detail": detail}
            console.print(f"[red]{self.tracker} upload failed after {max_retries} attempts: HTTP {response.status_code}[/red]")
            return False

        try:
            response_data = response.json()
        except ValueError:
            response_data = {"error": f"HTTP {response.status_code}"}

        if isinstance(response_data, dict) and not response_data.get("error"):
            torrent_id = response_data.get("id") or (response_data.get("torrent") or {}).get("id")
            if torrent_id:
                meta["tracker_status"][self.tracker]["torrent_id"] = str(torrent_id)
            meta["tracker_status"][self.tracker]["status_message"] = response_data
            return True

        meta["tracker_status"][self.tracker]["status_message"] = f"data error: {response_data}"
        return False
