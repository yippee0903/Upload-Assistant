# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
"""
torr9.xyz — French private tracker (custom REST API)

Upload endpoint:  POST https://api.torr9.xyz/api/v1/torrents/upload
Authentication:   Bearer token
Content-Type:     multipart/form-data

Required fields:  torrent_file, title, description, nfo, category, subcategory
Optional fields:  tags, is_exclusive, is_anonymous

API docs reverse-engineered from:
  https://codeberg.org/f4l5y/ntt/src/branch/main/docs/ntt-torr9up.md
"""

import asyncio
import base64
import glob
import json
import os
import re
from datetime import datetime
from typing import Any, Union

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

FRENCH_MONTHS: list[str] = [
    '', 'janvier', 'février', 'mars', 'avril', 'mai', 'juin',
    'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre',
]


class TORR9(FrenchTrackerMixin):
    """torr9.xyz tracker — French private tracker with custom REST API."""

    LOGIN_URL: str = 'https://api.torr9.xyz/api/v1/auth/login'

    def __init__(self, config: Config) -> None:
        self.config: Config = config
        self.tracker: str = 'TORR9'
        self.source_flag: str = 'TORR9'
        self.upload_url: str = 'https://api.torr9.xyz/api/v1/torrents/upload'
        self.torrent_url: str = 'https://torr9.xyz/torrents/'
        tracker_cfg = self.config['TRACKERS'].get(self.tracker, {})
        self.username: str = str(tracker_cfg.get('username', '')).strip()
        self.password: str = str(tracker_cfg.get('password', '')).strip()
        self.api_key: str = str(tracker_cfg.get('api_key', '')).strip()
        self._bearer_token: str | None = None  # cached JWT from login
        self.tmdb_manager = TmdbManager(config)
        self.banned_groups: list[str] = [""]

    # ──────────────────────────────────────────────────────────
    #  Authentication — login to obtain Bearer JWT
    # ──────────────────────────────────────────────────────────

    async def _login(self) -> str | None:
        """Authenticate via the login API and return a Bearer token.

        POST https://api.torr9.xyz/api/v1/auth/login
          Body: {"username": "...", "password": "...", "remember_me": true}
          Response: {"token": "<jwt>", "user": {"passkey": "...", ...}}
        """
        if not self.username or not self.password:
            return None

        payload = {
            'username': self.username,
            'password': self.password,
            'remember_me': True,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.post(
                    self.LOGIN_URL,
                    json=payload,
                    headers={'Accept': 'application/json', 'Content-Type': 'application/json'},
                )

            if resp.status_code in (200, 201):
                data = resp.json()
                token = data.get('token', '')
                if token:
                    return token
                else:
                    console.print("[red]TORR9: Login response missing token.[/red]")
                    return None
            else:
                detail = ''
                try:
                    detail = resp.json()
                except Exception:
                    detail = resp.text[:300]
                console.print(f"[red]TORR9: Login failed (HTTP {resp.status_code}): {detail}[/red]")
                return None

        except Exception as e:
            console.print(f"[red]TORR9: Login error: {e}[/red]")
            return None

    async def _get_token(self) -> str:
        """Return a valid Bearer token, logging in if necessary.

        Priority:
        1. Cached JWT from a previous _login() call
        2. Fresh JWT via _login() (username/password)
        3. Static api_key from config (fallback)
        """
        if self._bearer_token:
            return self._bearer_token

        if self.username and self.password:
            token = await self._login()
            if token:
                self._bearer_token = token
                return token
            console.print("[yellow]TORR9: Login failed, falling back to api_key.[/yellow]")

        return self.api_key

    # ──────────────────────────────────────────────────────────
    #  Audio / naming / French title — inherited from FrenchTrackerMixin
    # ──────────────────────────────────────────────────────────


    # ──────────────────────────────────────────────────────────
    #  Category / Subcategory  (exact strings from the upload form)
    #
    #  Categories:   Films, Séries
    #  Subcategories (Films):  Films, Films d'animation, Documentaires,
    #                          Concert, Spectacle, Sport, Vidéo-clips
    #  Subcategories (Séries): Séries TV, Emission TV, Séries Animées,
    #                          Mangas-Animes
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def _get_category(meta: Meta) -> tuple[str, str]:
        """Return (category, subcategory) strings for the Torr9 upload form.

        Values must match the exact labels shown on the site's upload page.
        """
        is_anime = bool(meta.get('mal_id'))

        if meta.get('category') == 'TV':
            if is_anime:
                return ('Séries', 'Mangas-Animes')
            return ('Séries', 'Séries TV')

        # Movie
        if is_anime:
            return ('Films', "Films d'animation")
        return ('Films', 'Films')

    # ──────────────────────────────────────────────────────────
    #  Tags  (comma-separated string inferred from release)
    #
    #  Matches the ntt-torr9up.nu autotag logic:
    #    quality, source, HDR/DV, video codec, language
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def _build_tags(meta: Meta, language_tag: str) -> str:
        """Build comma-separated tags string for Torr9.

        Mirrors the ntt script's infer_tags_from_name logic:
          quality (2160p, 1080p, 720p)
          source (REMUX, BluRay, WEB-DL, WEBRip, WEB)
          HDR/DV (HDR10Plus, DV, HDR)
          video codec (AV1, x265, x264)
          language (TRUEFRENCH, MULTi, VOSTFR, VOF, VFF, VFQ, VFI, VF2)
        """
        tags: list[str] = []

        # Quality / Resolution
        res = meta.get('resolution', '')
        if '2160' in res:
            tags.append('2160p')
        elif '1080' in res:
            tags.append('1080p')
        elif '720' in res:
            tags.append('720p')

        # Source
        type_val = meta.get('type', '').upper()
        source = meta.get('source', '')

        if type_val == 'REMUX':
            tags.append('REMUX')
        if source in ('BluRay',) or type_val == 'DISC':
            tags.append('BluRay')
        if type_val == 'WEBDL':
            tags.append('WEB-DL')
        elif type_val == 'WEBRIP':
            tags.append('WEBRip')
        elif type_val == 'HDTV':
            tags.append('HDTV')

        # HDR / DV
        hdr = meta.get('hdr', '')
        if 'HDR10+' in hdr or 'HDR10Plus' in hdr:
            tags.append('HDR10Plus')
        elif 'HDR' in hdr:
            tags.append('HDR')

        if meta.get('dv', '') or 'DV' in str(meta.get('hdr', '')):
            tags.append('DV')

        # Video codec
        codec = meta.get('video_codec', '') or meta.get('video_encode', '')
        codec_upper = codec.upper().replace('.', '').replace('-', '')
        if 'AV1' in codec_upper:
            tags.append('AV1')
        elif 'X265' in codec_upper or 'H265' in codec_upper or 'HEVC' in codec_upper:
            tags.append('x265')
        elif 'X264' in codec_upper or 'H264' in codec_upper or 'AVC' in codec_upper:
            tags.append('x264')

        # Language
        if language_tag:
            # Normalize MULTI.VFF → MULTi
            if language_tag.startswith('MULTI'):
                tags.append('MULTi')
                # Also add the specific variant (VFF, VOF, etc.)
                parts = language_tag.split('.')
                if len(parts) > 1:
                    tags.append(parts[1])
            else:
                tags.append(language_tag)

        return ', '.join(tags)

    # ──────────────────────────────────────────────────────────
    #  Description builder  (BBCode) — matches Torr9 site template
    # ──────────────────────────────────────────────────────────

    async def _build_description(self, meta: Meta) -> str:
        """Build BBCode description for Torr9, matching the site's presentation style.

        Structure: [center] wrapped, [font=Verdana] content, section headers,
        flag emojis for audio/subtitles, actor photos, rating badge.
        """
        C = '#3d85c6'   # accent colour
        TC = '#ea9999'  # tagline colour
        parts: list[str] = []

        # ── Fetch French TMDB data ──
        fr_data: dict[str, Any] = {}
        try:
            fr_data = await self.tmdb_manager.get_tmdb_localized_data(
                meta, data_type='main', language='fr', append_to_response='credits'
            ) or {}
        except Exception:
            pass

        fr_title = str(fr_data.get('title', '') or meta.get('title', '')).strip()
        fr_overview = str(fr_data.get('overview', '')).strip()
        year = meta.get('year', '')
        tagline = str(fr_data.get('tagline', '')).strip()

        # Full-size poster (w500)
        poster = meta.get('poster', '') or ''
        if 'image.tmdb.org/t/p/' in poster:
            poster = re.sub(r'/t/p/[^/]+/', '/t/p/w500/', poster)

        # MI text for technical parsing
        mi_text = await self._get_mediainfo_text(meta)

        # ── Open [center] ──
        parts.append('[center]')

        # ── Title block ──
        parts.append(f'[b][font=Verdana][color={C}][size=29]{fr_title} ({year})[/size][/color][/font][/b]')
        parts.append('')

        # ── Poster (original size) ──
        if poster:
            parts.append(f'[img]{poster}[/img]')
            parts.append('')

        # ── Tagline ──
        if tagline:
            parts.append(f'[color={TC}][i][b][font=Verdana][size=22]')
            parts.append(f'\"{ tagline }\"[/size][/font][/b][/i][/color]')
            parts.append('')

        # ══════════════════════════════════════════════════════
        #  Informations
        # ══════════════════════════════════════════════════════
        parts.append(f'[b][font=Verdana][color={C}][size=18]━━━ Informations ━━━[/size][/color][/font][/b]')

        # Open content wrapper
        parts.append('[font=Verdana][size=13]')

        # Original title
        original_title = str(meta.get('original_title', '') or meta.get('title', '')).strip()
        if original_title and original_title != fr_title:
            parts.append(f'[b][color={C}]Titre original :[/color][/b] [i]{original_title}[/i]')

        # Country
        countries = fr_data.get('production_countries', meta.get('production_countries', []))
        if countries and isinstance(countries, list):
            names = [c.get('name', '') for c in countries if isinstance(c, dict) and c.get('name')]
            if names:
                parts.append(f'[b][color={C}]Pays :[/color][/b] [i]{", ".join(names)}[/i]')

        # Genres (with tag links)
        genres_list = fr_data.get('genres', [])
        if genres_list and isinstance(genres_list, list):
            links = []
            for g in genres_list:
                if isinstance(g, dict) and g.get('name'):
                    gn = g['name']
                    links.append(f'[i][url=/torrents?tags={gn}]{gn}[/url][/i]')
            if links:
                parts.append(f'[b][color={C}]Genres :[/color][/b] {", ".join(links)}')

        # Release date (French formatted)
        release_date = str(
            fr_data.get('release_date', '')
            or meta.get('release_date', '')
            or meta.get('first_air_date', '')
        ).strip()
        if release_date:
            parts.append(f'[b][color={C}]Date de sortie :[/color][/b] [i]{self._format_french_date(release_date)}[/i]')
        elif year:
            parts.append(f'[b][color={C}]Date de sortie :[/color][/b] [i]{year}[/i]')

        # Runtime
        runtime = fr_data.get('runtime') or meta.get('runtime', 0)
        if runtime:
            h, m = divmod(int(runtime), 60)
            dur = f"{h}h{m:02d}" if h > 0 else f"{m}min"
            parts.append(f'[b][color={C}]Durée :[/color][/b] [i]{dur}[/i]')

        # Credits
        credits = fr_data.get('credits', {})
        crew = credits.get('crew', []) if isinstance(credits, dict) else []
        cast = credits.get('cast', []) if isinstance(credits, dict) else []

        directors = [p['name'] for p in crew if isinstance(p, dict) and p.get('job') == 'Director' and p.get('name')]
        if not directors:
            meta_dirs = meta.get('tmdb_directors', [])
            if isinstance(meta_dirs, list):
                directors = [d.get('name', d) if isinstance(d, dict) else str(d) for d in meta_dirs]
        if directors:
            label = 'Réalisateur' if len(directors) == 1 else 'Réalisateurs'
            parts.append(f'[b][color={C}]{label} :[/color][/b] [i]{", ".join(directors)}[/i]')

        # Scénaristes
        seen_w: set[str] = set()
        writers: list[str] = []
        for p in crew:
            if isinstance(p, dict) and p.get('job') in ('Screenplay', 'Writer', 'Story') and p.get('name') and p['name'] not in seen_w:
                writers.append(p['name'])
                seen_w.add(p['name'])
        if writers:
            w_label = 'Scénariste' if len(writers) == 1 else 'Scénaristes'
            parts.append(f'[b][color={C}]{w_label} :[/color][/b] [i]{", ".join(writers)}[/i]')

        actors = [p['name'] for p in cast[:5] if isinstance(p, dict) and p.get('name')]
        if actors:
            parts.append(f'[b][color={C}]Acteurs :[/color][/b] [i]{", ".join(actors)}[/i]')

        # Blank line before rating/links
        parts.append('')

        # Actor profile photos (w185 thumbnails)
        actor_photos = []
        for p in cast[:5]:
            if isinstance(p, dict) and p.get('profile_path'):
                actor_photos.append(f'[img]https://image.tmdb.org/t/p/w185{p["profile_path"]}[/img]')
        if actor_photos:
            parts.append('')
            parts.append(' '.join(actor_photos))

        # Rating with SVG badge
        vote_avg = fr_data.get('vote_average') or meta.get('vote_average')
        vote_count = fr_data.get('vote_count') or meta.get('vote_count')
        if vote_avg and vote_count:
            score = round(float(vote_avg) * 10)
            parts.append(
                f'[img]https://img.streetprez.com/note/{score}.svg[/img] '
                f'[i]{vote_avg} ({vote_count})[/i]'
            )

        # External links
        ext_links: list[str] = []
        imdb_id = meta.get('imdb_id', 0)
        if imdb_id and int(imdb_id) > 0:
            ext_links.append(f'[url=https://www.imdb.com/title/tt{str(imdb_id).zfill(7)}/]IMDb[/url]')
        tmdb_id_val = meta.get('tmdb', '')
        if tmdb_id_val:
            tmdb_cat = 'movie' if meta.get('category', '').upper() != 'TV' else 'tv'
            ext_links.append(f'[url=https://www.themoviedb.org/{tmdb_cat}/{tmdb_id_val}]TMDB[/url]')
        if ext_links:
            parts.append('')
            parts.append(' │ '.join(ext_links))

        parts.append('')

        # ══════════════════════════════════════════════════════
        #  Synopsis
        # ══════════════════════════════════════════════════════
        parts.append(f'[b][color={C}][size=18]━━━ Synopsis ━━━[/size][/color][/b]')
        synopsis = fr_overview or str(meta.get('overview', '')).strip() or 'Aucun synopsis disponible.'
        parts.append(synopsis)
        parts.append('')

        # ══════════════════════════════════════════════════════
        #  Informations techniques
        # ══════════════════════════════════════════════════════
        parts.append(f'[b][color={C}][size=18]━━━ Informations techniques ━━━[/size][/color][/b]')

        # Type (Remux, Encode, WEB-DL, …)
        type_label = self._get_type_label(meta)
        if type_label:
            parts.append(f'[b][color={C}]Type :[/color][/b] [i]{type_label}[/i]')

        # Source
        source_str = meta.get('source', '') or meta.get('type', '')
        if source_str:
            parts.append(f'[b][color={C}]Source :[/color][/b] [i]{source_str}[/i]')

        # Resolution
        resolution = meta.get('resolution', '')
        if resolution:
            parts.append(f'[b][color={C}]Résolution :[/color][/b] [i]{resolution}[/i]')

        # Container format from MI
        container_display = self._format_container(mi_text)
        if container_display:
            parts.append(f'[b][color={C}]Format vidéo :[/color][/b] [i]{container_display}[/i]')

        # Video codec
        video_codec = meta.get('video_codec', '') or meta.get('video_encode', '')
        if video_codec:
            parts.append(f'[b][color={C}]Codec vidéo :[/color][/b] [i]{video_codec}[/i]')

        # HDR / Dolby Vision
        hdr_dv_badge = self._format_hdr_dv_bbcode(meta)
        if hdr_dv_badge:
            parts.append(f'[b][color={C}]HDR :[/color][/b] {hdr_dv_badge}')

        # Video bitrate from MI
        if mi_text:
            vbr_match = re.search(r'(?:^|\n)Bit rate\s*:\s*(.+?)\s*(?:\n|$)', mi_text)
            if vbr_match:
                parts.append(f'[b][color={C}]Débit vidéo :[/color][/b] [i]{vbr_match.group(1).strip()}[/i]')

        parts.append('')

        # ── Audio tracks ──
        parts.append(f'[b][color={C}][size=18]━━━ Audio(s) ━━━[/size][/color][/b]')
        audio_lines = self._format_audio_bbcode(mi_text)
        if audio_lines:
            for al in audio_lines:
                parts.append(f' {al}')
        else:
            parts.append(' [i]Non spécifié[/i]')
        parts.append('')

        # ── Subtitles ──
        parts.append(f'[b][color={C}][size=18]━━━ Sous-titre(s) ━━━[/size][/color][/b]')
        sub_lines = self._format_subtitle_bbcode(mi_text)
        if sub_lines:
            for sl in sub_lines:
                parts.append(f' {sl}')
        else:
            parts.append(' [i]Aucun[/i]')
        parts.append('')

        # ══════════════════════════════════════════════════════
        #  Captures d'écran  (opt-in via config: include_screenshots)
        # ══════════════════════════════════════════════════════
        include_screens = self.config['TRACKERS'].get(self.tracker, {}).get('include_screenshots', False)
        image_list: list[dict[str, Any]] = meta.get('image_list', []) if include_screens else []
        if image_list:
            parts.append(f'[b][color={C}][size=18]━━━ Captures d\'écran ━━━[/size][/color][/b]')
            for img in image_list:
                raw = img.get('raw_url', '')
                web = img.get('web_url', '')
                if raw:
                    if web:
                        parts.append(f'[url={web}][img]{raw}[/img][/url]')
                    else:
                        parts.append(f'[img]{raw}[/img]')
            parts.append('')

        # ══════════════════════════════════════════════════════
        #  Release
        # ══════════════════════════════════════════════════════
        parts.append(f'[b][color={C}][size=18]━━━ Release ━━━[/size][/color][/b]')

        release_name = meta.get('uuid', '')
        parts.append(f'[b][color={C}]Titre :[/color][/b] [i]{release_name}[/i]')

        # Total size
        if mi_text:
            size_match = re.search(r'File size\s*:\s*(.+?)\s*(?:\n|$)', mi_text)
            if size_match:
                parts.append(f'[b][color={C}]Taille totale :[/color][/b] {size_match.group(1).strip()}')

        # File count
        file_count = self._count_files(meta)
        if file_count:
            parts.append(f'[b][color={C}]Nombre de fichier :[/color][/b] {file_count}')

        # Release group
        group = self._get_release_group(meta)
        if group:
            parts.append(f'[b][color={C}]Groupe :[/color][/b] [i]{group}[/i]')

        # Close content wrapper
        parts.append('[/size][/font]')

        # Close center
        parts.append('[/center]')

        # ── Signature ──
        ua_sig = meta.get('ua_signature', 'Created by Upload Assistant')
        parts.append('')
        parts.append(f'[right][url=https://github.com/Audionut/Upload-Assistant][size=1]{ua_sig}[/size][/url][/right]')

        return '\n'.join(parts)

    async def _get_mediainfo_text(self, meta: Meta) -> str:
        """Read MediaInfo text from temp files."""
        base = os.path.join(meta.get('base_dir', ''), 'tmp', meta.get('uuid', ''))

        for fname in ('MEDIAINFO_CLEANPATH.txt', 'MEDIAINFO.txt'):
            fpath = os.path.join(base, fname)
            if os.path.exists(fpath):
                async with aiofiles.open(fpath, encoding='utf-8') as f:
                    content = await f.read()
                    if content.strip():
                        return content

        if meta.get('bdinfo') is not None:
            bd_path = os.path.join(base, 'BD_SUMMARY_00.txt')
            if os.path.exists(bd_path):
                async with aiofiles.open(bd_path, encoding='utf-8') as f:
                    return await f.read()

        return ''

    @staticmethod
    def _format_french_date(date_str: str) -> str:
        """Format YYYY-MM-DD to French full date, e.g. '24 octobre 2011'."""
        try:
            dt = datetime.strptime(date_str, '%Y-%m-%d')
            day_str = '1er' if dt.day == 1 else str(dt.day)
            return f"{day_str} {FRENCH_MONTHS[dt.month]} {dt.year}"
        except (ValueError, IndexError):
            return date_str

    @staticmethod
    def _count_files(meta: Meta) -> str:
        """Count files in the release path."""
        path = meta.get('path', '')
        if not path or not os.path.exists(path):
            return ''
        if os.path.isfile(path):
            return '1'
        count = sum(1 for _, _, files in os.walk(path) for _ in files)
        return str(count) if count else ''

    # ──────────────────────────────────────────────────────────
    #  NFO file
    # ──────────────────────────────────────────────────────────

    async def _get_or_generate_nfo(self, meta: Meta) -> Union[str, None]:
        """Get existing NFO path or generate one from MediaInfo.

        Torr9 requires an NFO file for every upload.
        """
        base = os.path.join(meta['base_dir'], 'tmp', meta['uuid'])

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
        """Upload torrent to torr9.xyz.

        POST https://api.torr9.xyz/api/v1/torrents/upload
          Authorization: Bearer <api_key>
          Content-Type:  multipart/form-data

        Required fields: torrent_file, title, description, nfo, category, subcategory
        Optional fields: tags, is_exclusive, is_anonymous
        """
        common = COMMON(config=self.config)
        await common.create_torrent_for_upload(meta, self.tracker, self.source_flag)

        # ── Build release name ──
        name_result = await self.get_name(meta)
        title = name_result.get('name', '') if isinstance(name_result, dict) else str(name_result)

        # ── Language tag (for tags) ──
        language_tag = await self._build_audio_string(meta)

        # ── Read torrent file ──
        torrent_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}].torrent"
        async with aiofiles.open(torrent_path, 'rb') as f:
            torrent_bytes = await f.read()

        # ── NFO file ──
        nfo_path = await self._get_or_generate_nfo(meta)
        nfo_bytes = b''
        if nfo_path and os.path.exists(nfo_path):
            async with aiofiles.open(nfo_path, 'rb') as f:
                nfo_bytes = await f.read()
        else:
            console.print("[yellow]TORR9: No NFO available — upload may be rejected[/yellow]")

        # ── Description (BBCode) ──
        description = await self._build_description(meta)

        # ── Category / Subcategory (exact strings from site form) ──
        category, subcategory = self._get_category(meta)

        # ── Tags (comma-separated) ──
        tags = self._build_tags(meta, language_tag)

        # ── Anonymous flag ──
        anon = meta.get('anon', False) or self.config['TRACKERS'].get(self.tracker, {}).get('anon', False)

        # ── Multipart form ──
        files: dict[str, tuple[str, bytes, str]] = {
            'torrent_file': (f'{title}.torrent', torrent_bytes, 'application/x-bittorrent'),
        }

        data: dict[str, Any] = {
            'title': title,
            'description': description,
            'nfo': nfo_bytes.decode('utf-8', errors='replace') if nfo_bytes else '',
            'category': category,
            'subcategory': subcategory,
            'tags': tags,
            'is_exclusive': 'false',
            'is_anonymous': str(anon).lower(),
        }

        token = await self._get_token()
        if not token:
            console.print("[red]TORR9: No authentication available (set username/password or api_key).[/red]")
            meta['tracker_status'][self.tracker]['status_message'] = 'No authentication configured'
            return False

        headers: dict[str, str] = {
            'Authorization': f'Bearer {token}',
            'Accept': '*/*',
            'Origin': 'https://torr9.xyz',
            'Referer': 'https://torr9.xyz',
        }

        try:
            if not meta['debug']:
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

                                if isinstance(response_data, dict) and response_data.get('error'):
                                    error_msg = response_data.get('error', 'Unknown error')
                                    meta['tracker_status'][self.tracker]['status_message'] = f"API error: {error_msg}"
                                    console.print(f"[yellow]TORR9 upload failed: {error_msg}[/yellow]")
                                    return False

                                # Extract torrent_id from response
                                torrent_id = None
                                if isinstance(response_data, dict):
                                    torrent_id = (
                                        response_data.get('torrent_id')
                                        or response_data.get('id')
                                        or response_data.get('slug')
                                    )
                                if torrent_id:
                                    meta['tracker_status'][self.tracker]['torrent_id'] = torrent_id
                                meta['tracker_status'][self.tracker]['status_message'] = response_data

                                # Download the tracker-generated torrent file
                                # (the site may randomise the infohash, so
                                #  the locally-created .torrent is invalid)
                                await self._save_tracker_torrent(
                                    response_data, torrent_path, headers,
                                )

                                return True
                            except json.JSONDecodeError:
                                meta['tracker_status'][self.tracker]['status_message'] = (
                                    "data error: TORR9 JSON decode error"
                                )
                                return False

                        elif response.status_code in (400, 401, 403, 404, 422):
                            error_detail: Any = ''
                            try:
                                error_detail = response.json()
                            except Exception:
                                error_detail = response.text[:500]
                            meta['tracker_status'][self.tracker]['status_message'] = {
                                'error': f'HTTP {response.status_code}',
                                'detail': error_detail,
                            }
                            console.print(f"[red]TORR9 upload failed: HTTP {response.status_code}[/red]")
                            if error_detail:
                                console.print(f"[dim]{error_detail}[/dim]")
                            return False

                        else:
                            if attempt < max_retries - 1:
                                console.print(
                                    f"[yellow]TORR9: HTTP {response.status_code}, retrying in "
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
                            console.print(f"[red]TORR9 upload failed after {max_retries} attempts: HTTP {response.status_code}[/red]")
                            if error_detail:
                                console.print(f"[dim]{error_detail}[/dim]")
                            return False

                    except httpx.TimeoutException:
                        if attempt < max_retries - 1:
                            timeout = timeout * 1.5
                            console.print(
                                f"[yellow]TORR9: timeout, retrying in {retry_delay}s with "
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
                                f"[yellow]TORR9: request error, retrying in {retry_delay}s… "
                                f"(attempt {attempt + 1}/{max_retries})[/yellow]"
                            )
                            await asyncio.sleep(retry_delay)
                            continue
                        meta['tracker_status'][self.tracker]['status_message'] = (
                            f"data error: Upload failed: {e}"
                        )
                        console.print(f"[red]TORR9 upload error: {e}[/red]")
                        return False

                return False  # exhausted retries

            else:
                # ── Debug mode ──
                desc_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}]DESCRIPTION.txt"
                async with aiofiles.open(desc_path, 'w', encoding='utf-8') as f:
                    await f.write(description)
                console.print(f"DEBUG: Saving final description to {desc_path}")
                console.print("[cyan]TORR9 Debug — Request data:[/cyan]")
                console.print(f"  Title:       {title}")
                console.print(f"  Category:    {category} / Sub: {subcategory}")
                console.print(f"  Tags:        {tags}")
                console.print(f"  Anonymous:   {anon}")
                console.print(f"  Description: {description[:500]}…")
                meta['tracker_status'][self.tracker]['status_message'] = "Debug mode, not uploaded."
                await common.create_torrent_for_upload(
                    meta, f"{self.tracker}_DEBUG", f"{self.tracker}_DEBUG",
                    announce_url="https://fake.tracker",
                )
                return True

        except Exception as e:
            meta['tracker_status'][self.tracker]['status_message'] = f"data error: Upload failed: {e}"
            console.print(f"[red]TORR9 upload error: {e}[/red]")
            return False

    # ──────────────────────────────────────────────────────────
    #  Download tracker-generated torrent
    # ──────────────────────────────────────────────────────────

    async def _save_tracker_torrent(
        self,
        response_data: dict[str, Any],
        torrent_path: str,
        headers: dict[str, str],
    ) -> None:
        """Replace the local .torrent with the tracker-generated one.

        TORR9 may randomise the infohash server-side, so the locally
        created torrent file is no longer valid for client injection.

        Strategy (mirrors the reference *ntt-torr9up* script):
        1. Try base64-decoding ``response_data['torrent_file']``.
        2. Fall back to downloading from ``response_data['download_url']``.
        """
        saved = False

        # ── 1. base64-encoded torrent in the response ────────
        b64 = response_data.get('torrent_file') or ''
        if b64:
            try:
                raw = b64.strip()
                # Pad to a multiple of 4 if necessary
                pad = len(raw) % 4
                if pad:
                    raw += '=' * (4 - pad)
                torrent_bytes = base64.b64decode(raw)
                async with aiofiles.open(torrent_path, 'wb') as f:
                    await f.write(torrent_bytes)
                saved = True
            except Exception as e:
                console.print(f"[yellow]TORR9: base64 torrent decode failed: {e}[/yellow]")

        # ── 2. Fallback: download from URL ───────────────────
        if not saved:
            download_url = response_data.get('download_url') or ''
            if download_url:
                # Make absolute if the API returns a relative path
                if download_url.startswith('/'):
                    download_url = f"https://api.torr9.xyz{download_url}"
                try:
                    async with httpx.AsyncClient(
                        headers=headers, timeout=30.0, follow_redirects=True,
                    ) as client:
                        async with client.stream('GET', download_url) as r:
                            r.raise_for_status()
                            async with aiofiles.open(torrent_path, 'wb') as f:
                                async for chunk in r.aiter_bytes():
                                    await f.write(chunk)
                    saved = True
                except Exception as e:
                    console.print(f"[yellow]TORR9: torrent download failed: {e}[/yellow]")

        if not saved:
            console.print(
                "[yellow]TORR9: could not obtain tracker torrent — "
                "client injection may use a stale infohash.[/yellow]"
            )

    # ──────────────────────────────────────────────────────────
    #  Dupe search
    # ──────────────────────────────────────────────────────────

    async def search_existing(self, meta: Meta, _: Any = None) -> list[dict[str, Any]]:
        """Search for existing torrents on Torr9.

        Uses the dedicated ``/api/v1/torrents/search?q=…`` endpoint which
        performs a title-based search.  The generic ``/api/v1/torrents``
        listing endpoint ignores the ``q`` parameter and just returns
        paginated results.
        """
        dupes: list[dict[str, Any]] = []

        token = await self._get_token()
        if not token:
            console.print("[yellow]TORR9: No authentication configured, skipping dupe check.[/yellow]")
            return []

        title = meta.get('title', '')
        year = meta.get('year', '')
        search_term = f"{title} {year}".strip()

        if not search_term:
            return []

        try:
            headers = {
                'Authorization': f'Bearer {token}',
                'Accept': 'application/json',
            }
            params: dict[str, str] = {'q': search_term}

            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(
                    'https://api.torr9.xyz/api/v1/torrents/search',
                    headers=headers,
                    params=params,
                )

            if response.status_code != 200:
                if meta.get('debug'):
                    console.print(f"[yellow]TORR9 search returned HTTP {response.status_code}[/yellow]")
                return []

            try:
                data = response.json()
            except json.JSONDecodeError:
                return []

            items = data.get('torrents', data.get('data', []))
            if items is None:
                items = []

            # Normalize the search title for relevance filtering
            def _normalize(s: str) -> str:
                return re.sub(r'[^a-z0-9]', '', unidecode(s).lower())

            title_norm = _normalize(title)
            year_str = str(year).strip()

            for item in items:
                if not isinstance(item, dict):
                    continue
                name = item.get('title', item.get('name', ''))
                if not name:
                    continue

                # Filter: the result must contain the title AND year to be relevant
                name_norm = _normalize(name)
                if title_norm not in name_norm:
                    if meta.get('debug'):
                        console.print(f"[dim]TORR9 dupe skip (title mismatch): {name}[/dim]")
                    continue
                if year_str and year_str not in name:
                    if meta.get('debug'):
                        console.print(f"[dim]TORR9 dupe skip (year mismatch): {name}[/dim]")
                    continue

                dupes.append({
                    'name': name,
                    'size': item.get('size', item.get('file_size_bytes')),
                    'link': item.get('url', item.get('link')),
                    'id': item.get('id', item.get('torrent_id')),
                })

        except Exception as e:
            if meta.get('debug'):
                console.print(f"[yellow]TORR9 search error: {e}[/yellow]")

        if meta.get('debug'):
            console.print(f"[cyan]TORR9 dupe search found {len(dupes)} result(s)[/cyan]")

        return await self._check_french_lang_dupes(dupes, meta)

    async def edit_desc(self, _meta: Meta) -> None:
        """No-op — TORR9 descriptions are built in upload()."""
        return
