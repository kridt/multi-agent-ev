from dataclasses import dataclass


@dataclass(frozen=True)
class Bookmaker:
    name: str
    display_name: str
    optic_odds_key: str
    the_odds_api_key: str | None
    region: str
    is_sharp: bool = False
    active: bool = True


BOOKMAKERS: dict[str, Bookmaker] = {
    "bet365_dk": Bookmaker(
        name="bet365_dk",
        display_name="Bet365 DK",
        optic_odds_key="bet365",
        the_odds_api_key="bet365",
        region="eu",
    ),
    "unibet_dk": Bookmaker(
        name="unibet_dk",
        display_name="Unibet DK",
        optic_odds_key="unibet",
        the_odds_api_key="unibet_eu",
        region="eu",
    ),
    "danske_spil": Bookmaker(
        name="danske_spil",
        display_name="Danske Spil",
        optic_odds_key="danske_spil",
        the_odds_api_key=None,  # Not available on The Odds API
        region="dk",
    ),
    "pinnacle": Bookmaker(
        name="pinnacle",
        display_name="Pinnacle",
        optic_odds_key="pinnacle",
        the_odds_api_key="pinnacle",
        region="eu",
        is_sharp=True,  # Sharp benchmark
    ),
}


TARGET_BOOKMAKERS = {k: v for k, v in BOOKMAKERS.items() if not v.is_sharp and v.active}
SHARP_BOOKMAKERS = {k: v for k, v in BOOKMAKERS.items() if v.is_sharp}


def get_all_bookmaker_keys_optic() -> list[str]:
    return [b.optic_odds_key for b in BOOKMAKERS.values() if b.active]


def get_all_bookmaker_keys_odds_api() -> list[str]:
    return [b.the_odds_api_key for b in BOOKMAKERS.values() if b.the_odds_api_key and b.active]
