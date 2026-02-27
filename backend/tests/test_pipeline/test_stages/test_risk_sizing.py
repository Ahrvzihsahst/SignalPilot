"""Tests for RiskSizingStage."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from signalpilot.db.models import UserConfig
from signalpilot.pipeline.context import ScanContext
from signalpilot.pipeline.stages.risk_sizing import RiskSizingStage
from signalpilot.utils.constants import IST


async def test_sizes_ranked_signals():
    """Stage should call risk_manager.filter_and_size with ranked signals."""
    risk_manager = MagicMock()
    risk_manager.filter_and_size = MagicMock(return_value=["final1"])
    trade_repo = AsyncMock()
    trade_repo.get_active_trade_count = AsyncMock(return_value=2)

    stage = RiskSizingStage(risk_manager, trade_repo)
    ctx = ScanContext(
        now=datetime.now(IST),
        ranked_signals=["ranked1"],
        user_config=UserConfig(),
    )
    result = await stage.process(ctx)

    assert result.final_signals == ["final1"]
    assert result.active_trade_count == 2
    risk_manager.filter_and_size.assert_called_once()


async def test_no_op_when_no_ranked_signals():
    """Stage should be a no-op when there are no ranked signals."""
    risk_manager = MagicMock()
    trade_repo = AsyncMock()
    stage = RiskSizingStage(risk_manager, trade_repo)
    ctx = ScanContext(now=datetime.now(IST), ranked_signals=[])
    result = await stage.process(ctx)

    assert result.final_signals == []
    risk_manager.filter_and_size.assert_not_called()
