# AI Soccer EV Betting Platform -- Comprehensive Implementation Plan

## Table of Contents
1. Project Structure
2. Phase-by-Phase Breakdown
3. Database Schema
4. API Integration Plan
5. Architecture Decisions
6. Data Flow Diagram
7. Risk and Edge Cases
8. Testing Strategy

---

## 1. Project Structure

```
C:\Users\chrni\Desktop\multi-agent-ev\
│
├── pyproject.toml                       # Project metadata, dependencies, scripts
├── README.md                            # Project overview, setup instructions
├── .env.example                         # Template for API keys and config
├── .env                                 # (gitignored) Actual secrets
├── alembic.ini                          # DB migration config
├── Makefile                             # Common commands (test, lint, migrate, run)
│
├── config/
│   ├── __init__.py
│   ├── settings.py                      # Pydantic Settings: env vars, defaults
│   ├── leagues.py                       # League definitions, API key mappings
│   ├── bookmakers.py                    # Bookmaker definitions and region mappings
│   └── constants.py                     # EV thresholds, Kelly fraction, limits
│
├── db/
│   ├── __init__.py
│   ├── engine.py                        # SQLAlchemy engine factory (SQLite/Postgres)
│   ├── session.py                       # Session management, context managers
│   ├── models/
│   │   ├── __init__.py
│   │   ├── base.py                      # DeclarativeBase, common mixins (TimestampMixin)
│   │   ├── raw.py                       # RawFixture, RawOdds, RawPlayerStats
│   │   ├── entities.py                  # Team, Player, League, Season, Alias
│   │   ├── matches.py                   # Match, MatchStats, MatchLineup
│   │   ├── odds.py                      # OddsSnapshot, OddsMovement, ClosingLine
│   │   ├── stats.py                     # PlayerSeasonStats, TeamSeasonStats, FeatureVector
│   │   ├── predictions.py              # ModelPrediction, EVSignal
│   │   ├── betting.py                   # Bet, BankrollSnapshot, DailyExposure
│   │   └── system.py                    # IngestionLog, EntityResolutionLog, ModelRun
│   └── migrations/
│       ├── env.py                       # Alembic migration environment
│       └── versions/                    # Auto-generated migration files
│
├── ingestion/
│   ├── __init__.py
│   ├── base_client.py                   # Abstract HTTP client (httpx): retry, rate-limit, logging
│   ├── optic_odds/
│   │   ├── __init__.py
│   │   ├── client.py                    # OpticOdds API client
│   │   ├── schemas.py                   # Pydantic response models
│   │   ├── fixtures.py                  # Fixture fetching and storage
│   │   ├── odds.py                      # Odds fetching (pre-match + live)
│   │   ├── player_results.py            # Player results/stats fetching
│   │   └── mappers.py                   # Raw response -> DB model mappers
│   ├── the_odds_api/
│   │   ├── __init__.py
│   │   ├── client.py                    # The Odds API client
│   │   ├── schemas.py                   # Pydantic response models
│   │   ├── odds.py                      # Odds fetching (h2h, totals, btts, corners, player props)
│   │   ├── events.py                    # Event listing and scores
│   │   └── mappers.py                   # Raw response -> DB model mappers
│   ├── sportmonks/
│   │   ├── __init__.py
│   │   ├── client.py                    # SportMonks API client
│   │   ├── schemas.py                   # Pydantic response models
│   │   ├── fixtures.py                  # Historical fixture data
│   │   ├── statistics.py                # Player and team statistics
│   │   ├── standings.py                 # League standings
│   │   └── mappers.py                   # Raw response -> DB model mappers
│   └── scheduler.py                     # APScheduler jobs: periodic ingestion triggers
│
├── entity_resolution/
│   ├── __init__.py
│   ├── resolver.py                      # Main EntityResolver class
│   ├── matchers.py                      # ExactMatcher, FuzzyMatcher, ContextualMatcher
│   ├── alias_store.py                   # Alias table CRUD operations
│   ├── confidence.py                    # Confidence scoring and thresholds
│   ├── seed_data.py                     # Initial alias seeds for known teams/leagues
│   └── cross_source.py                  # Cross-API entity linking (Optic<->OddsAPI<->SportMonks)
│
├── features/
│   ├── __init__.py
│   ├── pipeline.py                      # Feature pipeline orchestrator
│   ├── per90.py                         # Per-90-minute normalization
│   ├── rolling.py                       # Rolling window calculations (3, 5, 10 matches)
│   ├── opponent_adjustment.py           # Opponent strength adjustments
│   ├── consistency.py                   # Variance/consistency scoring
│   ├── drift.py                         # Statistical drift detection (PSI, KS-test)
│   └── feature_store.py                 # Read/write feature vectors to DB
│
├── models/
│   ├── __init__.py
│   ├── base_model.py                    # Abstract StatisticalModel interface
│   ├── poisson.py                       # Poisson regression for goals
│   ├── negative_binomial.py             # NegBin for over-dispersed stats (corners, shots)
│   ├── dixon_coles.py                   # Dixon-Coles bivariate correction
│   ├── player_props.py                  # Player prop models (NegBin per stat type)
│   ├── btts.py                          # BTTS logistic regression model
│   ├── ensemble.py                      # Model ensembling / weighting
│   ├── calibration.py                   # Platt scaling, isotonic regression
│   ├── evaluation.py                    # Brier score, log-loss, calibration curves
│   └── registry.py                      # Model versioning and persistence (joblib)
│
├── ev_engine/
│   ├── __init__.py
│   ├── calculator.py                    # EV = (prob * odds) - 1
│   ├── odds_comparison.py               # Best-price finder across bookmakers
│   ├── signal_generator.py              # Generate EVSignal objects above threshold
│   ├── filters.py                       # Odds range filter, confidence filter, market filter
│   └── closing_line.py                  # Closing line value tracking
│
├── risk/
│   ├── __init__.py
│   ├── kelly.py                         # Quarter-Kelly stake calculator
│   ├── bankroll.py                      # Bankroll state management
│   ├── exposure.py                      # Daily exposure, per-fixture exposure tracking
│   ├── stops.py                         # Stop-loss logic (daily 5%, drawdown 20%)
│   └── position_sizer.py               # Combined sizing: Kelly + all constraints
│
├── backtesting/
│   ├── __init__.py
│   ├── walk_forward.py                  # Walk-forward backtesting engine
│   ├── simulator.py                     # Bet simulation with bankroll tracking
│   ├── metrics.py                       # ROI, Brier, drawdown, CLV, Sharpe
│   ├── historical_loader.py             # Load SportMonks historical data for backtests
│   └── reports.py                       # Generate backtest result reports
│
├── agents/
│   ├── __init__.py
│   ├── base_agent.py                    # Abstract agent: system prompt, tool definitions
│   ├── orchestrator.py                  # Lead orchestrator (runtime agent)
│   ├── anomaly_reasoner.py              # Anomaly reasoning agent (runtime)
│   ├── message_bus.py                   # In-process message passing (asyncio queues)
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── db_tools.py                  # Claude tools: query DB, get stats
│   │   ├── ev_tools.py                  # Claude tools: run EV scan, get signals
│   │   ├── risk_tools.py                # Claude tools: check exposure, get bankroll
│   │   ├── ingestion_tools.py           # Claude tools: trigger data refresh
│   │   └── model_tools.py              # Claude tools: retrain, evaluate model
│   └── prompts/
│       ├── orchestrator_system.md       # System prompt for orchestrator
│       └── anomaly_system.md            # System prompt for anomaly reasoner
│
├── cli/
│   ├── __init__.py
│   ├── app.py                           # Typer app entry point
│   ├── commands/
│   │   ├── __init__.py
│   │   ├── ingest.py                    # CLI: trigger ingestion
│   │   ├── scan.py                      # CLI: run EV scan
│   │   ├── bet.py                       # CLI: view/record/approve bets
│   │   ├── backtest.py                  # CLI: run backtests
│   │   ├── model.py                     # CLI: train/evaluate models
│   │   ├── bankroll.py                  # CLI: bankroll status
│   │   ├── entity.py                    # CLI: entity resolution management
│   │   └── dashboard.py                 # CLI: launch web dashboard
│   └── formatters.py                    # Rich tables, panels, progress bars
│
├── dashboard/
│   ├── __init__.py
│   ├── app.py                           # NiceGUI application entry
│   ├── pages/
│   │   ├── __init__.py
│   │   ├── overview.py                  # Main dashboard: bankroll, P&L, active signals
│   │   ├── signals.py                   # Current EV signals with approve/reject
│   │   ├── history.py                   # Bet history, performance charts
│   │   ├── models.py                    # Model performance, calibration plots
│   │   ├── ingestion.py                 # Data freshness, ingestion health
│   │   └── settings.py                  # Configuration, league toggles
│   └── components/
│       ├── __init__.py
│       ├── charts.py                    # ECharts wrappers for P&L, ROI, calibration
│       ├── tables.py                    # Signal tables, bet tables
│       └── nav.py                       # Navigation sidebar
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                      # Fixtures: test DB, mock API responses, factories
│   ├── fixtures/                        # JSON response fixtures for API mocking
│   │   ├── optic_odds_fixtures.json
│   │   ├── optic_odds_odds.json
│   │   ├── optic_odds_player_results.json
│   │   ├── the_odds_api_odds.json
│   │   ├── sportmonks_fixtures.json
│   │   └── sportmonks_statistics.json
│   ├── unit/
│   │   ├── test_entity_resolution.py
│   │   ├── test_poisson.py
│   │   ├── test_negative_binomial.py
│   │   ├── test_dixon_coles.py
│   │   ├── test_ev_calculator.py
│   │   ├── test_kelly.py
│   │   ├── test_exposure.py
│   │   ├── test_feature_pipeline.py
│   │   ├── test_per90.py
│   │   ├── test_rolling.py
│   │   ├── test_odds_comparison.py
│   │   ├── test_filters.py
│   │   └── test_stops.py
│   ├── integration/
│   │   ├── test_ingestion_pipeline.py
│   │   ├── test_optic_odds_client.py
│   │   ├── test_the_odds_api_client.py
│   │   ├── test_sportmonks_client.py
│   │   ├── test_entity_cross_source.py
│   │   └── test_ev_pipeline_end_to_end.py
│   └── backtests/
│       ├── test_walk_forward.py
│       └── test_historical_accuracy.py
│
└── scripts/
    ├── seed_aliases.py                  # One-time alias seeding
    ├── backfill_sportmonks.py           # Historical data backfill from SportMonks
    ├── export_signals.py                # Export signals to CSV
    └── health_check.py                  # System health verification
```

---

## 2. Phase-by-Phase Breakdown

### PHASE 1-2: Data Infrastructure (Weeks 1-4)

#### Week 1: Project Scaffolding and API Clients

**Deliverables:**
- Project skeleton with `pyproject.toml`, dependency management, and configuration
- Base HTTP client with retry logic, rate limiting, and structured logging
- Optic Odds API client (all relevant endpoints)
- The Odds API client (all relevant endpoints)
- SportMonks API client (all relevant endpoints)

**Specific Tasks:**

1. **Project initialization** (Day 1)
   - Create `pyproject.toml` with all dependencies:
     - Runtime: `httpx[http2]`, `sqlalchemy[asyncio]>=2.0`, `alembic`, `pydantic>=2.0`, `pydantic-settings`, `typer[all]`, `rich`, `statsmodels`, `scikit-learn`, `xgboost`, `scipy`, `numpy`, `pandas`, `rapidfuzz`, `apscheduler>=3.10`, `anthropic`, `nicegui`, `joblib`, `echarts`
     - Dev: `pytest`, `pytest-asyncio`, `pytest-cov`, `respx` (httpx mocking), `factory-boy`, `ruff`, `mypy`
   - Create `config/settings.py` using `pydantic-settings.BaseSettings` reading from `.env`:
     - `OPTIC_ODDS_API_KEY`, `THE_ODDS_API_KEY`, `SPORTMONKS_API_KEY`, `ANTHROPIC_API_KEY`
     - `DATABASE_URL` (default `sqlite:///./ev_system.db`)
     - `LOG_LEVEL`, `BANKROLL_DKK`, `MIN_EV_THRESHOLD`, `MAX_STAKE_PCT`, `KELLY_FRACTION`
   - Create `config/leagues.py` with a `League` dataclass mapping:
     - `name`, `optic_odds_id`, `the_odds_api_key`, `sportmonks_id`, `country`, `active`
     - Pre-populate all 8 leagues with their API-specific identifiers
   - Create `config/bookmakers.py` with:
     - `Bookmaker` dataclass: `name`, `optic_odds_key`, `the_odds_api_key`, `region`, `active`
     - Entries for: Bet365 (key `bet365`), Unibet (`unibet`), Danske Spel (mapped via Optic Odds only since The Odds API lacks Danish-specific books; use `eu` region for Unibet/Bet365 EU variants)
   - **Agent responsibility**: System Architect (Agent 2), Backend Builder (Agent 3)
   - **Acceptance criteria**: `python -c "from config.settings import settings; print(settings.model_dump())"` runs without error; all 8 leagues defined; all bookmakers defined

