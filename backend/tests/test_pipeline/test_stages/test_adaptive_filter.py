"""Tests for AdaptiveFilterStage."""

from datetime import datetime
from unittest.mock import MagicMock

from signalpilot.db.models import CandidateSignal, SignalDirection
from signalpilot.pipeline.context import ScanContext
from signalpilot.pipeline.stages.adaptive_filter import AdaptiveFilterStage
from signalpilot.utils.constants import IST


def _make_candidate(symbol="SBIN", strategy_name="Gap & Go"):
    return CandidateSignal(
        symbol=symbol,
        direction=SignalDirection.BUY,
        strategy_name=strategy_name,
        entry_price=100.0,
        stop_loss=97.0,
        target_1=105.0,
        target_2=107.0,
    )


async def test_no_op_when_manager_is_none():
    """Stage should be a no-op when adaptive_manager is not configured."""
    stage = AdaptiveFilterStage(adaptive_manager=None)
    candidates = [_make_candidate()]
    ctx = ScanContext(now=datetime.now(IST), all_candidates=candidates)
    result = await stage.process(ctx)
    assert result.all_candidates == candidates


async def test_no_op_when_no_candidates():
    """Stage should be a no-op when there are no candidates."""
    mgr = MagicMock()
    stage = AdaptiveFilterStage(adaptive_manager=mgr)
    ctx = ScanContext(now=datetime.now(IST), all_candidates=[])
    result = await stage.process(ctx)
    assert result.all_candidates == []


async def test_allows_signal_through():
    """Signals allowed by adaptive manager should pass through."""
    mgr = MagicMock()
    mgr.should_allow_signal = MagicMock(return_value=True)

    candidates = [_make_candidate()]
    stage = AdaptiveFilterStage(adaptive_manager=mgr)
    ctx = ScanContext(now=datetime.now(IST), all_candidates=candidates)
    result = await stage.process(ctx)

    assert len(result.all_candidates) == 1


async def test_blocks_signal():
    """Signals blocked by adaptive manager should be filtered out."""
    mgr = MagicMock()
    mgr.should_allow_signal = MagicMock(return_value=False)

    candidates = [_make_candidate()]
    stage = AdaptiveFilterStage(adaptive_manager=mgr)
    ctx = ScanContext(now=datetime.now(IST), all_candidates=candidates)
    result = await stage.process(ctx)

    assert result.all_candidates == []


async def test_uses_composite_score_for_strength():
    """When composite_scores available, strength should be derived from score."""
    mgr = MagicMock()
    # Only allow strength >= 5 (score >= 80)
    mgr.should_allow_signal = MagicMock(side_effect=lambda name, strength: strength >= 5)

    c_high = _make_candidate("HIGH")
    c_low = _make_candidate("LOW")

    mock_score_high = MagicMock()
    mock_score_high.composite_score = 85.0
    mock_score_low = MagicMock()
    mock_score_low.composite_score = 45.0

    stage = AdaptiveFilterStage(adaptive_manager=mgr)
    ctx = ScanContext(
        now=datetime.now(IST),
        all_candidates=[c_high, c_low],
        composite_scores={"HIGH": mock_score_high, "LOW": mock_score_low},
    )
    result = await stage.process(ctx)

    assert len(result.all_candidates) == 1
    assert result.all_candidates[0].symbol == "HIGH"
