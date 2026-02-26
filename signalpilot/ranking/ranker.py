"""Signal ranking engine — scores, ranks, and selects top-N signals."""

from __future__ import annotations

from signalpilot.db.models import CandidateSignal, RankedSignal
from signalpilot.ranking.composite_scorer import CompositeScoreResult
from signalpilot.ranking.confidence import ConfirmationResult
from signalpilot.ranking.scorer import SignalScorer


class SignalRanker:
    """Ranks scored signals, assigns star ratings, and selects top N.

    Supports two ranking modes:
    1. Composite (Phase 3): when ``composite_scores`` is provided, ranks by
       composite score with multi-factor tiebreakers and confirmation star boost.
    2. Legacy (Phase 1/2): scores candidates via the injected ``SignalScorer``.
    """

    def __init__(self, scorer: SignalScorer, max_signals: int = 8) -> None:
        self._scorer = scorer
        self._max_signals = max_signals

    def rank(
        self,
        candidates: list[CandidateSignal],
        composite_scores: dict[str, CompositeScoreResult] | None = None,
        confirmations: dict[str, ConfirmationResult] | None = None,
    ) -> list[RankedSignal]:
        """Score all candidates, sort descending, assign stars, return top N.

        When *composite_scores* is provided, delegates to ``_rank_composite``.
        Otherwise, falls back to ``_rank_legacy`` (original behavior).
        """
        if composite_scores is not None:
            return self._rank_composite(candidates, composite_scores, confirmations)
        return self._rank_legacy(candidates)

    # ------------------------------------------------------------------
    # Composite ranking (Phase 3)
    # ------------------------------------------------------------------

    def _rank_composite(
        self,
        candidates: list[CandidateSignal],
        composite_scores: dict[str, CompositeScoreResult],
        confirmations: dict[str, ConfirmationResult] | None,
    ) -> list[RankedSignal]:
        """Rank candidates using pre-computed composite scores.

        Sort order (all descending):
        1. composite_score
        2. win_rate_score (tiebreaker)
        3. risk_reward_score (tiebreaker)
        4. generated_at (most recent first)

        Star rating derived from ``_composite_to_stars`` with an optional
        confirmation boost (capped at 5).
        """
        # Build (candidate, score_result) pairs, defaulting missing symbols
        pairs: list[tuple[CandidateSignal, CompositeScoreResult]] = []
        default_score = CompositeScoreResult(
            composite_score=0.0,
            strategy_strength_score=0.0,
            win_rate_score=0.0,
            risk_reward_score=0.0,
            confirmation_bonus=0.0,
        )
        for candidate in candidates:
            score_result = composite_scores.get(candidate.symbol, default_score)
            pairs.append((candidate, score_result))

        # Sort by composite_score DESC, win_rate_score DESC,
        # risk_reward_score DESC, generated_at DESC
        pairs.sort(
            key=lambda p: (
                p[1].composite_score,
                p[1].win_rate_score,
                p[1].risk_reward_score,
                p[0].generated_at.timestamp() if p[0].generated_at else 0,
            ),
            reverse=True,
        )

        ranked: list[RankedSignal] = []
        for i, (candidate, score_result) in enumerate(pairs[: self._max_signals]):
            base_stars = self._composite_to_stars(score_result.composite_score)

            # Apply confirmation star boost
            if confirmations is not None and candidate.symbol in confirmations:
                conf = confirmations[candidate.symbol]
                stars = min(base_stars + conf.star_boost, 5)
            else:
                stars = base_stars

            ranked.append(
                RankedSignal(
                    candidate=candidate,
                    composite_score=score_result.composite_score,
                    rank=i + 1,
                    signal_strength=stars,
                )
            )

        return ranked

    # ------------------------------------------------------------------
    # Legacy ranking (Phase 1/2)
    # ------------------------------------------------------------------

    def _rank_legacy(self, candidates: list[CandidateSignal]) -> list[RankedSignal]:
        """Original ranking logic using the injected SignalScorer."""
        scored: list[tuple[CandidateSignal, float]] = []
        for candidate in candidates:
            score = self._scorer.score(candidate)
            scored.append((candidate, score))

        scored.sort(key=lambda x: x[1], reverse=True)

        ranked: list[RankedSignal] = []
        for i, (candidate, score) in enumerate(scored[: self._max_signals]):
            stars = self._score_to_stars(score)
            ranked.append(
                RankedSignal(
                    candidate=candidate,
                    composite_score=score,
                    rank=i + 1,
                    signal_strength=stars,
                )
            )
        return ranked

    # ------------------------------------------------------------------
    # Star mapping helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _score_to_stars(score: float) -> int:
        """Map legacy composite score (0.0-1.0) to 1-5 star rating.

        [0.0, 0.2) -> 1, [0.2, 0.4) -> 2, [0.4, 0.6) -> 3,
        [0.6, 0.8) -> 4, [0.8, 1.0] -> 5.
        """
        if score >= 0.8:
            return 5
        if score >= 0.6:
            return 4
        if score >= 0.4:
            return 3
        if score >= 0.2:
            return 2
        return 1

    @staticmethod
    def _composite_to_stars(composite_score: float) -> int:
        """Map Phase 3 composite score (0-100) to 1-5 star rating.

        >=80 -> 5, >=65 -> 4, >=50 -> 3, >=35 -> 2, else 1.
        """
        if composite_score >= 80:
            return 5
        if composite_score >= 65:
            return 4
        if composite_score >= 50:
            return 3
        if composite_score >= 35:
            return 2
        return 1
