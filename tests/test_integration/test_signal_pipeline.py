"""Integration tests for the full signal pipeline.

Tests: strategy -> ranker -> risk_manager -> DB + telegram.
Uses real DB (SQLite in-memory) and mocked upstream components.
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from signalpilot.scheduler.lifecycle import SignalPilotApp
from signalpilot.utils.constants import IST
from signalpilot.utils.market_calendar import StrategyPhase

from tests.test_integration.conftest import make_final_signal, make_signal_record


async def test_valid_signal_stored_and_sent(db, repos):
    """Mock strategy returns candidates, ranker ranks them, risk_manager sizes
    them. Run one scan loop iteration. Verify signal is in DB and bot.send_signal
    was called."""
    now = datetime.now(IST)
    signal = make_final_signal(generated_at=now)

    mock_bot = AsyncMock()
    mock_strategy = AsyncMock(evaluate=AsyncMock(return_value=["candidate"]))
    mock_ranker = MagicMock(rank=MagicMock(return_value=["ranked"]))
    mock_risk = MagicMock(filter_and_size=MagicMock(return_value=[signal]))

    # Initialize user config so get_user_config returns a value
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
        strategy=mock_strategy,
        ranker=mock_ranker,
        risk_manager=mock_risk,
        exit_monitor=MagicMock(check_all_trades=AsyncMock()),
        bot=mock_bot,
        scheduler=MagicMock(),
    )

    # Run exactly 1 iteration then stop
    original_sleep = asyncio.sleep

    async def stop_after_one(s):
        app._scanning = False
        await original_sleep(0)

    with patch(
        "signalpilot.scheduler.lifecycle.get_current_phase",
        return_value=StrategyPhase.OPENING,
    ), patch("asyncio.sleep", side_effect=stop_after_one):
        app._scanning = True
        app._accepting_signals = True
        await app._scan_loop()

    # Verify signal stored in DB
    signals = await repos["signal_repo"].get_signals_by_date(now.date())
    assert len(signals) == 1
    assert signals[0].symbol == "SBIN"
    assert signals[0].entry_price == 100.0
    assert signals[0].status == "sent"

    # Verify bot was called
    mock_bot.send_signal.assert_awaited_once_with(signal)


async def test_no_candidates_no_signal(db, repos):
    """Strategy returns empty list. Verify no signals in DB."""
    mock_strategy = AsyncMock(evaluate=AsyncMock(return_value=[]))
    await repos["config_repo"].initialize_default("123")

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
        strategy=mock_strategy,
        ranker=MagicMock(),
        risk_manager=MagicMock(),
        exit_monitor=MagicMock(check_all_trades=AsyncMock()),
        bot=AsyncMock(),
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

    signals = await repos["signal_repo"].get_signals_by_date(datetime.now(IST).date())
    assert len(signals) == 0


async def test_multiple_signals_all_stored(db, repos):
    """Strategy produces 3 candidates -> 3 final signals. All 3 stored in DB."""
    now = datetime.now(IST)
    final_signals = [
        make_final_signal(symbol="SBIN", entry_price=100.0, generated_at=now),
        make_final_signal(symbol="TCS", entry_price=200.0, generated_at=now),
        make_final_signal(symbol="RELIANCE", entry_price=300.0, generated_at=now),
    ]

    mock_bot = AsyncMock()
    mock_strategy = AsyncMock(evaluate=AsyncMock(return_value=["c1", "c2", "c3"]))
    mock_ranker = MagicMock(rank=MagicMock(return_value=["r1", "r2", "r3"]))
    mock_risk = MagicMock(filter_and_size=MagicMock(return_value=final_signals))

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
        strategy=mock_strategy,
        ranker=mock_ranker,
        risk_manager=mock_risk,
        exit_monitor=MagicMock(check_all_trades=AsyncMock()),
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

    signals = await repos["signal_repo"].get_signals_by_date(now.date())
    assert len(signals) == 3
    symbols = {s.symbol for s in signals}
    assert symbols == {"SBIN", "TCS", "RELIANCE"}

    # Bot called 3 times
    assert mock_bot.send_signal.await_count == 3


async def test_signal_not_generated_during_continuous(db, repos):
    """Strategy returns candidates but phase is CONTINUOUS. No signals generated."""
    mock_strategy = AsyncMock(evaluate=AsyncMock(return_value=["candidate"]))
    await repos["config_repo"].initialize_default("123")

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
        strategy=mock_strategy,
        ranker=MagicMock(),
        risk_manager=MagicMock(),
        exit_monitor=MagicMock(check_all_trades=AsyncMock()),
        bot=AsyncMock(),
        scheduler=MagicMock(),
    )

    original_sleep = asyncio.sleep

    async def stop(s):
        app._scanning = False
        await original_sleep(0)

    with patch(
        "signalpilot.scheduler.lifecycle.get_current_phase",
        return_value=StrategyPhase.CONTINUOUS,
    ), patch("asyncio.sleep", side_effect=stop):
        app._scanning = True
        app._accepting_signals = True
        await app._scan_loop()

    # Strategy should not even be called during CONTINUOUS phase
    mock_strategy.evaluate.assert_not_awaited()
