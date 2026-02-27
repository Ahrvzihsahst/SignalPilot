"""Tests for application configuration."""

import pytest
from pydantic import ValidationError

from signalpilot.config import AppConfig


class TestAppConfig:
    def test_loads_with_all_required_fields(self, required_env):
        """Verify config loads when all required env vars are set."""
        config = AppConfig(_env_file=None)

        assert config.angel_api_key == "test_key"
        assert config.angel_client_id == "test_client"
        assert config.angel_mpin == "1234"
        assert config.angel_totp_secret == "JBSWY3DPEHPK3PXP"
        assert config.telegram_bot_token == "123456:ABC-DEF"
        assert config.telegram_chat_id == "987654321"

    def test_defaults_are_sensible(self, required_env):
        """Verify default values for optional fields."""
        config = AppConfig(_env_file=None)

        # Database
        assert config.db_path == "signalpilot.db"

        # Instrument data
        assert config.nifty500_csv_path == "data/nifty500_list.csv"

        # Risk management
        assert config.default_capital == 50000.0
        assert config.default_max_positions == 8

        # Strategy parameters
        assert config.gap_min_pct == 3.0
        assert config.gap_max_pct == 5.0
        assert config.volume_threshold_pct == 50.0
        assert config.target_1_pct == 5.0
        assert config.target_2_pct == 7.0
        assert config.max_risk_pct == 3.0
        assert config.signal_expiry_minutes == 30

        # Scoring weights
        assert config.scoring_gap_weight == 0.40
        assert config.scoring_volume_weight == 0.35
        assert config.scoring_price_distance_weight == 0.25

        # Trailing SL
        assert config.trailing_sl_breakeven_trigger_pct == 2.0
        assert config.trailing_sl_trail_trigger_pct == 4.0
        assert config.trailing_sl_trail_distance_pct == 2.0

        # Retry / resilience
        assert config.auth_max_retries == 3
        assert config.ws_max_reconnect_attempts == 3
        assert config.historical_api_rate_limit == 3
        assert config.max_crashes_per_session == 3

    def test_missing_required_fields_raises_validation_error(self, monkeypatch):
        """Verify that missing required env vars cause a validation error."""
        for key in [
            "ANGEL_API_KEY", "ANGEL_CLIENT_ID", "ANGEL_MPIN",
            "ANGEL_TOTP_SECRET", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
        ]:
            monkeypatch.delenv(key, raising=False)

        with pytest.raises(ValidationError):
            AppConfig(_env_file=None)

    def test_overrides_defaults_from_env(self, required_env, monkeypatch):
        """Verify optional fields can be overridden via env vars."""
        monkeypatch.setenv("DEFAULT_CAPITAL", "100000")
        monkeypatch.setenv("GAP_MIN_PCT", "2.5")
        monkeypatch.setenv("SIGNAL_EXPIRY_MINUTES", "15")

        config = AppConfig(_env_file=None)

        assert config.default_capital == 100000.0
        assert config.gap_min_pct == 2.5
        assert config.signal_expiry_minutes == 15

    def test_phase3_defaults(self, required_env):
        """Verify Phase 3 default values load correctly."""
        config = AppConfig(_env_file=None)

        # Composite scoring
        assert config.composite_weight_strategy == 0.4
        assert config.composite_weight_win_rate == 0.3
        assert config.composite_weight_risk_reward == 0.2
        assert config.composite_weight_confirmation == 0.1

        # Confirmation
        assert config.confirmation_window_minutes == 15

        # Circuit breaker
        assert config.circuit_breaker_sl_limit == 3

        # Adaptive
        assert config.adaptive_consecutive_loss_throttle == 3
        assert config.adaptive_consecutive_loss_pause == 5
        assert config.adaptive_5d_warn_threshold == 35.0
        assert config.adaptive_10d_pause_threshold == 30.0

        # Confirmed caps
        assert config.confirmed_double_cap_pct == 20.0
        assert config.confirmed_triple_cap_pct == 25.0

        # Dashboard
        assert config.dashboard_enabled is True
        assert config.dashboard_port == 8000
        assert config.dashboard_host == "127.0.0.1"

    def test_composite_weights_must_sum_to_one(self, required_env, monkeypatch):
        """Verify invalid composite weight sums raise ValidationError."""
        monkeypatch.setenv("COMPOSITE_WEIGHT_STRATEGY", "0.5")
        monkeypatch.setenv("COMPOSITE_WEIGHT_WIN_RATE", "0.5")
        # Sum = 0.5+0.5+0.2+0.1 = 1.3
        with pytest.raises(ValidationError, match="Composite scoring weights"):
            AppConfig(_env_file=None)

    def test_phase3_env_overrides(self, required_env, monkeypatch):
        """Verify Phase 3 fields can be overridden via env vars."""
        monkeypatch.setenv("CIRCUIT_BREAKER_SL_LIMIT", "5")
        monkeypatch.setenv("DASHBOARD_PORT", "9000")
        monkeypatch.setenv("CONFIRMATION_WINDOW_MINUTES", "10")

        config = AppConfig(_env_file=None)

        assert config.circuit_breaker_sl_limit == 5
        assert config.dashboard_port == 9000
        assert config.confirmation_window_minutes == 10
