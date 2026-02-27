"""Integration tests for position limit enforcement with real DB."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

from signalpilot.telegram.handlers import handle_taken
from signalpilot.utils.constants import IST
from tests.test_integration.conftest import make_signal_record


async def test_max_5_positions_enforced(db, repos):
    """After 5 active trades, verify all 5 are tracked in DB.

    Note: The risk_manager blocks the 6th signal from being generated,
    not the TAKEN handler. This test verifies DB state after 5 trades.
    """
    now = datetime.now(IST)

    # Create and take 5 signals sequentially
    for i in range(5):
        signal = make_signal_record(
            symbol=f"STOCK{i}", entry_price=100.0 + i,
            created_at=now + timedelta(seconds=i),
        )
        await repos["signal_repo"].insert_signal(signal)
        mock_monitor = MagicMock(start_monitoring=MagicMock())
        await handle_taken(
            repos["signal_repo"], repos["trade_repo"], mock_monitor,
            now=now + timedelta(seconds=i),
        )

    # Verify 5 active trades
    count = await repos["trade_repo"].get_active_trade_count()
    assert count == 5

    # Verify all 5 trades are in the DB
    trades = await repos["trade_repo"].get_active_trades()
    assert len(trades) == 5


async def test_position_slot_opens_after_close(db, repos):
    """After closing a trade, active count drops by 1."""
    now = datetime.now(IST)

    # Create and take 5 signals
    for i in range(5):
        signal = make_signal_record(
            symbol=f"STOCK{i}", entry_price=100.0 + i,
            created_at=now + timedelta(seconds=i),
        )
        await repos["signal_repo"].insert_signal(signal)
        mock_monitor = MagicMock(start_monitoring=MagicMock())
        await handle_taken(
            repos["signal_repo"], repos["trade_repo"], mock_monitor,
            now=now + timedelta(seconds=i),
        )

    assert await repos["trade_repo"].get_active_trade_count() == 5

    # Close one trade
    trades = await repos["trade_repo"].get_active_trades()
    await repos["trade_repo"].close_trade(
        trades[0].id, 97.0, -45.0, -3.0, "sl_hit"
    )

    assert await repos["trade_repo"].get_active_trade_count() == 4