2. **Base HTTP client** (Day 1-2)
   - File: `ingestion/base_client.py`
   - Implement `BaseAPIClient` class using `httpx.AsyncClient`:
     - Constructor takes `base_url`, `api_key`, `rate_limit_per_second`, `max_retries`, `timeout`
     - `_request()` method with: exponential backoff (base 2s, max 60s), retry on 429/500/502/503, structured logging of request/response, rate limiting via `asyncio.Semaphore`
     - Response validation: raise custom `APIError`, `RateLimitError`, `AuthenticationError`
     - Request/response logging to `ingestion_log` table
   - **Agent responsibility**: Data Integration (Agent 4)
   - **Acceptance criteria**: Unit tests pass for retry logic with mocked 429 responses; rate limiter correctly throttles

3. **Optic Odds client** (Day 2-3)
   - Files: `ingestion/optic_odds/client.py`, `schemas.py`, `fixtures.py`, `odds.py`, `player_results.py`, `mappers.py`
   - `OpticOddsClient(BaseAPIClient)` with `base_url = "https://api.opticodds.com/api/v3"` and `X-Api-Key` header auth
   - Methods:
     - `get_fixtures(sport="soccer", league=None, status=None)` -> calls `GET /fixtures`
     - `get_active_fixtures(league=None)` -> calls `GET /fixtures/active`
     - `get_odds(fixture_id, sportsbook=None, market=None)` -> calls `GET /fixtures/odds`
     - `get_historical_odds(fixture_id, sportsbook=None)` -> calls `GET /fixtures/odds/historical`
     - `get_player_results(fixture_id)` -> calls `GET /fixtures/player-results`
     - `get_player_results_last_x(player_id, count=10)` -> calls `GET /fixtures/player-results/last-x`
     - `get_results(fixture_id=None)` -> calls `GET /fixtures/results`
     - `get_leagues(sport="soccer", active=True)` -> calls `GET /leagues/active`
     - `get_sportsbooks(active=True)` -> calls `GET /sportsbooks/active`
     - `get_markets(active=True)` -> calls `GET /markets/active`
     - `get_teams(sport="soccer")` -> calls `GET /teams`
     - `get_players(sport="soccer")` -> calls `GET /players`
     - `get_head_to_head(team1, team2)` -> calls `GET /fixtures/results/head-to-head`
   - Pydantic schemas in `schemas.py` for every response type
   - Mapper functions in `mappers.py` to convert Pydantic models to SQLAlchemy models
   - **Agent responsibility**: Data Integration (Agent 4)
   - **Acceptance criteria**: Each method returns correctly typed Pydantic models from saved JSON fixtures; mapper functions produce valid SQLAlchemy model instances

4. **The Odds API client** (Day 3-4)
   - Files: `ingestion/the_odds_api/client.py`, `schemas.py`, `odds.py`, `events.py`, `mappers.py`
   - `TheOddsAPIClient(BaseAPIClient)` with `base_url = "https://api.the-odds-api.com"` and `apiKey` query param auth
   - Methods:
     - `get_sports()` -> `GET /v4/sports/`
     - `get_events(sport_key)` -> `GET /v4/sports/{sport}/events`
     - `get_odds(sport_key, regions="eu", markets="h2h,totals,btts,alternate_totals_corners,alternate_totals_cards", odds_format="decimal")` -> `GET /v4/sports/{sport}/odds/`
     - `get_event_odds(sport_key, event_id, regions="eu", markets=None)` -> `GET /v4/sports/{sport}/events/{eventId}/odds`
     - `get_event_markets(sport_key, event_id, regions="eu")` -> `GET /v4/sports/{sport}/events/{eventId}/markets`
     - `get_scores(sport_key, days_from=3)` -> `GET /v4/sports/{sport}/scores/`
     - `get_historical_odds(sport_key, date, regions="eu", markets=None)` -> `GET /v4/historical/sports/{sport}/odds`
   - Track remaining credits via response headers `x-requests-remaining`, `x-requests-used`
   - Sport keys constant map: `SPORT_KEYS = {"epl": "soccer_epl", "la_liga": "soccer_spain_la_liga", "serie_a": "soccer_italy_serie_a", "bundesliga": "soccer_germany_bundesliga", "ligue_1": "soccer_france_ligue_one", "danish_superliga": "soccer_denmark_superliga", "allsvenskan": "soccer_sweden_allsvenskan", "eliteserien": "soccer_norway_eliteserien"}`
   - Key markets to request: `h2h`, `h2h_3_way`, `totals`, `btts`, `alternate_totals_corners`, `alternate_totals_cards`, `team_totals`, `alternate_team_totals`, `draw_no_bet`, `alternate_spreads`
   - **Agent responsibility**: Data Integration (Agent 4)
   - **Acceptance criteria**: Credit tracking works; all 8 league sport keys resolve; Danish bookmaker odds retrieved via `eu` region

5. **SportMonks client** (Day 4-5)
   - Files: `ingestion/sportmonks/client.py`, `schemas.py`, `fixtures.py`, `statistics.py`, `standings.py`, `mappers.py`
   - `SportMonksClient(BaseAPIClient)` with `base_url = "https://api.sportmonks.com/v3/football"` and `Authorization: {api_token}` header
   - Methods:
     - `get_fixtures_by_date_range(start, end, includes="statistics;lineups;events")` -> `GET /fixtures/date-range`
     - `get_fixture(fixture_id, includes="statistics;lineups;events;scores")` -> `GET /fixtures/{id}`
     - `get_season_statistics(season_id, participant_type="team")` -> `GET /statistics/season`
     - `get_player(player_id)` -> `GET /players/{id}`
     - `get_team(team_id)` -> `GET /teams/{id}`
     - `get_teams_by_season(season_id)` -> `GET /teams/season/{season_id}`
     - `get_standings(season_id)` -> `GET /standings/season/{id}`
     - `get_topscorers(season_id)` -> `GET /topscorers/season/{id}`
     - `get_leagues()` -> `GET /leagues`
     - `get_seasons(league_id=None)` -> `GET /seasons`
     - `get_squads(team_id, season_id)` -> team squad endpoint
   - Pagination handling: SportMonks uses cursor-based pagination; implement auto-pagination in `_paginate()` method
   - **Agent responsibility**: Data Integration (Agent 4)
   - **Acceptance criteria**: Pagination works across 100+ result pages; historical fixture data loads from March 2024 onward

#### Week 2: Database Schema and Raw Data Ingestion

**Deliverables:**
- Complete database schema via SQLAlchemy models and Alembic migrations
- Raw data ingestion pipelines that store every API response before transformation
- Ingestion scheduler for periodic data fetching

**Specific Tasks:**

6. **Database models** (Day 6-7)
   - All files in `db/models/` (see schema section below for full detail)
   - `db/engine.py`: factory function `create_engine(url)` that returns SQLAlchemy engine; auto-detect SQLite vs Postgres from URL
   - `db/session.py`: async session factory, `get_session()` context manager
   - **Agent responsibility**: Database & Data Model (Agent 7)
   - **Acceptance criteria**: `alembic upgrade head` creates all tables; both SQLite and Postgres URLs work

7. **Alembic migration setup** (Day 7)
   - Initialize Alembic, configure `env.py` to auto-detect models from `db.models`
   - Generate initial migration from all model definitions
   - **Agent responsibility**: Database & Data Model (Agent 7)
   - **Acceptance criteria**: `alembic upgrade head` and `alembic downgrade base` both succeed cleanly

8. **Raw ingestion pipelines** (Day 7-9)
   - `ingestion/optic_odds/fixtures.py`: `ingest_fixtures(league)` -> fetch and store to `raw_fixtures`
   - `ingestion/optic_odds/odds.py`: `ingest_odds(fixture_id)` -> fetch and store to `raw_odds`
   - `ingestion/optic_odds/player_results.py`: `ingest_player_results(fixture_id)` -> store to `raw_player_stats`
   - `ingestion/the_odds_api/odds.py`: `ingest_odds(sport_key)` -> fetch all odds for sport and store
   - `ingestion/the_odds_api/events.py`: `ingest_events(sport_key)` -> fetch events and store
   - `ingestion/sportmonks/fixtures.py`: `backfill_fixtures(league_id, start_date, end_date)` -> paginate and store all historical fixtures
   - `ingestion/sportmonks/statistics.py`: `backfill_statistics(season_id)` -> store all player/team stats
   - Every raw record stores: `source` (enum: optic_odds/the_odds_api/sportmonks), `raw_json` (JSONB/JSON column), `fetched_at` timestamp, `processed` boolean flag
   - **Agent responsibility**: Backend Builder (Agent 3), Data Integration (Agent 4)
   - **Acceptance criteria**: Raw tables populated with real API data for at least one league; `raw_json` fields contain complete API responses; no data loss between API and storage

9. **Ingestion scheduler** (Day 9-10)
   - File: `ingestion/scheduler.py`
   - Use `APScheduler` with these jobs:
     - `ingest_upcoming_fixtures`: every 6 hours, fetch fixtures for next 7 days from all 8 leagues via Optic Odds
     - `ingest_prematch_odds`: every 30 minutes for fixtures starting within 24 hours, from both Optic Odds and The Odds API
     - `ingest_closing_odds`: 5 minutes before kickoff, final odds snapshot
     - `ingest_results`: every hour, fetch completed match results
     - `ingest_player_results`: after match completion (triggered by results ingestion), fetch player stats
   - Job persistence using APScheduler's SQLAlchemy job store (same DB)
   - Credit-aware scheduling for The Odds API: track remaining credits and skip if below 500
   - **Agent responsibility**: Backend Builder (Agent 3)
   - **Acceptance criteria**: Jobs execute on schedule; no duplicate ingestion; credit tracking prevents overspend

#### Week 3: Entity Resolution System

**Deliverables:**
- Multi-strategy entity resolver matching teams, players, and leagues across all three APIs
- Seed alias data for all 8 leagues' teams
- Cross-source entity linking

**Specific Tasks:**

10. **Entity resolution core** (Day 11-13)
    - `entity_resolution/resolver.py`: `EntityResolver` class with method `resolve(name, entity_type, source, context=None) -> (canonical_id, confidence)`
    - Resolution cascade (in order):
      1. Exact match against canonical name
      2. Exact match against alias table
      3. Normalized match (lowercase, strip FC/FK/IF prefixes, remove diacritics)
      4. Fuzzy match using `rapidfuzz.fuzz.token_sort_ratio` with threshold >= 85
      5. Contextual match: if league is known, restrict candidates to that league's teams
    - `entity_resolution/matchers.py`: `ExactMatcher`, `NormalizedMatcher`, `FuzzyMatcher(threshold=85)`, `ContextualMatcher`
    - `entity_resolution/confidence.py`: confidence scoring: exact=1.0, alias=0.95, normalized=0.90, fuzzy=0.70-0.89 (scaled by similarity), contextual boost +0.05
    - `entity_resolution/alias_store.py`: CRUD for alias table; `add_alias(canonical_id, alias_name, source)`, `get_aliases(canonical_id)`, `find_canonical(alias_name)`
    - **Agent responsibility**: Entity Resolution (Agent 5)
    - **Acceptance criteria**: "FC Barcelona", "Barcelona", "Barca", "FC Barca" all resolve to same canonical ID with confidence >= 0.85; "FC Copenhagen" vs "Copenhagen" resolves correctly; Swedish/Norwegian/Danish team names with special characters resolve correctly

