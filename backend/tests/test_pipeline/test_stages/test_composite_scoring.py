"""Tests for CompositeScoringStage."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from signalpilot.db.models import CandidateSignal, SignalDirection
from signalpilot.pipeline.context import ScanContext
from signalpilot.pipeline.stages.composite_scoring import CompositeScoringStage
from signalpilot.utils.constants import IST


def _make_candidate(symbol="SBIN"):
    return CandidateSignal(
        symbol=symbol,
        direction=SignalDirection.BUY,
        strategy_name="Gap & Go",
        entry_price=100.0,
        stop_loss=97.0,
        target_1=105.0,
        target_2=107.0,
    )


async def test_no_op_when_scorer_is_none():
    """Stage should be a no-op when composite_scorer is not configured."""
    stage = CompositeScoringStage(composite_scorer=None)
    ctx = ScanContext(
        now=datetime.now(IST),
        all_candidates=[_make_candidate()],
    )
    result = await stage.process(ctx)
    assert result.composite_scores is None


async def test_no_op_when_no_candidates():
    """Stage should be a no-op when there are no candidates."""
    scorer = AsyncMock()
    stage = CompositeScoringStage(composite_scorer=scorer)
    ctx = ScanContext(now=datetime.now(IST), all_candidates=[])
    result = await stage.process(ctx)
    assert result.composite_scores is None


async def test_scores_candidates():
    """Stage should produce a symbol -> score map."""
    candidate = _make_candidate()
    mock_score = MagicMock()
    mock_score.composite_score = 75.0

    scorer = AsyncMock()
    scorer.score = AsyncMock(return_value=mock_score)

    stage = CompositeScoringStage(composite_scorer=scorer)
    ctx = ScanContext(
        now=datetime.now(IST),
        all_candidates=[candidate],
    )
    result = await stage.process(ctx)

    assert result.composite_scores is not None
    assert "SBIN" in result.composite_scores
    assert result.composite_scores["SBIN"] is mock_score


async def test_uses_confirmation_map_when_available():
    """Stage should pass confirmation to scorer when available."""
    candidate = _make_candidate()
    mock_conf = MagicMock()
    mock_score = MagicMock()
    mock_score.composite_score = 80.0

    scorer = AsyncMock()
    scorer.score = AsyncMock(return_value=mock_score)

    stage = CompositeScoringStage(composite_scorer=scorer)
    ctx = ScanContext(
        now=datetime.now(IST),
        all_candidates=[candidate],
        confirmation_map={"SBIN": mock_conf},
    )
    await stage.process(ctx)

    # Verify the confirmation was passed to the scorer
    call_args = scorer.score.call_args
    assert call_args[0][1] is mock_conf
