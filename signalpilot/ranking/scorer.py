"""Multi-factor composite scoring for candidate signals."""

from signalpilot.db.models import CandidateSignal, ScoringWeights


class SignalScorer:
    """Calculates composite scores for candidate signals.

    Each factor (gap %, volume ratio, price distance from open) is normalized
    to 0.0-1.0 and then weighted according to ``ScoringWeights``.
    """

    def __init__(self, weights: ScoringWeights) -> None:
        self._weights = weights

    def score(self, signal: CandidateSignal) -> float:
        """Compute a composite score in [0.0, 1.0] for a candidate signal.

        composite = (norm_gap * gap_weight) +
                    (norm_volume * volume_weight) +
                    (norm_price_distance * price_distance_weight)
        """
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
