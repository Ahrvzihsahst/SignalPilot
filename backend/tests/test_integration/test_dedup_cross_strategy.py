"""Integration tests for cross-strategy deduplication."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from signalpilot.monitor.duplicate_checker import DuplicateChecker
from signalpilot.scheduler.lifecycle import SignalPilotApp
from signalpilot.utils.constants import IST
from signalpilot.utils.market_calendar import StrategyPhase
from tests.test_integration.conftest import make_final_signal_for_strategy, make_mock_strategy, make_signal_record


async def test_duplicate_checker_blocks_same_stock_across_strategies(db, repos):
    """If Gap & Go already signaled SBIN today, ORB should not signal SBIN."""
    now = datetime.now(IST)

    # Insert existing Gap & Go signal for SBIN
    existing = make_signal_record(symbol="SBIN", created_at=now, status="sent")
    await repos["signal_repo"].insert_signal(existing)

    # Now create ORB candidate for SBIN and TCS
    from signalpilot.db.models import CandidateSignal, SignalDirection

    orb_candidates = [
        CandidateSignal(
            symbol="SBIN",
            direction=SignalDirection.BUY,
            strategy_name="ORB",
            entry_price=520.0,
            stop_loss=510.0,
            target_1=530.0,
            target_2=540.0,
        ),
        CandidateSignal(
            symbol="TCS",
            direction=SignalDirection.BUY,
            strategy_name="ORB",
            entry_price=3500.0,
            stop_loss=3400.0,
            target_1=3600.0,
            target_2=3700.0,
        ),
    ]

    checker = DuplicateChecker(repos["signal_repo"], repos["trade_repo"])
    filtered = await checker.filter_duplicates(orb_candidates, now.date())

    # SBIN should be blocked (already signaled), TCS should pass
    assert len(filtered) == 1
    assert filtered[0].symbol == "TCS"


async def test_active_trade_blocks_all_strategies(db, repos):
    """If stock has an active trade, no strategy can signal it."""
    now = datetime.now(IST)

    # Insert a signal first (trade FK requires it), then an active trade for RELIANCE
    signal_record = make_signal_record(symbol="RELIANCE", created_at=now, status="taken")
    signal_id = await repos["signal_repo"].insert_signal(signal_record)

    from tests.test_integration.conftest import make_trade_record

    trade = make_trade_record(signal_id=signal_id, symbol="RELIANCE", taken_at=now)
    await repos["trade_repo"].insert_trade(trade)

    from signalpilot.db.models import CandidateSignal, SignalDirection

    candidates = [
        CandidateSignal(
            symbol="RELIANCE",
            direction=SignalDirection.BUY,
            strategy_name="Gap & Go",
            entry_price=2500.0,
            stop_loss=2400.0,
            target_1=2600.0,
            target_2=2700.0,
        ),
        CandidateSignal(
            symbol="RELIANCE",
            direction=SignalDirection.BUY,
            strategy_name="ORB",
            entry_price=2505.0,
            stop_loss=2405.0,
            target_1=2605.0,
            target_2=2705.0,
        ),
        CandidateSignal(
            symbol="INFY",
            direction=SignalDirection.BUY,
            strategy_name="VWAP Reversal",
            entry_price=1500.0,
            stop_loss=1450.0,
            target_1=1550.0,
            target_2=1600.0,
        ),
    ]

    checker = DuplicateChecker(repos["signal_repo"], repos["trade_repo"])
    filtered = await checker.filter_duplicates(candidates, now.date())

    # Both RELIANCE candidates blocked, INFY passes
    assert len(filtered) == 1
    assert filtered[0].symbol == "INFY"


async def test_dedup_in_scan_loop_suppresses_second_strategy(db, repos):
    """Scan loop uses DuplicateChecker to suppress SBIN from ORB after Gap & Go signals it."""
    now = datetime.now(IST)

    # Gap & Go already signaled SBIN (insert into DB)
    existing = make_signal_record(symbol="SBIN", created_at=now, status="sent")
    await repos["signal_repo"].insert_signal(existing)

    # ORB produces candidates for SBIN + TCS
    from signalpilot.db.models import CandidateSignal, SignalDirection

    orb_candidates = [
        CandidateSignal(
            symbol="SBIN",
            direction=SignalDirection.BUY,
            strategy_name="ORB",
            entry_price=520.0,
            stop_loss=510.0,
            target_1=530.0,
            target_2=540.0,
        ),
        CandidateSignal(
            symbol="TCS",
            direction=SignalDirection.BUY,
            strategy_name="ORB",
            entry_price=3500.0,
            stop_loss=3400.0,
            target_1=3600.0,
            target_2=3700.0,
        ),
    ]

    orb_signal = make_final_signal_for_strategy("ORB", symbol="TCS", generated_at=now)

    orb_strat = make_mock_strategy(
        "ORB",
        [StrategyPhase.OPENING, StrategyPhase.ENTRY_WINDOW],
        orb_candidates,
    )

    mock_ranker = MagicMock(rank=MagicMock(return_value=["r1"]))
    mock_risk = MagicMock(filter_and_size=MagicMock(return_value=[orb_signal]))
    mock_bot = AsyncMock()

    checker = DuplicateChecker(repos["signal_repo"], repos["trade_repo"])

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
        strategies=[orb_strat],
        ranker=mock_ranker,
        risk_manager=mock_risk,
        exit_monitor=MagicMock(check_trade=AsyncMock()),
        bot=mock_bot,
        scheduler=MagicMock(),
        duplicate_checker=checker,
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

    # Ranker should receive only TCS (SBIN filtered by DuplicateChecker)
    mock_ranker.rank.assert_called_once()
    ranked_args = mock_ranker.rank.call_args[0][0]
    ranked_symbols = [c.symbol for c in ranked_args]
    assert "SBIN" not in ranked_symbols
    assert "TCS" in ranked_symbols
