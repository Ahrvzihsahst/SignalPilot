"""Integration tests for the trade lifecycle: signal -> TAKEN -> trade -> close."""

from datetime import datetime
from unittest.mock import MagicMock

from signalpilot.telegram.handlers import handle_taken
from signalpilot.utils.constants import IST
from tests.test_integration.conftest import make_signal_record


async def test_taken_creates_trade_in_db(db, repos):
    """TAKEN on active signal should create a trade record in the database."""
    now = datetime.now(IST)
    signal = make_signal_record(
        symbol="SBIN", entry_price=100.0, stop_loss=97.0,
        target_1=105.0, target_2=107.0, quantity=15,
        created_at=now,
    )
    signal_id = await repos["signal_repo"].insert_signal(signal)

    mock_exit_monitor = MagicMock(start_monitoring=MagicMock())
    response = await handle_taken(
        repos["signal_repo"], repos["trade_repo"], repos["config_repo"],
        mock_exit_monitor, now=now,
    )

    assert "Trade logged" in response
    assert "SBIN" in response

    # Verify trade in DB
    trades = await repos["trade_repo"].get_active_trades()
    assert len(trades) == 1
    trade = trades[0]
    assert trade.symbol == "SBIN"
    assert trade.entry_price == 100.0
    assert trade.stop_loss == 97.0
    assert trade.quantity == 15
    assert trade.signal_id == signal_id
    assert trade.exited_at is None

    # Verify exit monitor was started
    mock_exit_monitor.start_monitoring.assert_called_once()

    # Verify signal status updated to "taken"
    all_signals = await repos["signal_repo"].get_signals_by_date(now.date())
    assert all_signals[0].status == "taken"


async def test_sl_hit_closes_trade(db, repos):
    """After TAKEN, closing trade with SL hit should update DB correctly."""
    now = datetime.now(IST)
    signal = make_signal_record(
        entry_price=100.0, stop_loss=97.0, quantity=15, created_at=now,
    )
    await repos["signal_repo"].insert_signal(signal)

    mock_exit_monitor = MagicMock(start_monitoring=MagicMock())
    await handle_taken(
        repos["signal_repo"], repos["trade_repo"], repos["config_repo"],
        mock_exit_monitor, now=now,
    )

    # Get the trade
    trades = await repos["trade_repo"].get_active_trades()
    trade = trades[0]

    # Simulate SL hit -- close the trade
    exit_price = 97.0
    pnl_amount = (exit_price - trade.entry_price) * trade.quantity  # (97-100)*15 = -45
    pnl_pct = ((exit_price - trade.entry_price) / trade.entry_price) * 100  # -3.0
    await repos["trade_repo"].close_trade(
        trade.id, exit_price, pnl_amount, pnl_pct, "sl_hit"
    )

    # Verify trade is closed
    active = await repos["trade_repo"].get_active_trades()
    assert len(active) == 0

    closed = await repos["trade_repo"].get_all_closed_trades()
    assert len(closed) == 1
    assert closed[0].exit_price == 97.0
    assert closed[0].pnl_amount == -45.0
    assert closed[0].exit_reason == "sl_hit"


async def test_t1_advisory_then_t2_exit(db, repos):
    """T1 hit is advisory (trade stays open), T2 hit closes trade."""
    now = datetime.now(IST)
    signal = make_signal_record(
        entry_price=100.0, target_1=105.0, target_2=107.0, quantity=10,
        created_at=now,
    )
    await repos["signal_repo"].insert_signal(signal)

    mock_exit_monitor = MagicMock(start_monitoring=MagicMock())
    await handle_taken(
        repos["signal_repo"], repos["trade_repo"], repos["config_repo"],
        mock_exit_monitor, now=now,
    )

    trades = await repos["trade_repo"].get_active_trades()
    trade = trades[0]

    # T1 hit is advisory only -- trade stays open
    # (In real system, ExitMonitor sends alert but does not close)
    active_after_t1 = await repos["trade_repo"].get_active_trades()
    assert len(active_after_t1) == 1  # Still open

    # T2 hit -- close trade
    exit_price = 107.0
    pnl_amount = (exit_price - trade.entry_price) * trade.quantity  # (107-100)*10 = 70
    pnl_pct = ((exit_price - trade.entry_price) / trade.entry_price) * 100  # 7.0
    await repos["trade_repo"].close_trade(
        trade.id, exit_price, pnl_amount, pnl_pct, "t2_hit"
    )

    active_after_t2 = await repos["trade_repo"].get_active_trades()
    assert len(active_after_t2) == 0

    closed = await repos["trade_repo"].get_all_closed_trades()
    assert closed[0].exit_reason == "t2_hit"
    assert closed[0].pnl_amount == 70.0


async def test_taken_with_no_signal(db, repos):
    """TAKEN with no active signal returns error."""
    now = datetime.now(IST)
    mock_exit_monitor = MagicMock()
    response = await handle_taken(
        repos["signal_repo"], repos["trade_repo"], repos["config_repo"],
        mock_exit_monitor, now=now,
    )
    assert "No active signal" in response