11. **Seed data** (Day 13-14)
    - `entity_resolution/seed_data.py`: Pre-populate aliases for:
      - All teams in 8 leagues (approximately 160 teams)
      - Common name variations (with/without FC, city abbreviations, local language names)
      - Cross-API ID mappings: for each team, store `optic_odds_id`, `the_odds_api_name`, `sportmonks_id`
    - `scripts/seed_aliases.py`: script to populate from seed data
    - **Agent responsibility**: Entity Resolution (Agent 5)
    - **Acceptance criteria**: Every team in every active league has at least 2 alias entries; cross-API mappings exist for > 90% of teams

12. **Cross-source entity linking** (Day 14)
    - `entity_resolution/cross_source.py`: `CrossSourceLinker` class
    - Method `link_fixture(optic_fixture, odds_api_event)` -> match by: date (within 2 hours), team name resolution, league
    - Method `link_player(optic_player, sportmonks_player)` -> match by: name similarity + team + position
    - Unmatched entities logged to `entity_resolution_log` table for manual review
    - **Agent responsibility**: Entity Resolution (Agent 5)
    - **Acceptance criteria**: > 95% of fixtures matched across sources; unmatched entities flagged with reason

#### Week 4: Feature Pipeline

**Deliverables:**
- Complete feature engineering pipeline that transforms raw stats into model-ready feature vectors
- All statistical features: per-90, rolling windows, opponent adjustment, consistency scoring
- Drift detection system

**Specific Tasks:**

13. **Per-90 normalization** (Day 15-16)
    - `features/per90.py`: `normalize_per90(stat_value, minutes_played)` -> `stat_value * 90 / minutes_played`
    - Handle edge cases: minutes < 15 (exclude), substitute appearances, multi-game aggregation
    - Apply to: goals, assists, shots, shots_on_target, tackles, interceptions, passes, key_passes, corners_won, fouls, cards
    - **Agent responsibility**: Backend Builder (Agent 3)
    - **Acceptance criteria**: Per-90 values mathematically correct for test cases; players with < 15 minutes excluded

14. **Rolling window calculations** (Day 16-17)
    - `features/rolling.py`: `RollingCalculator` class
    - Methods:
      - `rolling_mean(player_id, stat, window)` -> mean over last N matches
      - `rolling_median(player_id, stat, window)` -> median over last N matches
      - `rolling_std(player_id, stat, window)` -> standard deviation
      - `rolling_trend(player_id, stat, window)` -> linear slope (is stat increasing/decreasing?)
    - Windows: 3, 5, 10 matches
    - Same methods for team-level stats
    - Must respect chronological ordering and never include future data
    - **Agent responsibility**: Backend Builder (Agent 3)
    - **Acceptance criteria**: Rolling calculations verified against hand-calculated examples; no future data leakage confirmed by date ordering tests

15. **Opponent adjustment** (Day 17-18)
    - `features/opponent_adjustment.py`: `OpponentAdjuster` class
    - Calculate league-average for each stat, then compute opponent's defensive/offensive strength ratio
    - `adjust(raw_stat, opponent_team_id, stat_type)` -> `raw_stat * league_avg / opponent_avg`
    - Opponent strength computed from their season-long conceded stats (goals conceded, corners conceded, etc.)
    - **Agent responsibility**: Backend Builder (Agent 3)
    - **Acceptance criteria**: Stats against weak defenses adjusted down; stats against strong defenses adjusted up; adjustments mathematically verified

16. **Consistency scoring** (Day 18)
    - `features/consistency.py`: `ConsistencyScorer` class
    - `score(player_id, stat, window=10)` -> coefficient of variation (CV = std/mean)
    - Categorize: CV < 0.3 = "consistent", 0.3-0.6 = "moderate", > 0.6 = "volatile"
    - Used as a model input and as a filter (prefer bets on consistent performers)
    - **Agent responsibility**: Backend Builder (Agent 3)
    - **Acceptance criteria**: CV calculations correct; consistency categories assigned properly

17. **Drift detection** (Day 19)
    - `features/drift.py`: `DriftDetector` class
    - Methods:
      - `detect_psi(reference_distribution, current_distribution, threshold=0.2)` -> Population Stability Index
      - `detect_ks(reference, current, p_threshold=0.05)` -> Kolmogorov-Smirnov test
      - `check_all_features(model_id)` -> run PSI and KS for all features, flag drifted ones
    - Reference distribution: training data feature distributions (stored at training time)
    - If drift detected: log warning, flag model for retraining
    - **Agent responsibility**: Backend Builder (Agent 3)
    - **Acceptance criteria**: PSI correctly flags distribution shifts in synthetic test data; KS test p-values validated

18. **Feature pipeline orchestrator** (Day 19-20)
    - `features/pipeline.py`: `FeaturePipeline` class
    - Method `build_features(match_id)` -> orchestrates all feature calculations for a given match:
      1. Load raw player/team stats from DB
      2. Apply per-90 normalization
      3. Compute rolling windows (3, 5, 10)
      4. Apply opponent adjustments
      5. Compute consistency scores
      6. Store as `FeatureVector` in DB
    - Method `build_features_batch(match_ids)` -> parallel feature building
    - `features/feature_store.py`: read/write feature vectors, with versioning
    - **Agent responsibility**: Backend Builder (Agent 3)
    - **Acceptance criteria**: Full pipeline produces feature vectors for historical matches; no null values in required features; feature store supports multiple versions

---

### PHASE 3: Statistical Modeling (Weeks 5-7)

#### Week 5: Team Market Models (Tier 2 -- FIRST PRIORITY)

**Deliverables:**
- Poisson model for team goals
- Dixon-Coles model for improved goal prediction
- Negative Binomial model for team corners
- BTTS logistic regression model

**Specific Tasks:**

19. **Base model interface** (Day 21)
    - `models/base_model.py`: Abstract class `StatisticalModel`
    - Methods:
      - `fit(X, y)` -> train on feature matrix
      - `predict_proba(X)` -> probability distribution or single probability
      - `predict_line(X, line)` -> probability of over/under a specific line
      - `evaluate(X_test, y_test)` -> dict of metrics (Brier score, log-loss, calibration)
      - `save(path)` / `load(path)` -> persistence via joblib
      - `get_params()` -> model parameters for reproducibility
    - `models/registry.py`: `ModelRegistry` class storing model versions with metadata: `model_type`, `trained_at`, `training_data_cutoff`, `metrics`, `file_path`, `active` flag
    - **Agent responsibility**: System Architect (Agent 2), Backend Builder (Agent 3)
    - **Acceptance criteria**: Interface enforced via ABC; registry tracks model history

20. **Poisson goal model** (Day 21-23)
    - `models/poisson.py`: `PoissonGoalModel(StatisticalModel)`
    - Inputs: team attack strength, team defense strength, home/away, league, recent form (rolling features)
    - Uses `statsmodels.genmod.generalized_linear_model.GLM` with Poisson family
    - `predict_proba(features)` returns dict: `{0: p_0goals, 1: p_1goal, 2: p_2goals, ...}` for each team
    - `predict_line(features, line=2.5)` -> P(goals > 2.5) = 1 - sum(P(0), P(1), P(2))
    - `predict_match_score_matrix(home_features, away_features)` -> 7x7 score probability matrix
    - Training on SportMonks historical data: all 8 leagues, from March 2024 onward
    - Separate attack and defense parameters per team (team strength model)
    - **Agent responsibility**: Backend Builder (Agent 3)
    - **Acceptance criteria**: Brier score < 0.25 on holdout set; predicted goal distributions match observed frequencies within 5%

21. **Dixon-Coles model** (Day 23-25)
    - `models/dixon_coles.py`: `DixonColesModel(StatisticalModel)`
    - Extends Poisson with:
      - Bivariate correction for low-scoring games (0-0, 1-0, 0-1, 1-1) via rho parameter
      - Time-decay weighting: recent matches weighted more heavily (half-life of ~30 matches)
      - Home advantage parameter
    - Fit via maximum likelihood estimation using `scipy.optimize.minimize`
    - Parameters: `alpha_i` (attack strength per team), `beta_i` (defense strength per team), `gamma` (home advantage), `rho` (bivariate correction)
    - `predict_match_outcome(home_team, away_team)` -> `{home_win: p, draw: p, away_win: p}`
    - `predict_goals_ou(home_team, away_team, line)` -> P(total > line)
    - **Agent responsibility**: Backend Builder (Agent 3)
    - **Acceptance criteria**: Brier score improvement over basic Poisson by at least 2%; rho parameter negative (correcting for excess low scores); home advantage parameter positive and significant

22. **Negative Binomial corners model** (Day 25-26)
    - `models/negative_binomial.py`: `NegBinModel(StatisticalModel)`
    - Used for team corners (variance > mean, overdispersed)
    - Uses `statsmodels.genmod.generalized_linear_model.GLM` with NegativeBinomial family
    - Inputs: team's corner-taking tendency (rolling), opponent's corners conceded (rolling), match importance, home/away
    - `predict_line(features, line=10.5)` -> P(corners > 10.5)
    - `predict_team_corners(features, line=5.5)` -> P(team corners > 5.5)
    - **Agent responsibility**: Backend Builder (Agent 3)
    - **Acceptance criteria**: Overdispersion parameter significant (variance > mean confirmed); line predictions calibrated on holdout

23. **BTTS model** (Day 26-27)
    - `models/btts.py`: `BTTSModel(StatisticalModel)`
    - Logistic regression or gradient-boosted classifier
    - Inputs: both teams' scoring rates, both teams' clean sheet rates, both teams' BTTS history (rolling), league average BTTS rate
    - Alternative: derive from Poisson/Dixon-Coles: P(BTTS) = 1 - P(home=0) - P(away=0) + P(home=0 AND away=0)
    - Implement both approaches and compare
    - **Agent responsibility**: Backend Builder (Agent 3)
    - **Acceptance criteria**: AUC > 0.65; calibration curve within 5% of diagonal

#### Week 6: Player Prop Models (Tier 1)

**Deliverables:**
- Negative Binomial models for player shots, tackles, passes over/under
- Anytime goalscorer model
- Player cards model

**Specific Tasks:**

24. **Player shots O/U model** (Day 28-29)
    - `models/player_props.py`: `PlayerPropModel(StatisticalModel)` parameterized by stat type
    - `PlayerShotsModel = PlayerPropModel(stat="shots")`
    - NegBin regression with inputs: player's rolling shots per 90, opponent shots conceded per 90, home/away, player minutes projection, consistency score
    - `predict_line(player_features, line=2.5)` -> P(shots > 2.5)
    - **Agent responsibility**: Backend Builder (Agent 3)
    - **Acceptance criteria**: Calibration within 5% across all common lines (0.5, 1.5, 2.5, 3.5)

25. **Player tackles and passes models** (Day 29-30)
    - Same `PlayerPropModel` class with `stat="tackles"` and `stat="passes"`
    - Tackles: NegBin, inputs include opponent possession rate, match tempo
    - Passes: NegBin or Poisson (passes often high count, less overdispersed), inputs include team possession, opponent pressing intensity
    - **Agent responsibility**: Backend Builder (Agent 3)
    - **Acceptance criteria**: Overdispersion test determines correct distribution family per stat

26. **Anytime goalscorer model** (Day 30-31)
    - Separate model in `models/player_props.py`: `AnytimeGoalscorerModel`
    - Logistic regression / XGBoost classifier
    - Inputs: player xG per 90 (from SportMonks), shots per 90, shot accuracy, minutes projection, opponent goals conceded rate
    - P(player scores) calculated; compare to bookmaker implied probability
    - **Agent responsibility**: Backend Builder (Agent 3)
    - **Acceptance criteria**: AUC > 0.70; profit in backtest when EV > 5%

27. **Player cards model** (Day 31-32)
    - `PlayerCardsModel` in `models/player_props.py`
    - Logistic regression for P(player gets carded)
    - Inputs: player card history per 90, referee card rate, match rivalry factor, player position (defenders/midfielders more likely)
    - **Agent responsibility**: Backend Builder (Agent 3)
    - **Acceptance criteria**: AUC > 0.60 (cards are inherently hard to predict, lower bar acceptable)

#### Week 7: Match Market Models (Tier 3) and Model Calibration

**Deliverables:**
- 1X2 match result model (derived from Dixon-Coles)
- Asian handicap model
- Model ensemble framework
- Calibration pipeline

**Specific Tasks:**

28. **1X2 and Asian Handicap models** (Day 33-34)
    - These are derived from the Dixon-Coles model already built
    - 1X2: direct output of `predict_match_outcome()`
    - Asian Handicap: from the score matrix, sum probabilities where `(home_goals - away_goals + handicap_line) > 0`
    - Implement in `models/dixon_coles.py` as additional methods
    - **Agent responsibility**: Backend Builder (Agent 3)
    - **Acceptance criteria**: 1X2 probabilities sum to 1.0; Asian handicap probabilities consistent with 1X2

29. **Model ensemble** (Day 34-35)
    - `models/ensemble.py`: `ModelEnsemble` class
    - For goals: weighted average of Poisson and Dixon-Coles (weights determined by recent Brier scores)
    - For player props: single model per stat (no ensemble needed initially)
    - Dynamic weight update after each evaluation window
    - **Agent responsibility**: Backend Builder (Agent 3)
    - **Acceptance criteria**: Ensemble Brier score <= best individual model's Brier score

30. **Calibration** (Day 35)
    - `models/calibration.py`: `ModelCalibrator` class
    - Apply Platt scaling (logistic) or isotonic regression to raw model probabilities
    - `calibrate(model, X_cal, y_cal)` -> calibrated model
    - `plot_calibration(y_true, y_pred, bins=10)` -> reliability diagram data
    - Recalibrate every 2 weeks using most recent 200 predictions
    - **Agent responsibility**: Backend Builder (Agent 3), QA & Testing (Agent 8)
    - **Acceptance criteria**: Post-calibration reliability diagram within 3% of perfect diagonal for each bin

31. **Model evaluation framework** (Day 35)
    - `models/evaluation.py`: `ModelEvaluator` class
    - Metrics: Brier score, log-loss, AUC-ROC, calibration error (ECE), Sharpe ratio of hypothetical bets
    - `evaluate(model, X_test, y_test, market_odds=None)` -> comprehensive evaluation dict
    - Store results in `model_runs` table
    - **Agent responsibility**: QA & Testing (Agent 8)
    - **Acceptance criteria**: All metrics computed and stored; historical comparison available

---

### PHASE 4: EV Engine + Forward Backtesting (Weeks 8-9)

#### Week 8: EV Engine

**Deliverables:**
- EV calculator with configurable thresholds
- Odds comparison engine across bookmakers
- Signal generator with filtering
- Closing line value tracker

**Specific Tasks:**

32. **EV calculator** (Day 36-37)
    - `ev_engine/calculator.py`: `EVCalculator` class
    - `calculate_ev(model_prob, decimal_odds)` -> `(model_prob * decimal_odds) - 1`
    - `calculate_ev_with_margin(model_prob, odds, market_margin)` -> adjust for bookmaker margin
    - `meets_threshold(ev, threshold=0.03)` -> boolean
    - Support batch calculation for all markets in a fixture
    - **Agent responsibility**: Odds & Value Analysis (Agent 6)
    - **Acceptance criteria**: EV calculations mathematically verified against hand calculations; threshold filtering works

33. **Odds comparison** (Day 37-38)
    - `ev_engine/odds_comparison.py`: `OddsComparer` class
    - `find_best_price(fixture_id, market, selection)` -> best odds across Bet365 DK, Unibet DK, Danske Spil
    - `calculate_market_margin(odds_set)` -> implied probability sum - 1
    - `detect_odds_movement(fixture_id, market, selection, window_hours=24)` -> direction and magnitude
    - `get_sharp_bookmaker_line(fixture_id, market)` -> Pinnacle line (via Optic Odds) as benchmark
    - **Agent responsibility**: Odds & Value Analysis (Agent 6)
    - **Acceptance criteria**: Best price correctly identified; market margins within expected range (2-8% for major markets)

34. **Signal generator** (Day 38-39)
    - `ev_engine/signal_generator.py`: `SignalGenerator` class
    - `scan_fixtures(date=None)` -> for each upcoming fixture:
      1. Run all applicable models to get probabilities
      2. Fetch latest odds from all bookmakers
      3. Calculate EV for every market/selection/bookmaker combination
      4. Apply filters (odds range, confidence, consistency)
      5. Generate `EVSignal` objects for bets passing all criteria
    - `EVSignal` dataclass: `fixture_id`, `market`, `selection`, `bookmaker`, `odds`, `model_prob`, `ev`, `confidence`, `model_version`, `features_used`, `generated_at`
    - `ev_engine/filters.py`: `OddsRangeFilter(min=1.50, max=4.00)`, `EVThresholdFilter(min=0.03)`, `ConfidenceFilter(min=0.75)`, `ConsistencyFilter(max_cv=0.6)`, `ModelAgreementFilter(min_models=1)`
    - **Agent responsibility**: Odds & Value Analysis (Agent 6), Backend Builder (Agent 3)
    - **Acceptance criteria**: Signals generated for real upcoming fixtures; all filters applied; signals stored in DB

35. **Closing line value tracker** (Day 39-40)
    - `ev_engine/closing_line.py`: `ClosingLineTracker` class
    - Capture odds at time of signal generation
    - Capture closing odds (last odds before match start)
    - `calculate_clv(signal_odds, closing_odds)` -> `(signal_odds / closing_odds) - 1`
    - Track CLV% over time as a key performance indicator
    - Schedule closing odds capture via APScheduler (5 min before kickoff)
    - **Agent responsibility**: Odds & Value Analysis (Agent 6)
    - **Acceptance criteria**: CLV calculated for all resolved signals; CLV > 0 indicates finding value before the market adjusts

#### Week 9: Risk Management and Backtesting

**Deliverables:**
- Quarter-Kelly staking calculator
- Bankroll management with all stop conditions
- Walk-forward backtesting engine
- Historical backtest on SportMonks data

**Specific Tasks:**

36. **Kelly staking** (Day 41-42)
    - `risk/kelly.py`: `KellyCalculator` class
    - `full_kelly(model_prob, decimal_odds)` -> `(model_prob * decimal_odds - 1) / (decimal_odds - 1)`
    - `quarter_kelly(model_prob, decimal_odds)` -> `full_kelly() * 0.25`
    - `stake_amount(bankroll, kelly_fraction)` -> DKK amount
    - Edge cases: negative Kelly (no bet), very high Kelly (cap at max_stake)
    - **Agent responsibility**: Backend Builder (Agent 3)
    - **Acceptance criteria**: Kelly fractions mathematically correct; quarter-Kelly properly scaled; negative edges produce zero stake

37. **Bankroll and exposure management** (Day 42-43)
    - `risk/bankroll.py`: `BankrollManager` class
    - Track current bankroll, peak bankroll, current drawdown
    - `risk/exposure.py`: `ExposureTracker` class
    - `get_daily_exposure()` -> sum of all pending stakes today as % of bankroll
    - `get_fixture_exposure(fixture_id)` -> sum of stakes on this fixture as % of bankroll
    - `risk/stops.py`: `StopLossManager` class
    - `check_daily_stop(daily_pnl, bankroll)` -> halt if loss > 5%
    - `check_drawdown_stop(current_bankroll, peak_bankroll)` -> halt if drawdown > 20%
    - `risk/position_sizer.py`: `PositionSizer` class combining all constraints:
      - Start with quarter-Kelly stake
      - Cap at 3% of bankroll
      - Check daily exposure < 10%
      - Check fixture exposure < 5%
      - Check stop-loss conditions
      - Return final stake or zero
    - **Agent responsibility**: Backend Builder (Agent 3)
    - **Acceptance criteria**: All limits enforced simultaneously; stop-loss correctly halts all betting; bankroll snapshots persisted after every bet resolution

38. **Walk-forward backtesting** (Day 43-45)
    - `backtesting/walk_forward.py`: `WalkForwardBacktester` class
    - Parameters: `train_window` (matches), `test_window` (matches), `step_size` (matches)
    - Process:
      1. Train model on first `train_window` matches
      2. Generate predictions for next `test_window` matches
      3. Compare predictions to actual outcomes
      4. Slide window by `step_size`
      5. Repeat until all data consumed
    - Never allow future data in training set (strict temporal ordering)
    - `backtesting/simulator.py`: `BetSimulator` class
    - Simulate bankroll trajectory: starting DKK 10,000, apply quarter-Kelly, apply all risk rules
    - Track: cumulative P&L, ROI, max drawdown, Sharpe ratio, longest losing streak
    - `backtesting/metrics.py`: comprehensive metrics computation
    - `backtesting/reports.py`: generate Rich-formatted backtest reports
    - **Agent responsibility**: Backend Builder (Agent 3), QA & Testing (Agent 8)
    - **Acceptance criteria**: Walk-forward produces valid results with no future leakage; backtest ROI computed over 500+ simulated bets; report clearly shows equity curve and key metrics

39. **Historical backtest execution** (Day 45-46)
    - `backtesting/historical_loader.py`: load all SportMonks data from March 2024
    - Run walk-forward backtest for each market tier:
      - Team corners O/U
      - Team goals O/U  
      - BTTS
      - Player shots O/U
      - 1X2 match result
    - Compare to go-live criteria: Brier < 0.22, ROI > 3%, drawdown < 15%, CLV > 55%
    - Document results, identify which markets meet criteria
    - **Agent responsibility**: QA & Testing (Agent 8), Critic (Agent 9)
    - **Acceptance criteria**: Backtest results documented per market; markets not meeting criteria flagged for improvement before going live

---

### PHASE 5: Multi-Agent System with Claude (Weeks 10-12)

#### Week 10: Agent Framework and Orchestrator

**Deliverables:**
- Agent base class with Claude API integration
- Tool definitions for Claude function calling
- Orchestrator agent (runtime)
- Message bus for agent communication

**Specific Tasks:**

40. **Agent base class** (Day 47-48)
    - `agents/base_agent.py`: `BaseAgent` class
    - Properties: `name`, `system_prompt`, `tools` (list of function definitions for Claude), `model` (default `claude-sonnet-4-20250514`)
    - Method `run(user_message, context=None)` -> call Claude API with tools, process tool calls, return final response
    - Tool execution loop: Claude responds with tool_use -> execute tool -> send result back -> repeat until text response
    - Conversation history management (keep last N turns to manage context window)
    - **Agent responsibility**: System Architect (Agent 2), Backend Builder (Agent 3)
    - **Acceptance criteria**: Agent can call tools and receive results; conversation history managed; errors in tool execution handled gracefully

41. **Tool definitions** (Day 48-50)
    - `agents/tools/db_tools.py`:
      - `get_upcoming_fixtures(league=None, days=7)` -> list of fixtures
      - `get_fixture_details(fixture_id)` -> full fixture info with stats
      - `get_player_stats(player_id, window=5)` -> recent player statistics
      - `get_team_stats(team_id, window=5)` -> recent team statistics
      - `query_historical(query_params)` -> flexible historical data query
    - `agents/tools/ev_tools.py`:
      - `run_ev_scan(league=None, fixture_id=None)` -> trigger signal generation, return signals
      - `get_active_signals(min_ev=0.03)` -> current open signals
      - `get_signal_details(signal_id)` -> full signal breakdown
      - `get_model_prediction(fixture_id, market)` -> model probabilities
    - `agents/tools/risk_tools.py`:
      - `get_bankroll_status()` -> current bankroll, drawdown, daily exposure
      - `check_bet_feasibility(stake, fixture_id)` -> passes all risk checks?
      - `get_daily_summary()` -> today's bets, P&L, exposure
    - `agents/tools/ingestion_tools.py`:
      - `trigger_odds_refresh(fixture_id=None)` -> force re-fetch odds
      - `get_data_freshness()` -> when was each data source last updated
      - `check_api_health()` -> status of all API connections
    - `agents/tools/model_tools.py`:
      - `retrain_model(model_type, market)` -> trigger model retraining
      - `get_model_metrics(model_type)` -> current model performance
      - `compare_models(model_type)` -> compare model versions
    - **Agent responsibility**: Backend Builder (Agent 3)
    - **Acceptance criteria**: All tools callable by Claude via function calling; tools return structured data; error handling for invalid parameters

