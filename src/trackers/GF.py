# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
"""GF – generation-free.org (UNIT3D, French private tracker)."""

import re
from typing import Any

import httpx
from unidecode import unidecode

from src.console import console
from src.nfo_generator import SceneNfoGenerator
from src.trackers.COMMON import COMMON
from src.trackers.FRENCH import FrenchTrackerMixin
from src.trackers.UNIT3D import UNIT3D, QueryValue


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
        if 'VOSTFR' in language_tag:
            return {'type_id': '14'}
        # VO: empty language tag but audio tracks present → no French content
        if not language_tag:
            audio_tracks = self._get_audio_tracks(meta)
            if audio_tracks:
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
    #  Dupe search — broader search for VOSTFR / VO uploads
    # ──────────────────────────────────────────────────────────

    async def search_existing(self, meta: dict[str, Any], _: Any = None) -> list[dict[str, Any]]:
        """Search for existing torrents on GF.

        GF maps VOSTFR and VO to dedicated type IDs (14, 15).  The default
        UNIT3D ``search_existing`` filters by type, so a VOSTFR upload
        would never see existing MULTI releases (which have a different
        type ID).  This override removes the type filter so that
        ``_check_french_lang_dupes`` can detect superior French-audio
        releases and warn the user.
        """
        dupes: list[dict[str, Any]] = []

        meta.setdefault("tracker_status", {})
        meta["tracker_status"].setdefault(self.tracker, {})

        if not self.api_key:
            if not meta["debug"]:
                console.print(
                    f"[bold red]{self.tracker}: Missing API key in config file. Skipping upload...[/bold red]"
                )
            meta["skipping"] = f"{self.tracker}"
            return dupes

        should_continue = await self.get_additional_checks(meta)
        if not should_continue:
            meta["skipping"] = f"{self.tracker}"
            return dupes

        headers = {
            "authorization": f"Bearer {self.api_key}",
            "accept": "application/json",
        }

        category_id = str((await self.get_category_id(meta))['category_id'])
        params: list[tuple[str, QueryValue]] = [
            ("tmdbId", str(meta['tmdb'])),
            ("categories[]", category_id),
            ("name", ""),
            ("perPage", "100"),
        ]

        # Add resolution filter(s)
        resolutions = await self.get_resolution_id(meta)
        resolution_id = str(resolutions["resolution_id"])
        if resolution_id in ["3", "4"]:
            params.append(("resolutions[]", "3"))
            params.append(("resolutions[]", "4"))
        else:
            params.append(("resolutions[]", resolution_id))

        # Do NOT filter by type — we want to see MULTI releases even
        # when uploading VOSTFR/VO so that dupe checking can warn.

        if meta["category"] == "TV":
            params = [
                (k, (str(v) + f" {meta.get('season', '')}" if k == "name" else v))
                for k, v in params
            ]

        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                response = await client.get(url=self.search_url, headers=headers, params=params)
                response.raise_for_status()
                if response.status_code == 200:
                    data = response.json()
                    for each in data["data"]:
                        torrent_id = each.get("id", None)
                        attributes = each.get("attributes", {})
                        name = attributes.get("name", "")
                        size = attributes.get("size", 0)
                        result: dict[str, Any] = {
                            "name": name,
                            "size": size,
                            "files": (
                                [f["name"] for f in attributes.get("files", []) if isinstance(f, dict) and "name" in f]
                                if not meta["is_disc"] else []
                            ),
                            "file_count": len(attributes.get("files", [])) if isinstance(attributes.get("files"), list) else 0,
                            "trumpable": attributes.get("trumpable", False),
                            "link": attributes.get("details_link", None),
                            "download": attributes.get("download_link", None),
                            "id": torrent_id,
                            "type": attributes.get("type", None),
                            "res": attributes.get("resolution", None),
                            "internal": attributes.get("internal", False),
                        }
                        if meta["is_disc"]:
                            result["bd_info"] = attributes.get("bd_info", "")
                            result["description"] = attributes.get("description", "")
                        dupes.append(result)
                else:
                    console.print(f"[bold red]Failed to search torrents on {self.tracker}. HTTP Status: {response.status_code}")
        except httpx.HTTPStatusError as e:
            meta["tracker_status"][self.tracker]["status_message"] = (
                f"data error: HTTP {e.response.status_code}"
            )
        except Exception as e:
            console.print(f"[bold red]{self.tracker}: Error searching for existing torrents — {e}[/bold red]")

        return await self._check_french_lang_dupes(dupes, meta)

    # ──────────────────────────────────────────────────────────
    #  Title override — GF uses English title (except French works)
    # ──────────────────────────────────────────────────────────

    async def _get_french_title(self, meta):
        """GF uses the English title unless the work is originally French."""
        orig_lang = str(meta.get('original_language', '')).lower()
        if orig_lang == 'fr':
            return await super()._get_french_title(meta)
        return meta.get('title', '')

    # ──────────────────────────────────────────────────────────
    #  Cleaning override (GF forbids ALL special chars incl. +)
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def _fr_clean(text: str) -> str:
        """Strip accents and non-filename characters.

        GF forbids *all* special characters including ``+``.
        DD+ → DDP and HDR10+ → HDR10PLUS are handled upstream in
        ``FrenchTrackerMixin.get_name`` before this function is called.
        """
        text = unidecode(text)
        return re.sub(r'[^a-zA-Z0-9 .\-]', '', text)

    def _format_name(self, raw_name: str) -> dict[str, str]:
        """GF uses spaces as separators (not dots).

        Dots inside audio channel counts (e.g. ``5.1``, ``7.1``) are
        preserved because they are flanked by digits.
        """
        clean = self._fr_clean(raw_name)

        # Replace dots NOT between digits (keep 5.1, 7.1, 2.0 …)
        clean = re.sub(r'(?<!\d)\.(?!\d)', ' ', clean)

        # Keep only the LAST hyphen (group-tag separator)
        idx = clean.rfind('-')
        if idx > 0:
            clean = clean[:idx].replace('-', ' ') + clean[idx:]

        # Remove isolated hyphens between spaces
        clean = re.sub(r' (- )+', ' ', clean)
        # Collapse multiple spaces
        clean = re.sub(r' {2,}', ' ', clean).strip()

        return {'name': clean}
