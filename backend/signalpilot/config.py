"""Application configuration loaded from environment variables."""

from pydantic import Field, model_validator
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

    # Logging
    log_level: str = Field(default="INFO", description="Log level (DEBUG, INFO, WARNING, ERROR)")
    log_file: str = Field(default="log/signalpilot.log", description="Path to the rotating log file")

    # Database
    db_path: str = Field(default="signalpilot.db", description="SQLite database path")

    # Instrument data
    nifty500_csv_path: str = Field(
        default="data/nifty500_list.csv",
        description="Path to Nifty 500 constituent CSV",
    )

    # Risk management defaults
    default_capital: float = Field(default=50000.0, description="Default trading capital (INR)")
    default_max_positions: int = Field(default=8, description="Max simultaneous positions")

    # Strategy parameters (Gap & Go)
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

    # Gap & Go scoring weights
    scoring_gap_weight: float = Field(default=0.40)
    scoring_volume_weight: float = Field(default=0.35)
    scoring_price_distance_weight: float = Field(default=0.25)

    # Trailing stop loss (Gap & Go defaults)
    trailing_sl_breakeven_trigger_pct: float = Field(default=2.0)
    trailing_sl_trail_trigger_pct: float = Field(default=4.0)
    trailing_sl_trail_distance_pct: float = Field(default=2.0)

    # ORB strategy parameters
    orb_range_min_pct: float = Field(default=0.5, description="Min opening range size %")
    orb_range_max_pct: float = Field(default=3.0, description="Max opening range size %")
    orb_volume_multiplier: float = Field(default=1.5, description="Volume multiplier for ORB breakout")
    orb_signal_window_end: str = Field(default="11:00", description="ORB signal window end time")
    orb_target_1_pct: float = Field(default=1.5, description="ORB Target 1 %")
    orb_target_2_pct: float = Field(default=2.5, description="ORB Target 2 %")
    orb_breakeven_trigger_pct: float = Field(default=1.5, description="ORB breakeven trigger %")
    orb_trail_trigger_pct: float = Field(default=2.0, description="ORB trailing trigger %")
    orb_trail_distance_pct: float = Field(default=1.0, description="ORB trailing distance %")
    orb_gap_exclusion_pct: float = Field(default=3.0, description="Exclude stocks gapping >= this %")

    # ORB scoring weights
    orb_scoring_volume_weight: float = Field(default=0.40)
    orb_scoring_range_weight: float = Field(default=0.30)
    orb_scoring_distance_weight: float = Field(default=0.30)

    # VWAP strategy parameters
    vwap_scan_start: str = Field(default="10:00", description="VWAP scan start time")
    vwap_scan_end: str = Field(default="14:30", description="VWAP scan end time")
    vwap_touch_threshold_pct: float = Field(default=0.3, description="VWAP touch threshold %")
    vwap_reclaim_volume_multiplier: float = Field(default=1.5, description="VWAP reclaim volume multiplier")
    vwap_pullback_volume_multiplier: float = Field(default=1.0, description="VWAP pullback volume multiplier")
    vwap_max_signals_per_stock: int = Field(default=2, description="Max VWAP signals per stock per day")
    vwap_cooldown_minutes: int = Field(default=60, description="VWAP cooldown between signals (minutes)")
    vwap_setup1_sl_below_vwap_pct: float = Field(default=0.5, description="Setup 1 SL below VWAP %")
    vwap_setup1_target1_pct: float = Field(default=1.0, description="Setup 1 Target 1 %")
    vwap_setup1_target2_pct: float = Field(default=1.5, description="Setup 1 Target 2 %")
    vwap_setup2_target1_pct: float = Field(default=1.5, description="Setup 2 Target 1 %")
    vwap_setup2_target2_pct: float = Field(default=2.0, description="Setup 2 Target 2 %")
    vwap_setup1_breakeven_trigger_pct: float = Field(default=1.0, description="Setup 1 breakeven trigger %")
    vwap_setup2_breakeven_trigger_pct: float = Field(default=1.5, description="Setup 2 breakeven trigger %")

    # VWAP scoring weights
    vwap_scoring_volume_weight: float = Field(default=0.35)
    vwap_scoring_touch_weight: float = Field(default=0.35)
    vwap_scoring_trend_weight: float = Field(default=0.30)

    # Paper trading mode
    orb_paper_mode: bool = Field(default=True, description="ORB paper trading mode")
    vwap_paper_mode: bool = Field(default=True, description="VWAP paper trading mode")

    # Retry / resilience
    auth_max_retries: int = Field(default=3)
    ws_max_reconnect_attempts: int = Field(default=3)
    historical_api_rate_limit: int = Field(default=3, description="Requests per second")
    max_crashes_per_session: int = Field(default=3)

    # Phase 3: Composite scoring weights
    composite_weight_strategy: float = Field(default=0.4, description="Composite scoring: strategy strength weight")
    composite_weight_win_rate: float = Field(default=0.3, description="Composite scoring: win rate weight")
    composite_weight_risk_reward: float = Field(default=0.2, description="Composite scoring: risk-reward weight")
    composite_weight_confirmation: float = Field(default=0.1, description="Composite scoring: confirmation bonus weight")

    # Phase 3: Confirmation
    confirmation_window_minutes: int = Field(default=15, description="Multi-strategy confirmation window (minutes)")

    # Phase 3: Circuit breaker
    circuit_breaker_sl_limit: int = Field(default=3, description="Daily SL hits before circuit breaker activates")

    # Phase 3: Adaptive learning
    adaptive_consecutive_loss_throttle: int = Field(default=3, description="Consecutive losses before throttling")
    adaptive_consecutive_loss_pause: int = Field(default=5, description="Consecutive losses before pausing")
    adaptive_5d_warn_threshold: float = Field(default=35.0, description="5-day win rate warning threshold %")
    adaptive_10d_pause_threshold: float = Field(default=30.0, description="10-day win rate auto-pause threshold %")

    # Phase 3: Confirmed signal caps
    confirmed_double_cap_pct: float = Field(default=20.0, description="Max position % for double-confirmed signals")
    confirmed_triple_cap_pct: float = Field(default=25.0, description="Max position % for triple-confirmed signals")

    # Phase 3: Dashboard
    dashboard_enabled: bool = Field(default=True, description="Enable FastAPI dashboard")
    dashboard_port: int = Field(default=9000, description="Dashboard port")
    dashboard_host: str = Field(default="127.0.0.1", description="Dashboard host")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }

    @model_validator(mode="after")
    def _validate_scoring_weights(self) -> "AppConfig":
        """Validate that all scoring weight groups sum to 1.0."""
        tolerance = 0.01
        gap_go_sum = self.scoring_gap_weight + self.scoring_volume_weight + self.scoring_price_distance_weight
        if abs(gap_go_sum - 1.0) > tolerance:
            raise ValueError(
                f"Gap & Go scoring weights must sum to 1.0, got {gap_go_sum:.3f}"
            )
        orb_sum = self.orb_scoring_volume_weight + self.orb_scoring_range_weight + self.orb_scoring_distance_weight
        if abs(orb_sum - 1.0) > tolerance:
            raise ValueError(
                f"ORB scoring weights must sum to 1.0, got {orb_sum:.3f}"
            )
        vwap_sum = self.vwap_scoring_volume_weight + self.vwap_scoring_touch_weight + self.vwap_scoring_trend_weight
        if abs(vwap_sum - 1.0) > tolerance:
            raise ValueError(
                f"VWAP scoring weights must sum to 1.0, got {vwap_sum:.3f}"
            )
        composite_sum = (
            self.composite_weight_strategy + self.composite_weight_win_rate
            + self.composite_weight_risk_reward + self.composite_weight_confirmation
        )
        if abs(composite_sum - 1.0) > tolerance:
            raise ValueError(
                f"Composite scoring weights must sum to 1.0, got {composite_sum:.3f}"
            )
        return self
