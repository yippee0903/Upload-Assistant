# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
#
# V3X (v3x.club) — French private tracker with a custom (non-UNIT3D) API.
#
# API surface (api.v3x.club):
#   GET  /torrents?search=…&page=…      public listing (torrents/total/page/perPage)
#   GET  /torrents/{uuid}               detail: tmdbId, infoHash, description, nfo, files…
#   GET  /categories                    public category tree (id/name/children)
#   POST /api/torrents                  upload — multipart, Authorization: Bearer <api key>
#     required: file (.torrent), name, categoryId (subcategory number), rightsDeclared
#     accepted: description, nfo, tmdbId, anonymous, language

from typing import Any, Optional

import aiofiles
import httpx

from src.console import console
from src.get_desc import DescriptionBuilder
from src.trackers.COMMON import COMMON
from src.trackers.FRENCH import FrenchTrackerMixin

Meta = dict[str, Any]


class V3X(FrenchTrackerMixin):
    WEB_LABEL: str = "WEB"
    notag_label: str = ""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.common = COMMON(config)
        self.tracker = "V3X"
        self.source_flag = "V3X"
        self.base_url = "https://v3x.club"
        self.api_base = "https://api.v3x.club"
        self.upload_url = f"{self.api_base}/api/torrents"
        self.search_url = f"{self.api_base}/torrents"
        self.torrent_url = f"{self.base_url}/torrents/"
        self.api_key = str(self.config["TRACKERS"].get(self.tracker, {}).get("api_key", "") or "").strip()
        self.banned_groups: list[Any] = []

    async def get_category_id(self, meta: Meta) -> str:
        # Subcategory ids: Film=8, Animation=2, Série TV=9, Animation Série=3.
        # ponytail: Documentaire (5/6) and the other trees are not mapped yet;
        # add them when a real upload needs it.
        if meta.get("category") == "TV":
            return "3" if meta.get("anime") else "9"
        return "2" if meta.get("anime") else "8"

    async def search_existing(self, meta: Meta, _disctype: Any = None) -> list[dict[str, Any]]:
        dupes: list[dict[str, Any]] = []
        search_term = str(meta.get("title") or "")
        if not search_term:
            return dupes
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(self.search_url, params={"search": search_term, "perPage": 100})
                if response.status_code != 200:
                    console.print(f"[yellow]{self.tracker}: search returned HTTP {response.status_code}[/yellow]")
                    return dupes
                torrents = response.json().get("torrents", [])
        except (httpx.RequestError, httpx.TimeoutException, ValueError) as e:
            console.print(f"[yellow]{self.tracker}: search failed: {type(e).__name__}[/yellow]")
            return dupes

        meta_tmdb = int(meta.get("tmdb_id") or 0)
        for torrent in torrents:
            if not isinstance(torrent, dict):
                continue
            # The listing has no tmdbId; keep every name match. The detail
            # endpoint has it, but one request per result is not worth it for
            # a dupe pre-filter.
            _ = meta_tmdb
            dupes.append({"name": torrent.get("name", ""), "size": torrent.get("size", 0), "link": f"{self.torrent_url}{torrent.get('slug') or torrent.get('id', '')}"})
        return dupes

    async def _read_tmp_file(self, meta: Meta, filename: str) -> Optional[bytes]:
        path = f"{meta['base_dir']}/tmp/{meta['uuid']}/{filename}"
        try:
            async with aiofiles.open(path, "rb") as f:
                return await f.read()
        except OSError:
            return None

    async def upload(self, meta: Meta, _disctype: str) -> bool:
        await self.common.create_torrent_for_upload(meta, self.tracker, self.source_flag)

        name_result = await self.get_name(meta)
        name = name_result.get("name", "") if isinstance(name_result, dict) else str(name_result)

        torrent_bytes = await self._read_tmp_file(meta, f"[{self.tracker}].torrent")
        if not torrent_bytes:
            meta["tracker_status"][self.tracker]["status_message"] = "data error: torrent file missing"
            return False

        description = await DescriptionBuilder(self.tracker, self.config).unit3d_edit_desc(meta)
        nfo_bytes = await self._read_tmp_file(meta, "MEDIAINFO_CLEANPATH.txt")

        data: dict[str, Any] = {
            "name": name,
            "categoryId": await self.get_category_id(meta),
            "rightsDeclared": "true",
            "description": description,
            "anonymous": "true" if meta.get("anon") else "false",
        }
        if nfo_bytes:
            data["nfo"] = nfo_bytes.decode("utf-8", errors="replace")
        if int(meta.get("tmdb_id") or 0):
            data["tmdbId"] = str(meta["tmdb_id"])

        files = {"file": (f"{name}.torrent", torrent_bytes, "application/x-bittorrent")}
        headers = {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}

        if meta.get("debug"):
            console.print(f"[cyan]{self.tracker} debug: would upload '{name}' with categoryId={data['categoryId']}[/cyan]")
            meta["tracker_status"][self.tracker]["status_message"] = "Debug mode, not uploaded."
            return True

        try:
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                response = await client.post(self.upload_url, files=files, data=data, headers=headers)
        except (httpx.RequestError, httpx.TimeoutException) as e:
            meta["tracker_status"][self.tracker]["status_message"] = f"data error: upload failed: {type(e).__name__}"
            return False

        try:
            response_data = response.json()
        except ValueError:
            response_data = {"error": f"HTTP {response.status_code}"}

        if response.status_code in (200, 201) and isinstance(response_data, dict) and not response_data.get("error"):
            torrent_id = response_data.get("id") or (response_data.get("torrent") or {}).get("id")
            if torrent_id:
                meta["tracker_status"][self.tracker]["torrent_id"] = str(torrent_id)
            meta["tracker_status"][self.tracker]["status_message"] = response_data
            return True

        meta["tracker_status"][self.tracker]["status_message"] = f"data error: {response_data}"
        return False
