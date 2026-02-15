# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
"""
la-cale.space — French private tracker (custom REST API)

Upload endpoint:  POST https://la-cale.space/api/external/upload
Authentication:   X-Api-Key header
Content-Type:     multipart/form-data

Required fields:  title, categoryId, file, nfoFile
Optional fields:  description, tmdbId, tmdbType, coverUrl, tags[]

API docs:  https://la-cale.space/api/external/docs
Source flag: lacale (MUST appear in the torrent's info.source)
"""

import asyncio
import glob
import json
import os
import re
from datetime import datetime
from typing import Any

import aiofiles
import httpx
from unidecode import unidecode

from src.console import console
from src.nfo_generator import SceneNfoGenerator
from src.tmdb import TmdbManager
from src.trackers.COMMON import COMMON
from src.trackers.FRENCH import FrenchTrackerMixin

Meta = dict[str, Any]
Config = dict[str, Any]

# Language → flag emoji mapping
LANG_FLAGS: dict[str, str] = {
    'english': '🇺🇸', 'french': '🇫🇷', 'german': '🇩🇪', 'spanish': '🇪🇸',
    'italian': '🇮🇹', 'portuguese': '🇵🇹', 'russian': '🇷🇺', 'japanese': '🇯🇵',
    'korean': '🇰🇷', 'chinese': '🇨🇳', 'arabic': '🇸🇦', 'dutch': '🇳🇱',
    'polish': '🇵🇱', 'turkish': '🇹🇷', 'thai': '🇹🇭', 'swedish': '🇸🇪',
    'norwegian': '🇳🇴', 'danish': '🇩🇰', 'finnish': '🇫🇮', 'czech': '🇨🇿',
    'hungarian': '🇭🇺', 'romanian': '🇷🇴', 'greek': '🇬🇷', 'hebrew': '🇮🇱',
    'indonesian': '🇮🇩', 'bulgarian': '🇧🇬', 'croatian': '🇭🇷', 'serbian': '🇷🇸',
    'slovenian': '🇸🇮', 'estonian': '🇪🇪', 'icelandic': '🇮🇸', 'lithuanian': '🇱🇹',
    'latvian': '🇱🇻', 'ukrainian': '🇺🇦', 'hindi': '🇮🇳', 'tamil': '🇮🇳',
    'telugu': '🇮🇳', 'malay': '🇲🇾', 'vietnamese': '🇻🇳', 'persian': '🇮🇷',
}

FRENCH_MONTHS: list[str] = [
    '', 'janvier', 'février', 'mars', 'avril', 'mai', 'juin',
    'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre',
]