42. **Message bus** (Day 50)
    - `agents/message_bus.py`: `MessageBus` class
    - In-process async message passing using `asyncio.Queue`
    - `AgentMessage` dataclass: `from_agent`, `to_agent`, `message_type` (enum: REQUEST, RESPONSE, ALERT, INFO), `payload`, `timestamp`
    - Methods: `publish(message)`, `subscribe(agent_name, message_types)`, `get_messages(agent_name)`
    - Not a heavyweight message broker -- simple in-process queue suitable for single-process deployment
    - **Agent responsibility**: System Architect (Agent 2)
    - **Acceptance criteria**: Messages delivered between agents; subscription filtering works; messages persisted to log table

43. **Orchestrator agent** (Day 50-52)
    - `agents/orchestrator.py`: `OrchestratorAgent(BaseAgent)`
    - System prompt (`agents/prompts/orchestrator_system.md`):
      - "You are the orchestrator of an EV soccer betting system. Your role is to coordinate data ingestion, model predictions, and signal generation for upcoming matches. You proactively scan for value, alert the user to opportunities, and manage system health."
      - Include risk rules, EV thresholds, and market priorities in system prompt
    - Scheduled invocation: every 30 minutes during active betting hours (8:00-23:00 CET)
    - Workflow per invocation:
      1. Check data freshness (trigger refresh if stale)
      2. Check for upcoming fixtures in next 24 hours
      3. Run EV scan for those fixtures
      4. Evaluate signals against risk constraints
      5. Present recommended bets to user
      6. Check model health (drift detection)
    - **Agent responsibility**: System Architect (Agent 2), Backend Builder (Agent 3)
    - **Acceptance criteria**: Orchestrator completes full workflow cycle; produces actionable recommendations; handles API errors gracefully

#### Week 11: Anomaly Reasoning Agent and CLI

**Deliverables:**
- Anomaly reasoning agent for contextual interpretation
- Complete CLI with all commands
- Bet tracking and approval workflow

**Specific Tasks:**

44. **Anomaly reasoning agent** (Day 53-55)
    - `agents/anomaly_reasoner.py`: `AnomalyReasonerAgent(BaseAgent)`
    - System prompt (`agents/prompts/anomaly_system.md`):
      - "You analyze anomalies in betting signals. When odds or predictions seem unusual, you investigate possible causes: injuries, lineup changes, weather, team news, historical patterns. You provide reasoning about whether a signal should be trusted or dismissed."
    - Triggers:
      - EV > 10% (unusually high -- could be trap or genuine value)
      - Odds moved > 15% from opening
      - Model disagreement (Poisson vs Dixon-Coles differ by > 10%)
      - Player prop line significantly different from rolling average
    - Tools available: all DB tools + web search for team news (optional, can start without)
    - Output: structured assessment: `{trust_signal: bool, reasoning: str, confidence: float, suggested_action: str}`
    - **Agent responsibility**: System Architect (Agent 2), Backend Builder (Agent 3)
    - **Acceptance criteria**: Anomaly agent produces coherent reasoning for test cases; correctly identifies suspicious signals in synthetic scenarios

45. **CLI implementation** (Day 55-58)
    - `cli/app.py`: main Typer app with subcommands
    - `cli/commands/ingest.py`:
      - `ev ingest run` -> run all ingestion jobs now
      - `ev ingest status` -> show last ingestion times, record counts
      - `ev ingest backfill --league EPL --from 2024-03-01` -> historical backfill
    - `cli/commands/scan.py`:
      - `ev scan` -> run EV scan for today's fixtures
      - `ev scan --league EPL` -> scan specific league
      - `ev scan --fixture-id X` -> scan specific fixture
      - Output: Rich table with columns: Fixture, Market, Selection, Bookmaker, Odds, Model Prob, EV%, Confidence, Suggested Stake
    - `cli/commands/bet.py`:
      - `ev bet approve <signal_id>` -> mark signal as approved, record bet
      - `ev bet reject <signal_id>` -> dismiss signal with reason
      - `ev bet result <bet_id> --outcome win|loss|void` -> record outcome
      - `ev bet list --status pending|approved|settled` -> list bets
      - `ev bet history --days 30` -> bet history with P&L
    - `cli/commands/backtest.py`:
      - `ev backtest run --market goals_ou --from 2024-03-01` -> run backtest
      - `ev backtest report` -> show latest backtest results
    - `cli/commands/model.py`:
      - `ev model train --type poisson` -> train specific model
      - `ev model evaluate --type poisson` -> show model metrics
      - `ev model list` -> show all model versions
    - `cli/commands/bankroll.py`:
      - `ev bankroll status` -> current bankroll, drawdown, exposure
      - `ev bankroll set <amount>` -> set initial bankroll
      - `ev bankroll history` -> bankroll trajectory
    - `cli/commands/entity.py`:
      - `ev entity unresolved` -> show unmatched entities
      - `ev entity resolve <id> --canonical <name>` -> manually resolve
      - `ev entity aliases <team_name>` -> show known aliases
    - `cli/commands/dashboard.py`:
      - `ev dashboard` -> launch NiceGUI web dashboard on port 8080
    - `cli/formatters.py`: Rich panels, tables, progress bars, color-coded EV values (green > 5%, yellow 3-5%)
    - **Agent responsibility**: Backend Builder (Agent 3), Documentation & Delivery (Agent 10)
    - **Acceptance criteria**: All commands execute without error; output is formatted and readable; tab-completion works via Typer

#### Week 12: Web Dashboard and Integration Testing

**Deliverables:**
- NiceGUI web dashboard with all pages
- End-to-end integration tests
- System health monitoring

**Specific Tasks:**

46. **Web dashboard** (Day 59-63)
    - `dashboard/app.py`: NiceGUI app with dark theme, sidebar navigation
    - `dashboard/pages/overview.py`:
      - Bankroll card (current, peak, drawdown %)
      - Today's P&L card
      - Active signals count
      - Daily exposure gauge
      - Equity curve chart (ECharts line chart)
      - Recent bets table (last 10)
    - `dashboard/pages/signals.py`:
      - Table of current EV signals: fixture, market, selection, bookmaker, odds, EV%, confidence
      - Approve/Reject buttons per signal
      - Filter by league, market, minimum EV
      - Auto-refresh every 60 seconds
    - `dashboard/pages/history.py`:
      - Bet history table with pagination
      - Cumulative P&L chart
      - ROI by market type bar chart
      - ROI by league bar chart
      - Monthly summary table
    - `dashboard/pages/models.py`:
      - Model performance table: model type, version, Brier score, log-loss, last trained
      - Calibration plot per model
      - Drift detection status
      - Retrain button
    - `dashboard/pages/ingestion.py`:
      - Data freshness indicators per API source
      - Record counts per table
      - Entity resolution stats (resolved %, unresolved count)
      - Ingestion log (last 50 entries)
    - `dashboard/pages/settings.py`:
      - League toggles (enable/disable per league)
      - Risk parameter adjustment (EV threshold, Kelly fraction, max stake)
      - Bookmaker toggles
      - API health check buttons
    - **Agent responsibility**: Backend Builder (Agent 3), Documentation & Delivery (Agent 10)
    - **Acceptance criteria**: All pages render; data refreshes; approve/reject workflow works; dashboard accessible on LAN

47. **End-to-end integration tests** (Day 63-65)
    - `tests/integration/test_ev_pipeline_end_to_end.py`:
      - Test full pipeline: ingest fixture -> resolve entities -> compute features -> run models -> calculate EV -> apply risk -> generate signal
      - Use recorded API responses (not live)
      - Verify signal output is correct and consistent
    - `tests/integration/test_ingestion_pipeline.py`:
      - Test each API client with saved JSON fixtures
      - Verify raw data stored correctly
      - Verify entity resolution produces linked records
    - **Agent responsibility**: QA & Testing (Agent 8)
    - **Acceptance criteria**: End-to-end test passes; pipeline produces expected signals from known test data

---

### PHASE 6: Live Operation

**Deliverables:**
- System running on VPS with small stakes
- Monitoring and alerting
- Gradual scale-up plan

**Specific Tasks:**

48. **VPS deployment** (Day 66-68)
    - Set up PostgreSQL on VPS
    - Run Alembic migrations
    - Configure APScheduler for production schedule
    - Set up systemd service for the main application
    - NiceGUI dashboard served via reverse proxy (nginx)
    - Environment variables for all API keys
    - **Agent responsibility**: System Architect (Agent 2), Backend Builder (Agent 3)

49. **Paper trading period** (Day 68-72)
    - Run system for 1 week without real stakes
    - Record all signals, track what would have been bet
    - Verify CLV, Brier score, and signal quality
    - **Acceptance criteria**: System generates signals daily; no crashes; CLV > 0

50. **Small stakes launch** (Day 73+)
    - Start with 5,000 DKK bankroll
    - Quarter-Kelly staking with all risk constraints active
    - Daily review of signals before placing bets manually
    - Weekly model performance review
    - **Go-live criteria check**: Brier < 0.22, ROI > 3% over 500+ bets, drawdown < 15%, CLV > 55%

---

## 3. Database Schema

### Raw Data Tables

**`raw_fixtures`**
| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| source | ENUM('optic_odds', 'the_odds_api', 'sportmonks') | Which API |
| source_fixture_id | VARCHAR(100) | ID from source API |
| raw_json | JSONB | Complete API response |
| fetched_at | TIMESTAMP | When fetched |
| processed | BOOLEAN DEFAULT FALSE | Has been normalized |
| created_at | TIMESTAMP | |

**`raw_odds`**
| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| source | ENUM | Which API |
| source_fixture_id | VARCHAR(100) | |
| source_market | VARCHAR(100) | Market type from API |
| raw_json | JSONB | Complete odds data |
| fetched_at | TIMESTAMP | |
| processed | BOOLEAN DEFAULT FALSE | |
| created_at | TIMESTAMP | |

**`raw_player_stats`**
| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| source | ENUM | |
| source_fixture_id | VARCHAR(100) | |
| source_player_id | VARCHAR(100) | |
| raw_json | JSONB | |
| fetched_at | TIMESTAMP | |
| processed | BOOLEAN DEFAULT FALSE | |
| created_at | TIMESTAMP | |

### Entity Tables

**`leagues`**
| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | Canonical league ID |
| name | VARCHAR(200) | E.g. "English Premier League" |
| country | VARCHAR(100) | |
| optic_odds_id | VARCHAR(100) | Optic Odds identifier |
| the_odds_api_key | VARCHAR(100) | E.g. "soccer_epl" |
| sportmonks_id | INTEGER | SportMonks league ID |
| active | BOOLEAN DEFAULT TRUE | |
| created_at | TIMESTAMP | |

**`teams`**
| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | Canonical team ID |
| name | VARCHAR(200) | Canonical name |
| league_id | UUID FK -> leagues | |
| optic_odds_id | VARCHAR(100) | |
| the_odds_api_name | VARCHAR(200) | Name used by The Odds API |
| sportmonks_id | INTEGER | |
| active | BOOLEAN DEFAULT TRUE | |
| created_at | TIMESTAMP | |

**`players`**
| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| name | VARCHAR(200) | |
| team_id | UUID FK -> teams | Current team |
| position | VARCHAR(50) | GK, DEF, MID, FWD |
| optic_odds_id | VARCHAR(100) | |
| sportmonks_id | INTEGER | |
| active | BOOLEAN DEFAULT TRUE | |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

**`aliases`**
| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| entity_type | ENUM('team', 'player', 'league') | |
| canonical_id | UUID | FK to teams/players/leagues |
| alias_name | VARCHAR(300) | The variant name |
| source | VARCHAR(50) | Which API uses this name |
| confidence | FLOAT | How certain the match is |
| created_at | TIMESTAMP | |
| UNIQUE(entity_type, alias_name, source) | | |

### Match Tables

**`matches`**
| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| league_id | UUID FK -> leagues | |
| home_team_id | UUID FK -> teams | |
| away_team_id | UUID FK -> teams | |
| kickoff_at | TIMESTAMP | |
| status | ENUM('scheduled', 'live', 'finished', 'postponed', 'cancelled') | |
| home_goals | INTEGER NULL | Final score |
| away_goals | INTEGER NULL | |
| optic_odds_fixture_id | VARCHAR(100) | |
| the_odds_api_event_id | VARCHAR(100) | |
| sportmonks_fixture_id | INTEGER | |
| season | VARCHAR(20) | E.g. "2024-25" |
| matchday | INTEGER | |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

