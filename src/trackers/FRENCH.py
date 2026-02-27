# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
"""
French tracker mixin — shared logic for all French-language trackers.

All French trackers (C411, G3MINI, LACALE, TORR9, …) inherit from this mixin
to share a single, canonical implementation of:
  · Audio language detection / French dub suffix (VFF, VFQ, VF2, …)
  · Language tag building  (MULTI.VFF, VOSTFR, MUET, …)
  · French title from TMDB
  · Release naming (dot-separated, French-tracker conventions)
"""

import os
import re
from typing import Any, Optional, Union

from unidecode import unidecode

Meta = dict[str, Any]

# ── Language → 3-letter ISO 639 mapping (comprehensive) ──────
LANG_MAP: dict[str, str] = {
    # French
    "fr": "FRA",
    "fre": "FRA",
    "fra": "FRA",
    "french": "FRA",
    "français": "FRA",
    "francais": "FRA",
    "fr-fr": "FRA",
    "fr-ca": "FRA",
    "fr-be": "FRA",
    "fr-ch": "FRA",
    # English
    "en": "ENG",
    "eng": "ENG",
    "english": "ENG",
    "en-us": "ENG",
    "en-gb": "ENG",
    # Spanish
    "es": "SPA",
    "spa": "SPA",
    "spanish": "SPA",
    "español": "SPA",
    "castellano": "SPA",
    "es-es": "SPA",
    "lat": "LAT",
    "latino": "LAT",
    "latin american spanish": "LAT",
    "es-mx": "LAT",
    "es-419": "LAT",
    # German
    "de": "DEU",
    "deu": "DEU",
    "ger": "DEU",
    "german": "DEU",
    "deutsch": "DEU",
    # Italian
    "it": "ITA",
    "ita": "ITA",
    "italian": "ITA",
    "italiano": "ITA",
    # Portuguese
    "pt": "POR",
    "por": "POR",
    "portuguese": "POR",
    "português": "POR",
    "portuguese (iberian)": "POR",
    "pt-br": "POR",
    "pt-pt": "POR",
    # Japanese
    "ja": "JPN",
    "jpn": "JPN",
    "japanese": "JPN",
    "日本語": "JPN",
    # Korean
    "ko": "KOR",
    "kor": "KOR",
    "korean": "KOR",
    "한국어": "KOR",
    # Chinese
    "zh": "ZHO",
    "zho": "ZHO",
    "chi": "ZHO",
    "chinese": "ZHO",
    "mandarin": "ZHO",
    "中文": "ZHO",
    "zh-cn": "ZHO",
    # Russian
    "ru": "RUS",
    "rus": "RUS",
    "russian": "RUS",
    "русский": "RUS",
    # Arabic
    "ar": "ARA",
    "ara": "ARA",
    "arabic": "ARA",
    # Hindi
    "hi": "HIN",
    "hin": "HIN",
    "hindi": "HIN",
    # Dutch
    "nl": "NLD",
    "nld": "NLD",
    "dut": "NLD",
    "dutch": "NLD",
    # Polish
    "pl": "POL",
    "pol": "POL",
    "polish": "POL",
    # Turkish
    "tr": "TUR",
    "tur": "TUR",
    "turkish": "TUR",
    # Thai
    "th": "THA",
    "tha": "THA",
    "thai": "THA",
    # Vietnamese
    "vi": "VIE",
    "vie": "VIE",
    "vietnamese": "VIE",
    # Swedish
    "sv": "SWE",
    "swe": "SWE",
    "swedish": "SWE",
    # Norwegian
    "no": "NOR",
    "nor": "NOR",
    "norwegian": "NOR",
    "nb": "NOR",
    "nob": "NOR",
    # Danish
    "da": "DAN",
    "dan": "DAN",
    "danish": "DAN",
    # Finnish
    "fi": "FIN",
    "fin": "FIN",
    "finnish": "FIN",
    # Czech
    "cs": "CES",
    "ces": "CES",
    "cze": "CES",
    "czech": "CES",
    # Hungarian
    "hu": "HUN",
    "hun": "HUN",
    "hungarian": "HUN",
    # Romanian
    "ro": "RON",
    "ron": "RON",
    "rum": "RON",
    "romanian": "RON",
    # Greek
    "el": "ELL",
    "ell": "ELL",
    "gre": "ELL",
    "greek": "ELL",
    # Hebrew
    "he": "HEB",
    "heb": "HEB",
    "hebrew": "HEB",
    # Indonesian
    "id": "IND",
    "ind": "IND",
    "indonesian": "IND",
    # Ukrainian
    "uk": "UKR",
    "ukr": "UKR",
    "ukrainian": "UKR",
    # Tamil / Telugu
    "ta": "TAM",
    "tam": "TAM",
    "tamil": "TAM",
    "te": "TEL",
    "tel": "TEL",
    "telugu": "TEL",
    # Malay
    "ms": "MSA",
    "msa": "MSA",
    "may": "MSA",
    "malay": "MSA",
    # Persian
    "fa": "FAS",
    "fas": "FAS",
    "per": "FAS",
    "persian": "FAS",
}

# ── Language → flag emoji mapping (for BBCode descriptions) ──
LANG_FLAGS: dict[str, str] = {
    "english": "🇺🇸",
    "french": "🇫🇷",
    "german": "🇩🇪",
    "spanish": "🇪🇸",
    "italian": "🇮🇹",
    "portuguese": "🇵🇹",
    "russian": "🇷🇺",
    "japanese": "🇯🇵",
    "korean": "🇰🇷",
    "chinese": "🇨🇳",
    "arabic": "🇸🇦",
    "dutch": "🇳🇱",
    "polish": "🇵🇱",
    "turkish": "🇹🇷",
    "thai": "🇹🇭",
    "swedish": "🇸🇪",
    "norwegian": "🇳🇴",
    "norwegian bokmal": "🇳🇴",
    "norwegian bokmål": "🇳🇴",
    "norwegian nynorsk": "🇳🇴",
    "danish": "🇩🇰",
    "finnish": "🇫🇮",
    "czech": "🇨🇿",
    "hungarian": "🇭🇺",
    "romanian": "🇷🇴",
    "greek": "🇬🇷",
    "hebrew": "🇮🇱",
    "indonesian": "🇮🇩",
    "bulgarian": "🇧🇬",
    "croatian": "🇭🇷",
    "serbian": "🇷🇸",
    "slovenian": "🇸🇮",
    "estonian": "🇪🇪",
    "icelandic": "🇮🇸",
    "lithuanian": "🇱🇹",
    "latvian": "🇱🇻",
    "ukrainian": "🇺🇦",
    "hindi": "🇮🇳",
    "tamil": "🇮🇳",
    "telugu": "🇮🇳",
    "malay": "🇲🇾",
    "vietnamese": "🇻🇳",
    "persian": "🇮🇷",
    "cantonese": "🇨🇳",
    "mandarin": "🇨🇳",
    "slovak": "🇸🇰",
    "catalan": "🇪🇸",
    "basque": "🇪🇸",
    "galician": "🇪🇸",
    "bengali": "🇧🇩",
    "urdu": "🇵🇰",
    "tagalog": "🇵🇭",
    "filipino": "🇵🇭",
    "khmer": "🇰🇭",
    "mongolian": "🇲🇳",
    "georgian": "🇬🇪",
    "albanian": "🇦🇱",
    "macedonian": "🇲🇰",
    "bosnian": "🇧🇦",
    "swahili": "🇰🇪",
}

