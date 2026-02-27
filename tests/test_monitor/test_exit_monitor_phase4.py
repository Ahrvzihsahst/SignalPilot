"""Tests for Phase 4 exit monitor enhancements."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from signalpilot.db.models import ExitAlert, ExitType, TickData, TradeRecord
from signalpilot.monitor.exit_monitor import ExitMonitor, TrailingStopConfig
from signalpilot.utils.constants import IST


def _make_trade(trade_id=1, entry=100.0, sl=95.0, t1=110.0, t2=115.0):
    return TradeRecord(
        id=trade_id, signal_id=1, symbol="SBIN", entry_price=entry,
        stop_loss=sl, target_1=t1, target_2=t2, quantity=15,
        taken_at=datetime.now(IST), strategy="Gap & Go",
    )


def _make_tick(symbol="SBIN", ltp=100.0):
    now = datetime.now(IST)
    return TickData(
        symbol=symbol, ltp=ltp, open_price=100.0, high=ltp + 1,
        low=ltp - 1, close=99.0, volume=1000000,
        last_traded_timestamp=now, updated_at=now,
    )


class TestSLApproachingAlert:
    async def test_sl_approaching_alert_fires(self):
        """Price within 0.5% of SL triggers sl_approaching alert."""
        alerts = []
        async def capture(alert):
            alerts.append(alert)

        get_tick = AsyncMock(return_value=_make_tick(ltp=95.3))  # ~0.3% above SL of 95.0
        monitor = ExitMonitor(get_tick=get_tick, alert_callback=capture)

        trade = _make_trade(sl=95.0)
        monitor.start_monitoring(trade)

        result = await monitor.check_trade(trade)
        assert result is not None
        assert result.keyboard_type == "sl_approaching"
        assert result.is_alert_only is True

    async def test_sl_approaching_cooldown(self):
        """No repeat SL-approaching alert within 60s."""
        alerts = []
        async def capture(alert):
            alerts.append(alert)

        get_tick = AsyncMock(return_value=_make_tick(ltp=95.3))
        monitor = ExitMonitor(get_tick=get_tick, alert_callback=capture)

        trade = _make_trade(sl=95.0)
        monitor.start_monitoring(trade)

        # First alert should fire
        result1 = await monitor.check_trade(trade)
        assert result1 is not None
        assert result1.keyboard_type == "sl_approaching"

        # Second check immediately should NOT fire (cooldown)
        result2 = await monitor.check_trade(trade)
        assert result2 is None


class TestNearT2Alert:
    async def test_near_t2_alert_fires(self):
        """Price within 0.3% of T2 triggers near_t2 alert."""
        alerts = []
        async def capture(alert):
            alerts.append(alert)

        # T2 = 115.0, 0.3% below = 114.655. Set price to 114.8 (~0.17% from T2)
        get_tick = AsyncMock(return_value=_make_tick(ltp=114.8))
        monitor = ExitMonitor(get_tick=get_tick, alert_callback=capture)

        trade = _make_trade(t1=110.0, t2=115.0)
        monitor.start_monitoring(trade)
        # Need to mark T1 as already alerted so it doesn't interfere
        state = monitor._active_states[trade.id]
        state.t1_alerted = True

        result = await monitor.check_trade(trade)
        assert result is not None
        assert result.keyboard_type == "near_t2"
        assert result.is_alert_only is True

    async def test_near_t2_alert_one_shot(self):
        """Near-T2 alert is only sent once."""
        alerts = []
        async def capture(alert):
            alerts.append(alert)

        get_tick = AsyncMock(return_value=_make_tick(ltp=114.8))
        monitor = ExitMonitor(get_tick=get_tick, alert_callback=capture)

        trade = _make_trade(t1=110.0, t2=115.0)
        monitor.start_monitoring(trade)
        state = monitor._active_states[trade.id]
        state.t1_alerted = True

        result1 = await monitor.check_trade(trade)
        assert result1 is not None
        assert result1.keyboard_type == "near_t2"

        result2 = await monitor.check_trade(trade)
        # Should return None (no trailing update, no other alerts)
        assert result2 is None


class TestKeyboardTypeOnAlerts:
    async def test_t1_alert_has_keyboard_type(self):
        """T1 hit alert has keyboard_type='t1'."""
        alerts = []
        async def capture(alert):
            alerts.append(alert)

        get_tick = AsyncMock(return_value=_make_tick(ltp=110.5))
        monitor = ExitMonitor(get_tick=get_tick, alert_callback=capture)

        trade = _make_trade(t1=110.0, t2=115.0)
        monitor.start_monitoring(trade)

        result = await monitor.check_trade(trade)
        assert result is not None
        assert result.exit_type == ExitType.T1_HIT
        assert result.keyboard_type == "t1"

    async def test_t2_alert_has_keyboard_type(self):
        """T2 hit alert has keyboard_type='t2'."""
        alerts = []
        async def capture(alert):
            alerts.append(alert)

        get_tick = AsyncMock(return_value=_make_tick(ltp=115.5))
        monitor = ExitMonitor(get_tick=get_tick, alert_callback=capture, close_trade=AsyncMock())

        trade = _make_trade(t1=110.0, t2=115.0)
        monitor.start_monitoring(trade)

        result = await monitor.check_trade(trade)
        assert result is not None
        assert result.exit_type == ExitType.T2_HIT
        assert result.keyboard_type == "t2"
