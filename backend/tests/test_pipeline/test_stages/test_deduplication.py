"""Tests for DeduplicationStage."""

from datetime import datetime
from unittest.mock import AsyncMock

from signalpilot.db.models import CandidateSignal, SignalDirection
from signalpilot.pipeline.context import ScanContext
from signalpilot.pipeline.stages.deduplication import DeduplicationStage
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


async def test_no_op_when_checker_is_none():
    """Stage should be a no-op when duplicate_checker is not configured."""
    stage = DeduplicationStage(duplicate_checker=None)
    candidates = [_make_candidate()]
    ctx = ScanContext(now=datetime.now(IST), all_candidates=candidates)
    result = await stage.process(ctx)
    assert result.all_candidates == candidates


async def test_no_op_when_no_candidates():
    """Stage should be a no-op when there are no candidates."""
    checker = AsyncMock()
    stage = DeduplicationStage(duplicate_checker=checker)
    ctx = ScanContext(now=datetime.now(IST), all_candidates=[])
    result = await stage.process(ctx)
    assert result.all_candidates == []
    checker.filter_duplicates.assert_not_awaited()


async def test_filters_duplicates():
    """Stage should delegate to duplicate_checker and update candidates."""
    c1 = _make_candidate("SBIN")
    c2 = _make_candidate("TCS")
    checker = AsyncMock()
    checker.filter_duplicates = AsyncMock(return_value=[c1])

    stage = DeduplicationStage(duplicate_checker=checker)
    ctx = ScanContext(now=datetime.now(IST), all_candidates=[c1, c2])
    result = await stage.process(ctx)

    assert result.all_candidates == [c1]
    checker.filter_duplicates.assert_awaited_once()
