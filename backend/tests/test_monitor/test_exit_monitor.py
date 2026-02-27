"""Tests for ExitMonitor."""

from datetime import datetime

import pytest

from signalpilot.db.models import ExitAlert, ExitType, TickData, TradeRecord
from signalpilot.monitor.exit_monitor import (
    DEFAULT_TRAILING_CONFIGS,
    ExitMonitor,
    TrailingStopConfig,
    TrailingStopState,
)
from signalpilot.utils.constants import IST


def _make_trade(
    trade_id: int = 1,
    symbol: str = "SBIN",
    entry_price: float = 100.0,
    stop_loss: float = 97.0,
    target_1: float = 105.0,
    target_2: float = 107.0,
    quantity: int = 10,
) -> TradeRecord:
    return TradeRecord(
        id=trade_id,
        signal_id=1,
        symbol=symbol,
        entry_price=entry_price,
        stop_loss=stop_loss,
        target_1=target_1,
        target_2=target_2,
        quantity=quantity,
        taken_at=datetime(2025, 1, 6, 9, 35, 0, tzinfo=IST),
    )


def _make_tick(symbol: str = "SBIN", ltp: float = 100.0) -> TickData:
    now = datetime.now(IST)
    return TickData(
        symbol=symbol,
        ltp=ltp,
        open_price=100.0,
        high=ltp,
        low=ltp,
        close=99.0,
        volume=10000,
        last_traded_timestamp=now,
        updated_at=now,
    )


class MockAlertSink:
    """Collects alerts sent by ExitMonitor."""

    def __init__(self) -> None:
        self.alerts: list[ExitAlert] = []

    async def __call__(self, alert: ExitAlert) -> None:
        self.alerts.append(alert)


def _build_monitor(
    tick: TickData | None = None,
) -> tuple[ExitMonitor, MockAlertSink]:
    """Create an ExitMonitor with a mock tick source and alert sink."""
    alert_sink = MockAlertSink()

    async def get_tick(symbol: str) -> TickData | None:
        if tick is not None and tick.symbol == symbol:
            return tick
        return None

    monitor = ExitMonitor(get_tick=get_tick, alert_callback=alert_sink)
    return monitor, alert_sink


def _build_monitor_with_price_sequence(
    symbol: str,
    prices: list[float],
) -> tuple[ExitMonitor, MockAlertSink]:
    """Create an ExitMonitor that returns successive prices on each call."""
    alert_sink = MockAlertSink()
    price_iter = iter(prices)

    async def get_tick(sym: str) -> TickData | None:
        if sym != symbol:
            return None
        try:
            price = next(price_iter)
        except StopIteration:
            return None
        return _make_tick(sym, price)

    monitor = ExitMonitor(get_tick=get_tick, alert_callback=alert_sink)
    return monitor, alert_sink


# ── TrailingStopState dataclass ────────────────────────────────


def test_trailing_stop_state_defaults() -> None:
    state = TrailingStopState(
        trade_id=1, original_sl=97.0, current_sl=97.0, highest_price=100.0
    )
    assert state.breakeven_triggered is False
    assert state.trailing_active is False
    assert state.t1_alerted is False


# ── start_monitoring / stop_monitoring ─────────────────────────


def test_start_monitoring_initializes_state() -> None:
    monitor, _ = _build_monitor()
    trade = _make_trade()

    monitor.start_monitoring(trade)

    assert trade.id in monitor._active_states
    state = monitor._active_states[trade.id]
    assert state.original_sl == 97.0
    assert state.current_sl == 97.0
    assert state.highest_price == 100.0


def test_stop_monitoring_removes_state() -> None:
    monitor, _ = _build_monitor()
    trade = _make_trade()
    monitor.start_monitoring(trade)

    monitor.stop_monitoring(trade.id)

    assert trade.id not in monitor._active_states


def test_stop_monitoring_nonexistent_is_noop() -> None:
    monitor, _ = _build_monitor()
    monitor.stop_monitoring(999)  # Should not raise


# ── SL hit ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sl_hit_triggers_exit() -> None:
    """Entry=100, SL=97, price drops to 97 -> exit with SL_HIT."""
    trade = _make_trade(entry_price=100.0, stop_loss=97.0)
    tick = _make_tick(ltp=97.0)
    monitor, alerts = _build_monitor(tick)
    monitor.start_monitoring(trade)

    result = await monitor.check_trade(trade)

    assert result is not None
    assert result.exit_type == ExitType.SL_HIT
    assert result.is_alert_only is False
    assert result.current_price == 97.0
    assert result.pnl_pct == pytest.approx(-3.0)
    assert len(alerts.alerts) == 1
    # Trade should be removed from monitoring
    assert trade.id not in monitor._active_states


@pytest.mark.asyncio
async def test_sl_hit_below_sl() -> None:
    """Price drops below SL -> still triggers exit."""
    trade = _make_trade(entry_price=100.0, stop_loss=97.0)
    tick = _make_tick(ltp=95.0)
    monitor, alerts = _build_monitor(tick)
    monitor.start_monitoring(trade)

    result = await monitor.check_trade(trade)

    assert result is not None
    assert result.exit_type == ExitType.SL_HIT
    assert result.current_price == 95.0


