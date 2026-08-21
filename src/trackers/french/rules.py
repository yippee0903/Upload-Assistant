"""Release eligibility for French trackers (the rule set). Maps to upbrr rules.go / validation.go.

Every French tracker declares its rules as data (``RULES``) and reports a
failed rule through :meth:`FrenchRulesMixin._rule_failed`, which applies the
declared disposition:

* ``strict``   — always blocks the tracker (upbrr: non-overridable)
* ``waivable`` — the user may approve; ``--unattended`` excludes the tracker
* ``advisory`` — recorded as a warning, never blocks
"""

from dataclasses import dataclass
from typing import Any, Literal

from src.console import console
from src.trackers.COMMON import ask_to_continue
from src.trackers.french.languages import FRENCH_LANG_VALUES

Meta = dict[str, Any]

Disposition = Literal["strict", "waivable", "advisory"]
Evidence = Literal["mediainfo", "name", "filesystem", "metadata"]


@dataclass(frozen=True)
class Rule:
    key: str  # stable identifier, used in code and in the future upbrr RuleSet
    disposition: Disposition
    summary: str  # what the tracker requires, one line
    evidence: Evidence = "mediainfo"  # where the fact that proves it comes from
    default_answer: bool = False  # waivable only: the prompt's default


FRENCH_LANGUAGE_RULE = Rule("french_language", "strict", "French audio, or original audio with French subtitles")


class FrenchRulesMixin:
    """Release eligibility for French trackers (the rule set)."""

    RULES: tuple[Rule, ...] = (FRENCH_LANGUAGE_RULE,)

    @classmethod
    def rule(cls, key: str) -> Rule:
        for rule in cls.RULES:
            if rule.key == key:
                return rule
        raise KeyError(f"{cls.__name__} declares no rule {key!r}")

    def _rule_failed(self, meta: Meta, key: str, message: str, details: tuple[str, ...] = ()) -> bool:
        """Report a failed rule; returns whether the upload may still proceed on this tracker."""
        rule = self.rule(key)
        tracker = getattr(self, "tracker", "")
        if rule.disposition == "advisory":
            console.print(f"[bold yellow]{tracker}: {message}[/bold yellow]")
            for line in details:
                console.print(f"[yellow]  → {line}[/yellow]")
            return True
        if rule.disposition == "waivable":
            for line in details:
                console.print(f"[yellow]  → {line}[/yellow]")
            return ask_to_continue(meta, f"{tracker}: {message}", default=rule.default_answer)
        console.print(f"[bold red]{tracker}: {message}[/bold red]")
        for line in details:
            console.print(f"[bold yellow]  → {line}[/bold yellow]")
        return False

    async def _check_french_language(self, meta: Meta, **kwargs: Any) -> bool:
        """The shared French language rule; kwargs tune check_language_requirements per tracker."""
        options: dict[str, Any] = {"languages_to_check": list(FRENCH_LANG_VALUES), "check_audio": True, "check_subtitle": True, "require_both": False}
        options.update(kwargs)
        if not await self.common.check_language_requirements(meta, self.tracker, **options):
            return self._rule_failed(meta, "french_language", f"Language requirements not met ({self.rule('french_language').summary}).")
        # The shared check accepts French subtitles on their own; here they
        # only count alongside an original-language audio track (VOSTFR).
        # A dub in a third language with French subtitles is neither VF nor
        # VOSTFR. Unknown original language or audio tracks are not judged.
        if self._has_audio_in(meta, options["languages_to_check"]) or self._has_original_audio(meta):
            return True
        return self._rule_failed(
            meta,
            "french_language",
            f"Language requirements not met ({self.rule('french_language').summary}).",
            ("French subtitles only count with an original-language audio track.",),
        )

    def _has_audio_in(self, meta: Meta, languages: list[str]) -> bool:
        wanted = {lang.lower() for lang in languages}
        return any(lang.lower() in wanted for lang in self.common._coerce_language_values(meta.get("audio_languages", [])))

    def _has_original_audio(self, meta: Meta) -> bool:
        """True when an audio track is in the original language — or when that cannot be judged."""
        original = meta.get("original_language") or ""
        if isinstance(original, list):
            original = original[0] if original and isinstance(original[0], str) else ""
        if not original.strip() or meta.get("audio_languages") is None:
            return True
        candidates = self.common._expand_language_candidates(original.strip(), self.common._build_language_alias_lookup())
        audio = {self.common._normalize_language_token(lang) for lang in self.common._coerce_language_values(meta.get("audio_languages", []))}
        return bool(candidates & audio)

    async def get_additional_checks(self, meta: Meta) -> bool:
        """Default French language check for all French trackers.

        Subclasses that inherit UNIT3D get this called automatically from
        ``UNIT3D.search_existing()``.  Standalone French trackers (C411,
        V3X) must call it explicitly from their own ``search_existing()``.
        Subclasses add rules by extending ``RULES`` and overriding this.
        """
        return await self._check_french_language(meta)
