"""Entity resolution system — resolve team/player names across data sources."""

from entity_resolution.alias_store import AliasStore
from entity_resolution.confidence import calculate_confidence
from entity_resolution.cross_source import CrossSourceLinker
from entity_resolution.matchers import (
    ContextualMatcher,
    ExactMatcher,
    FuzzyMatcher,
    NormalizedMatcher,
)
from entity_resolution.resolver import EntityResolver

__all__ = [
    "AliasStore",
    "calculate_confidence",
    "ContextualMatcher",
    "CrossSourceLinker",
    "EntityResolver",
    "ExactMatcher",
    "FuzzyMatcher",
    "NormalizedMatcher",
]