# ── T1 hit ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_t1_hit_sends_advisory() -> None:
    """Entry=100, T1=105, price reaches 105 -> advisory alert, trade stays open."""
    trade = _make_trade(entry_price=100.0, target_1=105.0)
    tick = _make_tick(ltp=105.0)
    monitor, alerts = _build_monitor(tick)
    monitor.start_monitoring(trade)

    result = await monitor.check_trade(trade)

    assert result is not None
    assert result.exit_type == ExitType.T1_HIT
    assert result.is_alert_only is True
    assert result.pnl_pct == pytest.approx(5.0)
    # Trade should still be monitored
    assert trade.id in monitor._active_states


@pytest.mark.asyncio
async def test_t1_alert_fires_only_once() -> None:
    """Price oscillates around T1 -> only one advisory alert."""
    # Use high targets so trailing SL logic doesn't interfere
    trade = _make_trade(entry_price=100.0, target_1=101.0, target_2=107.0)
    monitor, alerts = _build_monitor_with_price_sequence(
        "SBIN", [101.0, 100.5, 101.5]
    )
    monitor.start_monitoring(trade)

    # First check: T1 hit at 101
    r1 = await monitor.check_trade(trade)
    assert r1 is not None
    assert r1.exit_type == ExitType.T1_HIT

    # Second check: price dips to 100.5, no alert
    r2 = await monitor.check_trade(trade)
    assert r2 is None

    # Third check: price back above T1 at 101.5, no duplicate alert
    r3 = await monitor.check_trade(trade)
    assert r3 is None

    assert len(alerts.alerts) == 1


# ── T2 hit ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_t2_hit_triggers_exit() -> None:
    """Entry=100, T2=107, price reaches 107 -> full exit."""
    trade = _make_trade(entry_price=100.0, target_2=107.0)
    tick = _make_tick(ltp=107.0)
    monitor, alerts = _build_monitor(tick)
    monitor.start_monitoring(trade)

    result = await monitor.check_trade(trade)

    assert result is not None
    assert result.exit_type == ExitType.T2_HIT
    assert result.is_alert_only is False
    assert result.pnl_pct == pytest.approx(7.0)
    assert trade.id not in monitor._active_states


# ── Trailing SL: breakeven at +2% ─────────────────────────────


@pytest.mark.asyncio
async def test_trailing_sl_breakeven_at_2pct() -> None:
    """Entry=100, price reaches 102 -> SL moves to 100 (breakeven)."""
    trade = _make_trade(entry_price=100.0, stop_loss=97.0)
    tick = _make_tick(ltp=102.0)
    monitor, alerts = _build_monitor(tick)
    monitor.start_monitoring(trade)

    result = await monitor.check_trade(trade)

    # Should send trailing SL update alert
    assert result is not None
    assert result.is_alert_only is True
    assert result.trailing_sl_update == pytest.approx(100.0)
    # State should reflect breakeven
    state = monitor._active_states[trade.id]
    assert state.breakeven_triggered is True
    assert state.current_sl == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_breakeven_fires_only_once() -> None:
    """Breakeven alert fires only once, even if price stays at +2%."""
    trade = _make_trade(entry_price=100.0, stop_loss=97.0)
    monitor, alerts = _build_monitor_with_price_sequence(
        "SBIN", [102.0, 102.5]
    )
    monitor.start_monitoring(trade)

    r1 = await monitor.check_trade(trade)
    assert r1 is not None
    assert r1.trailing_sl_update == pytest.approx(100.0)

    r2 = await monitor.check_trade(trade)
    # At 102.5, still +2.5% but breakeven already triggered, and not yet +4%
    assert r2 is None

    assert len(alerts.alerts) == 1


# ── Trailing SL: trail at +4% ─────────────────────────────────


@pytest.mark.asyncio
async def test_trailing_sl_at_4pct() -> None:
    """Entry=100, price reaches 104 -> trailing SL at 101.92 (104*0.98)."""
    trade = _make_trade(entry_price=100.0, stop_loss=97.0)
    tick = _make_tick(ltp=104.0)
    monitor, alerts = _build_monitor(tick)
    monitor.start_monitoring(trade)

    result = await monitor.check_trade(trade)

    assert result is not None
    assert result.is_alert_only is True
    assert result.trailing_sl_update == pytest.approx(104.0 * 0.98)
    state = monitor._active_states[trade.id]
    assert state.trailing_active is True
    assert state.current_sl == pytest.approx(101.92)


@pytest.mark.asyncio
async def test_trail_moves_up() -> None:
    """Price 104 -> 106: trailing SL moves from 101.92 to 103.88."""
    trade = _make_trade(entry_price=100.0, stop_loss=97.0)
    monitor, alerts = _build_monitor_with_price_sequence(
        "SBIN", [104.0, 106.0]
    )
    monitor.start_monitoring(trade)

    # First tick: 104 -> trailing SL = 101.92
    await monitor.check_trade(trade)
    assert monitor._active_states[trade.id].current_sl == pytest.approx(101.92)

    # Second tick: 106 -> trailing SL = 103.88
    await monitor.check_trade(trade)
    assert monitor._active_states[trade.id].current_sl == pytest.approx(103.88)


