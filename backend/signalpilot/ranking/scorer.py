"""Multi-factor composite scoring for candidate signals."""

from signalpilot.db.models import CandidateSignal, ScoringWeights
from signalpilot.ranking.orb_scorer import ORBScorer
from signalpilot.ranking.vwap_scorer import VWAPScorer


class SignalScorer:
    """Calculates composite scores for candidate signals.

    Dispatches to strategy-specific scorers for ORB and VWAP signals.
    Falls back to the default Gap & Go scoring for unrecognized strategies.
    """

    def __init__(
        self,
        weights: ScoringWeights,
        orb_scorer: ORBScorer | None = None,
        vwap_scorer: VWAPScorer | None = None,
    ) -> None:
        self._weights = weights
        self._orb_scorer = orb_scorer
        self._vwap_scorer = vwap_scorer

    def score(self, signal: CandidateSignal) -> float:
        """Compute a composite score in [0.0, 1.0] for a candidate signal.

        Dispatches based on strategy_name:
        - "ORB" -> ORBScorer
        - "VWAP Reversal" -> VWAPScorer
        - default -> Gap & Go scoring
        """
        if signal.strategy_name == "ORB" and self._orb_scorer is not None:
            return self._orb_scorer.score(
                volume_ratio=signal.volume_ratio,
                range_size_pct=signal.gap_pct,  # reused for range size
                distance_from_breakout_pct=signal.price_distance_from_open_pct,
            )
        if signal.strategy_name == "VWAP Reversal" and self._vwap_scorer is not None:
            return self._vwap_scorer.score(
                volume_ratio=signal.volume_ratio,
                vwap_touch_pct=signal.price_distance_from_open_pct,
                candles_above_vwap_ratio=signal.gap_pct,  # reused for trend ratio
            )
        return self._score_gap_and_go(signal)

    def _score_gap_and_go(self, signal: CandidateSignal) -> float:
        """Default Gap & Go scoring."""
        norm_gap = self._normalize_gap(signal.gap_pct)
        norm_vol = self._normalize_volume_ratio(signal.volume_ratio)
        norm_dist = self._normalize_price_distance(signal.price_distance_from_open_pct)

        return (
            norm_gap * self._weights.gap_pct_weight
            + norm_vol * self._weights.volume_ratio_weight
            + norm_dist * self._weights.price_distance_weight
        )

    @staticmethod
    def _normalize_gap(gap_pct: float) -> float:
        """Normalize gap percentage to [0.0, 1.0].

        3% → 0.0, 5% → 1.0, linear interpolation, clamped.
        """
        return min(max((gap_pct - 3.0) / 2.0, 0.0), 1.0)

    @staticmethod
    def _normalize_volume_ratio(volume_ratio: float) -> float:
        """Normalize volume ratio to [0.0, 1.0].

        0.5 (threshold) → 0.0, 3.0+ → 1.0, linear interpolation, clamped.
        """
        return min(max((volume_ratio - 0.5) / 2.5, 0.0), 1.0)

    @staticmethod
    def _normalize_price_distance(distance_pct: float) -> float:
        """Normalize price distance from open to [0.0, 1.0].

        0% → 0.0, 3%+ → 1.0, linear interpolation, clamped.
        """
        return min(max(distance_pct / 3.0, 0.0), 1.0)