**`match_stats`**
| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| match_id | UUID FK -> matches | |
| team_id | UUID FK -> teams | |
| is_home | BOOLEAN | |
| goals | INTEGER | |
| shots | INTEGER | |
| shots_on_target | INTEGER | |
| corners | INTEGER | |
| fouls | INTEGER | |
| yellow_cards | INTEGER | |
| red_cards | INTEGER | |
| possession_pct | FLOAT | |
| passes | INTEGER | |
| pass_accuracy_pct | FLOAT | |
| tackles | INTEGER | |
| interceptions | INTEGER | |
| offsides | INTEGER | |
| xg | FLOAT NULL | Expected goals if available |
| created_at | TIMESTAMP | |

**`player_match_stats`**
| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| match_id | UUID FK -> matches | |
| player_id | UUID FK -> players | |
| team_id | UUID FK -> teams | |
| minutes_played | INTEGER | |
| goals | INTEGER | |
| assists | INTEGER | |
| shots | INTEGER | |
| shots_on_target | INTEGER | |
| key_passes | INTEGER | |
| passes | INTEGER | |
| pass_accuracy_pct | FLOAT | |
| tackles | INTEGER | |
| interceptions | INTEGER | |
| clearances | INTEGER | |
| blocks | INTEGER | |
| dribbles_attempted | INTEGER | |
| dribbles_succeeded | INTEGER | |
| fouls_committed | INTEGER | |
| fouls_drawn | INTEGER | |
| yellow_cards | INTEGER | |
| red_cards | INTEGER | |
| corners_taken | INTEGER | |
| offsides | INTEGER | |
| xg | FLOAT NULL | |
| created_at | TIMESTAMP | |

### Odds Tables

**`odds_snapshots`**
| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| match_id | UUID FK -> matches | |
| bookmaker | VARCHAR(100) | E.g. "bet365_dk" |
| market | VARCHAR(100) | E.g. "goals_over_under" |
| selection | VARCHAR(200) | E.g. "Over 2.5" |
| odds | DECIMAL(8,4) | Decimal odds |
| implied_prob | DECIMAL(6,5) | 1/odds |
| source | ENUM | Which API provided this |
| snapshot_at | TIMESTAMP | When captured |
| is_closing | BOOLEAN DEFAULT FALSE | Is this the closing line |
| created_at | TIMESTAMP | |
| INDEX(match_id, bookmaker, market, selection) | | |

**`odds_movements`**
| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| match_id | UUID FK -> matches | |
| bookmaker | VARCHAR(100) | |
| market | VARCHAR(100) | |
| selection | VARCHAR(200) | |
| opening_odds | DECIMAL(8,4) | |
| closing_odds | DECIMAL(8,4) | |
| movement_pct | DECIMAL(6,4) | |
| created_at | TIMESTAMP | |

### Prediction and Signal Tables

**`feature_vectors`**
| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| match_id | UUID FK -> matches | |
| entity_type | ENUM('team', 'player') | |
| entity_id | UUID | team or player ID |
| feature_version | VARCHAR(20) | |
| features | JSONB | All computed features as key-value |
| computed_at | TIMESTAMP | |
| created_at | TIMESTAMP | |

**`model_predictions`**
| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| match_id | UUID FK -> matches | |
| model_type | VARCHAR(50) | E.g. "poisson", "dixon_coles", "negbin_corners" |
| model_version | VARCHAR(20) | |
| market | VARCHAR(100) | |
| selection | VARCHAR(200) | |
| predicted_prob | DECIMAL(6,5) | |
| predicted_at | TIMESTAMP | |
| actual_outcome | BOOLEAN NULL | Filled after match |
| created_at | TIMESTAMP | |

**`ev_signals`**
| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| match_id | UUID FK -> matches | |
| market | VARCHAR(100) | |
| selection | VARCHAR(200) | |
| bookmaker | VARCHAR(100) | Best-price bookmaker |
| odds_at_signal | DECIMAL(8,4) | Odds when signal generated |
| model_prob | DECIMAL(6,5) | |
| ev_pct | DECIMAL(6,4) | EV as percentage |
| confidence | DECIMAL(4,3) | Model confidence |
| suggested_stake_pct | DECIMAL(6,4) | Quarter-Kelly % |
| suggested_stake_dkk | DECIMAL(10,2) | DKK amount |
| status | ENUM('pending', 'approved', 'rejected', 'expired') | |
| anomaly_flag | BOOLEAN DEFAULT FALSE | Flagged by anomaly agent |
| anomaly_reasoning | TEXT NULL | |
| generated_at | TIMESTAMP | |
| expires_at | TIMESTAMP | Match kickoff time |
| created_at | TIMESTAMP | |

### Betting Tables

**`bets`**
| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| signal_id | UUID FK -> ev_signals | |
| match_id | UUID FK -> matches | |
| market | VARCHAR(100) | |
| selection | VARCHAR(200) | |
| bookmaker | VARCHAR(100) | |
| odds | DECIMAL(8,4) | Actual odds placed at |
| stake_dkk | DECIMAL(10,2) | |
| potential_return_dkk | DECIMAL(10,2) | |
| outcome | ENUM('pending', 'won', 'lost', 'void', 'half_won', 'half_lost') NULL | |
| pnl_dkk | DECIMAL(10,2) NULL | |
| closing_odds | DECIMAL(8,4) NULL | |
| clv_pct | DECIMAL(6,4) NULL | |
| placed_at | TIMESTAMP | |
| settled_at | TIMESTAMP NULL | |
| created_at | TIMESTAMP | |

**`bankroll_snapshots`**
| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| balance_dkk | DECIMAL(12,2) | |
| peak_dkk | DECIMAL(12,2) | |
| drawdown_pct | DECIMAL(6,4) | |
| daily_exposure_pct | DECIMAL(6,4) | |
| total_bets | INTEGER | |
| total_wins | INTEGER | |
| total_losses | INTEGER | |
| roi_pct | DECIMAL(8,4) | |
| brier_score | DECIMAL(6,4) NULL | |
| snapshot_at | TIMESTAMP | |
| created_at | TIMESTAMP | |

### System Tables

**`model_runs`**
| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| model_type | VARCHAR(50) | |
| model_version | VARCHAR(20) | |
| training_data_cutoff | DATE | |
| training_samples | INTEGER | |
| brier_score | DECIMAL(6,4) | |
| log_loss | DECIMAL(8,4) | |
| auc_roc | DECIMAL(6,4) NULL | |
| calibration_error | DECIMAL(6,4) | |
| file_path | VARCHAR(500) | Serialized model location |
| active | BOOLEAN DEFAULT FALSE | Currently active model |
| trained_at | TIMESTAMP | |
| created_at | TIMESTAMP | |

**`ingestion_logs`**
| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| source | VARCHAR(50) | |
| endpoint | VARCHAR(200) | |
| status_code | INTEGER | |
| records_fetched | INTEGER | |
| duration_ms | INTEGER | |
| error_message | TEXT NULL | |
| credits_used | INTEGER NULL | For The Odds API |
| credits_remaining | INTEGER NULL | |
| fetched_at | TIMESTAMP | |
| created_at | TIMESTAMP | |

**`entity_resolution_logs`**
| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| entity_type | VARCHAR(20) | |
| input_name | VARCHAR(300) | |
| source | VARCHAR(50) | |
| resolved_to_id | UUID NULL | |
| resolved_to_name | VARCHAR(200) NULL | |
| method | VARCHAR(50) | exact, alias, normalized, fuzzy |
| confidence | DECIMAL(4,3) | |
| manual_override | BOOLEAN DEFAULT FALSE | |
| created_at | TIMESTAMP | |

---

## 4. API Integration Plan

### Optic Odds API

**Role**: Primary source for real-time and pre-match odds, fixture data, player results, and sportsbook coverage. This is the richest data source with 200+ sportsbooks and sub-second latency.

**Authentication**: `X-Api-Key` header on every request

**Key endpoints used**:
| Endpoint | Purpose | Polling frequency |
|----------|---------|-------------------|
| `GET /fixtures/active` | Discover upcoming matches | Every 6 hours |
| `GET /fixtures/odds` | Pre-match odds from target bookmakers | Every 30 min (24h before kickoff), every 5 min (2h before kickoff) |
| `GET /fixtures/odds/historical` | Historical odds for CLV analysis | On demand |
| `GET /fixtures/results` | Match outcomes | Every hour |
| `GET /fixtures/player-results` | Player stats per match | After match completion |
| `GET /fixtures/player-results/last-x` | Recent player performance | When generating player prop predictions |
| `GET /leagues/active` | League discovery and ID mapping | Daily |
| `GET /sportsbooks/active` | Bookmaker discovery | Daily |
| `GET /markets/active` | Available market types | Daily |
| `GET /teams` | Team roster and ID mapping | Weekly |
| `GET /players` | Player roster and ID mapping | Weekly |

**Sportsbook filtering**: Filter requests to target bookmakers (Bet365, Unibet, Danske Spel equivalents) plus Pinnacle as sharp benchmark. Optic Odds covers 200+ sportsbooks so filtering is essential to avoid processing irrelevant data.

**Rate limiting strategy**: Unknown explicit limits. Start conservative (1 req/sec), monitor for 429 responses, adjust. Implement exponential backoff.

### The Odds API

**Role**: Secondary odds source. Particularly valuable for EU region bookmakers, structured market coverage (BTTS, corners, cards as first-class markets), and credit-based billing that makes cost predictable.

**Authentication**: `apiKey` query parameter

**Key endpoints used**:
| Endpoint | Purpose | Credits | Polling frequency |
|----------|---------|---------|-------------------|
| `GET /v4/sports/` | Verify league availability | 0 | Daily |
| `GET /v4/sports/{sport}/events` | Event discovery without odds | 0 | Every 6 hours |
| `GET /v4/sports/{sport}/odds/` | Odds for all events in league | 1 per region per market | Every 30 min |
| `GET /v4/sports/{sport}/events/{id}/odds` | Single event, all markets | 1 per market per region | On demand |
| `GET /v4/sports/{sport}/events/{id}/markets` | Available markets for event | 1 | On demand |
| `GET /v4/sports/{sport}/scores/` | Live scores and results | 1-2 | Every hour |
| `GET /v4/historical/sports/{sport}/odds` | Historical odds snapshots | 10 per region per market | For backtesting only |

**Sport keys**: `soccer_epl`, `soccer_spain_la_liga`, `soccer_italy_serie_a`, `soccer_germany_bundesliga`, `soccer_france_ligue_one`, `soccer_denmark_superliga`, `soccer_sweden_allsvenskan`, `soccer_norway_eliteserien`

**Markets to request**: `h2h`, `h2h_3_way`, `totals`, `btts`, `team_totals`, `alternate_totals`, `alternate_totals_corners`, `alternate_totals_cards`, `alternate_team_totals`, `draw_no_bet`, `alternate_spreads`, `alternate_spreads_corners`

**Region**: Always `eu` to get European bookmaker odds

**Credit budget**: Recommend the 100K plan ($59/month). Budget allocation:
- 8 leagues x 4 market groups x 48 scans/day (every 30 min) = ~1,536 credits/day for ongoing odds
- Scores: 8 leagues x 24 checks/day = ~192 credits/day
- Buffer for single-event drilldowns: ~500 credits/day
- Total ~2,200 credits/day = ~66,000/month, well within 100K

**Danish bookmaker gap**: The Odds API does not have dedicated Danish bookmakers (no Bet365 DK, Unibet DK, Danske Spel). Mitigation: Use `eu` region which includes Unibet (EU), Bet365 (EU variant). For Danske Spel specifically, rely on Optic Odds. If Optic Odds also lacks Danske Spel, consider scraping Danske Spel odds manually or accepting that only Bet365 and Unibet are covered.

### SportMonks API

**Role**: Historical data provider. Primary source for backtesting: detailed player/team statistics, fixture data from past seasons, xG data.

**Authentication**: `Authorization` header with API token