@pytest.mark.asyncio
async def test_trail_never_moves_down() -> None:
    """Price 106 -> 104: trailing SL stays at 103.88, doesn't decrease."""
    trade = _make_trade(entry_price=100.0, stop_loss=97.0)
    monitor, alerts = _build_monitor_with_price_sequence(
        "SBIN", [106.0, 104.0]
    )
    monitor.start_monitoring(trade)

    # First tick: 106 -> trailing SL = 103.88
    await monitor.check_trade(trade)
    sl_after_106 = monitor._active_states[trade.id].current_sl
    assert sl_after_106 == pytest.approx(103.88)

    # Second tick: 104 -> move_pct=4%, new_sl = 104*0.98 = 101.92 < 103.88
    # Trailing SL should NOT move down
    await monitor.check_trade(trade)
    assert monitor._active_states[trade.id].current_sl == pytest.approx(103.88)


@pytest.mark.asyncio
async def test_trailing_sl_hit_triggers_exit() -> None:
    """Price drops to trailing SL -> exit with TRAILING_SL_HIT."""
    trade = _make_trade(entry_price=100.0, stop_loss=97.0)
    monitor, alerts = _build_monitor_with_price_sequence(
        "SBIN", [106.0, 103.88]  # First sets trail, then hits it
    )
    monitor.start_monitoring(trade)

    # Set up trailing SL at 103.88
    await monitor.check_trade(trade)
    assert monitor._active_states[trade.id].current_sl == pytest.approx(103.88)

    # Price drops to trailing SL
    result = await monitor.check_trade(trade)
    assert result is not None
    assert result.exit_type == ExitType.TRAILING_SL_HIT
    assert result.is_alert_only is False
    assert trade.id not in monitor._active_states


# ── No tick data ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_tick_data_returns_none() -> None:
    """If no tick data available, check_trade returns None."""
    trade = _make_trade()
    monitor, alerts = _build_monitor(None)
    monitor.start_monitoring(trade)

    result = await monitor.check_trade(trade)

    assert result is None
    assert len(alerts.alerts) == 0


@pytest.mark.asyncio
async def test_unmonitored_trade_returns_none() -> None:
    """If trade is not being monitored, check_trade returns None."""
    trade = _make_trade()
    tick = _make_tick(ltp=97.0)
    monitor, alerts = _build_monitor(tick)
    # Not calling start_monitoring

    result = await monitor.check_trade(trade)

    assert result is None


# ── Highest price tracking ─────────────────────────────────────


@pytest.mark.asyncio
async def test_highest_price_tracked() -> None:
    """highest_price should track the maximum price seen."""
    trade = _make_trade(entry_price=100.0, target_1=110.0, target_2=115.0)
    monitor, _ = _build_monitor_with_price_sequence(
        "SBIN", [101.0, 103.0, 101.5]
    )
    monitor.start_monitoring(trade)

    await monitor.check_trade(trade)
    await monitor.check_trade(trade)
    await monitor.check_trade(trade)

    state = monitor._active_states[trade.id]
    assert state.highest_price == pytest.approx(103.0)


# ── Time-based exits ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_time_exit_advisory_3pm() -> None:
    """3:00 PM: send advisory alerts with current P&L for all open trades."""
    trade1 = _make_trade(trade_id=1, symbol="SBIN", entry_price=100.0)
    trade2 = _make_trade(trade_id=2, symbol="RELIANCE", entry_price=200.0)

    alert_sink = MockAlertSink()
    ticks = {"SBIN": _make_tick("SBIN", 103.0), "RELIANCE": _make_tick("RELIANCE", 210.0)}

    async def get_tick(symbol: str) -> TickData | None:
        return ticks.get(symbol)

    monitor = ExitMonitor(get_tick=get_tick, alert_callback=alert_sink)
    monitor.start_monitoring(trade1)
    monitor.start_monitoring(trade2)

    alerts = await monitor.trigger_time_exit(
        [trade1, trade2], is_mandatory=False
    )

    assert len(alerts) == 2
    assert all(a.is_alert_only is True for a in alerts)
    assert alerts[0].pnl_pct == pytest.approx(3.0)
    assert alerts[1].pnl_pct == pytest.approx(5.0)
    # Trades should still be monitored
    assert trade1.id in monitor._active_states
    assert trade2.id in monitor._active_states


@pytest.mark.asyncio
async def test_time_exit_mandatory_315pm() -> None:
    """3:15 PM: mandatory exit for all open trades."""
    trade = _make_trade(trade_id=1, entry_price=100.0)
    tick = _make_tick(ltp=98.0)
    monitor, alert_sink = _build_monitor(tick)
    monitor.start_monitoring(trade)

    alerts = await monitor.trigger_time_exit([trade], is_mandatory=True)

    assert len(alerts) == 1
    assert alerts[0].exit_type == ExitType.TIME_EXIT
    assert alerts[0].is_alert_only is False
    assert alerts[0].pnl_pct == pytest.approx(-2.0)
    # Trade should be removed from monitoring
    assert trade.id not in monitor._active_states


