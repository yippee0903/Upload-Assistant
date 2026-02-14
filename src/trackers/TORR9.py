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


class TORR9:
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
    #  French language detection  (shared with C411 conventions)
    # ──────────────────────────────────────────────────────────

    async def _build_audio_string(self, meta: Meta) -> str:
        """Build language tag from MediaInfo audio tracks.

        Returns one of: TRUEFRENCH, VOF, VFF, VFI, VFQ, VF2,
                         MULTI.VOF, MULTI.TRUEFRENCH, MULTI.VFF, MULTI.VFQ, MULTI.VF2,
                         VOSTFR, MUET, or '' (for English/other VO).
        """
        if 'mediainfo' not in meta or 'media' not in meta.get('mediainfo', {}):
            return ''

        audio_tracks = self._get_audio_tracks(meta)

        if not audio_tracks:
            has_french_subs = self._has_french_subs(meta)
            return 'MUET.VOSTFR' if has_french_subs else 'MUET'

        audio_langs = self._extract_audio_languages(audio_tracks, meta)
        if not audio_langs:
            return ''

        has_french_audio = 'FRA' in audio_langs
        has_french_subs = self._has_french_subs(meta)
        num_audio_tracks = len(audio_tracks)
        fr_suffix = self._get_french_dub_suffix(audio_tracks)
        is_original_french = str(meta.get('original_language', '')).lower() == 'fr'
        is_truefrench = self._detect_truefrench(meta)
        is_vfi = self._detect_vfi(meta)

        def _fr_precision() -> str:
            if fr_suffix == 'VF2':
                return 'VF2'
            if is_truefrench:
                return 'TRUEFRENCH'
            if is_original_french:
                return 'VOF'
            if is_vfi:
                return 'VFI'
            if fr_suffix == 'VFQ':
                return 'VFQ'
            if fr_suffix == 'VFF':
                return 'VFF'
            return 'VFF'  # conservative default

        if not has_french_audio:
            return 'VOSTFR' if has_french_subs else ''

        non_fr = [l for l in audio_langs if l != 'FRA']

        if non_fr or num_audio_tracks > 1:
            return f'MULTI.{_fr_precision()}'

        if is_original_french:
            return 'VOF'

        return _fr_precision()

    @staticmethod
    def _get_audio_tracks(meta: Meta) -> list[dict[str, Any]]:
        media = meta.get('mediainfo', {}).get('media', {})
        tracks = media.get('track', [])
        return [t for t in tracks if t.get('@type') == 'Audio']

    @staticmethod
    def _extract_audio_languages(audio_tracks: list[dict[str, Any]], meta: Meta) -> list[str]:
        langs: list[str] = []
        for track in audio_tracks:
            lang = str(track.get('Language', '')).strip().upper()
            if not lang:
                lang_title = str(track.get('Title', '')).strip().lower()
                if any(k in lang_title for k in ('french', 'français', 'francais')):
                    lang = 'FRA'
                elif any(k in lang_title for k in ('english', 'anglais')):
                    lang = 'ENG'
            if len(lang) == 2:
                lang_map = {'FR': 'FRA', 'EN': 'ENG', 'JA': 'JPN', 'DE': 'DEU', 'ES': 'SPA', 'IT': 'ITA', 'PT': 'POR', 'RU': 'RUS', 'KO': 'KOR', 'ZH': 'ZHO'}
                lang = lang_map.get(lang, lang)
            if lang and lang not in langs:
                langs.append(lang)
        return langs

    @staticmethod
    def _get_french_dub_suffix(audio_tracks: list[dict[str, Any]]) -> str:
        for track in audio_tracks:
            lang = str(track.get('Language', '')).strip().upper()
            if lang in ('FR', 'FRA', 'FRE'):
                title = str(track.get('Title', '')).upper()
                if 'VF2' in title:
                    return 'VF2'
                if 'VFQ' in title:
                    return 'VFQ'
                if 'VFF' in title:
                    return 'VFF'
                if 'VFI' in title:
                    return 'VFI'
        return ''

    def _detect_truefrench(self, meta: Meta) -> bool:
        uuid = meta.get('uuid', '')
        return bool(re.search(r'\bTRUEFRENCH\b', uuid, re.IGNORECASE))

    def _detect_vfi(self, meta: Meta) -> bool:
        uuid = meta.get('uuid', '')
        return bool(re.search(r'\bVFI\b', uuid, re.IGNORECASE))

    def _has_french_subs(self, meta: Meta) -> bool:
        media = meta.get('mediainfo', {}).get('media', {})
        tracks = media.get('track', [])
        for track in tracks:
            if track.get('@type') == 'Text':
                lang = str(track.get('Language', '')).lower()
                title = str(track.get('Title', '')).lower()
                if lang in ('french', 'fre', 'fra', 'fr', 'français', 'francais', 'fr-fr', 'fr-ca'):
                    return True
                if 'french' in title or 'français' in title or 'francais' in title:
                    return True
        return False

    # ──────────────────────────────────────────────────────────
    #  French title from TMDB
    # ──────────────────────────────────────────────────────────

    async def _get_french_title(self, meta: Meta) -> str:
        """Get French title from TMDB, cached in meta['frtitle']."""
        if meta.get('frtitle'):
            return meta['frtitle']

        try:
            fr_data = await self.tmdb_manager.get_tmdb_localized_data(
                meta, data_type='main', language='fr', append_to_response=''
            ) or {}
            fr_title = str(fr_data.get('title', '') or fr_data.get('name', '')).strip()
            if fr_title:
                meta['frtitle'] = fr_title
                return fr_title
        except Exception:
            pass

        return meta.get('title', '')

    # ──────────────────────────────────────────────────────────
    #  Release naming   (dot-separated, Torr9 convention)
    # ──────────────────────────────────────────────────────────

    async def get_name(self, meta: Meta) -> dict[str, str]:
        """Build dot-separated release name for Torr9."""

        def _dots(text: str) -> str:
            return text.replace(' ', '.')

        def _clean(name: str) -> str:
            name = unidecode(name)
            name = re.sub(r'[^a-zA-Z0-9 .+\-]', '', name)
            return name

        type_val = meta.get('type', '').upper()
        title = await self._get_french_title(meta)
        year = meta.get('year', '')
        manual_year = meta.get('manual_year')
        if manual_year is not None and int(manual_year) > 0:
            year = manual_year

        resolution = meta.get('resolution', '')
        if resolution == 'OTHER':
            resolution = ''
        audio = meta.get('audio', '').replace('Dual-Audio', '').replace('Dubbed', '').replace('DD+', 'DDP')
        language = await self._build_audio_string(meta)

        service = meta.get('service', '')
        season = meta.get('season', '')
        episode = meta.get('episode', '')
        part = meta.get('part', '')
        repack = meta.get('repack', '')
        three_d = meta.get('3D', '')
        tag = meta.get('tag', '')
        source = meta.get('source', '')
        uhd = meta.get('uhd', '')
        hdr = meta.get('hdr', '').replace('HDR10+', 'HDR10PLUS')
        hybrid = 'Hybrid' if meta.get('webdv', '') else ''
        edition = meta.get('edition', '')
        if 'hybrid' in edition.upper():
            edition = edition.replace('Hybrid', '').strip()

        video_codec = ''
        video_encode = ''
        region = ''
        dvd_size = ''

        if meta.get('is_disc') == 'BDMV':
            video_codec = meta.get('video_codec', '').replace('H.264', 'H264').replace('H.265', 'H265')
            region = meta.get('region', '') or ''
        elif meta.get('is_disc') == 'DVD':
            region = meta.get('region', '') or ''
            dvd_size = meta.get('dvd_size', '')
        else:
            video_codec = meta.get('video_codec', '').replace('H.264', 'H264').replace('H.265', 'H265')
            video_encode = meta.get('video_encode', '').replace('H.264', 'H264').replace('H.265', 'H265')

        if meta['category'] == 'TV':
            year = meta['year'] if meta.get('search_year', '') != '' else ''
            if meta.get('manual_date'):
                season = ''
                episode = ''
        if meta.get('no_season', False) is True:
            season = ''
        if meta.get('no_year', False) is True:
            year = ''

        name = ''

        # ── MOVIE ──
        if meta['category'] == 'MOVIE':
            if type_val == 'DISC':
                if meta.get('is_disc') == 'BDMV':
                    name = f"{title} {year} {three_d} {edition} {hybrid} {repack} {language} {resolution} {region} {uhd} {source} {hdr} {audio} {video_codec}"
                elif meta.get('is_disc') == 'DVD':
                    name = f"{title} {year} {repack} {edition} {language} {region} {source} {dvd_size} {audio}"
                elif meta.get('is_disc') == 'HDDVD':
                    name = f"{title} {year} {edition} {repack} {language} {resolution} {source} {audio} {video_codec}"
            elif type_val == 'REMUX' and source in ('BluRay', 'HDDVD'):
                name = f"{title} {year} {three_d} {edition} {hybrid} {repack} {language} {resolution} {uhd} {source} REMUX {hdr} {audio} {video_codec}"
            elif type_val == 'REMUX' and source in ('PAL DVD', 'NTSC DVD', 'DVD'):
                name = f"{title} {year} {edition} {repack} {language} {source} REMUX {audio}"
            elif type_val == 'ENCODE':
                name = f"{title} {year} {edition} {hybrid} {repack} {language} {resolution} {uhd} {source} {hdr} {audio} {video_encode}"
            elif type_val == 'WEBDL':
                name = f"{title} {year} {edition} {hybrid} {repack} {language} {resolution} {uhd} {service} WEB {hdr} {audio} {video_encode}"
            elif type_val == 'WEBRIP':
                name = f"{title} {year} {edition} {hybrid} {repack} {language} {resolution} {uhd} {service} WEBRip {hdr} {audio} {video_encode}"
            elif type_val == 'HDTV':
                name = f"{title} {year} {edition} {repack} {language} {resolution} {source} {audio} {video_encode}"
            elif type_val == 'DVDRIP':
                name = f"{title} {year} {language} {source} DVDRip {audio} {video_encode}"

        # ── TV ──
        elif meta['category'] == 'TV':
            if type_val == 'DISC':
                if meta.get('is_disc') == 'BDMV':
                    name = f"{title} {year} {season}{episode} {three_d} {edition} {hybrid} {repack} {language} {resolution} {region} {uhd} {source} {hdr} {audio} {video_codec}"
                elif meta.get('is_disc') == 'DVD':
                    name = f"{title} {year} {season}{episode} {three_d} {repack} {edition} {language} {region} {source} {dvd_size} {audio}"
                elif meta.get('is_disc') == 'HDDVD':
                    name = f"{title} {year} {edition} {repack} {language} {resolution} {source} {audio} {video_codec}"
            elif type_val == 'REMUX' and source in ('BluRay', 'HDDVD'):
                name = f"{title} {year} {season}{episode} {part} {three_d} {edition} {hybrid} {repack} {language} {resolution} {uhd} {source} REMUX {hdr} {audio} {video_codec}"
            elif type_val == 'REMUX' and source in ('PAL DVD', 'NTSC DVD', 'DVD'):
                name = f"{title} {year} {season}{episode} {part} {edition} {repack} {language} {source} REMUX {audio}"
            elif type_val == 'ENCODE':
                name = f"{title} {year} {season}{episode} {part} {edition} {hybrid} {repack} {language} {resolution} {uhd} {source} {hdr} {audio} {video_encode}"
            elif type_val == 'WEBDL':
                name = f"{title} {year} {season}{episode} {part} {edition} {hybrid} {repack} {language} {resolution} {uhd} {service} WEB {hdr} {audio} {video_encode}"
            elif type_val == 'WEBRIP':
                name = f"{title} {year} {season}{episode} {part} {edition} {hybrid} {repack} {language} {resolution} {uhd} {service} WEBRip {hdr} {audio} {video_encode}"
            elif type_val == 'HDTV':
                name = f"{title} {year} {season}{episode} {part} {edition} {repack} {language} {resolution} {source} {audio} {video_encode}"
            elif type_val == 'DVDRIP':
                name = f"{title} {year} {season} {language} {source} DVDRip {audio} {video_encode}"

        try:
            name = ' '.join(name.split())
        except Exception:
            console.print("[bold red]TORR9: Unable to generate release name.[/bold red]")
            return {'name': ''}

        name_notag = name
        name = name_notag + tag
        clean_name = _clean(name)
        dot_name = _dots(clean_name)

        # Replace all hyphens with dots EXCEPT the last one (group tag separator)
        last_dash = dot_name.rfind('-')
        if last_dash > 0:
            before_tag = dot_name[:last_dash].replace('-', '.')
            dot_name = before_tag + dot_name[last_dash:]

        # Remove isolated hyphens between dots (e.g. "Title.-.Subtitle" → "Title.Subtitle")
        dot_name = re.sub(r'\.(-\.)+', '.', dot_name)
        # Collapse consecutive dots and strip boundary dots
        dot_name = re.sub(r'\.{2,}', '.', dot_name)
        dot_name = dot_name.strip('.')

        return {'name': dot_name}

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

        # Full-size poster (original)
        poster = meta.get('poster', '') or ''

        # MI text for technical parsing
        mi_text = await self._get_mediainfo_text(meta)

        # ── Open [center] ──
        parts.append('[center]')

        # ── Title block ──
        parts.append(f'[b][font=Verdana][color={C}][size=29]{fr_title}[/size]')
        parts.append('')
        parts.append(f'[size=18]({year})[/size][/color][/font][/b]')
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
        parts.append('')

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
        if directors:
            label = 'Réalisateur' if len(directors) == 1 else 'Réalisateurs'
            parts.append(f'[b][color={C}]{label} :[/color][/b] [i]{", ".join(directors)}[/i]')

        actors = [p['name'] for p in cast[:5] if isinstance(p, dict) and p.get('name')]
        if actors:
            parts.append(f'[b][color={C}]Acteurs :[/color][/b] [i]{", ".join(actors)}[/i]')

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
        parts.append('')
        synopsis = fr_overview or str(meta.get('overview', '')).strip() or 'Aucun synopsis disponible.'
        parts.append(synopsis)
        parts.append('')
        parts.append('')

        # ══════════════════════════════════════════════════════
        #  Informations techniques
        # ══════════════════════════════════════════════════════
        parts.append(f'[b][color={C}][size=18]━━━ Informations techniques ━━━[/size][/color][/b]')
        parts.append('')

        # Source
        source_str = meta.get('source', '') or meta.get('type', '')
        if source_str:
            parts.append(f'[b][color={C}]Source :[/color][/b] [i]{source_str}[/i]')

        # Resolution
        resolution = meta.get('resolution', '')
        if resolution:
            parts.append(f'[b][color={C}]Qualité vidéo :[/color][/b] [i]{resolution}[/i]')

        # Container format from MI
        container = self._parse_mi_container(mi_text)
        if container:
            parts.append(f'[b][color={C}]Format vidéo :[/color][/b] [i]{container.upper()}[/i]')

        # Video codec
        video_codec = meta.get('video_codec', '') or meta.get('video_encode', '')
        if video_codec:
            parts.append(f'[b][color={C}]Codec vidéo :[/color][/b] [i]{video_codec}[/i]')

        # Video bitrate from MI
        if mi_text:
            vbr_match = re.search(r'(?:^|\n)Bit rate\s*:\s*(.+?)\s*(?:\n|$)', mi_text)
            if vbr_match:
                parts.append(f'[b][color={C}]Débit vidéo :[/color][/b] [i]{vbr_match.group(1).strip()}[/i]')

        parts.append('')

        # ── Audio tracks ──
        audio_tracks = self._parse_mi_audio_tracks(mi_text)
        if audio_tracks:
            parts.append(f'[b][color={C}]Audio(s) :[/color][/b]')
            for at in audio_tracks:
                lang = at.get('language', 'Unknown')
                flag = self._lang_to_flag(lang)
                commercial = at.get('commercial_name', '')
                fmt = at.get('format', '')
                bitrate = at.get('bitrate', '')
                channels = at.get('channels', '')
                # Build display: flag Language — CommercialName @ Bitrate
                display = f' {flag} {lang}'
                codec_part = commercial or fmt
                if codec_part:
                    display += f' — {codec_part}'
                if channels:
                    display += f' ({channels})'
                if bitrate:
                    display += f' @ {bitrate}'
                parts.append(display)
            parts.append('')

        # ── Subtitles ──
        sub_tracks = self._parse_mi_subtitle_tracks(mi_text)
        if sub_tracks:
            parts.append(f'[b][color={C}]Sous-titres :[/color][/b]')
            # Handle duplicate languages with numbering
            lang_count: dict[str, int] = {}
            lang_total: dict[str, int] = {}
            for st in sub_tracks:
                key = st.get('title', '') or st.get('language', 'Unknown')
                lang_total[key] = lang_total.get(key, 0) + 1
            for st in sub_tracks:
                title = st.get('title', '') or st.get('language', 'Unknown')
                lang = st.get('language', title)
                flag = self._lang_to_flag(lang)
                fmt = st.get('format', '')
                # Format short name
                fmt_short = fmt
                if 'PGS' in fmt.upper():
                    fmt_short = 'PGS'
                elif 'SRT' in fmt.upper() or 'UTF-8' in fmt.upper():
                    fmt_short = 'SRT'
                elif 'ASS' in fmt.upper() or 'SSA' in fmt.upper():
                    fmt_short = 'ASS'
                # Numbering for duplicates
                suffix = ''
                if lang_total.get(title, 0) > 1:
                    lang_count[title] = lang_count.get(title, 0) + 1
                    suffix = f' (#{lang_count[title]})'
                line = f' {flag} {title} : {fmt_short}{suffix}' if fmt_short else f' {flag} {title}{suffix}'
                parts.append(line)
            parts.append('')

        # ══════════════════════════════════════════════════════
        #  Captures d'écran  (opt-in via config: include_screenshots)
        # ══════════════════════════════════════════════════════
        include_screens = self.config['TRACKERS'].get(self.tracker, {}).get('include_screenshots', False)
        image_list: list[dict[str, Any]] = meta.get('image_list', []) if include_screens else []
        if image_list:
            parts.append(f'[b][color={C}][size=18]━━━ Captures d\'écran ━━━[/size][/color][/b]')
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

        # ══════════════════════════════════════════════════════
        #  Release
        # ══════════════════════════════════════════════════════
        parts.append(f'[b][color={C}][size=18]━━━ Release ━━━[/size][/color][/b]')
        parts.append('')

        release_name = meta.get('uuid', '')
        parts.append(f'[b][color={C}]Release :[/color][/b] [i]{release_name}[/i]')

        # Total size
        if mi_text:
            size_match = re.search(r'File size\s*:\s*(.+?)\s*(?:\n|$)', mi_text)
            if size_match:
                parts.append(f'[b][color={C}]Taille totale :[/color][/b] {size_match.group(1).strip()}')

        # File count
        file_count = self._count_files(meta)
        if file_count:
            parts.append(f'[b][color={C}]Nombre de fichier :[/color][/b] {file_count}')

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
    def _lang_to_flag(lang: str) -> str:
        """Map a language name to its flag emoji."""
        key = lang.lower().split('(')[0].strip()
        return LANG_FLAGS.get(key, '\U0001f3f3\ufe0f')

    @staticmethod
    def _parse_mi_container(mi_text: str) -> str:
        """Extract container format from MI General section."""
        if not mi_text:
            return ''
        for line in mi_text.split('\n'):
            stripped = line.strip()
            if stripped.startswith('Format') and ':' in stripped and 'profile' not in stripped.lower():
                match = re.search(r':\s*(.+)', stripped)
                if match:
                    return match.group(1).strip()
            # Stop after General section
            if stripped in ('Video', 'Audio', 'Text', 'Menu') or stripped.startswith('Video'):
                break
        return ''

    @staticmethod
    def _parse_mi_audio_tracks(mi_text: str) -> list[dict[str, str]]:
        """Parse audio tracks from MediaInfo text into structured dicts.

        Each dict may contain: language, format, commercial_name, bitrate, channels, title.
        """
        tracks: list[dict[str, str]] = []
        if not mi_text:
            return tracks
        current: dict[str, str] | None = None

        for line in mi_text.split('\n'):
            stripped = line.strip()
            if stripped == 'Audio' or stripped.startswith('Audio #'):
                if current:
                    tracks.append(current)
                current = {}
                continue
            if current is not None and (
                stripped.startswith('Text') or stripped.startswith('Menu')
                or stripped == 'Video' or stripped.startswith('Video #')
                or stripped == 'General'
            ):
                tracks.append(current)
                current = None
            if current is not None and ':' in stripped:
                key, _, val = stripped.partition(':')
                key = key.strip()
                val = val.strip()
                if key == 'Language':
                    current['language'] = val
                elif key == 'Format':
                    current['format'] = val
                elif key == 'Commercial name':
                    current['commercial_name'] = val
                elif key == 'Bit rate':
                    current['bitrate'] = val
                elif key == 'Channel(s)':
                    current['channels'] = val
                elif key == 'Title':
                    current['title'] = val

        if current:
            tracks.append(current)
        return tracks

    @staticmethod
    def _parse_mi_subtitle_tracks(mi_text: str) -> list[dict[str, str]]:
        """Parse subtitle tracks from MediaInfo text into structured dicts.

        Each dict may contain: language, format, title.
        """
        tracks: list[dict[str, str]] = []
        if not mi_text:
            return tracks
        current: dict[str, str] | None = None

        for line in mi_text.split('\n'):
            stripped = line.strip()
            if stripped == 'Text' or stripped.startswith('Text #'):
                if current:
                    tracks.append(current)
                current = {}
                continue
            if current is not None and (
                stripped.startswith('Menu') or stripped.startswith('Audio')
                or stripped == 'Video' or stripped == 'General'
            ):
                tracks.append(current)
                current = None
            if current is not None and ':' in stripped:
                key, _, val = stripped.partition(':')
                key = key.strip()
                val = val.strip()
                if key == 'Language':
                    current['language'] = val
                elif key == 'Format':
                    current['format'] = val
                elif key == 'Title':
                    current['title'] = val

        if current:
            tracks.append(current)
        return tracks

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
    #  Dupe search
    # ──────────────────────────────────────────────────────────

    async def search_existing(self, meta: Meta, _disctype: str) -> list[dict[str, Any]]:
        """Search for existing torrents on Torr9.

        Torr9 API may support search — we try the standard path.
        If not available, we return an empty list (no dupe check).
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
            params = {'q': search_term}

            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(
                    'https://api.torr9.xyz/api/v1/torrents',
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

            # Handle both list and paginated response formats
            items = data if isinstance(data, list) else data.get('data', data.get('torrents', []))

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
                    'size': item.get('size'),
                    'link': item.get('url', item.get('link')),
                    'id': item.get('id', item.get('torrent_id')),
                })

        except Exception as e:
            if meta.get('debug'):
                console.print(f"[yellow]TORR9 search error: {e}[/yellow]")

        if meta.get('debug'):
            console.print(f"[cyan]TORR9 dupe search found {len(dupes)} result(s)[/cyan]")

        return dupes

    async def edit_desc(self, _meta: Meta) -> None:
        """No-op — TORR9 descriptions are built in upload()."""
        return
