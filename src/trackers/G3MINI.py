# Upload Assistant © 2025 Audionut &amp; wastaken7 — Licensed under UAPL v1.0
#import aiofiles
#import click
from typing import Any

from src.console import console
from src.nfo_generator import SceneNfoGenerator
from src.trackers.COMMON import COMMON
from src.trackers.UNIT3D import UNIT3D


class G3MINI(UNIT3D):
    def __init__(self, config):
        super().__init__(config, tracker_name='G3MINI')
        self.config = config
        self.common = COMMON(config)
        self.tracker = 'G3MINI'
        self.base_url = 'https://gemini-tracker.org'
        self.id_url = f'{self.base_url}/api/torrents/'
        self.upload_url = f'{self.base_url}/api/torrents/upload'
        self.requests_url = f'{self.base_url}/api/requests/filter'
        self.search_url = f'{self.base_url}/api/torrents/filter'
        self.torrent_url = f'{self.base_url}/torrents/'
        self.banned_groups = [""]
        pass

    async def get_category_id(
        self, meta: dict[str, Any], category: str = "", reverse: bool = False, mapping_only: bool = False
    ) -> dict[str, str]:
        category_id = {
            'MOVIE': '1',
            'TV': '2',
            #Film anim 7
            #anim 6
        }
        if mapping_only:
            return category_id
        elif reverse:
            return {v: k for k, v in category_id.items()}
        elif category:
            return {"category_id": category_id.get(category, "0")}
        else:
            meta_category = meta.get("category", "")
            resolved_id = category_id.get(meta_category, "0")
            return {"category_id": resolved_id}

    async def get_type_id(
            self, meta: dict[str, Any], type: str = "", reverse: bool = False, mapping_only: bool = False
    ) -> dict[str, str]:
        type_id = {
            'DISC': '1',
            'REMUX': '2',
            'WEBDL': '4',
            'WEBRIP': '5',
            'HDTV': '6',
            'ENCODE': '3',
            'ISO': '7'
        }
        if mapping_only:
            return type_id
        elif reverse:
            return {v: k for k, v in type_id.items()}
        elif type:
            return {"type_id": type_id.get(type, "0")}
        else:
            meta_type = meta.get("type", "")
            resolved_id = type_id.get(meta_type, "0")
            return {"type_id": resolved_id}

    async def get_resolution_id(
        self, meta: dict[str, Any], resolution: str = "", reverse: bool = False, mapping_only: bool = False
    ) -> dict[str, str]:
        resolution_id = {
            '4320p': '1',
            '2160p': '2',
            '1080p': '3',
            '1080i': '4',
            '720p': '5',
            '576p': '6',
            '576i': '7',
            '480p': '8',
            '480i': '9'
        }
        if mapping_only:
            return resolution_id
        elif reverse:
            return {v: k for k, v in resolution_id.items()}
        elif resolution:
            return {"resolution_id": resolution_id.get(resolution, "10")}
        else:
            meta_resolution = meta.get("resolution", "")
            resolved_id = resolution_id.get(meta_resolution, "10")
            return {"resolution_id": resolved_id}

    async def get_additional_checks(self, meta: dict[str, Any]) -> bool:
        french_languages = ["french", "fre", "fra", "fr", "français", "francais", 'fr-fr', 'fr-ca']
        #check or ignore audio req config
        #self.config['TRACKERS'][self.tracker].get('check_for_rules', True):
        if not await self.common.check_language_requirements(
            meta,
            self.tracker,
            languages_to_check=french_languages,
            check_audio=True,
            check_subtitle=True,
            require_both=False,
            #original_language=True,   # Devlopement version
        ):
            console.print(f"[bold red]Language requirements not met for {self.tracker}.[/bold red]")
            return False

        # Generate NFO if enabled in tracker config
        tracker_config = self.config.get('TRACKERS', {}).get(self.tracker, {})
        if tracker_config.get('generate_nfo', False) and not meta.get('nfo') and not meta.get('auto_nfo'):
            generator = SceneNfoGenerator(self.config)
            nfo_path = await generator.generate_nfo(meta, self.tracker)
            if nfo_path:
                meta['nfo'] = nfo_path
                meta['auto_nfo'] = True
                console.print(f"[green]{self.tracker}: NFO file generated automatically[/green]")

        return True

    async def _build_audio_string(self, meta):
        def get_extra_audio_tag(audio_track):
            vfq = None
            vff = None
            vf = None

            for item in audio_track:
                item = item.get('Language').lower()
                if item == "fr-ca":
                    vfq = True
                elif item == "fr-fr":
                    vff = True
                elif item == "fr":
                    vf = True

            if vff and vfq:
                return 'VF2'
            elif vfq:
                return 'VFQ'
            elif vff:
                return 'VFF'
            elif vf:
                return 'VFI'
            else:
                return None

