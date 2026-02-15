"""Tests for SignalPilotApp lifecycle orchestrator."""

import asyncio
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from signalpilot.db.models import (
    CandidateSignal,
    DailySummary,
    FinalSignal,
    RankedSignal,
    SignalDirection,
    SignalRecord,
    TradeRecord,
    UserConfig,
)
from signalpilot.scheduler.lifecycle import SignalPilotApp
from signalpilot.utils.constants import IST
from signalpilot.utils.market_calendar import StrategyPhase


def _make_app(**overrides) -> SignalPilotApp:
    """Create a SignalPilotApp with all mocked dependencies."""
    defaults = {
        "db": AsyncMock(),
        "signal_repo": AsyncMock(),
        "trade_repo": AsyncMock(),
        "config_repo": AsyncMock(),
        "metrics_calculator": AsyncMock(),
        "authenticator": AsyncMock(),
        "instruments": AsyncMock(),
        "market_data": MagicMock(),
        "historical": AsyncMock(),
        "websocket": AsyncMock(),
        "strategy": AsyncMock(),
        "ranker": MagicMock(),
        "risk_manager": MagicMock(),
        "exit_monitor": MagicMock(
            check_all_trades=AsyncMock(),
            trigger_time_exit_check=AsyncMock(),
            start_monitoring=MagicMock(),
        ),
        "bot": AsyncMock(),
        "scheduler": MagicMock(),
    }
    defaults.update(overrides)
    return SignalPilotApp(**defaults)


def _make_final_signal(symbol: str = "SBIN") -> FinalSignal:
    candidate = CandidateSignal(
        symbol=symbol,
        direction=SignalDirection.BUY,
        strategy_name="Gap & Go",
        entry_price=100.0,
        stop_loss=97.0,
        target_1=105.0,
        target_2=107.0,
        gap_pct=4.0,
        volume_ratio=2.0,
        price_distance_from_open_pct=1.5,
        reason="test",
        generated_at=datetime(2025, 1, 6, 9, 35, 0, tzinfo=IST),
    )
    ranked = RankedSignal(
        candidate=candidate, composite_score=0.8, rank=1, signal_strength=4
    )
    return FinalSignal(
        ranked_signal=ranked,
        quantity=10,
        capital_required=1000.0,
        expires_at=datetime(2025, 1, 6, 10, 5, 0, tzinfo=IST),
    )


# -- startup -------------------------------------------------------------------


async def test_startup_calls_all_init_methods() -> None:
    app = _make_app()
    await app.startup()

    app._db.initialize.assert_awaited_once()
    app._authenticator.authenticate.assert_awaited_once()
    app._instruments.load.assert_awaited_once()
    app._historical.fetch_previous_day_data.assert_awaited_once()
    app._historical.fetch_average_daily_volume.assert_awaited_once()
    app._bot.start.assert_awaited_once()
    app._scheduler.configure_jobs.assert_called_once_with(app)
    app._scheduler.start.assert_called_once()


async def test_startup_initializes_default_config() -> None:
    app = _make_app()
    await app.startup()
    app._config_repo.initialize_default.assert_awaited_once()


# -- scan loop -----------------------------------------------------------------


async def test_scan_loop_evaluates_strategy_during_entry_window() -> None:
    """Scan loop should evaluate strategy during OPENING/ENTRY_WINDOW phases."""
    app = _make_app()
    app._strategy.evaluate = AsyncMock(return_value=[])
    app._exit_monitor.check_all_trades = AsyncMock()
    app._signal_repo.expire_stale_signals = AsyncMock(return_value=0)

    call_count = 0
    original_sleep = asyncio.sleep

    async def mock_sleep(seconds):
        nonlocal call_count
        call_count += 1
        if call_count >= 1:
            app._scanning = False
        await original_sleep(0)

    with patch(
        "signalpilot.scheduler.lifecycle.get_current_phase",
        return_value=StrategyPhase.ENTRY_WINDOW,
    ), patch("asyncio.sleep", side_effect=mock_sleep):
        app._scanning = True
        app._accepting_signals = True
        await app._scan_loop()

    app._strategy.evaluate.assert_awaited()


