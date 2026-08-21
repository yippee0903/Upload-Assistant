"""Audio/subtitle language facts and French tags (VFF, VFQ, VF2, VOSTFR, MUET). Pure; maps to upbrr languageutil/french.go."""

import re
from typing import Any, Optional, Union

from src.audio import AD_TRACK_RE

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
    "VFB": 6,
    "VF2": 6,
    "VOF": 5,
    "VOQ": 5,  # original Québécois audio — Québec counterpart of VOF
    "TRUEFRENCH": 4,
    "FRENCH": 3,
    "VOSTFR": 2,
    "SUBFRENCH": 2,  # legacy alias for VOSTFR
    "VO": 1,
}

# Threshold: tags at or above this level indicate French audio is present
_FRENCH_AUDIO_THRESHOLD = 3  # FRENCH and above


class FrenchLanguageMixin:
    """Audio/subtitle language facts and French tags (VFF, VFQ, VF2, VOSTFR, MUET). Pure; maps to upbrr languageutil/french.go."""

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
    def _is_audio_desc_track(track: dict[str, Any]) -> bool:
        """Return True when an audio track is an audio-description track."""
        title = str(track.get("Title") or track.get("title") or "")
        return bool(AD_TRACK_RE.search(title))

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
            elif ll == "fr-be" and "fr-be" not in fr_variants:
                fr_variants.append("fr-be")
            elif ll == "fr-ch":
                if "fr-fr" not in fr_variants:
                    fr_variants.append("fr-fr")  # Swiss French → treat as VFF
            elif ll in ("fr", "fre", "fra", "french", "français", "francais"):
                # Generic French — check Title for explicit VFF/VFQ/VFB or region keywords
                title = str(track.get("Title", "")).upper()
                # Canadian French indicators
                is_canadian = (
                    "VFQ" in title
                    or "CANADA" in title
                    or "CANADIEN" in title
                    or "QUÉB" in title
                    or "QUEB" in title
                    or "(CA)" in title
                    or re.search(r"\bCA\b", title)  # "FR CA 5.1" → matches CA as word
                )
                # Belgian French indicators
                is_belgian = "VFB" in title or "BELGE" in title or "BELGIQUE" in title or "(BE)" in title
                if is_canadian:
                    if "fr-ca" not in fr_variants:
                        fr_variants.append("fr-ca")
                elif is_belgian:
                    if "fr-be" not in fr_variants:
                        fr_variants.append("fr-be")
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
        if n >= 2:
            return f"VF{n}"

        has_vfq = "fr-ca" in fr_variants
        has_vfb = "fr-be" in fr_variants
        has_vff = "fr-fr" in fr_variants

        if has_vfq:
            return "VFQ"
        if has_vfb:
            return "VFB"
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

    @staticmethod
    def _detect_vfb(meta: Meta) -> bool:
        """Check if the release path/name indicates VFB (Belgian French)."""
        for field in ("uuid", "name", "path"):
            val = str(meta.get(field, "")).upper()
            if re.search(r"(?:^|[\.\-_\s])VFB(?:[\.\-_\s]|$)", val):
                return True
        return False

    @staticmethod
    def _detect_subfrench(meta: Meta) -> bool:
        """Check if the release path/name indicates SUBFRENCH or VOSTFR.

        Used as a filename-based fallback when MediaInfo does not detect
        French subtitles (e.g. external .srt files, untagged tracks).
        """
        for field in ("uuid", "name", "path"):
            val = str(meta.get(field, "")).upper()
            if re.search(r"(?:^|[\.\-_\s])(?:SUBFRENCH|VOSTFR)(?:[\.\-_\s]|$)", val):
                return True
        return False

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
