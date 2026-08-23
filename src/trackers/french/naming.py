"""French release naming conventions. Maps to upbrr name.go."""

import re
from typing import Any

from unidecode import unidecode

from src.audio import codec_info_from_track

Meta = dict[str, Any]


class FrenchNamingMixin:
    """French release naming conventions. Maps to upbrr name.go."""

    # Subclasses may override to change the WEBDL source label in release names
    # e.g. "WEB" (C411/V3X) vs "WEB-DL" (G3MINI)
    WEB_LABEL: str = "WEB"

    # Whether to include the streaming service name (NF, AMZN, …) in the release name.
    # Set to False for trackers that want the service only in the description.
    INCLUDE_SERVICE_IN_NAME: bool = True

    # Whether to prefer the original-language title in release names.
    # When True and the movie is not originally French, the English/original
    # title is used instead of the French TMDB translation.
    # Set to True for trackers that accept both title languages (e.g. NST).
    PREFER_ORIGINAL_TITLE: bool = False

    # Whether the "UHD" tag should only appear for REMUX / DISC releases.
    # C411 wiki: "UHD is only allowed when the title contains REMUX/BDMV/ISO".
    # When True, UHD is stripped from ENCODE, WEBDL, WEBRIP, HDTV, DVDRIP.
    UHD_ONLY_FOR_REMUX_DISC: bool = False

    # Subclasses may set this to a non-empty string to accept notag releases
    # with a replacement label (e.g. "NOTAG", "NoGrp").
    notag_label: str = ""

    @staticmethod
    def _format_edition(edition: str) -> str:
        """Convert an uppercased edition to title case for French trackers.

        French trackers use title case for edition keywords:
        ``SPECIAL EDITION`` → ``Special Edition``,
        ``DIRECTOR'S CUT`` → ``Director's Cut``, etc.

        Mixed-case scene-style tags (e.g. ``LiMiTED``) are preserved as-is.
        """
        if not edition:
            return edition
        # Only title-case fully uppercased strings; preserve scene-style
        # mixed-case tags like "LiMiTED" unchanged.
        if edition != edition.upper():
            return edition
        result = edition.title()
        # Fix capitalization after apostrophes: "Director'S" → "Director's"
        result = re.sub(r"(\w)'(\w)", lambda m: f"{m.group(1)}'{m.group(2).lower()}", result)
        return result

    def _should_include_ad_prefix(self, has_french_audio: bool, ad_audio_langs: list[str]) -> bool:
        """Whether to include the ``AD.`` prefix in the release name.

        Subclasses may override for tracker-specific rules.
        """
        return True

    def _get_audio_for_name(self, meta: Meta) -> str:
        """Return the audio codec+channels string for the release name.

        Base implementation uses ``meta['audio']`` (first track in stream
        order).  Subclasses may override to pick a different track, e.g.
        the first French audio track for French-tracker NFO validation.
        """

        lossless_additional_features = ["XLL", "HD MA", ":X", "16-ch", "MLP FBA"]
        lossless_tracks = []
        lossy_tracks = []
        audio_tracks = self._get_audio_tracks(meta)

        main_tracks = [
            t
            for t in audio_tracks
            if not self._is_audio_desc_track(t) and "compatibility" not in str(t.get("Title", t.get("title", ""))).lower() and t.get("Channels") and t.get("Format")
        ]

        if not main_tracks:  # Fallback if no "main tracks" was found
            return meta.get("audio", "").replace("Dual-Audio", "").replace("Dubbed", "").replace("DD+", "DDP")

        def most_channels_priority(t):
            channels = int(t.get("Channels", "0"))
            is_french = 1 if self._map_language(str(t.get("Language", ""))) == "FRA" else 0
            return (channels, is_french)

        for t in main_tracks:
            is_lossless = (
                t.get("Compression_Mode") == "Lossless"
                or any(f in str(t.get("Format_AdditionalFeatures", "")) for f in lossless_additional_features)
                or any(f in str(t.get("Format_Commercial_IfAny", "")) for f in lossless_additional_features)
            )
            if is_lossless:
                lossless_tracks.append(t)
            else:
                lossy_tracks.append(t)

        if lossless_tracks:
            return codec_info_from_track(max(lossless_tracks, key=most_channels_priority)).replace("Dual-Audio", "").replace("Dubbed", "").replace("DD+", "DDP")
        elif lossy_tracks:
            return codec_info_from_track(max(lossy_tracks, key=most_channels_priority)).replace("Dual-Audio", "").replace("Dubbed", "").replace("DD+", "DDP")

        return meta.get("audio", "").replace("Dual-Audio", "").replace("Dubbed", "").replace("DD+", "DDP")

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

        ad_audio_tracks = [track for track in audio_tracks if self._is_audio_desc_track(track)]
        main_audio_tracks = [track for track in audio_tracks if not self._is_audio_desc_track(track)]

        audio_langs = self._extract_audio_languages(main_audio_tracks, meta)
        if not audio_langs and not ad_audio_tracks:
            return ""

        has_french_audio = "FRA" in audio_langs
        has_french_subs = self._has_french_subs(meta)
        num_audio_tracks = len(main_audio_tracks)
        fr_suffix = self._get_french_dub_suffix(main_audio_tracks)
        ad_audio_langs = self._extract_audio_languages(ad_audio_tracks)
        has_non_french_ad = any(lang != "FRA" for lang in ad_audio_langs)
        has_audiodesc = bool(meta.get("has_audiodesc") or ad_audio_tracks)
        is_original_french = str(meta.get("original_language", "")).lower() == "fr"
        is_truefrench = self._detect_truefrench(meta)
        is_vfi = self._detect_vfi(meta)
        is_vfq_filename = self._detect_vfq(meta)
        is_vfb_filename = self._detect_vfb(meta)
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
                # Original French production. Distinguish Québec (fr-CA audio) from
                # France: a Québécois original is VOQ, a French one VOF. Filename VFQ
                # only counts as a fallback when MediaInfo carries no explicit region,
                # so an explicit fr-FR (VFF) is never overridden to VOQ.
                if fr_suffix == "VFQ" or (not fr_suffix and is_vfq_filename):
                    return "VOQ"
                return "VOF"
            if is_vfi:
                return "VFI"
            if fr_suffix == "VFQ":
                return "VFQ"
            if fr_suffix == "VFB":
                return "VFB"
            if fr_suffix == "VFF":
                return "VFF"
            # MediaInfo has generic 'fr' without region — check filename
            if is_vfq_filename:
                return "VFQ"
            if is_vfb_filename:
                return "VFB"
            if is_vff_filename or is_truefrench:
                return "VFF"
            # Generic 'fr' without region — conservative default
            return "VFF"

        # ── No French audio ──
        if not has_french_audio:
            # MediaInfo subs OR filename hint (SUBFRENCH / VOSTFR)
            language = "VOSTFR" if has_french_subs or self._detect_subfrench(meta) else ""
        # ── MULTi — 2+ audio tracks (or non-French track present) ──
        elif [la for la in audio_langs if la != "FRA"] or num_audio_tracks > 1 or has_non_french_ad:
            language = f"MULTI.{_fr_precision()}"
        # ── Single French track ──
        else:
            # Includes the original-French case: _fr_precision() returns VOF, or
            # VOQ when the original audio is Québécois (fr-CA).
            language = _fr_precision()

        # ── Audio Description prefix ──
        if language and has_audiodesc and self._should_include_ad_prefix(has_french_audio, ad_audio_langs):
            language = f"AD.{language}"

        return language

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

    async def french_synopsis(self, meta: Meta, fr_data: dict[str, Any]) -> str:
        """Synopsis for a French fiche: TMDB French, else the IMDb French plot, else TMDB English."""
        synopsis = str(fr_data.get("overview", "")).strip()
        if not synopsis and meta.get("imdb_id"):
            from src.imdb import imdb_manager

            synopsis = await imdb_manager.get_imdb_plot(meta["imdb_id"], "fr-FR")
        return synopsis or str(meta.get("overview", "")).strip()

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
        audio = self._get_audio_for_name(meta)
        service = meta.get("service", "") if self.INCLUDE_SERVICE_IN_NAME else ""
        season = meta.get("season", "")
        episode = meta.get("episode", "")
        part = meta.get("part", "")
        repack = meta.get("repack", "")
        three_d = meta.get("3D", "")
        tag = meta.get("tag", "")
        source = meta.get("source", "")
        light = self._light_encode_tag(meta)
        uhd = meta.get("uhd", "")
        hdr = meta.get("hdr", "").replace("HDR10+", "HDR10PLUS")
        hybrid = str(meta.get("webdv", "")) if meta.get("webdv", "") else ""
        edition = self._format_edition(meta.get("edition", ""))
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
            video_codec = meta.get("video_codec", "").replace("H.264", "H264").replace("H.265", "H265").replace("VC-1", "VC1")
            region = meta.get("region", "") or ""
        elif meta.get("is_disc") == "DVD":
            region = meta.get("region", "") or ""
            dvd_size = meta.get("dvd_size", "")
        else:
            video_codec = meta.get("video_codec", "").replace("H.264", "H264").replace("H.265", "H265").replace("VC-1", "VC1")
            video_encode = meta.get("video_encode", "").replace("H.264", "H264").replace("H.265", "H265").replace("VC-1", "VC1")

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

        # Some trackers want video codec before audio.
        # Set AUDIO_BEFORE_VIDEO = False on the subclass to flip the order.
        _audio_first = getattr(self, "AUDIO_BEFORE_VIDEO", True)

        def _av(codec: str, aud: str) -> str:
            return f"{aud} {codec}" if _audio_first else f"{codec} {aud}"

        name = ""

        # ── MOVIE ──
        if category == "MOVIE":
            if type_val == "DISC":
                disc = meta.get("is_disc", "")
                if disc == "BDMV":
                    name = f"{title} {year} {three_d} {edition} {repack} {language} {resolution} {hybrid} {region} {uhd} {source} {hdr} {_av(video_codec, audio)}"
                elif disc == "DVD":
                    name = f"{title} {year} {edition} {repack} {language} {region} {source} {dvd_size} {audio}"
                elif disc == "HDDVD":
                    name = f"{title} {year} {edition} {repack} {language} {resolution} {source} {_av(video_codec, audio)}"
            elif type_val == "REMUX" and source in ("BluRay", "HDDVD"):
                name = f"{title} {year} {three_d} {edition} {repack} {language} {resolution} {hybrid} {uhd} {source} REMUX {hdr} {_av(video_codec, audio)}"
            elif type_val == "REMUX" and source in ("PAL DVD", "NTSC DVD", "DVD"):
                name = f"{title} {year} {edition} {repack} {language} {source} REMUX {audio}"
            elif type_val == "REMUX":
                name = f"{title} {year} {edition} {repack} {language} {resolution} {hybrid} {uhd} {source} REMUX {hdr} {_av(video_codec, audio)}"
            elif type_val == "ENCODE":
                name = f"{title} {year} {edition} {repack} {language} {resolution} {hybrid} {uhd} {source} {light} {hdr} {_av(video_encode, audio)}"
            elif type_val == "WEBDL":
                name = f"{title} {year} {edition} {repack} {language} {resolution} {hybrid} {uhd} {service} {web_lbl} {hdr} {_av(video_encode, audio)}"
            elif type_val == "WEBRIP":
                name = f"{title} {year} {edition} {repack} {language} {resolution} {hybrid} {uhd} {service} WEBRip {hdr} {_av(video_encode, audio)}"
            elif type_val == "HDTV":
                name = f"{title} {year} {edition} {repack} {language} {resolution} {source} {_av(video_encode, audio)}"
            elif type_val == "DVDRIP":
                name = f"{title} {year} {repack} {language} {source} DVDRip {_av(video_encode, audio)}"

        # ── TV ──
        elif category == "TV":
            se = f"{season}{episode}"
            if type_val == "DISC":
                disc = meta.get("is_disc", "")
                if disc == "BDMV":
                    name = f"{title} {year} {se} {three_d} {edition} {repack} {language} {resolution} {hybrid} {region} {uhd} {source} {hdr} {_av(video_codec, audio)}"
                elif disc == "DVD":
                    name = f"{title} {year} {se} {three_d} {edition} {repack} {language} {region} {source} {dvd_size} {audio}"
                elif disc == "HDDVD":
                    name = f"{title} {year} {se} {edition} {repack} {language} {resolution} {source} {_av(video_codec, audio)}"
            elif type_val == "REMUX" and source in ("BluRay", "HDDVD"):
                name = f"{title} {year} {se} {part} {three_d} {edition} {repack} {language} {resolution} {hybrid} {uhd} {source} REMUX {hdr} {_av(video_codec, audio)}"
            elif type_val == "REMUX" and source in ("PAL DVD", "NTSC DVD", "DVD"):
                name = f"{title} {year} {se} {part} {edition} {repack} {language} {source} REMUX {audio}"
            elif type_val == "REMUX":
                name = f"{title} {year} {se} {part} {edition} {repack} {language} {resolution} {hybrid} {uhd} {source} REMUX {hdr} {_av(video_codec, audio)}"
            elif type_val == "ENCODE":
                name = f"{title} {year} {se} {part} {edition} {repack} {language} {resolution} {hybrid} {uhd} {source} {light} {hdr} {_av(video_encode, audio)}"
            elif type_val == "WEBDL":
                name = f"{title} {year} {se} {part} {edition} {repack} {language} {resolution} {hybrid} {uhd} {service} {web_lbl} {hdr} {_av(video_encode, audio)}"
            elif type_val == "WEBRIP":
                name = f"{title} {year} {se} {part} {edition} {repack} {language} {resolution} {hybrid} {uhd} {service} WEBRip {hdr} {_av(video_encode, audio)}"
            elif type_val == "HDTV":
                name = f"{title} {year} {se} {part} {edition} {repack} {language} {resolution} {source} {_av(video_encode, audio)}"
            elif type_val == "DVDRIP":
                name = f"{title} {year} {se} {repack} {language} {source} DVDRip {_av(video_encode, audio)}"

        if not name:
            name = f"{title} {year} {language} {resolution} {type_val} {_av(video_encode, audio)}"

        # ── Post-processing ──
        name = " ".join(name.split())  # collapse whitespace

        # Handle notag: if tag is empty/invalid and tracker accepts notag, use the label
        tag_group = tag.strip("-").strip().lower() if tag else ""
        invalid_tags = ["nogrp", "nogroup", "unknown", "unk"]
        if not tag_group or any(inv == tag_group for inv in invalid_tags):
            label = getattr(self, "notag_label", "")
            if label:
                tag = f"-{label}"

        name = name + tag  # tag starts with '-', no space needed

        return self._format_name(name)

    @staticmethod
    def _normalize_audio_name_tokens(dot_name: str) -> str:
        """Normalize audio codec tokens in a dotted release name to the
        French-scene convention: DD→AC3, TRUEHD, DTS.HD.MA, DTS.X, and
        ATMOS placed between the codec and the channel count.
        """
        # DD → AC3 (but not DDP which stays as-is)
        dot_name = re.sub(r"\.DD\.", ".AC3.", dot_name)
        # TrueHD → TRUEHD (case normalization)
        dot_name = re.sub(r"\.TrueHD\.", ".TRUEHD.", dot_name, flags=re.IGNORECASE)
        dot_name = re.sub(r"\.TrueHD$", ".TRUEHD", dot_name, flags=re.IGNORECASE)
        # DTS-HD.MA → DTS.HD.MA (dash to dot)
        dot_name = dot_name.replace(".DTS-HD.MA.", ".DTS.HD.MA.")
        dot_name = dot_name.replace(".DTS-HD.HRA.", ".DTS.HD.HRA.")
        # DTS:X → DTS.X (colon to dot)
        dot_name = dot_name.replace(".DTS:X.", ".DTS.X.")
        dot_name = dot_name.replace(".DTSX.", ".DTS.X.")
        # Atmos capitalization
        dot_name = re.sub(r"\.Atmos\.", ".ATMOS.", dot_name, flags=re.IGNORECASE)
        dot_name = re.sub(r"\.Atmos$", ".ATMOS", dot_name, flags=re.IGNORECASE)
        # ATMOS must appear AFTER the audio codec and BEFORE audio channels : DDP.5.1.ATMOS → DDP.ATMOS.5.1
        # Pattern 1: codec.channels.ATMOS → codec.ATMOS.channels
        dot_name = re.sub(r"\.(DDP|AC3|EAC3|DTS|TRUEHD|FLAC|AAC|LPCM|DTS\.HD\.MA|DTS\.HD\.HRA|DTS\.X)\.(\d\.\d)\.ATMOS([.-])", r".\1.ATMOS.\2\3", dot_name, flags=re.IGNORECASE)
        # Pattern 2: ATMOS.codec.channels → codec.ATMOS.channels
        dot_name = re.sub(r"\.ATMOS\.(DDP|AC3|EAC3|DTS|TRUEHD|FLAC|AAC|LPCM|DTS\.HD\.MA|DTS\.HD\.HRA|DTS\.X)\.(\d\.\d)([.-])", r".\1.ATMOS.\2\3", dot_name, flags=re.IGNORECASE)
        return dot_name

    @staticmethod
    def _enforce_web_codec_convention(meta: Meta, name: str) -> str:
        """WEB codec token per the actual MediaInfo, not the type label:
        untouched WEB streams (no Encoded_Library_Settings) use H264/H265,
        re-encodes use x264/x265.
        """
        if str(meta.get("type", "")).upper() in ("WEBDL", "WEBRIP"):
            if meta.get("has_encode_settings", False):
                name = re.sub(r"\.H264\b", ".x264", name, flags=re.IGNORECASE)
                name = re.sub(r"\.H265\b", ".x265", name, flags=re.IGNORECASE)
            else:
                name = re.sub(r"\.x264\b", ".H264", name, flags=re.IGNORECASE)
                name = re.sub(r"\.x265\b", ".H265", name, flags=re.IGNORECASE)
        return name

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
        the apostrophe becomes a space while preserving the original case:
        ``l'autre`` → ``l autre``, ``L'Ordre`` → ``L Ordre``.
        """
        import unicodedata

        # Normalise to NFC first so that combining-character sequences
        # (e.g. U+0065 U+0301 for "é") are collapsed into their
        # precomposed form before unidecode sees them.  Without this,
        # unidecode turns the bare combining accent (U+0301) into an
        # empty string, silently dropping the following vowel.
        text = unicodedata.normalize("NFC", text)
        for char, repl in FrenchNamingMixin._TITLE_CHAR_MAP.items():
            text = text.replace(char, repl)
        text = unidecode(text)
        # Replace apostrophes / RIGHT SINGLE QUOTATION MARK / backticks
        # that follow a French elided article with a space, preserving
        # the original case:  l'autre → l autre,  L'Ordre → L Ordre
        text = re.sub(
            r"\b([lLdDnNsScCjJmM]|[Qq]u|[Jj]usqu|[Ll]orsqu|[Pp]uisqu)['\u2019`]",
            lambda m: m.group(1) + " ",
            text,
        )
        return re.sub(r"[^a-zA-Z0-9 .+\-]", "", text)
