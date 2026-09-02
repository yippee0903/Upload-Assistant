# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
#
# DRAU (draupnirr.xyz) — French private tracker with a custom (non-UNIT3D) API.
#
# One credential for everything: the account passkey is the API key (header
# X-Api-Key) and the announce URL is /announce/<passkey>.
#
# API surface:
#   GET  /api/categories                    upload slugs (family or sub-category)
#   GET  /api/torrents?q=&limit=&offset=    JSON catalogue, newest first, 100 max
#                                           per page, no total (a short page ends
#                                           the pagination); q matches ordered
#                                           words against the stored name
#   GET  /api/torrents/{sqid|infohash}      detail: file_count only, no file list
#   POST /api/upload                        multipart upload:
#     required: torrent (private, info.source = "DRAUPNIRR"), category slug
#     accepted: nfo, description (bbcode), mediainfo (text), meta[work_title],
#               meta[year], meta[tmdb_id] + meta[tmdb_type], meta[poster_url],
#               meta[synopsis], meta[episode], meta[facets][source|group|edition]
#     201 {id: <opaque sqid>, infohash, status: approved|pending, awaiting_validation}
#     401 invalid api key · 403 uploads disabled · 422 {error: <reason>} for a
#     duplicate, a non-private torrent, a missing source tag or a bot refusal —
#     none of which a retry can fix.
#   Video uploads enter a quarantine while the site bot reads the file headers
#   FROM THE UPLOADER (awaiting_validation: true): the release must stay seeded.

import asyncio
import re
from typing import Any, Optional

import aiofiles
import httpx
from torf import Torrent
from unidecode import unidecode

from src.console import console
from src.get_desc import DescriptionBuilder
from src.nfo_generator import decode_nfo, is_multi_episode_nfo
from src.tmdb import TmdbManager
from src.trackers.COMMON import COMMON
from src.trackers.FRENCH import _FRENCH_AUDIO_THRESHOLD as FRENCH_AUDIO_THRESHOLD
from src.trackers.FRENCH import FrenchTrackerMixin

Meta = dict[str, Any]

RETRY_DELAY = 5.0  # seconds between upload retries
PAGE_SIZE = 100  # catalogue page size (site maximum)
MAX_OFFSET = 5000  # hard cap so a misbehaving catalogue can't loop forever

# Release type → site "source" facet vocabulary (Nomenclature › Films).
SOURCE_FACETS: dict[str, str] = {
    "WEBDL": "WEB.DL",
    "WEBRIP": "WEBRip",
    "HDTV": "HDTV",
    "DVDRIP": "DVDRip",
    "REMUX": "Bluray",
    "ENCODE": "Bluray",
    "DISC": "Bluray",
}