async def test_scan_loop_skips_strategy_when_not_accepting() -> None:
    """Scan loop should not evaluate strategy when _accepting_signals is False."""
    app = _make_app()
    app._strategy.evaluate = AsyncMock(return_value=[])
    app._exit_monitor.check_all_trades = AsyncMock()
    app._signal_repo.expire_stale_signals = AsyncMock(return_value=0)

    call_count = 0
    original_sleep = asyncio.sleep

    async def mock_sleep(seconds):
        nonlocal call_count
        call_count += 1
        if call_count >= 1:
            app._scanning = False
        await original_sleep(0)

    with patch(
        "signalpilot.scheduler.lifecycle.get_current_phase",
        return_value=StrategyPhase.ENTRY_WINDOW,
    ), patch("asyncio.sleep", side_effect=mock_sleep):
        app._scanning = True
        app._accepting_signals = False
        await app._scan_loop()

    app._strategy.evaluate.assert_not_awaited()


async def test_scan_loop_skips_strategy_during_continuous() -> None:
    """Scan loop should not evaluate strategy during CONTINUOUS phase."""
    app = _make_app()
    app._strategy.evaluate = AsyncMock(return_value=[])
    app._exit_monitor.check_all_trades = AsyncMock()
    app._signal_repo.expire_stale_signals = AsyncMock(return_value=0)

    call_count = 0
    original_sleep = asyncio.sleep

    async def mock_sleep(seconds):
        nonlocal call_count
        call_count += 1
        if call_count >= 1:
            app._scanning = False
        await original_sleep(0)

    with patch(
        "signalpilot.scheduler.lifecycle.get_current_phase",
        return_value=StrategyPhase.CONTINUOUS,
    ), patch("asyncio.sleep", side_effect=mock_sleep):
        app._scanning = True
        app._accepting_signals = True
        await app._scan_loop()

    app._strategy.evaluate.assert_not_awaited()


async def test_scan_loop_always_checks_exits() -> None:
    """Exit monitor should be checked every iteration regardless of phase."""
    app = _make_app()
    app._exit_monitor.check_all_trades = AsyncMock()
    app._signal_repo.expire_stale_signals = AsyncMock(return_value=0)

    call_count = 0
    original_sleep = asyncio.sleep

    async def mock_sleep(seconds):
        nonlocal call_count
        call_count += 1
        if call_count >= 1:
            app._scanning = False
        await original_sleep(0)

    with patch(
        "signalpilot.scheduler.lifecycle.get_current_phase",
        return_value=StrategyPhase.WIND_DOWN,
    ), patch("asyncio.sleep", side_effect=mock_sleep):
        app._scanning = True
        await app._scan_loop()

    app._exit_monitor.check_all_trades.assert_awaited()


async def test_scan_loop_sends_signal_when_candidates_found() -> None:
    """When strategy produces candidates, they should be ranked, filtered, saved, and sent."""
    signal = _make_final_signal()

    app = _make_app()
    app._strategy.evaluate = AsyncMock(return_value=["candidate1"])
    app._ranker.rank = MagicMock(return_value=["ranked1"])
    app._config_repo.get_user_config = AsyncMock(
        return_value=UserConfig(total_capital=50000.0, max_positions=5)
    )
    app._trade_repo.get_active_trade_count = AsyncMock(return_value=0)
    app._risk_manager.filter_and_size = MagicMock(return_value=[signal])
    app._signal_repo.insert_signal = AsyncMock(return_value=1)
    app._bot.send_signal = AsyncMock()
    app._exit_monitor.check_all_trades = AsyncMock()
    app._signal_repo.expire_stale_signals = AsyncMock(return_value=0)

    call_count = 0
    original_sleep = asyncio.sleep

    async def mock_sleep(seconds):
        nonlocal call_count
        call_count += 1
        if call_count >= 1:
            app._scanning = False
        await original_sleep(0)

    with patch(
        "signalpilot.scheduler.lifecycle.get_current_phase",
        return_value=StrategyPhase.OPENING,
    ), patch("asyncio.sleep", side_effect=mock_sleep):
        app._scanning = True
        app._accepting_signals = True
        await app._scan_loop()

    app._signal_repo.insert_signal.assert_awaited_once()
    app._bot.send_signal.assert_awaited_once_with(signal)


