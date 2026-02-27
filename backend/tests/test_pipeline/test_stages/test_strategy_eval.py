"""Tests for StrategyEvalStage."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from signalpilot.db.models import CandidateSignal, SignalDirection, UserConfig
from signalpilot.pipeline.context import ScanContext
from signalpilot.pipeline.stages.strategy_eval import StrategyEvalStage
from signalpilot.utils.constants import IST
from signalpilot.utils.market_calendar import StrategyPhase


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


def _make_strategy(name="Gap & Go", active_phases=None, evaluate_return=None):
    mock = MagicMock()
    mock.name = name
    mock.active_phases = active_phases or [StrategyPhase.OPENING, StrategyPhase.ENTRY_WINDOW]
    mock.evaluate = AsyncMock(return_value=evaluate_return or [])
    return mock


async def test_evaluates_strategies_in_active_phase():
    """Strategies active in the current phase should be evaluated."""
    candidate = _make_candidate()
    strategy = _make_strategy(evaluate_return=[candidate])
    config_repo = AsyncMock()
    config_repo.get_user_config = AsyncMock(return_value=UserConfig())
    market_data = MagicMock()

    stage = StrategyEvalStage([strategy], config_repo, market_data)
    ctx = ScanContext(
        now=datetime.now(IST),
        phase=StrategyPhase.OPENING,
    )
    result = await stage.process(ctx)

    assert len(result.all_candidates) == 1
    assert result.all_candidates[0] is candidate
    strategy.evaluate.assert_awaited_once()


async def test_skips_strategy_outside_active_phase():
    """Strategy not active in CONTINUOUS should not be evaluated."""
    strategy = _make_strategy(
        active_phases=[StrategyPhase.OPENING],
        evaluate_return=[_make_candidate()],
    )
    config_repo = AsyncMock()
    config_repo.get_user_config = AsyncMock(return_value=UserConfig())

    stage = StrategyEvalStage([strategy], config_repo, MagicMock())
    ctx = ScanContext(now=datetime.now(IST), phase=StrategyPhase.CONTINUOUS)
    result = await stage.process(ctx)

    assert result.all_candidates == []
    strategy.evaluate.assert_not_awaited()


async def test_filters_disabled_strategy():
    """A strategy disabled in user_config should not be evaluated."""
    strategy = _make_strategy(name="ORB", active_phases=[StrategyPhase.CONTINUOUS])
    config_repo = AsyncMock()
    config_repo.get_user_config = AsyncMock(
        return_value=UserConfig(orb_enabled=False)
    )

    stage = StrategyEvalStage([strategy], config_repo, MagicMock())
    ctx = ScanContext(now=datetime.now(IST), phase=StrategyPhase.CONTINUOUS)
    result = await stage.process(ctx)

    assert result.enabled_strategies == []


async def test_empty_strategies_list():
    """No strategies should produce no candidates."""
    config_repo = AsyncMock()
    config_repo.get_user_config = AsyncMock(return_value=UserConfig())

    stage = StrategyEvalStage([], config_repo, MagicMock())
    ctx = ScanContext(now=datetime.now(IST), phase=StrategyPhase.OPENING)
    result = await stage.process(ctx)

    assert result.all_candidates == []
    assert result.enabled_strategies == []
