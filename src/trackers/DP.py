# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any, cast

import pycountry

from src.console import console
from src.get_desc import DescriptionBuilder
from src.languages import languages_manager
from src.tmdb import TmdbManager
from src.trackers.UNIT3D import UNIT3D


class DP(UNIT3D):
    skip_nfo: bool = True

    def __init__(self, config: dict[str, Any]):
        super().__init__(config, tracker_name="DP")
        self.config = config
        self.tmdb_manager = TmdbManager(config)
        self.tracker = "DP"
        self.base_url = "https://darkpeers.org"
        self.id_url = f"{self.base_url}/api/torrents/"
        self.upload_url = f"{self.base_url}/api/torrents/upload"
        self.requests_url = f"{self.base_url}/api/requests/filter"
        self.search_url = f"{self.base_url}/api/torrents/filter"
        self.torrent_url = f"{self.base_url}/torrents/"
        self.banned_groups = [
            "ARCADE",
            "aXXo",
            "BANDOLEROS",
            "BONE",
            "BRrip",
            "CM8",
            "CrEwSaDe",
            "CTFOH",
            "dAV1nci",
            "DNL",
            "eranger2",
            "FaNGDiNG0",
            "FGT",
            "FiSTER",
            "flower",
            "GalaxyTV",
            "HD2DVD",
            "HDTime",
            "HorribleSubs",
            "iHYTECH",
            "ION10",
            "iPlanet",
            "KiNGDOM",
            "LAMA",
            "MeGusta",
            "mHD",
            "mSD",
            "NaNi",
            "NhaNc3",
            "nHD",
            "nikt0",
            "nSD",
            "OFT",
            "PiTBULL",
            "PRODJi",
            "PSA",
            "RARBG",
            "Rifftrax",
            "ROCKETRACCOON",
            "SANTi",
            "SasukeducK",
            "SEEDSTER",
            "ShAaNiG",
            "Sicario",
            "STUTTERSHIT",
            "Subsplease",
            "SyncUp",
            "TAoE",
            "TGALAXY",
            "TGx",
            "TORRENTGALAXY",
            "ToVaR",
            "Trix",
            "TSP",
            "TSPxL",
            "ViSION",
            "VXT",
            "WAF",
            "WKS",
            "X0r",
            "YIFY",
            "YTS",
        ]
        pass

    async def get_additional_files(self, meta: dict[str, Any]) -> dict[str, tuple[str, bytes, str]]:
        return {}

    async def get_additional_checks(self, meta: dict[str, Any]) -> bool:
        should_continue = True
        nordic_languages = ["danish", "swedish", "norwegian", "icelandic", "finnish", "english"]
        if not await self.common.check_language_requirements(meta, self.tracker, languages_to_check=nordic_languages, check_audio=True, check_subtitle=True):
            return False

        group = str(meta.get("tag") or "").lstrip("-").strip().upper()
        if group == "EVO" and meta["type"] != "WEBDL":
            console.print(f"[bold red]{self.tracker} only allows EVO releases when they are WEB-DLs. Skipping upload.")
            return False
        if group == "HDT" and meta["type"] != "REMUX":
            console.print(f"[bold red]{self.tracker} only allows HDT releases when they are Remuxes. Skipping upload.")
            return False

        if meta.get("hardcoded_subs", False):
            console.print(f"[bold red]{self.tracker} does not allow hardcoded subtitles. Skipping upload.")
            return False

        return should_continue

    async def get_description(self, meta: dict[str, Any]) -> dict[str, str]:
        if meta.get("logo", "") == "":
            TMDB_API_KEY = self.config["DEFAULT"].get("tmdb_api")
            TMDB_BASE_URL = "https://api.themoviedb.org/3"
            tmdb_id_raw = meta.get("tmdb")
            tmdb_id = int(tmdb_id_raw) if isinstance(tmdb_id_raw, (int, str)) and str(tmdb_id_raw).isdigit() else 0
            category = str(meta.get("category", ""))
            debug = bool(meta.get("debug"))
            logo_languages = ["da", "sv", "no", "fi", "is", "en"]
            tmdb_api_key = str(TMDB_API_KEY) if TMDB_API_KEY else ""
            if tmdb_id and category:
                logo_path = await self.tmdb_manager.get_logo(
                    tmdb_id,
                    category,
                    debug,
                    logo_languages=logo_languages,
                    TMDB_API_KEY=tmdb_api_key,
                    TMDB_BASE_URL=TMDB_BASE_URL,
                )
                if logo_path:
                    meta["logo"] = logo_path

        return {"description": await DescriptionBuilder(self.tracker, self.config).unit3d_edit_desc(meta)}

    async def get_additional_data(self, meta: dict[str, Any]) -> dict[str, Any]:
        data = {
            "mod_queue_opt_in": await self.get_flag(meta, "modq"),
        }

        return data

    async def get_audio(self, meta: dict[str, Any]) -> str:
        if not meta.get("language_checked", False):
            await languages_manager.process_desc_language(meta, tracker=self.tracker)

        audio_languages = meta.get("audio_languages")
        if not isinstance(audio_languages, list):
            return "SKIPPED"

        audio_languages_list = cast(list[Any], audio_languages)
        seen: set[str] = set()
        unique_languages: list[str] = []
        for lang in audio_languages_list:
            s = str(lang).strip()
            s_lower = s.lower()
            if s and s_lower not in seen:
                seen.add(s_lower)
                unique_languages.append(s)

        if not unique_languages:
            return "SKIPPED"

        # Disc releases: no dub tag per naming guide
        if meta.get("is_disc"):
            return ""

        # Resolve original language to its ISO alpha_2 code
        orig_code = str(meta.get("original_language") or "").strip().lower()
        orig_canonical = ""
        if orig_code:
            try:
                lang_obj = pycountry.languages.get(alpha_2=orig_code) or pycountry.languages.get(alpha_3=orig_code)
                if lang_obj:
                    orig_canonical = getattr(lang_obj, "alpha_2", None) or getattr(lang_obj, "alpha_3", None) or getattr(lang_obj, "bibliographic", None) or ""
            except Exception:
                orig_canonical = orig_code

        is_english_original = orig_canonical in ("en", "eng") or orig_code in ("en", "eng")
        nordic_codes = {"da", "sv", "no", "fi", "is", "nb", "nn"}
        is_nordic_original = orig_canonical in nordic_codes

        def resolve_code(lang: str) -> str:
            try:
                obj = pycountry.languages.lookup(lang)
                return getattr(obj, "alpha_2", None) or getattr(obj, "alpha_3", None) or getattr(obj, "bibliographic", None) or lang.lower()
            except LookupError:
                return lang.lower()

        resolved = [resolve_code(lang) for lang in unique_languages]
        has_original = (orig_canonical in resolved) if orig_canonical else False
        has_english = "en" in resolved

        n = len(unique_languages)

        # ── 1 language ────────────────────────────────────────────────────────
        if n == 1:
            lang_code = resolved[0]
            lang_display = unique_languages[0][0].upper() + unique_languages[0][1:]
            if has_original:
                return ""  # original language only → no tag
            if has_english and not is_english_original:
                return "Dubbed"  # English-only on non-English original
            if lang_code in nordic_codes and not is_english_original and not is_nordic_original:
                return f"{lang_display} Dubbed"  # Nordic-only on non-English/non-Nordic original
            return ""

        # ── 3+ languages ──────────────────────────────────────────────────────
        if n >= 3:
            return "MULTi"

        # ── 2 languages ───────────────────────────────────────────────────────
        # Non-English original + original track + English track → Dual-Audio
        if not is_english_original and has_original and has_english:
            return "Dual-Audio"

        # Find the "label" language for Language MULTi.
        # Priority: if English is present (and not the original), it is the anchor
        # and the other language is the label; otherwise the non-original is the label.
        label_lang = unique_languages[1]  # safe fallback
        if is_english_original:
            for lang, code in zip(unique_languages, resolved):
                if code not in ("en", "eng"):
                    label_lang = lang
                    break
        elif has_english and not has_original:
            # No original track in audio; English acts as anchor
            for lang, code in zip(unique_languages, resolved):
                if code not in ("en", "eng"):
                    label_lang = lang
                    break
        else:
            for lang, code in zip(unique_languages, resolved):
                if code != orig_canonical:
                    label_lang = lang
                    break

        # French label → "French MULTi" (DP is a French-primary tracker)
        try:
            label_obj = pycountry.languages.lookup(label_lang)
            label_code = getattr(label_obj, "alpha_2", None) or ""
            if label_code == "fr":
                return "French MULTi"
        except LookupError:
            if label_lang.lower().startswith("fr"):
                return "French MULTi"

        display = label_lang[0].upper() + label_lang[1:]
        return f"{display} MULTi"

    async def get_name(self, meta: dict[str, Any]) -> dict[str, str]:
        dp_name = str(meta.get("name", ""))

        audio = await self.get_audio(meta)
        if audio and audio != "SKIPPED":
            if "Dual-Audio" in dp_name:
                dp_name = dp_name.replace("Dual-Audio", audio)
            elif "MULTi" in dp_name and audio not in dp_name:
                dp_name = dp_name.replace("MULTi", audio)
            elif "Dubbed" in dp_name and audio not in dp_name:
                # e.g. "Dubbed" → "Swedish Dubbed"
                dp_name = dp_name.replace("Dubbed", audio)
            elif audio not in dp_name:
                # No existing dub token (e.g. Nordic-only on Japanese content where
                # audio.py doesn't set "Dubbed"): insert before the audio codec string.
                audio_raw = str(meta.get("audio", "")).strip()
                audio_codec = audio_raw
                for prefix in ("Dual-Audio ", "Dubbed ", "MULTi "):
                    if audio_raw.startswith(prefix):
                        audio_codec = audio_raw[len(prefix) :]
                        break
                if audio_codec and audio_codec in dp_name:
                    dp_name = dp_name.replace(audio_codec, f"{audio} {audio_codec}", 1)

        return {"name": dp_name}
