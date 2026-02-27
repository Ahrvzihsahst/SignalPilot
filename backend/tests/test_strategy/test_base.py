"""Tests for BaseStrategy abstract base class."""

import pytest

from signalpilot.data.market_data_store import MarketDataStore
from signalpilot.strategy.base import BaseStrategy
from signalpilot.utils.market_calendar import StrategyPhase


def test_base_strategy_cannot_be_instantiated() -> None:
    """BaseStrategy is abstract and cannot be instantiated directly."""
    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        BaseStrategy()  # type: ignore[abstract]


def test_concrete_subclass_can_be_instantiated() -> None:
    """A properly implemented subclass should be instantiable."""

    class ConcreteStrategy(BaseStrategy):
        @property
        def name(self) -> str:
            return "Test Strategy"

        @property
        def active_phases(self) -> list[StrategyPhase]:
            return [StrategyPhase.CONTINUOUS]

        async def evaluate(self, market_data: MarketDataStore, current_phase: StrategyPhase):
            return []

    s = ConcreteStrategy()
    assert s.name == "Test Strategy"
    assert s.active_phases == [StrategyPhase.CONTINUOUS]
