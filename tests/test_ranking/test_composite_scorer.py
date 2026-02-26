"""Tests for CompositeScorer."""

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from signalpilot.db.models import CandidateSignal, SignalDirection
from signalpilot.ranking.composite_scorer import CompositeScorer
from signalpilot.ranking.confidence import ConfirmationResult
from signalpilot.utils.constants import IST


def _make_candidate(
    entry=100.0, sl=95.0, t1=105.0, t2=110.0, strategy_score=None
) -> CandidateSignal:
    """Create a CandidateSignal with sensible defaults for scoring tests."""
    c = CandidateSignal(
        symbol="RELIANCE",
        direction=SignalDirection.BUY,
        strategy_name="Gap & Go",
        entry_price=entry,
        stop_loss=sl,
        target_1=t1,
        target_2=t2,
        reason="test",
        generated_at=datetime.now(IST),
    )
    if strategy_score is not None:
        c.strategy_specific_score = strategy_score
    return c


def _single_conf():
    return ConfirmationResult(
        confirmation_level="single",
        confirmed_by=["Gap & Go"],
        star_boost=0,
        position_size_multiplier=1.0,
    )


def _double_conf():
    return ConfirmationResult(
        confirmation_level="double",
        confirmed_by=["Gap & Go", "ORB"],
        star_boost=1,
        position_size_multiplier=1.5,
    )


def _triple_conf():
    return ConfirmationResult(
        confirmation_level="triple",
        confirmed_by=["Gap & Go", "ORB", "VWAP Reversal"],
        star_boost=2,
        position_size_multiplier=2.0,
    )


# ---------------------------------------------------------------------------
# _calculate_risk_reward_score (static method)
# ---------------------------------------------------------------------------


class TestRiskRewardScore:
    def test_rr_zero_risk(self):
        """Zero risk (entry == SL) returns 0."""
        score = CompositeScorer._calculate_risk_reward_score(
            _make_candidate(entry=100, sl=100, t2=110)
        )
        assert score == 0.0

    def test_rr_one_to_one(self):
        """R:R = 1:1 returns 0 (below minimum useful R:R)."""
        # entry=100, sl=95, t2=105 -> risk=5, reward=5 -> R:R=1.0 -> 0
        score = CompositeScorer._calculate_risk_reward_score(
            _make_candidate(entry=100, sl=95, t2=105)
        )
        assert score == 0.0

    def test_rr_two_to_one(self):
        """R:R = 2:1 maps to 50."""
        # entry=100, sl=95, t2=110 -> risk=5, reward=10 -> R:R=2.0 -> 50
        score = CompositeScorer._calculate_risk_reward_score(
            _make_candidate(entry=100, sl=95, t2=110)
        )
        assert score == 50.0

    def test_rr_three_to_one(self):
        """R:R = 3:1 maps to 100."""
        # entry=100, sl=95, t2=115 -> risk=5, reward=15 -> R:R=3.0 -> 100
        score = CompositeScorer._calculate_risk_reward_score(
            _make_candidate(entry=100, sl=95, t2=115)
        )
        assert score == 100.0

    def test_rr_above_three(self):
        """R:R > 3 caps at 100."""
        # risk=5, reward=20 -> R:R=4.0 -> 100 (capped)
        score = CompositeScorer._calculate_risk_reward_score(
            _make_candidate(entry=100, sl=95, t2=120)
        )
        assert score == 100.0

    def test_negative_reward(self):
        """Target below entry returns 0."""
        score = CompositeScorer._calculate_risk_reward_score(
            _make_candidate(entry=100, sl=95, t2=90)
        )
        assert score == 0.0

    def test_negative_risk(self):
        """SL above entry (inverted) returns 0."""
        score = CompositeScorer._calculate_risk_reward_score(
            _make_candidate(entry=100, sl=105, t2=110)
        )
        assert score == 0.0

    def test_rr_1_5_to_one(self):
        """R:R = 1.5:1 maps to 25 (linear interpolation)."""
        # entry=100, sl=95, t2=107.5 -> risk=5, reward=7.5 -> R:R=1.5
        # (1.5 - 1.0) / 2.0 * 100 = 25
        score = CompositeScorer._calculate_risk_reward_score(
            _make_candidate(entry=100, sl=95, t2=107.5)
        )
        assert score == pytest.approx(25.0)

    def test_rr_2_5_to_one(self):
        """R:R = 2.5:1 maps to 75 (linear interpolation)."""
        # entry=100, sl=95, t2=112.5 -> risk=5, reward=12.5 -> R:R=2.5
        # (2.5 - 1.0) / 2.0 * 100 = 75
        score = CompositeScorer._calculate_risk_reward_score(
            _make_candidate(entry=100, sl=95, t2=112.5)
        )
        assert score == pytest.approx(75.0)