@pytest.mark.asyncio
async def test_time_exit_skips_no_tick() -> None:
    """Time exit skips trades with no tick data."""
    trade = _make_trade()
    monitor, alerts = _build_monitor(None)
    monitor.start_monitoring(trade)

    result = await monitor.trigger_time_exit([trade], is_mandatory=True)

    assert result == []


# ── SL before trailing ────────────────────────────────────────


@pytest.mark.asyncio
async def test_sl_hit_before_any_trailing_update() -> None:
    """SL hit without any trailing update -> ExitType.SL_HIT (not TRAILING_SL)."""
    trade = _make_trade(entry_price=100.0, stop_loss=97.0)
    tick = _make_tick(ltp=96.0)
    monitor, _ = _build_monitor(tick)
    monitor.start_monitoring(trade)

    result = await monitor.check_trade(trade)

    assert result.exit_type == ExitType.SL_HIT


# ── Price exactly at entry after breakeven ────────────────────


@pytest.mark.asyncio
async def test_breakeven_sl_hit_at_entry_price() -> None:
    """After breakeven, price drops to entry -> SL hit at breakeven."""
    trade = _make_trade(entry_price=100.0, stop_loss=97.0)
    monitor, alerts = _build_monitor_with_price_sequence(
        "SBIN", [102.0, 100.0]
    )
    monitor.start_monitoring(trade)

    # Trigger breakeven
    await monitor.check_trade(trade)
    assert monitor._active_states[trade.id].current_sl == pytest.approx(100.0)

    # Price drops to entry -> SL hit
    result = await monitor.check_trade(trade)
    assert result is not None
    assert result.exit_type == ExitType.SL_HIT  # Not trailing since trailing_active is False
    assert result.pnl_pct == pytest.approx(0.0)


# ── Jump past breakeven directly to trailing ──────────────────


@pytest.mark.asyncio
async def test_jump_past_breakeven_to_trailing() -> None:
    """Price jumps from entry directly to +5% — breakeven is implied, trail activates."""
    trade = _make_trade(entry_price=100.0, stop_loss=97.0, target_1=110.0, target_2=115.0)
    tick = _make_tick(ltp=105.0)
    monitor, alerts = _build_monitor(tick)
    monitor.start_monitoring(trade)

    result = await monitor.check_trade(trade)

    assert result is not None
    assert result.trailing_sl_update == pytest.approx(105.0 * 0.98)
    state = monitor._active_states[trade.id]
    assert state.breakeven_triggered is True  # Implied by trail branch
    assert state.trailing_active is True


# ── Custom trailing stop thresholds ───────────────────────────


@pytest.mark.asyncio
async def test_custom_breakeven_threshold() -> None:
    """Custom breakeven trigger at +3% instead of default +2%."""
    trade = _make_trade(entry_price=100.0, stop_loss=97.0)
    alert_sink = MockAlertSink()

    async def get_tick(symbol: str) -> TickData | None:
        return _make_tick(symbol, 102.5)

    monitor = ExitMonitor(
        get_tick=get_tick, alert_callback=alert_sink, breakeven_trigger_pct=3.0,
    )
    monitor.start_monitoring(trade)

    # At +2.5%, should NOT trigger breakeven with custom 3% threshold
    result = await monitor.check_trade(trade)
    assert result is None
    assert monitor._active_states[trade.id].breakeven_triggered is False


# ── Priority: SL checked before T2 ────────────────────────────


@pytest.mark.asyncio
async def test_sl_checked_before_t2() -> None:
    """SL is checked before T2 in the priority order."""
    # Degenerate: SL at 101, T2 at 101. Price = 101 satisfies both.
    # SL uses <=, T2 uses >=. SL check runs first.
    trade = _make_trade(entry_price=100.0, stop_loss=101.0, target_2=101.0)
    tick = _make_tick(ltp=101.0)
    monitor, _ = _build_monitor(tick)
    monitor.start_monitoring(trade)

    result = await monitor.check_trade(trade)

    # SL check (101 <= 101) fires before T2 check (101 >= 101)
    assert result.exit_type == ExitType.SL_HIT


# =========================================================================
# Per-strategy trailing stop configs (Phase 2)
# =========================================================================


def _build_monitor_with_configs(
    tick: TickData | None = None,
    trailing_configs: dict[str, TrailingStopConfig] | None = DEFAULT_TRAILING_CONFIGS,
) -> tuple[ExitMonitor, MockAlertSink]:
    """Create an ExitMonitor with per-strategy trailing configs and a mock tick source."""
    alert_sink = MockAlertSink()

    async def get_tick(symbol: str) -> TickData | None:
        if tick is not None and tick.symbol == symbol:
            return tick
        return None

    monitor = ExitMonitor(
        get_tick=get_tick,
        alert_callback=alert_sink,
        trailing_configs=trailing_configs,
    )
    return monitor, alert_sink


