"""ORB (Opening Range Breakout) signal scorer."""


class ORBScorer:
    """Scores ORB breakout signals based on volume, range tightness, and distance."""

    def __init__(
        self,
        volume_weight: float = 0.40,
        range_weight: float = 0.30,
        distance_weight: float = 0.30,
    ) -> None:
        self._volume_weight = volume_weight
        self._range_weight = range_weight
        self._distance_weight = distance_weight

    def score(
        self,
        volume_ratio: float,
        range_size_pct: float,
        distance_from_breakout_pct: float,
    ) -> float:
        """Compute composite score in [0.0, 1.0].

        Args:
            volume_ratio: Current volume / avg candle volume (1.5x min for breakout).
            range_size_pct: Opening range size as % (0.5-3%).
            distance_from_breakout_pct: How far price has moved past breakout level.
        """
        norm_vol = self._normalize_volume(volume_ratio)
        norm_range = self._normalize_range(range_size_pct)
        norm_dist = self._normalize_distance(distance_from_breakout_pct)

        return (
            norm_vol * self._volume_weight
            + norm_range * self._range_weight
            + norm_dist * self._distance_weight
        )

    @staticmethod
    def _normalize_volume(ratio: float) -> float:
        """1.5x -> 0.0, 4.0x -> 1.0, linear interpolation, clamped."""
        return min(max((ratio - 1.5) / 2.5, 0.0), 1.0)

    @staticmethod
    def _normalize_range(range_pct: float) -> float:
        """3% -> 0.0, 0.5% -> 1.0 (inverse: tighter range = better)."""
        return min(max((3.0 - range_pct) / 2.5, 0.0), 1.0)

    @staticmethod
    def _normalize_distance(distance_pct: float) -> float:
        """0% -> 1.0, 3%+ -> 0.0 (closer to breakout = better)."""
        return min(max(1.0 - distance_pct / 3.0, 0.0), 1.0)
