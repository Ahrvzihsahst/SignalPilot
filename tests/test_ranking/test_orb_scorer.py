"""Tests for ORBScorer."""

import pytest

from signalpilot.ranking.orb_scorer import ORBScorer


@pytest.fixture
def scorer() -> ORBScorer:
    return ORBScorer()


# -- Volume normalization: 1.5x -> 0.0, 4.0x -> 1.0 --


def test_normalize_volume_at_minimum() -> None:
    """1.5x ratio maps to 0.0."""
    assert ORBScorer._normalize_volume(1.5) == 0.0


def test_normalize_volume_at_maximum() -> None:
    """4.0x ratio maps to 1.0."""
    assert ORBScorer._normalize_volume(4.0) == 1.0


def test_normalize_volume_midpoint() -> None:
    """Midpoint (2.75) maps to ~0.5."""
    assert ORBScorer._normalize_volume(2.75) == pytest.approx(0.5)


def test_normalize_volume_below_minimum_clamps_to_zero() -> None:
    """Values below 1.5x clamp to 0.0."""
    assert ORBScorer._normalize_volume(0.5) == 0.0
    assert ORBScorer._normalize_volume(1.0) == 0.0


def test_normalize_volume_above_maximum_clamps_to_one() -> None:
    """Values above 4.0x clamp to 1.0."""
    assert ORBScorer._normalize_volume(5.0) == 1.0
    assert ORBScorer._normalize_volume(10.0) == 1.0


# -- Range tightness: 3% -> 0.0, 0.5% -> 1.0 (inverse) --


def test_normalize_range_at_3pct() -> None:
    """3% range maps to 0.0 (widest acceptable range)."""
    assert ORBScorer._normalize_range(3.0) == 0.0


def test_normalize_range_at_0_5pct() -> None:
    """0.5% range maps to 1.0 (tightest = best)."""
    assert ORBScorer._normalize_range(0.5) == 1.0


def test_normalize_range_midpoint() -> None:
    """1.75% maps to ~0.5."""
    assert ORBScorer._normalize_range(1.75) == pytest.approx(0.5)


def test_normalize_range_above_3pct_clamps_to_zero() -> None:
    """Ranges wider than 3% clamp to 0.0."""
    assert ORBScorer._normalize_range(4.0) == 0.0
    assert ORBScorer._normalize_range(5.5) == 0.0


def test_normalize_range_below_0_5pct_clamps_to_one() -> None:
    """Ranges tighter than 0.5% clamp to 1.0."""
    assert ORBScorer._normalize_range(0.0) == 1.0
    assert ORBScorer._normalize_range(-0.5) == 1.0


# -- Distance from breakout: 0% -> 1.0, 3% -> 0.0 --


def test_normalize_distance_at_zero() -> None:
    """0% distance (at breakout) maps to 1.0."""
    assert ORBScorer._normalize_distance(0.0) == 1.0


def test_normalize_distance_at_3pct() -> None:
    """3% distance maps to 0.0."""
    assert ORBScorer._normalize_distance(3.0) == pytest.approx(0.0)


def test_normalize_distance_midpoint() -> None:
    """1.5% distance maps to ~0.5."""
    assert ORBScorer._normalize_distance(1.5) == pytest.approx(0.5)


def test_normalize_distance_above_3pct_clamps_to_zero() -> None:
    """Distances beyond 3% clamp to 0.0."""
    assert ORBScorer._normalize_distance(5.0) == 0.0
    assert ORBScorer._normalize_distance(10.0) == 0.0


def test_normalize_distance_negative_clamps_to_one() -> None:
    """Negative distances (shouldn't occur, but defensive) clamp to 1.0."""
    assert ORBScorer._normalize_distance(-1.0) == 1.0


# -- Composite score --


def test_score_all_minimum(scorer: ORBScorer) -> None:
    """All factors at minimum produce score = 0.0."""
    result = scorer.score(
        volume_ratio=1.5,
        range_size_pct=3.0,
        distance_from_breakout_pct=3.0,
    )
    assert result == pytest.approx(0.0)


def test_score_all_maximum(scorer: ORBScorer) -> None:
    """All factors at maximum produce score = 1.0."""
    result = scorer.score(
        volume_ratio=4.0,
        range_size_pct=0.5,
        distance_from_breakout_pct=0.0,
    )
    assert result == pytest.approx(1.0)


def test_score_midpoints(scorer: ORBScorer) -> None:
    """All factors at midpoint produce score = 0.5."""
    result = scorer.score(
        volume_ratio=2.75,
        range_size_pct=1.75,
        distance_from_breakout_pct=1.5,
    )
    assert result == pytest.approx(0.5)


def test_score_in_range(scorer: ORBScorer) -> None:
    """Output is always in [0, 1] for reasonable inputs."""
    result = scorer.score(
        volume_ratio=2.0,
        range_size_pct=2.0,
        distance_from_breakout_pct=1.0,
    )
    assert 0.0 <= result <= 1.0


def test_score_clamped_below_range(scorer: ORBScorer) -> None:
    """Inputs below minimums still produce a score in [0, 1]."""
    result = scorer.score(
        volume_ratio=0.0,
        range_size_pct=5.0,
        distance_from_breakout_pct=10.0,
    )
    assert result == pytest.approx(0.0)


def test_score_clamped_above_range(scorer: ORBScorer) -> None:
    """Inputs above maximums still produce a score in [0, 1]."""
    result = scorer.score(
        volume_ratio=10.0,
        range_size_pct=0.0,
        distance_from_breakout_pct=-1.0,
    )
    assert result == pytest.approx(1.0)


def test_score_volume_dominant() -> None:
    """With volume_weight=1.0 and others=0.0, only volume matters."""
    scorer = ORBScorer(volume_weight=1.0, range_weight=0.0, distance_weight=0.0)
    result = scorer.score(
        volume_ratio=4.0,
        range_size_pct=3.0,
        distance_from_breakout_pct=3.0,
    )
    assert result == pytest.approx(1.0)


def test_score_with_custom_weights() -> None:
    """Custom equal weights produce expected result."""
    scorer = ORBScorer(
        volume_weight=1 / 3,
        range_weight=1 / 3,
        distance_weight=1 / 3,
    )
    # vol=1.0, range=0.0, dist=1.0 -> (1/3)*1 + (1/3)*0 + (1/3)*1 = 2/3
    result = scorer.score(
        volume_ratio=4.0,
        range_size_pct=3.0,
        distance_from_breakout_pct=0.0,
    )
    assert result == pytest.approx(2 / 3)
