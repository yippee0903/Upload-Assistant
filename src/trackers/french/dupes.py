"""French language hierarchy applied to duplicate candidates. Maps to upbrr dupe.go."""

from typing import Any

from src.trackers.french.languages import _FRENCH_AUDIO_THRESHOLD

Meta = dict[str, Any]


class FrenchDupeMixin:
    """French language hierarchy applied to duplicate candidates. Maps to upbrr dupe.go."""

    async def _check_french_lang_dupes(
        self,
        dupes: list[dict[str, Any]],
        meta: Meta,
    ) -> list[dict[str, Any]]:
        """Filter and flag dupes based on French language hierarchy.

        On French trackers:

        1. **Upload has French audio** (MULTI, VFF, …): existing releases
           that *lack* French audio (VOSTFR, VO) are **removed** from the
           dupe list — they are inferior and do not block the upload.

        2. **Upload lacks French audio** (VOSTFR, VO): existing releases
           that *have* French audio are **flagged** with
           ``'french_lang_supersede'`` so the dupe checker keeps them as
           blocking dupes regardless of other exclusion criteria.
        """
        upload_audio = await self._build_audio_string(meta)

        # MUET (silent film) — special category, not subject to French lang checks
        if upload_audio.startswith("MUET"):
            return dupes

        # Determine the upload's French language level
        upload_tag, upload_level = self._extract_french_lang_tag(upload_audio)
        if not upload_tag:
            # No recognised tag in the audio string — try the raw string
            # e.g. "MULTI.VFF" → extract "MULTI"
            for part in upload_audio.split("."):
                t, lv = self._extract_french_lang_tag(part)
                if lv > upload_level:
                    upload_tag, upload_level = t, lv

        # ── Case 1: Upload HAS French audio → drop inferior dupes ──
        if upload_level >= _FRENCH_AUDIO_THRESHOLD:
            filtered: list[dict[str, Any]] = []
            for dupe in dupes:
                name = dupe.get("name", "") if isinstance(dupe, dict) else str(dupe)
                _, existing_level = self._extract_french_lang_tag(name)
                # Keep the dupe only if it also has French audio (or no tag at all,
                # meaning we can't tell — safer to show it)
                if existing_level >= _FRENCH_AUDIO_THRESHOLD or existing_level == 0:
                    filtered.append(dupe)
                # else: existing is VOSTFR/VO — inferior, silently drop
            return filtered

        # ── Case 2: Upload LACKS French audio → flag superior dupes ──
        if upload_audio in ("VOSTFR", "") or upload_level < _FRENCH_AUDIO_THRESHOLD:
            for dupe in dupes:
                name = dupe.get("name", "") if isinstance(dupe, dict) else str(dupe)
                _, existing_level = self._extract_french_lang_tag(name)
                if existing_level >= _FRENCH_AUDIO_THRESHOLD and isinstance(dupe, dict):
                    flags: list[str] = dupe.setdefault("flags", [])
                    if "french_lang_supersede" not in flags:
                        flags.append("french_lang_supersede")

        return dupes

    async def search_existing(self, meta: Meta, _: Any = None) -> list[dict[str, Any]]:
        """Wrap the parent's ``search_existing`` with French dupe flagging.

        Trackers that define their *own* ``search_existing`` (C411, V3X)
        take priority via MRO and call
        :meth:`_check_french_lang_dupes` explicitly.  This wrapper handles
        trackers that inherit ``search_existing`` from a parent class
        (e.g. G3MINI / TOS inheriting from UNIT3D).
        """
        dupes = await super().search_existing(meta, _)  # type: ignore[misc]
        return await self._check_french_lang_dupes(dupes, meta)
