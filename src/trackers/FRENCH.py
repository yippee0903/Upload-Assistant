# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
"""
French tracker mixin — shared logic for all French-language trackers.

All French trackers (C411, G3MINI, V3X, …) inherit from this mixin. The
implementation is split by concern under ``src/trackers/french/`` so that
each piece maps onto one module of a future upbrr tracker:

  · languages   — audio/subtitle facts, VFF/VFQ/VF2/VOSTFR tags (pure)
  · naming      — release name conventions
  · rules       — release eligibility
  · dupes       — French language hierarchy on duplicate candidates
  · description — BBCode blocks from MediaInfo
  · nfo         — NFO discovery/generation, torrent re-creation
"""

from typing import Any

from src.trackers.french.description import FrenchDescriptionMixin
from src.trackers.french.dupes import FrenchDupeMixin
from src.trackers.french.languages import (
    _FRENCH_AUDIO_THRESHOLD,
    FRENCH_LANG_HIERARCHY,
    FRENCH_LANG_VALUES,
    LANG_FLAGS,
    LANG_MAP,
    LANG_NAMES_FR,
    FrenchLanguageMixin,
)
from src.trackers.french.naming import FrenchNamingMixin
from src.trackers.french.nfo import FrenchNfoMixin
from src.trackers.french.rules import FrenchRulesMixin

__all__ = [
    "_FRENCH_AUDIO_THRESHOLD",
    "FRENCH_LANG_HIERARCHY",
    "FRENCH_LANG_VALUES",
    "LANG_FLAGS",
    "LANG_MAP",
    "LANG_NAMES_FR",
    "FrenchTrackerMixin",
]

Meta = dict[str, Any]


class FrenchTrackerMixin(FrenchRulesMixin, FrenchLanguageMixin, FrenchNamingMixin, FrenchDupeMixin, FrenchDescriptionMixin, FrenchNfoMixin):
    """Mixin providing French-tracker naming and audio analysis.

    Mix this into any tracker class that targets a French tracker.
    Requires the host class to have a ``tmdb_manager`` attribute
    (instance of :class:`src.tmdb.TmdbManager`).
    """