# ---------------------------------------------------------------------------
# _get_confirmation_bonus (static method)
# ---------------------------------------------------------------------------


class TestConfirmationBonus:
    def test_single(self):
        assert CompositeScorer._get_confirmation_bonus(_single_conf()) == 0.0

    def test_double(self):
        assert CompositeScorer._get_confirmation_bonus(_double_conf()) == 50.0

    def test_triple(self):
        assert CompositeScorer._get_confirmation_bonus(_triple_conf()) == 100.0

    def test_unknown_level_defaults_to_zero(self):
        """An unknown confirmation level returns 0."""
        conf = ConfirmationResult(
            confirmation_level="unknown", confirmed_by=[], star_boost=0,
            position_size_multiplier=1.0,
        )
        assert CompositeScorer._get_confirmation_bonus(conf) == 0.0


# ---------------------------------------------------------------------------
# score (async, composite calculation)
# ---------------------------------------------------------------------------


class TestCompositeScore:
    async def test_known_inputs_single_confirmation(self):
        """All defaults: strength=50, win_rate=50, rr=50 (2:1), bonus=0."""
        scorer = CompositeScorer(signal_scorer=None, strategy_performance_repo=None)
        # entry=100, sl=95, t2=110 -> R:R=2.0 -> rr_score=50
        candidate = _make_candidate(entry=100, sl=95, t2=110)
        result = await scorer.score(candidate, _single_conf(), date(2025, 1, 15))

        # 50*0.4 + 50*0.3 + 50*0.2 + 0*0.1 = 20+15+10+0 = 45
        assert result.composite_score == 45.0
        assert result.strategy_strength_score == 50.0
        assert result.win_rate_score == 50.0
        assert result.risk_reward_score == 50.0
        assert result.confirmation_bonus == 0.0

    async def test_double_confirmation_bonus(self):
        """Double confirmation adds bonus=50 at weight 0.1 -> +5 points."""
        scorer = CompositeScorer(signal_scorer=None, strategy_performance_repo=None)
        candidate = _make_candidate(entry=100, sl=95, t2=110)
        result = await scorer.score(candidate, _double_conf(), date(2025, 1, 15))

        # 50*0.4 + 50*0.3 + 50*0.2 + 50*0.1 = 20+15+10+5 = 50
        assert result.composite_score == 50.0
        assert result.confirmation_bonus == 50.0

    async def test_triple_confirmation_bonus(self):
        """Triple confirmation adds bonus=100 at weight 0.1 -> +10 points."""
        scorer = CompositeScorer(signal_scorer=None, strategy_performance_repo=None)
        candidate = _make_candidate(entry=100, sl=95, t2=110)
        result = await scorer.score(candidate, _triple_conf(), date(2025, 1, 15))

        # 50*0.4 + 50*0.3 + 50*0.2 + 100*0.1 = 20+15+10+10 = 55
        assert result.composite_score == 55.0
        assert result.confirmation_bonus == 100.0

    async def test_max_score(self):
        """Maximum inputs: strength=100, win_rate=50 (default), rr=100, bonus=100."""
        scorer = CompositeScorer(signal_scorer=None, strategy_performance_repo=None)
        # strategy_score=1.0 -> strength=100, R:R=3:1 -> rr=100
        candidate = _make_candidate(entry=100, sl=95, t2=115, strategy_score=1.0)
        result = await scorer.score(candidate, _triple_conf(), date(2025, 1, 15))

        # 100*0.4 + 50*0.3 + 100*0.2 + 100*0.1 = 40+15+20+10 = 85
        assert result.composite_score == 85.0

    async def test_min_score(self):
        """Minimum inputs: strength=50 (default), win_rate=50, rr=0, bonus=0."""
        scorer = CompositeScorer(signal_scorer=None, strategy_performance_repo=None)
        # R:R=1:1 -> rr=0
        candidate = _make_candidate(entry=100, sl=95, t2=105)
        result = await scorer.score(candidate, _single_conf(), date(2025, 1, 15))

        # 50*0.4 + 50*0.3 + 0*0.2 + 0*0.1 = 20+15+0+0 = 35
        assert result.composite_score == 35.0

    async def test_score_within_range(self):
        """Composite score is always in [0, 100]."""
        scorer = CompositeScorer(signal_scorer=None, strategy_performance_repo=None)
        candidate = _make_candidate(entry=100, sl=95, t2=115)
        result = await scorer.score(candidate, _triple_conf(), date(2025, 1, 15))
        assert 0.0 <= result.composite_score <= 100.0

    async def test_strategy_strength_from_candidate(self):
        """Strategy-specific score on candidate is used for strength factor."""
        scorer = CompositeScorer(signal_scorer=None, strategy_performance_repo=None)
        # strategy_specific_score=0.9 -> strength=90
        candidate = _make_candidate(strategy_score=0.9)
        # entry=100, sl=95, t2=110 -> rr=50
        result = await scorer.score(candidate, _single_conf(), date(2025, 1, 15))

        assert result.strategy_strength_score == 90.0
        # 90*0.4 + 50*0.3 + 50*0.2 + 0*0.1 = 36+15+10+0 = 61
        assert result.composite_score == 61.0

    async def test_strategy_strength_zero(self):
        """Strategy score of 0.0 yields strength=0."""
        scorer = CompositeScorer(signal_scorer=None, strategy_performance_repo=None)
        candidate = _make_candidate(strategy_score=0.0)
        result = await scorer.score(candidate, _single_conf(), date(2025, 1, 15))
        assert result.strategy_strength_score == 0.0

    async def test_strategy_strength_clamped_above_one(self):
        """Strategy score > 1.0 is clamped to 100."""
        scorer = CompositeScorer(signal_scorer=None, strategy_performance_repo=None)
        candidate = _make_candidate(strategy_score=1.5)
        result = await scorer.score(candidate, _single_conf(), date(2025, 1, 15))
        assert result.strategy_strength_score == 100.0

    async def test_default_win_rate_when_no_data(self):
        """Without a performance repo, win rate defaults to 50.0."""
        scorer = CompositeScorer(signal_scorer=None, strategy_performance_repo=None)
        candidate = _make_candidate()
        result = await scorer.score(candidate, _single_conf(), date(2025, 1, 15))
        assert result.win_rate_score == 50.0