# ── Language → French display name ───────────────────────────
LANG_NAMES_FR: dict[str, str] = {
    "english": "Anglais",
    "french": "Français",
    "german": "Allemand",
    "spanish": "Espagnol",
    "italian": "Italien",
    "portuguese": "Portugais",
    "russian": "Russe",
    "japanese": "Japonais",
    "korean": "Coréen",
    "chinese": "Chinois",
    "arabic": "Arabe",
    "dutch": "Néerlandais",
    "polish": "Polonais",
    "turkish": "Turc",
    "thai": "Thaï",
    "swedish": "Suédois",
    "norwegian": "Norvégien",
    "norwegian bokmal": "Norvégien",
    "norwegian bokmål": "Norvégien",
    "norwegian nynorsk": "Norvégien (nynorsk)",
    "danish": "Danois",
    "finnish": "Finnois",
    "czech": "Tchèque",
    "hungarian": "Hongrois",
    "romanian": "Roumain",
    "greek": "Grec",
    "hebrew": "Hébreu",
    "indonesian": "Indonésien",
    "bulgarian": "Bulgare",
    "croatian": "Croate",
    "serbian": "Serbe",
    "slovenian": "Slovène",
    "estonian": "Estonien",
    "icelandic": "Islandais",
    "lithuanian": "Lituanien",
    "latvian": "Letton",
    "ukrainian": "Ukrainien",
    "hindi": "Hindi",
    "tamil": "Tamoul",
    "telugu": "Télougou",
    "malay": "Malais",
    "vietnamese": "Vietnamien",
    "persian": "Persan",
    "cantonese": "Cantonais",
    "mandarin": "Mandarin",
    "slovak": "Slovaque",
    "catalan": "Catalan",
    "basque": "Basque",
    "galician": "Galicien",
    "bengali": "Bengali",
    "urdu": "Ourdou",
    "tagalog": "Tagalog",
    "filipino": "Filipino",
    "khmer": "Khmer",
    "mongolian": "Mongol",
    "georgian": "Géorgien",
    "albanian": "Albanais",
    "macedonian": "Macédonien",
    "bosnian": "Bosniaque",
    "swahili": "Swahili",
}

# Canonical list of French language values (for subtitle/audio detection)
FRENCH_LANG_VALUES = frozenset(
    {
        "french",
        "fre",
        "fra",
        "fr",
        "français",
        "francais",
        "fr-fr",
        "fr-ca",
        "fr-be",
        "fr-ch",
    }
)

# ── French language hierarchy for dupe checking ──────────────
# On French trackers a release with French audio always supersedes a
# VOSTFR (subtitles-only) or VO (original-only) version of the same
# content.  The hierarchy ranks tags from most desirable (MULTI, 7)
# to least (VO, 1).
FRENCH_LANG_HIERARCHY: dict[str, int] = {
    "MULTI": 7,
    "VFF": 6,
    "VFQ": 6,
    "VF2": 6,
    "VOF": 5,
    "TRUEFRENCH": 4,
    "FRENCH": 3,
    "VOSTFR": 2,
    "VO": 1,
}

# Threshold: tags at or above this level indicate French audio is present
_FRENCH_AUDIO_THRESHOLD = 3  # FRENCH and above


