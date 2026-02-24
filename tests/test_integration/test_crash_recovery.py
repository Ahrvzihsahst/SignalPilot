"""Integration tests for crash recovery with pre-populated DB."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from signalpilot.db.models import TradeRecord
from signalpilot.scheduler.lifecycle import SignalPilotApp
from signalpilot.utils.constants import IST
from signalpilot.utils.market_calendar import StrategyPhase
from tests.test_integration.conftest import (
    _make_mock_historical,
    _make_mock_market_data,
    make_signal_record,
)


async def test_recovery_reloads_active_trades(db, repos):
    """Recovery should reload active trades and start monitoring them."""
    now = datetime.now(IST)

    # Pre-populate DB with signals
    for i, symbol in enumerate(["SBIN", "TCS", "RELIANCE"]):
        signal = make_signal_record(
            symbol=symbol, entry_price=100.0 + i * 10, created_at=now,
        )
        await repos["signal_repo"].insert_signal(signal)

    # Pre-populate 2 active trades (manually insert, simulating prior TAKEN)
    for sig_id, symbol in [(1, "SBIN"), (2, "TCS")]:
        trade = TradeRecord(
            signal_id=sig_id, date=now.date(), symbol=symbol,
            entry_price=100.0, stop_loss=97.0, target_1=105.0, target_2=107.0,
            quantity=15, taken_at=now,
        )
        await repos["trade_repo"].insert_trade(trade)

    # Verify pre-conditions
    assert await repos["trade_repo"].get_active_trade_count() == 2

    mock_bot = AsyncMock()
    mock_exit_monitor = MagicMock(
        check_trade=AsyncMock(),
        trigger_time_exit=AsyncMock(return_value=[]),
        start_monitoring=MagicMock(),
    )
    mock_auth = AsyncMock()
    mock_instruments = AsyncMock()
    mock_websocket = AsyncMock()
    mock_scheduler = MagicMock()

    app = SignalPilotApp(
        db=db, signal_repo=repos["signal_repo"], trade_repo=repos["trade_repo"],
        config_repo=repos["config_repo"], metrics_calculator=repos["metrics"],
        authenticator=mock_auth, instruments=mock_instruments,
        market_data=_make_mock_market_data(), historical=_make_mock_historical(),
        websocket=mock_websocket,
        strategy=AsyncMock(), ranker=MagicMock(), risk_manager=MagicMock(),
        exit_monitor=mock_exit_monitor, bot=mock_bot, scheduler=mock_scheduler,
    )

    # Patch db.initialize to no-op (avoid closing/reopening the in-memory DB which
    # would lose all pre-populated data), start_scanning to avoid launching a real
    # scan loop, and get_current_phase to return CONTINUOUS (after entry window).
    with patch.object(db, "initialize", new_callable=AsyncMock) as mock_db_init, \
         patch.object(app, "start_scanning", new_callable=AsyncMock) as mock_start_scanning, \
         patch(
             "signalpilot.scheduler.lifecycle.get_current_phase",
             return_value=StrategyPhase.CONTINUOUS,
         ):
        await app.recover()

    # Verify db.initialize was called (recovery re-initializes DB)
    mock_db_init.assert_awaited_once()

    # Verify re-authentication
    mock_auth.authenticate.assert_awaited_once()

    # Verify instruments loaded
    mock_instruments.load.assert_awaited_once()

    # Verify bot started
    mock_bot.start.assert_awaited_once()

    # Verify exit monitor has 2 trades registered
    assert mock_exit_monitor.start_monitoring.call_count == 2

    # Verify recovery alert sent
    mock_bot.send_alert.assert_awaited()
    recovery_msg = mock_bot.send_alert.call_args[0][0]
    assert "recovered" in recovery_msg.lower() or "resumed" in recovery_msg.lower()

    # Verify scheduler was configured and started
    mock_scheduler.configure_jobs.assert_called_once_with(app)
    mock_scheduler.start.assert_called_once()

    # Verify start_scanning was called (which connects websocket)
    mock_start_scanning.assert_awaited_once()

    # Since phase is CONTINUOUS, new signals should be disabled
    assert app._accepting_signals is False


async def test_recovery_during_entry_window_accepts_signals(db, repos):
    """Recovery during ENTRY_WINDOW should keep signal generation enabled."""
    mock_bot = AsyncMock()
    mock_exit_monitor = MagicMock(
        check_trade=AsyncMock(),
        trigger_time_exit=AsyncMock(return_value=[]),
        start_monitoring=MagicMock(),
    )
    mock_scheduler = MagicMock()

    app = SignalPilotApp(
        db=db, signal_repo=repos["signal_repo"], trade_repo=repos["trade_repo"],
        config_repo=repos["config_repo"], metrics_calculator=repos["metrics"],
        authenticator=AsyncMock(), instruments=AsyncMock(),
        market_data=_make_mock_market_data(), historical=_make_mock_historical(),
        websocket=AsyncMock(),
        strategy=AsyncMock(), ranker=MagicMock(), risk_manager=MagicMock(),
        exit_monitor=mock_exit_monitor, bot=mock_bot, scheduler=mock_scheduler,
    )

    # Patch db.initialize to no-op to preserve in-memory DB state
    with patch.object(db, "initialize", new_callable=AsyncMock), \
         patch.object(app, "start_scanning", new_callable=AsyncMock), \
         patch(
             "signalpilot.scheduler.lifecycle.get_current_phase",
             return_value=StrategyPhase.ENTRY_WINDOW,
         ):
        await app.recover()

    # During ENTRY_WINDOW, accepting_signals should remain True
    # (start_scanning sets it to True, and recovery does NOT disable it)
    assert app._accepting_signals is True
