"""Tests for RankingStage."""

from datetime import datetime
from unittest.mock import MagicMock

from signalpilot.db.models import CandidateSignal, SignalDirection
from signalpilot.pipeline.context import ScanContext
from signalpilot.pipeline.stages.ranking import RankingStage
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


async def test_ranks_candidates():
    """Stage should call ranker.rank with candidates and scores."""
    ranker = MagicMock()
    ranker.rank = MagicMock(return_value=["ranked1", "ranked2"])

    stage = RankingStage(ranker)
    candidates = [_make_candidate("SBIN"), _make_candidate("TCS")]
    ctx = ScanContext(
        now=datetime.now(IST),
        all_candidates=candidates,
    )
    result = await stage.process(ctx)

    assert result.ranked_signals == ["ranked1", "ranked2"]
    ranker.rank.assert_called_once()


async def test_no_op_when_no_candidates():
    """Stage should be a no-op when there are no candidates."""
    ranker = MagicMock()
    stage = RankingStage(ranker)
    ctx = ScanContext(now=datetime.now(IST), all_candidates=[])
    result = await stage.process(ctx)

    assert result.ranked_signals == []
    ranker.rank.assert_not_called()


async def test_passes_composite_scores_and_confirmations():
    """Ranker should receive composite_scores and confirmation_map."""
    ranker = MagicMock()
    ranker.rank = MagicMock(return_value=[])
    scores = {"SBIN": MagicMock()}
    confs = {"SBIN": MagicMock()}

    stage = RankingStage(ranker)
    ctx = ScanContext(
        now=datetime.now(IST),
        all_candidates=[_make_candidate()],
        composite_scores=scores,
        confirmation_map=confs,
    )
    await stage.process(ctx)

    ranker.rank.assert_called_once()
    call_kwargs = ranker.rank.call_args[1]
    assert call_kwargs["composite_scores"] is scores
    assert call_kwargs["confirmations"] is confs
