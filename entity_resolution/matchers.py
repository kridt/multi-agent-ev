"""Matchers for entity resolution — exact, normalized, fuzzy, and contextual."""

import re
import unicodedata

from rapidfuzz import fuzz

from config.constants import FUZZY_MATCH_THRESHOLD


class ExactMatcher:
    """Exact string match against a list of candidate names."""

    def match(self, input_name: str, candidates: list[str]) -> tuple[str, float] | None:
        """Return (matched_name, confidence=1.0) if exact match found."""
        for candidate in candidates:
            if input_name == candidate:
                return (candidate, 1.0)
        return None


class NormalizedMatcher:
    """Match after normalizing names — strips prefixes/suffixes, diacritics, etc.

    Handles real cases like:
    - "FC Barcelona" -> "barcelona"
    - "Malmö FF" -> "malmo ff" (diacritics removed)
    - "Brøndby IF" -> "brondby" (diacritics + suffix stripped)
    - "1. FC Köln" -> "koln"
    - "Manchester United" stays "manchester united"
    - "AC Milan" -> "milan"
    - "RB Leipzig" -> "leipzig"
    """

    # Common prefixes that appear before the core team name.
    # Order matters — longer/more-specific patterns first.
    _PREFIXES = re.compile(
        r"^(?:1\.\s*)?"  # Optional leading "1. "
        r"(?:"
        r"Olympique de|Olympique|"  # French club prefixes
        r"S\.S\.C\.\s*|A\.S\.\s*|S\.S\.\s*|"  # Dotted abbreviations
        r"SpVgg|"  # 5-char
        r"BSC|TSG|OGC|ACF|SSC|GIF|VfB|VfL|"  # 3-char
        r"FC|FK|IF|SC|AC|CF|AS|SS|US|RB|BK|SK|SV"  # 2-char
        r")\s+",
        re.IGNORECASE,
    )

    # Club-type suffixes only — short identifiers, NOT descriptive name parts
    # like "United", "City", "Town", etc.
    _SUFFIXES = re.compile(
        r"\s+(?:FC|FK|IF|SC|AC|CF|BK|SK|IL|FF)$",
        re.IGNORECASE,
    )

    # Characters that don't decompose under NFD but should map to ASCII.
    # Mainly Scandinavian/special Latin characters.
    _SPECIAL_CHAR_MAP: dict[str, str] = {
        "\u00f8": "o",  # ø → o
        "\u00d8": "O",  # Ø → O
        "\u00e6": "ae",  # æ → ae
        "\u00c6": "AE",  # Æ → AE
        "\u0111": "d",  # đ → d
        "\u0110": "D",  # Đ → D
        "\u0142": "l",  # ł → l
        "\u0141": "L",  # Ł → L
        "\u00df": "ss",  # ß → ss
    }

    @classmethod
    def _remove_diacritics(cls, text: str) -> str:
        """Remove diacritics/accents from characters.

        Uses NFD decomposition to strip combining marks, plus explicit
        mappings for characters like ø, æ, đ that don't decompose.
        """
        # First, replace characters that don't decompose under NFD
        for char, replacement in cls._SPECIAL_CHAR_MAP.items():
            text = text.replace(char, replacement)
        # Then, NFD decompose and strip combining marks
        nfkd = unicodedata.normalize("NFKD", text)
        return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")

    @classmethod
    def normalize(cls, name: str) -> str:
        """Normalize a team/entity name for comparison.

        Steps:
        1. Strip leading/trailing whitespace and collapse internal whitespace
        2. Remove diacritics (NFD decompose, strip combining marks)
        3. Strip common prefixes: FC, FK, IF, SC, AC, CF, AS, SS, US, BSC, TSG, RB, VfB, VfL, etc.
        4. Strip club-type suffixes: FC, FK, IF, FF, BK, SK, IL, etc.
        5. Lowercase and strip whitespace
        """
        # Pre-clean whitespace so prefix regex anchors work
        result = re.sub(r"\s+", " ", name).strip()
        # Remove diacritics
        result = cls._remove_diacritics(result)
        # Remove prefixes (may need multiple passes for "1. FC ...")
        result = cls._PREFIXES.sub("", result)
        # Remove suffixes
        result = cls._SUFFIXES.sub("", result)
        # Final lowercase + strip
        result = result.strip().lower()
        return result

    def match(self, input_name: str, candidates: list[str]) -> tuple[str, float] | None:
        """Return (matched_name, confidence=0.90) if normalized match found."""
        normalized_input = self.normalize(input_name)
        for candidate in candidates:
            if self.normalize(candidate) == normalized_input:
                return (candidate, 0.90)
        return None


class FuzzyMatcher:
    """Fuzzy matching using rapidfuzz token_sort_ratio."""

    def __init__(self, threshold: int = FUZZY_MATCH_THRESHOLD):
        self.threshold = threshold

    def match(self, input_name: str, candidates: list[str]) -> tuple[str, float] | None:
        """Return (best_match, confidence) using rapidfuzz token_sort_ratio.

        Confidence is the score/100 scaled between 0.70 and 0.89.
        Only returns a match if the score is above the threshold.
        """
        best_match: str | None = None
        best_score: float = 0.0

        for candidate in candidates:
            score = fuzz.token_sort_ratio(input_name, candidate)
            if score > best_score:
                best_score = score
                best_match = candidate

        if best_match is not None and best_score >= self.threshold:
            # Scale score from [threshold..100] to [0.70..0.89]
            confidence = 0.70 + (best_score - self.threshold) / (100 - self.threshold) * 0.19
            return (best_match, round(confidence, 4))
        return None


class ContextualMatcher:
    """Fuzzy matching restricted to teams within the same league, with a confidence boost."""

    def __init__(self, threshold: int = FUZZY_MATCH_THRESHOLD):
        self.fuzzy = FuzzyMatcher(threshold=threshold)

    def match(
        self,
        input_name: str,
        candidates: list[str],
        league_teams: list[str] | None = None,
    ) -> tuple[str, float] | None:
        """Restrict fuzzy matching to teams in the same league. Boost confidence by 0.05."""
        search_candidates = league_teams if league_teams else candidates
        result = self.fuzzy.match(input_name, search_candidates)
        if result is not None:
            matched_name, confidence = result
            boosted = min(confidence + 0.05, 0.99)
            return (matched_name, round(boosted, 4))
        return None
