# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
"""
c411.org — French private tracker (custom API, NOT UNIT3D)

Upload endpoint:  POST https://c411.org/api/torrents
Authentication:   Bearer token
Content-Type:     multipart/form-data

Required fields:  torrent, nfo, title, description, categoryId, subcategoryId
Optional fields:  options (JSON), uploaderNote, tmdbData, rawgData
"""

import glob
import json
import os
import re
import xml.etree.ElementTree as ET
from typing import Any, Union

import aiofiles
import httpx

from src.console import console
from src.nfo_generator import SceneNfoGenerator
from src.tmdb import TmdbManager
from src.trackers.COMMON import COMMON

Meta = dict[str, Any]
Config = dict[str, Any]


class C411:
    """c411.org tracker — French private tracker with custom API."""

    def __init__(self, config: Config) -> None:
        self.config: Config = config
        self.tracker: str = 'C411'
        self.source_flag: str = 'C411'
        self.upload_url: str = 'https://c411.org/api/torrents'
        self.torrent_url: str = 'https://c411.org/torrents/'
        self.api_key: str = str(self.config['TRACKERS'].get(self.tracker, {}).get('api_key', '')).strip()
        self.tmdb_manager = TmdbManager(config)
        self.banned_groups: list[str] = [""]

    # ──────────────────────────────────────────────────────────
    #  French language detection   (C411 conventions)
    #
    #  C411 language tags (filenames):
    #    Single:  VOF · TRUEFRENCH · VFF · VFI · VFQ
    #    Multi:   MULTI.VOF · MULTI.TRUEFRENCH · MULTI.VFF · MULTI.VFQ · MULTI.VF2
    #    Subs:    VOSTFR
    #    Silent:  MUET
    # ──────────────────────────────────────────────────────────

    async def _build_audio_string(self, meta: Meta) -> str:
        """Build C411-specific language tag from MediaInfo audio tracks.

        Returns one of the C411 language convention tags, or '' for
        English/other VO content.
        """
        if 'mediainfo' not in meta or 'media' not in meta.get('mediainfo', {}):
            return ''

        audio_tracks = self._get_audio_tracks(meta)

        # MUET — mediainfo present but no audio tracks
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

        # ── Determine the FR precision tag ──
        def _fr_precision() -> str:
            """Return the best FR precision tag."""
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
            # Generic 'fr' without region — default to VFF
            return 'VFF'

        # ── MULTi — 2+ audio tracks with at least 1 French ──
        if num_audio_tracks >= 2 and has_french_audio:
            return f'MULTI.{_fr_precision()}'

        # ── Single French audio ──
        if num_audio_tracks >= 1 and has_french_audio:
            return _fr_precision()

        # ── VOSTFR — no French audio but French subtitles ──
        if not has_french_audio and has_french_subs:
            return 'VOSTFR'

        # ── VO — no French content at all ──
        return ''

    def _detect_truefrench(self, meta: Meta) -> bool:
        """Check if the release is tagged TRUEFRENCH in its source name/path."""
        candidates = [
            str(meta.get('path', '')),
            str(meta.get('name', '')),
            str(meta.get('uuid', '')),
        ]
        return any('TRUEFRENCH' in text.upper() for text in candidates)

    def _detect_vfi(self, meta: Meta) -> bool:
        """Check if the release is tagged VFI (Version Française Internationale)."""
        candidates = [
            str(meta.get('path', '')),
            str(meta.get('name', '')),
            str(meta.get('uuid', '')),
        ]
        for text in candidates:
            upper = text.upper()
            # Match .VFI. or -VFI- or _VFI_ but not inside other words
            if '.VFI.' in upper or '-VFI-' in upper or '_VFI_' in upper or '.VFI-' in upper or '-VFI.' in upper:
                return True
        return False

    def _get_french_dub_suffix(self, audio_tracks: list[dict[str, Any]]) -> Union[str, None]:
        """Determine French dub variant from audio track language tags.

        Returns: 'VFF', 'VFQ', 'VF2', 'VF<n>' (n>2), or None.
        """
        fr_variants: list[str] = []

        for track in audio_tracks:
            lang = track.get('Language', '')
            if isinstance(lang, str):
                ll = lang.lower().strip()
                if ll == 'fr-fr' and 'fr-fr' not in fr_variants:
                    fr_variants.append('fr-fr')
                elif ll == 'fr-ca' and 'fr-ca' not in fr_variants:
                    fr_variants.append('fr-ca')
                elif ll in ('fr', 'fre', 'fra', 'french', 'français', 'francais') and 'fr' not in fr_variants:
                    fr_variants.append('fr')

        n = len(fr_variants)
        if n == 0:
            return None
        if n > 2:
            return f"VF{n}"

        has_vff = 'fr-fr' in fr_variants
        has_vfq = 'fr-ca' in fr_variants

        if has_vff and has_vfq:
            return 'VF2'
        if has_vfq:
            return 'VFQ'
        if has_vff:
            return 'VFF'
        return None  # generic 'fr' — no suffix

    def _get_audio_tracks(self, meta: Meta) -> list[dict[str, Any]]:
        """Extract audio tracks from mediainfo."""
        if 'mediainfo' not in meta or 'media' not in meta['mediainfo']:
            return []
        tracks = meta['mediainfo']['media'].get('track', [])
        return [t for t in tracks if t.get('@type') == 'Audio']

    def _extract_audio_languages(self, audio_tracks: list[dict[str, Any]], meta: Meta) -> list[str]:
        """Extract and normalize audio language codes."""
        audio_langs: list[str] = []
        for track in audio_tracks:
            lang = track.get('Language', '')
            if lang:
                code = self._map_language(lang)
                if code and code not in audio_langs:
                    audio_langs.append(code)
        # fallback to meta audio_languages
        if not audio_langs and meta.get('audio_languages'):
            for lang in meta['audio_languages']:
                code = self._map_language(lang)
                if code and code not in audio_langs:
                    audio_langs.append(code)
        return audio_langs

    def _map_language(self, lang: str) -> str:
        """Map language name/code to normalized 3-letter code."""
        if not lang:
            return ''
        lang_map: dict[str, str] = {
            'fre': 'FRA', 'fra': 'FRA', 'fr': 'FRA', 'french': 'FRA',
            'français': 'FRA', 'francais': 'FRA', 'fr-fr': 'FRA', 'fr-ca': 'FRA',
            'eng': 'ENG', 'en': 'ENG', 'english': 'ENG', 'en-us': 'ENG', 'en-gb': 'ENG',
            'spa': 'ESP', 'es': 'ESP', 'spanish': 'ESP', 'español': 'ESP',
            'ger': 'ALE', 'deu': 'ALE', 'de': 'ALE', 'german': 'ALE', 'deutsch': 'ALE',
            'ita': 'ITA', 'it': 'ITA', 'italian': 'ITA', 'italiano': 'ITA',
            'por': 'POR', 'pt': 'POR', 'portuguese': 'POR', 'português': 'POR',
            'jpn': 'JAP', 'ja': 'JAP', 'japanese': 'JAP',
            'kor': 'COR', 'ko': 'COR', 'korean': 'COR',
            'chi': 'CHI', 'zho': 'CHI', 'zh': 'CHI', 'chinese': 'CHI',
            'rus': 'RUS', 'ru': 'RUS', 'russian': 'RUS',
            'ara': 'ARA', 'ar': 'ARA', 'arabic': 'ARA',
            'hin': 'HIN', 'hi': 'HIN', 'hindi': 'HIN',
        }
        ll = str(lang).lower().strip()
        mapped = lang_map.get(ll)
        if mapped:
            return mapped
        return lang.upper()[:3] if len(lang) >= 3 else lang.upper()

    def _has_french_subs(self, meta: Meta) -> bool:
        """Check if French subtitles are present in MediaInfo tracks."""
        if 'mediainfo' not in meta or 'media' not in meta['mediainfo']:
            return False
        for track in meta['mediainfo']['media'].get('track', []):
            if track.get('@type') == 'Text':
                lang = str(track.get('Language', '')).lower()
                title = str(track.get('Title', '')).lower()
                if lang in ('french', 'fre', 'fra', 'fr', 'français', 'francais', 'fr-fr', 'fr-ca'):
                    return True
                if 'french' in title or 'français' in title or 'francais' in title:
                    return True
        return False

    # ──────────────────────────────────────────────────────────
    #  Release naming   (dot-separated, C411 convention)
    #
    #  Film:     Nom.Année.Langue.Résolution.Source.CodecAudio.CodecVidéo-TAG
    #  TV ep:    NOM.SXXEXX.Langue.Résolution.Source.CodecAudio.CodecVidéo-TAG
    #  TV pack:  NOM.SXX.Langue.Résolution.Source.CodecAudio.CodecVidéo-TAG
    # ──────────────────────────────────────────────────────────

    async def get_name(self, meta: Meta) -> dict[str, str]:
        """Build C411-compliant dot-separated release name."""

        def _dots(text: str) -> str:
            return text.replace(' ', '.')

        def _clean(name: str) -> str:
            for c in '<>:"/\\|?*':
                name = name.replace(c, '-')
            return name

        type_val = meta.get('type', '').upper()
        title = meta.get('title', '')
        year = meta.get('year', '')
        manual_year = meta.get('manual_year')
        if manual_year is not None and int(manual_year) > 0:
            year = manual_year

        resolution = meta.get('resolution', '')
        if resolution == 'OTHER':
            resolution = ''
        audio = meta.get('audio', '').replace('Dual-Audio', '').replace('Dubbed', '')
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
        hdr = meta.get('hdr', '')
        hybrid = 'Hybrid' if meta.get('webdv', '') else ''
        edition = meta.get('edition', '')
        if 'hybrid' in edition.upper():
            edition = edition.replace('Hybrid', '').strip()

        video_codec = ''
        video_encode = ''
        region = ''
        dvd_size = ''

        if meta.get('is_disc') == 'BDMV':
            video_codec = meta.get('video_codec', '')
            region = meta.get('region', '') or ''
        elif meta.get('is_disc') == 'DVD':
            region = meta.get('region', '') or ''
            dvd_size = meta.get('dvd_size', '')
        else:
            video_codec = meta.get('video_codec', '')
            video_encode = meta.get('video_encode', '')

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

        # ── C411 pattern: Nom.Année.Edition.Hybrid.Langue.Résolution.Source.HDR.CodecAudio.CodecVidéo-TAG ──

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
                name = f"{title} {year} {edition} {hybrid} {repack} {language} {resolution} {uhd} {service} WEB-DL {hdr} {audio} {video_encode}"
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
                name = f"{title} {year} {season}{episode} {part} {edition} {hybrid} {repack} {language} {resolution} {uhd} {service} WEB-DL {hdr} {audio} {video_encode}"
            elif type_val == 'WEBRIP':
                name = f"{title} {year} {season}{episode} {part} {edition} {hybrid} {repack} {language} {resolution} {uhd} {service} WEBRip {hdr} {audio} {video_encode}"
            elif type_val == 'HDTV':
                name = f"{title} {year} {season}{episode} {part} {edition} {repack} {language} {resolution} {source} {audio} {video_encode}"
            elif type_val == 'DVDRIP':
                name = f"{title} {year} {season} {language} {source} DVDRip {audio} {video_encode}"

        try:
            name = ' '.join(name.split())  # collapse whitespace
        except Exception:
            console.print("[bold red]C411: Unable to generate release name.[/bold red]")
            console.print(f"  category={meta.get('category')}  type={meta.get('type')}  source={meta.get('source')}")
            return {'name': ''}

        name_notag = name
        name = name_notag + tag
        clean_name = _clean(name)
        dot_name = _dots(clean_name)
        return {'name': dot_name}

    # ──────────────────────────────────────────────────────────
    #  C411 API field mapping
    # ──────────────────────────────────────────────────────────

    def _get_category_subcategory(self, meta: Meta) -> tuple[int, int]:
        """Map meta category to C411 categoryId + subcategoryId.

        C411 categories (main):
          categoryId 1 (Vidéos) → subcategoryId 6=Films, 7=Séries TV
          categoryId 3 (Musique) → 18=Albums
          categoryId 5 (Jeux)    → 36=PC
        """
        if meta.get('category') == 'TV':
            return (1, 7)   # Vidéos → Séries TV
        return (1, 6)       # Vidéos → Films (default)

    def _get_quality_option_id(self, meta: Meta) -> Union[int, None]:
        """Map resolution + source + type to C411 quality option (Type 2).

        Confirmed C411 quality option IDs:
          10=BluRay 4K       12=BluRay Remux
          16=HDRip 1080
          25=WEB-DL 1080     26=WEB-DL 4K
        """
        type_val = meta.get('type', '').upper()
        res = meta.get('resolution', '')
        is_4k = res == '2160p'

        if type_val == 'REMUX':
            return 12       # BluRay Remux (any resolution)

        if type_val == 'DISC':
            return 10 if is_4k else 12  # BluRay 4K or BluRay Remux

        if type_val in ('WEBDL', 'WEBRIP'):
            return 26 if is_4k else 25  # WEB-DL 4K or WEB-DL 1080

        if type_val in ('ENCODE', 'DVDRIP', 'HDTV'):
            return 16       # HDRip 1080

        return None

    def _get_language_option_id(self, language_tag: str) -> Union[int, None]:
        """Map C411 language tag to API option value (Type 1).

        1=Anglais  2=Français(VFF)  4=Multi(FR inclus)
        6=Québécois(VFQ)  8=VOSTFR  422=Multi VF2(FR+QC)
        """
        tag_map: dict[str, int] = {
            'MULTI.VF2':        422,
            'MULTI.VFF':        4,
            'MULTI.VFQ':        4,
            'MULTI.VOF':        4,
            'MULTI.TRUEFRENCH': 4,
            'MULTI':            4,
            'TRUEFRENCH':       2,
            'VOF':              2,
            'VFF':              2,
            'VFI':              2,
            'VFQ':              6,
            'VOSTFR':           8,
        }
        return tag_map.get(language_tag, 1)  # default: 1 (Anglais)

    def _get_season_episode_options(self, meta: Meta) -> dict[str, int]:
        """Map season/episode to C411 option types 7 and 6.

        Type 7 (Saison):   118=Intégrale, 121…150 → S01…S30
        Type 6 (Épisode):  96=Saison complète, 97…116 → E01…E20
        """
        opts: dict[str, int] = {}

        if meta.get('category') != 'TV':
            return opts

        # Season option (Type 7)
        season_str = str(meta.get('season', '')).strip()
        if season_str:
            m = re.search(r'S(\d+)', season_str, re.IGNORECASE)
            if m:
                snum = int(m.group(1))
                if 1 <= snum <= 30:
                    opts['7'] = 120 + snum      # S01 → 121 … S30 → 150
                else:
                    opts['7'] = 118             # Intégrale (fallback)

        # Episode option (Type 6)
        episode_str = str(meta.get('episode', '')).strip()
        if episode_str:
            m = re.search(r'E(\d+)', episode_str, re.IGNORECASE)
            if m:
                enum_val = int(m.group(1))
                if 1 <= enum_val <= 20:
                    opts['6'] = 96 + enum_val   # E01 → 97 … E20 → 116
        elif season_str and not episode_str:
            # Season pack → "Saison complète"
            if meta.get('tv_pack', 0):
                opts['6'] = 96                  # Saison complète

        return opts

    def _build_options(self, meta: Meta, language_tag: str) -> dict[str, Any]:
        """Build C411 options JSON: {"typeId": value_or_array, …}

        Type 1 (Langue)  → array   e.g. [4]
        Type 2 (Qualité) → scalar  e.g. 25
        Type 6 (Épisode) → scalar
        Type 7 (Saison)  → scalar
        """
        options: dict[str, Any] = {}

        # Type 1 — Language
        lang_id = self._get_language_option_id(language_tag)
        if lang_id is not None:
            options['1'] = [lang_id]

        # Type 2 — Quality
        quality_id = self._get_quality_option_id(meta)
        if quality_id is not None:
            options['2'] = quality_id

        # Types 6 & 7 — Episode & Season
        se_opts = self._get_season_episode_options(meta)
        options.update(se_opts)

        return options

    # ──────────────────────────────────────────────────────────
    #  Description builder   (BBCode)
    # ──────────────────────────────────────────────────────────

    async def _build_description(self, meta: Meta) -> str:
        """Build C411-compliant BBCode description using French template.

        Template:
          (poster)
          🎬 Informations — country, genres, date, runtime, directors, actors
          📖 Synopsis — French overview from TMDB (fallback to English)
          ⚙️ Détails Techniques — resolution, codec, bitrate from mediainfo
          🔊 Langue(s) — audio languages
          💬 Sous-titre(s) — subtitle languages
          📥 Téléchargement — release name, team, total size
          Captures d'écran
        """
        parts: list[str] = []

        # ── Poster ──
        poster = meta.get('poster', '')
        if poster:
            parts.append(f"[center][img]{poster}[/img][/center]")
            parts.append("")

        # ── Fetch French TMDB data ──
        fr_overview = ''
        fr_title = ''
        try:
            fr_data = await self.tmdb_manager.get_tmdb_localized_data(
                meta, data_type='main', language='fr', append_to_response='credits'
            )
            if fr_data:
                fr_overview = str(fr_data.get('overview', '')).strip()
                fr_title = str(fr_data.get('title', '')).strip()
        except Exception:
            pass

        # ── 🎬 Informations ──
        parts.append("[b]🎬 Informations[/b]")
        parts.append("")

        # Country
        countries = meta.get('production_countries', [])
        if countries:
            country_names = [c.get('name', '') for c in countries if isinstance(c, dict) and c.get('name')]
            if country_names:
                parts.append(f"[b]Pays :[/b] {', '.join(country_names)}")
        elif meta.get('origin_country'):
            oc = meta['origin_country']
            if isinstance(oc, list):
                parts.append(f"[b]Pays :[/b] {', '.join(oc)}")
            else:
                parts.append(f"[b]Pays :[/b] {oc}")

        # Genres
        genres = meta.get('genres', '')
        if genres:
            parts.append(f"[b]Genres :[/b] {genres}")

        # Release date
        release_date = meta.get('release_date', '') or meta.get('first_air_date', '')
        year = meta.get('year', '')
        if release_date:
            parts.append(f"[b]Date de sortie :[/b] {release_date}")
        elif year:
            parts.append(f"[b]Date de sortie :[/b] {year}")

        # Runtime
        runtime = meta.get('runtime', 0)
        if runtime:
            hours = int(runtime) // 60
            mins = int(runtime) % 60
            if hours > 0:
                parts.append(f"[b]Durée :[/b] {hours}h {mins:02d}min")
            else:
                parts.append(f"[b]Durée :[/b] {mins}min")

        # Directors
        directors = meta.get('tmdb_directors', [])
        if directors:
            if isinstance(directors, list):
                dir_names = [d.get('name', d) if isinstance(d, dict) else str(d) for d in directors]
                parts.append(f"[b]Réalisateur(s) :[/b] {', '.join(dir_names)}")
            else:
                parts.append(f"[b]Réalisateur(s) :[/b] {directors}")

        # Actors (top 5)
        cast_list = meta.get('tmdb_cast', [])
        if cast_list and isinstance(cast_list, list):
            actor_names = []
            for actor in cast_list[:5]:
                if isinstance(actor, dict):
                    actor_names.append(actor.get('name', ''))
                else:
                    actor_names.append(str(actor))
            actor_names = [n for n in actor_names if n]
            if actor_names:
                parts.append(f"[b]Acteur(s) :[/b] {', '.join(actor_names)}")

        parts.append("")

        # ── 📖 Synopsis ──
        parts.append("[b]📖 Synopsis[/b]")
        parts.append("")
        synopsis = fr_overview or str(meta.get('overview', '')).strip()
        if synopsis:
            parts.append(synopsis)
        else:
            parts.append("Aucun synopsis disponible.")
        parts.append("")

        # ── ⚙️ Détails Techniques ──
        parts.append("[b]⚙️ Détails Techniques[/b]")
        parts.append("")

        resolution = meta.get('resolution', '')
        if resolution:
            parts.append(f"[b]Résolution :[/b] {resolution}")

        # Video codec from meta
        video_codec = meta.get('video_codec', '') or meta.get('video_encode', '')
        if video_codec:
            parts.append(f"[b]Codec Vidéo :[/b] {video_codec}")

        # Video bitrate from mediainfo
        mi_text = await self._get_mediainfo_text(meta)
        if mi_text:
            # Extract video bitrate
            vbr_match = re.search(r'(?:^|\n)Bit rate\s*:\s*(.+?)\s*(?:\n|$)', mi_text)
            if vbr_match:
                parts.append(f"[b]Débit vidéo :[/b] {vbr_match.group(1).strip()}")

        parts.append("")

        # ── 🔊 Langue(s) ──
        parts.append("[b]🔊 Langue(s)[/b]")
        parts.append("")
        audio_langs = self._parse_mi_audio_languages(mi_text)
        if audio_langs:
            parts.append(audio_langs)
        else:
            parts.append("Non spécifié")
        parts.append("")

        # ── 💬 Sous-titre(s) ──
        parts.append("[b]💬 Sous-titre(s)[/b]")
        parts.append("")
        sub_langs = self._parse_mi_subtitle_languages(mi_text)
        if sub_langs:
            parts.append(sub_langs)
        else:
            parts.append("Aucun")
        parts.append("")

        # ── 📥 Téléchargement ──
        parts.append("[b]📥 Téléchargement[/b]")
        parts.append("")

        release_name = meta.get('uuid', '')
        if release_name:
            parts.append(f"[b]Release :[/b] {release_name}")

        # Team / release group
        tag = meta.get('tag', '')
        if tag:
            # tag usually starts with '-'
            team = tag.lstrip('-').strip()
            if team:
                parts.append(f"[b]Team :[/b] {team}")

        # Total size from mediainfo
        size_match = re.search(r'File size\s*:\s*(.+?)\s*(?:\n|$)', mi_text) if mi_text else None
        if size_match:
            parts.append(f"[b]Poids Total :[/b] {size_match.group(1).strip()}")

        parts.append("")

        # ── Captures d'écran ──
        image_list: list[dict[str, Any]] = meta.get('image_list', [])
        if image_list:
            parts.append("[b]📸 Captures d'écran[/b]")
            img_lines: list[str] = []
            for img in image_list:
                raw = img.get('raw_url', '')
                web = img.get('web_url', '')
                if raw:
                    if web:
                        img_lines.append(f"[url={web}][img]{raw}[/img][/url]")
                    else:
                        img_lines.append(f"[img]{raw}[/img]")
            if img_lines:
                parts.append("[center]")
                parts.append("\n".join(img_lines))
                parts.append("[/center]")

        # ── UA Signature ──
        ua_sig = meta.get('ua_signature', 'Created by Upload Assistant')
        parts.append("")
        parts.append(f"[right][url=https://github.com/Audionut/Upload-Assistant][size=1]{ua_sig}[/size][/url][/right]")

        return "\n".join(parts)

    @staticmethod
    def _parse_mi_audio_languages(mi_text: str) -> str:
        """Extract audio language(s) from MediaInfo text."""
        if not mi_text:
            return ''
        langs: list[str] = []
        # Split by sections and find Audio sections
        in_audio = False
        for line in mi_text.split('\n'):
            stripped = line.strip()
            if stripped.startswith('Audio') and not stripped.startswith('Audio #'):
                in_audio = True
                continue
            if stripped.startswith('Audio #'):
                in_audio = True
                continue
            if in_audio and (stripped.startswith('Text') or stripped.startswith('Menu') or stripped == ''):
                if stripped.startswith('Text') or stripped.startswith('Menu'):
                    in_audio = False
            if in_audio and stripped.startswith('Language'):
                lang_match = re.search(r':\s*(.+)', stripped)
                if lang_match:
                    lang = lang_match.group(1).strip()
                    if lang not in langs:
                        langs.append(lang)
            if in_audio and stripped.startswith('Commercial name'):
                # also grab format info
                pass
        return ', '.join(langs) if langs else ''

    @staticmethod
    def _parse_mi_subtitle_languages(mi_text: str) -> str:
        """Extract subtitle language(s) from MediaInfo text."""
        if not mi_text:
            return ''
        langs: list[str] = []
        in_text = False
        for line in mi_text.split('\n'):
            stripped = line.strip()
            if stripped.startswith('Text') and not stripped.startswith('Text #'):
                in_text = True
                continue
            if stripped.startswith('Text #'):
                in_text = True
                continue
            if in_text and (stripped.startswith('Menu') or (stripped.startswith('Audio') and not stripped.startswith('Audio '))):
                in_text = False
            if in_text and stripped.startswith('Language'):
                lang_match = re.search(r':\s*(.+)', stripped)
                if lang_match:
                    lang = lang_match.group(1).strip()
                    if lang not in langs:
                        langs.append(lang)
        return ', '.join(langs) if langs else ''

    async def _get_mediainfo_text(self, meta: Meta) -> str:
        """Read MediaInfo text from temp files."""
        base = os.path.join(meta.get('base_dir', ''), 'tmp', meta.get('uuid', ''))

        # Prefer clean-path, then standard mediainfo
        for fname in ('MEDIAINFO_CLEANPATH.txt', 'MEDIAINFO.txt'):
            fpath = os.path.join(base, fname)
            if os.path.exists(fpath):
                async with aiofiles.open(fpath, encoding='utf-8') as f:
                    content = await f.read()
                    if content.strip():
                        return content

        # BDInfo for disc releases
        if meta.get('bdinfo') is not None:
            bd_path = os.path.join(base, 'BD_SUMMARY_00.txt')
            if os.path.exists(bd_path):
                async with aiofiles.open(bd_path, encoding='utf-8') as f:
                    return await f.read()

        return ''

    def _build_tmdb_data(self, meta: Meta) -> Union[str, None]:
        """Build tmdbData JSON string from meta, or None if unavailable."""
        tmdb_id = meta.get('tmdb')
        if not tmdb_id:
            return None

        tmdb_data: dict[str, Any] = {'id': int(tmdb_id)}

        if meta.get('title'):
            tmdb_data['title'] = meta['title']
        if meta.get('overview'):
            tmdb_data['overview'] = meta['overview']
        if meta.get('poster'):
            tmdb_data['poster_path'] = meta['poster']
        if meta.get('year'):
            tmdb_data['release_date'] = str(meta['year'])
        if meta.get('original_language'):
            tmdb_data['original_language'] = meta['original_language']

        return json.dumps(tmdb_data, ensure_ascii=False)

    # ──────────────────────────────────────────────────────────
    #  NFO generation
    # ──────────────────────────────────────────────────────────

    async def _get_or_generate_nfo(self, meta: Meta) -> Union[str, None]:
        """Get existing NFO path or generate one from MediaInfo.

        C411 requires an NFO file for every upload.
        """
        base = os.path.join(meta['base_dir'], 'tmp', meta['uuid'])

        # Check for existing .nfo
        existing = glob.glob(os.path.join(base, '*.nfo'))
        if existing:
            return existing[0]

        # Generate from MediaInfo
        nfo_gen = SceneNfoGenerator(self.config)
        nfo_path = await nfo_gen.generate_nfo(meta, self.tracker)
        return nfo_path

    # ──────────────────────────────────────────────────────────
    #  Upload / Search interface
    # ──────────────────────────────────────────────────────────

    async def upload(self, meta: Meta, _disctype: str) -> bool:
        """Upload torrent to c411.org.

        POST https://c411.org/api/torrents
          Authorization: Bearer <api_key>
          Content-Type:  multipart/form-data

        Required fields: torrent, nfo, title, description, categoryId, subcategoryId
        Optional fields: options, uploaderNote, tmdbData, rawgData
        """
        common = COMMON(config=self.config)
        await common.create_torrent_for_upload(meta, self.tracker, self.source_flag)

        # ── Build release name ──
        name_result = await self.get_name(meta)
        title = name_result.get('name', '') if isinstance(name_result, dict) else str(name_result)

        # ── Language tag (for options) ──
        language_tag = await self._build_audio_string(meta)

        # ── Read torrent file ──
        torrent_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}].torrent"
        async with aiofiles.open(torrent_path, 'rb') as f:
            torrent_bytes = await f.read()

        # ── NFO file (required by C411) ──
        nfo_path = await self._get_or_generate_nfo(meta)
        nfo_bytes = b''
        if nfo_path and os.path.exists(nfo_path):
            async with aiofiles.open(nfo_path, 'rb') as f:
                nfo_bytes = await f.read()
        else:
            console.print("[yellow]C411: No NFO available — upload may be rejected[/yellow]")

        # ── Description ──
        description = await self._build_description(meta)

        # ── Category / Subcategory ──
        cat_id, subcat_id = self._get_category_subcategory(meta)

        # ── Options JSON ──
        options = self._build_options(meta, language_tag)
        options_json = json.dumps(options, ensure_ascii=False)

        # ── TMDB data ──
        tmdb_data = self._build_tmdb_data(meta)

        # ── Multipart form ──
        files: dict[str, tuple[str, bytes, str]] = {
            'torrent': ('torrent.torrent', torrent_bytes, 'application/x-bittorrent'),
            'nfo': ('release.nfo', nfo_bytes, 'application/octet-stream'),
        }

        data: dict[str, Any] = {
            'title': title,
            'description': description,
            'categoryId': str(cat_id),
            'subcategoryId': str(subcat_id),
            'options': options_json,
        }

        if tmdb_data:
            data['tmdbData'] = tmdb_data

        headers: dict[str, str] = {
            'Authorization': f'Bearer {self.api_key}',
            'Accept': 'application/json',
        }

        try:
            if not meta['debug']:
                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.post(
                        url=self.upload_url,
                        files=files,
                        data=data,
                        headers=headers,
                    )
                    if response.status_code in (200, 201):
                        try:
                            response_data = response.json()
                            # Extract torrent_id for the standard URL output
                            torrent_id = None
                            if isinstance(response_data, dict):
                                data_block = response_data.get('data', {})
                                if isinstance(data_block, dict):
                                    torrent_id = data_block.get('id') or data_block.get('slug') or data_block.get('infoHash')
                            if torrent_id:
                                meta['tracker_status'][self.tracker]['torrent_id'] = torrent_id
                            meta['tracker_status'][self.tracker]['status_message'] = response_data
                            return True
                        except json.JSONDecodeError:
                            meta['tracker_status'][self.tracker]['status_message'] = (
                                "data error: C411 JSON decode error"
                            )
                            return False
                    else:
                        error_detail: Any = ''
                        try:
                            error_detail = response.json()
                        except Exception:
                            error_detail = response.text[:500]
                        meta['tracker_status'][self.tracker]['status_message'] = {
                            'error': f'HTTP {response.status_code}',
                            'detail': error_detail,
                        }
                        console.print(f"[red]C411 upload failed: HTTP {response.status_code}[/red]")
                        if error_detail:
                            console.print(f"[dim]{error_detail}[/dim]")
                        return False
            else:
                # ── Debug mode — save description & show summary ──
                desc_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}]DESCRIPTION.txt"
                async with aiofiles.open(desc_path, 'w', encoding='utf-8') as f:
                    await f.write(description)
                console.print(f"DEBUG: Saving final description to {desc_path}")
                console.print("[cyan]C411 Debug — Request data:[/cyan]")
                console.print(f"  Title:       {title}")
                console.print(f"  Category:    {cat_id} / Sub: {subcat_id}")
                console.print(f"  Language:    {language_tag}")
                console.print(f"  Options:     {options_json}")
                console.print(f"  Description: {description[:500]}…")
                meta['tracker_status'][self.tracker]['status_message'] = "Debug mode, not uploaded."
                await common.create_torrent_for_upload(
                    meta, f"{self.tracker}_DEBUG", f"{self.tracker}_DEBUG",
                    announce_url="https://fake.tracker",
                )
                return True

        except Exception as e:
            meta['tracker_status'][self.tracker]['status_message'] = f"data error: Upload failed: {e}"
            console.print(f"[red]C411 upload error: {e}[/red]")
            return False

    async def search_existing(self, meta: Meta, _disctype: str) -> list[dict[str, Any]]:
        """Search for existing torrents on C411 via its Torznab API.

        Torznab endpoint: GET https://c411.org/api?t=search&q=QUERY&apikey=KEY
        Also supports:    ?t=movie&imdbid=IMDBID  and  ?t=tvsearch&q=QUERY
        Response format:  RSS/XML with <item> elements.
        """
        dupes: list[dict[str, Any]] = []

        if not self.api_key:
            console.print("[yellow]C411: No API key configured, skipping dupe check.[/yellow]")
            return []

        # Build search queries — use IMDB for movies, title+year for everything
        queries: list[dict[str, str]] = []

        imdb_id = meta.get('imdb_id', 0)
        title = meta.get('title', '')
        year = meta.get('year', '')
        category = meta.get('category', '')

        # Primary: IMDB search for movies
        if imdb_id and int(imdb_id) > 0 and category == 'MOVIE':
            imdb_str = f"tt{str(imdb_id).zfill(7)}"
            queries.append({'t': 'movie', 'imdbid': imdb_str})

        # Secondary: text search with title + year
        search_term = f"{title} {year}".strip()
        if search_term:
            if category == 'TV':
                queries.append({'t': 'tvsearch', 'q': search_term})
            else:
                queries.append({'t': 'search', 'q': search_term})

        if not queries:
            return []

        seen_guids: set[str] = set()

        for params in queries:
            try:
                url_params = {**params, 'apikey': self.api_key}
                async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                    response = await client.get('https://c411.org/api', params=url_params)

                if response.status_code != 200:
                    if meta.get('debug'):
                        console.print(f"[yellow]C411 Torznab search returned HTTP {response.status_code}[/yellow]")
                    continue

                # Parse XML response
                items = self._parse_torznab_response(response.text)

                for item in items:
                    guid = item.get('guid', item.get('name', ''))
                    if guid in seen_guids:
                        continue
                    seen_guids.add(guid)
                    dupes.append(item)

            except Exception as e:
                if meta.get('debug'):
                    console.print(f"[yellow]C411 Torznab search error: {e}[/yellow]")
                continue

        if meta.get('debug'):
            console.print(f"[cyan]C411 dupe search found {len(dupes)} result(s)[/cyan]")

        return dupes

    @staticmethod
    def _parse_torznab_response(xml_text: str) -> list[dict[str, Any]]:
        """Parse a Torznab XML response into a list of DupeEntry-compatible dicts."""
        results: list[dict[str, Any]] = []

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return results

        # Torznab namespace for <torznab:attr>
        ns = {'torznab': 'http://torznab.com/schemas/2015/feed'}

        # Items can be at /rss/channel/item or just /channel/item
        items = root.findall('.//item')

        for item in items:
            name = ''
            title_el = item.find('title')
            if title_el is not None and title_el.text:
                name = title_el.text.strip()

            size_val = 0
            size_el = item.find('size')
            if size_el is not None and size_el.text:
                try:
                    size_val = int(size_el.text)
                except (ValueError, TypeError):
                    pass

            link = ''
            link_el = item.find('link')
            if link_el is not None and link_el.text:
                link = link_el.text.strip()
            # Fallback to comments or guid for URL
            if not link:
                comments_el = item.find('comments')
                if comments_el is not None and comments_el.text:
                    link = comments_el.text.strip()
            if not link:
                guid_el = item.find('guid')
                if guid_el is not None and guid_el.text:
                    link = guid_el.text.strip()

            guid = ''
            guid_el = item.find('guid')
            if guid_el is not None and guid_el.text:
                guid = guid_el.text.strip()

            # Extract torznab attributes (resolution, category, files, etc.)
            files_count = 0
            resolution = ''
            for attr in item.findall('torznab:attr', ns):
                attr_name = attr.get('name', '')
                attr_value = attr.get('value', '')
                if attr_name == 'files':
                    try:
                        files_count = int(attr_value)
                    except (ValueError, TypeError):
                        pass
                elif attr_name == 'resolution':
                    resolution = attr_value

            if name:
                results.append({
                    'name': name,
                    'size': size_val if size_val else None,
                    'link': link or None,
                    'id': guid or None,
                    'file_count': files_count,
                    'res': resolution or None,
                    'files': [],
                    'trumpable': False,
                    'internal': False,
                    'flags': [],
                    'type': None,
                    'bd_info': None,
                    'description': None,
                    'download': None,
                })

        return results

    async def edit_desc(self, _meta: Meta) -> None:
        """No-op — C411 descriptions are built in upload()."""
        return
