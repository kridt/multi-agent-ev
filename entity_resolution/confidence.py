"""Confidence scoring for entity resolution methods."""

from config.constants import (
    ENTITY_CONFIDENCE_ALIAS,
    ENTITY_CONFIDENCE_CONTEXTUAL_BOOST,
    ENTITY_CONFIDENCE_EXACT,
    ENTITY_CONFIDENCE_FUZZY_MIN,
    ENTITY_CONFIDENCE_NORMALIZED,
    FUZZY_MATCH_THRESHOLD,
)


def calculate_confidence(method: str, score: float | None = None) -> float:
    """Calculate confidence based on resolution method.

    Args:
        method: Resolution method — one of "exact", "alias", "normalized",
                "fuzzy", "contextual".
        score: Raw fuzzy match score (0-100). Only used for "fuzzy" and
               "contextual" methods.

    Returns:
        Confidence value between 0.0 and 1.0.
    """
    if method == "exact":
        return ENTITY_CONFIDENCE_EXACT

    if method == "alias":
        return ENTITY_CONFIDENCE_ALIAS

    if method == "normalized":
        return ENTITY_CONFIDENCE_NORMALIZED

    if method == "fuzzy":
        if score is None:
            return ENTITY_CONFIDENCE_FUZZY_MIN
        # Scale score from [threshold..100] to [0.70..0.89]
        scaled = ENTITY_CONFIDENCE_FUZZY_MIN + (
            (score - FUZZY_MATCH_THRESHOLD) / (100 - FUZZY_MATCH_THRESHOLD) * 0.19
        )
        return round(min(max(scaled, ENTITY_CONFIDENCE_FUZZY_MIN), 0.89), 4)

    if method == "contextual":
        base = calculate_confidence("fuzzy", score)
        return round(min(base + ENTITY_CONFIDENCE_CONTEXTUAL_BOOST, 0.99), 4)

    return 0.0