**Key endpoints used**:
| Endpoint | Purpose | When |
|----------|---------|------|
| `GET /fixtures/date-range` | Historical fixtures with stats | Initial backfill, then weekly |
| `GET /fixtures/{id}` (with includes) | Detailed fixture with lineups, events, statistics | Per fixture during backfill |
| `GET /statistics/season` | Season-long player/team stats | Season start, then weekly |
| `GET /standings/season/{id}` | League standings for strength calculations | Weekly |
| `GET /teams/season/{season_id}` | Team rosters per season | Season start |
| `GET /players/{id}` | Player details | On demand |
| `GET /topscorers/season/{id}` | Top scorers for validation | Weekly |
| `GET /leagues` | League ID mapping | One-time |
| `GET /seasons` | Season ID mapping | One-time |

**Key includes** (nested data in single request): `statistics`, `lineups`, `events`, `scores`, `venue`, `referee`

**Pagination**: Cursor-based. Implement auto-pagination to traverse all pages.

**Historical coverage**: Data from March 2024 onward (as stated in spec). Need to identify SportMonks season IDs for:
- EPL 2023-24 (partial), 2024-25, 2025-26
- La Liga 2023-24 (partial), 2024-25, 2025-26
- Same pattern for all 8 leagues

**Rate limits**: Varies by plan. Standard plan typically 3,000 requests/hour. Backfill should be rate-limited to 1 request/second to stay well within limits.

### Cross-API Data Flow

```
SportMonks (Historical)  ─────────────┐
  - Fixtures from March 2024          │
  - Player/team statistics            ├── Entity Resolution ──> Canonical DB
  - Season standings                  │      (team/player/league matching)
                                      │
Optic Odds (Real-time)  ──────────────┤
  - Live/upcoming fixtures            │
  - Real-time odds (200+ books)       │
  - Player results                    │
                                      │
The Odds API (Structured odds) ───────┘
  - EU region odds
  - BTTS, corners, cards markets
  - Historical odds snapshots
```

---

## 5. Architecture Decisions

### Dashboard Framework: NiceGUI

**Decision**: Use **NiceGUI** for the web dashboard.

**Rationale**:
- Pure Python -- no separate frontend codebase, reducing complexity for a single developer
- Built on FastAPI -- can serve REST endpoints for CLI integration too
- Reactive data binding -- dashboard auto-updates when underlying data changes
- ECharts integration for rich charting (equity curves, calibration plots, P&L)
- Dark theme support out of the box
- Timer-based auto-refresh for real-time signal updates
- Deployable standalone or behind nginx on VPS
- Lightweight enough for a single-server deployment

**Alternatives considered**:
- Streamlit: simpler but lacks real-time updates, re-runs entire script on interaction, poor for persistent state
- Dash/Plotly: heavier, steeper learning curve, more suited for data science dashboards than operational systems
- React frontend: maximum flexibility but requires full-stack development, overkill for this use case

### Message Passing Between Agents: In-Process Async Queues

**Decision**: Use `asyncio.Queue` for agent-to-agent communication, wrapped in a `MessageBus` abstraction.

**Rationale**:
- Only 2 runtime agents (orchestrator + anomaly reasoner) -- no need for distributed messaging
- Single-process deployment on VPS -- no need for Redis/RabbitMQ overhead
- Async queues integrate naturally with httpx async clients and SQLAlchemy async sessions
- If scaling needed later, the `MessageBus` abstraction can be swapped for Redis pub/sub without changing agent code

**Message flow**:
1. Orchestrator runs scheduled scan
2. If anomalous signals detected, Orchestrator publishes `ANALYZE_SIGNAL` message to Anomaly Reasoner
3. Anomaly Reasoner processes and publishes `SIGNAL_ASSESSMENT` back
4. Orchestrator incorporates assessment into final recommendation

### Scheduling Approach: APScheduler with SQLAlchemy Job Store

**Decision**: Use **APScheduler** (AsyncIOScheduler) with job persistence in the same database.

**Rationale**:
- Cron-like scheduling for periodic ingestion (every 30 min, every 6 hours)
- Date-based scheduling for one-time events (closing odds capture 5 min before specific kickoff)
- Job persistence survives process restarts
- No external scheduler dependency (no systemd timers, no cron, no Celery)
- Integrates with async event loop

**Job schedule**:
| Job | Schedule | Description |
|-----|----------|-------------|
| `ingest_fixtures` | Every 6 hours | Fetch upcoming fixtures from all APIs |
| `ingest_prematch_odds` | Every 30 min, 8:00-23:00 CET | Fetch odds for matches within 24h |
| `ingest_closing_odds` | 5 min before each kickoff | Final odds snapshot |
| `ingest_results` | Every hour | Fetch completed match results |
| `ingest_player_stats` | After results ingestion | Fetch player stats for completed matches |
| `run_feature_pipeline` | After player stats ingestion | Compute features for new matches |
| `run_ev_scan` | Every 30 min, 8:00-23:00 CET | Generate EV signals |
| `snapshot_bankroll` | Daily at 23:59 CET | Record daily bankroll state |
| `check_model_drift` | Weekly, Sunday 06:00 CET | Run drift detection |

### Application Entry Point

**Decision**: Single async Python process managing all concerns.

The application runs as one process with:
- APScheduler running ingestion and scanning jobs
- Claude agents invoked on-demand within scanning jobs
- NiceGUI dashboard served via embedded FastAPI
- CLI as a separate entry point (same codebase, direct function calls)

```
main.py (or `ev dashboard` command)
  ├── APScheduler (background jobs)
  ├── NiceGUI (web dashboard on :8080)
  └── Claude agents (invoked by scheduler/CLI)
```

For VPS deployment: `systemd` service running `python -m cli.app dashboard` (or a dedicated `main.py`), with nginx reverse proxy for HTTPS.

---

## 6. Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          EXTERNAL DATA SOURCES                         │
│                                                                         │
│  ┌──────────────┐   ┌───────────────┐   ┌──────────────────┐           │
│  │  Optic Odds   │   │ The Odds API  │   │   SportMonks     │           │
│  │  - Fixtures   │   │ - Odds (EU)   │   │ - Historical     │           │
│  │  - Odds (200+)│   │ - BTTS/Corners│   │ - Player stats   │           │
│  │  - Player res.│   │ - Scores      │   │ - Team stats     │           │
│  │  - Results    │   │ - Events      │   │ - Standings      │           │
│  └──────┬───────┘   └──────┬────────┘   └────────┬─────────┘           │
└─────────┼──────────────────┼─────────────────────┼─────────────────────┘
          │                  │                     │
          ▼                  ▼                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 1: INGESTION                                                     │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  APScheduler triggers  →  API Clients (httpx async)             │    │
│  │  → Rate limiting, retry, error handling                         │    │
│  │  → Store raw JSON to raw_fixtures, raw_odds, raw_player_stats   │    │
│  │  → Log to ingestion_logs                                        │    │
│  └─────────────────────────────────┬───────────────────────────────┘    │
└────────────────────────────────────┼───────────────────────────────────-┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 2: ENTITY RESOLUTION & NORMALIZATION                             │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  EntityResolver processes raw records:                          │    │
│  │  1. Extract team/player/league names from raw JSON              │    │
│  │  2. Resolve via cascade: exact → alias → normalized → fuzzy     │    │
│  │  3. Create/link to canonical entities (teams, players, leagues) │    │
│  │  4. Create matched records (matches, player_match_stats)        │    │
│  │  5. Store odds_snapshots with canonical match_id                │    │
│  │  6. Log unresolved entities for manual review                   │    │
│  └─────────────────────────────────┬───────────────────────────────┘    │
└────────────────────────────────────┼───────────────────────────────────-┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 3: FEATURE ENGINEERING                                           │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  FeaturePipeline processes normalized data:                     │    │
│  │  1. Per-90 normalization of player stats                        │    │
│  │  2. Rolling windows (3, 5, 10 match) for players and teams     │    │
│  │  3. Opponent strength adjustments                               │    │
│  │  4. Consistency scoring (CV calculation)                        │    │
│  │  5. Store feature_vectors in DB                                 │    │
│  │  6. Drift detection against reference distributions             │    │
│  └─────────────────────────────────┬───────────────────────────────┘    │
└────────────────────────────────────┼───────────────────────────────────-┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 4: STATISTICAL MODELING                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  Models generate probability estimates:                         │    │
│  │                                                                 │    │
│  │  ┌──────────┐ ┌─────────────┐ ┌──────────┐ ┌───────┐          │    │
│  │  │ Poisson  │ │ Dixon-Coles │ │ NegBin   │ │ BTTS  │          │    │
│  │  │ (goals)  │ │ (goals+)    │ │ (corners,│ │ (log  │          │    │
│  │  │          │ │             │ │  props)  │ │  reg) │          │    │
│  │  └────┬─────┘ └──────┬──────┘ └────┬─────┘ └──┬────┘          │    │
│  │       └──────────┬────┴─────────────┴──────────┘               │    │
│  │                  ▼                                              │    │
│  │         ModelEnsemble + Calibration                             │    │
│  │                  │                                              │    │
│  │                  ▼                                              │    │
│  │         model_predictions table                                 │    │
│  └─────────────────────────────────┬───────────────────────────────┘    │
└────────────────────────────────────┼───────────────────────────────────-┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 5: EV ENGINE                                                     │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  SignalGenerator for each upcoming match:                       │    │
│  │  1. OddsComparer finds best price across bookmakers             │    │
│  │  2. EVCalculator: EV = (model_prob × best_odds) - 1             │    │
│  │  3. Filters: odds range [1.50-4.00], EV >= 3%, confidence      │    │
│  │  4. Generate EVSignal objects                                   │    │
│  │  5. If anomalous → send to Anomaly Reasoner agent              │    │
│  │  6. Store to ev_signals table                                   │    │
│  └─────────────────────────────────┬───────────────────────────────┘    │
└────────────────────────────────────┼───────────────────────────────────-┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 6: RISK MANAGEMENT                                               │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  PositionSizer applies all constraints to each signal:          │    │
│  │  1. Quarter-Kelly stake calculation                             │    │
│  │  2. Cap at 3% bankroll                                          │    │
│  │  3. Check daily exposure < 10%                                  │    │
│  │  4. Check fixture exposure < 5%                                 │    │
│  │  5. Check stop-loss conditions                                  │    │
│  │  6. Final stake amount in DKK                                   │    │
│  └─────────────────────────────────┬───────────────────────────────┘    │
└────────────────────────────────────┼───────────────────────────────────-┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 7: PRESENTATION & USER INTERACTION                               │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  ┌──────────────┐    ┌─────────────────────────────────────┐   │    │
│  │  │  CLI (Typer)  │    │  Web Dashboard (NiceGUI :8080)      │   │    │
│  │  │  - ev scan    │    │  - Overview (bankroll, P&L)         │   │    │
│  │  │  - ev bet     │    │  - Signals (approve/reject)         │   │    │
│  │  │  - ev bankroll│    │  - History (charts)                 │   │    │
│  │  │  - ev backtest│    │  - Models (metrics)                 │   │    │
│  │  └──────────────┘    └─────────────────────────────────────┘   │    │
│  │                                                                 │    │
│  │  User reviews signals → approves → places bet manually          │    │
│  │  User records outcome → system calculates P&L, CLV              │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 8: FEEDBACK LOOP                                                 │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  After match settlement:                                        │    │
│  │  1. Record actual outcome in model_predictions                  │    │
│  │  2. Update bankroll_snapshots                                   │    │
│  │  3. Calculate CLV (signal odds vs closing odds)                 │    │
│  │  4. Update model evaluation metrics                             │    │
│  │  5. Check if model retraining needed (weekly or on drift)       │    │
│  │  6. Feed results back into feature pipeline                     │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Risks and Edge Cases

