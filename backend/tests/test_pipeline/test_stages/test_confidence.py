"""Tests for ConfidenceStage."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from signalpilot.db.models import CandidateSignal, SignalDirection
from signalpilot.pipeline.context import ScanContext
from signalpilot.pipeline.stages.confidence import ConfidenceStage
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


async def test_no_op_when_detector_is_none():
    """Stage should be a no-op when confidence_detector is not configured."""
    stage = ConfidenceStage(confidence_detector=None)
    ctx = ScanContext(
        now=datetime.now(IST),
        all_candidates=[_make_candidate()],
    )
    result = await stage.process(ctx)
    assert result.confirmation_map is None


async def test_no_op_when_no_candidates():
    """Stage should be a no-op when there are no candidates."""
    detector = AsyncMock()
    stage = ConfidenceStage(confidence_detector=detector)
    ctx = ScanContext(now=datetime.now(IST), all_candidates=[])
    result = await stage.process(ctx)
    assert result.confirmation_map is None


async def test_builds_confirmation_map():
    """Stage should build a symbol -> ConfirmationResult map."""
    candidate = _make_candidate()
    mock_result = MagicMock()
    mock_result.confirmation_level = "multi"
    mock_result.confirmed_by = ["Gap & Go", "ORB"]

    detector = AsyncMock()
    detector.detect_confirmations = AsyncMock(return_value=[(candidate, mock_result)])

    stage = ConfidenceStage(confidence_detector=detector)
    ctx = ScanContext(now=datetime.now(IST), all_candidates=[candidate])
    result = await stage.process(ctx)

    assert result.confirmation_map is not None
    assert "SBIN" in result.confirmation_map
    assert result.confirmation_map["SBIN"] is mock_result