class FrenchTrackerMixin:
    """Mixin providing French-tracker naming and audio analysis.

    Mix this into any tracker class that targets a French tracker.
    Requires the host class to have a ``tmdb_manager`` attribute
    (instance of :class:`src.tmdb.TmdbManager`).
    """

    # Subclasses may override to change the WEBDL source label in release names
    # e.g. "WEB" (C411/TORR9/LACALE) vs "WEB-DL" (G3MINI)
    WEB_LABEL: str = "WEB"

    # Whether to include the streaming service name (NF, AMZN, …) in the release name.
    # Set to False for trackers that want the service only in the description.
    INCLUDE_SERVICE_IN_NAME: bool = True

    # Whether to prefer the original-language title in release names.
    # When True and the movie is not originally French, the English/original
    # title is used instead of the French TMDB translation.
    # Set to True for trackers that accept both title languages (e.g. TORR9).
    PREFER_ORIGINAL_TITLE: bool = False

    # Whether the "UHD" tag should only appear for REMUX / DISC releases.
    # C411 wiki: "UHD is only allowed when the title contains REMUX/BDMV/ISO".
    # When True, UHD is stripped from ENCODE, WEBDL, WEBRIP, HDTV, DVDRIP.
    UHD_ONLY_FOR_REMUX_DISC: bool = False

    # ──────────────────────────────────────────────────────────
    #  Audio-track helpers
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def _get_audio_tracks(meta: Meta, filter_commentary: bool = True) -> list[dict[str, Any]]:
        """Extract audio tracks from MediaInfo, optionally filtering commentary."""
        if "mediainfo" not in meta or "media" not in meta.get("mediainfo", {}):
            return []
        tracks = meta["mediainfo"]["media"].get("track", [])
        audio = [t for t in tracks if t.get("@type") == "Audio"]
        if filter_commentary:
            audio = [t for t in audio if "commentary" not in str(t.get("Title", "")).lower() and "comment" not in str(t.get("Title", "")).lower()]
        return audio

    @staticmethod
    def _map_language(lang: str) -> str:
        """Map a language name/code to a normalised 3-letter code."""
        if not lang:
            return ""
        mapped = LANG_MAP.get(str(lang).lower().strip())
        if mapped:
            return mapped
        raw = str(lang).strip()
        return raw.upper()[:3] if len(raw) >= 3 else raw.upper()

    @staticmethod
    def _extract_audio_languages(audio_tracks: list[dict[str, Any]], meta: Optional[Meta] = None) -> list[str]:
        """Extract and normalise audio language codes (de-duplicated, ordered)."""
        langs: list[str] = []
        for track in audio_tracks:
            raw = str(track.get("Language", "")).strip().lower()
            if not raw:
                # Fallback: infer from track Title
                title = str(track.get("Title", "")).strip().lower()
                if any(k in title for k in ("french", "français", "francais")):
                    raw = "french"
                elif any(k in title for k in ("english", "anglais")):
                    raw = "english"
            mapped = LANG_MAP.get(raw, raw.upper()[:3] if raw else "")
            if mapped and mapped not in langs:
                langs.append(mapped)
        # Fallback: meta['audio_languages']
        if not langs and meta and meta.get("audio_languages"):
            for lang in meta["audio_languages"]:
                code = LANG_MAP.get(str(lang).lower().strip(), str(lang).upper()[:3])
                if code and code not in langs:
                    langs.append(code)
        return langs

    @staticmethod
    def _get_french_dub_suffix(audio_tracks: list[dict[str, Any]]) -> Union[str, None]:
        """Determine French dub variant from audio-track Language/Title fields.

        Checks the *raw* Language tag for regional variants (``fr-fr`` → VFF,
        ``fr-ca`` → VFQ) and the track Title for explicit VFF/VFQ/VF2 labels.

        Returns ``'VFF'``, ``'VFQ'``, ``'VF2'``, ``'VF<n>'`` (n>2), or ``None``.
        """
        fr_variants: list[str] = []

        for track in audio_tracks:
            lang = track.get("Language", "")
            if not isinstance(lang, str):
                continue
            ll = lang.lower().strip()

            # Check raw Language tag for region codes
            if ll == "fr-fr" and "fr-fr" not in fr_variants:
                fr_variants.append("fr-fr")
            elif ll in ("fr-ca", "fr-qc") and "fr-ca" not in fr_variants:
                fr_variants.append("fr-ca")
            elif ll in ("fr-be", "fr-ch"):
                if "fr-fr" not in fr_variants:
                    fr_variants.append("fr-fr")  # Belgium/Switzerland → treat as VFF
            elif ll in ("fr", "fre", "fra", "french", "français", "francais"):
                # Generic French — check Title for explicit VFF/VFQ or region keywords
                title = str(track.get("Title", "")).upper()
                # Canadian French indicators: VFQ, CANADA, CANADIEN, QUÉBEC, (CA), or standalone "CA"
                is_canadian = (
                    "VFQ" in title
                    or "CANADA" in title
                    or "CANADIEN" in title
                    or "QUÉB" in title
                    or "QUEB" in title
                    or "(CA)" in title
                    or re.search(r"\bCA\b", title)  # "FR CA 5.1" → matches CA as word
                )
                if is_canadian:
                    if "fr-ca" not in fr_variants:
                        fr_variants.append("fr-ca")
                elif "VFF" in title or "(FR)" in title or "FRANCE" in title:
                    if "fr-fr" not in fr_variants:
                        fr_variants.append("fr-fr")
                elif "VF2" in title:
                    return "VF2"  # explicit VF2 in title
                else:
                    if "fr" not in fr_variants:
                        fr_variants.append("fr")

        n = len(fr_variants)
        if n == 0:
            return None
        if n > 2:
            return f"VF{n}"

        has_vff = "fr-fr" in fr_variants
        has_vfq = "fr-ca" in fr_variants
        has_generic_fr = "fr" in fr_variants

        # VF2 = two distinct French variants (France + Canada)
        if has_vff and has_vfq:
            return "VF2"
        # Generic French + Canadian = 2 distinct versions → VF2
        if has_generic_fr and has_vfq:
            return "VF2"
        if has_vfq:
            return "VFQ"
        if has_vff:
            return "VFF"
        return None  # generic 'fr' only — no suffix

    @staticmethod
    def _has_french_subs(meta: Meta) -> bool:
        """Check whether French subtitles are present in MediaInfo."""
        if "mediainfo" not in meta or "media" not in meta.get("mediainfo", {}):
            return False
        for track in meta["mediainfo"]["media"].get("track", []):
            if track.get("@type") != "Text":
                continue
            lang = str(track.get("Language", "")).lower().strip()
            if lang in FRENCH_LANG_VALUES or lang.startswith("fr"):
                return True
            title = str(track.get("Title", "")).lower()
            if "french" in title or "français" in title or "francais" in title:
                return True
        return False

    # ──────────────────────────────────────────────────────────
    #  French language hierarchy — dupe checking
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def _extract_french_lang_tag(name: str) -> tuple[str, int]:
        """Extract the highest-level French language tag from a release name.

        Returns ``(tag, level)`` where *level* comes from
        :data:`FRENCH_LANG_HIERARCHY`.  ``('', 0)`` when no tag is found.

        The match is case-insensitive and requires the tag to be delimited
        by dots, spaces, hyphens, underscores, or string boundaries so that
        ``VO`` does not match inside ``VOSTFR`` and ``FRENCH`` does not
        match inside ``TRUEFRENCH``.
        """
        name_upper = name.upper()
        best_tag = ""
        best_level = 0
        for tag, level in FRENCH_LANG_HIERARCHY.items():
            pattern = rf"(?:^|[\.\s\-_])({re.escape(tag)})(?:[\.\s\-_]|$)"
            if re.search(pattern, name_upper) and level > best_level:
                best_tag = tag
                best_level = level
        return (best_tag, best_level)

    async def _check_french_lang_dupes(
        self,
        dupes: list[dict[str, Any]],
        meta: Meta,
    ) -> list[dict[str, Any]]:
        """Filter and flag dupes based on French language hierarchy.

        On French trackers:

        1. **Upload has French audio** (MULTI, VFF, …): existing releases
           that *lack* French audio (VOSTFR, VO) are **removed** from the
           dupe list — they are inferior and do not block the upload.

        2. **Upload lacks French audio** (VOSTFR, VO): existing releases
           that *have* French audio are **flagged** with
           ``'french_lang_supersede'`` so the dupe checker keeps them as
           blocking dupes regardless of other exclusion criteria.
        """
        upload_audio = await self._build_audio_string(meta)

        # MUET (silent film) — special category, not subject to French lang checks
        if upload_audio.startswith("MUET"):
            return dupes

        # Determine the upload's French language level
        upload_tag, upload_level = self._extract_french_lang_tag(upload_audio)
        if not upload_tag:
            # No recognised tag in the audio string — try the raw string
            # e.g. "MULTI.VFF" → extract "MULTI"
            for part in upload_audio.split("."):
                t, lv = self._extract_french_lang_tag(part)
                if lv > upload_level:
                    upload_tag, upload_level = t, lv

        # ── Case 1: Upload HAS French audio → drop inferior dupes ──
        if upload_level >= _FRENCH_AUDIO_THRESHOLD:
            filtered: list[dict[str, Any]] = []
            for dupe in dupes:
                name = dupe.get("name", "") if isinstance(dupe, dict) else str(dupe)
                _, existing_level = self._extract_french_lang_tag(name)
                # Keep the dupe only if it also has French audio (or no tag at all,
                # meaning we can't tell — safer to show it)
                if existing_level >= _FRENCH_AUDIO_THRESHOLD or existing_level == 0:
                    filtered.append(dupe)
                # else: existing is VOSTFR/VO — inferior, silently drop
            return filtered

        # ── Case 2: Upload LACKS French audio → flag superior dupes ──
        if upload_audio in ("VOSTFR", "") or upload_level < _FRENCH_AUDIO_THRESHOLD:
            for dupe in dupes:
                name = dupe.get("name", "") if isinstance(dupe, dict) else str(dupe)
                _, existing_level = self._extract_french_lang_tag(name)
                if existing_level >= _FRENCH_AUDIO_THRESHOLD and isinstance(dupe, dict):
                    flags: list[str] = dupe.setdefault("flags", [])
                    if "french_lang_supersede" not in flags:
                        flags.append("french_lang_supersede")

        return dupes

    async def search_existing(self, meta: Meta, _: Any = None) -> list[dict[str, Any]]:
        """Wrap the parent's ``search_existing`` with French dupe flagging.

        Trackers that define their *own* ``search_existing`` (C411, TORR9,
        LACALE) take priority via MRO and call
        :meth:`_check_french_lang_dupes` explicitly.  This wrapper handles
        trackers that inherit ``search_existing`` from a parent class
        (e.g. G3MINI / TOS inheriting from UNIT3D).
        """
        dupes = await super().search_existing(meta, _)  # type: ignore[misc]
        return await self._check_french_lang_dupes(dupes, meta)

    @staticmethod
    def _detect_truefrench(meta: Meta) -> bool:
        """Check if the release path/name indicates TRUEFRENCH."""
        return any("TRUEFRENCH" in str(meta.get(field, "")).upper() for field in ("uuid", "name", "path"))

    @staticmethod
    def _detect_vfi(meta: Meta) -> bool:
        """Check if the release path/name indicates VFI."""
        for field in ("uuid", "name", "path"):
            val = str(meta.get(field, "")).upper()
            if re.search(r"[\.\-_]VFI[\.\-_]", val) or val.endswith(".VFI") or val.endswith("-VFI"):
                return True
        return False

    @staticmethod
    def _detect_vfq(meta: Meta) -> bool:
        """Check if the release path/name indicates VFQ (Québec French)."""
        for field in ("uuid", "name", "path"):
            val = str(meta.get(field, "")).upper()
            if re.search(r"(?:^|[\.\-_\s])VFQ(?:[\.\-_\s]|$)", val):
                return True
        return False

    @staticmethod
    def _detect_vff(meta: Meta) -> bool:
        """Check if the release path/name indicates VFF (France French)."""
        for field in ("uuid", "name", "path"):
            val = str(meta.get(field, "")).upper()
            if re.search(r"(?:^|[\.\-_\s])VFF(?:[\.\-_\s]|$)", val):
                return True
        return False

    @staticmethod
    def _detect_vf2(meta: Meta) -> bool:
        """Check if the release path/name indicates VF2 (dual French: VFF + VFQ)."""
        for field in ("uuid", "name", "path"):
            val = str(meta.get(field, "")).upper()
            if re.search(r"(?:^|[\.\-_\s])VF2(?:[\.\-_\s]|$)", val):
                return True
        return False

    # ──────────────────────────────────────────────────────────
    #  Build audio/language string
    # ──────────────────────────────────────────────────────────

    async def _build_audio_string(self, meta: Meta) -> str:
        """Build the French language tag from MediaInfo audio tracks.

        Returns one of:
            Single:  VOF · VFF · VFI · VFQ
            Multi:   MULTI.VOF · MULTI.VFF · MULTI.VFQ · MULTI.VF2
            Subs:    VOSTFR
            Silent:  MUET  (or MUET.VOSTFR)
            VO:      '' (empty — English or other VO)

        Note: TRUEFRENCH in source filenames is converted to VFF (modern equivalent).
        """
        if "mediainfo" not in meta or "media" not in meta.get("mediainfo", {}):
            return ""

        audio_tracks = self._get_audio_tracks(meta)

        # MUET — MediaInfo present but no audio tracks
        if not audio_tracks:
            return "MUET.VOSTFR" if self._has_french_subs(meta) else "MUET"

        audio_langs = self._extract_audio_languages(audio_tracks, meta)
        if not audio_langs:
            return ""

        has_french_audio = "FRA" in audio_langs
        has_french_subs = self._has_french_subs(meta)
        num_audio_tracks = len(audio_tracks)
        fr_suffix = self._get_french_dub_suffix(audio_tracks)
        is_original_french = str(meta.get("original_language", "")).lower() == "fr"
        is_truefrench = self._detect_truefrench(meta)
        is_vfi = self._detect_vfi(meta)
        is_vfq_filename = self._detect_vfq(meta)
        is_vff_filename = self._detect_vff(meta)
        is_vf2_filename = self._detect_vf2(meta)

        def _fr_precision() -> str:
            """Determine the best French precision tag."""
            if fr_suffix == "VF2":
                return "VF2"
            # VF2 from filename when MediaInfo doesn't have region codes
            if is_vf2_filename:
                return "VF2"
            if is_original_french:
                return "VOF"
            if is_vfi:
                return "VFI"
            if fr_suffix == "VFQ":
                return "VFQ"
            if fr_suffix == "VFF":
                return "VFF"
            # MediaInfo has generic 'fr' without region — check filename
            if is_vfq_filename:
                return "VFQ"
            if is_vff_filename or is_truefrench:
                return "VFF"
            # Generic 'fr' without region — conservative default
            return "VFF"

        # ── No French audio ──
        if not has_french_audio:
            return "VOSTFR" if has_french_subs else ""

        # ── MULTi — 2+ audio tracks (or non-French track present) ──
        non_fr = [la for la in audio_langs if la != "FRA"]
        if non_fr or num_audio_tracks > 1:
            return f"MULTI.{_fr_precision()}"

        # ── Single French track ──
        if is_original_french:
            return "VOF"
        return _fr_precision()

    # ──────────────────────────────────────────────────────────
    #  French title from TMDB
    # ──────────────────────────────────────────────────────────

    async def _get_french_title(self, meta: Meta) -> str:
        """Get French title from TMDB, cached in ``meta['frtitle']``.

        If TMDB returns the original-language title (i.e. no actual French
        translation exists), falls back to the English title stored in
        ``meta['title']``.  Exception: if the work is originally French,
        the original title *is* the French title and is kept.
        """
        if meta.get("frtitle"):
            return meta["frtitle"]

        tmdb_mgr: Any = getattr(self, "tmdb_manager", None)
        if tmdb_mgr is None:
            return meta.get("title", "")

        try:
            fr_data = await tmdb_mgr.get_tmdb_localized_data(meta, data_type="main", language="fr", append_to_response="") or {}
            fr_title = str(fr_data.get("title", "") or fr_data.get("name", "")).strip()
            original = str(fr_data.get("original_title", "") or fr_data.get("original_name", "")).strip()
            orig_lang = str(fr_data.get("original_language", "")).strip().lower()
            if fr_title and (fr_title != original or orig_lang == "fr"):
                meta["frtitle"] = fr_title
                return fr_title
        except Exception:
            pass

        return meta.get("title", "")

    # ──────────────────────────────────────────────────────────
    #  Release naming   (dot-separated, French-tracker convention)
    #
    #  Film:  Nom.Année.Edition.Repack.Hybrid.Langue.Résolution.Source.HDR.Audio.Codec-TAG
    #  TV:    Nom.Année.SXXEXX.Edition.Repack.Hybrid.Langue.Résolution.Source.HDR.Audio.Codec-TAG
    # ──────────────────────────────────────────────────────────

    async def get_name(self, meta: Meta) -> dict[str, str]:
        """Build the dot-separated release name (French-tracker conventions)."""

        # When PREFER_ORIGINAL_TITLE is set and the movie is not originally
        # French, use the original (English) title instead of the TMDB French
        # translation.  For originally-French works the French title *is* the
        # original, so we always fetch it.
        is_original_french = str(meta.get("original_language", "")).lower() == "fr"
        if self.PREFER_ORIGINAL_TITLE and not is_original_french:
            title = meta.get("title", "")
        else:
            title = await self._get_french_title(meta)
        language = await self._build_audio_string(meta)

        year = meta.get("year", "")
        manual_year = meta.get("manual_year")
        if manual_year is not None and int(manual_year) > 0:
            year = manual_year

        resolution = meta.get("resolution", "")
        if resolution == "OTHER":
            resolution = ""
        audio = meta.get("audio", "").replace("Dual-Audio", "").replace("Dubbed", "").replace("DD+", "DDP")
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
        hybrid = str(meta.get("webdv", "")) if meta.get("webdv", "") else ""
        edition = meta.get("edition", "")
        if "hybrid" in edition.upper() or "custom" in edition.upper():
            edition = re.sub(r"\b(?:Hybrid|CUSTOM|Custom)\b", "", edition, flags=re.IGNORECASE).strip()

        type_val = meta.get("type", "").upper()
        category = meta.get("category", "MOVIE")

        # Some trackers (e.g. C411) only allow UHD for REMUX/DISC releases
        if self.UHD_ONLY_FOR_REMUX_DISC and type_val not in ("REMUX", "DISC"):
            uhd = ""

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

        web_lbl = self.WEB_LABEL  # "WEB" or "WEB-DL" depending on tracker

        name = ""

        # ── MOVIE ──
        if category == "MOVIE":
            if type_val == "DISC":
                disc = meta.get("is_disc", "")
                if disc == "BDMV":
                    name = f"{title} {year} {three_d} {edition} {repack} {hybrid} {language} {resolution} {region} {uhd} {source} {hdr} {audio} {video_codec}"
                elif disc == "DVD":
                    name = f"{title} {year} {edition} {repack} {language} {region} {source} {dvd_size} {audio}"
                elif disc == "HDDVD":
                    name = f"{title} {year} {edition} {repack} {language} {resolution} {source} {audio} {video_codec}"
            elif type_val == "REMUX" and source in ("BluRay", "HDDVD"):
                name = f"{title} {year} {three_d} {edition} {repack} {hybrid} {language} {resolution} {uhd} {source} REMUX {hdr} {audio} {video_codec}"
            elif type_val == "REMUX" and source in ("PAL DVD", "NTSC DVD", "DVD"):
                name = f"{title} {year} {edition} {repack} {language} {source} REMUX {audio}"
            elif type_val == "REMUX":
                name = f"{title} {year} {edition} {repack} {hybrid} {language} {resolution} {uhd} {source} REMUX {hdr} {audio} {video_codec}"
            elif type_val == "ENCODE":
                name = f"{title} {year} {edition} {repack} {hybrid} {language} {resolution} {uhd} {source} {hdr} {audio} {video_encode}"
            elif type_val == "WEBDL":
                name = f"{title} {year} {edition} {repack} {hybrid} {language} {resolution} {uhd} {service} {web_lbl} {hdr} {audio} {video_encode}"
            elif type_val == "WEBRIP":
                name = f"{title} {year} {edition} {repack} {hybrid} {language} {resolution} {uhd} {service} WEBRip {hdr} {audio} {video_encode}"
            elif type_val == "HDTV":
                name = f"{title} {year} {edition} {repack} {language} {resolution} {source} {audio} {video_encode}"
            elif type_val == "DVDRIP":
                name = f"{title} {year} {repack} {language} {source} DVDRip {audio} {video_encode}"

        # ── TV ──
        elif category == "TV":
            se = f"{season}{episode}"
            if type_val == "DISC":
                disc = meta.get("is_disc", "")
                if disc == "BDMV":
                    name = f"{title} {year} {se} {three_d} {edition} {repack} {hybrid} {language} {resolution} {region} {uhd} {source} {hdr} {audio} {video_codec}"
                elif disc == "DVD":
                    name = f"{title} {year} {se} {three_d} {edition} {repack} {language} {region} {source} {dvd_size} {audio}"
                elif disc == "HDDVD":
                    name = f"{title} {year} {se} {edition} {repack} {language} {resolution} {source} {audio} {video_codec}"
            elif type_val == "REMUX" and source in ("BluRay", "HDDVD"):
                name = f"{title} {year} {se} {part} {three_d} {edition} {repack} {hybrid} {language} {resolution} {uhd} {source} REMUX {hdr} {audio} {video_codec}"
            elif type_val == "REMUX" and source in ("PAL DVD", "NTSC DVD", "DVD"):
                name = f"{title} {year} {se} {part} {edition} {repack} {language} {source} REMUX {audio}"
            elif type_val == "REMUX":
                name = f"{title} {year} {se} {part} {edition} {repack} {hybrid} {language} {resolution} {uhd} {source} REMUX {hdr} {audio} {video_codec}"
            elif type_val == "ENCODE":
                name = f"{title} {year} {se} {part} {edition} {repack} {hybrid} {language} {resolution} {uhd} {source} {hdr} {audio} {video_encode}"
            elif type_val == "WEBDL":
                name = f"{title} {year} {se} {part} {edition} {repack} {hybrid} {language} {resolution} {uhd} {service} {web_lbl} {hdr} {audio} {video_encode}"
            elif type_val == "WEBRIP":
                name = f"{title} {year} {se} {part} {edition} {repack} {hybrid} {language} {resolution} {uhd} {service} WEBRip {hdr} {audio} {video_encode}"
            elif type_val == "HDTV":
                name = f"{title} {year} {se} {part} {edition} {repack} {language} {resolution} {source} {audio} {video_encode}"
            elif type_val == "DVDRIP":
                name = f"{title} {year} {se} {repack} {language} {source} DVDRip {audio} {video_encode}"

        if not name:
            name = f"{title} {year} {language} {resolution} {type_val} {audio} {video_encode}"

        # ── Post-processing ──
        name = " ".join(name.split())  # collapse whitespace
        name = name + tag  # tag starts with '-', no space needed

        return self._format_name(name)

    def _format_name(self, raw_name: str) -> dict[str, str]:
        """Clean and format the release name (dot-separated by default).

        Subclasses may override this to change the separator (e.g. spaces).
        """
        clean = self._fr_clean(raw_name)
        dot_name = clean.replace(" ", ".")

        # Keep only the LAST hyphen (group-tag separator)
        idx = dot_name.rfind("-")
        if idx > 0:
            dot_name = dot_name[:idx].replace("-", ".") + dot_name[idx:]

        # Remove isolated hyphens between dots
        dot_name = re.sub(r"\.(-\.)+", ".", dot_name)
        # Collapse consecutive dots, strip boundary dots
        dot_name = re.sub(r"\.{2,}", ".", dot_name).strip(".")

        return {"name": dot_name}

    # Map special Unicode chars to their ASCII equivalents *before*
    # unidecode (which would map · → * and lose the separator).
    _TITLE_CHAR_MAP: dict[str, str] = {
        "\u00b7": " ",  # middle dot   (WALL·E → WALL E → WALL.E / Wall E)
        "\u2022": " ",  # bullet       (same rationale)
        "\u2010": "-",  # hyphen
        "\u2011": "-",  # non-breaking hyphen
        "\u2012": "-",  # figure dash
        "\u2013": "-",  # en dash
        "\u2014": "-",  # em dash
        "\u2015": "-",  # horizontal bar
        "\u2212": "-",  # minus sign
    }

    @staticmethod
    def _fr_clean(text: str) -> str:
        """Strip accents and non-filename characters.

        French elided articles (l', d', qu', etc.) are expanded so that
        ``l'Ordre`` becomes ``L Ordre`` (→ ``L.Ordre`` after dot-formatting),
        matching French-tracker naming conventions.
        """
        for char, repl in FrenchTrackerMixin._TITLE_CHAR_MAP.items():
            text = text.replace(char, repl)
        text = unidecode(text)
        # Replace apostrophes / RIGHT SINGLE QUOTATION MARK / backticks
        # that follow a French elided article with a space, and uppercase
        # the article letter:  l'Ordre → L Ordre,  d'Artagnan → D Artagnan
        text = re.sub(
            r"\b([lLdDnNsScCjJmM]|[Qq]u|[Jj]usqu|[Ll]orsqu|[Pp]uisqu)['\u2019`]",
            lambda m: m.group(1).capitalize() + " ",
            text,
        )
        return re.sub(r"[^a-zA-Z0-9 .+\-]", "", text)

    # ──────────────────────────────────────────────────────────
    #  MediaInfo parsing helpers (shared by description builders)
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def _lang_to_flag(lang: str) -> str:
        """Map a language name (from MediaInfo) to its flag emoji."""
        key = lang.lower().split("(")[0].strip()
        return LANG_FLAGS.get(key, "\U0001f3f3\ufe0f")

    @staticmethod
    def _lang_to_french_name(lang: str) -> str:
        """Map a language name (from MediaInfo) to its French display name."""
        key = lang.lower().split("(")[0].strip()
        return LANG_NAMES_FR.get(key, lang)

    @staticmethod
    def _channels_to_layout(channels: str) -> str:
        """Convert MI channel count to layout notation.

        '6 channels' → '5.1', '8 channels' → '7.1', '2 channels' → '2.0', etc.
        """
        m = re.search(r"(\d+)", channels)
        if not m:
            return channels
        n = int(m.group(1))
        mapping = {1: "1.0", 2: "2.0", 3: "2.1", 6: "5.1", 8: "7.1"}
        return mapping.get(n, str(n))

    @staticmethod
    def _parse_mi_audio_tracks(mi_text: str) -> list[dict[str, str]]:
        """Parse audio tracks from MediaInfo text into structured dicts.

        Each dict may contain: language, format, commercial_name, bitrate,
        channels, channel_layout, title.
        """
        tracks: list[dict[str, str]] = []
        if not mi_text:
            return tracks
        current: Optional[dict[str, str]] = None

        for line in mi_text.split("\n"):
            stripped = line.strip()
            if stripped == "Audio" or stripped.startswith("Audio #"):
                if current:
                    tracks.append(current)
                current = {}
                continue
            if current is not None and (
                stripped.startswith("Text") or stripped.startswith("Menu") or stripped == "Video" or stripped.startswith("Video #") or stripped == "General"
            ):
                tracks.append(current)
                current = None
            if current is not None and ":" in stripped:
                key, _, val = stripped.partition(":")
                key = key.strip()
                val = val.strip()
                if key == "Language":
                    current["language"] = val
                elif key == "Format":
                    current["format"] = val
                elif key == "Commercial name":
                    current["commercial_name"] = val
                elif key == "Bit rate":
                    current["bitrate"] = val
                elif key == "Channel(s)":
                    current["channels"] = val
                elif key == "Channel layout":
                    current["channel_layout"] = val
                elif key == "Title":
                    current["title"] = val

        if current:
            tracks.append(current)
        return tracks

    @staticmethod
    def _parse_mi_subtitle_tracks(mi_text: str) -> list[dict[str, str]]:
        """Parse subtitle tracks from MediaInfo text into structured dicts.

        Each dict may contain: language, format, title, forced, default.
        """
        tracks: list[dict[str, str]] = []
        if not mi_text:
            return tracks
        current: Optional[dict[str, str]] = None

        for line in mi_text.split("\n"):
            stripped = line.strip()
            if stripped == "Text" or stripped.startswith("Text #"):
                if current:
                    tracks.append(current)
                current = {}
                continue
            if current is not None and (stripped.startswith("Menu") or stripped.startswith("Audio") or stripped == "Video" or stripped == "General"):
                tracks.append(current)
                current = None
            if current is not None and ":" in stripped:
                key, _, val = stripped.partition(":")
                key = key.strip()
                val = val.strip()
                if key == "Language":
                    current["language"] = val
                elif key == "Format":
                    current["format"] = val
                elif key == "Title":
                    current["title"] = val
                elif key == "Forced":
                    current["forced"] = val
                elif key == "Default":
                    current["default"] = val

        if current:
            tracks.append(current)
        return tracks

    @staticmethod
    def _sub_format_short(fmt: str) -> str:
        """Return a short label for a subtitle format string."""
        up = fmt.upper()
        if "PGS" in up:
            return "PGS"
        if "SRT" in up or "UTF-8" in up:
            return "SRT"
        if "ASS" in up or "SSA" in up:
            return "ASS"
        if "VOBSUB" in up:
            return "VobSub"
        return fmt

    # ── Release type labels ───────────────────────────────────────────
    TYPE_LABELS: dict[str, str] = {
        "DISC": "Disc",
        "REMUX": "Remux",
        "ENCODE": "Encode",
        "WEBDL": "WEB-DL",
        "WEBRIP": "WEBRip",
        "HDTV": "HDTV",
        "DVDRIP": "DVDRip",
    }

    @staticmethod
    def _get_type_label(meta: dict) -> str:
        """Return a human-readable release type label."""
        raw = (meta.get("type") or "").upper()
        return FrenchTrackerMixin.TYPE_LABELS.get(raw, raw)

    # Container name → common file extension
    CONTAINER_EXT: dict[str, str] = {
        "MATROSKA": "MKV",
        "AVI": "AVI",
        "MPEG-4": "MP4",
        "MPEG-TS": "TS",
        "BDAV": "M2TS",
        "WEBM": "WEBM",
        "OGG": "OGG",
        "FLASH VIDEO": "FLV",
        "WINDOWS MEDIA": "WMV",
    }

    @staticmethod
    def _parse_mi_container(mi_text: str) -> str:
        """Extract container format from the MI General section."""
        if not mi_text:
            return ""
        for line in mi_text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("Format") and ":" in stripped and "profile" not in stripped.lower():
                match = re.search(r":\s*(.+)", stripped)
                if match:
                    return match.group(1).strip()
            # Stop after General section
            if stripped in ("Video", "Audio", "Text", "Menu") or stripped.startswith("Video"):
                break
        return ""

    @classmethod
    def _format_container(cls, mi_text: str) -> str:
        """Return container with file extension, e.g. 'MATROSKA (MKV)'."""
        raw = cls._parse_mi_container(mi_text)
        if not raw:
            return ""
        upper = raw.upper()
        ext = cls.CONTAINER_EXT.get(upper, "")
        return f"{upper} ({ext})" if ext else upper

    @staticmethod
    def _get_release_group(meta: dict) -> str:
        """Extract release group name from meta['tag'] (strip leading hyphen)."""
        tag = (meta.get("tag") or "").strip()
        return tag.lstrip("-") if tag else ""

    # ── Total size / file count (season packs vs single files) ──────────

    @staticmethod
    def _get_total_size(meta: dict, mi_text: str) -> str:
        """Return human-readable total size for the release.

        For a single file, use the MediaInfo 'File size' line.
        For a directory (season pack), sum every file on disk.
        """
        path = meta.get("path", "")
        if path and os.path.isdir(path):
            total = sum(os.path.getsize(os.path.join(root, f)) for root, _dirs, files in os.walk(path) for f in files)
            if total <= 0:
                return ""
            # Format to GiB / MiB like MediaInfo does
            if total >= 1 << 30:  # >= 1 GiB
                return f"{total / (1 << 30):.2f} GiB"
            if total >= 1 << 20:  # >= 1 MiB
                return f"{total / (1 << 20):.2f} MiB"
            return f"{total / (1 << 10):.2f} KiB"
        # Single file: use MediaInfo
        if mi_text:
            size_match = re.search(r"File size\s*:\s*(.+?)\s*(?:\n|$)", mi_text)
            if size_match:
                return size_match.group(1).strip()
        return ""

    # Extensions included in the torrent (video files only).
    _TORRENT_EXTENSIONS: frozenset[str] = frozenset((".mkv", ".mp4", ".ts", ".m2ts", ".vob", ".avi"))

    @staticmethod
    def _count_files(meta: dict) -> str:
        """Count files actually included in the torrent.

        Only video extensions are counted (matching torrent creation logic
        which excludes .nfo, .jpg, .srt, etc.).
        """
        path = meta.get("path", "")
        if not path or not os.path.exists(path):
            return ""
        if os.path.isfile(path):
            return "1"
        exts = FrenchTrackerMixin._TORRENT_EXTENSIONS
        count = sum(1 for _, _, files in os.walk(path) for f in files if os.path.splitext(f)[1].lower() in exts)
        return str(count) if count else ""

    # ── HDR / Dolby Vision display (plain text labels) ──────────────────
    HDR_LABELS: dict[str, str] = {
        "DV": "Dolby Vision",
        "HDR10+": "HDR10+",
        "HDR": "HDR10",
        "HLG": "HLG",
        "PQ10": "PQ10",
        "WCG": "WCG",
    }

    def _format_hdr_dv_bbcode(self, meta: dict) -> Optional[str]:
        """Return a plain-text string listing HDR formats.

        When Dolby Vision is detected, the DV profile (e.g. "Profile 8.1")
        is appended if available in the MediaInfo JSON data.

        Returns *None* when there is nothing to display (SDR content).
        """
        hdr_raw: str = (meta.get("hdr") or "").strip()
        if not hdr_raw:
            return None

        # Match longest tokens first so "HDR10+" is not consumed by "HDR".
        ordered_keys = ["HDR10+", "DV", "HDR", "HLG", "PQ10", "WCG"]
        remaining = hdr_raw
        labels: list[str] = []
        for key in ordered_keys:
            if key in remaining:
                label = self.HDR_LABELS[key]
                # Enrich "Dolby Vision" with the DV profile from MediaInfo JSON
                if key == "DV":
                    dv_profile = self._get_dv_profile(meta)
                    if dv_profile:
                        label = f"{label} ({dv_profile})"
                labels.append(label)
                remaining = remaining.replace(key, "", 1).strip()

        return " + ".join(labels) if labels else None

    @staticmethod
    def _get_dv_profile(meta: dict) -> str:
        """Extract a human-readable Dolby Vision profile from MediaInfo JSON.

        ``HDR_Format_Profile`` typically looks like ``dvhe.08.06`` (Profile 8,
        Level 6) or ``dvhe.05.06``.  We parse it into ``Profile 8.6`` etc.
        Returns an empty string when unavailable.
        """
        tracks = meta.get("mediainfo", {}).get("media", {}).get("track", [])
        for track in tracks:
            if track.get("@type") != "Video":
                continue
            raw = track.get("HDR_Format_Profile", "")
            if not raw or isinstance(raw, dict):
                # Also try HDR_Format_String which may contain "Profile X.Y"
                hdr_str = track.get("HDR_Format_String", "")
                if isinstance(hdr_str, str) and "Profile" in hdr_str:
                    import re as _re

                    m = _re.search(r"Profile\s+(\d+(?:\.\d+)?)", hdr_str)
                    if m:
                        return f"Profile {m.group(1)}"
                return ""
            # Parse "dvhe.08.06" → Profile 8.6
            # Format: dvhe.PP.LL or dvav.PP.LL (PP=profile, LL=level)
            if isinstance(raw, str):
                import re as _re

                m = _re.search(r"(?:dvhe|dvav)\.(\d+)\.(\d+)", raw)
                if m:
                    profile = int(m.group(1))
                    level = int(m.group(2))
                    return f"Profile {profile}.{level}"
                # Fallback: sometimes it's just "dvhe.08"
                m = _re.search(r"(?:dvhe|dvav)\.(\d+)", raw)
                if m:
                    return f"Profile {int(m.group(1))}"
            break
        return ""

    def _format_audio_bbcode(self, mi_text: str, meta: Optional[Meta] = None) -> list[str]:
        """Build pretty BBCode lines for audio tracks.

        When *meta* is provided, cross-references the JSON MediaInfo data
        (which contains raw BCP-47 language codes like ``fr-CA``) with the
        text-parsed tracks for accurate VFF/VFQ/VFB detection.

        Detection priority:
          1. JSON MediaInfo language code (``fr-FR`` → VFF, ``fr-CA`` → VFQ, ``fr-BE`` → VFB)
          2. Explicit label in the track Title field (VFF, VFQ, VFB, VF2, VOF, VFI)
          3. No variant suffix — just "Français"

        Returns a list like::

            ['🇫🇷 Français VFF [5.1] : DTS-HD @ 2 046 kb/s',
             '🇨🇦 Français VFQ [5.1] : Dolby Digital Plus @ 1 024 kb/s',
             '🇧🇪 Français VFB [5.1] : AC3 @ 448 kb/s',
             '🇺🇸 Anglais [5.1] : AC3 @ 384 kb/s']
        """
        tracks = self._parse_mi_audio_tracks(mi_text)
        lines: list[str] = []

        # ── Build a list of raw language codes from JSON MediaInfo ──
        # This lets us detect fr-CA (VFQ) vs fr-FR (VFF) vs fr-BE (VFB)
        # reliably, because MediaInfo text output only shows "French" for all.
        json_audio_langs: list[str] = []
        if meta:
            try:
                json_tracks = meta.get("mediainfo", {}).get("media", {}).get("track", [])
                json_audio_langs = [str(t.get("Language", "")).lower().strip() for t in json_tracks if t.get("@type") == "Audio"]
            except (AttributeError, TypeError):
                pass

        for i, at in enumerate(tracks):
            lang = at.get("language", "Unknown")
            flag = self._lang_to_flag(lang)
            name = self._lang_to_french_name(lang)
            channels = at.get("channels", "")
            layout = self._channels_to_layout(channels) if channels else ""
            commercial = at.get("commercial_name", "")
            fmt = at.get("format", "")
            bitrate = at.get("bitrate", "")
            title = at.get("title", "").upper()

            # Normalise language: "French (CA)" → base="french", region="ca"
            lang_lower = lang.lower().strip()
            region_match = re.search(r"\((\w+)\)", lang_lower)
            lang_region = region_match.group(1) if region_match else ""
            lang_base = lang_lower.split("(")[0].strip()

            # For French tracks: detect VFQ/VFF/VFB variant
            if lang_base in ("french", "fre", "fra", "français", "francais"):
                variant_detected = False

                # Priority 1: raw BCP-47 language code from JSON MediaInfo
                if i < len(json_audio_langs):
                    raw_code = json_audio_langs[i]
                    if raw_code in ("fr-ca", "fr-qc"):
                        flag = "🇨🇦"
                        name = "Français VFQ"
                        variant_detected = True
                    elif raw_code == "fr-be":
                        flag = "🇧🇪"
                        name = "Français VFB"
                        variant_detected = True
                    elif raw_code in ("fr-fr", "fr-ch"):
                        # VFF / standard France French — "Français" suffices
                        variant_detected = True

                # Priority 2: region from MI text, e.g. "French (CA)" → "ca"
                if not variant_detected and lang_region:
                    if lang_region == "ca":
                        flag = "🇨🇦"
                        name = "Français VFQ"
                        variant_detected = True
                    elif lang_region == "be":
                        flag = "🇧🇪"
                        name = "Français VFB"
                        variant_detected = True
                    elif lang_region in ("fr", "ch"):
                        variant_detected = True

                # Priority 3: explicit label in the track Title field
                if not variant_detected:
                    if "VFQ" in title or "QUÉB" in title or "QUEB" in title:
                        flag = "🇨🇦"
                        name = "Français VFQ"
                    elif "VFB" in title or "BELG" in title:
                        flag = "🇧🇪"
                        name = "Français VFB"
                    elif "VFI" in title:
                        name = "Français VFI"
                    # VFF, TRUEFRENCH, VOF → just "Français" (default)

            # ── Spanish region detection ──
            elif lang_base in ("spanish", "spa", "español", "espanol"):
                variant_detected = False

                if i < len(json_audio_langs):
                    raw_code = json_audio_langs[i]
                    if raw_code == "es-es":
                        flag = "🇪🇸"
                        variant_detected = True
                    elif raw_code.startswith("es-") and raw_code != "es-es":
                        flag = "🇲🇽"
                        variant_detected = True

                if not variant_detected and lang_region:
                    if lang_region == "es":
                        flag = "🇪🇸"
                    elif lang_region in ("419", "mx", "ar", "co", "cl", "pe", "ve") or "latin" in lang_lower:
                        flag = "🇲🇽"

                if not variant_detected and not lang_region and title:
                    if "LATIN" in title or "LATINO" in title:
                        flag = "🇲🇽"
                    elif "SPAIN" in title or "ESPAÑA" in title or "CASTILL" in title:
                        flag = "🇪🇸"

            # ── Portuguese region detection ──
            elif lang_base in ("portuguese", "por", "português", "portugues"):
                variant_detected = False

                if i < len(json_audio_langs):
                    raw_code = json_audio_langs[i]
                    if raw_code in ("pt-br",):
                        flag = "🇧🇷"
                        variant_detected = True
                    elif raw_code in ("pt-pt", "pt"):
                        flag = "🇵🇹"
                        variant_detected = True

                if not variant_detected and lang_region:
                    if lang_region == "br":
                        flag = "🇧🇷"
                    elif lang_region in ("pt",):
                        flag = "🇵🇹"

                if not variant_detected and not lang_region and title and ("BRAZIL" in title or "BRASIL" in title):
                    flag = "🇧🇷"

            # ── Mandarin script variant detection ──
            elif lang_base in ("mandarin",):
                flag = "🇨🇳"
                if lang_region == "hant":
                    name = "Mandarin (traditionnel)"
                elif lang_region == "hans":
                    name = "Mandarin (simplifié)"

            # ── Cantonese script variant detection ──
            elif lang_base in ("cantonese",):
                flag = "🇨🇳"
                if lang_region == "hant":
                    name = "Cantonais (traditionnel)"
                elif lang_region == "hans":
                    name = "Cantonais (simplifié)"

            # ── Audio Description detection ──
            is_audio_desc = bool(title and "AUDIO DESCRIPTION" in title)

            # ── Commentary detection ──
            commentary_tag = ""
            title_original = at.get("title", "")
            if title and "COMMENTARY" in title:
                # Extract short descriptor from title patterns:
                #   "English [Philosopher Commentary]" → "Philosopher"
                #   "Cast and Crew Commentary" → "Cast and Crew"
                #   "Composer Commentary/Music-Only Track" → "Composer"
                #   "Commentary by Director ..." → too long, just [Commentaire]
                label = ""
                # Pattern: "Language [Descriptor Commentary...]"
                bracket_match = re.search(r"\[([^\]]*commentary[^\]]*)\]", title_original, re.IGNORECASE)
                if bracket_match:
                    inner = bracket_match.group(1).strip()
                    # Remove "Commentary" and anything after "/" from inner text
                    inner = re.sub(r"\s*Commentary.*", "", inner, flags=re.IGNORECASE).strip()
                    if inner and inner.lower() != lang_base:
                        label = inner
                else:
                    # Pattern: "Descriptor Commentary" (no brackets)
                    comm_match = re.match(r"^(.+?)\s+Commentary", title_original, re.IGNORECASE)
                    if comm_match:
                        label = comm_match.group(1).strip()

                commentary_tag = f"Commentaire : {label}" if label and len(label) <= 40 else "Commentaire"

            # Build: flag Name [layout] : Codec @ Bitrate
            parts: list[str] = [f"{flag} {name}"]
            if is_audio_desc:
                parts.append(" [AD]")
            if commentary_tag:
                parts.append(f" [{commentary_tag}]")
            if layout:
                parts.append(f" [{layout}]")
            codec = commercial or fmt
            if codec:
                parts.append(f" : {codec}")
            if bitrate:
                parts.append(f" @ {bitrate}")
            lines.append("".join(parts))
        return lines

    def _format_subtitle_bbcode(self, mi_text: str, meta: Optional[Meta] = None) -> list[str]:
        """Build pretty BBCode lines for subtitle tracks.

        When *meta* is provided, cross-references the JSON MediaInfo data
        (which contains raw BCP-47 language codes like ``fr-CA``) with the
        text-parsed tracks for accurate region flag detection.

        Detection priority (same as audio):
          1. JSON MediaInfo language code (``fr-FR`` → 🇫🇷, ``fr-CA`` → 🇨🇦, ``es-419`` → 🌎)
          2. Region from MI text, e.g. ``French (CA)``
          3. Explicit label in the track Title field

        Returns a list like:
          ['🇫🇷 Français : PGS (complets)',
           '🇨🇦 Français : PGS (forcés)',
           '🇺🇸 Anglais : PGS (SDH)']
        """
        tracks = self._parse_mi_subtitle_tracks(mi_text)
        lines: list[str] = []

        # ── Build a list of raw language codes from JSON MediaInfo ──
        json_text_langs: list[str] = []
        if meta:
            try:
                json_tracks = meta.get("mediainfo", {}).get("media", {}).get("track", [])
                json_text_langs = [str(t.get("Language", "")).lower().strip() for t in json_tracks if t.get("@type") == "Text"]
            except (AttributeError, TypeError):
                pass

        for i, st in enumerate(tracks):
            lang = st.get("language", "") or "Unknown"
            flag = self._lang_to_flag(lang)
            name = self._lang_to_french_name(lang)
            fmt = st.get("format", "")
            fmt_short = self._sub_format_short(fmt) if fmt else ""
            forced = st.get("forced", "").lower() == "yes"
            title = st.get("title", "")

            # Detect forced from title field too
            if not forced and title and "forced" in title.lower():
                forced = True

            # Detect SDH from title
            sdh = bool(title and ("sdh" in title.lower() or "hearing" in title.lower()))

            # Normalise language: "French (CA)" → base="french", region="ca"
            lang_lower = lang.lower().strip()
            region_match = re.search(r"\((\w+)\)", lang_lower)
            lang_region = region_match.group(1) if region_match else ""
            lang_base = lang_lower.split("(")[0].strip()

            # ── French region detection (VFQ / VFB) ──
            if lang_base in ("french", "fre", "fra", "français", "francais"):
                variant_detected = False

                # Priority 1: raw BCP-47 language code from JSON MediaInfo
                if i < len(json_text_langs):
                    raw_code = json_text_langs[i]
                    if raw_code in ("fr-ca", "fr-qc"):
                        flag = "🇨🇦"
                        variant_detected = True
                    elif raw_code == "fr-be":
                        flag = "🇧🇪"
                        variant_detected = True
                    elif raw_code in ("fr-fr", "fr-ch"):
                        variant_detected = True

                # Priority 2: region from MI text, e.g. "French (CA)" → "ca"
                if not variant_detected and lang_region:
                    if lang_region == "ca":
                        flag = "🇨🇦"
                        variant_detected = True
                    elif lang_region == "be":
                        flag = "🇧🇪"
                        variant_detected = True
                    elif lang_region in ("fr", "ch"):
                        variant_detected = True

                # Priority 3: explicit label in the track Title field
                if not variant_detected and title:
                    title_upper = title.upper()
                    if "CANADA" in title_upper or "VFQ" in title_upper or "QUÉB" in title_upper or "QUEB" in title_upper:
                        flag = "🇨🇦"
                    elif "BELG" in title_upper or "VFB" in title_upper:
                        flag = "🇧🇪"

            # ── Spanish region detection ──
            elif lang_base in ("spanish", "spa", "español", "espanol"):
                variant_detected = False

                if i < len(json_text_langs):
                    raw_code = json_text_langs[i]
                    if raw_code == "es-es":
                        flag = "🇪🇸"
                        variant_detected = True
                    elif raw_code.startswith("es-") and raw_code != "es-es":
                        # Latin American variant (es-419, es-MX, etc.)
                        flag = "🇲🇽"
                        variant_detected = True

                if not variant_detected and lang_region:
                    if lang_region == "es":
                        flag = "🇪🇸"
                    elif lang_region in ("419", "mx", "ar", "co", "cl", "pe", "ve") or "latin" in lang_lower:
                        flag = "🇲🇽"

                if not variant_detected and not lang_region and title:
                    title_lower = title.lower()
                    if "latin" in title_lower or "latino" in title_lower:
                        flag = "🇲🇽"
                    elif "spain" in title_lower or "españa" in title_lower or "castill" in title_lower:
                        flag = "🇪🇸"

            # ── Portuguese region detection ──
            elif lang_base in ("portuguese", "por", "português", "portugues"):
                if i < len(json_text_langs):
                    raw_code = json_text_langs[i]
                    if raw_code in ("pt-br",):
                        flag = "🇧🇷"
                    elif raw_code in ("pt-pt", "pt"):
                        flag = "🇵🇹"
                elif lang_region:
                    if lang_region == "br":
                        flag = "🇧🇷"
                elif title:
                    title_lower = title.lower()
                    if "brazil" in title_lower or "brasil" in title_lower:
                        flag = "🇧🇷"

            # ── Mandarin script variant detection ──
            elif lang_base in ("mandarin",):
                flag = "🇨🇳"
                if lang_region == "hant":
                    name = "Mandarin (traditionnel)"
                elif lang_region == "hans":
                    name = "Mandarin (simplifié)"

            # ── Cantonese script variant detection ──
            elif lang_base in ("cantonese",):
                flag = "🇨🇳"
                if lang_region == "hant":
                    name = "Cantonais (traditionnel)"
                elif lang_region == "hans":
                    name = "Cantonais (simplifié)"

            # ── Commentary detection ──
            is_commentary = bool(title and "commentary" in title.lower())

            # Build qualifier
            if forced:
                qualifier = "forcés"
            elif sdh:
                qualifier = "SDH"
            else:
                qualifier = "complets"

            if is_commentary:
                qualifier += ", commentaire"

            parts: list[str] = [f"{flag} {name}"]
            if fmt_short:
                parts.append(f" : {fmt_short} ({qualifier})")
            else:
                parts.append(f" ({qualifier})")
            lines.append("".join(parts))
        return lines
