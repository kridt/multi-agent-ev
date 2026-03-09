"""Seed data for entity resolution — canonical team aliases across all leagues."""

from sqlalchemy.ext.asyncio import AsyncSession

from entity_resolution.alias_store import AliasStore

# ---------------------------------------------------------------------------
# Canonical team name → list of known aliases.
# The canonical name itself is NOT included in the alias list.
# At least 100 teams across 8 leagues.
# ---------------------------------------------------------------------------
TEAM_ALIASES: dict[str, list[str]] = {
    # -----------------------------------------------------------------------
    # EPL (20 teams)
    # -----------------------------------------------------------------------
    "Arsenal": ["Arsenal FC", "Arsenal Football Club", "The Gunners"],
    "Aston Villa": ["Aston Villa FC", "Villa"],
    "Bournemouth": ["AFC Bournemouth", "Bournemouth FC"],
    "Brentford": ["Brentford FC"],
    "Brighton": [
        "Brighton & Hove Albion",
        "Brighton and Hove Albion",
        "Brighton FC",
        "Brighton Hove Albion",
    ],
    "Chelsea": ["Chelsea FC", "Chelsea Football Club"],
    "Crystal Palace": ["Crystal Palace FC"],
    "Everton": ["Everton FC"],
    "Fulham": ["Fulham FC"],
    "Ipswich": ["Ipswich Town", "Ipswich Town FC"],
    "Leicester": ["Leicester City", "Leicester City FC"],
    "Liverpool": ["Liverpool FC"],
    "Manchester City": ["Man City", "Man. City", "Manchester City FC"],
    "Manchester United": [
        "Man United",
        "Man Utd",
        "Man. United",
        "Manchester United FC",
    ],
    "Newcastle": [
        "Newcastle United",
        "Newcastle Utd",
        "Newcastle United FC",
    ],
    "Nottingham Forest": [
        "Nott'm Forest",
        "Nottm Forest",
        "Nottingham Forest FC",
    ],
    "Southampton": ["Southampton FC"],
    "Tottenham": [
        "Tottenham Hotspur",
        "Spurs",
        "Tottenham Hotspur FC",
    ],
    "West Ham": [
        "West Ham United",
        "West Ham Utd",
        "West Ham United FC",
    ],
    "Wolverhampton": [
        "Wolverhampton Wanderers",
        "Wolves",
        "Wolverhampton FC",
    ],
    # -----------------------------------------------------------------------
    # La Liga (20 teams)
    # -----------------------------------------------------------------------
    "Barcelona": ["FC Barcelona", "Barca", "FC Barca"],
    "Real Madrid": ["Real Madrid CF"],
    "Atletico Madrid": [
        "Atlético Madrid",
        "Atlético de Madrid",
        "Atletico de Madrid",
        "Club Atletico de Madrid",
    ],
    "Real Sociedad": ["Real Sociedad de Fútbol"],
    "Real Betis": ["Real Betis Balompié", "Betis"],
    "Athletic Bilbao": ["Athletic Club", "Athletic Club Bilbao"],
    "Villarreal": ["Villarreal CF"],
    "Sevilla": ["Sevilla FC"],
    "Valencia": ["Valencia CF"],
    "Girona": ["Girona FC"],
    "Osasuna": ["CA Osasuna", "Club Atlético Osasuna"],
    "Celta Vigo": ["Celta de Vigo", "RC Celta", "RC Celta de Vigo"],
    "Mallorca": ["RCD Mallorca", "Real Mallorca"],
    "Getafe": ["Getafe CF"],
    "Rayo Vallecano": ["Rayo", "Rayo Vallecano de Madrid"],
    "Las Palmas": ["UD Las Palmas", "Union Deportiva Las Palmas"],
    "Alaves": ["Deportivo Alavés", "Deportivo Alaves", "CD Alavés"],
    "Cadiz": ["Cádiz CF", "Cadiz CF"],
    "Granada": ["Granada CF"],
    "Almeria": ["UD Almería", "UD Almeria", "Almería"],
    # -----------------------------------------------------------------------
    # Serie A (18 teams)
    # -----------------------------------------------------------------------
    "AC Milan": ["Milan", "AC Milan 1899"],
    "Inter Milan": [
        "Inter",
        "Internazionale",
        "FC Internazionale",
        "Inter Milano",
    ],
    "Juventus": ["Juventus FC", "Juve"],
    "Napoli": ["SSC Napoli", "S.S.C. Napoli"],
    "Roma": ["AS Roma", "A.S. Roma"],
    "Lazio": ["SS Lazio", "S.S. Lazio"],
    "Atalanta": ["Atalanta BC", "Atalanta Bergamo"],
    "Fiorentina": ["ACF Fiorentina", "AC Fiorentina"],
    "Bologna": ["Bologna FC", "Bologna FC 1909"],
    "Torino": ["Torino FC"],
    "Monza": ["AC Monza"],
    "Udinese": ["Udinese Calcio"],
    "Cagliari": ["Cagliari Calcio"],
    "Empoli": ["Empoli FC"],
    "Genoa": ["Genoa CFC"],
    "Sassuolo": ["US Sassuolo", "US Sassuolo Calcio"],
    "Lecce": ["US Lecce"],
    "Salernitana": ["US Salernitana", "US Salernitana 1919"],
    # -----------------------------------------------------------------------
    # Bundesliga (18 teams)
    # -----------------------------------------------------------------------
    "Bayern Munich": [
        "FC Bayern München",
        "Bayern München",
        "FC Bayern Munich",
        "Bayern",
    ],
    "Borussia Dortmund": [
        "BVB",
        "Dortmund",
        "Borussia Dortmund 09",
    ],
    "RB Leipzig": ["Leipzig", "RasenBallsport Leipzig"],
    "Bayer Leverkusen": [
        "Leverkusen",
        "Bayer 04 Leverkusen",
    ],
    "Eintracht Frankfurt": [
        "Frankfurt",
        "SGE",
        "Eintracht",
    ],
    "VfB Stuttgart": ["Stuttgart"],
    "VfL Wolfsburg": ["Wolfsburg"],
    "Borussia Monchengladbach": [
        "Borussia Mönchengladbach",
        "Gladbach",
        "Mönchengladbach",
        "BMG",
    ],
    "1. FC Köln": [
        "Köln",
        "FC Koln",
        "1. FC Koeln",
        "Cologne",
    ],
    "Union Berlin": ["1. FC Union Berlin", "FC Union Berlin"],
    "SC Freiburg": ["Freiburg"],
    "Werder Bremen": ["Bremen", "SV Werder Bremen"],
    "Hoffenheim": ["TSG Hoffenheim", "TSG 1899 Hoffenheim"],
    "Mainz": ["1. FSV Mainz 05", "Mainz 05", "FSV Mainz"],
    "Augsburg": ["FC Augsburg"],
    "Heidenheim": ["1. FC Heidenheim", "FC Heidenheim"],
    "Darmstadt": ["SV Darmstadt 98", "Darmstadt 98"],
    "FC Koln": ["1. FC Koln"],
    # -----------------------------------------------------------------------
    # Ligue 1 (15 teams)
    # -----------------------------------------------------------------------
    "PSG": [
        "Paris Saint-Germain",
        "Paris Saint Germain",
        "Paris SG",
    ],
    "Marseille": [
        "Olympique de Marseille",
        "Olympique Marseille",
        "OM",
    ],
    "Lyon": [
        "Olympique Lyonnais",
        "Olympique Lyon",
        "OL",
    ],
    "Monaco": ["AS Monaco", "AS Monaco FC"],
    "Lille": ["Lille OSC", "LOSC", "LOSC Lille"],
    "Nice": ["OGC Nice", "OGC Nice Côte d'Azur"],
    "Lens": ["RC Lens"],
    "Rennes": ["Stade Rennais", "Stade Rennais FC"],
    "Strasbourg": ["RC Strasbourg", "RC Strasbourg Alsace"],
    "Nantes": ["FC Nantes"],
    "Toulouse": ["Toulouse FC"],
    "Montpellier": ["Montpellier HSC"],
    "Brest": ["Stade Brestois", "Stade Brestois 29"],
    "Reims": ["Stade de Reims"],
    "Le Havre": ["Le Havre AC"],
    # -----------------------------------------------------------------------
    # Danish Superliga (12 teams)
    # -----------------------------------------------------------------------
    "FC Copenhagen": ["København", "FC København", "Copenhagen"],
    "FC Midtjylland": ["Midtjylland", "FC Midtjylland Herning"],
    "Brondby": ["Brøndby IF", "Brøndby", "Brondby IF"],
    "FC Nordsjaelland": [
        "Nordsjælland",
        "FC Nordsjælland",
        "Nordsjaelland",
    ],
    "AGF": ["Aarhus GF", "AGF Aarhus", "Aarhus"],
    "Aalborg": ["AaB", "Aalborg BK"],
    "Silkeborg": ["Silkeborg IF"],
    "Viborg": ["Viborg FF"],
    "Randers": ["Randers FC"],
    "Lyngby": ["Lyngby BK", "Lyngby Boldklub"],
    "Vejle": ["Vejle BK", "Vejle Boldklub"],
    "Hvidovre": ["Hvidovre IF"],
    # -----------------------------------------------------------------------
    # Allsvenskan (16 teams)
    # -----------------------------------------------------------------------
    "Malmo FF": ["Malmö FF", "Malmö", "Malmo"],
    "AIK": ["AIK Stockholm", "AIK Fotboll"],
    "Djurgarden": ["Djurgårdens IF", "Djurgården", "DIF"],
    "Hammarby": ["Hammarby IF", "Hammarby Fotboll"],
    "IFK Goteborg": ["IFK Göteborg", "Göteborg"],
    "IFK Norrkoping": ["IFK Norrköping", "Norrköping"],
    "Hacken": ["BK Häcken", "Häcken"],
    "Elfsborg": ["IF Elfsborg"],
    "Kalmar": ["Kalmar FF"],
    "Mjallby": ["Mjällby AIF", "Mjällby"],
    "Sirius": ["IK Sirius", "IK Sirius FK"],
    "Varberg": ["Varbergs BoIS", "Varbergs"],
    "Halmstad": ["Halmstads BK", "Halmstad BK"],
    "Varnamo": ["IFK Värnamo", "Värnamo"],
    "Degerfors": ["Degerfors IF"],
    "GAIS": ["GAIS Göteborg"],
    # -----------------------------------------------------------------------
    # Eliteserien (16 teams)
    # -----------------------------------------------------------------------
    "Bodo/Glimt": [
        "FK Bodø/Glimt",
        "Bodø/Glimt",
        "Bodo Glimt",
    ],
    "Molde": ["Molde FK"],
    "Rosenborg": ["Rosenborg BK", "RBK"],
    "Viking": ["Viking FK"],
    "Brann": ["SK Brann"],
    "Lillestrom": ["Lillestrøm SK", "Lillestrøm", "LSK"],
    "Valerenga": ["Vålerenga IF", "Vålerenga", "VIF"],
    "Stromsgodset": ["Strømsgodset IF", "Strømsgodset"],
    "Tromso": ["Tromsø IL", "Tromsø"],
    "Sarpsborg": ["Sarpsborg 08", "Sarpsborg 08 FF"],
    "Odd": ["Odds BK", "Odd Grenland"],
    "Haugesund": ["FK Haugesund"],
    "Stabaek": ["Stabæk IF", "Stabæk"],
    "Sandefjord": ["Sandefjord Fotball"],
    "HamKam": ["Hamarkameratene", "Ham-Kam"],
    "Kristiansund": ["Kristiansund BK"],
}


async def seed_aliases(session: AsyncSession) -> int:
    """Insert all aliases from ``TEAM_ALIASES`` into the aliases table.

    Each canonical name is used as both the ``canonical_id`` and as a
    lookup key. The canonical name itself is also inserted as an alias
    (identity mapping) to simplify lookups.

    Returns:
        Number of alias rows inserted.
    """
    store = AliasStore()
    count = 0

    for canonical_name, aliases in TEAM_ALIASES.items():
        # Insert the canonical name as a self-alias
        await store.add_alias(
            session,
            entity_type="team",
            canonical_id=canonical_name,
            alias_name=canonical_name,
            source="seed",
            confidence=1.0,
        )
        count += 1

        # Insert every alias
        for alias in aliases:
            await store.add_alias(
                session,
                entity_type="team",
                canonical_id=canonical_name,
                alias_name=alias,
                source="seed",
                confidence=1.0,
            )
            count += 1

    return count
