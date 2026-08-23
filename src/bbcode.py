# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import html
import os
import re
import urllib.parse
from typing import Any

from src.console import console

# Bold - KEEP
# Italic - KEEP
# Underline - KEEP
# Strikethrough - KEEP
# Color - KEEP
# URL - KEEP
# PARSING - Probably not exist in uploads
# Spoiler - KEEP

# QUOTE - CONVERT to CODE
# PRE - CONVERT to CODE
# Hide - CONVERT to SPOILER
# COMPARISON - CONVERT

# LIST - REMOVE TAGS/REPLACE with * or something

# Size - REMOVE TAGS

# Align - REMOVE (ALL LEFT ALIGNED)
# VIDEO - REMOVE
# HR - REMOVE
# MEDIAINFO - REMOVE
# MOVIE - REMOVE
# PERSON - REMOVE
# USER - REMOVE
# IMG - REMOVE?
# INDENT - Probably not an issue, but maybe just remove tags


_PIXHOST_FULL = re.compile(r"^https?://img(\d+)\.pixhost\.to/images/")
_PIXHOST_THUMB = re.compile(r"^https?://t(\d+)\.pixhost\.to/thumbs/")


def image_entry(img_url: str, web_url: str = "") -> dict[str, str]:
    """Image dict for a URL found in a description, with the host's thumbnail/full-size pair derived.

    Descriptions often embed the full-size image; sites that do not scale [img]
    (C411, V3X) then render it full width — or not at all. Only imgbox and pixhost
    expose both forms through a predictable URL rewrite.
    """
    img_url = img_url.strip()
    raw_url = img_url
    host = urllib.parse.urlparse(img_url).hostname or ""
    if host == "thumbs2.imgbox.com":
        raw_url = img_url.replace("thumbs2.imgbox.com", "images2.imgbox.com").replace("_t.png", "_o.png")
    elif _PIXHOST_FULL.match(img_url):
        img_url = _PIXHOST_FULL.sub(r"https://t\1.pixhost.to/thumbs/", img_url)
    elif _PIXHOST_THUMB.match(img_url):
        raw_url = _PIXHOST_THUMB.sub(r"https://img\1.pixhost.to/images/", img_url)
    return {"img_url": img_url, "raw_url": raw_url, "web_url": web_url.strip() or raw_url}


