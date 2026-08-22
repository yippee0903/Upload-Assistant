# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any, Optional

from src.console import console
from src.trackers.COMMON import COMMON, ask_to_continue, is_adult
from src.trackers.UNIT3D import UNIT3D

Meta = dict[str, Any]
Config = dict[str, Any]


class YUS(UNIT3D):
    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name="YUS")
        self.config = config
        self.common = COMMON(config)
        self.tracker = "YUS"
        self.base_url = "https://yu-scene.net"
        self.id_url = f"{self.base_url}/api/torrents/"
        self.upload_url = f"{self.base_url}/api/torrents/upload"
        self.search_url = f"{self.base_url}/api/torrents/filter"
        self.torrent_url = f"{self.base_url}/torrents/"
        self.banned_groups = [
            "ADDICTION",
            "B3LLUM",
            "BANDOLEROS",
            "BigEasy",
            "CINEMAXIS",
            "D3US",
            "d3g",
            "DUMMESCHWEDEN",
            "FGT",
            "GRANiTEN",
            "KiNGDOM",
            "Lama",
            "MeGusta",
            "MezRips",
            "mHD",
            "mRS",
            "msd",
            "NeXus",
            "NhaNc3",
            "nHD",
            "NorTekst",
            "NORViNE",
            "PANDEMONiUM",
            "PiTBULL",
            "RAPiDCOWS",
            "RARBG",
            "Radarr",
            "RCDiVX",
            "RDN",
            "ROCKETRACCOON",
            "SANTi",
            "SHOWTiME",
            "SOOSi",
            "SUXWIC",
            "TOXVIO",
            "TWA",
            "VXT",
            "Will1869",
            "x0r",
            "XS",
            "YIFY",
            "YOLAND",
            "YTS",
            "ZKBL",
            "ZmN",
            "ZMNT",
        ]
        pass

    async def get_additional_checks(self, meta: Meta) -> bool:
        should_continue = True

        if is_adult(meta) and not ask_to_continue(meta, "Porn/xxx is not allowed at YUS."):
            return False

        tag_group = str(meta.get("tag", "")).strip("-").strip().lower()
        invalid_tags = ["nogrp", "nogroup", "unknown", "unk"]
        if not tag_group or tag_group in invalid_tags:
            console.print(f"[bold red]{self.tracker}: Releases without a group tag are not accepted. Skipping.[/bold red]")
            return False

        return should_continue

    async def get_type_id(
        self,
        meta: Meta,
        type: Optional[str] = None,
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        type_id = {"DISC": "17", "REMUX": "2", "WEBDL": "4", "WEBRIP": "5", "HDTV": "6", "ENCODE": "3"}
        if mapping_only:
            return type_id
        elif reverse:
            return {v: k for k, v in type_id.items()}
        elif type is not None:
            return {"type_id": type_id.get(type, "0")}
        else:
            meta_type = meta.get("type", "")
            resolved_id = type_id.get(meta_type, "0")
            return {"type_id": resolved_id}
