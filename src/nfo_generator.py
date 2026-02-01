# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
"""MediaInfo-based NFO generator for trackers that require/support NFO files."""

import os
from typing import Any

import aiofiles

from src.console import console


class SceneNfoGenerator:
    """Generates MediaInfo-based NFO files for releases."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    async def generate_nfo(
        self,
        meta: dict[str, Any],
        tracker: str,
        output_dir: str | None = None,
    ) -> str | None:
        """
        Generate a MediaInfo-based NFO file.

        Args:
            meta: Release metadata dictionary
            tracker: Tracker name (for customization)
            output_dir: Output directory (defaults to tmp/{uuid}/)

        Returns:
            Path to generated NFO file, or None on failure
        """
        try:
            # Determine output directory
            if output_dir is None:
                output_dir = os.path.join(meta['base_dir'], "tmp", meta['uuid'])

            os.makedirs(output_dir, exist_ok=True)

            # Get release name
            release_name = meta.get('name', meta.get('uuid', 'Unknown'))
            if isinstance(release_name, dict):
                release_name = release_name.get('name', meta.get('uuid', 'Unknown'))

            # Get MediaInfo content
            nfo_content = await self._get_mediainfo_content(meta)

            if not nfo_content:
                console.print(f"[yellow]{tracker}: No MediaInfo available for NFO generation[/yellow]")
                return None

            # Save NFO file
            nfo_filename = f"{release_name}.nfo"
            nfo_path = os.path.join(output_dir, nfo_filename)

            async with aiofiles.open(nfo_path, 'w', encoding='utf-8') as f:
                await f.write(nfo_content)

            if meta.get('debug'):
                console.print(f"[green]NFO generated: {nfo_path}[/green]")

            return nfo_path

        except Exception as e:
            console.print(f"[red]Failed to generate NFO: {e}[/red]")
            return None

    async def _get_mediainfo_content(self, meta: dict[str, Any]) -> str | None:
        """Get MediaInfo text content from meta or file."""

        # First try: Check for MEDIAINFO_CLEANPATH.txt (clean path version)
        cleanpath_file = os.path.join(
            meta.get('base_dir', ''),
            "tmp",
            meta.get('uuid', ''),
            "MEDIAINFO_CLEANPATH.txt"
        )
        if os.path.exists(cleanpath_file):
            async with aiofiles.open(cleanpath_file, encoding='utf-8') as f:
                content = await f.read()
                if content.strip():
                    return content

        # Second try: Check for MEDIAINFO.txt
        mediainfo_file = os.path.join(
            meta.get('base_dir', ''),
            "tmp",
            meta.get('uuid', ''),
            "MEDIAINFO.txt"
        )
        if os.path.exists(mediainfo_file):
            async with aiofiles.open(mediainfo_file, encoding='utf-8') as f:
                content = await f.read()
                if content.strip():
                    return content

        # Third try: Get from meta['mediainfo_text'] if available
        if meta.get('mediainfo_text'):
            return meta['mediainfo_text']

        return None