# ---------------------------------------------------------------------------
# Win rate caching
# ---------------------------------------------------------------------------


class TestWinRateCache:
    async def test_win_rate_cached_within_same_day(self):
        """Win rate for a strategy is fetched once per day, then cached."""
        mock_repo = AsyncMock()
        mock_summary = MagicMock()
        mock_summary.win_rate = 70.0
        mock_repo.get_performance_summary = AsyncMock(return_value=mock_summary)

        scorer = CompositeScorer(strategy_performance_repo=mock_repo)
        candidate = _make_candidate()

        await scorer.score(candidate, _single_conf(), date(2025, 1, 15))
        await scorer.score(candidate, _single_conf(), date(2025, 1, 15))

        # Should only call repo once (cached for same day + same strategy)
        assert mock_repo.get_performance_summary.call_count == 1

    async def test_win_rate_cache_invalidated_on_new_day(self):
        """Cache is invalidated when the date changes."""
        mock_repo = AsyncMock()
        mock_summary = MagicMock()
        mock_summary.win_rate = 70.0
        mock_repo.get_performance_summary = AsyncMock(return_value=mock_summary)

        scorer = CompositeScorer(strategy_performance_repo=mock_repo)
        candidate = _make_candidate()

        await scorer.score(candidate, _single_conf(), date(2025, 1, 15))
        # Different date -> cache invalidated
        await scorer.score(candidate, _single_conf(), date(2025, 1, 16))

        assert mock_repo.get_performance_summary.call_count == 2

    async def test_win_rate_from_repo_used_in_score(self):
        """Win rate fetched from repo is incorporated into composite score."""
        mock_repo = AsyncMock()
        mock_summary = MagicMock()
        mock_summary.win_rate = 80.0
        mock_repo.get_performance_summary = AsyncMock(return_value=mock_summary)

        scorer = CompositeScorer(strategy_performance_repo=mock_repo)
        # entry=100, sl=95, t2=110 -> rr=50
        candidate = _make_candidate()
        result = await scorer.score(candidate, _single_conf(), date(2025, 1, 15))

        assert result.win_rate_score == 80.0
        # 50*0.4 + 80*0.3 + 50*0.2 + 0*0.1 = 20+24+10+0 = 54
        assert result.composite_score == 54.0

    async def test_win_rate_repo_exception_falls_back(self):
        """If the repo raises an exception, win rate defaults to 50.0."""
        mock_repo = AsyncMock()
        mock_repo.get_performance_summary = AsyncMock(
            side_effect=RuntimeError("DB error")
        )

        scorer = CompositeScorer(strategy_performance_repo=mock_repo)
        candidate = _make_candidate()
        result = await scorer.score(candidate, _single_conf(), date(2025, 1, 15))

        assert result.win_rate_score == 50.0

    async def test_win_rate_repo_returns_none(self):
        """If the repo returns None, win rate defaults to 50.0."""
        mock_repo = AsyncMock()
        mock_repo.get_performance_summary = AsyncMock(return_value=None)

        scorer = CompositeScorer(strategy_performance_repo=mock_repo)
        candidate = _make_candidate()
        result = await scorer.score(candidate, _single_conf(), date(2025, 1, 15))

        assert result.win_rate_score == 50.0

    async def test_different_strategies_cached_separately(self):
        """Each strategy has its own cache entry."""
        mock_repo = AsyncMock()
        mock_summary_gap = MagicMock()
        mock_summary_gap.win_rate = 70.0
        mock_summary_orb = MagicMock()
        mock_summary_orb.win_rate = 60.0

        async def side_effect(strategy_name, days=30):
            if strategy_name == "Gap & Go":
                return mock_summary_gap
            return mock_summary_orb

        mock_repo.get_performance_summary = AsyncMock(side_effect=side_effect)

        scorer = CompositeScorer(strategy_performance_repo=mock_repo)

        gap_candidate = _make_candidate()
        gap_candidate.strategy_name = "Gap & Go"
        orb_candidate = _make_candidate()
        orb_candidate.strategy_name = "ORB"

        gap_result = await scorer.score(gap_candidate, _single_conf(), date(2025, 1, 15))
        orb_result = await scorer.score(orb_candidate, _single_conf(), date(2025, 1, 15))

        assert gap_result.win_rate_score == 70.0
        assert orb_result.win_rate_score == 60.0
        assert mock_repo.get_performance_summary.call_count == 2
