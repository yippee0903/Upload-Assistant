# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
"""GF – generation-free.org (UNIT3D, French private tracker)."""

import re
from typing import Any

from src.console import console
from src.nfo_generator import SceneNfoGenerator
from src.trackers.COMMON import COMMON
from src.trackers.FRENCH import FrenchTrackerMixin
from src.trackers.UNIT3D import UNIT3D


class GF(FrenchTrackerMixin, UNIT3D):
    """Tracker class for generation-free.org (GF-FREE).

    GF uses a content/language-aware *type* system that differs from
    the standard UNIT3D layout.  The ``get_type_id`` method maps UA's
    internal type + language tag to the right GF type ID.

    Categories
    ----------
    1   Films
    2   Séries
    3   Ebook
    4   Jeux
    5   Logiciel
    6   Musique

    Types (video-relevant)
    ----------------------
    2   4K              – 2160p Remux / DISC
    3   Documentaire
    6   Film ISO        – DISC (DVD ISO)
    7   Film X
    8   HD              – 1080p encode
    9   HDlight X264    – 720p encode x264
    10  HDlight X265    – 720p encode x265
    11  Remux           – 1080p Remux
    12  SD              – SD encode / DVDRip
    13  Spectacle
    14  VOSTFR          – any VOSTFR release
    15  VO              – any VO release
    16  WEB             – WEB-DL / WEBRip
    41  AV1
    42  4KLight         – 2160p encode

    Resolutions
    -----------
    1   4320p
    2   2160p
    3   1080p
    4   1080i
    5   720p
    10  Other
    """

    def __init__(self, config: dict[str, Any]):
        super().__init__(config, tracker_name='GF')
        self.config = config
        self.common = COMMON(config)
        self.tracker = 'GF'
        self.base_url = 'https://generation-free.org'
        self.id_url = f'{self.base_url}/api/torrents/'
        self.upload_url = f'{self.base_url}/api/torrents/upload'
        self.requests_url = f'{self.base_url}/api/requests/filter'
        self.search_url = f'{self.base_url}/api/torrents/filter'
        self.torrent_url = f'{self.base_url}/torrents/'
        self.banned_groups = ['']
        self.source_flag = 'GF'

    WEB_LABEL: str = 'WEB'

    # ──────────────────────────────────────────────────────────
    #  Category / Type / Resolution mappings
    # ──────────────────────────────────────────────────────────

    async def get_category_id(
        self,
        meta: dict[str, Any],
        category: str = '',
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        category_id = {
            'MOVIE': '1',
            'TV': '2',
        }
        if mapping_only:
            return category_id
        if reverse:
            return {v: k for k, v in category_id.items()}
        if category:
            return {'category_id': category_id.get(category, '0')}
        return {'category_id': category_id.get(meta.get('category', ''), '0')}

    async def get_type_id(
        self,
        meta: dict[str, Any],
        type: str = '',
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        """Map UA type + context to GF-specific type IDs.

        GF has a language/content-aware type system:
        - VOSTFR and VO releases get their own type regardless of format
        - Encodes at different resolutions map to HD / HDlight / SD / 4KLight
        - WEB-DL and WEBRip both map to WEB (16)
        - Remux splits by resolution: 2160p→4K (2), else→Remux (11)
        - AV1 codec gets its own type (41)
        """
        type_map = {
            'DISC': '6',          # Film ISO
            'REMUX': '11',        # Remux (default, overridden for 2160p below)
            'ENCODE': '8',        # HD (default, overridden by resolution below)
            'WEBDL': '16',        # WEB
            'WEBRIP': '16',       # WEB
            'HDTV': '8',          # HD
        }
        if mapping_only:
            return type_map
        if reverse:
            return {v: k for k, v in type_map.items()}

        meta_type = type or meta.get('type', '')
        resolution = meta.get('resolution', '')
        video_encode = meta.get('video_encode', '')

        # Language-based types take priority
        language_tag = await self._build_audio_string(meta)
        if language_tag == 'VOSTFR':
            return {'type_id': '14'}
        if language_tag == 'VO':
            return {'type_id': '15'}

        # AV1 codec → dedicated type
        if 'AV1' in video_encode.upper():
            return {'type_id': '41'}

        # DISC (ISO)
        if meta_type == 'DISC':
            if meta.get('is_disc') == 'BDMV':
                # BluRay disc → treat as 4K or Remux depending on resolution
                if resolution in ('2160p', '4320p'):
                    return {'type_id': '2'}    # 4K
                return {'type_id': '11'}       # Remux
            return {'type_id': '6'}            # Film ISO (DVD)

        # Remux: 2160p → 4K (2), else → Remux (11)
        if meta_type == 'REMUX':
            if resolution in ('2160p', '4320p'):
                return {'type_id': '2'}        # 4K
            return {'type_id': '11'}           # Remux

        # WEB-DL / WEBRip
        if meta_type in ('WEBDL', 'WEBRIP'):
            return {'type_id': '16'}           # WEB

        # Encode / HDTV – resolution-dependent
        if meta_type in ('ENCODE', 'HDTV'):
            if resolution in ('2160p', '4320p'):
                return {'type_id': '42'}       # 4KLight
            if resolution == '1080p':
                return {'type_id': '8'}        # HD
            if resolution in ('720p',):
                if 'x265' in video_encode.lower() or 'hevc' in video_encode.lower():
                    return {'type_id': '10'}   # HDlight X265
                return {'type_id': '9'}        # HDlight X264
            # SD (480p, 576p, etc.)
            return {'type_id': '12'}           # SD

        return {'type_id': type_map.get(meta_type, '0')}

    async def get_resolution_id(
        self,
        meta: dict[str, Any],
        resolution: str = '',
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        resolution_id = {
            '4320p': '1',
            '2160p': '2',
            '1080p': '3',
            '1080i': '4',
            '720p': '5',
        }
        if mapping_only:
            return resolution_id
        if reverse:
            return {v: k for k, v in resolution_id.items()}
        if resolution:
            return {'resolution_id': resolution_id.get(resolution, '10')}
        return {'resolution_id': resolution_id.get(meta.get('resolution', ''), '10')}

    # ──────────────────────────────────────────────────────────
    #  Additional checks (language requirement + NFO)
    # ──────────────────────────────────────────────────────────

    async def get_additional_checks(self, meta: dict[str, Any]) -> bool:
        """Enforce French language requirements and auto-generate NFO."""
        french_languages = ['french', 'fre', 'fra', 'fr', 'français', 'francais', 'fr-fr', 'fr-ca']

        if not await self.common.check_language_requirements(
            meta,
            self.tracker,
            languages_to_check=french_languages,
            check_audio=True,
            check_subtitle=True,
            require_both=False,
        ):
            console.print(f'[bold red]Language requirements not met for {self.tracker}.[/bold red]')
            return False

        # Auto-generate NFO if not provided (GF requires NFO for VOSTFR & multi)
        if not meta.get('nfo') and not meta.get('auto_nfo'):
            generator = SceneNfoGenerator(self.config)
            nfo_path = await generator.generate_nfo(meta, self.tracker)
            if nfo_path:
                meta['nfo'] = nfo_path
                meta['auto_nfo'] = True

        return True

    # ──────────────────────────────────────────────────────────
    #  Audio tag (inherited pattern)
    # ──────────────────────────────────────────────────────────

    async def _build_audio_string(self, meta: dict[str, Any]) -> str:
        """Build the language tag following GF conventions.

        Tags: MUTE, MULTi [VFF|VFQ|VF2], FRENCH [VFQ], VOSTFR, VO
        """
        if 'mediainfo' not in meta or 'media' not in meta.get('mediainfo', {}):
            return ''

        audio_tracks = self._get_audio_tracks(meta)

        if not audio_tracks:
            return 'MUTE'

        audio_langs = self._extract_audio_languages(audio_tracks, meta)
        if not audio_langs:
            return ''

        has_french_audio = 'FRA' in audio_langs
        has_french_subs = self._has_french_subs(meta)
        num_audio_tracks = len(audio_tracks)
        fr_suffix = self._get_french_dub_suffix(audio_tracks)

        # MULTi – 2+ audio tracks with at least 1 French
        if num_audio_tracks >= 2 and has_french_audio:
            if fr_suffix:
                return f'MULTi {fr_suffix}'
            return 'MULTi'

        # FRENCH – 1 audio track, it's French
        if num_audio_tracks == 1 and has_french_audio:
            if fr_suffix == 'VFQ':
                return 'FRENCH VFQ'
            return 'FRENCH'

        # VOSTFR – No French audio but French subtitles present
        if not has_french_audio and has_french_subs:
            return 'VOSTFR'

        # VO – No French content at all
        if not has_french_audio and not has_french_subs:
            return 'VO'

        return ''

    # ──────────────────────────────────────────────────────────
    #  Release name (GF naming conventions)
    # ──────────────────────────────────────────────────────────

    async def get_name(self, meta: dict[str, Any]) -> dict[str, str]:
        """Build GF-compliant dot-separated release name.

        Structure (films):
            TITRE.ANNÉE.TAG.LANGUE.HDR.RÉSOLUTION.SOURCE.CODEC_VIDEO.CODEC_AUDIO-TEAM

        Structure (series):
            TITRE.ANNÉE?.SxxExx.TAG.LANGUE.HDR.RÉSOLUTION.SOURCE.CODEC_VIDEO.CODEC_AUDIO-TEAM

        Rules from https://generation-free.org/forums/33:
        - No accents, brackets, underscores, quotes
        - LANGUE: FRENCH / VOSTFR / MULTi / SUBFRENCH (uppercase)
        - SOURCE: WEBRiP, DVDRiP, BluRay, WEB…
        - Codec video: x264 / x265
        - Codec audio: AAC / AC3 / FLAC / DTS
        - Team: -Name or -NoTag
        """

        def _clean(text: str) -> str:
            """Strip non-alphanumeric chars except spaces, dots, hyphens, and +."""
            return re.sub(r'[^a-zA-Z0-9 .+\-]', '', text)

        meta_type = meta.get('type', '').upper()
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

        if meta.get('is_disc', '') == 'BDMV':
            video_codec = meta.get('video_codec', '')
            region = meta.get('region', '') or ''
        elif meta.get('is_disc', '') == 'DVD':
            region = meta.get('region', '') or ''
            dvd_size = meta.get('dvd_size', '')
        else:
            video_codec = meta.get('video_codec', '')
            video_encode = meta.get('video_encode', '')

        # TV-specific year handling
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

        if meta['category'] == 'MOVIE':
            if meta_type == 'DISC':
                if meta['is_disc'] == 'BDMV':
                    name = f"{title} {year} {three_d} {edition} {hybrid} {repack} {language} {resolution} {region} {uhd} {source} {hdr} {video_codec} {audio}"
                elif meta['is_disc'] == 'DVD':
                    name = f"{title} {year} {repack} {edition} {region} {source} {dvd_size} {audio}"
                elif meta['is_disc'] == 'HDDVD':
                    name = f"{title} {year} {edition} {repack} {language} {resolution} {source} {video_codec} {audio}"
            elif meta_type == 'REMUX' and source in ('BluRay', 'HDDVD'):
                name = f"{title} {year} {three_d} {edition} {hybrid} {repack} {language} {resolution} {uhd} {source} REMUX {hdr} {video_codec} {audio}"
            elif meta_type == 'REMUX' and source in ('PAL DVD', 'NTSC DVD', 'DVD'):
                name = f"{title} {year} {edition} {repack} {source} REMUX {audio}"
            elif meta_type == 'ENCODE':
                name = f"{title} {year} {edition} {hybrid} {repack} {language} {resolution} {uhd} {source} {audio} {hdr} {video_encode}"
            elif meta_type == 'WEBDL':
                name = f"{title} {year} {edition} {hybrid} {repack} {language} {resolution} {uhd} {service} {self.WEB_LABEL} {audio} {hdr} {video_encode}"
            elif meta_type == 'WEBRIP':
                name = f"{title} {year} {edition} {hybrid} {repack} {language} {resolution} {uhd} {service} WEBRip {audio} {hdr} {video_encode}"
            elif meta_type == 'HDTV':
                name = f"{title} {year} {edition} {repack} {language} {resolution} {source} {audio} {video_encode}"
            elif meta_type == 'DVDRIP':
                name = f"{title} {year} {source} {video_encode} DVDRip {audio}"

        elif meta['category'] == 'TV':
            if meta_type == 'DISC':
                if meta['is_disc'] == 'BDMV':
                    name = f"{title} {year} {season}{episode} {three_d} {edition} {hybrid} {repack} {language} {resolution} {region} {uhd} {source} {hdr} {video_codec} {audio}"
                elif meta['is_disc'] == 'DVD':
                    name = f"{title} {year} {season}{episode} {three_d} {repack} {edition} {region} {source} {dvd_size} {audio}"
                elif meta['is_disc'] == 'HDDVD':
                    name = f"{title} {year} {edition} {repack} {language} {resolution} {source} {video_codec} {audio}"
            elif meta_type == 'REMUX' and source in ('BluRay', 'HDDVD'):
                name = f"{title} {year} {season}{episode} {part} {three_d} {edition} {hybrid} {repack} {language} {resolution} {uhd} {source} REMUX {hdr} {video_codec} {audio}"
            elif meta_type == 'REMUX' and source in ('PAL DVD', 'NTSC DVD', 'DVD'):
                name = f"{title} {year} {season}{episode} {part} {edition} {repack} {source} REMUX {audio}"
            elif meta_type == 'ENCODE':
                name = f"{title} {year} {season}{episode} {part} {edition} {hybrid} {repack} {language} {resolution} {uhd} {source} {audio} {hdr} {video_encode}"
            elif meta_type == 'WEBDL':
                name = f"{title} {year} {season}{episode} {part} {edition} {hybrid} {repack} {language} {resolution} {uhd} {service} {self.WEB_LABEL} {audio} {hdr} {video_encode}"
            elif meta_type == 'WEBRIP':
                name = f"{title} {year} {season}{episode} {part} {edition} {hybrid} {repack} {language} {resolution} {uhd} {service} WEBRip {audio} {hdr} {video_encode}"
            elif meta_type == 'HDTV':
                name = f"{title} {year} {season}{episode} {part} {edition} {repack} {language} {resolution} {source} {audio} {video_encode}"
            elif meta_type == 'DVDRIP':
                name = f"{title} {year} {season} {source} DVDRip {audio} {video_encode}"

        if not name:
            console.print('[bold red]Unable to generate name for GF. Check --category / --type / --source.[/bold red]')
            return {'name': ''}

        name = ' '.join(name.split())
        name_notag = name
        name = name_notag + tag

        clean_name = _clean(name)
        dot_name = clean_name.replace(' ', '.')
        # Remove isolated hyphens between dots (e.g. "Chainsaw.Man.-.The.Movie")
        dot_name = re.sub(r'\.(-\.)+', '.', dot_name)
        # Collapse consecutive dots and strip boundary dots
        dot_name = re.sub(r'\.{2,}', '.', dot_name)
        dot_name = dot_name.strip('.')

        return {'name': dot_name}
