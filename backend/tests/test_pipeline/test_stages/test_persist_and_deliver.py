"""Tests for PersistAndDeliverStage."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from signalpilot.db.models import (
    CandidateSignal,
    FinalSignal,
    RankedSignal,
    SignalDirection,
)
from signalpilot.pipeline.context import ScanContext
from signalpilot.pipeline.stages.persist_and_deliver import PersistAndDeliverStage
from signalpilot.utils.constants import IST
from signalpilot.utils.market_calendar import StrategyPhase


def _make_final_signal(symbol="SBIN", strategy_name="Gap & Go"):
    candidate = CandidateSignal(
        symbol=symbol,
        direction=SignalDirection.BUY,
        strategy_name=strategy_name,
        entry_price=100.0,
        stop_loss=97.0,
        target_1=105.0,
        target_2=107.0,
        generated_at=datetime(2025, 1, 6, 9, 35, 0, tzinfo=IST),
    )
    ranked = RankedSignal(candidate=candidate, composite_score=0.8, rank=1, signal_strength=4)
    return FinalSignal(
        ranked_signal=ranked,
        quantity=10,
        capital_required=1000.0,
        expires_at=datetime(2025, 1, 6, 10, 5, 0, tzinfo=IST),
    )


async def test_persists_and_sends_signal():
    """Stage should insert signal into DB and send via bot."""
    signal_repo = AsyncMock()
    signal_repo.insert_signal = AsyncMock(return_value=42)
    bot = AsyncMock()
    app_config = SimpleNamespace(orb_paper_mode=False, vwap_paper_mode=False)

    stage = PersistAndDeliverStage(
        signal_repo=signal_repo,
        hybrid_score_repo=None,
        bot=bot,
        adaptive_manager=None,
        app_config=app_config,
    )

    signal = _make_final_signal()
    ctx = ScanContext(
        now=datetime.now(IST),
        phase=StrategyPhase.OPENING,
        cycle_id="abc123",
        final_signals=[signal],
    )
    await stage.process(ctx)

    signal_repo.insert_signal.assert_awaited_once()
    bot.send_signal.assert_awaited_once()

    # Verify signal_id was passed
    call_kwargs = bot.send_signal.call_args[1]
    assert call_kwargs["signal_id"] == 42


async def test_no_op_when_no_final_signals():
    """Stage should be a no-op when there are no final signals."""
    signal_repo = AsyncMock()
    bot = AsyncMock()

    stage = PersistAndDeliverStage(
        signal_repo=signal_repo,
        hybrid_score_repo=None,
        bot=bot,
        adaptive_manager=None,
        app_config=None,
    )
    ctx = ScanContext(now=datetime.now(IST), final_signals=[])
    await stage.process(ctx)

    signal_repo.insert_signal.assert_not_awaited()
    bot.send_signal.assert_not_awaited()


async def test_paper_mode_sets_paper_status():
    """ORB signal with paper mode should be saved with status='paper'."""
    signal_repo = AsyncMock()
    signal_repo.insert_signal = AsyncMock(return_value=1)
    bot = AsyncMock()
    app_config = SimpleNamespace(orb_paper_mode=True, vwap_paper_mode=False)

    stage = PersistAndDeliverStage(
        signal_repo=signal_repo,
        hybrid_score_repo=None,
        bot=bot,
        adaptive_manager=None,
        app_config=app_config,
    )

    signal = _make_final_signal(strategy_name="ORB")
    ctx = ScanContext(
        now=datetime.now(IST),
        phase=StrategyPhase.OPENING,
        cycle_id="abc",
        final_signals=[signal],
    )
    await stage.process(ctx)

    record = signal_repo.insert_signal.call_args[0][0]
    assert record.status == "paper"
    bot.send_signal.assert_awaited_once()
    assert bot.send_signal.call_args[1]["is_paper"] is True
