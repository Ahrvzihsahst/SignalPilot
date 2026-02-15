"""Tests for market calendar utilities."""

from datetime import date, datetime

import pytest

from signalpilot.utils.constants import IST
from signalpilot.utils.market_calendar import (
    StrategyPhase,
    get_current_phase,
    is_market_hours,
    is_trading_day,
)


class TestIsTradingDay:
    def test_weekday_is_trading_day(self):
        # Monday 2026-02-16
        assert is_trading_day(date(2026, 2, 16)) is True

    def test_friday_is_trading_day(self):
        assert is_trading_day(date(2026, 2, 20)) is True

    def test_saturday_is_not_trading_day(self):
        assert is_trading_day(date(2026, 2, 14)) is False

    def test_sunday_is_not_trading_day(self):
        assert is_trading_day(date(2026, 2, 15)) is False

    def test_republic_day_is_not_trading_day(self):
        assert is_trading_day(date(2026, 1, 26)) is False

    def test_diwali_is_not_trading_day(self):
        assert is_trading_day(date(2026, 11, 9)) is False

    def test_independence_day_is_not_trading_day(self):
        assert is_trading_day(date(2026, 8, 15)) is False

    def test_christmas_is_not_trading_day(self):
        assert is_trading_day(date(2026, 12, 25)) is False

    def test_regular_weekday_not_in_holidays(self):
        assert is_trading_day(date(2026, 6, 2)) is True

    def test_unsupported_year_weekday_raises_value_error(self):
        # 2025-03-17 is a Monday
        with pytest.raises(ValueError, match="No NSE holiday data for year 2025"):
            is_trading_day(date(2025, 3, 17))

    def test_weekend_returns_false_even_for_unsupported_year(self):
        # Weekends don't need holiday data -- checked before year lookup
        assert is_trading_day(date(2025, 3, 15)) is False  # Saturday

    def test_unsupported_future_year_raises(self):
        with pytest.raises(ValueError, match="No NSE holiday data for year 2027"):
            is_trading_day(date(2027, 3, 17))  # Wednesday


class TestIsMarketHours:
    def test_before_market_open(self):
        dt = datetime(2026, 2, 16, 9, 0, tzinfo=IST)
        assert is_market_hours(dt) is False

    def test_at_market_open(self):
        dt = datetime(2026, 2, 16, 9, 15, tzinfo=IST)
        assert is_market_hours(dt) is True

    def test_during_market_hours(self):
        dt = datetime(2026, 2, 16, 12, 0, tzinfo=IST)
        assert is_market_hours(dt) is True

    def test_at_market_close(self):
        dt = datetime(2026, 2, 16, 15, 30, tzinfo=IST)
        assert is_market_hours(dt) is False

    def test_after_market_close(self):
        dt = datetime(2026, 2, 16, 16, 0, tzinfo=IST)
        assert is_market_hours(dt) is False

    def test_just_before_close(self):
        dt = datetime(2026, 2, 16, 15, 29, 59, tzinfo=IST)
        assert is_market_hours(dt) is True

    def test_naive_datetime_treated_as_ist(self):
        dt = datetime(2026, 2, 16, 12, 0)
        assert is_market_hours(dt) is True


class TestGetCurrentPhase:
    def test_pre_market(self):
        dt = datetime(2026, 2, 16, 8, 0, tzinfo=IST)
        assert get_current_phase(dt) == StrategyPhase.PRE_MARKET

    def test_pre_market_at_850(self):
        dt = datetime(2026, 2, 16, 8, 50, tzinfo=IST)
        assert get_current_phase(dt) == StrategyPhase.PRE_MARKET

    def test_opening_at_915(self):
        dt = datetime(2026, 2, 16, 9, 15, tzinfo=IST)
        assert get_current_phase(dt) == StrategyPhase.OPENING

    def test_opening_at_929(self):
        dt = datetime(2026, 2, 16, 9, 29, tzinfo=IST)
        assert get_current_phase(dt) == StrategyPhase.OPENING

    def test_entry_window_at_930(self):
        dt = datetime(2026, 2, 16, 9, 30, tzinfo=IST)
        assert get_current_phase(dt) == StrategyPhase.ENTRY_WINDOW

    def test_entry_window_at_944(self):
        dt = datetime(2026, 2, 16, 9, 44, tzinfo=IST)
        assert get_current_phase(dt) == StrategyPhase.ENTRY_WINDOW

    def test_continuous_at_945(self):
        dt = datetime(2026, 2, 16, 9, 45, tzinfo=IST)
        assert get_current_phase(dt) == StrategyPhase.CONTINUOUS

    def test_continuous_at_noon(self):
        dt = datetime(2026, 2, 16, 12, 0, tzinfo=IST)
        assert get_current_phase(dt) == StrategyPhase.CONTINUOUS

    def test_continuous_at_1429(self):
        dt = datetime(2026, 2, 16, 14, 29, tzinfo=IST)
        assert get_current_phase(dt) == StrategyPhase.CONTINUOUS

    def test_wind_down_at_1430(self):
        dt = datetime(2026, 2, 16, 14, 30, tzinfo=IST)
        assert get_current_phase(dt) == StrategyPhase.WIND_DOWN

    def test_wind_down_at_1500(self):
        dt = datetime(2026, 2, 16, 15, 0, tzinfo=IST)
        assert get_current_phase(dt) == StrategyPhase.WIND_DOWN

    def test_wind_down_at_1529(self):
        dt = datetime(2026, 2, 16, 15, 29, tzinfo=IST)
        assert get_current_phase(dt) == StrategyPhase.WIND_DOWN

    def test_post_market_at_1530(self):
        dt = datetime(2026, 2, 16, 15, 30, tzinfo=IST)
        assert get_current_phase(dt) == StrategyPhase.POST_MARKET

    def test_post_market_at_1600(self):
        dt = datetime(2026, 2, 16, 16, 0, tzinfo=IST)
        assert get_current_phase(dt) == StrategyPhase.POST_MARKET

    def test_naive_datetime_treated_as_ist(self):
        dt = datetime(2026, 2, 16, 12, 0)
        assert get_current_phase(dt) == StrategyPhase.CONTINUOUS
