"""Release eligibility for French trackers (the rule set). Maps to upbrr rules.go / validation.go."""

from typing import Any

from src.console import console
from src.trackers.french.languages import FRENCH_LANG_VALUES

Meta = dict[str, Any]


class FrenchRulesMixin:
    """Release eligibility for French trackers (the rule set). Maps to upbrr rules.go / validation.go."""

    async def get_additional_checks(self, meta: dict[str, Any]) -> bool:
        """Default French language check for all French trackers.

        Subclasses that inherit UNIT3D get this called automatically from
        ``UNIT3D.search_existing()``.  Standalone French trackers (C411,
        V3X) must call it explicitly from their own
        ``search_existing()``.

        Subclasses may override to add extra rules (banned types, etc.).
        """
        french_languages = list(FRENCH_LANG_VALUES)
        if not await self.common.check_language_requirements(
            meta,
            self.tracker,
            languages_to_check=french_languages,
            check_audio=True,
            check_subtitle=True,
            require_both=False,
        ):
            if not meta.get("unattended", False):
                console.print(f"[bold red]Language requirements not met for {self.tracker}.[/bold red]")
            return False
        return True
