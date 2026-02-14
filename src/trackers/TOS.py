# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
# import discord
import asyncio
from typing import Any, Optional

from src.console import console
from src.torrentcreate import TorrentCreator
from src.trackers.COMMON import COMMON
from src.trackers.UNIT3D import UNIT3D


class TOS(UNIT3D):

    def __init__(self, config: dict[str, Any]):
        super().__init__(config, tracker_name="TOS")
        self.config = config
        self.common = COMMON(config)
        self.tracker = "TOS"
        self.source_flag = "TheOldSchool"
        self.base_url = "https://theoldschool.cc"
        self.id_url = f"{self.base_url}/api/torrents/"
        self.upload_url = f"{self.base_url}/api/torrents/upload"
        self.search_url = f"{self.base_url}/api/torrents/filter"
        self.torrent_url = f"{self.base_url}/torrents/"
        self.banned_groups = [
            "FL3ER",
            "SUNS3T",
            "WoLFHD",
            "EXTREME",
            "Slay3R",
            "3T3AM",
            "BARBiE",
        ]
        pass

    async def get_category_id(
        self,
        meta: dict[str, Any],
        category: Optional[str] = None,
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        _ = (category, reverse, mapping_only)
        language_tag = await self._build_audio_string(meta)
        if language_tag == "VOSTFR":
            category_id = "9" if meta["category"] == "TV" and meta.get("tv_pack") else {"MOVIE": "6", "TV": "7"}.get(meta["category"], "0")
        else:
            category_id = "8" if meta["category"] == "TV" and meta.get("tv_pack") else {"MOVIE": "1", "TV": "2"}.get(meta["category"], "0")
        return {"category_id": category_id}

    async def get_type_id(
        self,
        meta: dict[str, Any],
        type: Optional[str] = None,
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        _ = (type, reverse, mapping_only)
        if meta["is_disc"] == "DVD":
            type_id = "7"
        elif meta.get("3D") == "3D":
            type_id = "8"
        else:
            type_id = {
                "DISC": "1",
                "REMUX": "2",
                "ENCODE": "3",
                "WEBDL": "4",
                "WEBRIP": "5",
                "HDTV": "6",
            }.get(meta["type"], "0")
        return {"type_id": type_id}

    async def get_name(self, meta: dict[str, Any]) -> dict[str, str]:
        """Build TOS-compliant dot-separated release name.

        Same layout as G3MINI but with video codec before audio codec:
            …LANGUE.Resolution.Source[.HDR.VideoCodec].AudioCodec.Channels[.Object]-TEAM
        """
        import re

        is_scene = meta.get("scene", False)
        if is_scene:
            return {"name": str(meta.get("scene_name", ""))}

        type_val = meta.get('type', '').upper()
        title = meta.get('title', '')
        year = str(meta.get('year', ''))
        manual_year = meta.get('manual_year')
        if manual_year is not None and int(manual_year) > 0:
            year = str(manual_year)

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
        edition = meta.get('edition', '')
        hybrid = 'Hybrid' if meta.get('webdv', '') else ''
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

        # ── MOVIE ──
        # G3MINI order with video/audio swapped:
        #   Disc/Remux: … Source HDR VideoCodec Audio
        #   Encode:     … Source HDR VideoEncode Audio
        #   WEB-DL:     … Service WEB-DL HDR VideoEncode Audio
        if meta['category'] == 'MOVIE':
            if type_val == 'DISC':
                if meta.get('is_disc') == 'BDMV':
                    name = f"{title} {year} {three_d} {edition} {hybrid} {repack} {language} {resolution} {region} {uhd} {source} {hdr} {video_codec} {audio}"
                elif meta.get('is_disc') == 'DVD':
                    name = f"{title} {year} {repack} {edition} {region} {source} {dvd_size} {audio}"
                elif meta.get('is_disc') == 'HDDVD':
                    name = f"{title} {year} {edition} {repack} {language} {resolution} {source} {video_codec} {audio}"
            elif type_val == 'REMUX' and source in ('BluRay', 'HDDVD'):
                name = f"{title} {year} {three_d} {edition} {hybrid} {repack} {language} {resolution} {uhd} {source} REMUX {hdr} {video_codec} {audio}"
            elif type_val == 'REMUX' and source in ('PAL DVD', 'NTSC DVD', 'DVD'):
                name = f"{title} {year} {edition} {repack} {source} REMUX {audio}"
            elif type_val == 'ENCODE':
                name = f"{title} {year} {edition} {hybrid} {repack} {language} {resolution} {uhd} {source} {hdr} {video_encode} {audio}"
            elif type_val == 'WEBDL':
                name = f"{title} {year} {edition} {hybrid} {repack} {language} {resolution} {uhd} {service} WEB-DL {hdr} {video_encode} {audio}"
            elif type_val == 'WEBRIP':
                name = f"{title} {year} {edition} {hybrid} {repack} {language} {resolution} {uhd} {service} WEBRip {hdr} {video_encode} {audio}"
            elif type_val == 'HDTV':
                name = f"{title} {year} {edition} {repack} {language} {resolution} {source} {video_encode} {audio}"
            elif type_val == 'DVDRIP':
                name = f"{title} {year} {source} {video_encode} DVDRip {audio}"

        # ── TV ──
        elif meta['category'] == 'TV':
            if type_val == 'DISC':
                if meta.get('is_disc') == 'BDMV':
                    name = f"{title} {year} {season}{episode} {three_d} {edition} {hybrid} {repack} {language} {resolution} {region} {uhd} {source} {hdr} {video_codec} {audio}"
                elif meta.get('is_disc') == 'DVD':
                    name = f"{title} {year} {season}{episode} {repack} {edition} {region} {source} {dvd_size} {audio}"
                elif meta.get('is_disc') == 'HDDVD':
                    name = f"{title} {year} {edition} {repack} {language} {resolution} {source} {video_codec} {audio}"
            elif type_val == 'REMUX' and source in ('BluRay', 'HDDVD'):
                name = f"{title} {year} {season}{episode} {part} {three_d} {edition} {hybrid} {repack} {language} {resolution} {uhd} {source} REMUX {hdr} {video_codec} {audio}"
            elif type_val == 'REMUX' and source in ('PAL DVD', 'NTSC DVD', 'DVD'):
                name = f"{title} {year} {season}{episode} {part} {edition} {repack} {source} REMUX {audio}"
            elif type_val == 'ENCODE':
                name = f"{title} {year} {season}{episode} {part} {edition} {hybrid} {repack} {language} {resolution} {uhd} {source} {hdr} {video_encode} {audio}"
            elif type_val == 'WEBDL':
                name = f"{title} {year} {season}{episode} {part} {edition} {hybrid} {repack} {language} {resolution} {uhd} {service} WEB-DL {hdr} {video_encode} {audio}"
            elif type_val == 'WEBRIP':
                name = f"{title} {year} {season}{episode} {part} {edition} {hybrid} {repack} {language} {resolution} {uhd} {service} WEBRip {hdr} {video_encode} {audio}"
            elif type_val == 'HDTV':
                name = f"{title} {year} {season}{episode} {part} {edition} {repack} {language} {resolution} {source} {video_encode} {audio}"
            elif type_val == 'DVDRIP':
                name = f"{title} {year} {season} {source} DVDRip {video_encode} {audio}"

        if not name:
            console.print("[bold red]TOS: Unable to generate release name.[/bold red]")
            console.print(f"  category={meta.get('category')}  type={meta.get('type')}  source={meta.get('source')}")
            return {'name': ''}

        # Collapse whitespace, append tag, dotify, clean
        name = ' '.join(name.split()) + tag
        # Normalise special codec notations before stripping
        name = name.replace('DTS:X', 'DTS-X')
        # Allow alphanumeric, spaces, dots, hyphens, colons, and + (for DD+, HDR10+)
        name = re.sub(r'[^a-zA-Z0-9 .+\-]', '', name)
        name = name.replace(' ', '.')
        name = re.sub(r'\.(-\.)+', '.', name)
        name = re.sub(r'\.{2,}', '.', name)
        name = name.strip('.')

        # Recreate torrent if keep_nfo is set
        if meta.get('keep_nfo', False):
            tracker_config = self.config['TRACKERS'].get(self.tracker, {})
            tracker_url = str(tracker_config.get('announce_url', "https://fake.tracker")).strip()
            torrent_create = f"[{self.tracker}]"
            try:
                cooldown = int(self.config.get('DEFAULT', {}).get('rehash_cooldown', 0) or 0)
            except (ValueError, TypeError):
                cooldown = 0
            if cooldown > 0:
                await asyncio.sleep(cooldown)
            await TorrentCreator.create_torrent(meta, str(meta['path']), torrent_create, tracker_url=tracker_url)

        return {"name": name}

    async def get_additional_checks(self, meta: dict[str, Any]) -> bool:
        # Check language requirements: must be French audio OR original audio with French subtitles
        french_languages = ["french", "fre", "fra", "fr", "français", "francais"]
        if not await self.common.check_language_requirements(
            meta,
            self.tracker,
            languages_to_check=french_languages,
            check_audio=True,
            check_subtitle=True,
            require_both=False,
            original_language=True,
        ):
            console.print(f"[bold red]Language requirements not met for {self.tracker}.[/bold red]")
            return False

        # Check if it's a Scene release without NFO - TOS requires NFO for Scene releases
        is_scene = meta.get("scene", False)
        has_nfo = meta.get("nfo", False) or meta.get("auto_nfo", False)

        if is_scene and not has_nfo:
            console.print(
                f"[red]{self.tracker}: Scene release detected but no NFO file found. TOS requires NFO files for Scene releases.[/red]"
            )
            return False

        return True

    async def _build_audio_string(self, meta):
        """Build the language tag following French tracker conventions.

        Tags: MUTE, MULTi [VFF|VFQ|VF2|VFn], FRENCH [VFQ], VOSTFR, VO
        """
        # No mediainfo available - can't determine language
        if 'mediainfo' not in meta or 'media' not in meta.get('mediainfo', {}):
            return ''

        audio_tracks = self._get_audio_tracks(meta)

        # MUTE - mediainfo present but no audio tracks
        if not audio_tracks:
            return 'MUTE'

        audio_langs = self._extract_audio_languages(audio_tracks, meta)
        if not audio_langs:
            return ''

        has_french_audio = 'FRA' in audio_langs
        has_french_subs = self._has_french_subs(meta)
        num_audio_tracks = len(audio_tracks)
        fr_suffix = self._get_french_dub_suffix(audio_tracks)

        # MULTi - 2+ audio tracks with at least 1 French
        if num_audio_tracks >= 2 and has_french_audio:
            if fr_suffix:
                return f"MULTi {fr_suffix}"
            return "MULTi"

        # FRENCH - 1 audio track, it's French
        if num_audio_tracks == 1 and has_french_audio:
            # Only append VFQ suffix; VFF or generic fr -> just FRENCH
            if fr_suffix == 'VFQ':
                return "FRENCH VFQ"
            return "FRENCH"

        # VOSTFR - No French audio but French subtitles present
        if not has_french_audio and has_french_subs:
            return "VOSTFR"

        # VO - No French content at all
        if not has_french_audio and not has_french_subs:
            return "VO"

        return ''

    def _get_french_dub_suffix(self, audio_tracks):
        """Determine French dub suffix from audio track languages.

        Returns: 'VFF', 'VFQ', 'VF2', 'VFn' (n>2), or None.
        """
        fr_variants = []

        for track in audio_tracks:
            lang = track.get('Language', '')
            if isinstance(lang, str):
                lang_lower = lang.lower().strip()
                if lang_lower == 'fr-fr' and 'fr-fr' not in fr_variants:
                    fr_variants.append('fr-fr')
                elif lang_lower == 'fr-ca' and 'fr-ca' not in fr_variants:
                    fr_variants.append('fr-ca')
                elif lang_lower in ('fr', 'fre', 'fra', 'french', 'français', 'francais') and 'fr' not in fr_variants:
                    fr_variants.append('fr')

        num_fr_dubs = len(fr_variants)

        if num_fr_dubs == 0:
            return None

        if num_fr_dubs > 2:
            return f"VF{num_fr_dubs}"

        has_vff = 'fr-fr' in fr_variants
        has_vfq = 'fr-ca' in fr_variants

        if has_vff and has_vfq:
            return 'VF2'
        elif has_vfq:
            return 'VFQ'
        elif has_vff:
            return 'VFF'

        # Generic 'fr' only - no suffix needed
        return None

    def _get_audio_tracks(self, meta):
        """Extract audio tracks from mediainfo"""
        if 'mediainfo' not in meta or 'media' not in meta['mediainfo']:
            return []

        tracks = meta['mediainfo']['media'].get('track', [])
        return [t for t in tracks if t.get('@type') == 'Audio']

    def _extract_audio_languages(self, audio_tracks, meta):
        """Extract and normalize audio languages"""
        audio_langs = []

        for track in audio_tracks:
            lang = track.get('Language', '')
            if lang:
                lang_code = self._map_language(lang)
                if lang_code and lang_code not in audio_langs:
                    audio_langs.append(lang_code)

        if not audio_langs and meta.get('audio_languages'):
            for lang in meta['audio_languages']:
                lang_code = self._map_language(lang)
                if lang_code and lang_code not in audio_langs:
                    audio_langs.append(lang_code)

        return audio_langs

    def _map_language(self, lang):
        """Map language codes and names to normalized 3-letter codes"""
        if not lang:
            return ''

        lang_map = {
            'spa': 'ESP', 'es': 'ESP', 'spanish': 'ESP', 'español': 'ESP', 'castellano': 'ESP', 'es-es': 'ESP',
            'eng': 'ENG', 'en': 'ENG', 'english': 'ENG', 'en-us': 'ENG', 'en-gb': 'ENG',
            'lat': 'LAT', 'latino': 'LAT', 'latin american spanish': 'LAT', 'es-mx': 'LAT', 'es-419': 'LAT',
            'fre': 'FRA', 'fra': 'FRA', 'fr': 'FRA', 'french': 'FRA', 'français': 'FRA', 'fr-fr': 'FRA', 'fr-ca': 'FRA',
            'ger': 'ALE', 'deu': 'ALE', 'de': 'ALE', 'german': 'ALE', 'deutsch': 'ALE',
            'jpn': 'JAP', 'ja': 'JAP', 'japanese': 'JAP', '日本語': 'JAP',
            'kor': 'COR', 'ko': 'COR', 'korean': 'COR', '한국어': 'COR',
            'ita': 'ITA', 'it': 'ITA', 'italian': 'ITA', 'italiano': 'ITA',
            'por': 'POR', 'pt': 'POR', 'portuguese': 'POR', 'portuguese (iberian)': 'POR', 'português': 'POR', 'pt-br': 'POR', 'pt-pt': 'POR',
            'chi': 'CHI', 'zho': 'CHI', 'zh': 'CHI', 'chinese': 'CHI', 'mandarin': 'CHI', '中文': 'CHI', 'zh-cn': 'CHI',
            'rus': 'RUS', 'ru': 'RUS', 'russian': 'RUS', 'русский': 'RUS',
            'ara': 'ARA', 'ar': 'ARA', 'arabic': 'ARA',
            'hin': 'HIN', 'hi': 'HIN', 'hindi': 'HIN',
            'tha': 'THA', 'th': 'THA', 'thai': 'THA',
            'vie': 'VIE', 'vi': 'VIE', 'vietnamese': 'VIE',
        }

        lang_lower = str(lang).lower().strip()
        mapped = lang_map.get(lang_lower)

        if mapped:
            return mapped

        return lang.upper()[:3] if len(lang) >= 3 else lang.upper()

    def _has_french_subs(self, meta):
        """Check if torrent has French subtitles"""
        if 'mediainfo' not in meta or 'media' not in meta['mediainfo']:
            return False

        tracks = meta['mediainfo']['media'].get('track', [])

        for track in tracks:
            if track.get('@type') == 'Text':
                lang = track.get('Language', '')
                lang = lang.lower() if isinstance(lang, str) else ''

                title = track.get('Title', '')
                title = title.lower() if isinstance(title, str) else ''

                if lang in ["french", "fre", "fra", "fr", "français", "francais", 'fr-fr', 'fr-ca']:
                    return True
                if 'french' in title or 'français' in title or 'francais' in title:
                    return True

        return False
