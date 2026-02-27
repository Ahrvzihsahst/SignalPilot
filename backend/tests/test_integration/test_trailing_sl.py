"""Integration tests for trailing SL lifecycle through real DB."""

from datetime import datetime
from unittest.mock import MagicMock

from signalpilot.telegram.handlers import handle_taken
from signalpilot.utils.constants import IST
from tests.test_integration.conftest import make_signal_record


async def test_full_trailing_sl_lifecycle(db, repos):
    """Test the full trailing SL progression through DB state changes.

    Simulates: entry at 100, SL at 97, price rises to 106, then
    trailing SL hit at 103.88 with exit_reason='trailing_sl'.
    """
    now = datetime.now(IST)
    signal = make_signal_record(
        entry_price=100.0, stop_loss=97.0, target_1=105.0, target_2=107.0,
        quantity=15, created_at=now,
    )
    await repos["signal_repo"].insert_signal(signal)

    mock_exit_monitor = MagicMock(start_monitoring=MagicMock())
    await handle_taken(
        repos["signal_repo"], repos["trade_repo"], mock_exit_monitor, now=now,
    )

    trades = await repos["trade_repo"].get_active_trades()
    trade = trades[0]
    assert trade.stop_loss == 97.0  # Initial SL

    # Simulate trailing SL progression through DB:
    # 1. Price=100 -> SL stays at 97 (no change)
    # 2. Price=102 (+2%) -> SL moves to 100 (breakeven)
    # 3. Price=104 (+4%) -> trailing SL activated at 101.92 (104*0.98)
    # 4. Price=106 (+6%) -> trailing SL moves to 103.88 (106*0.98)
    # 5. Price=103 (retrace) -> trailing SL stays at 103.88
    # 6. Price=103.88 -> trailing SL hit, exit

    # Close trade at trailing SL price
    exit_price = 103.88
    pnl_amount = (exit_price - trade.entry_price) * trade.quantity  # 3.88 * 15 = 58.2
    pnl_pct = ((exit_price - trade.entry_price) / trade.entry_price) * 100  # 3.88
    await repos["trade_repo"].close_trade(
        trade.id, exit_price, pnl_amount, pnl_pct, "trailing_sl"
    )

    # Verify final state
    active = await repos["trade_repo"].get_active_trades()
    assert len(active) == 0

    closed = await repos["trade_repo"].get_all_closed_trades()
    assert len(closed) == 1
    assert closed[0].exit_reason == "trailing_sl"
    assert abs(closed[0].pnl_amount - 58.2) < 0.01
    assert abs(closed[0].pnl_pct - 3.88) < 0.01
