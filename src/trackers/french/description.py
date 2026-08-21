"""French BBCode description blocks built from MediaInfo. Maps to upbrr description.go / bbcode.go."""

import os
import re
from datetime import datetime
from typing import Any, Optional

import aiofiles

Meta = dict[str, Any]


class FrenchDescriptionMixin:
    """French BBCode description blocks built from MediaInfo. Maps to upbrr description.go / bbcode.go."""

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
                elif key == "Default":
                    current["default"] = val

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
                elif key == "Count of elements":
                    current["element_count"] = val

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
        return FrenchDescriptionMixin.TYPE_LABELS.get(raw, raw)

    @staticmethod
    def _light_encode_tag(meta: dict) -> str:
        """French-scene light re-encode label, or '' when not one.

        4KLight (2160p) and HDLight (1080p) are BluRay re-encodes; the source
        release name declares which, but it isn't a meta field, so we read it
        from ``uuid`` exactly like the C411 slot/quality detection does. Surfaced
        in the generated name (after the source) so the tag isn't dropped.
        """
        uuid = str(meta.get("uuid", "")).lower()
        if "4klight" in uuid:
            return "4KLight"
        if "hdlight" in uuid:
            return "HDLight"
        return ""

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

    # Extensions included in the torrent (video files).
    _TORRENT_EXTENSIONS: frozenset[str] = frozenset((".mkv", ".mp4", ".ts", ".m2ts", ".vob", ".avi"))

    def _count_files(self, meta: dict) -> str:
        """Count files actually included in the torrent.

        Only video extensions are counted (matching torrent creation logic
        which excludes .nfo, .jpg, .srt, etc.).
        """
        path = meta.get("path", "")
        if not path or not os.path.exists(path):
            return ""
        if os.path.isfile(path):
            return "1"
        exts = self._TORRENT_EXTENSIONS
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

        default_found = False
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

            # ── Default track detection ──
            is_default = at.get("default", "").lower() == "yes" and not default_found
            if is_default:
                default_found = True

            # ── Audio Description detection ──
            is_audio_desc = self._is_audio_desc_track(at)

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
            if is_default:
                parts.append(" (piste par défaut)")
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

        default_found = False
        for i, st in enumerate(tracks):
            lang = st.get("language", "") or "Unknown"
            flag = self._lang_to_flag(lang)
            name = self._lang_to_french_name(lang)
            fmt = st.get("format", "")
            fmt_short = self._sub_format_short(fmt) if fmt else ""
            forced = st.get("forced", "").lower() == "yes"
            is_default = st.get("default", "").lower() == "yes" and not default_found
            if is_default:
                default_found = True
            element_count = st.get("element_count", "")
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

            # Default / forced status indicator
            if is_default and forced:
                status = " (piste par défaut et forcée)"
            elif is_default:
                status = " (piste par défaut)"
            elif forced:
                status = " (piste forcée)"
            else:
                status = ""

            # Element count display
            count_part = f", {element_count} éléments" if element_count else ""

            # Parenthesized info after format: (qualifier, N éléments)
            paren_inner = f"{qualifier}{count_part}"

            parts: list[str] = [f"{flag} {name}"]
            if status:
                parts.append(status)
            if fmt_short:
                parts.append(f" : {fmt_short} ({paren_inner})" if paren_inner else f" : {fmt_short}")
            elif paren_inner:
                parts.append(f" ({paren_inner})")
            lines.append("".join(parts))
        return lines

    async def _get_mediainfo_text(self, meta: Meta) -> str:
        """Read MediaInfo text from temp files (BDInfo/in-memory fallbacks).

        The ‘Complete name’ line is patched to match the tracker-generated
        release name (some sites, e.g. C411, check the two for consistency).
        """
        base = os.path.join(meta.get("base_dir", ""), "tmp", meta.get("uuid", ""))
        content = ""

        # Prefer clean-path, then standard mediainfo
        for fname in ("MEDIAINFO_CLEANPATH.txt", "MEDIAINFO.txt"):
            fpath = os.path.join(base, fname)
            if os.path.exists(fpath):
                async with aiofiles.open(fpath, encoding="utf-8") as f:
                    content = await f.read()
                    if content.strip():
                        break
                    content = ""

        # BDInfo for disc releases
        if not content and meta.get("bdinfo") is not None:
            bd_path = os.path.join(base, "BD_SUMMARY_00.txt")
            if os.path.exists(bd_path):
                async with aiofiles.open(bd_path, encoding="utf-8") as f:
                    return await f.read()

        # Fallback: use in-memory mediainfo from prep
        if not content:
            fallback = str(meta.get("mediainfo_text") or "").strip()
            if fallback:
                content = fallback

        if not content:
            return ""

        # Patch “Complete name” to match the tracker-generated release name
        try:
            name_result = await self.get_name(meta)
            tracker_release_name = name_result.get("name", "") if isinstance(name_result, dict) else str(name_result)
            if tracker_release_name:
                content = self._patch_mi_filename(content, tracker_release_name)
        except Exception:
            pass  # If naming fails, return unpatched MI

        return content

    async def _get_source_description(self, meta: Meta) -> str:
        """Reused/base description text (tmp DESCRIPTION.txt), already cleaned
        by the description pipeline, for trackers that opt in via the
        per-tracker ``include_source_description`` config flag.

        The pipeline's own NFO embed ([spoiler=Scene NFO:] and the like) is
        stripped: French trackers already send the NFO through their API
        field, so repeating it in the description is pure redundancy.
        """
        if not self.config["TRACKERS"].get(self.tracker, {}).get("include_source_description", False):  # type: ignore[attr-defined]
            return ""
        path = os.path.join(str(meta.get("base_dir", "")), "tmp", str(meta.get("uuid", "")), "DESCRIPTION.txt")
        try:
            async with aiofiles.open(path, encoding="utf-8") as f:
                content = await f.read()
        except OSError:
            return ""
        content = re.sub(r"\[center\]\[spoiler=(?:Scene|FraMeSToR) NFO:\].*?\[/center\]", "", content, flags=re.DOTALL)
        return content.strip()

    @staticmethod
    def _format_french_date(date_str: str) -> str:
        """Format YYYY-MM-DD to French full date, e.g. 'jeudi 15 juillet 2010'."""
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            days = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
            months = [
                "",
                "janvier",
                "février",
                "mars",
                "avril",
                "mai",
                "juin",
                "juillet",
                "août",
                "septembre",
                "octobre",
                "novembre",
                "décembre",
            ]
            return f"{days[dt.weekday()]} {dt.day} {months[dt.month]} {dt.year}"
        except (ValueError, IndexError):
            return date_str
