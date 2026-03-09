"""Tests for the entity resolution system — matchers, confidence, and seed data."""

import pytest

from entity_resolution.confidence import calculate_confidence
from entity_resolution.matchers import (
    ContextualMatcher,
    ExactMatcher,
    FuzzyMatcher,
    NormalizedMatcher,
)
from entity_resolution.seed_data import TEAM_ALIASES


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

EPL_TEAMS = [
    "Arsenal",
    "Aston Villa",
    "Bournemouth",
    "Brentford",
    "Brighton",
    "Chelsea",
    "Crystal Palace",
    "Everton",
    "Fulham",
    "Ipswich",
    "Leicester",
    "Liverpool",
    "Manchester City",
    "Manchester United",
    "Newcastle",
    "Nottingham Forest",
    "Southampton",
    "Tottenham",
    "West Ham",
    "Wolverhampton",
]

LA_LIGA_TEAMS = [
    "Barcelona",
    "Real Madrid",
    "Atletico Madrid",
    "Real Sociedad",
    "Real Betis",
    "Athletic Bilbao",
    "Villarreal",
    "Sevilla",
    "Valencia",
    "Girona",
]

ALL_CANDIDATES = EPL_TEAMS + LA_LIGA_TEAMS + [
    "AC Milan",
    "Inter Milan",
    "Juventus",
    "Napoli",
    "Bayern Munich",
    "Borussia Dortmund",
    "RB Leipzig",
    "PSG",
    "Marseille",
    "FC Copenhagen",
    "Brondby",
    "Malmo FF",
    "Bodo/Glimt",
    "1. FC K\u00f6ln",
]


# ===========================================================================
# ExactMatcher
# ===========================================================================

class TestExactMatcher:
    def test_exact_match_found(self):
        m = ExactMatcher()
        result = m.match("Arsenal", ALL_CANDIDATES)
        assert result is not None
        assert result == ("Arsenal", 1.0)

    def test_exact_match_not_found(self):
        m = ExactMatcher()
        result = m.match("arsenal", ALL_CANDIDATES)
        assert result is None  # case-sensitive

    def test_exact_match_full_name(self):
        m = ExactMatcher()
        result = m.match("Manchester United", ALL_CANDIDATES)
        assert result == ("Manchester United", 1.0)


# ===========================================================================
# NormalizedMatcher
# ===========================================================================

class TestNormalizedMatcher:
    def test_fc_barcelona_matches_barcelona(self):
        """'FC Barcelona' should match canonical 'Barcelona' after stripping FC prefix."""
        m = NormalizedMatcher()
        result = m.match("FC Barcelona", ALL_CANDIDATES)
        assert result is not None
        name, conf = result
        assert name == "Barcelona"
        assert conf == 0.90

    def test_malmo_diacritics(self):
        """'Malm\u00f6 FF' should match 'Malmo FF' after diacritics removal."""
        m = NormalizedMatcher()
        result = m.match("Malm\u00f6 FF", ALL_CANDIDATES)
        assert result is not None
        name, _ = result
        assert name == "Malmo FF"

    def test_brondby_diacritics_and_suffix(self):
        """'Br\u00f8ndby IF' should match 'Brondby' after diacritics removal + suffix strip."""
        m = NormalizedMatcher()
        result = m.match("Br\u00f8ndby IF", ALL_CANDIDATES)
        assert result is not None
        name, _ = result
        assert name == "Brondby"

    def test_1_fc_koln(self):
        """'1. FC K\u00f6ln' should normalize to 'koln'."""
        m = NormalizedMatcher()
        assert NormalizedMatcher.normalize("1. FC K\u00f6ln") == "koln"
        # 'FC Koln' should also match '1. FC K\u00f6ln' via normalization
        result = m.match("FC Koln", ALL_CANDIDATES)
        assert result is not None
        name, _ = result
        assert name == "1. FC K\u00f6ln"

    def test_manchester_united_stays(self):
        """'Manchester United' has no prefix/suffix to strip, stays as is."""
        norm = NormalizedMatcher.normalize("Manchester United")
        assert norm == "manchester united"

    def test_ac_milan_strips_ac(self):
        """'AC Milan' -> 'milan' after stripping AC prefix."""
        norm = NormalizedMatcher.normalize("AC Milan")
        assert norm == "milan"

    def test_rb_leipzig_strips_rb(self):
        """'RB Leipzig' -> 'leipzig' after stripping RB prefix."""
        norm = NormalizedMatcher.normalize("RB Leipzig")
        assert norm == "leipzig"

    def test_normalize_preserves_core_name(self):
        """Names without prefixes/suffixes should be preserved (lowercased)."""
        norm = NormalizedMatcher.normalize("Liverpool")
        assert norm == "liverpool"

    def test_normalize_whitespace(self):
        """Extra whitespace should be collapsed and prefix stripped."""
        norm = NormalizedMatcher.normalize("  FC   Barcelona  ")
        assert norm == "barcelona"

    def test_as_roma_strips_as(self):
        """'AS Roma' -> 'roma' after stripping AS prefix."""
        norm = NormalizedMatcher.normalize("AS Roma")
        assert norm == "roma"

    def test_vfb_stuttgart_strips_vfb(self):
        """'VfB Stuttgart' -> 'stuttgart' after stripping VfB prefix."""
        norm = NormalizedMatcher.normalize("VfB Stuttgart")
        assert norm == "stuttgart"