# -- stop_new_signals ----------------------------------------------------------


async def test_stop_new_signals() -> None:
    app = _make_app()
    await app.stop_new_signals()

    assert app._accepting_signals is False
    app._bot.send_alert.assert_awaited_once()
    assert "2:30 PM" in app._bot.send_alert.call_args[0][0]


# -- pre_market_alert ----------------------------------------------------------


async def test_send_pre_market_alert() -> None:
    app = _make_app()
    await app.send_pre_market_alert()
    app._bot.send_alert.assert_awaited_once()
    assert "Pre-market" in app._bot.send_alert.call_args[0][0]


# -- exit handling -------------------------------------------------------------


async def test_trigger_exit_reminder() -> None:
    app = _make_app()
    await app.trigger_exit_reminder()
    app._exit_monitor.trigger_time_exit_check.assert_awaited_once_with(
        is_mandatory=False
    )
    app._bot.send_alert.assert_awaited_once()


async def test_trigger_mandatory_exit() -> None:
    app = _make_app()
    await app.trigger_mandatory_exit()
    app._exit_monitor.trigger_time_exit_check.assert_awaited_once_with(
        is_mandatory=True
    )


# -- daily summary -------------------------------------------------------------


async def test_send_daily_summary() -> None:
    summary = DailySummary(
        date=date(2025, 1, 6),
        signals_sent=5,
        trades_taken=3,
        wins=2,
        losses=1,
        total_pnl=1200.0,
        cumulative_pnl=5000.0,
    )
    app = _make_app()
    app._metrics.calculate_daily_summary = AsyncMock(return_value=summary)

    await app.send_daily_summary()

    app._metrics.calculate_daily_summary.assert_awaited_once()
    app._bot.send_alert.assert_awaited_once()
    msg = app._bot.send_alert.call_args[0][0]
    assert "Daily Summary" in msg


# -- shutdown ------------------------------------------------------------------


async def test_shutdown_calls_all_cleanup() -> None:
    app = _make_app()
    await app.shutdown()

    assert app._scanning is False
    app._websocket.disconnect.assert_awaited_once()
    app._scheduler.shutdown.assert_called_once()
    app._bot.stop.assert_awaited_once()
    app._db.close.assert_awaited_once()


async def test_shutdown_cancels_scan_task() -> None:
    """Shutdown should cancel the running scan task."""
    app = _make_app()

    async def fake_scan():
        await asyncio.sleep(100)

    app._scan_task = asyncio.create_task(fake_scan())
    await app.shutdown()

    assert app._scan_task.cancelled()


# -- recover -------------------------------------------------------------------


async def test_recover_restores_active_trades() -> None:
    trades = [
        TradeRecord(
            id=1, symbol="SBIN", entry_price=100.0, stop_loss=97.0, quantity=10
        ),
        TradeRecord(
            id=2, symbol="TCS", entry_price=200.0, stop_loss=194.0, quantity=5
        ),
    ]
    app = _make_app()
    app._trade_repo.get_active_trades = AsyncMock(return_value=trades)
    app._websocket.connect = AsyncMock()

    with patch.object(app, "_scan_loop", new_callable=AsyncMock):
        await app.recover()

    app._db.initialize.assert_awaited_once()
    app._authenticator.authenticate.assert_awaited_once()
    assert app._exit_monitor.start_monitoring.call_count == 2
    app._bot.send_alert.assert_awaited()
    assert "recovered" in app._bot.send_alert.call_args[0][0].lower()


async def test_recover_starts_scanning() -> None:
    app = _make_app()
    app._trade_repo.get_active_trades = AsyncMock(return_value=[])
    app._websocket.connect = AsyncMock()

    with patch.object(app, "_scan_loop", new_callable=AsyncMock):
        await app.recover()

    assert app._scanning is True


# -- _expire_stale_signals -----------------------------------------------------


async def test_expire_stale_signals_delegates_to_repo() -> None:
    app = _make_app()
    app._signal_repo.expire_stale_signals = AsyncMock(return_value=3)

    await app._expire_stale_signals()

    app._signal_repo.expire_stale_signals.assert_awaited_once()


# -- _signal_to_record ---------------------------------------------------------


