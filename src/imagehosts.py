"""Single source of truth for image hosts: domains, config key, size limits."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ImageHost:
    domains: tuple[str, ...] = ()
    config_keys: tuple[str, ...] = ()  # config["DEFAULT"] keys the host needs (credential, URL)
    max_bytes: Optional[int] = None  # None = no upper limit
    uploadable: bool = True  # False = only recognised when rehosting


MIN_IMAGE_BYTES = 75_000

IMAGE_HOSTS: dict[str, ImageHost] = {
    "imgbb": ImageHost(("ibb.co", "imgbb.com"), ("imgbb_api",), 31_000_000),
    "ptpimg": ImageHost(("ptpimg.me",), ("ptpimg_api",)),
    "imgbox": ImageHost(("imgbox.com",), (), 10_000_000),
    "pixhost": ImageHost(("pixhost.to",), (), 10_000_000),
    "lensdump": ImageHost(("lensdump.com",), ("lensdump_api",)),
    "ptscreens": ImageHost(("ptscreens.com",), ("ptscreens_api",)),
    "onlyimage": ImageHost(("onlyimage.org",), ("onlyimage_api",)),
    "dalexni": ImageHost((), ("dalexni_api",)),
    "zipline": ImageHost((), ("zipline_url", "zipline_api_key")),
    "passtheimage": ImageHost(("passtheima.ge", "img.passtheima.ge"), ("passtheima_ge_api",)),
    "seedpool_cdn": ImageHost(("cdn.seedpool.org",), ("seedpool_cdn_api",)),
    "sharex": ImageHost(("digitalcore.club", "img.digitalcore.club"), ("sharex_url", "sharex_api_key")),
    "utppm": ImageHost(("utp.pm",), ("utppm_api",)),
    "lostimg": ImageHost(("lostimg.cc",), ("lostimg_api",)),
    "postimg": ImageHost(("postimg.cc",), ("postimg_api",)),
    # recognised when rehosting, never uploaded to
    "bhd": ImageHost(("beyondhd.co",), uploadable=False),
    "imagebam": ImageHost(("imagebam.com",), uploadable=False),
    "imgur": ImageHost(("imgur.com",), uploadable=False),
    "kshare": ImageHost(("kshare.club",), uploadable=False),
    "pterclub": ImageHost(("img.pterclub.com",), uploadable=False),
    "ilikeshots": ImageHost(("yes.ilikeshots.club",), uploadable=False),
}

UPLOAD_HOSTS: tuple[str, ...] = tuple(slug for slug, host in IMAGE_HOSTS.items() if host.uploadable)

# domain -> slug, for recognising where an existing image lives
URL_HOST_MAPPING: dict[str, str] = {domain: slug for slug, host in IMAGE_HOSTS.items() for domain in host.domains}

# slug -> config keys, for hosts that need credentials
IMAGE_HOST_CONFIG_KEYS: dict[str, tuple[str, ...]] = {slug: host.config_keys for slug, host in IMAGE_HOSTS.items() if host.config_keys}


def image_size_ok(img_host: Optional[str], size: int) -> bool:
    """True when a screenshot of `size` bytes is acceptable for `img_host`."""
    host = IMAGE_HOSTS.get(img_host or "")
    if host is None or not host.uploadable or size <= MIN_IMAGE_BYTES:
        return False
    return host.max_bytes is None or size <= host.max_bytes


def host_slug(hostname: str) -> str:
    """Slug of the image host serving `hostname` (suffix match on known domains); the hostname itself when unknown."""
    hostname = hostname.lower()
    for domain, slug in URL_HOST_MAPPING.items():
        if hostname == domain or hostname.endswith(f".{domain}"):
            return slug
    return hostname
