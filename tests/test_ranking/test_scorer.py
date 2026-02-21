"""Tests for SignalScorer."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from signalpilot.db.models import CandidateSignal, ScoringWeights, SignalDirection
from signalpilot.ranking.orb_scorer import ORBScorer
from signalpilot.ranking.scorer import SignalScorer
from signalpilot.ranking.vwap_scorer import VWAPScorer


def _make_candidate(
    gap_pct: float = 4.0,
    volume_ratio: float = 1.5,
    price_distance_pct: float = 1.5,
) -> CandidateSignal:
    return CandidateSignal(
        symbol="SBIN",
        direction=SignalDirection.BUY,
        strategy_name="Gap & Go",
        entry_price=104.0,
        stop_loss=101.0,
        target_1=109.2,
        target_2=111.28,
        gap_pct=gap_pct,
        volume_ratio=volume_ratio,
        price_distance_from_open_pct=price_distance_pct,
        reason="test signal",
        generated_at=datetime.now(),
    )


@pytest.fixture
def default_weights() -> ScoringWeights:
    return ScoringWeights()  # 0.40, 0.35, 0.25


@pytest.fixture
def scorer(default_weights: ScoringWeights) -> SignalScorer:
    return SignalScorer(default_weights)


# ── Normalize gap ────────────────────────────────────────────────


def test_normalize_gap_at_3pct() -> None:
    assert SignalScorer._normalize_gap(3.0) == 0.0


def test_normalize_gap_at_5pct() -> None:
    assert SignalScorer._normalize_gap(5.0) == 1.0


def test_normalize_gap_at_4pct() -> None:
    assert SignalScorer._normalize_gap(4.0) == pytest.approx(0.5)


def test_normalize_gap_below_min() -> None:
    """Values below 3% clamp to 0.0."""
    assert SignalScorer._normalize_gap(2.0) == 0.0


def test_normalize_gap_above_max() -> None:
    """Values above 5% clamp to 1.0."""
    assert SignalScorer._normalize_gap(7.0) == 1.0


# ── Normalize volume ratio ──────────────────────────────────────


def test_normalize_volume_at_threshold() -> None:
    assert SignalScorer._normalize_volume_ratio(0.5) == 0.0


def test_normalize_volume_at_max() -> None:
    assert SignalScorer._normalize_volume_ratio(3.0) == 1.0


def test_normalize_volume_midpoint() -> None:
    # (1.75 - 0.5) / 2.5 = 0.5
    assert SignalScorer._normalize_volume_ratio(1.75) == pytest.approx(0.5)


def test_normalize_volume_below_threshold() -> None:
    assert SignalScorer._normalize_volume_ratio(0.1) == 0.0


def test_normalize_volume_above_max() -> None:
    assert SignalScorer._normalize_volume_ratio(5.0) == 1.0


# ── Normalize price distance ────────────────────────────────────


def test_normalize_distance_at_zero() -> None:
    assert SignalScorer._normalize_price_distance(0.0) == 0.0


def test_normalize_distance_at_3pct() -> None:
    assert SignalScorer._normalize_price_distance(3.0) == 1.0


def test_normalize_distance_at_1_5pct() -> None:
    assert SignalScorer._normalize_price_distance(1.5) == pytest.approx(0.5)


def test_normalize_distance_negative() -> None:
    """Negative distance (price below open) clamps to 0.0."""
    assert SignalScorer._normalize_price_distance(-1.0) == 0.0


def test_normalize_distance_above_max() -> None:
    assert SignalScorer._normalize_price_distance(5.0) == 1.0


# ── Composite score ──────────────────────────────────────────────


def test_score_all_minimum(scorer: SignalScorer) -> None:
    """All factors at minimum → score = 0.0."""
    candidate = _make_candidate(gap_pct=3.0, volume_ratio=0.5, price_distance_pct=0.0)
    assert scorer.score(candidate) == pytest.approx(0.0)


def test_score_all_maximum(scorer: SignalScorer) -> None:
    """All factors at maximum → score = sum of weights = 1.0."""
    candidate = _make_candidate(gap_pct=5.0, volume_ratio=3.0, price_distance_pct=3.0)
    assert scorer.score(candidate) == pytest.approx(1.0)


def test_score_midpoint(scorer: SignalScorer) -> None:
    """All factors at midpoint → score = 0.5."""
    candidate = _make_candidate(gap_pct=4.0, volume_ratio=1.75, price_distance_pct=1.5)
    assert scorer.score(candidate) == pytest.approx(0.5)


def test_score_with_equal_weights() -> None:
    """Verify scoring with custom equal weights."""
    weights = ScoringWeights(
        gap_pct_weight=1 / 3,
        volume_ratio_weight=1 / 3,
        price_distance_weight=1 / 3,
    )
    scorer = SignalScorer(weights)

    # gap=4.0 → norm=0.5, vol=1.75 → norm=0.5, dist=1.5 → norm=0.5
    candidate = _make_candidate(gap_pct=4.0, volume_ratio=1.75, price_distance_pct=1.5)
    assert scorer.score(candidate) == pytest.approx(0.5)


def test_score_gap_dominant() -> None:
    """High gap, low other factors → score weighted by gap_weight."""
    weights = ScoringWeights()  # 0.40, 0.35, 0.25
    scorer = SignalScorer(weights)

    candidate = _make_candidate(gap_pct=5.0, volume_ratio=0.5, price_distance_pct=0.0)
    # gap=1.0*0.40 + vol=0.0*0.35 + dist=0.0*0.25 = 0.40
    assert scorer.score(candidate) == pytest.approx(0.40)


# ── Strategy dispatch (Phase 2) ────────────────────────────────


def _make_strategy_candidate(
    strategy_name: str,
    gap_pct: float = 2.0,
    volume_ratio: float = 2.5,
    price_distance_pct: float = 1.0,
) -> CandidateSignal:
    """Helper for strategy-dispatch tests with configurable strategy_name."""
    return CandidateSignal(
        symbol="SBIN",
        direction=SignalDirection.BUY,
        strategy_name=strategy_name,
        entry_price=104.0,
        stop_loss=101.0,
        target_1=109.2,
        target_2=111.28,
        gap_pct=gap_pct,
        volume_ratio=volume_ratio,
        price_distance_from_open_pct=price_distance_pct,
        reason="test signal",
        generated_at=datetime.now(),
    )


def test_orb_strategy_dispatches_to_orb_scorer() -> None:
    """ORB strategy candidate dispatches to ORBScorer.score()."""
    orb_scorer = MagicMock(spec=ORBScorer)
    orb_scorer.score.return_value = 0.75
    scorer = SignalScorer(ScoringWeights(), orb_scorer=orb_scorer)

    candidate = _make_strategy_candidate("ORB", volume_ratio=3.0,
                                         gap_pct=1.5, price_distance_pct=0.5)
    result = scorer.score(candidate)

    assert result == 0.75
    orb_scorer.score.assert_called_once_with(
        volume_ratio=3.0,
        range_size_pct=1.5,
        distance_from_breakout_pct=0.5,
    )


def test_vwap_strategy_dispatches_to_vwap_scorer() -> None:
    """VWAP Reversal candidate dispatches to VWAPScorer.score()."""
    vwap_scorer = MagicMock(spec=VWAPScorer)
    vwap_scorer.score.return_value = 0.65
    scorer = SignalScorer(ScoringWeights(), vwap_scorer=vwap_scorer)

    candidate = _make_strategy_candidate("VWAP Reversal", volume_ratio=2.5,
                                         price_distance_pct=0.1,
                                         gap_pct=0.8)
    result = scorer.score(candidate)

    assert result == 0.65
    vwap_scorer.score.assert_called_once_with(
        volume_ratio=2.5,
        vwap_touch_pct=0.1,
        candles_above_vwap_ratio=0.8,
    )


def test_gap_and_go_uses_default_scoring() -> None:
    """Gap & Go candidate uses _score_gap_and_go (default path)."""
    orb_scorer = MagicMock(spec=ORBScorer)
    vwap_scorer = MagicMock(spec=VWAPScorer)
    scorer = SignalScorer(ScoringWeights(), orb_scorer=orb_scorer, vwap_scorer=vwap_scorer)

    candidate = _make_strategy_candidate("Gap & Go", gap_pct=4.0,
                                         volume_ratio=1.75,
                                         price_distance_pct=1.5)
    result = scorer.score(candidate)

    # Default Gap & Go: norm_gap=0.5, norm_vol=0.5, norm_dist=0.5 -> 0.5
    assert result == pytest.approx(0.5)
    # Neither ORB nor VWAP scorer should be called
    orb_scorer.score.assert_not_called()
    vwap_scorer.score.assert_not_called()


def test_unknown_strategy_falls_back_to_gap_and_go() -> None:
    """Unknown strategy name falls back to Gap & Go scoring."""
    orb_scorer = MagicMock(spec=ORBScorer)
    vwap_scorer = MagicMock(spec=VWAPScorer)
    scorer = SignalScorer(ScoringWeights(), orb_scorer=orb_scorer, vwap_scorer=vwap_scorer)

    candidate = _make_strategy_candidate("Unknown Strategy", gap_pct=5.0,
                                         volume_ratio=3.0,
                                         price_distance_pct=3.0)
    result = scorer.score(candidate)

    # All at max: gap=1.0*0.40 + vol=1.0*0.35 + dist=1.0*0.25 = 1.0
    assert result == pytest.approx(1.0)
    orb_scorer.score.assert_not_called()
    vwap_scorer.score.assert_not_called()


def test_orb_without_scorer_falls_back_to_gap_and_go() -> None:
    """ORB candidate without ORBScorer instance falls back to Gap & Go."""
    scorer = SignalScorer(ScoringWeights(), orb_scorer=None, vwap_scorer=None)

    candidate = _make_strategy_candidate("ORB", gap_pct=4.0,
                                         volume_ratio=1.75,
                                         price_distance_pct=1.5)
    result = scorer.score(candidate)

    # Falls back to Gap & Go scoring: 0.5
    assert result == pytest.approx(0.5)


def test_vwap_without_scorer_falls_back_to_gap_and_go() -> None:
    """VWAP Reversal candidate without VWAPScorer instance falls back to Gap & Go."""
    scorer = SignalScorer(ScoringWeights(), orb_scorer=None, vwap_scorer=None)

    candidate = _make_strategy_candidate("VWAP Reversal", gap_pct=5.0,
                                         volume_ratio=3.0,
                                         price_distance_pct=3.0)
    result = scorer.score(candidate)

    # Falls back to Gap & Go scoring: 1.0
    assert result == pytest.approx(1.0)


def test_orb_dispatch_with_real_scorer() -> None:
    """ORB candidate scored by a real ORBScorer produces expected result."""
    orb_scorer = ORBScorer()
    scorer = SignalScorer(ScoringWeights(), orb_scorer=orb_scorer)

    # All at midpoint for ORB: vol=2.75, range=1.75, dist=1.5
    candidate = _make_strategy_candidate("ORB", volume_ratio=2.75,
                                         gap_pct=1.75,
                                         price_distance_pct=1.5)
    result = scorer.score(candidate)

    assert result == pytest.approx(0.5)


def test_vwap_dispatch_with_real_scorer() -> None:
    """VWAP Reversal candidate scored by a real VWAPScorer produces expected result."""
    vwap_scorer = VWAPScorer()
    scorer = SignalScorer(ScoringWeights(), vwap_scorer=vwap_scorer)

    # All at midpoint for VWAP: vol=2.0, touch=0.15, trend=0.5
    candidate = _make_strategy_candidate("VWAP Reversal", volume_ratio=2.0,
                                         price_distance_pct=0.15,
                                         gap_pct=0.5)
    result = scorer.score(candidate)

    assert result == pytest.approx(0.5)
