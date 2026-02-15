"""Tests for SignalRanker."""

from datetime import datetime

import pytest

from signalpilot.db.models import CandidateSignal, ScoringWeights, SignalDirection
from signalpilot.ranking.ranker import SignalRanker
from signalpilot.ranking.scorer import SignalScorer


def _make_candidate(
    symbol: str = "SBIN",
    gap_pct: float = 4.0,
    volume_ratio: float = 1.5,
    price_distance_pct: float = 1.5,
) -> CandidateSignal:
    return CandidateSignal(
        symbol=symbol,
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
def scorer() -> SignalScorer:
    return SignalScorer(ScoringWeights())


@pytest.fixture
def ranker(scorer: SignalScorer) -> SignalRanker:
    return SignalRanker(scorer, max_signals=5)


# ── Ranking order ────────────────────────────────────────────────


def test_ranking_order_descending(ranker: SignalRanker) -> None:
    """Highest score should be ranked first."""
    candidates = [
        _make_candidate("LOW", gap_pct=3.0, volume_ratio=0.5, price_distance_pct=0.0),
        _make_candidate("HIGH", gap_pct=5.0, volume_ratio=3.0, price_distance_pct=3.0),
        _make_candidate("MID", gap_pct=4.0, volume_ratio=1.75, price_distance_pct=1.5),
    ]

    ranked = ranker.rank(candidates)

    assert len(ranked) == 3
    assert ranked[0].candidate.symbol == "HIGH"
    assert ranked[1].candidate.symbol == "MID"
    assert ranked[2].candidate.symbol == "LOW"
    assert ranked[0].rank == 1
    assert ranked[1].rank == 2
    assert ranked[2].rank == 3


def test_ranking_scores_descending(ranker: SignalRanker) -> None:
    """Composite scores should be in descending order."""
    candidates = [
        _make_candidate("A", gap_pct=5.0, volume_ratio=3.0, price_distance_pct=3.0),
        _make_candidate("B", gap_pct=4.0, volume_ratio=1.75, price_distance_pct=1.5),
        _make_candidate("C", gap_pct=3.0, volume_ratio=0.5, price_distance_pct=0.0),
    ]

    ranked = ranker.rank(candidates)

    for i in range(len(ranked) - 1):
        assert ranked[i].composite_score >= ranked[i + 1].composite_score


# ── Top-5 cutoff ─────────────────────────────────────────────────


def test_top_5_cutoff(ranker: SignalRanker) -> None:
    """6 candidates should be capped to 5 returned."""
    candidates = [
        _make_candidate(f"S{i}", gap_pct=3.0 + i * 0.3, volume_ratio=1.0, price_distance_pct=1.0)
        for i in range(6)
    ]

    ranked = ranker.rank(candidates)

    assert len(ranked) == 5
    # Verify rank numbering is 1-5
    assert [r.rank for r in ranked] == [1, 2, 3, 4, 5]


def test_custom_max_signals(scorer: SignalScorer) -> None:
    """Custom max_signals should limit output."""
    ranker = SignalRanker(scorer, max_signals=2)
    candidates = [
        _make_candidate(f"S{i}", gap_pct=3.5 + i * 0.5)
        for i in range(5)
    ]

    ranked = ranker.rank(candidates)

    assert len(ranked) == 2


# ── Fewer than 5 candidates ─────────────────────────────────────


def test_fewer_than_max_returns_all(ranker: SignalRanker) -> None:
    """3 candidates with max_signals=5 should return all 3."""
    candidates = [
        _make_candidate(f"S{i}", gap_pct=3.5 + i * 0.5)
        for i in range(3)
    ]

    ranked = ranker.rank(candidates)

    assert len(ranked) == 3


# ── Empty list ───────────────────────────────────────────────────


def test_empty_candidates_returns_empty(ranker: SignalRanker) -> None:
    ranked = ranker.rank([])
    assert ranked == []


# ── Star ratings ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "score, expected_stars",
    [
        (0.0, 1),
        (0.1, 1),
        (0.19, 1),
        (0.2, 2),
        (0.3, 2),
        (0.39, 2),
        (0.4, 3),
        (0.5, 3),
        (0.59, 3),
        (0.6, 4),
        (0.7, 4),
        (0.79, 4),
        (0.8, 5),
        (0.9, 5),
        (1.0, 5),
    ],
)
def test_score_to_stars(score: float, expected_stars: int) -> None:
    assert SignalRanker._score_to_stars(score) == expected_stars


# ── Star assignment in ranked output ─────────────────────────────


def test_stars_assigned_in_ranked_output(ranker: SignalRanker) -> None:
    """Verify stars are correctly assigned based on composite score."""
    candidates = [
        # Max score → 5 stars
        _make_candidate("TOP", gap_pct=5.0, volume_ratio=3.0, price_distance_pct=3.0),
        # Min score → 1 star
        _make_candidate("BOT", gap_pct=3.0, volume_ratio=0.5, price_distance_pct=0.0),
    ]

    ranked = ranker.rank(candidates)

    assert ranked[0].signal_strength == 5
    assert ranked[0].composite_score == pytest.approx(1.0)
    assert ranked[1].signal_strength == 1
    assert ranked[1].composite_score == pytest.approx(0.0)


# ── Single candidate ────────────────────────────────────────────


def test_single_candidate(ranker: SignalRanker) -> None:
    candidates = [_make_candidate("ONLY")]

    ranked = ranker.rank(candidates)

    assert len(ranked) == 1
    assert ranked[0].rank == 1
    assert ranked[0].candidate.symbol == "ONLY"


# ── Stable sort on tied scores ───────────────────────────────────


def test_ranking_with_tied_scores(ranker: SignalRanker) -> None:
    """Signals with identical scores should maintain stable input order."""
    candidates = [
        _make_candidate("A", gap_pct=4.0, volume_ratio=1.75, price_distance_pct=1.5),
        _make_candidate("B", gap_pct=4.0, volume_ratio=1.75, price_distance_pct=1.5),
        _make_candidate("C", gap_pct=4.0, volume_ratio=1.75, price_distance_pct=1.5),
    ]

    ranked = ranker.rank(candidates)

    assert ranked[0].composite_score == ranked[1].composite_score == ranked[2].composite_score
    # Python's sort is stable — input order preserved on ties
    assert ranked[0].candidate.symbol == "A"
    assert ranked[1].candidate.symbol == "B"
    assert ranked[2].candidate.symbol == "C"
