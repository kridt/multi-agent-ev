from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # API Keys
    optic_odds_api_key: str = ""
    the_odds_api_key: str = ""
    sportmonks_api_key: str = ""
    anthropic_api_key: str = ""

    # Database
    database_url: str = "sqlite+aiosqlite:///./ev_system.db"

    # Bankroll
    bankroll_dkk: float = 10000.0

    # Risk Parameters
    min_ev_threshold: float = 0.03
    max_stake_pct: float = 0.03
    max_daily_exposure_pct: float = 0.10
    max_fixture_exposure_pct: float = 0.05
    kelly_fraction: float = 0.25
    min_odds: float = 1.50
    max_odds: float = 4.00
    daily_stop_loss_pct: float = 0.05
    max_drawdown_pct: float = 0.20

    # Logging
    log_level: str = "INFO"


settings = Settings()