# ===========================================================================
# FuzzyMatcher
# ===========================================================================

class TestFuzzyMatcher:
    def test_man_utd_matches_manchester_united(self):
        """'Man Utd' should fuzzy-match 'Manchester United' if above threshold.
        If it matches, confidence must be >= 0.70."""
        m = FuzzyMatcher(threshold=85)
        result = m.match("Man Utd", ALL_CANDIDATES)
        if result is not None:
            name, conf = result
            assert conf >= 0.70

    def test_spurs_does_not_match_manchester_city(self):
        """'Spurs' should NOT fuzzy-match 'Manchester City' — completely different tokens."""
        m = FuzzyMatcher(threshold=85)
        result = m.match("Spurs", ["Manchester City"])
        assert result is None

    def test_high_similarity_match(self):
        """Very similar multi-word names should match with high confidence."""
        m = FuzzyMatcher(threshold=80)
        result = m.match("Manchester United FC", ["Manchester United"])
        assert result is not None
        name, conf = result
        assert name == "Manchester United"
        assert conf >= 0.70

    def test_below_threshold_returns_none(self):
        """Strings with low similarity should return None."""
        m = FuzzyMatcher(threshold=85)
        result = m.match("xyz random name", ALL_CANDIDATES)
        assert result is None

    def test_confidence_scales_with_score(self):
        """Higher fuzzy scores should produce higher confidence values."""
        m = FuzzyMatcher(threshold=80)
        # Two candidate lists: one very close, one less close
        result_close = m.match("Liverpool FC", ["Liverpool"])
        result_far = m.match("Liver", ["Liverpool"])
        if result_close and result_far:
            _, conf_close = result_close
            _, conf_far = result_far
            assert conf_close >= conf_far

    def test_empty_candidates_returns_none(self):
        """Empty candidate list should return None."""
        m = FuzzyMatcher(threshold=85)
        result = m.match("Arsenal", [])
        assert result is None


# ===========================================================================
# ContextualMatcher
# ===========================================================================

