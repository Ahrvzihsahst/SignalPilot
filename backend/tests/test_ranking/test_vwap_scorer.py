"""Tests for VWAPScorer."""

import pytest

from signalpilot.ranking.vwap_scorer import VWAPScorer


@pytest.fixture
def scorer() -> VWAPScorer:
    return VWAPScorer()


# -- Volume normalization: 1x -> 0.0, 3x -> 1.0 --


def test_normalize_volume_at_minimum() -> None:
    """1.0x ratio maps to 0.0."""
    assert VWAPScorer._normalize_volume(1.0) == 0.0


def test_normalize_volume_at_maximum() -> None:
    """3.0x ratio maps to 1.0."""
    assert VWAPScorer._normalize_volume(3.0) == 1.0


def test_normalize_volume_midpoint() -> None:
    """2.0x ratio maps to 0.5."""
    assert VWAPScorer._normalize_volume(2.0) == pytest.approx(0.5)


def test_normalize_volume_below_minimum_clamps_to_zero() -> None:
    """Values below 1.0x clamp to 0.0."""
    assert VWAPScorer._normalize_volume(0.5) == 0.0
    assert VWAPScorer._normalize_volume(0.0) == 0.0


def test_normalize_volume_above_maximum_clamps_to_one() -> None:
    """Values above 3.0x clamp to 1.0."""
    assert VWAPScorer._normalize_volume(4.0) == 1.0
    assert VWAPScorer._normalize_volume(10.0) == 1.0


# -- VWAP touch precision: 0.3% -> 0.0, 0% (exact) -> 1.0 --


def test_normalize_touch_at_0_3pct() -> None:
    """0.3% distance from VWAP maps to 0.0 (worst acceptable touch)."""
    assert VWAPScorer._normalize_touch(0.3) == pytest.approx(0.0)


def test_normalize_touch_at_zero() -> None:
    """0% distance (exact touch) maps to 1.0."""
    assert VWAPScorer._normalize_touch(0.0) == 1.0


def test_normalize_touch_midpoint() -> None:
    """0.15% distance maps to ~0.5."""
    assert VWAPScorer._normalize_touch(0.15) == pytest.approx(0.5)


def test_normalize_touch_above_0_3pct_clamps_to_zero() -> None:
    """Distances beyond 0.3% clamp to 0.0."""
    assert VWAPScorer._normalize_touch(0.5) == 0.0
    assert VWAPScorer._normalize_touch(1.0) == 0.0


def test_normalize_touch_negative_clamps_to_one() -> None:
    """Negative touch distance (shouldn't occur, but defensive) clamps to 1.0."""
    assert VWAPScorer._normalize_touch(-0.1) == 1.0


# -- Trend alignment (candles_above_vwap_ratio) --


def test_trend_ratio_zero() -> None:
    """No candles above VWAP: trend component = 0.0."""
    scorer = VWAPScorer(volume_weight=0.0, touch_weight=0.0, trend_weight=1.0)
    result = scorer.score(
        volume_ratio=1.0,
        vwap_touch_pct=0.3,
        candles_above_vwap_ratio=0.0,
    )
    assert result == pytest.approx(0.0)


def test_trend_ratio_one() -> None:
    """All candles above VWAP: trend component = 1.0."""
    scorer = VWAPScorer(volume_weight=0.0, touch_weight=0.0, trend_weight=1.0)
    result = scorer.score(
        volume_ratio=1.0,
        vwap_touch_pct=0.3,
        candles_above_vwap_ratio=1.0,
    )
    assert result == pytest.approx(1.0)


def test_trend_ratio_midpoint() -> None:
    """Half candles above VWAP: trend component = 0.5."""
    scorer = VWAPScorer(volume_weight=0.0, touch_weight=0.0, trend_weight=1.0)
    result = scorer.score(
        volume_ratio=1.0,
        vwap_touch_pct=0.3,
        candles_above_vwap_ratio=0.5,
    )
    assert result == pytest.approx(0.5)