def _build_monitor_with_configs_and_prices(
    symbol: str,
    prices: list[float],
    trailing_configs: dict[str, TrailingStopConfig] | None = DEFAULT_TRAILING_CONFIGS,
) -> tuple[ExitMonitor, MockAlertSink]:
    """Create an ExitMonitor with per-strategy configs and successive prices."""
    alert_sink = MockAlertSink()
    price_iter = iter(prices)

    async def get_tick(sym: str) -> TickData | None:
        if sym != symbol:
            return None
        try:
            price = next(price_iter)
        except StopIteration:
            return None
        return _make_tick(sym, price)

    monitor = ExitMonitor(
        get_tick=get_tick,
        alert_callback=alert_sink,
        trailing_configs=trailing_configs,
    )
    return monitor, alert_sink


def _make_trade_with_strategy(
    trade_id: int = 1,
    symbol: str = "SBIN",
    entry_price: float = 100.0,
    stop_loss: float = 97.0,
    target_1: float = 105.0,
    target_2: float = 110.0,
    quantity: int = 10,
    strategy: str = "gap_go",
    setup_type: str | None = None,
) -> TradeRecord:
    """Create a TradeRecord with strategy and optional setup_type."""
    trade = TradeRecord(
        id=trade_id,
        signal_id=1,
        symbol=symbol,
        strategy=strategy,
        entry_price=entry_price,
        stop_loss=stop_loss,
        target_1=target_1,
        target_2=target_2,
        quantity=quantity,
        taken_at=datetime(2025, 1, 6, 9, 35, 0, tzinfo=IST),
    )
    if setup_type is not None:
        trade.setup_type = setup_type
    return trade


# ── ORB trailing stop: breakeven at +1.5%, trail at +2% with 1% distance ──


@pytest.mark.asyncio
async def test_orb_breakeven_at_1_5pct() -> None:
    """ORB trade: breakeven triggers at +1.5% above entry."""
    trade = _make_trade_with_strategy(
        entry_price=100.0, stop_loss=97.0, strategy="ORB",
        target_1=105.0, target_2=110.0,
    )
    tick = _make_tick(ltp=101.5)  # +1.5%
    monitor, alerts = _build_monitor_with_configs(tick)
    monitor.start_monitoring(trade)

    result = await monitor.check_trade(trade)

    assert result is not None
    assert result.is_alert_only is True
    assert result.trailing_sl_update == pytest.approx(100.0)  # Breakeven = entry
    state = monitor._active_states[trade.id]
    assert state.breakeven_triggered is True
    assert state.current_sl == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_orb_trail_at_2pct() -> None:
    """ORB trade: trailing SL activates at +2%, distance is 1%."""
    trade = _make_trade_with_strategy(
        entry_price=100.0, stop_loss=97.0, strategy="ORB",
        target_1=105.0, target_2=110.0,
    )
    tick = _make_tick(ltp=102.0)  # +2.0% -> trail triggers
    monitor, alerts = _build_monitor_with_configs(tick)
    monitor.start_monitoring(trade)

    result = await monitor.check_trade(trade)

    assert result is not None
    assert result.is_alert_only is True
    # Trail distance = 1%, so trailing SL = 102.0 * 0.99 = 100.98
    expected_sl = 102.0 * 0.99
    assert result.trailing_sl_update == pytest.approx(expected_sl)
    state = monitor._active_states[trade.id]
    assert state.trailing_active is True
    assert state.current_sl == pytest.approx(expected_sl)


@pytest.mark.asyncio
async def test_orb_trail_moves_up_with_price() -> None:
    """ORB trade: trailing SL moves up as price rises above +2%."""
    trade = _make_trade_with_strategy(
        entry_price=100.0, stop_loss=97.0, strategy="ORB",
        target_1=108.0, target_2=112.0,
    )
    monitor, alerts = _build_monitor_with_configs_and_prices(
        "SBIN", [102.0, 104.0]
    )
    monitor.start_monitoring(trade)

    # First tick: 102.0 -> trail at 100.98
    await monitor.check_trade(trade)
    assert monitor._active_states[trade.id].current_sl == pytest.approx(102.0 * 0.99)

    # Second tick: 104.0 -> trail at 102.96
    await monitor.check_trade(trade)
    assert monitor._active_states[trade.id].current_sl == pytest.approx(104.0 * 0.99)


# ── VWAP Reversal Setup 1 (uptrend_pullback): breakeven at +1.0%, NO trailing ──