class DRAU(FrenchTrackerMixin):
    WEB_LABEL: str = "WEB"
    notag_label: str = "NOTAG"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.common = COMMON(config)
        self.tracker = "DRAU"
        self.source_flag = "DRAUPNIRR"
        self.base_url = "https://draupnirr.xyz"
        self.upload_url = f"{self.base_url}/api/upload"
        self.search_url = f"{self.base_url}/api/torrents"
        self.torrent_url = f"{self.base_url}/torrents/"
        self.api_key = str(self.config["TRACKERS"].get(self.tracker, {}).get("api_key", "") or "").strip()
        self.announce_url = f"{self.base_url}/announce/{self.api_key}"
        # Every torrent-creation path (COMMON and the NFO re-creation in the
        # French mixin) reads the announce from the tracker config block, so
        # publish the passkey-derived URL there instead of asking for it.
        self.config["TRACKERS"].setdefault(self.tracker, {})["announce_url"] = self.announce_url
        self.tmdb_manager = TmdbManager(config)
        self.banned_groups: list[Any] = []

    # ── Category ──

    async def get_category_id(self, meta: Meta) -> str:
        """Sub-category slug: the site files animation and documentaries
        under their own sub-categories, everything else is a plain film or
        TV series."""
        genres = str(meta.get("genres", "")).lower()
        keywords = str(meta.get("keywords", "")).lower()
        is_docu = "documentary" in genres or "documentary" in keywords
        is_animation = bool(meta.get("anime") or meta.get("mal_id")) or "animation" in genres
        if meta.get("category") == "TV":
            return "series-serie-animee" if is_animation else "series-serie-tv"
        if is_animation and not is_docu:
            return "films-animation"
        if is_docu:
            return "films-documentaire"
        return "films-film"

    # ── Dupes ──

    async def search_existing(self, meta: Meta, _disctype: Any = None) -> list[dict[str, Any]]:
        dupes: list[dict[str, Any]] = []
        if not await self.get_additional_checks(meta):
            meta["skipping"] = self.tracker
            return dupes

        title = str(meta.get("title") or "")
        fr_title = str(meta.get("frtitle") or "") or await self._get_french_title(meta)
        year_str = str(meta.get("year") or "").strip()
        resolution = str(meta.get("resolution") or "")
        group = self._get_release_group(meta)
        debug = bool(meta.get("debug"))

        def _normalize(s: str) -> str:
            return re.sub(r"[^a-z0-9]", "", unidecode(s).lower())

        # The q filter matches ordered words against the stored name; never
        # append the year (TV names carry none).
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

        # A VOSTFR/VO upload must be blocked by an equivalent French-audio
        # release from ANY group, so the group filter must keep those.
        upload_audio = await self._build_audio_string(meta)
        upload_level = max((self._extract_french_lang_tag(part)[1] for part in upload_audio.split(".")), default=0)
        upload_lacks_french_audio = upload_level < FRENCH_AUDIO_THRESHOLD

        seen_names: set[str] = set()
        for search_term in queries:
            items = await self._search_catalogue(search_term)
            if items is None:
                # A failed page leaves a partial result set — a dupe could sit
                # on a page we never read. Fail closed rather than upload over
                # a possible dupe.
                console.print(f"[yellow]{self.tracker}: incomplete dupe search for '{search_term}', skipping tracker to avoid a false negative.[/yellow]")
                meta["skipping"] = self.tracker
                return []

            for torrent in items:
                name = str(torrent.get("name") or "")
                if not name:
                    continue
                name_norm = _normalize(name)
                if name_norm in seen_names:
                    continue
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
                seen_names.add(name_norm)
                size = torrent.get("size_bytes", 0)
                file_count = torrent.get("file_count")
                entry: dict[str, Any] = {
                    "name": name,
                    "size": int(size) if isinstance(size, (int, float)) or str(size).isdigit() else 0,
                    "link": f"{self.torrent_url}{torrent.get('id', '')}",
                    "id": torrent.get("id"),
                }
                if isinstance(file_count, int):
                    entry["file_count"] = file_count
                dupes.append(entry)

        if debug:
            console.print(f"[cyan]{self.tracker} dupe search found {len(dupes)} result(s)[/cyan]")
        return await self._check_french_lang_dupes(dupes, meta)

    async def _search_catalogue(self, query: str) -> Optional[list[dict[str, Any]]]:
        """All catalogue entries matching ``query``, or None when a page
        could not be read (HTTP error, bad JSON, or still full at the cap)."""
        items: list[dict[str, Any]] = []
        offset = 0
        while True:
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(self.search_url, params={"q": query, "limit": PAGE_SIZE, "offset": offset}, headers=self._headers())
                if response.status_code != 200:
                    return None
                page = response.json()
            except (httpx.RequestError, httpx.TimeoutException, ValueError):
                return None
            if not isinstance(page, list):
                return None
            items.extend(t for t in page if isinstance(t, dict))
            if len(page) < PAGE_SIZE:
                return items
            offset += PAGE_SIZE
            if offset >= MAX_OFFSET:
                return None

    def _headers(self) -> dict[str, str]:
        return {"X-Api-Key": self.api_key, "Accept": "application/json"}

    # ── Description ──

    async def edit_desc(self, meta: Meta) -> None:
        # Manual-mode hook required by trackerhandle; the description is
        # built at upload time instead.
        return None

    async def _build_description(self, meta: Meta) -> str:
        """Centered BBCode fiche: French title and poster, TMDB facts,
        synopsis, technical block, audio/subtitle language lines, release
        block and optional screenshots. MediaInfo goes to its own upload
        field, not here."""
        C = "#3d85c6"  # accent colour

        def header(label: str) -> str:
            return f"[b][color={C}]━━━ {label} ━━━[/color][/b]"

        def field(label: str, value: Any) -> str:
            return f"[b][color={C}]{label} :[/color][/b] {value}"

        mi_text = await self._get_mediainfo_text(meta)
        fr_data: dict[str, Any] = {}
        try:
            fr_data = await self.tmdb_manager.get_tmdb_localized_data(meta, data_type="main", language="fr", append_to_response="credits") or {}
        except Exception:
            fr_data = {}

        parts: list[str] = ["[center]"]

        title = (await self._get_french_title(meta)).strip() or str(meta.get("title") or "").strip()
        year = str(meta.get("year") or "").strip()
        if title:
            parts.append(f"[b][color={C}]{f'{title} ({year})' if year else title}[/color][/b]")
            parts.append("")

        # French-localized poster when TMDB has one (also reused as poster_url)
        fr_poster_path = str(fr_data.get("poster_path") or "")
        if fr_poster_path:
            poster = f"https://image.tmdb.org/t/p/w500{fr_poster_path}"
            meta["fr_poster"] = f"https://image.tmdb.org/t/p/original{fr_poster_path}"
        else:
            poster = re.sub(r"/t/p/[^/]+/", "/t/p/w500/", str(meta.get("poster") or ""))
        if poster:
            parts.append(f"[img]{poster}[/img]")
            parts.append("")

        # ── Informations ──
        info: list[str] = []
        original_title = str(meta.get("original_title") or meta.get("title") or "").strip()
        if original_title and original_title != title:
            info.append(field("Titre original", f"[i]{original_title}[/i]"))
        countries = fr_data.get("production_countries", meta.get("production_countries", []))
        names = [c["name"] for c in countries if isinstance(c, dict) and c.get("name")] if isinstance(countries, list) else []
        if names:
            info.append(field("Pays", f"[i]{', '.join(names)}[/i]"))
        genres_list = fr_data.get("genres", [])
        genre_names = [g["name"] for g in genres_list if isinstance(g, dict) and g.get("name")] if isinstance(genres_list, list) else []
        if genre_names:
            info.append(field("Genres", f"[i]{', '.join(genre_names)}[/i]"))
        elif meta.get("genres"):
            info.append(field("Genres", f"[i]{meta['genres']}[/i]"))
        release_date = str(fr_data.get("release_date") or fr_data.get("first_air_date") or meta.get("release_date") or meta.get("first_air_date") or "").strip()
        if release_date:
            info.append(field("Date de sortie", f"[i]{self._format_french_date(release_date)}[/i]"))
        elif year:
            info.append(field("Date de sortie", f"[i]{year}[/i]"))
        runtime = fr_data.get("runtime") or meta.get("runtime", 0)
        if runtime:
            h, m = divmod(int(runtime), 60)
            info.append(field("Durée", f"[i]{f'{h}h{m:02d}' if h else f'{m}min'}[/i]"))
        credits = fr_data.get("credits", {})
        crew = credits.get("crew", []) if isinstance(credits, dict) else []
        cast = credits.get("cast", []) if isinstance(credits, dict) else []
        directors = [p["name"] for p in crew if isinstance(p, dict) and p.get("job") == "Director" and p.get("name")]
        if not directors and isinstance(meta.get("tmdb_directors"), list):
            directors = [str(d.get("name", "") if isinstance(d, dict) else d) for d in meta["tmdb_directors"]]
            directors = [d for d in directors if d]
        if directors:
            info.append(field("Réalisateur" if len(directors) == 1 else "Réalisateurs", f"[i]{', '.join(directors)}[/i]"))
        writers = list(dict.fromkeys(p["name"] for p in crew if isinstance(p, dict) and p.get("job") in ("Screenplay", "Writer", "Story") and p.get("name")))
        if writers:
            info.append(field("Scénariste" if len(writers) == 1 else "Scénaristes", f"[i]{', '.join(writers)}[/i]"))
        actors = [p["name"] for p in cast[:5] if isinstance(p, dict) and p.get("name")]
        if actors:
            info.append(field("Acteurs", f"[i]{', '.join(actors)}[/i]"))
        vote_avg = fr_data.get("vote_average") or meta.get("vote_average")
        vote_count = fr_data.get("vote_count") or meta.get("vote_count")
        if vote_avg and vote_count:
            info.append(field("Note des spectateurs", f"[i]{vote_avg} ({vote_count} votes)[/i]"))

        links: list[str] = []
        imdb_digits = re.sub(r"^tt", "", str(meta.get("imdb_id") or ""), flags=re.IGNORECASE)
        if imdb_digits.isdigit() and int(imdb_digits) > 0:
            links.append(f"[url=https://www.imdb.com/title/tt{imdb_digits.zfill(7)}/]IMDb[/url]")
        tmdb_digits = str(meta.get("tmdb_id") or "")
        if tmdb_digits.isdigit() and int(tmdb_digits) > 0:
            links.append(f"[url=https://www.themoviedb.org/{self._tmdb_type(meta)}/{tmdb_digits}]TMDB[/url]")
        if meta.get("tvdb_id"):
            links.append(f"[url=https://www.thetvdb.com/?id={meta['tvdb_id']}&tab=series]TVDB[/url]")
        if meta.get("mal_id"):
            links.append(f"[url=https://myanimelist.net/anime/{meta['mal_id']}]MAL[/url]")
        if info or links:
            parts.append(header("Informations"))
            parts.extend(info)
            if links:
                parts.append(" | ".join(links))
            parts.append("")

        # ── Synopsis ──
        parts.append(header("Synopsis"))
        synopsis = await self.french_synopsis(meta, fr_data)
        meta["fr_synopsis"] = synopsis  # reused as the upload's meta[synopsis]
        parts.append(synopsis or "Aucun synopsis disponible.")
        parts.append("")

        # ── Informations techniques ──
        parts.append(header("Informations techniques"))
        type_label = self._get_type_label(meta)
        if type_label:
            parts.append(field("Type", type_label))
        source = str(meta.get("source") or meta.get("type") or "")
        if source:
            parts.append(field("Source", source))
        if meta.get("service"):
            parts.append(field("Service", meta["service"]))
        if meta.get("resolution"):
            parts.append(field("Résolution", meta["resolution"]))
        container = self._format_container(mi_text)
        if container:
            parts.append(field("Format vidéo", container))
        codec = str(meta.get("video_encode") or meta.get("video_codec") or "").strip().replace("H.264", "H264").replace("H.265", "H265")
        raw_codec = str(meta.get("video_codec") or "").strip()
        if codec and raw_codec and raw_codec != codec:
            codec = f"{codec} ({raw_codec})"
        if codec:
            parts.append(field("Codec vidéo", codec))
        hdr_badge = self._format_hdr_dv_bbcode(meta)
        if hdr_badge:
            parts.append(field("HDR", hdr_badge))
        vbr_match = re.search(r"(?:^|\n)Bit rate\s*:\s*(.+?)\s*(?:\n|$)", mi_text) if mi_text else None
        if vbr_match:
            parts.append(field("Débit vidéo", vbr_match.group(1).strip()))
        parts.append("")

        # ── Audio / Sous-titres ──
        parts.append(header("Audio(s)"))
        audio_lines = self._format_audio_bbcode(mi_text, meta)
        parts.extend(f" [i]{line}[/i]" for line in audio_lines or ["Non spécifié"])
        parts.append("")
        parts.append(header("Sous-titre(s)"))
        sub_lines = self._format_subtitle_bbcode(mi_text, meta)
        parts.extend(f" [i]{line}[/i]" for line in sub_lines or ["Aucun"])
        parts.append("")

        # ── Release ──
        parts.append(header("Release"))
        parts.append(field("Titre", meta.get("uuid", "")))
        note = await DescriptionBuilder(self.tracker, self.config).get_personal_note(meta)
        if note:
            parts.append(field("Note", note))
        size_str = self._get_total_size(meta, mi_text)
        if size_str:
            parts.append(field("Taille totale", size_str))
        file_count = self._count_files(meta)
        if file_count:
            parts.append(field("Nombre de fichiers", file_count))
        group = self._get_release_group(meta)
        if group:
            parts.append(field("Groupe", group))
        parts.append("")

        # ── Notes de la release d'origine (opt-in: include_source_description) ──
        source_desc = self._flatten_source_bbcode(await self._get_source_description(meta))
        if source_desc:
            parts.append(header("Notes de la release d'origine"))
            parts.append(source_desc)
            parts.append("")

        # ── Screenshots (opt-in: include_screenshots): thumbnails linked to
        # the full-size image, two per row.
        image_list = meta.get(f"{self.tracker}_images_key") or meta.get("image_list") or []
        if image_list and self.config["TRACKERS"].get(self.tracker, {}).get("include_screenshots", False):
            thumbs = [
                f"[url={img.get('web_url') or img.get('raw_url', '')}][img]{img.get('img_url') or img.get('raw_url', '')}[/img][/url]"
                for img in image_list
                if img.get("img_url") or img.get("raw_url")
            ]
            if thumbs:
                parts.append(header("Captures d'écran"))
                parts.extend(" ".join(thumbs[i : i + 2]) for i in range(0, len(thumbs), 2))

        # The site parser renders neither [size] nor [right]: plain tags only.
        ua_sig = meta.get("ua_signature", "Created by Upload Assistant")
        parts.append(f"[i][url=https://github.com/yippee0903/Upload-Assistant]{ua_sig}[/url][/i]")
        parts.append("[/center]")
        return "\n".join(parts).strip()

    @staticmethod
    def _flatten_source_bbcode(text: str) -> str:
        """Strip the UNIT3D-only tags a reused description may carry
        ([center] inside the centered fiche, [font], absolute [size] scales,
        [h1]-[h6], tracker-hosted [comparison] blocks)."""
        text = re.sub(r"\[/?(?:center|quote[^\]]*|font[^\]]*|size[^\]]*|h[1-6])\]", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\[comparison=[^\]]*\][\s\S]*?\[/comparison\]\s*", "", text, flags=re.IGNORECASE)
        return re.sub(r"\n{3,}", "\n\n", text).strip()

    @staticmethod
    def _tmdb_type(meta: Meta) -> str:
        return "tv" if str(meta.get("category", "")).upper() == "TV" else "movie"

    # ── Upload ──

    async def upload(self, meta: Meta, _disctype: str) -> bool:
        try:
            return await self._upload(meta, _disctype)
        except Exception as e:
            meta["tracker_status"][self.tracker]["status_message"] = f"data error: upload failed: {e}"
            console.print(f"[red]{self.tracker} upload error: {e}[/red]")
            return False

    async def _upload(self, meta: Meta, _disctype: str) -> bool:
        # Embed the release NFO in the .torrent when one exists, like the
        # other French trackers.
        nfo_files = self._get_nfo_files(meta)
        if nfo_files:
            await self._recreated_torrent_if_nfo(meta, self.common, self.config, self.tracker, self.source_flag)
        else:
            await self.common.create_torrent_for_upload(meta, self.tracker, self.source_flag)

        name_result = await self.get_name(meta)
        name = name_result.get("name", "") if isinstance(name_result, dict) else str(name_result)

        torrent_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}].torrent"
        try:
            async with aiofiles.open(torrent_path, "rb") as f:
                torrent_bytes = await f.read()
        except OSError:
            torrent_bytes = b""
        if not torrent_bytes:
            meta["tracker_status"][self.tracker]["status_message"] = "data error: torrent file missing"
            return False

        description = await self._build_description(meta)
        desc_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}]DESCRIPTION.txt"
        async with aiofiles.open(desc_path, "w", encoding="utf-8") as f:
            await f.write(description)

        # The original release NFO when there is one (a multi-episode
        # MediaInfo concatenation stays in the torrent but is too long for
        # the field); otherwise MediaInfo / a generated scene NFO with the
        # "Complete name" line patched to the tracker release name.
        usable_nfo = bool(nfo_files) and not await is_multi_episode_nfo(nfo_files[0])
        nfo_path = nfo_files[0] if usable_nfo else await self._get_or_generate_mediainfo_as_nfo(meta)
        nfo_text = ""
        if nfo_path:
            try:
                async with aiofiles.open(nfo_path, "rb") as f:
                    nfo_text = decode_nfo(await f.read())
            except OSError:
                nfo_text = ""
        if nfo_text and not usable_nfo:
            nfo_text = self._patch_mi_filename(nfo_text, name)

        data = await self._build_upload_fields(meta, name, description)
        files: dict[str, Any] = {"torrent": (f"{name}.torrent", torrent_bytes, "application/x-bittorrent")}
        if nfo_text:
            files["nfo"] = (f"{name}.nfo", nfo_text.encode("utf-8"), "text/plain")

        if meta.get("debug"):
            console.print(f"[cyan]{self.tracker} Debug — request data (description saved to {desc_path}):[/cyan]")
            console.print(f"  Name:        {name}")
            console.print(f"  Category:    {data['category']}")
            console.print(f"  Work title:  {data.get('meta[work_title]', '—')}")
            console.print(f"  Source:      {data.get('meta[facets][source]', '—')}")
            console.print(f"  Episode:     {data.get('meta[episode]', '—')}")
            console.print(f"  NFO:         {'yes' if 'nfo' in files else 'no'}")
            console.print(f"  MediaInfo:   {'yes' if 'mediainfo' in data else 'no'}")
            meta["tracker_status"][self.tracker]["status_message"] = "Debug mode, not uploaded."
            return True

        infohash = await asyncio.to_thread(lambda: str(Torrent.read(torrent_path).infohash))
        payload = await self._post_upload(meta, data, files, infohash)
        if payload is None:
            return False
        if payload.get("error"):
            meta["tracker_status"][self.tracker]["status_message"] = f"data error: {payload}"
            return False

        torrent_id = str(payload.get("id") or "")
        if torrent_id:
            meta["tracker_status"][self.tracker]["torrent_id"] = torrent_id
        if payload.get("reconciled"):
            console.print(f"[yellow]{self.tracker}: this exact torrent is already on the site (id {torrent_id}) — treating the upload as done.[/yellow]")
        if payload.get("status") == "pending":
            console.print(f"[yellow]{self.tracker}: upload sent to human moderation (status pending).[/yellow]")
        if payload.get("awaiting_validation"):
            console.print(f"[yellow]{self.tracker}: release in quarantine until the media check reads its headers from you — keep it seeding.[/yellow]")
        meta["tracker_status"][self.tracker]["status_message"] = payload
        return True

    async def _build_upload_fields(self, meta: Meta, name: str, description: str) -> dict[str, str]:
        data: dict[str, str] = {
            "category": await self.get_category_id(meta),
            "description": description,
            "description_format": "bbcode",
        }
        mi_text = await self._get_mediainfo_text(meta)
        if mi_text:
            data["mediainfo"] = mi_text
        # The fiche's canonical name needs the work title: French title
        # first (site catalogue language), original title as fallback.
        work_title = (await self._get_french_title(meta)).strip() or str(meta.get("title") or "").strip()
        if work_title:
            data["meta[work_title]"] = work_title
        year = str(meta.get("year") or "").strip()
        if year.isdigit():
            data["meta[year]"] = year
        tmdb_id = str(meta.get("tmdb_id") or "")
        if tmdb_id.isdigit() and int(tmdb_id) > 0:
            data["meta[tmdb_id]"] = tmdb_id
            data["meta[tmdb_type]"] = self._tmdb_type(meta)
        poster = str(meta.get("fr_poster") or meta.get("poster") or "")
        if poster:
            data["meta[poster_url]"] = poster
        synopsis = str(meta.get("fr_synopsis") or "").strip()
        if synopsis:
            data["meta[synopsis]"] = synopsis[:4000]
        source = SOURCE_FACETS.get(str(meta.get("type") or "").upper(), "")
        if source:
            data["meta[facets][source]"] = source
        group = self._get_release_group(meta)
        if group:
            data["meta[facets][group]"] = group
        edition = str(meta.get("edition") or "").strip()
        if edition:
            data["meta[facets][edition]"] = edition
        if meta.get("category") == "TV":
            episode = f"{meta.get('season', '')}{meta.get('episode', '')}".strip()
            if episode:
                data["meta[episode]"] = episode
        return data

    async def _find_by_infohash(self, infohash: str) -> Optional[dict[str, Any]]:
        """The catalogue entry for ``infohash`` (our own quarantined uploads
        included), or None when unknown or unreadable."""
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.get(f"{self.search_url}/{infohash}", headers=self._headers())
            detail = response.json() if response.status_code == 200 else None
        except (httpx.RequestError, httpx.TimeoutException, ValueError):
            return None
        return detail if isinstance(detail, dict) and detail.get("id") else None

    async def _post_upload(self, meta: Meta, data: dict[str, str], files: dict[str, Any], infohash: str) -> Optional[dict[str, Any]]:
        """POST the multipart upload; the response payload, or None when it
        failed (status recorded).

        The API has no idempotency key, so a request whose outcome is unknown
        (timeout, dropped connection, 5xx after the site stored it) is
        reconciled by looking the torrent up by infohash before any retry
        and on a 422: when the site already has it, the upload is done.
        """
        status = meta["tracker_status"][self.tracker]
        timeout = 60.0
        max_retries = 3

        async def _already_there() -> Optional[dict[str, Any]]:
            existing = await self._find_by_infohash(infohash)
            return {**existing, "reconciled": True} if existing else None

        for attempt in range(max_retries):
            try:
                # No redirect following: a cross-origin redirect would carry
                # the X-Api-Key header along.
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(self.upload_url, files=files, data=data, headers=self._headers())
            except (httpx.RequestError, httpx.TimeoutException) as e:
                if existing := await _already_there():
                    return existing
                if attempt < max_retries - 1:
                    timeout *= 1.5
                    console.print(f"[yellow]{self.tracker}: upload attempt failed ({type(e).__name__}), retrying in {RETRY_DELAY:.0f}s…[/yellow]")
                    await asyncio.sleep(RETRY_DELAY)
                    continue
                status["status_message"] = f"data error: upload failed: {type(e).__name__}"
                return None
            try:
                detail: Any = response.json()
            except ValueError:
                detail = response.text[:500]
            if response.status_code in (200, 201):
                return detail if isinstance(detail, dict) else {"error": f"unexpected response: {detail}"}
            if response.status_code in (400, 401, 403, 404, 422):
                # Client error — a retry cannot succeed: fail fast with the
                # site's own reason, unless the 422 is a duplicate of the
                # torrent we just sent (an earlier attempt went through).
                if response.status_code == 422 and (existing := await _already_there()):
                    return existing
                reason = detail.get("error", "") if isinstance(detail, dict) else str(detail)
                status["status_message"] = f"data error: HTTP {response.status_code}: {reason or detail}"
                console.print(f"[red]{self.tracker} upload failed: HTTP {response.status_code}[/red]")
                if reason:
                    console.print(f"[dim]{reason}[/dim]")
                return None
            if existing := await _already_there():
                return existing
            if attempt < max_retries - 1:
                console.print(f"[yellow]{self.tracker}: HTTP {response.status_code}, retrying in {RETRY_DELAY:.0f}s… (attempt {attempt + 1}/{max_retries})[/yellow]")
                await asyncio.sleep(RETRY_DELAY)
                continue
            status["status_message"] = {"error": f"HTTP {response.status_code}", "detail": detail}
            console.print(f"[red]{self.tracker} upload failed after {max_retries} attempts: HTTP {response.status_code}[/red]")
        return None