def test_trend_ratio_clamped_above_one() -> None:
    """Ratio above 1.0 clamps to 1.0."""
    scorer = VWAPScorer(volume_weight=0.0, touch_weight=0.0, trend_weight=1.0)
    result = scorer.score(
        volume_ratio=1.0,
        vwap_touch_pct=0.3,
        candles_above_vwap_ratio=1.5,
    )
    assert result == pytest.approx(1.0)


def test_trend_ratio_clamped_below_zero() -> None:
    """Negative ratio clamps to 0.0."""
    scorer = VWAPScorer(volume_weight=0.0, touch_weight=0.0, trend_weight=1.0)
    result = scorer.score(
        volume_ratio=1.0,
        vwap_touch_pct=0.3,
        candles_above_vwap_ratio=-0.5,
    )
    assert result == pytest.approx(0.0)


# -- Composite score --


def test_score_all_minimum(scorer: VWAPScorer) -> None:
    """All factors at minimum produce score = 0.0."""
    result = scorer.score(
        volume_ratio=1.0,
        vwap_touch_pct=0.3,
        candles_above_vwap_ratio=0.0,
    )
    assert result == pytest.approx(0.0)


def test_score_all_maximum(scorer: VWAPScorer) -> None:
    """All factors at maximum produce score = 1.0."""
    result = scorer.score(
        volume_ratio=3.0,
        vwap_touch_pct=0.0,
        candles_above_vwap_ratio=1.0,
    )
    assert result == pytest.approx(1.0)


def test_score_midpoints(scorer: VWAPScorer) -> None:
    """All factors at midpoint produce score = 0.5."""
    result = scorer.score(
        volume_ratio=2.0,
        vwap_touch_pct=0.15,
        candles_above_vwap_ratio=0.5,
    )
    assert result == pytest.approx(0.5)


def test_score_in_range(scorer: VWAPScorer) -> None:
    """Output is in [0, 1] for reasonable inputs."""
    result = scorer.score(
        volume_ratio=1.5,
        vwap_touch_pct=0.1,
        candles_above_vwap_ratio=0.7,
    )
    assert 0.0 <= result <= 1.0


def test_score_clamped_below_range(scorer: VWAPScorer) -> None:
    """Extreme low inputs produce a score in [0, 1]."""
    result = scorer.score(
        volume_ratio=0.0,
        vwap_touch_pct=1.0,
        candles_above_vwap_ratio=-1.0,
    )
    assert result == pytest.approx(0.0)


def test_score_clamped_above_range(scorer: VWAPScorer) -> None:
    """Extreme high inputs produce a score in [0, 1]."""
    result = scorer.score(
        volume_ratio=10.0,
        vwap_touch_pct=-1.0,
        candles_above_vwap_ratio=5.0,
    )
    assert result == pytest.approx(1.0)


def test_score_with_custom_weights() -> None:
    """Custom equal weights produce expected result."""
    scorer = VWAPScorer(
        volume_weight=1 / 3,
        touch_weight=1 / 3,
        trend_weight=1 / 3,
    )
    # vol=1.0, touch=0.0, trend=1.0 -> (1/3)*1 + (1/3)*0 + (1/3)*1 = 2/3
    result = scorer.score(
        volume_ratio=3.0,
        vwap_touch_pct=0.3,
        candles_above_vwap_ratio=1.0,
    )
    assert result == pytest.approx(2 / 3)


def test_score_touch_dominant() -> None:
    """With touch_weight=1.0 and others=0.0, only touch matters."""
    scorer = VWAPScorer(volume_weight=0.0, touch_weight=1.0, trend_weight=0.0)
    result = scorer.score(
        volume_ratio=0.5,
        vwap_touch_pct=0.0,
        candles_above_vwap_ratio=0.0,
    )
    assert result == pytest.approx(1.0)