def test_signal_to_record_conversion() -> None:
    signal = _make_final_signal(symbol="RELIANCE")
    now = datetime(2025, 1, 6, 9, 35, 0, tzinfo=IST)
    record = SignalPilotApp._signal_to_record(signal, now)

    assert isinstance(record, SignalRecord)
    assert record.symbol == "RELIANCE"
    assert record.entry_price == 100.0
    assert record.stop_loss == 97.0
    assert record.target_1 == 105.0
    assert record.target_2 == 107.0
    assert record.quantity == 10
    assert record.capital_required == 1000.0
    assert record.signal_strength == 4
    assert record.strategy == "Gap & Go"
    assert record.status == "sent"
    assert record.date == date(2025, 1, 6)


# -- scan loop error handling --------------------------------------------------


async def test_scan_loop_continues_after_error() -> None:
    """The scan loop should log errors but keep running."""
    app = _make_app()

    iteration = 0
    original_sleep = asyncio.sleep

    async def failing_check():
        nonlocal iteration
        iteration += 1
        if iteration == 1:
            raise RuntimeError("test error")

    app._exit_monitor.check_all_trades = failing_check
    app._signal_repo.expire_stale_signals = AsyncMock(return_value=0)

    call_count = 0

    async def mock_sleep(seconds):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            app._scanning = False
        await original_sleep(0)

    with patch(
        "signalpilot.scheduler.lifecycle.get_current_phase",
        return_value=StrategyPhase.WIND_DOWN,
    ), patch("asyncio.sleep", side_effect=mock_sleep):
        app._scanning = True
        await app._scan_loop()

    # Should have run 2 iterations (one with error, one without)
    assert call_count == 2


# -- circuit breaker -----------------------------------------------------------


async def test_scan_loop_circuit_breaker_stops_after_max_errors() -> None:
    """Scan loop should stop after max consecutive errors."""
    app = _make_app()
    app._max_consecutive_errors = 3

    async def always_fail():
        raise RuntimeError("persistent failure")

    app._exit_monitor.check_all_trades = always_fail
    app._signal_repo.expire_stale_signals = AsyncMock(return_value=0)

    original_sleep = asyncio.sleep

    async def mock_sleep(seconds):
        await original_sleep(0)

    with patch(
        "signalpilot.scheduler.lifecycle.get_current_phase",
        return_value=StrategyPhase.WIND_DOWN,
    ), patch("asyncio.sleep", side_effect=mock_sleep):
        app._scanning = True
        await app._scan_loop()

    assert app._scanning is False
    app._bot.send_alert.assert_awaited_once()
    assert "repeated errors" in app._bot.send_alert.call_args[0][0].lower()


# -- shutdown resilience -------------------------------------------------------


async def test_shutdown_continues_if_websocket_disconnect_fails() -> None:
    """If websocket disconnect fails, bot and DB should still be cleaned up."""
    app = _make_app()
    app._websocket.disconnect = AsyncMock(side_effect=RuntimeError("ws error"))

    await app.shutdown()

    app._bot.stop.assert_awaited_once()
    app._db.close.assert_awaited_once()
    app._scheduler.shutdown.assert_called_once()


# -- recover phase check -------------------------------------------------------


async def test_recover_disables_signals_after_entry_window() -> None:
    """Recovery after entry window should disable new signal generation."""
    app = _make_app()
    app._trade_repo.get_active_trades = AsyncMock(return_value=[])
    app._websocket.connect = AsyncMock()

    with patch.object(app, "_scan_loop", new_callable=AsyncMock), \
         patch(
            "signalpilot.scheduler.lifecycle.get_current_phase",
            return_value=StrategyPhase.CONTINUOUS,
         ):
        await app.recover()

    assert app._accepting_signals is False


async def test_recover_keeps_signals_during_entry_window() -> None:
    """Recovery during entry window should keep signal generation enabled."""
    app = _make_app()
    app._trade_repo.get_active_trades = AsyncMock(return_value=[])
    app._websocket.connect = AsyncMock()

    with patch.object(app, "_scan_loop", new_callable=AsyncMock), \
         patch(
            "signalpilot.scheduler.lifecycle.get_current_phase",
            return_value=StrategyPhase.ENTRY_WINDOW,
         ):
        await app.recover()

    assert app._accepting_signals is True
