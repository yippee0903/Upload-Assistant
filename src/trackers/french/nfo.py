"""NFO discovery/generation and torrent re-creation with NFO. Maps to upbrr media.go (artifacts)."""

import asyncio
import glob
import hashlib
import os
import re
from typing import Any, Union

from src.console import console
from src.nfo_generator import SceneNfoGenerator, is_multi_episode_nfo
from src.torrentcreate import TorrentCreator
from src.trackers.COMMON import COMMON

Meta = dict[str, Any]


class FrenchNfoMixin:
    """NFO discovery/generation and torrent re-creation with NFO. Maps to upbrr media.go (artifacts)."""

    # Signals that this tracker auto-detects NFO files on disk and includes them in
    # the torrent.  Used by upload.py to proactively set keep_nfo before BASE creation
    # so that BASE.torrent already contains the NFO (avoids a later full rehash).
    auto_nfo: bool = True

    def _get_nfo_files(self, meta: Meta) -> list[str]:
        """Get NFO files in the release folder (including subdirectories).

        Used by French trackers to include NFO files in .torrent and API upload."""
        path = str(meta.get("path", ""))
        if os.path.isdir(path):
            # Directory release: search top-level first, then subdirectories (season packs)
            nfo_files = glob.glob(os.path.join(path, "*.nfo"))
            if not nfo_files:
                nfo_files = glob.glob(os.path.join(path, "**", "*.nfo"), recursive=True)
        else:
            # Single-file release: only match an NFO with the same base name
            stem = os.path.splitext(path)[0]
            nfo_path = f"{stem}.nfo"
            nfo_files = [nfo_path] if os.path.isfile(nfo_path) else []
        if nfo_files:
            meta["keep_nfo"] = True
        return nfo_files

    async def _patch_torrent_with_nfo(
        self,
        meta: Meta,
        source_torrent_path: str,
        nfo_files: list[str],
    ) -> str | None:
        """Create [tracker].torrent from an existing torrent + NFO without full rehash.

        Appends NFO files to the END of the file list (after existing media
        files) so that all piece hashes for the original content stay valid.
        Only the last piece (which now includes NFO data) needs to be
        recomputed by reading a few MB from disk instead of the full content.
        """
        import asyncio

        from torf import Torrent

        from src.console import console

        try:
            src = Torrent.read(source_torrent_path)
            info = src.metainfo["info"]
            piece_size: int = info["piece length"]
            old_pieces_raw: bytes = info["pieces"]
            old_files: list[dict[str, Any]] = info["files"]
        except Exception:
            return None

        content_path = str(meta.get("path", ""))
        if not os.path.isdir(content_path):
            return None

        old_piece_count = len(old_pieces_raw) // 20

        tracker_name = getattr(self, "tracker", "")
        source_flag = getattr(self, "source_flag", "")
        tracker_config = self.config["TRACKERS"].get(tracker_name, {})  # type: ignore[attr-defined]
        announce_url = str(tracker_config.get("announce_url", "https://fake.tracker")).strip()
        if not tracker_name or not source_flag or not announce_url or announce_url == "https://fake.tracker":
            return None
        output_path = os.path.join(meta["base_dir"], "tmp", meta["uuid"], f"[{tracker_name}].torrent")

        result = await asyncio.to_thread(
            self._patch_torrent_with_nfo_sync,
            src,
            old_files,
            old_pieces_raw,
            old_piece_count,
            piece_size,
            content_path,
            nfo_files,
            source_flag,
            announce_url,
            output_path,
        )
        if result:
            nfo_kb, tail_mb = result
            console.print(f"[green]Patched torrent with NFO ({nfo_kb:.1f} KB) — read {tail_mb:.1f} MB instead of full rehash[/green]")
            return output_path
        return None

    @staticmethod
    def _patch_torrent_with_nfo_sync(
        src: Any,
        old_files: list[dict[str, Any]],
        old_pieces_raw: bytes,
        old_piece_count: int,
        piece_size: int,
        content_path: str,
        nfo_files: list[str],
        source_flag: str,
        announce_url: str,
        output_path: str,
    ) -> tuple[float, float] | None:
        """Synchronous core of _patch_torrent_with_nfo (runs in a thread)."""
        from torf import Torrent

        # Bail out if any NFO file already exists in the source torrent
        existing_rel_paths = {tuple(f_info["path"]) for f_info in old_files if f_info.get("path")}

        # Read NFO file data and build new file entries (appended at end)
        nfo_entries: list[dict[str, Any]] = []
        nfo_data = b""
        for nfo_path in sorted(nfo_files):
            # Compute path components relative to content_path
            rel = os.path.relpath(nfo_path, content_path)
            path_components = rel.replace("\\", "/").split("/")

            # Skip NFOs that live outside the release tree: they have no valid
            # in-torrent path. They are still delivered through the tracker's
            # separate NFO upload field, exactly like the generated MediaInfo NFO.
            if os.path.isabs(rel) or ".." in path_components:
                continue

            if tuple(path_components) in existing_rel_paths:
                return None

            try:
                with open(nfo_path, "rb") as f:  # noqa: ASYNC230
                    data = f.read()
            except Exception:
                return None
            nfo_entries.append({"length": len(data), "path": path_components})
            nfo_data += data

        if not nfo_data:
            return None

        # Determine which piece is the last one containing existing file data
        last_piece_idx = max(0, old_piece_count - 1)
        last_piece_start = last_piece_idx * piece_size

        # Read the data for the last piece from the content on disk.
        # Walk through old files to find the file(s) that overlap with this piece.
        offset = 0
        last_piece_data = b""
        for f_info in old_files:
            f_length: int = f_info["length"]
            f_name = os.path.join(content_path, *f_info["path"])
            file_end = offset + f_length
            if file_end <= last_piece_start:
                offset = file_end
                continue
            # This file overlaps with the last piece
            try:
                actual_size = os.path.getsize(f_name)
            except OSError:
                return None
            if actual_size != f_length:
                return None
            read_start = max(0, last_piece_start - offset)
            try:
                with open(f_name, "rb") as fh:  # noqa: ASYNC230
                    fh.seek(read_start)
                    last_piece_data += fh.read(f_length - read_start)
            except Exception:
                return None
            offset = file_end

        # Append all NFO data after the existing content
        last_piece_data += nfo_data

        # Compute piece hashes for this tail portion (usually just 1 piece)
        new_tail_hashes = b""
        for i in range(0, len(last_piece_data), piece_size):
            chunk = last_piece_data[i : i + piece_size]
            new_tail_hashes += hashlib.sha1(chunk, usedforsecurity=False).digest()  # nosec B324

        # Build final pieces: keep unchanged prefix, replace tail
        unchanged_prefix = old_pieces_raw[: last_piece_idx * 20]
        final_pieces = unchanged_prefix + new_tail_hashes

        # Build a copy of the source torrent with updated file list and pieces
        patched = Torrent.copy(src)
        patched.metainfo["info"]["files"] = list(old_files) + nfo_entries
        patched.metainfo["info"]["pieces"] = final_pieces
        patched.metainfo["info"]["source"] = source_flag
        patched.metainfo["comment"] = ""
        patched.metainfo["announce"] = announce_url

        # Strip residual tracker/seed fields from the source torrent
        for key in ("announce-list", "url-list", "httpseeds", "nodes"):
            patched.metainfo.pop(key, None)

        try:
            patched.write(output_path, overwrite=True)
        except Exception:
            return None

        nfo_kb = len(nfo_data) / 1024
        tail_mb = len(last_piece_data) / (1024 * 1024)
        return (nfo_kb, tail_mb)

    @staticmethod
    def _patch_mi_filename(mi_text: str, new_name: str) -> str:
        """Replace the ‘Complete name’ value in MediaInfo text with *new_name*.

        French trackers rename releases (language tags, notag label, French
        title…), so the original filename inside a MediaInfo report no longer
        matches the generated release name — some sites (e.g. C411) even
        validate the two against each other.  This patches the ‘Complete
        name’ line while preserving the file extension.
        """
        if not mi_text or not new_name:
            return mi_text

        def _replace_complete_name(match: re.Match[str]) -> str:
            prefix = match.group(1)  # "Complete name    : "
            old_value = match.group(2)
            ext_match = re.search(r"(\.[a-zA-Z0-9]{2,4})$", old_value)
            ext = ext_match.group(1) if ext_match else ""
            return f"{prefix}{new_name}{ext}"

        return re.sub(
            r"^(Complete name\s*:\s*)(.+)$",
            _replace_complete_name,
            mi_text,
            count=1,
            flags=re.MULTILINE,
        )

    async def _get_or_generate_nfo(self, meta: Meta) -> Union[str, None]:
        """Pick the NFO to upload: the release's own NFO when present,
        otherwise a MediaInfo file or a generated scene NFO.

        Useful for trackers that expect an NFO with every upload (e.g. C411).
        """
        nfo_files = self._get_nfo_files(meta)
        if nfo_files and not await is_multi_episode_nfo(nfo_files[0]):
            return nfo_files[0]
        else:
            return await self._get_or_generate_mediainfo_as_nfo(meta)

    async def _get_or_generate_mediainfo_as_nfo(self, meta: Meta) -> Union[str, None]:
        """Sub-function of _get_or_generate_nfo to get MI file if exists
        Else, generate a NFO
        """
        mi_dir = os.path.join(meta.get("base_dir", ""), "tmp", meta.get("uuid", ""))
        mi_clean = os.path.join(mi_dir, "MEDIAINFO_CLEANPATH.txt")
        mi = os.path.join(mi_dir, "MEDIAINFO.txt")
        if os.path.isfile(mi_clean):
            return mi_clean
        elif os.path.isfile(mi):
            return mi
        else:
            nfo_gen = SceneNfoGenerator(self.config)
            return await nfo_gen.generate_nfo(meta, self.tracker)

    async def _recreated_torrent_if_nfo(self, meta: dict[str, Any], common: COMMON, config: dict[str, Any], tracker: str, source_flag: str) -> str:
        """Re-create a .torrent if NFO is provided.

        Some trackers requires the NFO if provided
        by releaser. We generated a .torrent with
        it if needed
        """
        nfo_files = self._get_nfo_files(meta)
        if nfo_files:
            upload_torrent_path = os.path.join(meta["base_dir"], "tmp", meta["uuid"], f"[{tracker}].torrent")

            # Reuse existing torrent if it already contains .nfo files
            if os.path.exists(upload_torrent_path):
                try:
                    from torf import Torrent

                    existing = Torrent.read(upload_torrent_path)
                    has_nfo = any(str(f).lower().endswith(".nfo") for f in existing.files)
                    if has_nfo:
                        meta["upload_torrent_path"] = upload_torrent_path
                        return nfo_files[0]
                except Exception:
                    pass  # Fall through to recreation

            # If BASE.torrent already contains NFO, clone it (no rehash needed)
            base_torrent_path = os.path.join(meta["base_dir"], "tmp", meta["uuid"], "BASE.torrent")
            if os.path.exists(base_torrent_path):
                try:
                    from torf import Torrent

                    base = Torrent.read(base_torrent_path)
                    if any(str(f).lower().endswith(".nfo") for f in base.files):
                        await common.create_torrent_for_upload(meta, tracker, source_flag)
                        meta["upload_torrent_path"] = upload_torrent_path
                        return nfo_files[0]
                except Exception:
                    pass  # Fall through to full rehash

            # Check if another tracker already created a torrent with NFO (avoid duplicate rehash)
            tmp_dir = os.path.join(meta["base_dir"], "tmp", meta["uuid"])
            for fname in os.listdir(tmp_dir):
                if fname.startswith("[") and fname.endswith("].torrent") and fname != f"[{tracker}].torrent":
                    try:
                        from torf import Torrent

                        other = Torrent.read(os.path.join(tmp_dir, fname))
                        if any(str(f).lower().endswith(".nfo") for f in other.files):
                            await common.create_torrent_for_upload(meta, tracker, source_flag, torrent_filename=fname.replace(".torrent", ""))
                            meta["upload_torrent_path"] = upload_torrent_path
                            return nfo_files[0]
                    except Exception:  # nosec B112
                        continue

            # Patch an existing torrent by appending NFO to the file list.
            # Only the last piece needs rehashing (a few MB instead of the full content).
            patch_source = None
            if os.path.exists(base_torrent_path):
                patch_source = base_torrent_path
            else:
                # Try any tracker torrent as source
                for fname in os.listdir(tmp_dir):
                    if fname.startswith("[") and fname.endswith("].torrent") and fname != f"[{tracker}].torrent":
                        patch_source = os.path.join(tmp_dir, fname)
                        break
            if patch_source:
                try:
                    patched = await self._patch_torrent_with_nfo(meta, patch_source, nfo_files)
                    if patched and os.path.exists(patched):
                        meta["upload_torrent_path"] = upload_torrent_path
                        return nfo_files[0]
                except Exception as e:
                    console.print(f"[yellow]NFO patch failed ({e}), falling back to full rehash[/yellow]")

            tracker_config = config["TRACKERS"].get(tracker, {})
            tracker_url = str(tracker_config.get("announce_url", "https://fake.tracker")).strip()
            torrent_create = f"[{tracker}]"
            try:
                cooldown = int(config.get("DEFAULT", {}).get("rehash_cooldown", 0) or 0)
            except (ValueError, TypeError):
                cooldown = 0
            if cooldown > 0:
                await asyncio.sleep(cooldown)
            await TorrentCreator.create_torrent(meta, str(meta["path"]), torrent_create, tracker_url=tracker_url)
            if not os.path.exists(upload_torrent_path):
                raise FileNotFoundError(f"Failed to create {upload_torrent_path}")
            meta["upload_torrent_path"] = upload_torrent_path
            return nfo_files[0]
        else:
            return ""