#        Priority Order:
#        1. MULYi: Exactly 2 audio tracks
#        2. MULTI: 3 audio tracks
#        3. VOSTFR: Single audio (original lang) + French subs + NO French audio
#        4. VO: Single audio (original lang) + NO French subs + NO French audio

        audio_tracks = self._get_audio_tracks(meta)
        if not audio_tracks:
            return ''

        audio_langs = self._extract_audio_languages(audio_tracks, meta)
        if not audio_langs:
            return ''

        extra_audio = get_extra_audio_tag(audio_tracks)
        language = ""
        original_lang = await self._get_original_language(meta)
        has_french_audio = 'FRA' in audio_langs
        has_French_subs = self._has_french_subs(meta)
        num_audio_tracks = len(audio_tracks)

        # DUAL - Exactly 2 audios
        if num_audio_tracks == 2 and has_french_audio:
            language = "MULTi"

        # MULTI - 3+ audios
        if num_audio_tracks >= 3 and has_french_audio:
            language = "MULTi"

        # VOSTFR - Single audio (original) + French subs + NO French audio
        if num_audio_tracks == 1 and original_lang and not has_french_audio and has_French_subs and audio_langs[0] == original_lang:
            language = "VOSTFR"

        # VO - Single audio (original) + NO French subs + NO French audio
        if num_audio_tracks == 1 and original_lang and not has_french_audio and not has_French_subs and audio_langs[0] == original_lang:
            language = "VO"

        # FRENCH. - Single audio FRENCH
        if num_audio_tracks == 1 and has_french_audio and audio_langs[0] == original_lang:
            language = "FRENCH"

        if extra_audio:
            language = language + " " + extra_audio

        return language

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
        """Map language codes and names"""
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

    async def _get_original_language(self, meta):
        """Get the original language from existing metadata"""
        original_lang = None

        if meta.get('original_language'):
            original_lang = meta['original_language']

        if not original_lang:
            imdb_info = meta.get('imdb_info') or {}
            imdb_lang = imdb_info.get('language', '')

            if isinstance(imdb_lang, list) and imdb_lang:
                imdb_lang = imdb_lang[0]

            if imdb_lang:
                original_lang = imdb_lang.get('text', '') if isinstance(imdb_lang, dict) else str(imdb_lang).strip()

        if original_lang:
            return self._map_language(original_lang)

        return None

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

    # https://gemini-tracker.org/pages/7
    async def get_name(self, meta):
        def replace_spaces_with_dots(text: str) -> str:
            return text.replace(" ", ".")
        def _clean_filename(name):
            #[] () - ; : . # " ' +
            invalid = '<>:"/\\|?*'
            for char in invalid:
                name = name.replace(char, '-')
            return name

        type = meta.get('type', "").upper()
        title = meta.get('title', "")
        year = meta.get('year', "")
        manual_year = meta.get('manual_year')
        if manual_year is not None and int(manual_year) > 0:
            year = manual_year
        resolution = meta.get('resolution', "")
        if resolution == "OTHER":
            resolution = ""
        audio = meta.get('audio', "").replace("Dual-Audio", "").replace("Dubbed", "")
        language = await self._build_audio_string(meta)
        service = meta.get('service', "")
        season = meta.get('season', "")
        episode = meta.get('episode', "")
        part = meta.get('part', "")
        repack = meta.get('repack', "")
        three_d = meta.get('3D', "")
        tag = meta.get('tag', "")
        source = meta.get('source', "")
        uhd = meta.get('uhd', "")
        hdr = meta.get('hdr', "")
        hybrid = 'Hybrid' if meta.get('webdv', "") else ""
        # Ensure the following variables are always defined
        name = ""
        video_codec = ""
        video_encode = ""
        region = ""
        dvd_size = ""
        if meta.get('is_disc', "") == "BDMV":  # Disk
            video_codec = meta.get('video_codec', "")
            region = meta.get('region', "") if meta.get('region', "") is not None else ""
        elif meta.get('is_disc', "") == "DVD":
            region = meta.get('region', "") if meta.get('region', "") is not None else ""
            dvd_size = meta.get('dvd_size', "")
        else:
            video_codec = meta.get('video_codec', "")
            video_encode = meta.get('video_encode', "")
        edition = meta.get('edition', "")
        if 'hybrid' in edition.upper():
            edition = edition.replace('Hybrid', '').strip()

        if meta['category'] == "TV":
            year = meta['year'] if meta['search_year'] != "" else ""
            if meta.get('manual_date'):
                # Ignore season and year for --daily flagged shows, just use manual date stored in episode_name
                season = ''
                episode = ''
        if meta.get('no_season', False) is True:
            season = ''
        if meta.get('no_year', False) is True:
            year = ''
        if meta.get('no_aka', False) is True:
            pass
        if meta['debug']:
            console.log("[cyan]get_name cat/type")
            console.log(f"CATEGORY: {meta['category']}")
            console.log(f"TYPE: {meta['type']}")
            console.log("[cyan]get_name meta:")
            # console.log(meta)

        if meta['category'] == "MOVIE":  # MOVIE SPECIFIC
            if type == "DISC":  # Disk
                if meta['is_disc'] == 'BDMV':
                    name = f"{title} {year} {three_d} {edition} {hybrid} {repack} {language} {resolution} {region} {uhd} {source} {hdr} {video_codec} {audio}"
                elif meta['is_disc'] == 'DVD':
                    name = f"{title} {year} {repack} {edition} {region} {source} {dvd_size} {audio}"
                elif meta['is_disc'] == 'HDDVD':
                    name = f"{title} {year} {edition} {repack} {language} {resolution} {source} {video_codec} {audio}"
            elif type == "REMUX" and source in ("BluRay", "HDDVD"):  # BluRay/HDDVD Remux
                name = f"{title} {year} {three_d} {edition} {hybrid} {repack} {language} {resolution} {uhd} {source} REMUX {hdr} {video_codec} {audio}"
            elif type == "REMUX" and source in ("PAL DVD", "NTSC DVD", "DVD"):  # DVD Remux
                name = f"{title} {year} {edition} {repack} {source} REMUX  {audio}"
            elif type == "ENCODE":  # Encode
                name = f"{title} {year} {edition} {hybrid} {repack} {language} {resolution} {uhd} {source} {audio} {hdr} {video_encode}"
            elif type == "WEBDL":  # WEB-DL
                name = f"{title} {year} {edition} {hybrid} {repack} {language} {resolution} {uhd} {service} WEB-DL {audio} {hdr} {video_encode}"
            elif type == "WEBRIP":  # WEBRip
                name = f"{title} {year} {edition} {hybrid} {repack} {language} {resolution} {uhd} {service} WEBRip {audio} {hdr} {video_encode}"
            elif type == "HDTV":  # HDTV
                name = f"{title} {year} {edition} {repack} {language} {resolution} {source} {audio} {video_encode}"
            elif type == "DVDRIP":
                name = f"{title} {year} {source} {video_encode} DVDRip {audio}"

        elif meta['category'] == "TV":  # TV SPECIFIC
            if type == "DISC":  # Disk
                if meta['is_disc'] == 'BDMV':
                    name = f"{title} {year} {season}{episode} {three_d} {edition} {hybrid} {repack} {language} {resolution} {region} {uhd} {source} {hdr} {video_codec} {audio}"
                if meta['is_disc'] == 'DVD':
                    name = f"{title} {year} {season}{episode}{three_d} {repack} {edition} {region} {source} {dvd_size} {audio}"
                elif meta['is_disc'] == 'HDDVD':
                    name = f"{title} {year} {edition} {repack} {language} {resolution} {source} {video_codec} {audio}"
            elif type == "REMUX" and source in ("BluRay", "HDDVD"):  # BluRay Remux
                name = f"{title} {year} {season}{episode} {part} {three_d} {edition} {hybrid} {repack} {language} {resolution} {uhd} {source} REMUX {hdr} {video_codec} {audio}"  # SOURCE
            elif type == "REMUX" and source in ("PAL DVD", "NTSC DVD", "DVD"):  # DVD Remux
                name = f"{title} {year} {season}{episode} {part} {edition} {repack} {source} REMUX {audio}"  # SOURCE
            elif type == "ENCODE":  # Encode
                name = f"{title} {year} {season}{episode} {part} {edition} {hybrid} {repack} {language} {resolution} {uhd} {source} {audio} {hdr} {video_encode}"  # SOURCE
            elif type == "WEBDL":  # WEB-DL
                name = f"{title} {year} {season}{episode} {part} {edition} {hybrid} {repack} {language} {resolution} {uhd} {service} WEB-DL {audio} {hdr} {video_encode}"
            elif type == "WEBRIP":  # WEBRip
                name = f"{title} {year} {season}{episode} {part} {edition} {hybrid} {repack} {language} {resolution} {uhd} {service} WEBRip {audio} {hdr} {video_encode}"
            elif type == "HDTV":  # HDTV
                name = f"{title} {year} {season}{episode} {part} {edition} {repack} {language} {resolution} {source} {audio} {video_encode}"
            elif type == "DVDRIP":
                name = f"{title} {year} {season} {source} DVDRip {audio} {video_encode}"

        try:
            name = ' '.join(name.split())
        except Exception:
            console.print("[bold red]Unable to generate name. Please re-run and correct any of the following args if needed.")
            console.print(f"--category [yellow]{meta['category']}")
            console.print(f"--type [yellow]{meta['type']}")
            console.print(f"--source [yellow]{meta['source']}")
            console.print("[bold green]If you specified type, try also specifying source")

            exit()
        name_notag = name
        name = name_notag + tag
        clean_name = _clean_filename(name)
        dot_name = replace_spaces_with_dots(clean_name)
        return {'name': dot_name}
