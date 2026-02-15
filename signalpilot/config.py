"""Application configuration loaded from environment variables."""

from pydantic import Field
from pydantic_settings import BaseSettings


class AppConfig(BaseSettings):
    """Application configuration loaded from .env file and environment variables."""

    # Angel One SmartAPI
    angel_api_key: str = Field(..., description="Angel One SmartAPI API key")
    angel_client_id: str = Field(..., description="Angel One client ID")
    angel_mpin: str = Field(..., description="Angel One MPIN")
    angel_totp_secret: str = Field(..., description="TOTP secret key (32 chars)")

    # Telegram
    telegram_bot_token: str = Field(..., description="Telegram Bot API token")
    telegram_chat_id: str = Field(..., description="Telegram chat ID for delivery")

    # Database
    db_path: str = Field(default="signalpilot.db", description="SQLite database path")

    # Instrument data
    nifty500_csv_path: str = Field(
        default="data/nifty500_list.csv",
        description="Path to Nifty 500 constituent CSV",
    )

    # Risk management defaults
    default_capital: float = Field(default=50000.0, description="Default trading capital (INR)")
    default_max_positions: int = Field(default=5, description="Max simultaneous positions")

    # Strategy parameters
    gap_min_pct: float = Field(default=3.0, description="Minimum gap % for Gap & Go")
    gap_max_pct: float = Field(default=5.0, description="Maximum gap % for Gap & Go")
    volume_threshold_pct: float = Field(
        default=50.0,
        description="15-min volume must exceed this % of 20-day ADV",
    )
    target_1_pct: float = Field(default=5.0, description="Target 1 as % from entry")
    target_2_pct: float = Field(default=7.0, description="Target 2 as % from entry")
    max_risk_pct: float = Field(default=3.0, description="Max stop loss risk % from entry")
    signal_expiry_minutes: int = Field(default=30, description="Signal expiry in minutes")

    # Scoring weights
    scoring_gap_weight: float = Field(default=0.40)
    scoring_volume_weight: float = Field(default=0.35)
    scoring_price_distance_weight: float = Field(default=0.25)

    # Trailing stop loss
    trailing_sl_breakeven_trigger_pct: float = Field(default=2.0)
    trailing_sl_trail_trigger_pct: float = Field(default=4.0)
    trailing_sl_trail_distance_pct: float = Field(default=2.0)

    # Retry / resilience
    auth_max_retries: int = Field(default=3)
    ws_max_reconnect_attempts: int = Field(default=3)
    historical_api_rate_limit: int = Field(default=3, description="Requests per second")
    max_crashes_per_session: int = Field(default=3)

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }
