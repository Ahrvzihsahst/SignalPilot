"""Integration tests for strategy pause/resume flow."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from signalpilot.scheduler.lifecycle import SignalPilotApp
from signalpilot.utils.constants import IST
from signalpilot.utils.market_calendar import StrategyPhase
from tests.test_integration.conftest import make_final_signal_for_strategy


def _make_mock_strategy(name, active_phases, evaluate_return=None):
    mock = AsyncMock(evaluate=AsyncMock(return_value=evaluate_return or []))
    mock.name = name
    mock.active_phases = active_phases
    return mock


async def test_paused_orb_not_evaluated(db, repos):
    """When ORB is disabled in user config, it should not be evaluated."""
    now = datetime.now(IST)

    gap_strat = _make_mock_strategy(
        "Gap & Go",
        [StrategyPhase.OPENING, StrategyPhase.ENTRY_WINDOW],
        ["gap_c"],
    )
    orb_strat = _make_mock_strategy(
        "ORB",
        [StrategyPhase.OPENING, StrategyPhase.ENTRY_WINDOW],
        ["orb_c"],
    )

    gap_signal = make_final_signal_for_strategy("Gap & Go", symbol="SBIN", generated_at=now)
    mock_ranker = MagicMock(rank=MagicMock(return_value=["r1"]))
    mock_risk = MagicMock(filter_and_size=MagicMock(return_value=[gap_signal]))
    mock_bot = AsyncMock()

    # Initialize with ORB disabled
    await repos["config_repo"].initialize_default("123", total_capital=50000.0)
    # Disable ORB
    conn = db.connection
    await conn.execute("UPDATE user_config SET orb_enabled = 0")
    await conn.commit()

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
        strategies=[gap_strat, orb_strat],
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

    # Gap & Go evaluated, ORB skipped
    gap_strat.evaluate.assert_awaited_once()
    orb_strat.evaluate.assert_not_awaited()


async def test_resumed_orb_evaluated(db, repos):
    """When ORB is re-enabled, it should be evaluated again."""
    now = datetime.now(IST)

    gap_strat = _make_mock_strategy(
        "Gap & Go",
        [StrategyPhase.OPENING, StrategyPhase.ENTRY_WINDOW],
        ["gap_c"],
    )
    orb_strat = _make_mock_strategy(
        "ORB",
        [StrategyPhase.OPENING, StrategyPhase.ENTRY_WINDOW],
        ["orb_c"],
    )

    signals = [
        make_final_signal_for_strategy("Gap & Go", symbol="SBIN", generated_at=now),
        make_final_signal_for_strategy("ORB", symbol="TCS", generated_at=now),
    ]
    mock_ranker = MagicMock(rank=MagicMock(return_value=["r1", "r2"]))
    mock_risk = MagicMock(filter_and_size=MagicMock(return_value=signals))
    mock_bot = AsyncMock()

    # Initialize with ORB enabled (default)
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
        strategies=[gap_strat, orb_strat],
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

    # Both strategies evaluated
    gap_strat.evaluate.assert_awaited_once()
    orb_strat.evaluate.assert_awaited_once()


async def test_paused_vwap_not_evaluated(db, repos):
    """When VWAP is disabled, it should not be evaluated during CONTINUOUS."""
    vwap_strat = _make_mock_strategy(
        "VWAP Reversal", [StrategyPhase.CONTINUOUS], ["vwap_c"],
    )
    gap_strat = _make_mock_strategy(
        "Gap & Go", [StrategyPhase.OPENING, StrategyPhase.ENTRY_WINDOW],
    )

    mock_ranker = MagicMock()
    mock_risk = MagicMock()
    mock_bot = AsyncMock()

    await repos["config_repo"].initialize_default("123", total_capital=50000.0)
    conn = db.connection
    await conn.execute("UPDATE user_config SET vwap_enabled = 0")
    await conn.commit()

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
        strategies=[gap_strat, vwap_strat],
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
        return_value=StrategyPhase.CONTINUOUS,
    ), patch("asyncio.sleep", side_effect=stop):
        app._scanning = True
        app._accepting_signals = True
        await app._scan_loop()

    # VWAP skipped
    vwap_strat.evaluate.assert_not_awaited()
