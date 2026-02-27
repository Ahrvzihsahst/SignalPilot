"""VWAP Reversal signal scorer."""


class VWAPScorer:
    """Scores VWAP reversal signals based on volume, touch precision, and trend."""

    def __init__(
        self,
        volume_weight: float = 0.35,
        touch_weight: float = 0.35,
        trend_weight: float = 0.30,
    ) -> None:
        self._volume_weight = volume_weight
        self._touch_weight = touch_weight
        self._trend_weight = trend_weight

    def score(
        self,
        volume_ratio: float,
        vwap_touch_pct: float,
        candles_above_vwap_ratio: float,
    ) -> float:
        """Compute composite score in [0.0, 1.0].

        Args:
            volume_ratio: Bounce candle volume / avg candle volume.
            vwap_touch_pct: Distance from VWAP as % (0.3% max, 0% exact touch).
            candles_above_vwap_ratio: Fraction of prior candles closing above VWAP.
        """
        norm_vol = self._normalize_volume(volume_ratio)
        norm_touch = self._normalize_touch(vwap_touch_pct)
        norm_trend = min(max(candles_above_vwap_ratio, 0.0), 1.0)

        return (
            norm_vol * self._volume_weight
            + norm_touch * self._touch_weight
            + norm_trend * self._trend_weight
        )

    @staticmethod
    def _normalize_volume(ratio: float) -> float:
        """1.0x -> 0.0, 3.0x -> 1.0, linear interpolation, clamped."""
        return min(max((ratio - 1.0) / 2.0, 0.0), 1.0)

    @staticmethod
    def _normalize_touch(touch_pct: float) -> float:
        """0.3% -> 0.0, 0% (exact touch) -> 1.0."""
        return min(max(1.0 - touch_pct / 0.3, 0.0), 1.0)
