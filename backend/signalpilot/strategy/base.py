"""Abstract base class for trading strategies."""

from abc import ABC, abstractmethod

from signalpilot.data.market_data_store import MarketDataStore
from signalpilot.db.models import CandidateSignal
from signalpilot.utils.market_calendar import StrategyPhase


class BaseStrategy(ABC):
    """Abstract base class for all trading strategies.

    Subclasses must implement ``name``, ``active_phases``, and ``evaluate``.
    The scanning loop calls ``evaluate`` on each cycle during the strategy's
    active phases.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable strategy name."""
        ...

    @property
    @abstractmethod
    def active_phases(self) -> list[StrategyPhase]:
        """Which phases of the trading day this strategy operates in."""
        ...

    @abstractmethod
    async def evaluate(
        self,
        market_data: MarketDataStore,
        current_phase: StrategyPhase,
    ) -> list[CandidateSignal]:
        """Evaluate current market conditions and return candidate signals.

        Called by the scanning loop on each tick cycle during active phases.
        """
        ...
