# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import os
import platform
import re
from typing import Any

import aiofiles
import cli_ui
import httpx
import pycountry

from src.bbcode import BBCODE
from src.console import console
from src.trackers.COMMON import COMMON


class ACM:
    # ISO 3166-1 alpha-2 codes for Asian countries
    # Reference: https://en.wikipedia.org/wiki/List_of_Asian_countries_by_area
    ASIAN_COUNTRIES: frozenset[str] = frozenset(
        {
            "AF",  # Afghanistan
            "AE",  # United Arab Emirates
            "AM",  # Armenia
            "AZ",  # Azerbaijan
            "BD",  # Bangladesh
            "BH",  # Bahrain
            "BN",  # Brunei
            "BT",  # Bhutan
            "CN",  # China
            "CY",  # Cyprus
            "GE",  # Georgia
            "HK",  # Hong Kong
            "ID",  # Indonesia
            "IL",  # Israel
            "IN",  # India
            "IQ",  # Iraq
            "IR",  # Iran
            "JO",  # Jordan
            "JP",  # Japan
            "KG",  # Kyrgyzstan
            "KH",  # Cambodia
            "KP",  # North Korea
            "KR",  # South Korea
            "KW",  # Kuwait
            "KZ",  # Kazakhstan
            "LA",  # Laos
            "LB",  # Lebanon
            "LK",  # Sri Lanka
            "MM",  # Myanmar
            "MN",  # Mongolia
            "MO",  # Macao
            "MV",  # Maldives
            "MY",  # Malaysia
            "NP",  # Nepal
            "OM",  # Oman
            "PH",  # Philippines
            "PK",  # Pakistan
            "PS",  # Palestine
            "QA",  # Qatar
            "RU",  # Russia
            "SA",  # Saudi Arabia
            "SG",  # Singapore
            "SY",  # Syria
            "TH",  # Thailand
            "TJ",  # Tajikistan
            "TL",  # East Timor
            "TM",  # Turkmenistan
            "TR",  # Turkey
            "TW",  # Taiwan
            "UZ",  # Uzbekistan
            "VN",  # Vietnam
            "YE",  # Yemen
        }
    )

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.common = COMMON(config)
        self.tracker = "ACM"
        self.source_flag = "AsianCinema"
        self.base_url = "https://eiga.moi"
        self.id_url = f"{self.base_url}/api/torrents/"
        self.upload_url = f"{self.base_url}/api/torrents/upload"
        self.search_url = f"{self.base_url}/api/torrents/filter"
        self.torrent_url = f"{self.base_url}/torrents/"
        self.approved_image_hosts = ["imgbox", "imgbb", "postimg", "pixhost", "ptpimg", "imagebam"]
        self.banned_groups: list[str] = []

    async def get_type_id(self, meta: dict[str, Any]) -> str:
        if meta["is_disc"] == "BDMV":
            bdinfo = meta["bdinfo"]
            bd_sizes = [25, 50, 66, 100]
            bd_size = 100  # Default to largest size
            for each in bd_sizes:
                if bdinfo["size"] < each:
                    bd_size = each
                    break
            type_string = f"UHD {bd_size}" if meta["uhd"] == "UHD" and bd_size != 25 else f"BD {bd_size}"
            # if type_id not in ['UHD 100', 'UHD 66', 'UHD 50', 'BD 50', 'BD 25']:
            #     type_id = "Other"
        elif meta["is_disc"] == "DVD":
            if "DVD5" in meta["dvd_size"]:
                type_string = "DVD 5"
            elif "DVD9" in meta["dvd_size"]:
                type_string = "DVD 9"
            else:
                type_string = "Other"
        else:
            type_string = ("UHD REMUX" if meta["uhd"] == "UHD" else "REMUX") if meta["type"] == "REMUX" else meta["type"]
            # else:
            #     acceptable_res = ["2160p", "1080p", "1080i", "720p", "576p", "576i", "540p", "480p", "Other"]
            #     if meta['resolution'] in acceptable_res:
            #         type_id = meta['resolution']
            #     else:
            #         type_id = "Other"

        type_id_map = {
            "UHD 100": "1",
            "UHD 66": "2",
            "UHD 50": "3",
            "UHD REMUX": "12",
            "BD 50": "4",
            "BD 25": "5",
            "DVD 5": "14",
            "REMUX": "7",
            "WEBDL": "9",
            "SDTV": "13",
            "DVD 9": "16",
            "HDTV": "17",
        }
        type_id = type_id_map.get(type_string, "0")

        return type_id

    async def get_cat_id(self, category_name: str) -> str:
        category_id = {
            "MOVIE": "1",
            "TV": "2",
        }.get(category_name, "0")
        return category_id

    async def get_resolution_id(self, meta: dict[str, Any]) -> str:
        resolution_id = {"2160p": "1", "1080p": "2", "1080i": "2", "720p": "3", "576p": "4", "576i": "4", "480p": "5", "480i": "5"}.get(meta["resolution"], "10")
        return resolution_id

    # ACM rejects uploads with more that 10 keywords
    async def get_keywords(self, meta: dict[str, Any]) -> str:
        keywords: str = str(meta.get("keywords", ""))
        if keywords != "":
            keywords_list = keywords.split(",")
            keywords_list = [keyword.strip() for keyword in keywords_list if " " not in keyword.strip()][:10]
            keywords = ", ".join(keywords_list)
        return keywords

    def get_subtitles(self, meta: dict[str, Any]) -> list[str]:
        sub_lang_map: dict[tuple[str, ...], str] = {
            ("Arabic", "ara", "ar"): "Ara",
            ("Brazilian Portuguese", "Brazilian", "Portuguese-BR", "pt-br"): "Por-BR",
            ("Bulgarian", "bul", "bg"): "Bul",
            ("Chinese", "chi", "zh", "Chinese (Simplified)", "Chinese (Traditional)"): "Chi",
            ("Croatian", "hrv", "hr", "scr"): "Cro",
            ("Czech", "cze", "cz", "cs"): "Cze",
            ("Danish", "dan", "da"): "Dan",
            ("Dutch", "dut", "nl"): "Dut",
            ("English", "eng", "en", "English (CC)", "English - SDH"): "Eng",
            ("English - Forced", "English (Forced)", "en (Forced)"): "Eng",
            ("English Intertitles", "English (Intertitles)", "English - Intertitles", "en (Intertitles)"): "Eng",
            ("Estonian", "est", "et"): "Est",
            ("Finnish", "fin", "fi"): "Fin",
            ("French", "fre", "fr"): "Fre",
            ("German", "ger", "de"): "Ger",
            ("Greek", "gre", "el"): "Gre",
            ("Hebrew", "heb", "he"): "Heb",
            ("Hindi", "hin", "hi"): "Hin",
            ("Hungarian", "hun", "hu"): "Hun",
            ("Icelandic", "ice", "is"): "Ice",
            ("Indonesian", "ind", "id"): "Ind",
            ("Italian", "ita", "it"): "Ita",
            ("Japanese", "jpn", "ja"): "Jpn",
            ("Korean", "kor", "ko"): "Kor",
            ("Latvian", "lav", "lv"): "Lav",
            ("Lithuanian", "lit", "lt"): "Lit",
            ("Norwegian", "nor", "no"): "Nor",
            ("Persian", "fa", "far"): "Per",
            ("Polish", "pol", "pl"): "Pol",
            ("Portuguese", "por", "pt"): "Por",
            ("Romanian", "rum", "ro"): "Rom",
            ("Russian", "rus", "ru"): "Rus",
            ("Serbian", "srp", "sr", "scc"): "Ser",
            ("Slovak", "slo", "sk"): "Slo",
            ("Slovenian", "slv", "sl"): "Slv",
            ("Spanish", "spa", "es"): "Spa",
            ("Swedish", "swe", "sv"): "Swe",
            ("Thai", "tha", "th"): "Tha",
            ("Turkish", "tur", "tr"): "Tur",
            ("Ukrainian", "ukr", "uk"): "Ukr",
            ("Vietnamese", "vie", "vi"): "Vie",
        }

        sub_langs: list[str] = []
        if meta.get("is_disc", "") != "BDMV":
            mi = meta["mediainfo"]
            for track in mi["media"]["track"]:
                if track["@type"] == "Text":
                    language = track.get("Language")
                    if language == "en":
                        if track.get("Forced", "") == "Yes":
                            language = "en (Forced)"
                        title = track.get("Title", "")
                        if isinstance(title, str) and "intertitles" in title.lower():
                            language = "en (Intertitles)"
                    # Try exact match first, then fall back to the base language
                    # tag so that BCP 47 regional codes (e.g. "en-US", "zh-Hans",
                    # "pt-BR") are still recognised.
                    found = False
                    for lang, subID in sub_lang_map.items():
                        if language in lang and subID not in sub_langs:
                            sub_langs.append(subID)
                            found = True
                    if not found and language and "-" in language:
                        base_lang = language.split("-")[0]
                        for lang, subID in sub_lang_map.items():
                            if base_lang in lang and subID not in sub_langs:
                                sub_langs.append(subID)
                                break
        else:
            for language in meta["bdinfo"]["subtitles"]:
                for lang, subID in sub_lang_map.items():
                    if language in lang and subID not in sub_langs:
                        sub_langs.append(subID)

        # if sub_langs == []:
        #     sub_langs = [44] # No Subtitle
        return sub_langs

    def get_subs_tag(self, subs: list[str]) -> str:
        if subs == []:
            return " [No subs]"
        elif "Eng" in subs:
            return ""
        elif len(subs) > 1:
            return " [No Eng subs]"
        return f" [{subs[0]} subs only]"

    # Audio/subtitle language codes and names → ACM's title-case abbreviation.
    _LANG_ABBR: dict[str, set[str]] = {
        "Jpn": {"ja", "jpn", "jp", "japanese"},
        "Kor": {"ko", "kor", "korean"},
        "Chi": {"zh", "chi", "zho", "cmn", "yue", "chinese", "mandarin", "cantonese"},
        "Tha": {"th", "tha", "thai"},
        "Vie": {"vi", "vie", "vietnamese"},
        "Hin": {"hi", "hin", "hindi"},
        "Eng": {"en", "eng", "english"},
        "Fre": {"fr", "fre", "fra", "french"},
        "Ger": {"de", "ger", "deu", "german"},
        "Spa": {"es", "spa", "spanish"},
        "Ita": {"it", "ita", "italian"},
    }

    def _lang_abbr(self, code: Any) -> str:
        """Map a language code/name (e.g. 'ja', 'jpn', 'Japanese', 'ja-JP') to 'Jpn'."""
        value = str(code or "").lower().strip().split("-")[0]
        for abbr, forms in self._LANG_ABBR.items():
            if value in forms:
                return abbr
        return ""

    def _dub_only_abbr(self, meta: dict[str, Any]) -> str:
        """Return the dub language abbreviation when the only audio is a non-original dub.

        Empty when there's original audio, multiple audio languages, or the original
        language is unknown (can't tell it's a dub).
        """
        tracks = ((meta.get("mediainfo") or {}).get("media") or {}).get("track") or []
        abbrs: set[str] = set()
        for track in tracks:
            if not isinstance(track, dict) or track.get("@type") != "Audio":
                continue
            if "commentary" in str(track.get("Title", "") or "").lower():
                continue
            abbr = self._lang_abbr(track.get("Language"))
            if abbr:
                abbrs.add(abbr)
        if len(abbrs) != 1:
            return ""
        dub = abbrs.pop()
        original = self._lang_abbr(meta.get("original_language"))
        # Only a dub if we know the original and the sole audio differs from it.
        return dub if original and dub != original else ""

    def _language_tag(self, meta: dict[str, Any], subs: list[str]) -> str:
        """Build the trailing language tag, merging a dub-only marker with the subs tag."""
        subs_tag = self.get_subs_tag(subs)
        dub = self._dub_only_abbr(meta)
        if not dub:
            return subs_tag
        inner = subs_tag.strip().strip("[]").strip()
        return f" [{dub} dub only, {inner}]" if inner else f" [{dub} dub only]"

    @staticmethod
    def _normalize_countries(meta: dict[str, Any]) -> tuple[list[str], list[str]]:
        """Return (production_codes, origin_codes) as upper-cased ISO strings.

        Safely coerces both TMDB fields into lists of non-empty strings, tolerating
        ``None`` values and malformed entries (non-dict production countries, etc.).
        """
        prod = [str(pc.get("iso_3166_1", "")).strip().upper() for pc in (meta.get("production_countries") or []) if isinstance(pc, dict)]
        prod = [c for c in prod if c]
        origin = [c.strip().upper() for c in (meta.get("origin_country") or []) if isinstance(c, str) and c.strip()]
        return prod, origin

    def check_asian_origin(self, meta: dict[str, Any]) -> bool:
        """Return True only when *every* production country is Asian.

        A single non-Asian partner disqualifies the release: a Franco-Japanese
        co-production (e.g. Wasabi, produced in FR+JP) or a Japanese show
        co-produced with a US studio are both rejected.  Uses TMDB
        ``production_countries`` as the authoritative signal and falls back to
        ``origin_country`` only when no production countries are provided.
        """
        prod, origin = self._normalize_countries(meta)
        codes = prod or origin
        return bool(codes) and all(code in self.ASIAN_COUNTRIES for code in codes)

    async def get_additional_checks(self, meta: dict[str, Any]) -> bool:
        """Check ACM-specific requirements before searching/uploading."""

        def _deny(msg: str) -> bool:
            if not bool(meta.get("unattended")):
                console.print(msg)
            return False

        # ── Asian origin ────────────────────────────────────────────────────────
        if not self.check_asian_origin(meta):
            prod, origin = self._normalize_countries(meta)
            countries = ", ".join(dict.fromkeys(origin + prod)) or "Unknown"
            return _deny(f"[bold red]Only media produced in Asian countries is allowed at {self.tracker}.[/bold red]\n[red]Detected production countries: {countries}[/red]")

        # ── Release type ────────────────────────────────────────────────────────
        # Encodes and WEBRiPs are re-encodes and not allowed. HDTV/SDTV broadcasts
        # ARE allowed (TS/TP/MKV) as long as they weren't re-encoded — a raw capture
        # carries no encoder settings, whereas an HDTVRip does.
        release_type = str(meta.get("type", "")).upper()
        if release_type in ("ENCODE", "WEBRIP"):
            return _deny(
                f"[bold red]Encodes are not allowed at {self.tracker}.[/bold red]\n[red]Detected type: {release_type}. Only REMUX, WEB-DL, full discs, and untouched HDTV/SDTV broadcasts are allowed.[/red]"
            )
        if release_type == "HDTV" and meta.get("has_encode_settings"):
            return _deny(
                f"[bold red]{self.tracker}: Re-encoded HDTV (HDTVRip) is not allowed.[/bold red]\n"
                "[red]Only untouched broadcast captures (TS/TP/MKV without encoder settings) are permitted.[/red]"
            )

        # ── DVD source: only for pre-2010 titles with no HD available ────────────
        # "No HD available" can't be detected automatically, so this is enforced on
        # year only: a DVD source (full disc or DVD remux) for a 2010-or-later title
        # is rejected. Pre-2010 is allowed — the uploader judges HD availability.
        is_dvd_source = meta.get("is_disc") == "DVD" or str(meta.get("source", "") or "").upper().endswith("DVD")
        if is_dvd_source:
            try:
                year_val = int(str(meta.get("year", "") or "").strip()[:4])
            except ValueError:
                year_val = 0
            if year_val >= 2010:
                return _deny(
                    f"[bold red]{self.tracker}: DVD sources are only allowed for pre-2010 titles with no HD available.[/bold red]\n"
                    f"[red]Detected year: {year_val or 'unknown'}.[/red]"
                )

        # ── Single TV episodes — only allowed for currently-airing shows ─────────
        # A single episode (not a season pack) is prohibited unless the show is
        # currently airing, which can't be detected reliably — so ask the uploader.
        if meta.get("category") == "TV" and not meta.get("tv_pack") and str(meta.get("episode", "")).strip():
            if bool(meta.get("unattended")):
                return _deny(
                    f"[bold red]{self.tracker}: Single TV episodes are only allowed for currently-airing shows.[/bold red]\n"
                    "[red]This can't be confirmed in unattended mode — skipping.[/red]"
                )
            console.print(f"[bold yellow]{self.tracker}: Single episodes are only allowed for shows that are currently airing.[/bold yellow]")
            if not cli_ui.ask_yes_no("Is this show currently airing?", default=False):
                return False

        # ── Adult content (hentai, porn, JAV) ────────────────────────────────────
        # TMDB keywords are not always reliable, so this is a soft block: the user
        # can override if the detection is a false positive.
        genres_combined = f"{meta.get('keywords', '') or ''} {meta.get('combined_genres', '') or ''}".lower()
        adult_keywords = ["hentai", "xxx", "porn", "erotic", "adult animation", "softcore", "orgy", "jav", "japanese adult video"]
        if any(re.search(rf"(^|[,\s]){re.escape(kw)}([,\s]|$)", genres_combined) for kw in adult_keywords):
            if not bool(meta.get("unattended")) or (bool(meta.get("unattended")) and meta.get("unattended_confirm", False)):
                console.print(f"[bold red]{self.tracker}: Adult, hentai, and JAV content is not permitted.[/bold red]")
                console.print("[yellow]Note: TMDB keywords may not be reliable — override if this is a false positive.[/yellow]")
                if not cli_ui.ask_yes_no("Do you want to upload anyway?", default=False):
                    return False
            else:
                return False

        # BDMV full-disc structures are allowed (that's the primary Blu-ray format).
        # Only raw ISOs are restricted to 3D/MGVC, but UA never uploads ISOs — it
        # always works from a BDMV folder structure — so there's nothing to block.

        # ── R5 BDs (Digital TeleCine recordings) ─────────────────────────────────
        name_lower = str(meta.get("name", "") or "").lower()
        source_lower = str(meta.get("source", "") or "").lower()
        if re.search(r"\br5\b", name_lower) or re.search(r"\br5\b", source_lower):
            return _deny(f"[bold red]{self.tracker}: R5 BD (Digital TeleCine) releases are not allowed.[/bold red]")

        # ── Upscales ──────────────────────────────────────────────────────────────
        if re.search(r"\bupscal", name_lower):
            return _deny(f"[bold red]{self.tracker}: Upscaled releases are not allowed.[/bold red]")

        # ── Releases with URLs embedded in name or tag ───────────────────────────
        # Groups like HDWebMovies, XDMovies embed URLs in their release names.
        # False positives are possible (e.g. Apple.TV service tags, .io group names),
        # so this is a soft block — the user can override if it's a false positive.
        tag_clean = str(meta.get("tag", "") or "").lower().replace("-", "")
        if re.search(r"\.(com|net|org|info|io|me|tk|xyz|cc|tv)\b", name_lower + " " + tag_clean):
            if not bool(meta.get("unattended")) or (bool(meta.get("unattended")) and meta.get("unattended_confirm", False)):
                console.print(f"[bold red]{self.tracker}: Releases with URLs embedded in their name or tag are not allowed.[/bold red]")
                console.print("[yellow]E.g. HDWebMovies, XDMovies and similar URL-tagged groups are prohibited.[/yellow]")
                console.print("[yellow]Note: false positives are possible (e.g. service tags like Apple.TV) — override if needed.[/yellow]")
                if not cli_ui.ask_yes_no("Do you want to upload anyway?", default=False):
                    return False
            else:
                return False

        # ── Hybrid WEB-DL: audio replaced with Blu-ray audio ─────────────────────
        # Streaming services don't deliver FLAC/LPCM, so this audio came from a disc.
        # ACM allows such hybrids but they need BDInfo + eac3to logs, same as a REMUX
        # — so we require confirmation and reject unattended (logs can't be added).
        if release_type == "WEBDL":
            audio_codec = str(meta.get("audio", "") or "").upper()
            # Match anywhere, not just as a prefix: "Dual-Audio FLAC 2.0" is
            # still a disc-sourced hybrid.
            hybrid_codec = re.search(r"\b(FLAC|LPCM)\b", audio_codec)
            if hybrid_codec:
                if bool(meta.get("unattended")):
                    return _deny(
                        f"[bold red]{self.tracker}: hybrid WEB-DL ({hybrid_codec.group(1)} audio from a disc) requires BDInfo + eac3to logs.[/bold red]\n"
                        "[red]This can't be provided in unattended mode — skipping.[/red]"
                    )
                console.print(
                    f"[bold yellow]{self.tracker}: this looks like a hybrid WEB-DL ({hybrid_codec.group(1)} audio sourced from a disc). "
                    "It needs BDInfo and eac3to logs under spoilers, same as a REMUX.[/bold yellow]"
                )
                if not cli_ui.ask_yes_no("Do you have these logs and will you add them to the description after upload?", default=False):
                    return False

        # ── Non-original language audio on REMUX/WEB-DL ─────────────────────────
        # Additional non-original language audio tracks (dual-audio, dubbed) are
        # prohibited on REMUX and WEB-DL releases.
        # Exception: English dub is permitted for animation content only.
        if release_type in ("REMUX", "WEBDL"):
            audio_str = str(meta.get("audio", "") or "").lower()
            is_animation = "animation" in str(meta.get("genres", "") or "").lower()
            if ("dual-audio" in audio_str or "dubbed" in audio_str) and not is_animation:
                return _deny(
                    f"[bold red]{self.tracker}: Non-original language audio tracks are not allowed on REMUX/WEB-DL.[/bold red]\n"
                    "[red]Exception: English dub is only permitted for animation content.[/red]"
                )

        # ── Uncompressed/FLAC multichannel on REMUX ──────────────────────────────
        # Lossless mono/stereo may stay as FLAC, but multichannel LPCM/FLAC must be
        # converted to DTS-HD MA with the DTS-HD Master Audio Suite.
        if release_type == "REMUX":
            audio_codec_upper = str(meta.get("audio", "") or "").upper()
            channels_str = str(meta.get("channels", "") or "")
            lossless_codec = re.search(r"\b(FLAC|LPCM)\b", audio_codec_upper)
            if lossless_codec and channels_str:
                try:
                    main_ch = int(channels_str.split(".")[0])
                except ValueError:
                    main_ch = 0
                if main_ch > 2:
                    codec = lossless_codec.group(1)
                    return _deny(
                        f"[bold red]{self.tracker}: Multichannel {codec} ({channels_str}) is not allowed on REMUX.[/bold red]\n"
                        "[red]Multichannel tracks must be converted to DTS-HD MA (DTS-HD Master Audio Suite).[/red]\n"
                        "[red]Only mono/stereo lossless (≤2 channels) is permitted.[/red]"
                    )

        # ── Redundant audio: multiple channel mixes of the same language ─────────
        # REMUX/WEB-DL may not carry two mixes of the same language (e.g. 5.1 and
        # 2.0 for the same track). Commentary / audio-description tracks are exempt.
        if release_type in ("REMUX", "WEBDL"):
            tracks = ((meta.get("mediainfo") or {}).get("media") or {}).get("track") or []
            lang_channels: dict[str, set[str]] = {}
            for track in tracks:
                if not isinstance(track, dict) or track.get("@type") != "Audio":
                    continue
                title = str(track.get("Title", "") or "").lower()
                if "commentary" in title or "description" in title:
                    continue
                raw_lang = str(track.get("Language", "") or "").lower().strip()
                # Normalize aliases (ko/kor/Korean → Kor) so equivalent languages
                # group together; fall back to raw value when unknown to _LANG_ABBR.
                lang = self._lang_abbr(raw_lang) or raw_lang
                channels = str(track.get("Channels", "") or "").strip()
                if not lang or not channels:
                    continue
                lang_channels.setdefault(lang, set()).add(channels)
            if any(len(chans) > 1 for chans in lang_channels.values()):
                return _deny(
                    f"[bold red]{self.tracker}: Redundant audio — multiple channel mixes of the same language (e.g. 5.1 and 2.0) are not allowed on REMUX/WEB-DL.[/bold red]"
                )

        # ── REMUX must include English subtitles ─────────────────────────────────
        # Remux releases from non-English sources must include English subtitles.
        # Exception: if the original disc did not contain English subtitles (cannot
        # be detected automatically — the uploader must skip this check manually).
        if release_type == "REMUX":
            orig_lang = str(meta.get("original_language", "") or "").lower().strip()
            if orig_lang and orig_lang not in ("en", "zxx", "xx"):
                subtitle_languages = meta.get("subtitle_languages") or []
                if isinstance(subtitle_languages, list) and subtitle_languages:
                    has_english_subs = any("english" in str(lang).lower() for lang in subtitle_languages)
                    if not has_english_subs:
                        if not bool(meta.get("unattended")) or (bool(meta.get("unattended")) and meta.get("unattended_confirm", False)):
                            console.print(f"[bold red]{self.tracker}: REMUX releases from non-English sources must include English subtitles.[/bold red]")
                            console.print("[yellow]Override if the source disc does not contain English subtitles.[/yellow]")
                            if not cli_ui.ask_yes_no("Do you want to upload anyway?", default=False):
                                return False
                        else:
                            return False

        # ── REMUX eac3to / conversion logs ───────────────────────────────────────
        # Every remux needs an eac3to/demux log in the description, plus a conversion
        # log if mono/stereo was FLAC-encoded or LPCM was converted to DTS-HD MA.
        # UA performs no audio conversion and produces no such logs, so the uploader
        # must add them after upload — which is impossible unattended, so we reject.
        if release_type == "REMUX":
            if bool(meta.get("unattended")):
                return _deny(
                    f"[bold red]{self.tracker}: REMUX releases require an eac3to/demux log in the description.[/bold red]\n"
                    "[red]This can't be provided in unattended mode — skipping.[/red]"
                )
            console.print(
                f"[bold yellow]{self.tracker}: Remuxes must include an eac3to/demux log under spoilers in the description "
                "(plus a conversion log if mono/stereo was FLAC-encoded or LPCM was converted to DTS-HD MA).[/bold yellow]"
            )
            if not cli_ui.ask_yes_no("Do you have these logs and will you add them to the description after upload?", default=False):
                return False

        return True

    async def upload(self, meta: dict[str, Any], _) -> bool:
        await self.common.create_torrent_for_upload(meta, self.tracker, self.source_flag)
        cat_id = await self.get_cat_id(meta["category"])
        type_id = await self.get_type_id(meta)
        resolution_id = await self.get_resolution_id(meta)
        desc = await self.get_description(meta)
        region_id = await self.common.unit3d_region_ids(meta.get("region", ""))
        distributor_id = await self.common.unit3d_distributor_ids(meta.get("distributor", ""))
        acm_name = await self.get_name(meta)
        anon = 0 if meta["anon"] == 0 and not self.config["TRACKERS"][self.tracker].get("anon", False) else 1

        if meta["bdinfo"] is not None:
            # bd_dump = open(f"{meta['base_dir']}/tmp/{meta['uuid']}/BD_SUMMARY_00.txt", 'r', encoding='utf-8').read()
            mi_dump = None
            bd_dump = ""
            for each in meta["discs"]:
                bd_dump = bd_dump + each["summary"].strip() + "\n\n"
        else:
            async with aiofiles.open(f"{meta['base_dir']}/tmp/{meta['uuid']}/MEDIAINFO.txt", encoding="utf-8") as f:
                mi_dump = await f.read()
            bd_dump = None
        torrent_file_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}].torrent"
        async with aiofiles.open(torrent_file_path, "rb") as f:
            torrent_bytes = await f.read()
        files = {"torrent": ("torrent.torrent", torrent_bytes, "application/x-bittorrent")}
        data: dict[str, Any] = {
            "name": acm_name,
            "description": desc,
            "mediainfo": mi_dump,
            "bdinfo": bd_dump,
            "category_id": cat_id,
            "type_id": type_id,
            "resolution_id": resolution_id,
            "tmdb": meta["tmdb"],
            "imdb": meta["imdb"],
            "tvdb": meta["tvdb_id"],
            "mal": meta["mal_id"],
            "igdb": 0,
            "anonymous": anon,
            "stream": meta["stream"],
            "sd": meta["sd"],
            "keywords": await self.get_keywords(meta),
            "personal_release": int(meta.get("personalrelease", False)),
            "internal": 0,
            "featured": 0,
            "free": 0,
            "doubleup": 0,
            "sticky": 0,
        }
        if (
            self.config["TRACKERS"][self.tracker].get("internal", False) is True
            and meta["tag"] != ""
            and meta["tag"][1:] in self.config["TRACKERS"][self.tracker].get("internal_groups", [])
        ):
            data["internal"] = 1
        if region_id:
            data["region_id"] = region_id
        if distributor_id:
            data["distributor_id"] = distributor_id
        if meta.get("category") == "TV":
            data["season_number"] = meta.get("season_int", "0")
            data["episode_number"] = meta.get("episode_int", "0")
        headers = {"User-Agent": f"{meta['ua_name']} {meta.get('current_version', '')} ({platform.system()} {platform.release()})"}
        params = {"api_token": self.config["TRACKERS"][self.tracker]["api_key"].strip()}

        if meta["debug"] is False:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url=self.upload_url, files=files, data=data, headers=headers, params=params)
                try:
                    response_data = response.json()
                    meta["tracker_status"][self.tracker]["status_message"] = response_data
                    # adding torrent link to comment of torrent file
                    t_id = response_data["data"].split(".")[1].split("/")[3]
                    meta["tracker_status"][self.tracker]["torrent_id"] = t_id
                    await self.common.download_tracker_torrent(meta, self.tracker, headers=headers, params=params, downurl=response_data["data"])
                    return True
                except httpx.TimeoutException:
                    meta["tracker_status"][self.tracker]["status_message"] = f"data error: {self.tracker} request timed out after 10 seconds"
                    return False
                except httpx.RequestError as e:
                    meta["tracker_status"][self.tracker]["status_message"] = f"data error: Unable to upload to {self.tracker}: {e}"
                    return False
                except Exception:
                    meta["tracker_status"][self.tracker]["status_message"] = f"data error: It may have uploaded, go check: {self.tracker}"
                    return False
        else:
            console.print("[cyan]ACM Request Data:")
            console.print(data)
            meta["tracker_status"][self.tracker]["status_message"] = "Debug mode enabled, not uploading."
            await self.common.create_torrent_for_upload(meta, f"{self.tracker}" + "_DEBUG", f"{self.tracker}" + "_DEBUG", announce_url="https://fake.tracker")
            return True

    async def search_existing(self, meta: dict[str, Any], _) -> list[dict[str, Any]]:
        dupes: list[dict[str, Any]] = []

        # Check Asian origin requirement before searching
        should_continue = await self.get_additional_checks(meta)
        if not should_continue:
            meta["skipping"] = self.tracker
            return dupes

        params: dict[str, Any] = {
            "api_token": self.config["TRACKERS"][self.tracker]["api_key"].strip(),
            "tmdbId": str(meta["tmdb"]),
            "categories[]": (await self.get_cat_id(meta["category"])),
            "types[]": (await self.get_type_id(meta)),
            # A majority of the ACM library doesn't contain resolution information
            # 'resolutions[]': await self.get_resolution_id(meta),
            "name": "",
            "perPage": "100",
        }
        if meta["category"] == "TV":
            params["name"] = meta.get("season", "")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url=self.search_url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    for each in data["data"]:
                        torrent_id = each.get("id", None)
                        attributes = each.get("attributes", {})
                        result: dict[str, Any] = {
                            "name": attributes.get("name", ""),
                            "size": attributes.get("size", 0),
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
                    console.print(f"[bold red]Failed to search torrents. HTTP Status: {response.status_code}")
        except httpx.TimeoutException:
            console.print("[bold red]Request timed out after 10 seconds")
        except httpx.RequestError as e:
            console.print(f"[bold red]Unable to search for existing torrents: {e}")
        except Exception as e:
            console.print(f"[bold red]Unexpected error: {e}")
            await asyncio.sleep(5)

        return dupes

    def _bd_disc_count_tag(self, meta: dict[str, Any]) -> str:
        """Return the ' - NxBD50 …' disc-count tag for a multi-disc Blu-ray.

        Only Blu-ray full discs need it added here — DVD counts are already in the
        UA base name. Empty for single discs or non-BDMV sources.
        """
        discs = meta.get("discs") or []
        if meta.get("is_disc") != "BDMV" or len(discs) < 2:
            return ""
        # (max GiB, label) buckets, checked in order; last is the catch-all.
        buckets = [(48, "UHD50"), (63, "UHD66"), (float("inf"), "UHD100")] if meta.get("uhd") == "UHD" else [(23.3, "BD25"), (float("inf"), "BD50")]
        counts: dict[str, int] = {}
        for disc in discs:
            try:
                gib = float(disc.get("disc_size") or 0)
            except (TypeError, ValueError):
                gib = 0.0
            label = next(lab for cap, lab in buckets if gib < cap)
            counts[label] = counts.get(label, 0) + 1
        # By quantity (descending), then label for stable ordering.
        ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        return " - " + " ".join(f"{n}x{label}" for label, n in ordered)

    async def get_name(self, meta: dict[str, Any]) -> str:
        name: str = meta.get("name", "")
        aka: str = meta.get("aka", "")
        original_title: str = meta.get("original_title", "")
        audio: str = meta.get("audio", "")
        source: str = meta.get("source", "")
        is_disc: str = meta.get("is_disc", "")
        release_type: str = meta.get("type", "")
        subs = self.get_subtitles(meta)
        resolution: str = meta.get("resolution", "")
        category: str = meta.get("category", "")
        year: str = str(meta.get("year", ""))
        season: str = meta.get("season", "")

        # Handle AKA title format: "Title AKA Alt" -> "Title / OriginalTitle"
        if aka != "":
            aka_stripped = aka.strip()
            name = name.replace(f" {aka_stripped} ", f" / {original_title} {chr(int('202A', 16))}")
        elif aka == "":
            if meta.get("title") != original_title:
                name = name.replace(meta["title"], f"{meta['title']} / {original_title} {chr(int('202A', 16))}")

        # ACM naming convention: [year|season] - for TV use season only, for movies use year only
        # Account for special RTL embedding character \u202A that may be between title and year
        if category == "TV" and year and season:
            # Remove year for TV releases, keep only season
            # Pattern handles optional special characters before year
            name = re.sub(rf"(\u202A?)({re.escape(year)}) ({re.escape(season)})", r"\1\3", name)

        # ACM stream naming: audio codec comes BEFORE video codec (already the case in UA base names).
        # Only no-space fixups are needed for streams.
        is_stream = release_type in ("WEBDL", "WEBRIP", "HDTV", "ENCODE")

        # ACM stream naming: no space after audio codec (AAC2.0, DD+5.1, DD5.1)
        # ACM physical media: space after audio codec (AAC 2.0, DD+ 5.1, DD 5.1)
        if is_stream:
            if "AAC" in audio:
                name = name.replace(audio.strip().replace("  ", " "), audio.replace("AAC ", "AAC"))
            name = name.replace("DD+ ", "DD+")
            name = name.replace("DD ", "DD")
            # ACM streams use H.264 / HEVC, never AVC / x264 / x265
            name = re.sub(r"\bAVC\b", "H.264", name)
            name = re.sub(r"\bx264\b", "H.264", name, flags=re.IGNORECASE)
            name = re.sub(r"\bx265\b", "HEVC", name, flags=re.IGNORECASE)

        # Remux format: remove BluRay prefix
        name = name.replace("UHD BluRay REMUX", "Remux")
        name = name.replace("BluRay REMUX", "Remux")

        # ACM uses HEVC instead of H.265
        name = name.replace("H.265", "HEVC")

        # Remove Atmos suffix (integrated into audio codec)
        name = name.replace(" Atmos", "")

        # ACM titles never carry the Dual-Audio tag (any category/type)
        name = re.sub(r"\s*\bDual-Audio\b", "", name)

        # Blu-ray titles don't carry DoVi/HDR/DTS:X tags: the format has a
        # compatibility layer, so these are only tagged on WEB-DL and Remux.
        if is_disc == "BDMV":
            if meta.get("hdr"):
                name = name.replace(str(meta["hdr"]), "")
            # DTS:X is carried in a DTS-HD MA core — fall back to that base codec.
            name = name.replace("DTS:X", "DTS-HD MA")

        # Country code is omitted when it matches the country of origin.
        region = str(meta.get("region", "") or "").strip()
        if is_disc in ("BDMV", "DVD") and region:
            origin_a3: set[str] = set()
            for code in meta.get("origin_country") or []:
                country = pycountry.countries.get(alpha_2=str(code).strip().upper())
                if country:
                    origin_a3.add(country.alpha_3)
            if "DEU" in origin_a3:  # UA uses 'GER' for Germany, not ISO 'DEU'
                origin_a3.add("GER")
            if region.upper() in origin_a3:
                name = re.sub(rf"\s*\b{re.escape(region)}\b", "", name, count=1)

        # DVD format adjustments
        if is_disc == "DVD":
            name = name.replace(f"{source} DVD5", f"{resolution} DVD {source}")
            name = name.replace(f"{source} DVD9", f"{resolution} DVD {source}")
            if audio == meta.get("channels"):
                name = name.replace(f"{audio}", f"MPEG {audio}")

        name = name + self._bd_disc_count_tag(meta) + self._language_tag(meta, subs)
        # Remove the LTR embedding marker (U+202A) used for TV year removal
        name = name.replace("\u202a", "")
        # Collapse any double spaces left after marker/year removal
        name = " ".join(name.split())
        return name

    async def get_description(self, meta: dict[str, Any]) -> str:
        async with aiofiles.open(f"{meta['base_dir']}/tmp/{meta['uuid']}/DESCRIPTION.txt", encoding="utf-8") as f:
            base = await f.read()

        output_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}]DESCRIPTION.txt"

        async with aiofiles.open(output_path, "w", encoding="utf-8") as descfile:
            if meta.get("type") == "WEBDL" and meta.get("service_longname", ""):
                await descfile.write(
                    f"[center][b][color=#ff00ff][size=18]This release is sourced from {meta['service_longname']} and is not transcoded, "
                    f"just remuxed from the direct {meta['service_longname']} stream[/size][/color][/b][/center]\n"
                )

            bbcode = BBCODE()

            discs = meta.get("discs", [])
            if discs:
                if discs[0].get("type") == "DVD":
                    await descfile.write(f"[spoiler=VOB MediaInfo][code]{discs[0]['vob_mi']}[/code][/spoiler]\n\n")

                if len(discs) >= 2:
                    for each in discs[1:]:
                        if each.get("type") == "BDMV":
                            # descfile.write(f"[spoiler={each.get('name', 'BDINFO')}][code]{each['summary']}[/code][/spoiler]\n")
                            # descfile.write("\n")
                            pass
                        if each.get("type") == "DVD":
                            await descfile.write(f"{each.get('name')}:\n")
                            vob_mi = each.get("vob_mi", "")
                            ifo_mi = each.get("ifo_mi", "")
                            await descfile.write(
                                f"[spoiler={os.path.basename(each['vob'])}][code]{vob_mi}[/code][/spoiler] "
                                f"[spoiler={os.path.basename(each['ifo'])}][code]{ifo_mi}[/code][/spoiler]\n\n"
                            )

            desc = re.sub(r"\[center\]\[spoiler=Scene NFO:\].*?\[/center\]", "", base, flags=re.DOTALL)
            desc = bbcode.convert_pre_to_code(desc)
            desc = bbcode.convert_hide_to_spoiler(desc)
            desc = bbcode.convert_comparison_to_collapse(desc, 1000)
            desc = desc.replace("[img]", "[img=300]")

            await descfile.write(desc)

            images = meta.get("ACM_images_key", meta.get("image_list", []))

            if images:
                await descfile.write("[center]\n")
                for i in range(min(len(images), int(meta.get("screens", 0)), 12)):  # ACM caps the description at 12 screenshots
                    image = images[i]
                    web_url = image.get("web_url", "")
                    img_url = image.get("img_url", "")
                    await descfile.write(f"[url={web_url}][img=350]{img_url}[/img][/url]")
                await descfile.write("\n[/center]")

            await descfile.write(f"\n[right][url=https://github.com/yippee0903/Upload-Assistant][size=4]{meta['ua_signature']}[/size][/url][/right]")

        async with aiofiles.open(output_path, encoding="utf-8") as f:
            final_desc: str = await f.read()

        return final_desc