class LACALE(FrenchTrackerMixin):
    """la-cale.space tracker — French private tracker with custom API."""

    BASE_URL: str = 'https://la-cale.space'

    def __init__(self, config: Config) -> None:
        self.config: Config = config
        self.tracker: str = 'LACALE'
        self.source_flag: str = 'lacale'
        self.upload_url: str = f'{self.BASE_URL}/api/external/upload'
        self.search_url: str = f'{self.BASE_URL}/api/external'
        self.meta_url: str = f'{self.BASE_URL}/api/external/meta'
        self.torrent_url: str = f'{self.BASE_URL}/torrents/'
        self.api_key: str = str(self.config['TRACKERS'].get(self.tracker, {}).get('api_key', '')).strip()
        self.tmdb_manager = TmdbManager(config)
        self.banned_groups: list[str] = [""]

        # Category/tag metadata cache (fetched once from /api/external/meta)
        self._meta_cache: dict[str, Any] | None = None

    # ──────────────────────────────────────────────────────────
    #  Audio / naming / French title — inherited from FrenchTrackerMixin
    # ──────────────────────────────────────────────────────────

    # ──────────────────────────────────────────────────────────
    #  Metadata cache  (categories + tags from API)
    # ──────────────────────────────────────────────────────────

    async def _fetch_meta(self) -> dict[str, Any]:
        """Fetch and cache /api/external/meta (categories, tagGroups, ungroupedTags)."""
        if self._meta_cache is not None:
            return self._meta_cache

        headers = {'X-Api-Key': self.api_key, 'Accept': 'application/json'}
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(self.meta_url, headers=headers)
            if resp.status_code == 200:
                self._meta_cache = resp.json()
            else:
                console.print(f"[yellow]LACALE: /meta returned HTTP {resp.status_code}[/yellow]")
                self._meta_cache = {}
        except Exception as e:
            console.print(f"[yellow]LACALE: failed to fetch /meta: {e}[/yellow]")
            self._meta_cache = {}
        return self._meta_cache if self._meta_cache is not None else {}

    # ──────────────────────────────────────────────────────────
    #  Category mapping  (requires /meta data)
    # ──────────────────────────────────────────────────────────

    async def _get_category_id(self, meta: Meta) -> str:
        """Return the categoryId string for the upload.

        Category IDs come from /api/external/meta → categories[].children[].id
        We map based on meta['category'] (MOVIE vs TV) and anime detection.

        Fallback hardcoded IDs (from the API doc example):
          cat_films → Films subcategory
          cat_series → Séries TV subcategory
        """
        api_meta = await self._fetch_meta()
        categories = api_meta.get('categories', [])

        # Determine what we're looking for
        is_anime = bool(meta.get('mal_id'))
        is_tv = str(meta.get('category', '')).upper() == 'TV'

        # Build a flat lookup: slug → id
        slug_to_id: dict[str, str] = {}
        for cat in categories:
            if cat.get('slug') and cat.get('id'):
                slug_to_id[cat['slug'].lower()] = cat['id']
            for child in (cat.get('children') or []):
                if child.get('slug') and child.get('id'):
                    slug_to_id[child['slug'].lower()] = child['id']

        # Also build a name-based lookup for resilience
        name_to_id: dict[str, str] = {}
        for cat in categories:
            if cat.get('name') and cat.get('id'):
                name_to_id[cat['name'].lower()] = cat['id']
            for child in (cat.get('children') or []):
                if child.get('name') and child.get('id'):
                    name_to_id[child['name'].lower()] = child['id']

        # Try to find the best category
        if is_tv:
            if is_anime:
                # Try anime-related TV categories
                for slug in ('anime', 'animes', 'series-anime', 'mangas-animes'):
                    if slug in slug_to_id:
                        return slug_to_id[slug]
                for name in ('anime', 'animes', 'séries animées', 'mangas-animes'):
                    if name in name_to_id:
                        return name_to_id[name]
            # Standard TV
            for slug in ('series', 'series-tv', 'séries', 'séries-tv'):
                if slug in slug_to_id:
                    return slug_to_id[slug]
            for name in ('séries tv', 'séries', 'series'):
                if name in name_to_id:
                    return name_to_id[name]
        else:
            if is_anime:
                # Anime films
                for slug in ('films-animation', 'anime-films', 'animation'):
                    if slug in slug_to_id:
                        return slug_to_id[slug]
                for name in ("films d'animation", 'animation', 'anime'):
                    if name in name_to_id:
                        return name_to_id[name]
            # Standard films
            for slug in ('films', 'films-hd', 'movies'):
                if slug in slug_to_id:
                    return slug_to_id[slug]
            for name in ('films', 'movies'):
                if name in name_to_id:
                    return name_to_id[name]

        # Ultimate fallback: use hardcoded IDs from the API doc example
        if is_tv:
            return 'cat_series'
        return 'cat_films'

    # ──────────────────────────────────────────────────────────
    #  Tag mapping  (requires /meta data)
    # ──────────────────────────────────────────────────────────

    async def _build_tag_ids(self, meta: Meta, language_tag: str) -> list[str]:
        """Build a list of tag IDs to send with the upload.

        Tags come from /api/external/meta → tagGroups[].tags[].id
        We match based on resolution, source type, codec, HDR, language, etc.
        """
        api_meta = await self._fetch_meta()
        tag_groups = api_meta.get('tagGroups', [])
        ungrouped = api_meta.get('ungroupedTags', [])

        # Build flat lookup: slug → id (and name → id)
        slug_to_id: dict[str, str] = {}
        name_to_id: dict[str, str] = {}
        for group in tag_groups:
            for tag in (group.get('tags') or []):
                if tag.get('slug'):
                    slug_to_id[tag['slug'].lower()] = tag['id']
                if tag.get('name'):
                    name_to_id[tag['name'].lower()] = tag['id']
        for tag in (ungrouped or []):
            if tag.get('slug'):
                slug_to_id[tag['slug'].lower()] = tag['id']
            if tag.get('name'):
                name_to_id[tag['name'].lower()] = tag['id']

        def _find_tag(*candidates: str) -> str | None:
            for c in candidates:
                cl = c.lower()
                if cl in slug_to_id:
                    return slug_to_id[cl]
                if cl in name_to_id:
                    return name_to_id[cl]
            return None

        tag_ids: list[str] = []

        # Resolution
        res = meta.get('resolution', '')
        t = _find_tag(res)
        if t:
            tag_ids.append(t)

        # Source type
        type_val = meta.get('type', '')
        type_map: dict[str, list[str]] = {
            'REMUX': ['remux'],
            'ENCODE': ['encode', 'encodé'],
            'WEBDL': ['web-dl', 'webdl', 'web'],
            'WEBRIP': ['webrip', 'web-rip'],
            'HDTV': ['hdtv'],
            'DISC': ['disc', 'full-disc', 'bluray-disc'],
            'DVDRIP': ['dvdrip', 'dvd-rip'],
        }
        for candidate in type_map.get(type_val, []):
            t = _find_tag(candidate)
            if t:
                tag_ids.append(t)
                break

        # Source (BluRay, etc.)
        source = meta.get('source', '')
        if source:
            t = _find_tag(source.lower(), source.lower().replace(' ', '-'))
            if t and t not in tag_ids:
                tag_ids.append(t)

        # Video codec
        video_encode = meta.get('video_encode', '')
        if video_encode:
            t = _find_tag(video_encode)
            if t and t not in tag_ids:
                tag_ids.append(t)

        video_codec = meta.get('video_codec', '')
        if video_codec:
            codec_clean = video_codec.replace('.', '').lower()
            t = _find_tag(codec_clean, video_codec)
            if t and t not in tag_ids:
                tag_ids.append(t)

        # HDR / DV
        hdr = meta.get('hdr', '')
        if hdr:
            hdr_slug = hdr.replace('+', 'plus').lower()
            t = _find_tag(hdr_slug, hdr.lower())
            if t and t not in tag_ids:
                tag_ids.append(t)

        dv = meta.get('dv', '')
        if dv:
            t = _find_tag('dv', 'dolby-vision', 'dolbyvision')
            if t and t not in tag_ids:
                tag_ids.append(t)

        # Language tags
        if language_tag:
            parts = language_tag.split('.')
            for part in parts:
                t = _find_tag(part.lower())
                if t and t not in tag_ids:
                    tag_ids.append(t)

        return tag_ids

    # ──────────────────────────────────────────────────────────
    #  Description (BBCode)
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def _format_french_date(date_str: str) -> str:
        if not date_str or len(date_str) < 10:
            return date_str or ''
        try:
            dt = datetime.strptime(date_str[:10], '%Y-%m-%d')  # noqa: DTZ007
            return f'{dt.day} {FRENCH_MONTHS[dt.month]} {dt.year}'
        except (ValueError, IndexError):
            return date_str

    @staticmethod
    def _lang_to_flag(lang: str) -> str:
        return LANG_FLAGS.get(lang.strip().lower(), '🏳️')

    @staticmethod
    def _parse_mi_container(mi_text: str) -> str:
        m = re.search(r'Format\s*:\s*(.+)', mi_text)
        return m.group(1).strip() if m else ''

    @staticmethod
    def _parse_mi_audio_tracks(mi_text: str) -> list[dict[str, str]]:
        blocks = re.split(r'\nAudio(?: #\d+)?\n', mi_text)
        tracks: list[dict[str, str]] = []
        for block in blocks[1:]:
            chunk = block.split('\n\n')[0]
            info: dict[str, str] = {}
            for line in chunk.splitlines():
                if ':' in line:
                    key, _, val = line.partition(':')
                    info[key.strip()] = val.strip()
            lang = info.get('Language', info.get('Title', 'Unknown'))
            title_raw = info.get('Title', '')  # e.g. "VFF", "VFI", "MULTI"
            fmt = info.get('Commercial name', info.get('Format', ''))
            channels = info.get('Channel(s)', '')
            ch_m = re.search(r'(\d+)', channels)
            ch_label = f'{ch_m.group(1)} canaux' if ch_m else channels
            bitrate = info.get('Bit rate', info.get('Overall bit rate', ''))
            tracks.append({
                'lang': lang,
                'title_raw': title_raw,
                'format': fmt,
                'channels': ch_label,
                'bitrate': bitrate,
            })
        return tracks

    @staticmethod
    def _parse_mi_subtitle_tracks(mi_text: str) -> list[dict[str, Any]]:
        blocks = re.split(r'\nText(?: #\d+)?\n', mi_text)
        tracks: list[dict[str, Any]] = []
        for block in blocks[1:]:
            chunk = block.split('\n\n')[0]
            info: dict[str, str] = {}
            for line in chunk.splitlines():
                if ':' in line:
                    key, _, val = line.partition(':')
                    info[key.strip()] = val.strip()
            title = info.get('Title', info.get('Language', 'Unknown'))
            fmt = info.get('Format', '')
            forced = 'yes' in info.get('Forced', '').lower() or 'forc' in title.lower()
            tracks.append({'title': title, 'format': fmt, 'forced': forced})
        return tracks

    @staticmethod
    def _count_files(meta: Meta) -> str:
        path = meta.get('path', '')
        if not path:
            return '1'
        if os.path.isdir(path):
            count = sum(1 for f in os.listdir(path) if os.path.isfile(os.path.join(path, f)))
            return str(count) if count else '1'
        return '1'

    async def _get_mediainfo_text(self, meta: Meta) -> str:
        base = os.path.join(meta.get('base_dir', '/tmp'), 'tmp', meta.get('uuid', ''))
        mi_path = os.path.join(base, 'MEDIAINFO.txt')
        if await asyncio.to_thread(os.path.exists, mi_path):
            async with aiofiles.open(mi_path, encoding='utf-8', errors='replace') as f:
                return await f.read()

        # Fallback: try bdinfo summary
        for pattern in ('BDINFO_SUMMARY.txt', 'bdinfo_summary.txt', '*bdinfo*.txt'):
            for path in glob.glob(os.path.join(base, pattern)):
                async with aiofiles.open(path, encoding='utf-8', errors='replace') as f:
                    return await f.read()
        return ''

    async def _build_description(self, meta: Meta) -> str:
        """Build a BBCode description matching La Cale's site template."""
        tmdb_data = await self.tmdb_manager.get_tmdb_localized_data(
            meta, data_type='main', language='fr', append_to_response='credits,keywords'
        ) or {}
        mi_text = await self._get_mediainfo_text(meta)

        fr_title = tmdb_data.get('title', '') or meta.get('title', '')
        year = meta.get('year', '')
        overview = tmdb_data.get('overview', '') or meta.get('overview', '')
        poster = meta.get('poster', '')

        # Force w500 poster size (TMDB convention for La Cale)
        if poster and 'image.tmdb.org' in poster:
            poster = re.sub(r'/t/p/[^/]+/', '/t/p/w500/', poster)

        parts: list[str] = ['[center]']

        # ── Poster ──
        if poster:
            parts.append(f'[img]{poster}[/img]')
            parts.append('')

        # ── Title (year) ──
        title_line = fr_title
        if year:
            title_line += f' ({year})'
        parts.append(f'[size=6][color=#eab308][b]{title_line}[/b][/color][/size]')
        parts.append('')

        # ── Rating ──
        vote_avg = tmdb_data.get('vote_average')
        if vote_avg:
            try:
                score = round(float(vote_avg), 3)
                parts.append(f'[b]Note :[/b] {score}/10')
            except (ValueError, TypeError):
                pass

        # ── Genres ──
        genres = tmdb_data.get('genres', [])
        if genres:
            genre_names = [g['name'] for g in genres if g.get('name')]
            parts.append(f'[b]Genre :[/b] {", ".join(genre_names)}')

        parts.append('')

        # ── Synopsis (in [quote]) ──
        if overview:
            parts.append(f'[quote]{overview}[/quote]')
        parts.append('')

        # ── DÉTAILS separator ──
        parts.append('[color=#eab308][b]--- DÉTAILS ---[/b][/color]')
        parts.append('')

        # ── Qualité ──
        resolution = meta.get('resolution', '')
        if resolution:
            quality = resolution
            if resolution == '2160p':
                quality += ' (4K)'
            parts.append(f'[b]Qualité :[/b] {quality}')

        # ── Format (container from MI) ──
        container = self._parse_mi_container(mi_text) if mi_text else ''
        if container:
            parts.append(f'[b]Format :[/b] {container}')

        # ── Codec Vidéo ──
        video_encode = meta.get('video_encode', '')
        video_codec = meta.get('video_codec', '')
        codec = video_encode or video_codec or ''
        if codec:
            parts.append(f'[b]Codec Vidéo :[/b] {codec}')

        # ── Codec Audio ──
        audio_codec = meta.get('audio', '')
        if audio_codec:
            parts.append(f'[b]Codec Audio :[/b] {audio_codec}')

        # ── Langues (from MI audio tracks) ──
        audio_tracks = self._parse_mi_audio_tracks(mi_text) if mi_text else []
        if audio_tracks:
            lang_labels: list[str] = []
            for at in audio_tracks:
                label = at['lang']
                # Add format qualifier in parentheses if it has a title/tag
                title_raw = at.get('title_raw', '')
                if title_raw:
                    label += f' ({title_raw})'
                lang_labels.append(label)
            parts.append(f'[b]Langues :[/b] {", ".join(lang_labels)}')

        # ── Sous-titres (from MI text tracks) ──
        sub_tracks = self._parse_mi_subtitle_tracks(mi_text) if mi_text else []
        if sub_tracks:
            sub_labels: list[str] = []
            for st in sub_tracks:
                label = st['title']
                if st.get('forced'):
                    label += ' (Forcé)'
                sub_labels.append(label)
            parts.append(f'[b]Sous-titres :[/b] {", ".join(sub_labels)}')

        # ── Taille ──
        m_size = re.search(r'File size\s*:\s*(.+)', mi_text, re.IGNORECASE) if mi_text else None
        if m_size:
            parts.append(f'[b]Taille :[/b] {m_size.group(1).strip()}')

        parts.append('')

        # ── Screenshots (opt-in via config) ──
        include_screenshots = self.config['TRACKERS'].get(self.tracker, {}).get('include_screenshots', False)
        image_list = meta.get('image_list', []) if include_screenshots else []
        if image_list:
            parts.append('[color=#eab308][b]--- CAPTURES ---[/b][/color]')
            parts.append('')
            for img in image_list:
                raw = img.get('raw_url', '')
                web = img.get('web_url', '')
                if raw:
                    if web:
                        parts.append(f'[url={web}][img]{raw}[/img][/url]')
                    else:
                        parts.append(f'[img]{raw}[/img]')
            parts.append('')

        # ── Signature ──
        parts.append('[i]Généré par Upload Assistant[/i]')
        parts.append('[/center]')

        return '\n'.join(parts)

    # ──────────────────────────────────────────────────────────
    #  NFO generation
    # ──────────────────────────────────────────────────────────

    async def _get_or_generate_nfo(self, meta: Meta) -> str | None:
        base = os.path.join(meta.get('base_dir', '/tmp'), 'tmp', meta.get('uuid', ''))
        existing = glob.glob(os.path.join(base, '*.nfo'))
        if existing:
            return existing[0]

        nfo_gen = SceneNfoGenerator(self.config)
        nfo_path = await nfo_gen.generate_nfo(meta, self.tracker)
        return nfo_path

    # ──────────────────────────────────────────────────────────
    #  Upload
    # ──────────────────────────────────────────────────────────

    async def upload(self, meta: Meta, _disctype: str) -> bool:
        """Upload torrent to la-cale.space.

        POST https://la-cale.space/api/external/upload
          X-Api-Key: <api_key>
          Content-Type: multipart/form-data

        Required: title, categoryId, file (.torrent), nfoFile
        Optional: description, tmdbId, tmdbType, coverUrl, tags[]
        """
        common = COMMON(config=self.config)
        await common.create_torrent_for_upload(meta, self.tracker, self.source_flag)

        # ── Build release name ──
        name_result = await self.get_name(meta)
        title = name_result.get('name', '') if isinstance(name_result, dict) else str(name_result)

        # ── Language tag ──
        language_tag = await self._build_audio_string(meta)

        # ── Read torrent file ──
        torrent_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}].torrent"
        async with aiofiles.open(torrent_path, 'rb') as f:
            torrent_bytes = await f.read()

        # ── NFO file ──
        nfo_path = await self._get_or_generate_nfo(meta)
        nfo_bytes = b''
        if nfo_path and await asyncio.to_thread(os.path.exists, nfo_path):
            async with aiofiles.open(nfo_path, 'rb') as f:
                nfo_bytes = await f.read()
        else:
            console.print("[yellow]LACALE: No NFO available — upload will likely be rejected[/yellow]")

        # ── Description (BBCode) ──
        description = await self._build_description(meta)

        # ── Category ID (from /meta API) ──
        category_id = await self._get_category_id(meta)

        # ── Tags (list of IDs from /meta API) ──
        tag_ids = await self._build_tag_ids(meta, language_tag)

        # Small delay between meta lookups and upload to avoid rate limiting
        await asyncio.sleep(2)

        # ── TMDB metadata ──
        tmdb_id = str(meta.get('tmdb', '')) if meta.get('tmdb') else ''
        tmdb_type = 'TV' if str(meta.get('category', '')).upper() == 'TV' else 'MOVIE'
        cover_url = meta.get('poster', '')

        # ── Multipart form ──
        files: dict[str, tuple[str, bytes, str]] = {
            'file': (f'{title}.torrent', torrent_bytes, 'application/x-bittorrent'),
            'nfoFile': ('release.nfo', nfo_bytes, 'text/plain'),
        }

        data: dict[str, Any] = {
            'title': title,
            'categoryId': category_id,
        }

        if description:
            data['description'] = description
        if tmdb_id:
            data['tmdbId'] = tmdb_id
            data['tmdbType'] = tmdb_type
        if cover_url:
            data['coverUrl'] = cover_url

        headers: dict[str, str] = {
            'X-Api-Key': self.api_key,
            'Accept': 'application/json',
        }

        if not self.api_key:
            console.print("[red]LACALE: No API key configured (set api_key in config).[/red]")
            meta['tracker_status'][self.tracker]['status_message'] = 'No API key configured'
            return False

        try:
            if not meta['debug']:
                max_retries = 3
                retry_delay = 10
                timeout = 40.0

                # Build the multipart fields for tags (repeated field)
                # httpx handles repeated fields via a list of tuples
                form_fields: dict[str, Any] = dict(data)
                # For repeated tags, use the files approach
                tag_files: list[tuple[str, tuple[None, str]]] = [
                    ('tags', (None, tag_id)) for tag_id in tag_ids
                ]

                for attempt in range(max_retries):
                    try:
                        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                            # Merge tag fields into files for repeated form fields
                            all_files = {**files}
                            response = await client.post(
                                url=self.upload_url,
                                data=form_fields,
                                files=[*all_files.items(), *tag_files],
                                headers=headers,
                            )

                        if response.status_code == 200:
                            try:
                                response_data = response.json()

                                if not response_data.get('success', True):
                                    error_msg = response_data.get('message', 'Unknown error')
                                    meta['tracker_status'][self.tracker]['status_message'] = f"API error: {error_msg}"
                                    console.print(f"[yellow]LACALE upload failed: {error_msg}[/yellow]")
                                    return False

                                torrent_id = response_data.get('id', '')
                                link = response_data.get('link', '')
                                if torrent_id:
                                    meta['tracker_status'][self.tracker]['torrent_id'] = torrent_id
                                meta['tracker_status'][self.tracker]['status_message'] = response_data
                                if link:
                                    console.print(f"[green]LACALE upload success: {link}[/green]")
                                return True
                            except json.JSONDecodeError:
                                meta['tracker_status'][self.tracker]['status_message'] = (
                                    "data error: LACALE JSON decode error"
                                )
                                return False

                        elif response.status_code == 409:
                            error_detail: Any = ''
                            try:
                                error_detail = response.json()
                            except Exception:
                                error_detail = response.text[:500]
                            meta['tracker_status'][self.tracker]['status_message'] = {
                                'error': 'HTTP 409 — Duplicate torrent (same infoHash)',
                                'detail': error_detail,
                            }
                            console.print("[yellow]LACALE: Duplicate torrent (same infoHash already exists).[/yellow]")
                            return False

                        elif response.status_code in (400, 401, 403):
                            error_detail = ''
                            try:
                                error_detail = response.json()
                            except Exception:
                                error_detail = response.text[:500]
                            meta['tracker_status'][self.tracker]['status_message'] = {
                                'error': f'HTTP {response.status_code}',
                                'detail': error_detail,
                            }
                            console.print(f"[red]LACALE upload failed: HTTP {response.status_code}[/red]")
                            if error_detail:
                                console.print(f"[dim]{error_detail}[/dim]")
                            return False

                        elif response.status_code == 429:
                            if attempt < max_retries - 1:
                                console.print(
                                    f"[yellow]LACALE: Rate limited (429), retrying in "
                                    f"{retry_delay * 3}s… (attempt {attempt + 1}/{max_retries})[/yellow]"
                                )
                                await asyncio.sleep(retry_delay * 3)
                                continue
                            meta['tracker_status'][self.tracker]['status_message'] = {
                                'error': 'HTTP 429 — Rate limited',
                            }
                            console.print("[red]LACALE upload failed: rate limited after retries.[/red]")
                            return False

                        else:
                            if attempt < max_retries - 1:
                                console.print(
                                    f"[yellow]LACALE: HTTP {response.status_code}, retrying in "
                                    f"{retry_delay}s… (attempt {attempt + 1}/{max_retries})[/yellow]"
                                )
                                await asyncio.sleep(retry_delay)
                                continue
                            error_detail = ''
                            try:
                                error_detail = response.json()
                            except Exception:
                                error_detail = response.text[:500]
                            meta['tracker_status'][self.tracker]['status_message'] = {
                                'error': f'HTTP {response.status_code}',
                                'detail': error_detail,
                            }
                            console.print(f"[red]LACALE upload failed after {max_retries} attempts: HTTP {response.status_code}[/red]")
                            if error_detail:
                                console.print(f"[dim]{error_detail}[/dim]")
                            return False

                    except httpx.TimeoutException:
                        if attempt < max_retries - 1:
                            timeout = timeout * 1.5
                            console.print(
                                f"[yellow]LACALE: timeout, retrying in {retry_delay}s with "
                                f"{timeout:.0f}s timeout… (attempt {attempt + 1}/{max_retries})[/yellow]"
                            )
                            await asyncio.sleep(retry_delay)
                            continue
                        meta['tracker_status'][self.tracker]['status_message'] = (
                            "data error: Request timed out after multiple attempts"
                        )
                        return False

                    except httpx.RequestError as e:
                        if attempt < max_retries - 1:
                            console.print(
                                f"[yellow]LACALE: request error, retrying in {retry_delay}s… "
                                f"(attempt {attempt + 1}/{max_retries})[/yellow]"
                            )
                            await asyncio.sleep(retry_delay)
                            continue
                        meta['tracker_status'][self.tracker]['status_message'] = (
                            f"data error: Upload failed: {e}"
                        )
                        console.print(f"[red]LACALE upload error: {e}[/red]")
                        return False

                return False  # exhausted retries

            else:
                # ── Debug mode ──
                desc_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}]DESCRIPTION.txt"
                async with aiofiles.open(desc_path, 'w', encoding='utf-8') as f:
                    await f.write(description)
                console.print(f"DEBUG: Saving final description to {desc_path}")
                console.print("[cyan]LACALE Debug — Request data:[/cyan]")
                console.print(f"  Title:       {title}")
                console.print(f"  CategoryId:  {category_id}")
                console.print(f"  Tags:        {tag_ids}")
                console.print(f"  TMDB:        {tmdb_id} ({tmdb_type})")
                console.print(f"  Cover URL:   {cover_url}")
                console.print(f"  Description: {description[:500]}…")
                meta['tracker_status'][self.tracker]['status_message'] = "Debug mode, not uploaded."
                return True

        except Exception as e:
            meta['tracker_status'][self.tracker]['status_message'] = f"data error: Upload failed: {e}"
            console.print(f"[red]LACALE upload error: {e}[/red]")
            return False

    # ──────────────────────────────────────────────────────────
    #  Dupe search
    # ──────────────────────────────────────────────────────────

    async def search_existing(self, meta: Meta, _disctype: str) -> list[dict[str, Any]]:
        """Search for existing torrents on la-cale.space.

        GET /api/external?q=...&tmdbId=...
        Uses X-Api-Key header for authentication.
        """
        dupes: list[dict[str, Any]] = []

        if not self.api_key:
            console.print("[yellow]LACALE: No API key configured, skipping dupe check.[/yellow]")
            return []

        headers = {
            'X-Api-Key': self.api_key,
            'Accept': 'application/json',
        }

        # Strategy 1: Search by TMDB ID
        tmdb_id = meta.get('tmdb')
        seen_guids: set[str] = set()

        if tmdb_id:
            try:
                async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                    resp = await client.get(
                        self.search_url,
                        headers=headers,
                        params={'tmdbId': str(tmdb_id)},
                    )
                if resp.status_code == 200:
                    items = resp.json() if isinstance(resp.json(), list) else []
                    for item in items:
                        guid = item.get('guid', '')
                        if guid and guid not in seen_guids:
                            seen_guids.add(guid)
                            dupes.append({
                                'name': item.get('title', ''),
                                'size': item.get('size'),
                                'link': item.get('link', ''),
                                'id': guid,
                            })
            except Exception as e:
                if meta.get('debug'):
                    console.print(f"[yellow]LACALE TMDB search error: {e}[/yellow]")

        # Strategy 2: Search by text (title + year)
        title = meta.get('title', '')
        year = meta.get('year', '')
        search_term = f'{title} {year}'.strip()

        if search_term:
            try:
                async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                    resp = await client.get(
                        self.search_url,
                        headers=headers,
                        params={'q': search_term},
                    )
                if resp.status_code == 200:
                    items = resp.json() if isinstance(resp.json(), list) else []

                    def _normalize(s: str) -> str:
                        return re.sub(r'[^a-z0-9]', '', unidecode(s).lower())

                    title_norm = _normalize(title)
                    year_str = str(year).strip()

                    for item in items:
                        guid = item.get('guid', '')
                        if guid in seen_guids:
                            continue
                        name = item.get('title', '')
                        if not name:
                            continue
                        name_norm = _normalize(name)
                        if title_norm not in name_norm:
                            if meta.get('debug'):
                                console.print(f"[dim]LACALE dupe skip (title mismatch): {name}[/dim]")
                            continue
                        if year_str and year_str not in name:
                            if meta.get('debug'):
                                console.print(f"[dim]LACALE dupe skip (year mismatch): {name}[/dim]")
                            continue
                        seen_guids.add(guid)
                        dupes.append({
                            'name': name,
                            'size': item.get('size'),
                            'link': item.get('link', ''),
                            'id': guid,
                        })
            except Exception as e:
                if meta.get('debug'):
                    console.print(f"[yellow]LACALE text search error: {e}[/yellow]")

        if meta.get('debug'):
            console.print(f"[cyan]LACALE dupe search found {len(dupes)} result(s)[/cyan]")

        return await self._check_french_lang_dupes(dupes, meta)

    async def edit_desc(self, _meta: Meta) -> None:
        """No-op — LACALE descriptions are built in upload()."""
        return
