"""Performance-based capital allocation across strategies."""

import logging
from dataclasses import dataclass
from datetime import date, timedelta

logger = logging.getLogger(__name__)

STRATEGY_NAMES = ["gap_go", "ORB", "VWAP Reversal"]
RESERVE_PCT = 0.20


@dataclass
class StrategyAllocation:
    """Capital allocation for a single strategy."""

    strategy_name: str
    weight_pct: float
    allocated_capital: float
    max_positions: int


class CapitalAllocator:
    """Allocates capital across strategies based on historical performance."""

    def __init__(self, strategy_performance_repo, config_repo) -> None:
        self._perf_repo = strategy_performance_repo
        self._config_repo = config_repo
        self._manual_weights: dict[str, float] | None = None
        self._auto_mode = True

    async def calculate_allocations(
        self, total_capital: float, max_positions: int, today: date
    ) -> dict[str, StrategyAllocation]:
        """Calculate capital allocations per strategy.

        Uses expectancy-weighted allocation with 20% reserve.
        Falls back to equal allocation when no historical data.
        """
        if self._manual_weights is not None:
            return self._apply_weights(
                self._manual_weights, total_capital, max_positions
            )

        lookback_start = today - timedelta(days=30)
        records = await self._perf_repo.get_by_date_range(lookback_start, today)

        # Group by strategy
        strategy_data: dict[str, list] = {s: [] for s in STRATEGY_NAMES}
        for record in records:
            if record.strategy in strategy_data:
                strategy_data[record.strategy].append(record)

        # Calculate expectancy per strategy
        weights: dict[str, float] = {}
        has_data = False
        for strategy, recs in strategy_data.items():
            if not recs:
                weights[strategy] = 0.0
                continue
            has_data = True
            total_taken = sum(r.signals_taken for r in recs)
            total_wins = sum(r.wins for r in recs)
            total_losses = sum(r.losses for r in recs)
            total_pnl_wins = sum(r.avg_win * r.wins for r in recs if r.wins > 0)
            total_pnl_losses = sum(abs(r.avg_loss) * r.losses for r in recs if r.losses > 0)

            if total_taken > 0:
                win_rate = total_wins / total_taken
                avg_win = total_pnl_wins / total_wins if total_wins > 0 else 0
                avg_loss = total_pnl_losses / total_losses if total_losses > 0 else 0
                expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
                weights[strategy] = max(expectancy, 0.0)
            else:
                weights[strategy] = 0.0

        if not has_data or sum(weights.values()) == 0:
            # Equal allocation fallback
            equal_weight = (1.0 - RESERVE_PCT) / len(STRATEGY_NAMES)
            weights = {s: equal_weight for s in STRATEGY_NAMES}
        else:
            # Normalize to sum to (1 - RESERVE_PCT)
            total_weight = sum(weights.values())
            if total_weight > 0:
                available = 1.0 - RESERVE_PCT
                weights = {
                    s: (w / total_weight) * available for s, w in weights.items()
                }

        return self._apply_weights(weights, total_capital, max_positions)

    def _apply_weights(
        self,
        weights: dict[str, float],
        total_capital: float,
        max_positions: int,
    ) -> dict[str, StrategyAllocation]:
        """Apply weight percentages to capital and positions."""
        result: dict[str, StrategyAllocation] = {}
        for strategy, weight in weights.items():
            allocated_capital = total_capital * weight
            positions = max(1, round(max_positions * weight))
            result[strategy] = StrategyAllocation(
                strategy_name=strategy,
                weight_pct=weight * 100,
                allocated_capital=allocated_capital,
                max_positions=positions,
            )
        return result

    async def check_auto_pause(self, today: date) -> list[str]:
        """Check if any strategy should be auto-paused (win rate < 40%, >= 10 trades)."""
        pause_list: list[str] = []
        lookback_start = today - timedelta(days=30)

        for strategy in STRATEGY_NAMES:
            records = await self._perf_repo.get_performance_summary(
                strategy, lookback_start, today
            )
            total_taken = sum(r.signals_taken for r in records)
            total_wins = sum(r.wins for r in records)

            if total_taken >= 10:
                win_rate = (total_wins / total_taken) * 100
                if win_rate < 40:
                    pause_list.append(strategy)
                    logger.warning(
                        "Auto-pause recommended for %s: win_rate=%.1f%% (%d trades)",
                        strategy, win_rate, total_taken,
                    )

        return pause_list

    def set_manual_allocation(self, allocations: dict[str, float]) -> None:
        """Set manual allocation weights (disables auto-rebalancing)."""
        self._manual_weights = allocations
        self._auto_mode = False
        logger.info("Manual allocation set: %s", allocations)

    def enable_auto_allocation(self) -> None:
        """Re-enable automatic allocation (clears manual weights)."""
        self._manual_weights = None
        self._auto_mode = True
        logger.info("Auto allocation re-enabled")
