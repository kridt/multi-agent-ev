from dataclasses import dataclass


@dataclass(frozen=True)
class League:
    name: str
    country: str
    optic_odds_id: str
    the_odds_api_key: str
    sportmonks_id: int
    active: bool = True


LEAGUES: dict[str, League] = {
    "epl": League(
        name="English Premier League",
        country="England",
        optic_odds_id="english-premier-league",
        the_odds_api_key="soccer_epl",
        sportmonks_id=8,
    ),
    "la_liga": League(
        name="La Liga",
        country="Spain",
        optic_odds_id="spanish-la-liga",
        the_odds_api_key="soccer_spain_la_liga",
        sportmonks_id=564,
    ),
    "serie_a": League(
        name="Serie A",
        country="Italy",
        optic_odds_id="italian-serie-a",
        the_odds_api_key="soccer_italy_serie_a",
        sportmonks_id=384,
    ),
    "bundesliga": League(
        name="Bundesliga",
        country="Germany",
        optic_odds_id="german-bundesliga",
        the_odds_api_key="soccer_germany_bundesliga",
        sportmonks_id=82,
    ),
    "ligue_1": League(
        name="Ligue 1",
        country="France",
        optic_odds_id="french-ligue-1",
        the_odds_api_key="soccer_france_ligue_one",
        sportmonks_id=301,
    ),
    "danish_superliga": League(
        name="Danish Superliga",
        country="Denmark",
        optic_odds_id="danish-superliga",
        the_odds_api_key="soccer_denmark_superliga",
        sportmonks_id=271,
    ),
    "allsvenskan": League(
        name="Allsvenskan",
        country="Sweden",
        optic_odds_id="swedish-allsvenskan",
        the_odds_api_key="soccer_sweden_allsvenskan",
        sportmonks_id=1572,
    ),
    "eliteserien": League(
        name="Eliteserien",
        country="Norway",
        optic_odds_id="norwegian-eliteserien",
        the_odds_api_key="soccer_norway_eliteserien",
        sportmonks_id=444,
    ),
}


def get_active_leagues() -> dict[str, League]:
    return {k: v for k, v in LEAGUES.items() if v.active}