@pytest.mark.asyncio
async def test_vwap_setup1_breakeven_at_1pct() -> None:
    """VWAP Reversal (uptrend_pullback): breakeven triggers at +1.0%."""
    trade = _make_trade_with_strategy(
        entry_price=100.0, stop_loss=97.0, strategy="VWAP Reversal",
        setup_type="uptrend_pullback",
        target_1=105.0, target_2=110.0,
    )
    tick = _make_tick(ltp=101.0)  # +1.0%
    monitor, alerts = _build_monitor_with_configs(tick)
    monitor.start_monitoring(trade)

    result = await monitor.check_trade(trade)

    assert result is not None
    assert result.is_alert_only is True
    assert result.trailing_sl_update == pytest.approx(100.0)  # Breakeven
    state = monitor._active_states[trade.id]
    assert state.breakeven_triggered is True
    assert state.current_sl == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_vwap_setup1_no_trailing_beyond_breakeven() -> None:
    """VWAP Reversal (uptrend_pullback): no trailing SL beyond breakeven, even at +5%."""
    trade = _make_trade_with_strategy(
        entry_price=100.0, stop_loss=97.0, strategy="VWAP Reversal",
        setup_type="uptrend_pullback",
        target_1=108.0, target_2=112.0,
    )
    monitor, alerts = _build_monitor_with_configs_and_prices(
        "SBIN", [101.0, 105.0]
    )
    monitor.start_monitoring(trade)

    # First tick: breakeven triggers at +1%
    r1 = await monitor.check_trade(trade)
    assert r1 is not None
    assert r1.trailing_sl_update == pytest.approx(100.0)

    # Second tick: +5% -- but trail_trigger_pct is None, so SL stays at breakeven
    r2 = await monitor.check_trade(trade)
    assert r2 is None  # No trailing update
    state = monitor._active_states[trade.id]
    assert state.current_sl == pytest.approx(100.0)  # Still at breakeven
    assert state.trailing_active is False


# ── VWAP Reversal Setup 2 (vwap_reclaim): breakeven at +1.5%, NO trailing ──


@pytest.mark.asyncio
async def test_vwap_setup2_breakeven_at_1_5pct() -> None:
    """VWAP Reversal (vwap_reclaim): breakeven triggers at +1.5%."""
    trade = _make_trade_with_strategy(
        entry_price=100.0, stop_loss=97.0, strategy="VWAP Reversal",
        setup_type="vwap_reclaim",
        target_1=105.0, target_2=110.0,
    )
    tick = _make_tick(ltp=101.5)  # +1.5%
    monitor, alerts = _build_monitor_with_configs(tick)
    monitor.start_monitoring(trade)

    result = await monitor.check_trade(trade)

    assert result is not None
    assert result.is_alert_only is True
    assert result.trailing_sl_update == pytest.approx(100.0)  # Breakeven


@pytest.mark.asyncio
async def test_vwap_setup2_no_breakeven_below_threshold() -> None:
    """VWAP Reversal (vwap_reclaim): no breakeven at +1.0% (threshold is 1.5%)."""
    trade = _make_trade_with_strategy(
        entry_price=100.0, stop_loss=97.0, strategy="VWAP Reversal",
        setup_type="vwap_reclaim",
        target_1=105.0, target_2=110.0,
    )
    tick = _make_tick(ltp=101.0)  # Only +1.0%
    monitor, alerts = _build_monitor_with_configs(tick)
    monitor.start_monitoring(trade)

    result = await monitor.check_trade(trade)

    assert result is None
    state = monitor._active_states[trade.id]
    assert state.breakeven_triggered is False


@pytest.mark.asyncio
async def test_vwap_setup2_no_trailing() -> None:
    """VWAP Reversal (vwap_reclaim): no trailing SL even at +5%."""
    trade = _make_trade_with_strategy(
        entry_price=100.0, stop_loss=97.0, strategy="VWAP Reversal",
        setup_type="vwap_reclaim",
        target_1=108.0, target_2=112.0,
    )
    monitor, alerts = _build_monitor_with_configs_and_prices(
        "SBIN", [101.5, 105.0]
    )
    monitor.start_monitoring(trade)

    # First tick: breakeven at +1.5%
    r1 = await monitor.check_trade(trade)
    assert r1 is not None
    assert r1.trailing_sl_update == pytest.approx(100.0)

    # Second tick: +5% -- no trailing
    r2 = await monitor.check_trade(trade)
    assert r2 is None
    state = monitor._active_states[trade.id]
    assert state.current_sl == pytest.approx(100.0)
    assert state.trailing_active is False


# ── Gap & Go: unchanged behavior (2.0%/4.0%/2.0%) ──


@pytest.mark.asyncio
async def test_gap_go_unchanged_breakeven_at_2pct() -> None:
    """Gap & Go trade with DEFAULT_TRAILING_CONFIGS: breakeven at +2%."""
    trade = _make_trade_with_strategy(
        entry_price=100.0, stop_loss=97.0, strategy="Gap & Go",
        target_1=105.0, target_2=110.0,
    )
    tick = _make_tick(ltp=102.0)  # +2.0%
    monitor, alerts = _build_monitor_with_configs(tick)
    monitor.start_monitoring(trade)

    result = await monitor.check_trade(trade)

    assert result is not None
    assert result.trailing_sl_update == pytest.approx(100.0)  # Breakeven
    state = monitor._active_states[trade.id]
    assert state.breakeven_triggered is True