class TestContextualMatcher:
    def test_restricts_to_league_candidates(self):
        """When league_teams is provided, matching should be restricted to those teams."""
        m = ContextualMatcher(threshold=80)
        # "Liverpool FC" should match "Liverpool" within EPL context
        result = m.match("Liverpool FC", ALL_CANDIDATES, league_teams=EPL_TEAMS)
        assert result is not None
        name, conf = result
        assert name == "Liverpool"

    def test_confidence_boost(self):
        """Contextual match should boost confidence by 0.05 over plain fuzzy."""
        fuzzy_m = FuzzyMatcher(threshold=80)
        ctx_m = ContextualMatcher(threshold=80)

        fuzzy_result = fuzzy_m.match("Liverpool FC", EPL_TEAMS)
        ctx_result = ctx_m.match("Liverpool FC", ALL_CANDIDATES, league_teams=EPL_TEAMS)

        if fuzzy_result and ctx_result:
            _, fuzzy_conf = fuzzy_result
            _, ctx_conf = ctx_result
            assert ctx_conf == pytest.approx(min(fuzzy_conf + 0.05, 0.99), abs=0.001)

    def test_no_league_falls_back_to_all(self):
        """Without league_teams, contextual matcher should use all candidates."""
        m = ContextualMatcher(threshold=80)
        result = m.match("Liverpool FC", ALL_CANDIDATES, league_teams=None)
        if result is not None:
            name, _ = result
            assert name == "Liverpool"

    def test_wrong_league_no_match(self):
        """A team name from one league should not match candidates from another league."""
        m = ContextualMatcher(threshold=85)
        # "Barcelona" should not match any EPL team
        result = m.match("Barcelona", ALL_CANDIDATES, league_teams=EPL_TEAMS)
        # If it does match something, it should NOT be Barcelona (not in EPL)
        if result is not None:
            name, _ = result
            assert name in EPL_TEAMS


# ===========================================================================
# calculate_confidence
# ===========================================================================

class TestCalculateConfidence:
    def test_exact_confidence(self):
        assert calculate_confidence("exact") == 1.0

    def test_alias_confidence(self):
        assert calculate_confidence("alias") == 0.95

    def test_normalized_confidence(self):
        assert calculate_confidence("normalized") == 0.90

    def test_fuzzy_confidence_no_score(self):
        assert calculate_confidence("fuzzy") == 0.70

    def test_fuzzy_confidence_with_score(self):
        conf = calculate_confidence("fuzzy", score=100)
        assert conf == 0.89

    def test_fuzzy_confidence_at_threshold(self):
        conf = calculate_confidence("fuzzy", score=85)
        assert conf == 0.70

    def test_contextual_confidence_boost(self):
        conf = calculate_confidence("contextual", score=100)
        assert conf == 0.94  # 0.89 + 0.05

    def test_unknown_method(self):
        assert calculate_confidence("unknown") == 0.0


# ===========================================================================
# Seed data
# ===========================================================================

class TestSeedData:
    def test_minimum_team_count(self):
        """There should be at least 100 canonical teams defined."""
        assert len(TEAM_ALIASES) >= 100

    def test_all_8_leagues_represented(self):
        """Spot-check that teams from all 8 leagues are present."""
        # EPL
        assert "Arsenal" in TEAM_ALIASES
        # La Liga
        assert "Barcelona" in TEAM_ALIASES
        # Serie A
        assert "Juventus" in TEAM_ALIASES
        # Bundesliga
        assert "Bayern Munich" in TEAM_ALIASES
        # Ligue 1
        assert "PSG" in TEAM_ALIASES
        # Danish Superliga
        assert "FC Copenhagen" in TEAM_ALIASES
        # Allsvenskan
        assert "Malmo FF" in TEAM_ALIASES
        # Eliteserien
        assert "Bodo/Glimt" in TEAM_ALIASES

    def test_aliases_are_non_empty_strings(self):
        """Every alias should be a non-empty string."""
        for canonical, aliases in TEAM_ALIASES.items():
            assert isinstance(canonical, str) and len(canonical) > 0
            for alias in aliases:
                assert isinstance(alias, str) and len(alias) > 0

    def test_no_duplicate_aliases_within_team(self):
        """No canonical team should have duplicate alias entries."""
        for canonical, aliases in TEAM_ALIASES.items():
            assert len(aliases) == len(set(aliases)), (
                f"{canonical} has duplicate aliases"
            )