### Data Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **Danish bookmaker coverage gap**: The Odds API has no dedicated Danish books (Bet365 DK, Unibet DK, Danske Spel). Optic Odds may also lack some. | Cannot compare odds from user's actual bookmakers | HIGH | 1. Map EU variants (Bet365 EU, Unibet EU) as proxies -- odds are typically identical or within 1-2%. 2. On first API access, enumerate Optic Odds sportsbooks and check for Danish-specific entries. 3. If Danske Spel truly unavailable, restrict to Bet365 and Unibet only. 4. Consider adding Danske Spel odds manually via CLI. |
| **API rate limits unknown for Optic Odds** | Could get blocked during high-frequency polling | MEDIUM | Start at 1 req/sec. Log all 429 responses. Implement adaptive rate limiting that backs off automatically. Cache responses for 60 seconds to avoid redundant calls. |
| **The Odds API credit exhaustion** | No more odds data for remainder of month | MEDIUM | Implement credit tracking via response headers. Alert at 80% usage. Degrade gracefully: reduce polling frequency, prioritize leagues with upcoming matches. Budget 100K plan carefully. |
| **SportMonks data gaps**: Historical data may have missing stats for some leagues/players | Incomplete training data | MEDIUM | Implement null handling in feature pipeline. Exclude matches with < 50% stat coverage. Log coverage statistics per league to identify weak spots early. |
| **Entity resolution failures**: New teams (promoted), name changes, or transliteration issues | Orphaned odds/stats data | HIGH | Robust fuzzy matching + manual resolution queue. Alert on unresolved entities > 24 hours. Seed comprehensive alias data at project start. Regular audits of entity_resolution_logs. |

### Modeling Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **Overfitting on small sample**: Some markets (e.g., Scandinavian leagues) may have limited historical data | Overconfident predictions | HIGH | Hierarchical models: pool data across leagues with league-specific adjustments. Require minimum 100 training samples per league. Walk-forward validation to detect overfit. |
| **Model calibration drift**: Market efficiency changes, team personnel changes, tactical shifts | Degraded prediction accuracy | MEDIUM | Weekly drift detection (PSI, KS). Automatic retraining trigger. Rolling training window discards stale data. Monthly calibration refresh. |
| **Dixon-Coles convergence failure**: MLE optimization may not converge for all parameter sets | Model unavailable | LOW | Fall back to basic Poisson if Dixon-Coles fails to converge. Multiple initialization attempts with different starting parameters. Regularization. |
| **Player prop data sparsity**: Substitute players, injured players, newly transferred players have thin data | Poor player prop predictions | HIGH | Require minimum 5 appearances in rolling window. Use position-level priors for new players. Flag low-confidence predictions. |

### Operational Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **Odds change between signal and bet placement**: User sees signal, but by the time they manually place the bet, odds have moved | Bet placed at worse odds, negative EV | HIGH | Show "odds staleness" indicator in dashboard. Re-check odds before approval. Include "minimum acceptable odds" on each signal -- if current odds drop below this, signal auto-expires. |
| **System downtime during critical pre-match window** | Missed signals | MEDIUM | Systemd auto-restart. Health check endpoint. Alert via email/Telegram if scheduler misses a job. |
| **Claude API downtime or rate limits** | Orchestrator/anomaly agent unavailable | LOW | System operates without Claude agents (just no anomaly reasoning). All core logic (EV calculation, risk management) is pure Python, not LLM-dependent. |
| **Bankroll management error**: Bug in Kelly calculation, exposure tracking, or stop-loss | Overbetting, potential large losses | MEDIUM | Extensive unit tests for all risk calculations. Hard-coded maximum absolute stake (e.g., 750 DKK regardless of Kelly output). Paper trading period to validate. |
| **Time zone issues**: Kickoff times in different zones, DST transitions, UTC vs CET confusion | Missed closing odds, incorrect scheduling | MEDIUM | Store all times in UTC in database. Convert to CET only for display. Use `zoneinfo` (Python 3.9+) for conversions. Test around DST transition dates. |

### Edge Cases to Handle

1. **Postponed/cancelled matches**: Signal generated but match postponed -> auto-expire signal, void any pending bets
2. **Walkover results**: Match awarded 3-0 without playing -> handle as void for statistical purposes, settle bets per bookmaker rules
3. **Extra time / penalty shootout**: For pre-match bets, only regular time counts (90 min) -> ensure results ingestion uses regular-time-only scores
4. **Player substituted at halftime**: 45 minutes played affects per-90 calculations and O/U settlement -> track exact minutes
5. **Own goals**: Count for team goal totals but NOT for player goalscorer markets -> handle in results processing
6. **Market suspension**: Bookmaker suspends market (injury news) -> odds disappear from API -> handle null odds gracefully, expire related signals
7. **Half-result bets (Asian handicap)**: Half-win/half-loss outcomes -> stake split, P&L calculation must handle correctly
8. **Negative Kelly**: Model probability below implied probability -> zero stake, but still worth logging the prediction for calibration tracking

---

## 8. Testing Strategy

### Phase 1-2: Data Infrastructure Testing

**Unit Tests:**
- `test_base_client.py`: Retry logic with mocked 429/500 responses (using `respx`), rate limiting behavior, timeout handling, authentication header injection
- `test_optic_odds_client.py`: Each method returns correct Pydantic model from saved JSON fixtures, parameter serialization, error response handling
- `test_the_odds_api_client.py`: Credit tracking from response headers, sport key validation, region parameter handling
- `test_sportmonks_client.py`: Pagination behavior (auto-follow next page), includes parameter handling, date range validation
- `test_entity_resolution.py`: All matcher types (exact, alias, normalized, fuzzy) with known test pairs. Must include: diacritics (Malmo FF vs Malmoe FF), prefix variations (FC Barcelona vs Barcelona), abbreviations (Man Utd vs Manchester United), Scandinavian names (Brondby IF vs Brondbyx IF)
- `test_mappers.py`: Raw JSON -> SQLAlchemy model conversion for every entity type

**Integration Tests:**
- `test_ingestion_pipeline.py`: Full pipeline from saved API response JSON -> raw table storage -> entity resolution -> normalized table storage. Uses in-memory SQLite.
- `test_cross_source_linking.py`: Given fixture data from all 3 APIs, verify that the same real-world match is linked correctly across sources

**Test Data:**
- Save real API responses as JSON fixtures in `tests/fixtures/`. Capture responses for at least:
  - 1 full matchday of EPL (10 fixtures) from each API
  - 1 full matchday of Danish Superliga from each API
  - Historical data for 1 month from SportMonks
- Use `factory-boy` to generate randomized entity data for edge case testing

**Acceptance Criteria:**
- All API clients pass with saved fixtures
- Entity resolution achieves > 95% accuracy on test set of 100 known team name pairs
- No raw data lost between API response and database storage
- Ingestion logs correctly record all API calls

### Phase 3: Statistical Modeling Testing

**Unit Tests:**
- `test_poisson.py`: Verify Poisson PMF calculation against scipy.stats.poisson. Test that goal probability distribution sums to ~1.0 (within floating point). Test with known team parameters that the model reproduces expected goal rates.
- `test_negative_binomial.py`: Verify overdispersion detection (variance > mean). Test NegBin PMF against scipy. Test that corners model produces different distributions than Poisson for same mean.
- `test_dixon_coles.py`: Verify bivariate correction adjusts 0-0 and 1-1 probabilities. Verify home advantage parameter is positive. Test convergence with synthetic data where ground truth is known.
- `test_btts.py`: Verify BTTS probability derivation from score matrix matches logistic regression output within tolerance.
- `test_calibration.py`: Given perfectly calibrated predictions, verify Platt scaling does not distort. Given miscalibrated predictions, verify post-calibration ECE improves.
- `test_evaluation.py`: Brier score computation against hand-calculated examples. Log-loss against known values.

**Validation Tests (not unit tests, but systematic checks):**
- For each model, run on holdout data and verify:
  - Brier score within expected range
  - Calibration plot slope between 0.8 and 1.2
  - No extreme probability outputs (all between 0.01 and 0.99)
- Compare model predictions against bookmaker implied probabilities -- should correlate but not be identical

**Acceptance Criteria:**
- All statistical calculations verified against reference implementations (scipy)
- Holdout evaluation meets minimum thresholds before proceeding to Phase 4
- Model registry correctly stores and retrieves model versions

### Phase 4: EV Engine and Risk Testing

**Unit Tests:**
- `test_ev_calculator.py`: EV = (0.55 * 2.00) - 1 = 0.10 (10%). Test with edge cases: prob=1.0, prob=0.0, odds=1.0. Verify threshold filtering.
- `test_kelly.py`: Full Kelly = (0.55 * 2.00 - 1) / (2.00 - 1) = 0.10. Quarter Kelly = 0.025. Test negative edge (no bet). Test very high edge (capped).
- `test_exposure.py`: Daily exposure accumulates correctly across multiple fixtures. Fixture exposure tracked per-fixture. Limits enforced.
- `test_stops.py`: Daily loss of 5.1% triggers stop. Drawdown of 20.1% from peak triggers stop. Edge: exactly 5.0% does NOT trigger (strictly greater than).
- `test_odds_comparison.py`: Best price correctly identified from 3 bookmakers. Market margin calculated correctly.
- `test_filters.py`: Odds outside [1.50, 4.00] rejected. EV below 3% rejected. Low confidence rejected.

**Integration Tests:**
- `test_ev_pipeline_end_to_end.py`: Given a fixture with known features and known odds, verify the complete pipeline produces the expected signal with correct EV, stake, and bookmaker.
- `test_backtest_no_future_leakage.py`: Run walk-forward backtest and verify that for every prediction, the training data cutoff is strictly before the prediction date.

**Acceptance Criteria:**
- All risk limits enforced simultaneously (a bet must pass ALL constraints)
- Walk-forward backtest produces results for 500+ bets
- Kelly calculation mathematically verified
- No future leakage in backtesting (verified by date assertions)

### Phase 5: Agent and Integration Testing

**Unit Tests:**
- `test_base_agent.py`: Agent correctly constructs Claude API call with tools. Agent handles tool_use response and executes tool. Agent handles errors in tool execution.
- `test_orchestrator.py`: Given mock DB state with upcoming fixtures and pre-computed signals, orchestrator produces summary with recommendations.
- `test_anomaly_reasoner.py`: Given signal with EV > 10%, anomaly reasoner identifies it as suspicious and provides reasoning.
- `test_message_bus.py`: Messages delivered to subscribed agents. Unsubscribed agents do not receive messages.

**Integration Tests:**
- Full system integration test: Start with empty DB -> run ingestion (from saved fixtures) -> run entity resolution -> compute features -> train models -> run EV scan -> generate signals -> apply risk -> verify dashboard shows signals
- CLI command tests: each CLI command produces expected output format

**Acceptance Criteria:**
- Full pipeline runs end-to-end without human intervention
- Dashboard renders all pages without errors
- CLI commands all functional
- Agents produce coherent outputs

### Phase 6: Live Validation Testing

**Paper Trading Tests:**
- Run system for 7 days without real stakes
- Record all signals and compare against actual outcomes
- Verify: CLV > 0 on average, Brier score trending toward < 0.22, no system crashes
- Manual review of 100% of signals during paper trading

**Go-Live Validation:**
- After each week of live operation, compute rolling metrics
- Alert if any go-live criterion regresses:
  - Brier Score > 0.25 (warning), > 0.30 (halt)
  - ROI < 0% over 100 bets (investigate)
  - Drawdown > 15% (reduce stakes by half)
  - CLV < 50% (model may not be finding value)

---

### Critical Files for Implementation

- `C:\Users\chrni\Desktop\multi-agent-ev\config\settings.py` - Central configuration hub using pydantic-settings; all API keys, thresholds, and risk parameters flow from here into every other module
- `C:\Users\chrni\Desktop\multi-agent-ev\ingestion\base_client.py` - Foundation for all three API clients; retry logic, rate limiting, and error handling patterns established here propagate to Optic Odds, The Odds API, and SportMonks clients
- `C:\Users\chrni\Desktop\multi-agent-ev\entity_resolution\resolver.py` - The most architecturally critical module: if entity resolution fails, odds from different APIs cannot be matched to the same fixture, breaking the entire EV pipeline
- `C:\Users\chrni\Desktop\multi-agent-ev\models\dixon_coles.py` - The most mathematically complex model (MLE optimization of bivariate Poisson with time decay); getting this right determines prediction quality for all goal-based markets
- `C:\Users\chrni\Desktop\multi-agent-ev\ev_engine\signal_generator.py` - The orchestration point where model predictions meet odds data and risk constraints; this is where value bets are actually identified and represents the core business logic of the platform