@pytest.mark.asyncio
async def test_gap_go_unchanged_trail_at_4pct() -> None:
    """Gap & Go trade with DEFAULT_TRAILING_CONFIGS: trail at +4%, 2% distance."""
    trade = _make_trade_with_strategy(
        entry_price=100.0, stop_loss=97.0, strategy="Gap & Go",
        target_1=108.0, target_2=112.0,
    )
    tick = _make_tick(ltp=104.0)  # +4.0%
    monitor, alerts = _build_monitor_with_configs(tick)
    monitor.start_monitoring(trade)

    result = await monitor.check_trade(trade)

    assert result is not None
    # Trail distance = 2%, so trailing SL = 104.0 * 0.98 = 101.92
    assert result.trailing_sl_update == pytest.approx(104.0 * 0.98)
    state = monitor._active_states[trade.id]
    assert state.trailing_active is True
    assert state.current_sl == pytest.approx(101.92)


# ── Unknown strategy: falls back to constructor-level defaults ──


@pytest.mark.asyncio
async def test_unknown_strategy_uses_fallback() -> None:
    """Trade with unknown strategy falls back to constructor-level defaults."""
    trade = _make_trade_with_strategy(
        entry_price=100.0, stop_loss=97.0, strategy="MYSTERY",
        target_1=105.0, target_2=110.0,
    )
    tick = _make_tick(ltp=102.0)  # +2.0%
    monitor, alerts = _build_monitor_with_configs(tick)
    monitor.start_monitoring(trade)

    result = await monitor.check_trade(trade)

    # Fallback defaults: breakeven_trigger_pct=2.0 (from ExitMonitor constructor)
    assert result is not None
    assert result.is_alert_only is True
    assert result.trailing_sl_update == pytest.approx(100.0)  # Breakeven


@pytest.mark.asyncio
async def test_unknown_strategy_fallback_trail_at_4pct() -> None:
    """Unknown strategy fallback: trail at +4% with 2% distance (constructor defaults)."""
    trade = _make_trade_with_strategy(
        entry_price=100.0, stop_loss=97.0, strategy="MYSTERY",
        target_1=108.0, target_2=112.0,
    )
    tick = _make_tick(ltp=104.0)  # +4.0%
    monitor, alerts = _build_monitor_with_configs(tick)
    monitor.start_monitoring(trade)

    result = await monitor.check_trade(trade)

    assert result is not None
    assert result.trailing_sl_update == pytest.approx(104.0 * 0.98)
    state = monitor._active_states[trade.id]
    assert state.trailing_active is True


# ── Verify DEFAULT_TRAILING_CONFIGS has expected entries ──


def test_default_trailing_configs_keys() -> None:
    """DEFAULT_TRAILING_CONFIGS contains all expected strategy keys."""
    expected_keys = {
        "Gap & Go", "gap_go", "ORB",
        "VWAP Reversal", "VWAP Reversal:uptrend_pullback", "VWAP Reversal:vwap_reclaim",
    }
    assert set(DEFAULT_TRAILING_CONFIGS.keys()) == expected_keys


def test_default_trailing_configs_orb_values() -> None:
    """ORB config has breakeven=1.5%, trail=2.0%, distance=1.0%."""
    cfg = DEFAULT_TRAILING_CONFIGS["ORB"]
    assert cfg.breakeven_trigger_pct == 1.5
    assert cfg.trail_trigger_pct == 2.0
    assert cfg.trail_distance_pct == 1.0


def test_default_trailing_configs_vwap_no_trail() -> None:
    """VWAP Reversal configs have trail_trigger_pct=None (no trailing)."""
    cfg = DEFAULT_TRAILING_CONFIGS["VWAP Reversal"]
    assert cfg.breakeven_trigger_pct == 1.0
    assert cfg.trail_trigger_pct is None
    assert cfg.trail_distance_pct is None

    cfg_reclaim = DEFAULT_TRAILING_CONFIGS["VWAP Reversal:vwap_reclaim"]
    assert cfg_reclaim.breakeven_trigger_pct == 1.5
    assert cfg_reclaim.trail_trigger_pct is None


# =========================================================================
# Phase 3: on_sl_hit_callback and on_trade_exit_callback tests
# =========================================================================

from unittest.mock import AsyncMock


def _build_monitor_with_callbacks(
    tick: TickData | None = None,
    on_sl_hit_callback=None,
    on_trade_exit_callback=None,
    close_trade=None,
) -> tuple[ExitMonitor, MockAlertSink]:
    """Create an ExitMonitor with Phase 3 callbacks."""
    alert_sink = MockAlertSink()

    async def get_tick(symbol: str) -> TickData | None:
        if tick is not None and tick.symbol == symbol:
            return tick
        return None

    monitor = ExitMonitor(
        get_tick=get_tick,
        alert_callback=alert_sink,
        close_trade=close_trade,
        on_sl_hit_callback=on_sl_hit_callback,
        on_trade_exit_callback=on_trade_exit_callback,
    )
    return monitor, alert_sink


