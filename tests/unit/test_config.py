"""Tests for configuration modules."""

from config.bookmakers import BOOKMAKERS, TARGET_BOOKMAKERS, SHARP_BOOKMAKERS
from config.constants import ALL_MARKETS, MARKETS_TIER1, MARKETS_TIER2
from config.leagues import LEAGUES, get_active_leagues
from config.settings import Settings


def test_settings_defaults():
    s = Settings()
    assert s.min_ev_threshold == 0.03
    assert s.kelly_fraction == 0.25
    assert s.max_stake_pct == 0.03
    assert s.min_odds == 1.50
    assert s.max_odds == 4.00


def test_all_leagues_defined():
    assert len(LEAGUES) == 8
    expected = {"epl", "la_liga", "serie_a", "bundesliga", "ligue_1",
                "danish_superliga", "allsvenskan", "eliteserien"}
    assert set(LEAGUES.keys()) == expected


def test_leagues_have_api_ids():
    for key, league in LEAGUES.items():
        assert league.optic_odds_id, f"{key} missing optic_odds_id"
        assert league.the_odds_api_key, f"{key} missing the_odds_api_key"
        assert league.sportmonks_id > 0, f"{key} missing sportmonks_id"


def test_active_leagues():
    active = get_active_leagues()
    assert len(active) == 8


def test_bookmakers_defined():
    assert "bet365_dk" in BOOKMAKERS
    assert "unibet_dk" in BOOKMAKERS
    assert "danske_spil" in BOOKMAKERS
    assert "pinnacle" in BOOKMAKERS


def test_target_bookmakers_exclude_sharp():
    assert "pinnacle" not in TARGET_BOOKMAKERS
    assert len(TARGET_BOOKMAKERS) == 3


def test_sharp_bookmakers():
    assert "pinnacle" in SHARP_BOOKMAKERS
    assert len(SHARP_BOOKMAKERS) == 1


def test_danske_spil_no_odds_api_key():
    assert BOOKMAKERS["danske_spil"].the_odds_api_key is None


def test_markets_priority_order():
    # Tier 1 (team stat markets) comes first in ALL_MARKETS, then Tier 2 (player props).
    # 1X2 and Asian Handicap (previously Tier 3) have been removed entirely.
    assert ALL_MARKETS[:len(MARKETS_TIER1)] == MARKETS_TIER1
    assert ALL_MARKETS[len(MARKETS_TIER1):] == MARKETS_TIER2
    assert len(ALL_MARKETS) == len(MARKETS_TIER1) + len(MARKETS_TIER2)