class BBCODE:
    def __init__(self) -> None:
        pass

    def clean_hdb_description(self, description: str) -> tuple[str, list[dict[str, Any]]]:
        # Unescape html
        desc = html.unescape(description)
        desc = desc.replace("\r\n", "\n")
        imagelist: list[dict[str, Any]] = []

        # First pass: Remove entire comparison sections
        # Start by finding section headers for comparisons
        comparison_sections = re.finditer(r"\[center\]\s*\[b\].*?(Comparison|vs).*?\[\/b\][\s\S]*?\[\/center\]", desc, flags=re.IGNORECASE)
        for section in comparison_sections:
            section_text = section.group(0)
            # If section contains hdbits.org, remove the entire section
            if re.search(r"hdbits\.org", section_text, flags=re.IGNORECASE):
                desc = desc.replace(section_text, "")

        # Handle individual comparison lines
        comparison_lines = re.finditer(r"(.*comparison.*)\n", desc, flags=re.IGNORECASE)
        for comp_match in comparison_lines:
            comp_pos = comp_match.start()

            # Get the next lines after the comparison line
            next_lines = desc[comp_pos : comp_pos + 500].split("\n", 3)[:3]  # Get comparison line + 2 more lines
            next_lines_text = "\n".join(next_lines)

            # Check if any of these lines contain HDBits URLs
            if re.search(r"hdbits\.org", next_lines_text, flags=re.IGNORECASE):
                # Replace the entire section (comparison line + next 2 lines)
                line_end_pos = comp_pos + len(next_lines_text)
                to_remove = desc[comp_pos:line_end_pos]
                desc = desc.replace(to_remove, "")

        # Remove all empty URL tags containing hdbits.org
        desc = re.sub(r"\[url=https?:\/\/(img\.|t\.)?hdbits\.org[^\]]*\]\[\/url\]", "", desc, flags=re.IGNORECASE)

        # Remove URL tags with visible content
        hdbits_urls = re.findall(r"(\[url[\=\]]https?:\/\/(img\.|t\.)?hdbits\.org[^\]]+\])(.*?)(\[\/url\])?", desc, flags=re.IGNORECASE)
        for url_parts in hdbits_urls:
            full_url = "".join(url_parts)
            desc = desc.replace(full_url, "")

        # Remove HDBits image tags
        hdbits_imgs = re.findall(r"\[img\][\s\S]*?(img\.|t\.)?hdbits\.org[\s\S]*?\[\/img\]", desc, flags=re.IGNORECASE)
        for img_tag in hdbits_imgs:
            desc = desc.replace(img_tag, "")

        # Remove any standalone HDBits URLs
        standalone_urls = re.findall(r"https?:\/\/(img\.|t\.)?hdbits\.org\/[^\s\[\]]+", desc, flags=re.IGNORECASE)
        for url in standalone_urls:
            desc = desc.replace(url, "")

        # Catch any remaining URL tags with hdbits.org in them
        desc = re.sub(r"\[url[^\]]*hdbits\.org[^\]]*\](.*?)\[\/url\]", "", desc, flags=re.IGNORECASE)

        # Double-check for any self-closing URL tags that might have been missed
        desc = re.sub(r"\[url=https?:\/\/[^\]]*hdbits\.org[^\]]*\]\[\/url\]", "", desc, flags=re.IGNORECASE)

        # Remove empty comparison section headers and center tags
        desc = re.sub(r"\[center\]\s*\[b\].*?(Comparison|vs).*?\[\/b\][\s\S]*?\[\/center\]", "", desc, flags=re.IGNORECASE)

        # Remove any empty center tags that might be left
        desc = re.sub(r"\[center\]\s*\[\/center\]", "", desc, flags=re.IGNORECASE)

        # Clean up multiple consecutive newlines
        desc = re.sub(r"\n{3,}", "\n\n", desc)

        # Extract images wrapped in URL tags (e.g., [url=https://imgbox.com/xxx][img]https://thumbs.imgbox.com/xxx[/img][/url])
        url_img_pattern = r"\[url=(https?:\/\/[^\]]+)\]\[img\](https?:\/\/[^\]]+)\[\/img\]\[\/url\]"
        url_img_matches: list[tuple[str, str]] = re.findall(url_img_pattern, desc, flags=re.IGNORECASE)
        for web_url, img_url in url_img_matches:
            # Skip HDBits images
            web_host = urllib.parse.urlparse(web_url).hostname or ""
            img_host = urllib.parse.urlparse(img_url).hostname or ""
            if web_host == "hdbits.org" or img_host == "hdbits.org":
                desc = desc.replace(f"[url={web_url}][img]{img_url}[/img][/url]", "")
                continue

            imagelist.append(image_entry(img_url, web_url))
            desc = desc.replace(f"[url={web_url}][img]{img_url}[/img][/url]", "")

        description = desc.strip()
        if self.is_only_bbcode(description):
            return "", imagelist
        return description, imagelist

    def clean_bhd_description(self, description: str, meta: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
        # Unescape html
        desc = html.unescape(description)
        desc = desc.replace("\r\n", "\n")
        imagelist: list[dict[str, Any]] = []

        if "framestor" in meta and meta["framestor"]:
            framestor_desc = desc
            save_path = os.path.join(meta["base_dir"], "tmp", meta["uuid"])
            os.makedirs(save_path, exist_ok=True)
            nfo_file_path = os.path.join(save_path, "bhd.nfo")
            with open(nfo_file_path, "w", encoding="utf-8") as f:
                try:
                    f.write(framestor_desc)
                finally:
                    f.close()
            console.print(f"[green]FraMeSToR NFO saved to {nfo_file_path}")
            meta["nfo"] = True
            meta["bhd_nfo"] = True

        # Remove size tags
        desc = re.sub(r"\[size=.*?\]", "", desc)
        desc = desc.replace("[/size]", "")
        desc = desc.replace("<", "/")
        desc = desc.replace("<", "\\")

        # Remove Images in IMG tags
        desc = re.sub(r"\[img\][\s\S]*?\[\/img\]", "", desc, flags=re.IGNORECASE)
        desc = re.sub(r"\[img=[\s\S]*?\]", "", desc, flags=re.IGNORECASE)

        # Extract loose images and add to imagelist as dictionaries
        loose_images = re.findall(r"(https?:\/\/[^\s\[\]]+\.(?:png|jpg))", desc, flags=re.IGNORECASE)
        for img_url in loose_images:
            imagelist.append(image_entry(img_url))
            desc = desc.replace(img_url, "")

        # Now, remove matching URLs from [URL] tags
        for img in imagelist:
            img_url = re.escape(img["img_url"])
            desc = re.sub(rf"\[URL={img_url}\]\[/URL\]", "", desc, flags=re.IGNORECASE)
            desc = re.sub(rf"\[URL={img_url}\]\[img[^\]]*\]{img_url}\[/img\]\[/URL\]", "", desc, flags=re.IGNORECASE)

        # Remove leftover [img] or [URL] tags in the description
        desc = re.sub(r"\[img\][\s\S]*?\[\/img\]", "", desc, flags=re.IGNORECASE)
        desc = re.sub(r"\[img=[\s\S]*?\]", "", desc, flags=re.IGNORECASE)
        desc = re.sub(r"\[URL=[\s\S]*?\]\[\/URL\]", "", desc, flags=re.IGNORECASE)

        if meta.get("flux", False):
            # Strip trailing whitespace and newlines:
            desc = desc.rstrip()

            # Strip blank lines:
            desc = desc.strip("\n")
            desc = re.sub("\n\n+", "\n\n", desc)
            while desc.startswith("\n"):
                desc = desc.replace("\n", "", 1)
            desc = desc.strip("\n")

            if desc.replace("\n", "").strip() == "":
                console.print("[yellow]Description is empty after cleaning.")
                return "", imagelist

            description = f"[code]{desc}[/code]"
        else:
            description = ""

        if self.is_only_bbcode(description):
            return "", imagelist

        return description, imagelist

    def clean_ptp_description(self, desc: str, is_disc: str) -> tuple[str, list[dict[str, Any]]]:
        # console.print("[yellow]Cleaning PTP description...")

        # Convert Bullet Points to -
        desc = desc.replace("&bull;", "-")

        # Unescape html
        desc = html.unescape(desc)
        desc = desc.replace("\r\n", "\n")

        # Remove url tags with PTP/HDB links
        url_tags: list[str] = re.findall(
            r"(?:\[url(?:=|\])[^\]]*https?:\/\/passthepopcorn\.m[^\]]*\]|\bhttps?:\/\/passthepopcorn\.m[^\s]+)",
            desc,
            flags=re.IGNORECASE,
        )
        url_tags += [
            "".join(tag)
            for tag in re.findall(
                r"(\[url[\=\]]https?:\/\/hdbits\.o[^\]]+)([^\[]+)(\[\/url\])?",
                desc,
                flags=re.IGNORECASE,
            )
        ]
        if url_tags:
            for url_tag in url_tags:
                url_tag_removed = re.sub(r"(\[url[\=\]]https?:\/\/passthepopcorn\.m[^\]]+])", "", url_tag, flags=re.IGNORECASE)
                url_tag_removed = re.sub(r"(\[url[\=\]]https?:\/\/hdbits\.o[^\]]+])", "", url_tag_removed, flags=re.IGNORECASE)
                url_tag_removed = url_tag_removed.replace("[/url]", "")
                desc = desc.replace(url_tag, url_tag_removed)

        # Remove links to PTP/HDB
        desc = desc.replace("http://passthepopcorn.me", "PTP").replace("https://passthepopcorn.me", "PTP")
        desc = desc.replace("http://hdbits.org", "HDB").replace("https://hdbits.org", "HDB")

        # Catch Stray Images and Prepare Image List
        imagelist: list[dict[str, Any]] = []
        excluded_urls: set[str] = set()

        source_encode_comps = re.findall(r"\[comparison=Source, Encode\][\s\S]*", desc, flags=re.IGNORECASE)
        source_vs_encode_sections = re.findall(r"Source Vs Encode:[\s\S]*", desc, flags=re.IGNORECASE)
        specific_cases = source_encode_comps + source_vs_encode_sections

        # Extract URLs and update excluded_urls
        for block in specific_cases:
            urls = re.findall(r"(https?:\/\/[^\s\[\]]+\.(?:png|jpg))", block, flags=re.IGNORECASE)
            excluded_urls.update(urls)
            desc = desc.replace(block, "")

        # General [comparison=...] handling
        comps = re.findall(r"\[comparison=[\s\S]*?\[\/comparison\]", desc, flags=re.IGNORECASE)
        hides = re.findall(r"\[hide[\s\S]*?\[\/hide\]", desc, flags=re.IGNORECASE)
        comps.extend(hides)
        nocomp = desc

        # Exclude URLs from excluded array fom `nocomp`
        for url in excluded_urls:
            nocomp = nocomp.replace(url, "")

        comp_placeholders: list[str] = []

        # Replace comparison/hide tags with placeholder because sometimes uploaders use comp images as loose images
        for i, comp in enumerate(comps):
            nocomp = nocomp.replace(comp, "")
            desc = desc.replace(comp, f"COMPARISON_PLACEHOLDER-{i} ")
            comp_placeholders.append(comp)

        # as the name implies, protect image links while doing regex things
        def protect_links(desc: str) -> tuple[str, list[str]]:
            links: list[str] = re.findall(r"https?://\S+", desc)
            for i, link in enumerate(links):
                desc = desc.replace(link, f"__LINK_PLACEHOLDER_{i}__")
            return desc, links

        def restore_links(desc: str, links: list[str]) -> str:
            for i, link in enumerate(links):
                desc = desc.replace(f"__LINK_PLACEHOLDER_{i}__", link)
            return desc

        links: list[str] = []

        if is_disc == "DVD":
            desc = re.sub(r"\[mediainfo\][\s\S]*?\[\/mediainfo\]", "", desc)

        elif is_disc == "BDMV":
            desc = re.sub(r"\[mediainfo\][\s\S]*?\[\/mediainfo\]", "", desc)
            desc = re.sub(r"DISC INFO:[\s\S]*?(\n\n|$)", "", desc, flags=re.IGNORECASE)
            desc = re.sub(r"Disc Title:[\s\S]*?(\n\n|$)", "", desc, flags=re.IGNORECASE)
            desc = re.sub(r"Disc Size:[\s\S]*?(\n\n|$)", "", desc, flags=re.IGNORECASE)
            desc = re.sub(r"Protection:[\s\S]*?(\n\n|$)", "", desc, flags=re.IGNORECASE)
            desc = re.sub(r"BD-Java:[\s\S]*?(\n\n|$)", "", desc, flags=re.IGNORECASE)
            desc = re.sub(r"BDInfo:[\s\S]*?(\n\n|$)", "", desc, flags=re.IGNORECASE)
            desc = re.sub(r"PLAYLIST REPORT:[\s\S]*?(?=\n\n|$)", "", desc, flags=re.IGNORECASE)
            desc = re.sub(r"Name:[\s\S]*?(\n\n|$)", "", desc, flags=re.IGNORECASE)
            desc = re.sub(r"Length:[\s\S]*?(\n\n|$)", "", desc, flags=re.IGNORECASE)
            desc = re.sub(r"Size:[\s\S]*?(\n\n|$)", "", desc, flags=re.IGNORECASE)
            desc = re.sub(r"Total Bitrate:[\s\S]*?(\n\n|$)", "", desc, flags=re.IGNORECASE)
            desc = re.sub(r"VIDEO:[\s\S]*?(?=\n\n|$)", "", desc, flags=re.IGNORECASE)
            desc = re.sub(r"AUDIO:[\s\S]*?(?=\n\n|$)", "", desc, flags=re.IGNORECASE)
            desc = re.sub(r"SUBTITLES:[\s\S]*?(?=\n\n|$)", "", desc, flags=re.IGNORECASE)
            desc = re.sub(r"Codec\s+Bitrate\s+Description[\s\S]*?(?=\n\n|$)", "", desc, flags=re.IGNORECASE)
            desc = re.sub(r"Codec\s+Language\s+Bitrate\s+Description[\s\S]*?(?=\n\n|$)", "", desc, flags=re.IGNORECASE)

        else:
            desc = re.sub(r"\[mediainfo\][\s\S]*?\[\/mediainfo\]", "", desc)
            desc = re.sub(r"(^general\nunique)(.*?)^$", "", desc, flags=re.MULTILINE | re.IGNORECASE | re.DOTALL)
            desc = re.sub(r"(^general\ncomplete)(.*?)^$", "", desc, flags=re.MULTILINE | re.IGNORECASE | re.DOTALL)
            desc = re.sub(r"(^(Format[\s]{2,}:))(.*?)^$", "", desc, flags=re.MULTILINE | re.IGNORECASE | re.DOTALL)
            desc = re.sub(r"(^(video|audio|text)( #\d+)?\nid)(.*?)^$", "", desc, flags=re.MULTILINE | re.IGNORECASE | re.DOTALL)
            desc = re.sub(r"(^(menu)( #\d+)?\n)(.*?)^$", "", f"{desc}\n\n", flags=re.MULTILINE | re.IGNORECASE | re.DOTALL)

            desc, links = protect_links(desc)

            desc = re.sub(
                r"\[b\](.*?)(Matroska|DTS|AVC|x264|Progressive|23\.976 fps|16:9|[0-9]+x[0-9]+|[0-9]+ MiB|[0-9]+ Kbps|[0-9]+ bits|cabac=.*?/ aq=.*?|\d+\.\d+ Mbps)\[/b\]",
                "",
                desc,
                flags=re.IGNORECASE | re.DOTALL,
            )
            desc = re.sub(
                r"(Matroska|DTS|AVC|x264|Progressive|23\.976 fps|16:9|[0-9]+x[0-9]+|[0-9]+ MiB|[0-9]+ Kbps|[0-9]+ bits|cabac=.*?/ aq=.*?|\d+\.\d+ Mbps|[0-9]+\s+channels|[0-9]+\.[0-9]+\s+KHz|[0-9]+ KHz|[0-9]+\s+bits)",
                "",
                desc,
                flags=re.IGNORECASE | re.DOTALL,
            )
            desc = re.sub(
                r"\[u\](Format|Bitrate|Channels|Sampling Rate|Resolution):\[/u\]\s*\d*.*?",
                "",
                desc,
                flags=re.IGNORECASE,
            )
            desc = re.sub(
                r"^\s*\d+\s*(channels|KHz|bits)\s*$",
                "",
                desc,
                flags=re.MULTILINE | re.IGNORECASE,
            )

            desc = re.sub(r"^\s+$", "", desc, flags=re.MULTILINE)
            desc = re.sub(r"\n{2,}", "\n", desc)

        desc = restore_links(desc, links)

        # Convert Quote tags:
        desc = re.sub(r"\[quote.*?\]", "[code]", desc)
        desc = desc.replace("[/quote]", "[/code]")

        # Remove Alignments:
        desc = re.sub(r"\[align=.*?\]", "", desc)
        desc = desc.replace("[/align]", "")

        # Remove size tags
        desc = re.sub(r"\[size=.*?\]", "", desc)
        desc = desc.replace("[/size]", "")

        # Remove Videos
        desc = re.sub(r"\[video\][\s\S]*?\[\/video\]", "", desc)

        # Remove Staff tags
        desc = re.sub(r"\[staff[\s\S]*?\[\/staff\]", "", desc)

        # Remove Movie/Person/User/hr/Indent
        remove_list = ["[movie]", "[/movie]", "[artist]", "[/artist]", "[user]", "[/user]", "[indent]", "[/indent]", "[size]", "[/size]", "[hr]"]
        for each in remove_list:
            desc = desc.replace(each, "")

        # Remove Images in IMG tags
        desc = re.sub(r"\[img\][\s\S]*?\[\/img\]", "", desc, flags=re.IGNORECASE)
        desc = re.sub(r"\[img=[\s\S]*?\]", "", desc, flags=re.IGNORECASE)

        # Extract loose images and add to imagelist as dictionaries
        loose_images = re.findall(r"(https?:\/\/[^\s\[\]]+\.(?:png|jpg))", nocomp, flags=re.IGNORECASE)
        for img_url in loose_images:
            if img_url not in excluded_urls:  # Only include URLs not part of excluded sections
                imagelist.append(image_entry(img_url))
                desc = desc.replace(img_url, "")

        # Re-place comparisons
        for i, comp in enumerate(comp_placeholders):
            comp = re.sub(r"\[\/?img[\s\S]*?\]", "", comp, flags=re.IGNORECASE)
            desc = desc.replace(f"COMPARISON_PLACEHOLDER-{i} ", comp)

        # Convert hides with multiple images to comparison
        desc = self.convert_collapse_to_comparison(desc, "hide", hides)

        # Strip blank lines:
        desc = desc.strip("\n")
        desc = re.sub("\n\n+", "\n\n", desc)
        while desc.startswith("\n"):
            desc = desc.replace("\n", "", 1)
        desc = desc.strip("\n")

        if desc.replace("\n", "").strip() == "":
            return "", imagelist
        if self.is_only_bbcode(desc):
            return "", imagelist

        return desc, imagelist

    @staticmethod
    def _strip_generated_metadata(desc: str) -> str:
        """Remove the title/synopsis/info-table/cast/trailer sections a bot-built fiche carries.

        The tool regenerates all of them (and UNIT3D shows them on the fiche anyway);
        only unrecognised free text — encode notes, source info — is worth keeping.
        Each section is matched by its shape, never by its content.
        """
        # Decoration around a label: any mix of [b]/[i]/[size]/[color]/[center] tags
        tag = r"\[/?(?:b|i|center|size(?:=[^\]]*)?|color(?:=[^\]]*)?)\]"
        deco = rf"(?:{tag}|[ \t])*"
        # At least one tag before the text: plain "Synopsis: …" typed by an uploader is not a bot label.
        styled = rf"{deco}{tag}{deco}"
        # "[b][color=…]Title (2024)[/color][/b]" alone on its line
        desc = re.sub(rf"^{styled}[^\[\n]*\(\d{{4}}\){deco}$\n?", "", desc, flags=re.MULTILINE)
        # "Synopsis:" / "cast:" / "By:" labels with their value: the rest of the line
        # and, when the paragraph follows on the next line, that line or [quote] block
        label = r"(?:synopsis|plot|overview|cast|casting|by|director|directed by)\s*:?"
        desc = re.sub(
            rf"^{styled}{label}{deco}[^\n]*\n?(?:[ \t]*(?:\[quote\][\s\S]*?\[/quote\]|[^\[\n][^\n]*)[^\n]*\n?)?",
            "",
            desc,
            flags=re.IGNORECASE | re.MULTILINE,
        )
        # [table] made of metadata rows only (Genre / Rating / Release Date / Language / …)
        info_row = r"\s*\[tr\]\s*\[td\](?:genre|rating|release date|language|runtime|director|year|country|imdb|tmdb)s?\[/td\]\s*\[td\][^\[]*\[/td\]\s*\[/tr\]"
        desc = re.sub(rf"\[table\](?:{info_row})+\s*\[/table\]\s*", "", desc, flags=re.IGNORECASE)
        # Trailer link line
        desc = re.sub(r"^[ \t]*(?:\[b\])?\[url=https?://(?:www\.)?youtu[^\]]*\]\[?Trailer[^\[]*\]?\[/url\](?:\[/b\])?[ \t]*\n?", "", desc, flags=re.IGNORECASE | re.MULTILINE)
        # Empty table skeletons ([tr][td][/td]…[/tr] with nothing inside), possibly centered
        desc = re.sub(r"(?:\[center\])?(?:\s*\[tr\](?:\s*\[td\]\s*\[/td\])+\s*\[/tr\])+\s*(?:\[/center\])?\s*", "\n", desc, flags=re.IGNORECASE)
        return desc

    @staticmethod
    def _strip_generated_pack_blocks(desc: str) -> str:
        """Remove the per-file MediaInfo spoilers and filename headers of a generated pack description."""
        mediainfo_spoiler = re.compile(r"\[spoiler=[^\]]*\]\s*\[b\]General\[/b\](?:(?!\[spoiler)[\s\S])*?\[/spoiler\]", re.IGNORECASE)
        if not mediainfo_spoiler.search(desc):
            return desc
        # Innermost first, until none is left
        while True:
            desc, n = mediainfo_spoiler.subn("", desc)
            if not n:
                break
        # Now-empty "Other files" wrapper and the filename-only headers
        desc = re.sub(r"\[spoiler=Other files\](?:\s|\[/?center\])*\[/spoiler\]", "", desc, flags=re.IGNORECASE)
        desc = re.sub(r"\[center\]\s*[^\s\[\]]+\.[^\s\[\]]+-[\w.]+\s*\[/center\]", "", desc)
        return desc

    def clean_unit3d_description(self, desc: str, site: str) -> tuple[str, list[dict[str, Any]]]:
        # Unescape HTML
        desc = html.unescape(desc)
        # Replace carriage returns with newlines
        desc = desc.replace("\r\n", "\n")

        # Remove links to site
        site_netloc = urllib.parse.urlparse(site).netloc
        site_domain = site_netloc.split(".")[0]
        site_regex = rf"(\[url[\=\]]https?:\/\/{site_domain}\.[^\/\]]+/[^\]]+])([^\[]+)(\[\/url\])?"
        site_url_tags = re.findall(site_regex, desc)
        if site_url_tags:
            for site_url_tag in site_url_tags:
                site_url_tag = "".join(site_url_tag)
                url_tag_regex = rf"(\[url[\=\]]https?:\/\/{site_domain}\.[^\/\]]+[^\]]+])"
                url_tag_removed = re.sub(url_tag_regex, "", site_url_tag)
                url_tag_removed = url_tag_removed.replace("[/url]", "")
                desc = desc.replace(site_url_tag, url_tag_removed)

        # Bare mentions only: a host that is part of a URL or a subdomain
        # (cdn.<site>, i.<site>) must keep its TLD or the link breaks.
        desc = re.sub(rf"(?<![\w./-]){re.escape(site_netloc)}(?![\w-]|\.\w)", site_domain, desc)

        # A description reused from another tracker may itself be a generated
        # pack description: per-file MediaInfo spoilers (nested under "Other
        # files") and a bare filename header. Those get regenerated for this
        # upload, so keeping them would print every file's MediaInfo twice.
        desc = self._strip_generated_pack_blocks(desc)
        desc = self._strip_generated_metadata(desc)

        # Temporarily hide spoiler tags
        spoilers = re.findall(r"\[spoiler[\s\S]*?\[\/spoiler\]", desc)
        nospoil = desc
        spoiler_placeholders: list[str] = []
        for i in range(len(spoilers)):
            nospoil = nospoil.replace(spoilers[i], "")
            desc = desc.replace(spoilers[i], f"SPOILER_PLACEHOLDER-{i} ")
            spoiler_placeholders.append(spoilers[i])

        # Get Images from [img] tags, checking if they're wrapped in [url] tags
        imagelist: list[dict[str, Any]] = []

        # First, find images wrapped in URL tags: [url=web_url][img]img_url[/img][/url]
        url_img_pattern = r"\[url=(https?://[^\]]+)\]\[img[^\]]*\](.*?)\[/img\]\[/url\]"
        url_img_matches = re.findall(url_img_pattern, desc, flags=re.IGNORECASE)
        for web_url, img_url in url_img_matches:
            imagelist.append(image_entry(img_url, web_url))
            # Remove the entire [url=...][img]...[/img][/url] structure
            desc = re.sub(rf"\[url={re.escape(web_url)}\]\[img[^\]]*\]{re.escape(img_url)}\[/img\]\[/url\]", "", desc, flags=re.IGNORECASE)

        # Then find standalone [img] tags (not wrapped in URL)
        img_tags = re.findall(r"\[img[^\]]*\](.*?)\[/img\]", desc, re.IGNORECASE)
        if img_tags:
            for img_url in img_tags:
                img_url = img_url.strip()
                # Check if this image was already added (wrapped in URL)
                if not any(img_url in (img["img_url"], img["raw_url"]) for img in imagelist):
                    imagelist.append(image_entry(img_url))
                # Remove the [img] tag
                desc = re.sub(rf"\[img[^\]]*\]{re.escape(img_url)}\[/img\]", "", desc, flags=re.IGNORECASE)

        # Filter out bot images from imagelist
        bot_image_urls = [
            "https://blutopia.xyz/favicon.ico",  # Example bot image URL
            "https://i.ibb.co/2NVWb0c/uploadrr.webp",
            "https://blutopia/favicon.ico",
            "https://ptpimg.me/606tk4.png",
            # Add any other known bot image URLs here
        ]
        # A thumbnail with no full-size counterpart cannot be reused as a screenshot.
        imagelist = [img for img in imagelist if img["img_url"] not in bot_image_urls and not re.search(r"thumbs", img["raw_url"], re.IGNORECASE)]
        # ptpimg.me is dead: its images (flags, icons, screenshots) must not
        # be reused as if they were live screenshots
        imagelist = [img for img in imagelist if "ptpimg.me" not in str(img.get("raw_url", ""))]

        # Restore spoiler tags
        if spoiler_placeholders:
            for i, spoiler in enumerate(spoiler_placeholders):
                desc = desc.replace(f"SPOILER_PLACEHOLDER-{i} ", spoiler)

        # Check for and clean up empty [center] tags
        centers = re.findall(r"\[center[\s\S]*?\[\/center\]", desc)
        if centers:
            for center in centers:
                # If [center] contains only whitespace or empty tags, remove the entire tag
                cleaned_center = re.sub(r"\[center\]\s*\[\/center\]", "", center)
                cleaned_center = re.sub(r"\[center\]\s+", "[center]", cleaned_center)
                cleaned_center = re.sub(r"\s*\[\/center\]", "[/center]", cleaned_center)
                desc = desc.replace(center, "") if cleaned_center == "[center][/center]" else desc.replace(center, cleaned_center.strip())

        # Remove bot signatures
        bot_signature_regex = r"""
            \[center\]\s*\[img=\d+\]https:\/\/blutopia\.xyz\/favicon\.ico\[\/img\]\s*\[b\]
            Uploaded\sUsing\s\[url=https:\/\/github\.com\/HDInnovations\/UNIT3D\]UNIT3D\[\/url\]\s
            Auto\sUploader\[\/b\]\s*\[img=\d+\]https:\/\/blutopia\.xyz\/favicon\.ico\[\/img\]\s*\[\/center\]|
            \[center\]\s*\[b\]Uploaded\sUsing\s\[url=https:\/\/github\.com\/HDInnovations\/UNIT3D\]UNIT3D\[\/url\]
            \sAuto\sUploader\[\/b\]\s*\[\/center\]|
            \[center\]\[url=https:\/\/github\.com\/z-ink\/uploadrr\]\[img=\d+\]https:\/\/i\.ibb\.co\/2NVWb0c\/uploadrr\.webp\[\/img\]\[\/url\]\[\/center\]|
            \n\[center\]\[url=https:\/\/github\.com\/edge20200\/Only-Uploader\]Powered\sby\s
            Only-Uploader\[\/url\]\[\/center\]|
            \[center\]\[url=\/torrents\?perPage=\d+&name=[^\]]*\]\[\/url\]\[\/center\]
        """
        desc = re.sub(bot_signature_regex, "", desc, flags=re.IGNORECASE | re.VERBOSE)
        # Remove Aither internal signature
        desc = re.sub(
            r"\[center\]\[b\]\[size=\d+\]🖌️\[/size\]\[/b\][\s\S]*?This is an internal release which was first released exclusively on Aither\.[\s\S]*?🍻 Cheers to all the Aither.*?\[/center\]",
            "",
            desc,
            flags=re.IGNORECASE,
        )
        # Remove seedpool signature: the ASCII-art block and the closing
        # seedbrr sentence. The block must show two distinct anchors of the
        # logo — a ".4HH" stroke and the closing ".JHHL." line — so a real
        # NFO code block that merely shares one stroke survives.
        desc = re.sub(r"\s*\[code\]\[center\][^\[]*\.4HH[^\[]*\.JHHL\.\s*\[/center\]\[/code\]\s*", "\n\n", desc, flags=re.IGNORECASE).strip()
        # The tool name after "with" varies per uploader (seedbrr, seed-tools, …);
        # the bounded character class stops before any BBCode bracket.
        desc = re.sub(r"\s*Posted to this fine tracker with [\w -]{1,40}\.?", "", desc, flags=re.IGNORECASE)
        # Same family of tool signatures, variable "sponsor" name.
        desc = re.sub(r"\s*This description is rendered for you via config\.yaml and is sponsored by [\w -]{1,40}\.?", "", desc, flags=re.IGNORECASE)
        # Boilerplate note about tonemapped screenshots — meaningless once the
        # screenshots are re-rendered by the destination tracker
        desc = re.sub(r"\s*Screenshots have been tonemapped for reference\s*\.?", "", desc, flags=re.IGNORECASE)
        # ...and its sample-link spoiler ([b][spoiler=Sample: xyz]url[/spoiler][/b])
        desc = re.sub(r"\s*(\[b\])?\[spoiler=Sample[^\]]*\][\s\S]*?\[/spoiler\](\[/b\])?\s*", "\n\n", desc, flags=re.IGNORECASE).strip()
        # ptpimg.me is dead: comparison blocks whose images live there are all
        # broken — drop the block and its "[b]… Comparison[/b]" header line.
        # A comparison body holds only bare URLs, so [^\[]* spans it safely
        # and blocks hosted elsewhere are left untouched.
        desc = re.sub(
            r"\s*(?:\[b\][^\[\]]*comparison[^\[\]]*\[/b\]\s*)?\[comparison=[^\]]*\][^\[]*ptpimg\.me[^\[]*\[/comparison\]\s*",
            "\n\n",
            desc,
            flags=re.IGNORECASE,
        ).strip()
        desc = re.sub(r"\[center\].*Created by.*Upload Assistant.*\[\/center\]", "", desc, flags=re.IGNORECASE)
        desc = re.sub(r"\[right\].*Created by.*Upload Assistant.*\[\/right\]", "", desc, flags=re.IGNORECASE)
        # ...and bare (unwrapped) signature lines: only complete lines made of
        # the marker plus known BBCode wrappers — ordinary note text that
        # merely mentions a tool name must survive.
        _sig_decor = r"(?:\[/?(?:center|right|b|i|u|url(?:=[^\]]*)?|size(?:=[^\]]*)?|color(?:=[^\]]*)?)\]|[^\w\n\[\]])*"
        for _sig_marker in (
            r"Created by Upload Assistant(?:\s+v?[\w.]+)?",
            r"Powered by GG-BOT Upload Assistant(?:\s+v?[\w.]+)?",
            r"Uploaded with (?:\[/?color(?:=[^\]]*)?\]|[^\w\n\[\]])*using GG-BOT Upload Assistant(?:\s+v?[\w.]+)?",
            r"Created by Hentai Bot(?:\s+v?[\w.]+)?",
            r"Brought to you by Only-Uploader(?:\s+v?[\w.]+)?",
            r"Uploaded using EASY UPLOAD3R(?:\s+v?[\w.]+)?",
            r"Uploaded by upbrr(?:\s+v?[\w.]+)?",
            r"A UNIT3D plugin proudly developed by (?:\[/?b\])?[\w.\-]{1,40}",
            r"Shared with Upload-Assistant(?:\s+v?[\w.]+)?(?:\s+\(fork\))?",
            r"OnlyEncodes Upload Assistant(?:\s+v?[\w.]+)?",
            r"OnlyEncodes Uploader(?:\s*[-–]\s*Powered by L4G'?s Upload Assistant)?",
            r"Created with mkbrr, ffmpeg,? and mediainfo",
            r"This release is sourced from [\w+ ]{1,30} and is not transcoded, just remuxed from the direct [\w+ ]{1,30} stream",
            r"Please PM [\w.\-]{1,40} if you have any issues(?: or need a reseed)?",
        ):
            desc = re.sub(rf"^\s*{_sig_decor}{_sig_marker}\s*[.!]?\s*{_sig_decor}\s*$\n?", "", desc, flags=re.IGNORECASE | re.MULTILINE)
        # Group signatures pointing at another tracker's search page
        # ("Find our uploads [url=…]here[/url]"), wherever they sit on the line.
        desc = re.sub(r"(?:\[center\])?\s*Find (?:our|my) uploads\s*\[url=[^\]]*\][^\[]*\[/url\]\.?\s*(?:\[/center\])?", "", desc, flags=re.IGNORECASE)
        # UNIT3D-internal [note] tags: drop empty blocks, unwrap the rest
        desc = re.sub(r"\[note\]\s*\[/note\]\s*", "", desc, flags=re.IGNORECASE)
        desc = re.sub(r"\[/?note\]", "", desc, flags=re.IGNORECASE)
        # Embedded video players don't render outside the source site
        desc = re.sub(r"\[youtube\][^\[]*\[/youtube\]\n?", "", desc, flags=re.IGNORECASE)
        # Empty [code] blocks (an NFO placeholder left blank), with any
        # [center] wrapper that would otherwise be left empty too
        desc = re.sub(r"(\[center\])?[^\S\n]*\[code\]\s*\[/code\][^\S\n]*(?(1)\[/center\])[^\S\n]*\n?", "", desc, flags=re.IGNORECASE)
        # ...and [center] wrappers the removals above left empty
        desc = re.sub(r"\[center\]\s*\[/center\][^\S\n]*\n?", "", desc, flags=re.IGNORECASE)

        # Remove leftover [img] or [URL] tags in the description — mostly
        # images inside [spoiler] blocks, which are shielded from extraction.
        # The sized form must go WITH its URL and closing tag: stripping only
        # the [img=N] opener leaves an orphan "url[/img]" behind.
        desc = re.sub(r"\[img\][\s\S]*?\[\/img\]", "", desc, flags=re.IGNORECASE)
        desc = re.sub(r"\[img=[^\]]*\][\s\S]*?\[\/img\]", "", desc, flags=re.IGNORECASE)
        desc = re.sub(r"\[img=[^\]]*\]", "", desc, flags=re.IGNORECASE)
        # desc = re.sub(r"\[URL=[\s\S]*?\]\[\/URL\]", "", desc, flags=re.IGNORECASE)

        # Drop unmatched [url] tags left behind by the removals above — e.g.
        # a stripped site link whose label itself contained brackets, which
        # stops the label capture early and leaves the closing tag behind.
        def _drop_unmatched(text: str, token_pattern: str) -> str:
            token_re = re.compile(token_pattern, re.IGNORECASE)
            stack: list[tuple[int, int]] = []
            orphans: list[tuple[int, int]] = []
            for token_match in token_re.finditer(text):
                if token_match.group(0).startswith("[/"):
                    if stack:
                        stack.pop()
                    else:
                        orphans.append((token_match.start(), token_match.end()))
                else:
                    stack.append((token_match.start(), token_match.end()))
            orphans.extend(stack)
            for start, end in sorted(orphans, reverse=True):
                text = text[:start] + text[end:]
            return text

        desc = _drop_unmatched(desc, r"\[url(?:=[^\]]*)?\]|\[/url\]")

        # Screenshot headers are orphaned once their images were extracted
        # above (no [img] survives at this point): drop short lines that are
        # just a screenshots keyword, with or without [center]/[b]/[color]/
        # [size] decoration ("SCREENSHOTS", "Screens", "Captures d'écran :"…).
        # Decoration = known BBCode tags or any non-alphanumeric character
        # (dashes, dots, ornaments like ❅✧✦…), in any order around the keyword
        _wrap = r"(?:\[/?(?:center|b|i|u|h[1-6]|size(?:=[^\]]*)?|color(?:=[^\]]*)?)\]|[^\w\n\[\]])*"
        _keyword = r"(?:screen\s?shots?|screens|captures?(?:\s+d['’]?[ée]cran)?)"
        orphan_header_re = re.compile(rf"^{_wrap}{_keyword}{_wrap}$", re.IGNORECASE)
        desc = "\n".join(line for line in desc.split("\n") if not orphan_header_re.match(line))
        # A dropped header line may have carried the opening [hN] of a block
        # that continues below it: sweep the now-unmatched heading tags.
        desc = _drop_unmatched(desc, r"\[/?h[1-6]\]")
        # Bot fiches are often unbalanced ([/center] without its opener): sweep those too.
        desc = _drop_unmatched(desc, r"\[/?center\]")

        # Strip trailing whitespace and newlines:
        desc = desc.rstrip()

        if desc.replace("\n", "") == "":
            return "", imagelist
        if self.is_only_bbcode(desc):
            return "", imagelist
        return desc, imagelist

    def is_only_bbcode(self, desc: str) -> bool:
        # Remove all BBCode tags
        text = re.sub(r"\[/?[a-zA-Z0-9]+(?:=[^\]]*)?\]", "", desc)
        # Remove whitespace and newlines
        text = text.strip()
        # If nothing left, it's only BBCode
        return not text

    def convert_pre_to_code(self, desc: str) -> str:
        desc = desc.replace("[pre]", "[code]")
        desc = desc.replace("[/pre]", "[/code]")
        return desc

    def convert_code_to_pre(self, desc: str) -> str:
        desc = desc.replace("[code]", "[pre]")
        desc = desc.replace("[/code]", "[/pre]")
        return desc

    def convert_hide_to_spoiler(self, desc: str) -> str:
        desc = desc.replace("[hide", "[spoiler")
        desc = desc.replace("[/hide]", "[/spoiler]")
        return desc

    def convert_spoiler_to_hide(self, desc: str) -> str:
        desc = desc.replace("[spoiler", "[hide")
        desc = desc.replace("[/spoiler]", "[/hide]")
        return desc

    def remove_hide(self, desc: str) -> str:
        desc = desc.replace("[hide]", "").replace("[/hide]", "")
        return desc

    def convert_named_spoiler_to_named_hide(self, desc: str) -> str:
        """
        Converts [spoiler=Name] to [hide=Name]
        """
        desc = re.sub(r"\[spoiler=([^]]+)]", r"[hide=\1]", desc, flags=re.IGNORECASE)
        desc = desc.replace("[/spoiler]", "[/hide]")
        return desc

    def remove_spoiler(self, desc: str) -> str:
        desc = re.sub(r"\[\/?spoiler[\s\S]*?\]", "", desc, flags=re.IGNORECASE)
        return desc

    def remove_color(self, desc: str) -> str:
        """
        Removes [color=...] and [/color] tags.
        """
        pattern = r"\[/?color(?:=[^\]]*)?\]"
        return re.sub(pattern, "", desc, flags=re.IGNORECASE)

    def convert_named_spoiler_to_normal_spoiler(self, desc: str) -> str:
        desc = re.sub(r"(\[spoiler=[^]]+])", "[spoiler]", desc, flags=re.IGNORECASE)
        return desc

    def convert_spoiler_to_code(self, desc: str) -> str:
        desc = desc.replace("[spoiler", "[code")
        desc = desc.replace("[/spoiler]", "[/code]")
        return desc

    def convert_code_to_quote(self, desc: str) -> str:
        desc = desc.replace("[code", "[quote")
        desc = desc.replace("[/code]", "[/quote]")
        return desc

    def remove_img_resize(self, desc: str) -> str:
        """
        Converts [img=number] or any other parameters to just [img]
        """
        desc = re.sub(r"\[img(?:[^\]]*)\]", "[img]", desc, flags=re.IGNORECASE)
        return desc

    def remove_extra_lines(self, desc: str) -> str:
        """
        Removes more than 2 consecutive newlines
        """
        desc = re.sub(r"\n{3,}", "\n\n", desc)
        return desc

    def convert_to_align(self, desc: str) -> str:
        """
        Converts [right], [left], [center] to [align=right], [align=left], [align=center]
        """
        desc = re.sub(r"\[(right|center|left)\]", lambda m: f"[align={m.group(1)}]", desc)
        desc = re.sub(r"\[/(right|center|left)\]", "[/align]", desc)
        return desc

    def remove_sup(self, desc: str) -> str:
        """
        Removes [sup] tags
        """
        desc = desc.replace("[sup]", "").replace("[/sup]", "")
        return desc

    def remove_sub(self, desc: str) -> str:
        """
        Removes [sub] tags
        """
        desc = desc.replace("[sub]", "").replace("[/sub]", "")
        return desc

    def remove_list(self, desc: str) -> str:
        """
        Removes [list] tags
        """
        desc = desc.replace("[list]", "").replace("[/list]", "")
        return desc

    def convert_comparison_to_collapse(self, desc: str, max_width: int) -> str:
        comparisons = re.findall(r"\[comparison=[\s\S]*?\[\/comparison\]", desc)
        for comp in comparisons:
            line: list[str] = []
            output: list[str] = []
            comp_sources = comp.split("]", 1)[0].replace("[comparison=", "").replace(" ", "").split(",")
            comp_images = comp.split("]", 1)[1].replace("[/comparison]", "").replace(",", "\n").replace(" ", "\n")
            comp_images = re.findall(r"(https?:\/\/.*\.(?:png|jpg))", comp_images, flags=re.IGNORECASE)
            screens_per_line = len(comp_sources)
            img_size = int(max_width / screens_per_line)
            if img_size > 350:
                img_size = 350
            for img in comp_images:
                img = img.strip()
                if img != "":
                    bb = f"[url={img}][img={img_size}]{img}[/img][/url]"
                    line.append(bb)
                    if len(line) == screens_per_line:
                        output.append("".join(line))
                        line = []
            output_str = "\n".join(output)
            new_bbcode = f"[spoiler={' vs '.join(comp_sources)}][center]{' | '.join(comp_sources)}[/center]\n{output_str}[/spoiler]"
            desc = desc.replace(comp, new_bbcode)
        return desc

    def convert_comparison_to_centered(self, desc: str, max_width: int) -> str:
        comparisons = re.findall(r"\[comparison=[\s\S]*?\[\/comparison\]", desc)
        for comp in comparisons:
            line: list[str] = []
            output: list[str] = []
            comp_sources = comp.split("]", 1)[0].replace("[comparison=", "").strip()
            comp_sources = re.split(r"\s*,\s*", comp_sources)
            comp_images = comp.split("]", 1)[1].replace("[/comparison]", "").replace(",", "\n").replace(" ", "\n")
            comp_images = re.findall(r"(https?:\/\/.*\.(?:png|jpg))", comp_images, flags=re.IGNORECASE)
            screens_per_line = len(comp_sources)
            img_size = int(max_width / screens_per_line)
            if img_size > 350:
                img_size = 350
            for img in comp_images:
                img = img.strip()
                if img != "":
                    bb = f"[url={img}][img={img_size}]{img}[/img][/url]"
                    line.append(bb)
                    if len(line) == screens_per_line:
                        output.append("".join(line))
                        line = []
            output_str = "\n".join(output)
            new_bbcode = f"[center]{' | '.join(comp_sources)}\n{output_str}[/center]"
            desc = desc.replace(comp, new_bbcode)
        return desc

    def convert_collapse_to_comparison(self, desc: str, spoiler_hide: str, collapses: list[str]) -> str:
        # Convert Comparison spoilers to [comparison=]
        if collapses != []:
            for i in range(len(collapses)):
                tag = collapses[i]
                images = re.findall(r"\[img[\s\S]*?\[\/img\]", tag, flags=re.IGNORECASE)
                if len(images) >= 6:
                    comp_images: list[str] = []
                    final_sources: list[str] = []
                    for image in images:
                        image_url = re.sub(r"\[img[\s\S]*\]", "", image.replace("[/img]", ""), flags=re.IGNORECASE)
                        comp_images.append(image_url)
                    sources = ""
                    if spoiler_hide == "spoiler":
                        spoiler_match = re.match(r"\[spoiler[\s\S]*?\]", tag)
                        if spoiler_match:
                            sources = spoiler_match[0].replace("[spoiler=", "")[:-1]
                        else:
                            continue
                    elif spoiler_hide == "hide":
                        hide_match = re.match(r"\[hide[\s\S]*?\]", tag)
                        if hide_match:
                            sources = hide_match[0].replace("[hide=", "")[:-1]
                        else:
                            continue
                    if not sources:
                        continue
                    sources = re.sub("comparison", "", sources, flags=re.IGNORECASE)
                    for each in ["vs", ",", "|"]:
                        sources_list = sources.split(each)
                        sources = "$".join(sources_list)
                    sources_list = sources.split("$")
                    final_sources = [source.strip() for source in sources_list]
                    comp_images_str = "\n".join(comp_images)
                    final_sources_str = ", ".join(final_sources)
                    spoil2comp = f"[comparison={final_sources_str}]{comp_images_str}[/comparison]"
                    desc = desc.replace(tag, spoil2comp)
        return desc
