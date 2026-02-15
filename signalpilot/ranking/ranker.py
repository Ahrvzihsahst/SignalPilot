"""Signal ranking engine — scores, ranks, and selects top-N signals."""

from signalpilot.db.models import CandidateSignal, RankedSignal
from signalpilot.ranking.scorer import SignalScorer


class SignalRanker:
    """Ranks scored signals, assigns star ratings, and selects top N."""

    def __init__(self, scorer: SignalScorer, max_signals: int = 5) -> None:
        self._scorer = scorer
        self._max_signals = max_signals

    def rank(self, candidates: list[CandidateSignal]) -> list[RankedSignal]:
        """Score all candidates, sort descending, assign stars, return top N."""
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

    @staticmethod
    def _score_to_stars(score: float) -> int:
        """Map composite score to 1-5 star rating.

        [0.0, 0.2) → 1, [0.2, 0.4) → 2, [0.4, 0.6) → 3,
        [0.6, 0.8) → 4, [0.8, 1.0] → 5.
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
