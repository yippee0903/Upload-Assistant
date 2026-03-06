# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
# import discord
import asyncio
import os
import platform
import re
from typing import Any

import aiofiles
import httpx

from src.bbcode import BBCODE
from src.console import console
from src.rehostimages import RehostImagesManager
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
        self.rehost_images_manager = RehostImagesManager(config)
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
                    for lang, subID in sub_lang_map.items():
                        if language in lang and subID not in sub_langs:
                            sub_langs.append(subID)
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

    async def check_image_hosts(self, meta: dict[str, Any]) -> None:
        url_host_mapping = {
            "ibb.co": "imgbb",
            "imgbox.com": "imgbox",
            "postimg.cc": "postimg",
            "pixhost.to": "pixhost",
            "ptpimg.me": "ptpimg",
            "imagebam.com": "imagebam",
        }
        await self.rehost_images_manager.check_hosts(
            meta,
            self.tracker,
            url_host_mapping=url_host_mapping,
            img_host_index=1,
            approved_image_hosts=self.approved_image_hosts,
        )

    def check_asian_origin(self, meta: dict[str, Any]) -> bool:
        """Return True if the media originates from at least one Asian country.

        Uses TMDB ``origin_country`` as the primary signal (where the content
        actually comes from).  Falls back to ``production_countries`` only when
        ``origin_country`` is not available — co-productions with Asian studios
        (e.g. a US show filmed with a Japanese partner) should not qualify.
        """
        origin_codes = [c.strip().upper() for c in (meta.get("origin_country", []) or []) if isinstance(c, str) and c.strip()]
        if origin_codes:
            return any(code in self.ASIAN_COUNTRIES for code in origin_codes)

        # Fallback: origin_country not provided — check production_countries
        production_countries: list[dict[str, str]] = meta.get("production_countries", []) or []
        return any(pc.get("iso_3166_1", "").upper() in self.ASIAN_COUNTRIES for pc in production_countries)

    async def get_additional_checks(self, meta: dict[str, Any]) -> bool:
        """Check ACM-specific requirements before searching/uploading."""
        # Check Asian origin
        if not self.check_asian_origin(meta):
            origin = meta.get("origin_country", [])
            prod = [pc.get("iso_3166_1", "") for pc in (meta.get("production_countries", []) or [])]
            countries = ", ".join(filter(None, dict.fromkeys(origin + prod))) or "Unknown"
            if not bool(meta.get("unattended")):
                console.print(
                    f"[bold red]Only media produced in Asian countries is allowed at {self.tracker}.[/bold red]\n[red]Detected production countries: {countries}[/red]"
                )
            return False

        # Encodes are not allowed on ACM (ENCODE, WEBRIP, HDTV are all re-encoded content)
        # Only REMUX, WEBDL, and full discs are allowed
        release_type = str(meta.get("type", "")).upper()
        if release_type in ("ENCODE", "WEBRIP", "HDTV"):
            if not bool(meta.get("unattended")):
                console.print(
                    f"[bold red]Encodes are not allowed at {self.tracker}.[/bold red]\n"
                    f"[red]Detected type: {release_type}. Only REMUX, WEB-DL, and full discs are allowed.[/red]"
                )
            return False

        return True

    async def upload(self, meta: dict[str, Any], _) -> bool:
        # Safety net: Asian origin should already be checked in search_existing
        if not self.check_asian_origin(meta):
            meta["tracker_status"][self.tracker]["status_message"] = "Skipped: non-Asian origin"
            return False

        # Safety net: Encodes should already be blocked in get_additional_checks
        release_type = str(meta.get("type", "")).upper()
        if release_type in ("ENCODE", "WEBRIP", "HDTV"):
            meta["tracker_status"][self.tracker]["status_message"] = f"Skipped: {release_type} not allowed"
            return False

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
        video_encode: str = meta.get("video_encode", "")
        video_codec: str = meta.get("video_codec", "")
        hdr: str = meta.get("hdr", "")
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

        # ACM naming convention: video_codec comes BEFORE audio_codec
        # Base format is: ... WEB-DL {audio} {hdr} {video_encode}
        # ACM wants:      ... WEB-DL {video_encode} {hdr} {audio}
        is_stream = release_type in ("WEBDL", "WEBRIP", "HDTV", "ENCODE")
        video_tag = video_encode if video_encode else video_codec
        if is_stream and audio and video_tag:
            # Find and swap audio/video order
            # Current: "... WEB-DL AAC 2.0 HDR H.264-GROUP" or "... WEB-DL AAC 2.0 H.264-GROUP"
            # Target:  "... WEB-DL H.264 HDR AAC2.0-GROUP" or "... WEB-DL H.264 AAC2.0-GROUP"
            audio_stripped = audio.strip()
            if hdr:
                # Pattern: {audio} {hdr} {video}
                old_pattern = f"{audio_stripped} {hdr} {video_tag}"
                new_pattern = f"{video_tag} {hdr} {audio_stripped}"
                name = name.replace(old_pattern, new_pattern)
            else:
                # Pattern: {audio} {video}
                old_pattern = f"{audio_stripped} {video_tag}"
                new_pattern = f"{video_tag} {audio_stripped}"
                name = name.replace(old_pattern, new_pattern)

        # ACM stream naming: no space after audio codec (AAC2.0, DD+5.1)
        # ACM physical media: space after audio codec (AAC 2.0, DD 5.1)
        if is_stream:
            if "AAC" in audio:
                name = name.replace(audio.strip().replace("  ", " "), audio.replace("AAC ", "AAC"))
            name = name.replace("DD+ ", "DD+")

        # Remux format: remove BluRay prefix
        name = name.replace("UHD BluRay REMUX", "Remux")
        name = name.replace("BluRay REMUX", "Remux")

        # ACM uses HEVC instead of H.265
        name = name.replace("H.265", "HEVC")

        # Remove Atmos suffix (integrated into audio codec)
        name = name.replace(" Atmos", "")

        # DVD format adjustments
        if is_disc == "DVD":
            name = name.replace(f"{source} DVD5", f"{resolution} DVD {source}")
            name = name.replace(f"{source} DVD9", f"{resolution} DVD {source}")
            if audio == meta.get("channels"):
                name = name.replace(f"{audio}", f"MPEG {audio}")

        name = name + self.get_subs_tag(subs)
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
                for i in range(min(len(images), int(meta.get("screens", 0)))):
                    image = images[i]
                    web_url = image.get("web_url", "")
                    img_url = image.get("img_url", "")
                    await descfile.write(f"[url={web_url}][img=350]{img_url}[/img][/url]")
                await descfile.write("\n[/center]")

            await descfile.write(f"\n[right][url=https://github.com/yippee0903/Upload-Assistant][size=4]{meta['ua_signature']}[/size][/url][/right]")

        async with aiofiles.open(output_path, encoding="utf-8") as f:
            final_desc: str = await f.read()

        return final_desc
