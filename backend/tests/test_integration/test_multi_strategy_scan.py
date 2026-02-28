"""Integration tests for multi-strategy scanning in the scan loop."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from signalpilot.scheduler.lifecycle import SignalPilotApp
from signalpilot.utils.constants import IST
from signalpilot.utils.market_calendar import StrategyPhase
from tests.test_integration.conftest import make_final_signal_for_strategy, make_mock_strategy


async def test_multi_strategy_all_evaluated_during_opening(db, repos):
    """All 3 strategies are evaluated during OPENING phase if they include it."""
    now = datetime.now(IST)
    gap_signal = make_final_signal_for_strategy("Gap & Go", symbol="SBIN", generated_at=now)
    orb_signal = make_final_signal_for_strategy("ORB", symbol="TCS", generated_at=now)

    gap_strat = make_mock_strategy(
        "Gap & Go",
        [StrategyPhase.OPENING, StrategyPhase.ENTRY_WINDOW],
        ["gap_candidate"],
    )
    orb_strat = make_mock_strategy(
        "ORB",
        [StrategyPhase.OPENING, StrategyPhase.ENTRY_WINDOW],
        ["orb_candidate"],
    )
    vwap_strat = make_mock_strategy(
        "VWAP Reversal",
        [StrategyPhase.CONTINUOUS],
        ["vwap_candidate"],
    )

    mock_bot = AsyncMock()
    mock_ranker = MagicMock(rank=MagicMock(return_value=["r1", "r2"]))
    mock_risk = MagicMock(filter_and_size=MagicMock(return_value=[gap_signal, orb_signal]))

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
        strategies=[gap_strat, orb_strat, vwap_strat],
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

    # Gap & Go and ORB are active during OPENING, VWAP is not (CONTINUOUS only)
    gap_strat.evaluate.assert_awaited_once()
    orb_strat.evaluate.assert_awaited_once()
    vwap_strat.evaluate.assert_not_awaited()

    # 2 signals stored
    signals = await repos["signal_repo"].get_signals_by_date(now.date())
    assert len(signals) == 2
    symbols = {s.symbol for s in signals}
    assert symbols == {"SBIN", "TCS"}


async def test_vwap_evaluated_during_continuous(db, repos):
    """VWAP strategy is evaluated during CONTINUOUS phase."""
    now = datetime.now(IST)
    vwap_signal = make_final_signal_for_strategy(
        "VWAP Reversal", symbol="INFY", generated_at=now,
        setup_type="uptrend_pullback",
    )

    gap_strat = make_mock_strategy(
        "Gap & Go", [StrategyPhase.OPENING, StrategyPhase.ENTRY_WINDOW],
    )
    orb_strat = make_mock_strategy(
        "ORB", [StrategyPhase.OPENING, StrategyPhase.ENTRY_WINDOW],
    )
    vwap_strat = make_mock_strategy(
        "VWAP Reversal", [StrategyPhase.CONTINUOUS], ["vwap_candidate"],
    )

    mock_bot = AsyncMock()
    mock_ranker = MagicMock(rank=MagicMock(return_value=["r1"]))
    mock_risk = MagicMock(filter_and_size=MagicMock(return_value=[vwap_signal]))

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
        strategies=[gap_strat, orb_strat, vwap_strat],
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

    # Only VWAP is active during CONTINUOUS
    gap_strat.evaluate.assert_not_awaited()
    orb_strat.evaluate.assert_not_awaited()
    vwap_strat.evaluate.assert_awaited_once()

    signals = await repos["signal_repo"].get_signals_by_date(now.date())
    assert len(signals) == 1
    assert signals[0].symbol == "INFY"


async def test_candidates_merged_across_strategies(db, repos):
    """Candidates from multiple strategies are merged before ranking."""
    now = datetime.now(IST)
    final_signals = [
        make_final_signal_for_strategy("Gap & Go", symbol="SBIN", generated_at=now),
        make_final_signal_for_strategy("ORB", symbol="TCS", generated_at=now),
    ]

    gap_strat = make_mock_strategy(
        "Gap & Go",
        [StrategyPhase.OPENING, StrategyPhase.ENTRY_WINDOW],
        ["gap_c1"],
    )
    orb_strat = make_mock_strategy(
        "ORB",
        [StrategyPhase.OPENING, StrategyPhase.ENTRY_WINDOW],
        ["orb_c1"],
    )

    mock_ranker = MagicMock(rank=MagicMock(return_value=["r1", "r2"]))
    mock_risk = MagicMock(filter_and_size=MagicMock(return_value=final_signals))
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

    # Ranker received merged candidates (2 from 2 strategies)
    mock_ranker.rank.assert_called_once()
    args = mock_ranker.rank.call_args[0][0]
    assert len(args) == 2  # gap_c1 + orb_c1
