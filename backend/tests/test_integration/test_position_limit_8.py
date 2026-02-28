"""Integration tests for position limit of 8."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from signalpilot.scheduler.lifecycle import SignalPilotApp
from signalpilot.utils.constants import IST
from signalpilot.utils.market_calendar import StrategyPhase
from tests.test_integration.conftest import (
    make_final_signal_for_strategy,
    make_mock_strategy,
    make_signal_record,
    make_trade_record,
)


async def test_no_new_signals_at_8_active_trades(db, repos):
    """With 8 active trades, risk_manager should receive active_count=8 and not produce signals."""
    now = datetime.now(IST)

    # Insert 8 active trades (no exit) -- insert signal records first for FK
    for i in range(8):
        sig = make_signal_record(symbol=f"SYM{i}", created_at=now, status="taken")
        signal_id = await repos["signal_repo"].insert_signal(sig)
        trade = make_trade_record(
            signal_id=signal_id,
            symbol=f"SYM{i}",
            entry_price=100.0 + i,
            taken_at=now,
        )
        await repos["trade_repo"].insert_trade(trade)

    gap_strat = make_mock_strategy(
        "Gap & Go",
        [StrategyPhase.OPENING, StrategyPhase.ENTRY_WINDOW],
        ["candidate"],
    )
    mock_ranker = MagicMock(rank=MagicMock(return_value=["ranked"]))
    # Risk manager returns empty when positions are full
    mock_risk = MagicMock(filter_and_size=MagicMock(return_value=[]))
    mock_bot = AsyncMock()

    await repos["config_repo"].initialize_default("123", total_capital=50000.0)

    app = SignalPilotApp(
        db=db,
        signal_repo=repos["signal_repo"],
        trade_repo=repos["trade_repo"],
        config_repo=repos["config_repo"],
        metrics_calculator=repos["metrics"],
        authenticator=AsyncMock(),
        instruments=AsyncMock(),
        market_data=MagicMock(),
        historical=AsyncMock(),
        websocket=AsyncMock(),
        strategy=gap_strat,
        ranker=mock_ranker,
        risk_manager=mock_risk,
        exit_monitor=MagicMock(check_trade=AsyncMock()),
        bot=mock_bot,
        scheduler=MagicMock(),
    )

    original_sleep = asyncio.sleep

    async def stop(s):
        app._scanning = False
        await original_sleep(0)

    with patch(
        "signalpilot.scheduler.lifecycle.get_current_phase",
        return_value=StrategyPhase.OPENING,
    ), patch("asyncio.sleep", side_effect=stop):
        app._scanning = True
        app._accepting_signals = True
        await app._scan_loop()

    # Risk manager was called with active_count=8
    mock_risk.filter_and_size.assert_called_once()
    args = mock_risk.filter_and_size.call_args[0]
    assert args[2] == 8  # active_count

    # No signals sent
    mock_bot.send_signal.assert_not_awaited()


async def test_one_signal_allowed_at_7_active_trades(db, repos):
    """With 7 active trades, one more signal can be sent."""
    now = datetime.now(IST)

    # Insert 7 active trades -- insert signal records first for FK
    for i in range(7):
        sig = make_signal_record(symbol=f"SYM{i}", created_at=now, status="taken")
        signal_id = await repos["signal_repo"].insert_signal(sig)
        trade = make_trade_record(
            signal_id=signal_id,
            symbol=f"SYM{i}",
            entry_price=100.0 + i,
            taken_at=now,
        )
        await repos["trade_repo"].insert_trade(trade)

    signal = make_final_signal_for_strategy(
        "Gap & Go", symbol="NEWSTOCK", generated_at=now,
    )
    gap_strat = make_mock_strategy(
        "Gap & Go",
        [StrategyPhase.OPENING, StrategyPhase.ENTRY_WINDOW],
        ["candidate"],
    )
    mock_ranker = MagicMock(rank=MagicMock(return_value=["ranked"]))
    mock_risk = MagicMock(filter_and_size=MagicMock(return_value=[signal]))
    mock_bot = AsyncMock()

    await repos["config_repo"].initialize_default("123", total_capital=50000.0)

    app = SignalPilotApp(
        db=db,
        signal_repo=repos["signal_repo"],
        trade_repo=repos["trade_repo"],
        config_repo=repos["config_repo"],
        metrics_calculator=repos["metrics"],
        authenticator=AsyncMock(),
        instruments=AsyncMock(),
        market_data=MagicMock(),
        historical=AsyncMock(),
        websocket=AsyncMock(),
        strategy=gap_strat,
        ranker=mock_ranker,
        risk_manager=mock_risk,
        exit_monitor=MagicMock(check_trade=AsyncMock()),
        bot=mock_bot,
        scheduler=MagicMock(),
    )

    original_sleep = asyncio.sleep

    async def stop(s):
        app._scanning = False
        await original_sleep(0)

    with patch(
        "signalpilot.scheduler.lifecycle.get_current_phase",
        return_value=StrategyPhase.OPENING,
    ), patch("asyncio.sleep", side_effect=stop):
        app._scanning = True
        app._accepting_signals = True
        await app._scan_loop()

    # Risk manager was called with active_count=7
    args = mock_risk.filter_and_size.call_args[0]
    assert args[2] == 7

    # Signal sent
    mock_bot.send_signal.assert_awaited_once()
