"""Composite 4-factor scoring for Phase 3 hybrid ranking."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from signalpilot.db.models import CandidateSignal
from signalpilot.ranking.confidence import ConfirmationResult

logger = logging.getLogger(__name__)


@dataclass
class CompositeScoreResult:
    """Result of composite scoring."""

    composite_score: float  # 0-100
    strategy_strength_score: float  # 0-100
    win_rate_score: float  # 0-100
    risk_reward_score: float  # 0-100
    confirmation_bonus: float  # 0, 50, or 100


class CompositeScorer:
    """Unified 4-factor composite scoring engine.

    Factors:
    1. Strategy Strength (0-100) -- from strategy-specific scorer (0-1 scaled)
    2. Trailing 30-day Win Rate (0-100) -- from performance repo, cached per day
    3. Risk-Reward Ratio (0-100) -- linear map of R:R 1.0->0, 2.0->50, 3.0->100
    4. Confirmation Bonus (0, 50, 100) -- single/double/triple confirmation
    """

    WEIGHT_STRATEGY_STRENGTH = 0.4
    WEIGHT_WIN_RATE = 0.3
    WEIGHT_RISK_REWARD = 0.2
    WEIGHT_CONFIRMATION = 0.1

    def __init__(self, signal_scorer=None, strategy_performance_repo=None) -> None:
        self._signal_scorer = signal_scorer
        self._strategy_perf_repo = strategy_performance_repo
        self._win_rate_cache: dict[str, float] = {}
        self._cache_date: date | None = None

    async def score(
        self,
        candidate: CandidateSignal,
        confirmation: ConfirmationResult,
        today: date,
    ) -> CompositeScoreResult:
        """Compute composite score from four weighted factors.

        Returns a CompositeScoreResult with the overall score clamped to [0, 100].
        """
        logger.info(
            "Entering score",
            extra={"symbol": candidate.symbol, "strategy": candidate.strategy_name},
        )

        # Factor 1: Strategy Signal Strength (0-100)
        strength = self._get_strategy_strength(candidate)

        # Factor 2: Trailing 30-day Win Rate (0-100)
        win_rate = await self._get_trailing_win_rate(candidate.strategy_name, today)

        # Factor 3: Risk-Reward Ratio (0-100)
        rr_score = self._calculate_risk_reward_score(candidate)

        # Factor 4: Confirmation Bonus (0, 50, or 100)
        bonus = self._get_confirmation_bonus(confirmation)

        # Weighted composite
        composite = (
            strength * self.WEIGHT_STRATEGY_STRENGTH
            + win_rate * self.WEIGHT_WIN_RATE
            + rr_score * self.WEIGHT_RISK_REWARD
            + bonus * self.WEIGHT_CONFIRMATION
        )

        # Clamp to 0-100
        composite = max(0.0, min(100.0, composite))

        result = CompositeScoreResult(
            composite_score=round(composite, 2),
            strategy_strength_score=round(strength, 2),
            win_rate_score=round(win_rate, 2),
            risk_reward_score=round(rr_score, 2),
            confirmation_bonus=bonus,
        )

        logger.info(
            "Exiting score",
            extra={
                "symbol": candidate.symbol,
                "composite_score": result.composite_score,
            },
        )
        return result

    def _get_strategy_strength(self, candidate: CandidateSignal) -> float:
        """Get strategy-specific score, scaled to 0-100.

        Uses the candidate's ``strategy_specific_score`` field (typically 0-1
        from the per-strategy scorer) and scales it to 0-100.  Falls back to
        a neutral 50.0 if the field is absent or None.
        """
        if (
            self._signal_scorer is not None
            and hasattr(candidate, "strategy_specific_score")
            and candidate.strategy_specific_score is not None
        ):
            return min(100.0, max(0.0, candidate.strategy_specific_score * 100))
        # Check candidate directly even without signal_scorer
        if (
            hasattr(candidate, "strategy_specific_score")
            and candidate.strategy_specific_score is not None
        ):
            return min(100.0, max(0.0, candidate.strategy_specific_score * 100))
        # Fallback: use a neutral score
        return 50.0

    async def _get_trailing_win_rate(self, strategy_name: str, today: date) -> float:
        """Fetch trailing 30-day win rate, cached per day per strategy.

        Invalidates the entire cache when the date changes.  Returns a neutral
        50.0 when no performance data is available.
        """
        # Invalidate cache if day changed
        if self._cache_date != today:
            self._win_rate_cache.clear()
            self._cache_date = today

        if strategy_name in self._win_rate_cache:
            return self._win_rate_cache[strategy_name]

        win_rate = 50.0  # neutral default
        if self._strategy_perf_repo is not None:
            try:
                summary = await self._strategy_perf_repo.get_performance_summary(
                    strategy_name, days=30
                )
                if summary and hasattr(summary, "win_rate"):
                    win_rate = float(summary.win_rate)
            except Exception:
                logger.warning(
                    "Failed to get win rate for %s, using default",
                    strategy_name,
                )

        self._win_rate_cache[strategy_name] = win_rate
        return win_rate

    @staticmethod
    def _calculate_risk_reward_score(candidate: CandidateSignal) -> float:
        """Normalize risk-reward ratio to 0-100 score.

        Linear mapping:
        - R:R <= 1.0 -> 0
        - R:R  = 2.0 -> 50
        - R:R >= 3.0 -> 100

        Returns 0.0 for zero or negative risk/reward.
        """
        entry = candidate.entry_price
        sl = candidate.stop_loss
        t2 = candidate.target_2

        risk = entry - sl
        if risk <= 0:
            return 0.0

        reward = t2 - entry
        if reward <= 0:
            return 0.0

        rr_ratio = reward / risk

        if rr_ratio <= 1.0:
            return 0.0
        elif rr_ratio >= 3.0:
            return 100.0
        else:
            # Linear interpolation: 1.0 -> 0, 3.0 -> 100
            return (rr_ratio - 1.0) / 2.0 * 100.0

    @staticmethod
    def _get_confirmation_bonus(confirmation: ConfirmationResult) -> float:
        """Map confirmation level to bonus score.

        triple -> 100, double -> 50, single -> 0.
        """
        if confirmation.confirmation_level == "triple":
            return 100.0
        elif confirmation.confirmation_level == "double":
            return 50.0
        return 0.0