class TestExitMonitorPhase3Callbacks:
    """Tests for Phase 3 on_sl_hit_callback and on_trade_exit_callback."""

    @pytest.mark.asyncio
    async def test_sl_hit_fires_on_sl_hit_callback(self) -> None:
        """SL hit should call on_sl_hit_callback with symbol, strategy, pnl."""
        on_sl_hit = AsyncMock()
        on_trade_exit = AsyncMock()
        trade = _make_trade(entry_price=100.0, stop_loss=97.0, quantity=10)
        tick = _make_tick(ltp=96.0)
        monitor, alerts = _build_monitor_with_callbacks(
            tick=tick,
            on_sl_hit_callback=on_sl_hit,
            on_trade_exit_callback=on_trade_exit,
        )
        monitor.start_monitoring(trade)

        await monitor.check_trade(trade)

        on_sl_hit.assert_called_once()
        args = on_sl_hit.call_args[0]
        assert args[0] == "SBIN"  # symbol
        assert args[2] < 0  # pnl_amount is negative

    @pytest.mark.asyncio
    async def test_sl_hit_fires_on_trade_exit_callback(self) -> None:
        """SL hit should also call on_trade_exit_callback."""
        on_trade_exit = AsyncMock()
        trade = _make_trade(entry_price=100.0, stop_loss=97.0, quantity=10)
        tick = _make_tick(ltp=96.0)
        monitor, alerts = _build_monitor_with_callbacks(
            tick=tick,
            on_trade_exit_callback=on_trade_exit,
        )
        monitor.start_monitoring(trade)

        await monitor.check_trade(trade)

        on_trade_exit.assert_called_once()
        args = on_trade_exit.call_args[0]
        assert args[1] is True  # is_loss = True

    @pytest.mark.asyncio
    async def test_t2_hit_fires_on_trade_exit_but_not_on_sl_hit(self) -> None:
        """T2 hit should call on_trade_exit but NOT on_sl_hit."""
        on_sl_hit = AsyncMock()
        on_trade_exit = AsyncMock()
        trade = _make_trade(entry_price=100.0, target_2=107.0, quantity=10)
        tick = _make_tick(ltp=107.0)
        monitor, alerts = _build_monitor_with_callbacks(
            tick=tick,
            on_sl_hit_callback=on_sl_hit,
            on_trade_exit_callback=on_trade_exit,
        )
        monitor.start_monitoring(trade)

        await monitor.check_trade(trade)

        on_sl_hit.assert_not_called()
        on_trade_exit.assert_called_once()
        args = on_trade_exit.call_args[0]
        assert args[1] is False  # is_loss = False (profit)

    @pytest.mark.asyncio
    async def test_no_callbacks_backward_compatible(self) -> None:
        """Without callbacks, SL hit should work as before."""
        trade = _make_trade(entry_price=100.0, stop_loss=97.0)
        tick = _make_tick(ltp=96.0)
        monitor, alerts = _build_monitor_with_callbacks(tick=tick)
        monitor.start_monitoring(trade)

        result = await monitor.check_trade(trade)

        assert result is not None
        assert result.exit_type == ExitType.SL_HIT

    @pytest.mark.asyncio
    async def test_time_exit_fires_on_trade_exit(self) -> None:
        """Mandatory time exit should call on_trade_exit_callback."""
        on_trade_exit = AsyncMock()
        trade = _make_trade(trade_id=1, entry_price=100.0, quantity=10)

        alert_sink = MockAlertSink()
        tick_data = _make_tick("SBIN", 98.0)

        async def get_tick(symbol: str) -> TickData | None:
            if symbol == "SBIN":
                return tick_data
            return None

        monitor = ExitMonitor(
            get_tick=get_tick,
            alert_callback=alert_sink,
            on_trade_exit_callback=on_trade_exit,
        )
        monitor.start_monitoring(trade)

        await monitor.trigger_time_exit([trade], is_mandatory=True)

        on_trade_exit.assert_called_once()
        args = on_trade_exit.call_args[0]
        assert args[1] is True  # pnl negative, is_loss = True

    @pytest.mark.asyncio
    async def test_trailing_sl_hit_fires_on_sl_hit(self) -> None:
        """Trailing SL hit should fire on_sl_hit_callback."""
        on_sl_hit = AsyncMock()
        trade = _make_trade(entry_price=100.0, stop_loss=97.0, quantity=10)

        alert_sink = MockAlertSink()
        prices = iter([106.0, 103.88])  # First sets trail, then hits it

        async def get_tick(sym: str) -> TickData | None:
            if sym != "SBIN":
                return None
            try:
                price = next(prices)
            except StopIteration:
                return None
            return _make_tick(sym, price)

        monitor = ExitMonitor(
            get_tick=get_tick,
            alert_callback=alert_sink,
            on_sl_hit_callback=on_sl_hit,
        )
        monitor.start_monitoring(trade)

        # Set up trailing SL
        await monitor.check_trade(trade)
        # Hit trailing SL
        await monitor.check_trade(trade)

        on_sl_hit.assert_called_once()
        args = on_sl_hit.call_args[0]
        assert args[0] == "SBIN"
