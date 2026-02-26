# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
"""GF – generation-free.org (UNIT3D, French private tracker)."""

import re
from typing import Any

import httpx
from unidecode import unidecode

from src.console import console
from src.nfo_generator import SceneNfoGenerator
from src.trackers.COMMON import COMMON
from src.trackers.FRENCH import FRENCH_LANG_VALUES, FrenchTrackerMixin
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
        super().__init__(config, tracker_name="GF")
        self.config = config
        self.common = COMMON(config)
        self.tracker = "GF"
        self.base_url = "https://generation-free.org"
        self.id_url = f"{self.base_url}/api/torrents/"
        self.upload_url = f"{self.base_url}/api/torrents/upload"
        self.requests_url = f"{self.base_url}/api/requests/filter"
        self.search_url = f"{self.base_url}/api/torrents/filter"
        self.torrent_url = f"{self.base_url}/torrents/"
        self.banned_groups = [
            "Akebono",
            "Dread-Team",
            "EXTREME",
            "FL3ER",
            "KyX-LazerTeam",
            "RARBG",
            "STVFRV",
            "SUNS3T",
            "TireXo",
            "Zone80",
        ]
        self.source_flag = "GF"

    WEB_LABEL: str = "WEB"

    # ──────────────────────────────────────────────────────────
    #  Category / Type / Resolution mappings
    # ──────────────────────────────────────────────────────────

    async def get_category_id(
        self,
        meta: dict[str, Any],
        category: str = "",
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        category_id = {
            "MOVIE": "1",
            "TV": "2",
        }
        if mapping_only:
            return category_id
        if reverse:
            return {v: k for k, v in category_id.items()}
        if category:
            return {"category_id": category_id.get(category, "0")}
        return {"category_id": category_id.get(meta.get("category", ""), "0")}

    async def get_type_id(
        self,
        meta: dict[str, Any],
        type: str = "",
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
            "DISC": "6",  # Film ISO
            "REMUX": "11",  # Remux (default, overridden for 2160p below)
            "ENCODE": "8",  # HD (default, overridden by resolution below)
            "WEBDL": "16",  # WEB
            "WEBRIP": "16",  # WEB
            "HDTV": "8",  # HD
        }
        if mapping_only:
            return type_map
        if reverse:
            return {v: k for k, v in type_map.items()}

        meta_type = type or meta.get("type", "")
        resolution = meta.get("resolution", "")
        video_encode = meta.get("video_encode", "")

        # Language-based types take priority
        language_tag = await self._build_audio_string(meta)
        if "VOSTFR" in language_tag:
            return {"type_id": "14"}
        # VO: empty language tag but audio tracks present → no French content
        if not language_tag:
            audio_tracks = self._get_audio_tracks(meta)
            if audio_tracks:
                return {"type_id": "15"}

        # AV1 codec → dedicated type
        if "AV1" in video_encode.upper():
            return {"type_id": "41"}

        # DISC (ISO)
        if meta_type == "DISC":
            if meta.get("is_disc") == "BDMV":
                # BluRay disc → treat as 4K or Remux depending on resolution
                if resolution in ("2160p", "4320p"):
                    return {"type_id": "2"}  # 4K
                return {"type_id": "11"}  # Remux
            return {"type_id": "6"}  # Film ISO (DVD)

        # Remux: 2160p → 4K (2), else → Remux (11)
        if meta_type == "REMUX":
            if resolution in ("2160p", "4320p"):
                return {"type_id": "2"}  # 4K
            return {"type_id": "11"}  # Remux

        # WEB-DL / WEBRip
        if meta_type in ("WEBDL", "WEBRIP"):
            return {"type_id": "16"}  # WEB

        # Encode / HDTV – resolution-dependent
        if meta_type in ("ENCODE", "HDTV"):
            if resolution in ("2160p", "4320p"):
                return {"type_id": "42"}  # 4KLight
            if resolution == "1080p":
                return {"type_id": "8"}  # HD
            if resolution in ("720p",):
                if "x265" in video_encode.lower() or "hevc" in video_encode.lower():
                    return {"type_id": "10"}  # HDlight X265
                return {"type_id": "9"}  # HDlight X264
            # SD (480p, 576p, etc.)
            return {"type_id": "12"}  # SD

        return {"type_id": type_map.get(meta_type, "0")}

    async def get_resolution_id(
        self,
        meta: dict[str, Any],
        resolution: str = "",
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        resolution_id = {
            "4320p": "1",
            "2160p": "2",
            "1080p": "3",
            "1080i": "4",
            "720p": "5",
        }
        if mapping_only:
            return resolution_id
        if reverse:
            return {v: k for k, v in resolution_id.items()}
        if resolution:
            return {"resolution_id": resolution_id.get(resolution, "10")}
        return {"resolution_id": resolution_id.get(meta.get("resolution", ""), "10")}

    # ──────────────────────────────────────────────────────────
    #  Additional checks (language requirement + NFO)
    # ──────────────────────────────────────────────────────────

    async def get_additional_checks(self, meta: dict[str, Any]) -> bool:
        """Enforce French language requirements and auto-generate NFO."""
        french_languages = ["french", "fre", "fra", "fr", "français", "francais", "fr-fr", "fr-ca"]

        if not await self.common.check_language_requirements(
            meta,
            self.tracker,
            languages_to_check=french_languages,
            check_audio=True,
            check_subtitle=True,
            require_both=False,
        ):
            console.print(f"[bold red]Language requirements not met for {self.tracker}.[/bold red]")
            return False

        # Auto-generate NFO if not provided (GF requires NFO for VOSTFR & multi)
        if not meta.get("nfo") and not meta.get("auto_nfo"):
            generator = SceneNfoGenerator(self.config)
            nfo_path = await generator.generate_nfo(meta, self.tracker)
            if nfo_path:
                meta["nfo"] = nfo_path
                meta["auto_nfo"] = True

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
                console.print(f"[bold red]{self.tracker}: Missing API key in config file. Skipping upload...[/bold red]")
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

        category_id = str((await self.get_category_id(meta))["category_id"])
        params: list[tuple[str, QueryValue]] = [
            ("tmdbId", str(meta["tmdb"])),
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
            params = [(k, (str(v) + f" {meta.get('season', '')}" if k == "name" else v)) for k, v in params]

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
                            "files": ([f["name"] for f in attributes.get("files", []) if isinstance(f, dict) and "name" in f] if not meta["is_disc"] else []),
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
            meta["tracker_status"][self.tracker]["status_message"] = f"data error: HTTP {e.response.status_code}"
        except Exception as e:
            console.print(f"[bold red]{self.tracker}: Error searching for existing torrents — {e}[/bold red]")

        return await self._check_french_lang_dupes(dupes, meta)

    # ──────────────────────────────────────────────────────────
    #  Title override — GF uses English title (except French works)
    #  + GF title-case convention (capitalize words > 2 chars)
    # ──────────────────────────────────────────────────────────

    # Words that stay lowercase in English title case (unless first/last)
    _TITLE_CASE_LOWER = frozenset(
        {
            # articles
            "a",
            "an",
            "the",
            # coordinating conjunctions
            "and",
            "but",
            "or",
            "nor",
            "for",
            "yet",
            "so",
            # short prepositions
            "as",
            "at",
            "by",
            "in",
            "of",
            "on",
            "to",
            "up",
            "from",
            "into",
            "like",
            "near",
            "off",
            "over",
            "past",
            "than",
            "with",
            "upon",
            "via",
            # French articles / prepositions (for originally-French titles)
            "le",
            "la",
            "les",
            "un",
            "une",
            "des",
            "du",
            "de",
            "et",
        }
    )

    @classmethod
    def _title_case(cls, text: str) -> str:
        """Apply GF title capitalisation convention.

        Follows standard English title-case rules: capitalise every word
        except articles, short conjunctions and short prepositions —
        unless they are the first or last word.

        Examples:
            "Harry Potter and the Deathly Hallows Part 2"
              → "Harry Potter and the Deathly Hallows Part 2"
            "the lord of the rings" → "The Lord of the Rings"
        """
        if not text or not text.strip():
            return text
        words = text.split()
        last = len(words) - 1
        result: list[str] = []
        for i, word in enumerate(words):
            if i == 0 or i == last:
                # First / last word — always capitalise
                result.append(word.capitalize())
            elif word.lower() in cls._TITLE_CASE_LOWER:
                result.append(word.lower())
            else:
                result.append(word.capitalize())
        return " ".join(result)

    async def _get_french_title(self, meta):
        """GF uses the English title unless the work is originally French.

        In both cases the GF title-case convention is applied.
        """
        orig_lang = str(meta.get("original_language", "")).lower()
        if orig_lang == "fr":
            title = await super()._get_french_title(meta)
        else:
            title = meta.get("title", "")
        return self._title_case(title)

    # ──────────────────────────────────────────────────────────
    #  Audio codec from the French audio track
    # ──────────────────────────────────────────────────────────

    def _get_french_audio_label(self, meta: dict[str, Any]) -> str:
        """Build an audio codec + channel string from the French audio track.

        When the release contains French audio, GF wants the audio tag to
        reflect that track's codec (e.g. ``DTS 5.1``) rather than the
        first track's codec (which is often English DTS-HD MA 7.1).

        Returns the label for the first French track found, or an empty
        string if there is no French audio.
        """
        from src.audio import determine_channel_count

        audio_tracks = self._get_audio_tracks(meta)
        if not audio_tracks:
            return ""

        # find first French audio track
        fr_track: dict[str, Any] | None = None
        for t in audio_tracks:
            lang = str(t.get("Language", "")).lower().strip()
            if lang in FRENCH_LANG_VALUES or lang.startswith("fr"):
                fr_track = t
                break

        if fr_track is None:
            return ""

        # ── codec determination (mirrors src/audio.py logic) ──
        _CODEC_MAP = {
            "DTS": "DTS",
            "AAC": "AAC",
            "AAC LC": "AAC",
            "AC-3": "DD",
            "E-AC-3": "DD+",
            "A_EAC3": "DD+",
            "Enhanced AC-3": "DD+",
            "MLP FBA": "TrueHD",
            "FLAC": "FLAC",
            "Opus": "Opus",
            "Vorbis": "VORBIS",
            "PCM": "LPCM",
            "LPCM Audio": "LPCM",
            "Dolby Digital Audio": "DD",
            "Dolby Digital Plus Audio": "DD+",
            "Dolby Digital Plus": "DD+",
            "Dolby TrueHD Audio": "TrueHD",
            "DTS Audio": "DTS",
            "DTS-HD Master Audio": "DTS-HD MA",
            "DTS-HD High-Res Audio": "DTS-HD HRA",
            "DTS:X Master Audio": "DTS:X",
        }
        _EXTRA = {"XLL": "-HD MA", "XLL X": ":X", "ES": "-ES"}
        _ATMOS = {"JOC": " Atmos", "16-ch": " Atmos", "Atmos Audio": " Atmos"}
        _COMMERCIAL = {
            "Dolby Digital": "DD",
            "Dolby Digital Plus": "DD+",
            "Dolby TrueHD": "TrueHD",
            "DTS-ES": "DTS-ES",
            "DTS-HD High": "DTS-HD HRA",
            "Free Lossless Audio Codec": "FLAC",
            "DTS-HD Master Audio": "DTS-HD MA",
        }

        fmt = str(fr_track.get("Format", ""))
        commercial = str(fr_track.get("Format_Commercial", "") or fr_track.get("Format_Commercial_IfAny", ""))
        additional = str(fr_track.get("Format_AdditionalFeatures", "") or "")
        channels_raw = fr_track.get("Channels_Original", fr_track.get("Channels"))
        channel_layout = str(fr_track.get("ChannelLayout", "") or fr_track.get("ChannelLayout_Original", "") or fr_track.get("ChannelPositions", ""))

        codec = ""
        extra = ""
        search_format = True

        if commercial:
            for key, value in _COMMERCIAL.items():
                if key in commercial:
                    codec = value
                    search_format = False
                if "Atmos" in commercial or _ATMOS.get(additional, "") == " Atmos":
                    extra = " Atmos"
        if search_format:
            codec = _CODEC_MAP.get(fmt, "") + _EXTRA.get(additional, "")
            extra = _ATMOS.get(additional, "")
        if not codec:
            codec = fmt
        if fmt.startswith("DTS") and additional and additional.endswith("X"):
            codec = "DTS:X"

        chan = determine_channel_count(channels_raw, channel_layout, additional, fmt)
        if chan == "Unknown":
            chan = ""

        label = f"{codec} {chan}{extra}".strip()
        return label

    # ──────────────────────────────────────────────────────────
    #  Release naming override — GF-specific rules
    #
    #  Differences from the base FrenchTrackerMixin:
    #  - REMUX: Hybrid tag is suppressed
    #  - HDR/DV is placed right after the resolution
    #  - Audio codec reflects the French track (not the first track)
    # ──────────────────────────────────────────────────────────

    async def get_name(self, meta: dict[str, Any]) -> dict[str, str]:
        """Build the release name with GF-specific ordering rules."""

        is_original_french = str(meta.get("original_language", "")).lower() == "fr"
        if self.PREFER_ORIGINAL_TITLE and not is_original_french:
            title = meta.get("title", "")
        else:
            title = await self._get_french_title(meta)

        year = str(meta.get("year", ""))
        language = await self._build_audio_string(meta)
        resolution = meta.get("resolution", "")
        if resolution == "OTHER":
            resolution = ""
        audio = meta.get("audio", "").replace("Dual-Audio", "").replace("Dubbed", "").replace("DD+", "DDP")

        # ── GF: prefer French audio track's codec when French audio exists ──
        fr_audio_label = self._get_french_audio_label(meta)
        if fr_audio_label:
            audio = fr_audio_label.replace("DD+", "DDP")

        service = meta.get("service", "") if self.INCLUDE_SERVICE_IN_NAME else ""
        season = meta.get("season", "")
        episode = meta.get("episode", "")
        part = meta.get("part", "")
        repack = meta.get("repack", "")
        three_d = meta.get("3D", "")
        tag = meta.get("tag", "")
        source = meta.get("source", "")
        uhd = meta.get("uhd", "")
        hdr = meta.get("hdr", "").replace("HDR10+", "HDR10PLUS")
        edition = meta.get("edition", "")
        if "hybrid" in edition.upper() or "custom" in edition.upper():
            edition = re.sub(r"\b(?:Hybrid|CUSTOM|Custom)\b", "", edition, flags=re.IGNORECASE).strip()

        type_val = meta.get("type", "").upper()
        category = meta.get("category", "MOVIE")

        # ── GF: suppress Hybrid for REMUX ──
        hybrid = "" if type_val == "REMUX" else str(meta.get("webdv", "")) if meta.get("webdv", "") else ""

        video_codec = ""
        video_encode = ""
        region = ""
        dvd_size = ""

        if meta.get("is_disc") == "BDMV":
            video_codec = meta.get("video_codec", "").replace("H.264", "H264").replace("H.265", "H265")
            region = meta.get("region", "") or ""
        elif meta.get("is_disc") == "DVD":
            region = meta.get("region", "") or ""
            dvd_size = meta.get("dvd_size", "")
        else:
            video_codec = meta.get("video_codec", "").replace("H.264", "H264").replace("H.265", "H265")
            video_encode = meta.get("video_encode", "").replace("H.264", "H264").replace("H.265", "H265")

        if category == "TV":
            year = meta["year"] if meta.get("search_year", "") != "" else ""
            if meta.get("manual_date"):
                season = ""
                episode = ""
        if meta.get("no_season", False) is True:
            season = ""
        if meta.get("no_year", False) is True:
            year = ""

        web_lbl = self.WEB_LABEL
        name = ""

        # GF ordering: title year [se] edition hybrid repack language resolution HDR source [REMUX] audio codec

        # ── MOVIE ──
        if category == "MOVIE":
            if type_val == "DISC":
                disc = meta.get("is_disc", "")
                if disc == "BDMV":
                    name = f"{title} {year} {three_d} {edition} {hybrid} {repack} {language} {resolution} {hdr} {region} {uhd} {source} {audio} {video_codec}"
                elif disc == "DVD":
                    name = f"{title} {year} {repack} {edition} {language} {region} {source} {dvd_size} {audio}"
                elif disc == "HDDVD":
                    name = f"{title} {year} {edition} {repack} {language} {resolution} {hdr} {source} {audio} {video_codec}"
            elif type_val == "REMUX" and source in ("BluRay", "HDDVD"):
                name = f"{title} {year} {three_d} {edition} {repack} {language} {resolution} {hdr} {uhd} {source} REMUX {audio} {video_codec}"
            elif type_val == "REMUX" and source in ("PAL DVD", "NTSC DVD", "DVD"):
                name = f"{title} {year} {edition} {repack} {language} {source} REMUX {audio}"
            elif type_val == "REMUX":
                name = f"{title} {year} {edition} {repack} {language} {resolution} {hdr} {uhd} {source} REMUX {audio} {video_codec}"
            elif type_val == "ENCODE":
                name = f"{title} {year} {edition} {hybrid} {repack} {language} {resolution} {hdr} {uhd} {source} {audio} {video_encode}"
            elif type_val == "WEBDL":
                name = f"{title} {year} {edition} {hybrid} {repack} {language} {resolution} {hdr} {uhd} {service} {web_lbl} {audio} {video_encode}"
            elif type_val == "WEBRIP":
                name = f"{title} {year} {edition} {hybrid} {repack} {language} {resolution} {hdr} {uhd} {service} WEBRip {audio} {video_encode}"
            elif type_val == "HDTV":
                name = f"{title} {year} {edition} {repack} {language} {resolution} {hdr} {source} {audio} {video_encode}"
            elif type_val == "DVDRIP":
                name = f"{title} {year} {language} {source} DVDRip {audio} {video_encode}"

        # ── TV ──
        elif category == "TV":
            se = f"{season}{episode}"
            if type_val == "DISC":
                disc = meta.get("is_disc", "")
                if disc == "BDMV":
                    name = f"{title} {year} {se} {three_d} {edition} {hybrid} {repack} {language} {resolution} {hdr} {region} {uhd} {source} {audio} {video_codec}"
                elif disc == "DVD":
                    name = f"{title} {year} {se} {three_d} {repack} {edition} {language} {region} {source} {dvd_size} {audio}"
                elif disc == "HDDVD":
                    name = f"{title} {year} {se} {edition} {repack} {language} {resolution} {hdr} {source} {audio} {video_codec}"
            elif type_val == "REMUX" and source in ("BluRay", "HDDVD"):
                name = f"{title} {year} {se} {part} {three_d} {edition} {repack} {language} {resolution} {hdr} {uhd} {source} REMUX {audio} {video_codec}"
            elif type_val == "REMUX" and source in ("PAL DVD", "NTSC DVD", "DVD"):
                name = f"{title} {year} {se} {part} {edition} {repack} {language} {source} REMUX {audio}"
            elif type_val == "REMUX":
                name = f"{title} {year} {se} {part} {edition} {repack} {language} {resolution} {hdr} {uhd} {source} REMUX {audio} {video_codec}"
            elif type_val == "ENCODE":
                name = f"{title} {year} {se} {part} {edition} {hybrid} {repack} {language} {resolution} {hdr} {uhd} {source} {audio} {video_encode}"
            elif type_val == "WEBDL":
                name = f"{title} {year} {se} {part} {edition} {hybrid} {repack} {language} {resolution} {hdr} {uhd} {service} {web_lbl} {audio} {video_encode}"
            elif type_val == "WEBRIP":
                name = f"{title} {year} {se} {part} {edition} {hybrid} {repack} {language} {resolution} {hdr} {uhd} {service} WEBRip {audio} {video_encode}"
            elif type_val == "HDTV":
                name = f"{title} {year} {se} {part} {edition} {repack} {language} {resolution} {hdr} {source} {audio} {video_encode}"
            elif type_val == "DVDRIP":
                name = f"{title} {year} {se} {language} {source} DVDRip {audio} {video_encode}"

        if not name:
            name = f"{title} {year} {language} {resolution} {hdr} {type_val} {audio} {video_encode}"

        # ── Post-processing ──
        name = " ".join(name.split())
        name = name + tag

        return self._format_name(name)

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
        return re.sub(r"[^a-zA-Z0-9 .\-]", "", text)

    def _format_name(self, raw_name: str) -> dict[str, str]:
        """GF uses spaces as separators (not dots).

        Dots inside audio channel counts (e.g. ``5.1``, ``7.1``) are
        preserved because they are flanked by digits.
        """
        clean = self._fr_clean(raw_name)

        # Replace dots NOT between digits (keep 5.1, 7.1, 2.0 …)
        clean = re.sub(r"(?<!\d)\.(?!\d)", " ", clean)

        # Keep only the LAST hyphen (group-tag separator)
        idx = clean.rfind("-")
        if idx > 0:
            clean = clean[:idx].replace("-", " ") + clean[idx:]

        # Remove isolated hyphens between spaces
        clean = re.sub(r" (- )+", " ", clean)
        # Collapse multiple spaces
        clean = re.sub(r" {2,}", " ", clean).strip()

        return {"name": clean}
