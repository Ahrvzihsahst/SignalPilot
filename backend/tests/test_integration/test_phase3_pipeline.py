"""Phase 3 pipeline integration test: multi-strategy confirmation through to signal delivery."""

from datetime import datetime

from signalpilot.db.models import CandidateSignal, ScoringWeights, SignalDirection
from signalpilot.ranking.composite_scorer import CompositeScorer
from signalpilot.ranking.confidence import ConfidenceDetector
from signalpilot.ranking.ranker import SignalRanker
from signalpilot.ranking.scorer import SignalScorer
from signalpilot.risk.position_sizer import PositionSizer
from signalpilot.utils.constants import IST


def _make_candidate(symbol, strategy, entry=100.0, sl=95.0, t1=105.0, t2=110.0):
    return CandidateSignal(
        symbol=symbol,
        strategy_name=strategy,
        direction=SignalDirection.BUY,
        entry_price=entry,
        stop_loss=sl,
        target_1=t1,
        target_2=t2,
        reason=f"Test {strategy} signal for {symbol}",
        generated_at=datetime.now(IST),
    )


class TestPhase3Pipeline:
    """End-to-end test of the Phase 3 signal pipeline."""

    async def test_double_confirmation_pipeline(self):
        """Two strategies for the same stock produces double confirmation."""
        detector = ConfidenceDetector(signal_repo=None)
        scorer = CompositeScorer(signal_scorer=None, strategy_performance_repo=None)
        now = datetime.now(IST)

        # Two strategies signaling same stock
        candidates = [
            _make_candidate("RELIANCE", "gap_go"),
            _make_candidate("RELIANCE", "ORB"),
        ]

        # Step 1: Detect confirmations
        confirmations_list = await detector.detect_confirmations(candidates, now)
        assert len(confirmations_list) == 2
        for _, conf in confirmations_list:
            assert conf.confirmation_level == "double"
            assert conf.position_size_multiplier == 1.5

        # Step 2: Compute composite scores
        confirmation_map = {}
        composite_scores = {}
        for cand, conf in confirmations_list:
            result = await scorer.score(cand, conf, now.date())
            composite_scores[cand.symbol] = result
            confirmation_map[cand.symbol] = conf
            # Double confirmation -> bonus = 50
            assert result.confirmation_bonus == 50.0
            assert 0 <= result.composite_score <= 100

        # Step 3: Rank signals (provide a real scorer for the ranker)
        legacy_scorer = SignalScorer(weights=ScoringWeights())
        ranker = SignalRanker(scorer=legacy_scorer, max_signals=5)
        ranked = ranker.rank(
            candidates,
            composite_scores=composite_scores,
            confirmations=confirmation_map,
        )
        assert len(ranked) > 0
        # Both should have boosted stars
        for r in ranked:
            assert r.signal_strength >= 1  # At least 1 star

    async def test_triple_confirmation_pipeline(self):
        """Three strategies for the same stock produces triple confirmation."""
        detector = ConfidenceDetector(signal_repo=None)
        scorer = CompositeScorer(signal_scorer=None, strategy_performance_repo=None)
        now = datetime.now(IST)

        candidates = [
            _make_candidate("RELIANCE", "gap_go"),
            _make_candidate("RELIANCE", "ORB"),
            _make_candidate("RELIANCE", "VWAP Reversal"),
        ]

        confirmations_list = await detector.detect_confirmations(candidates, now)
        for _, conf in confirmations_list:
            assert conf.confirmation_level == "triple"
            assert conf.position_size_multiplier == 2.0

        # Composite score with triple bonus
        cand, conf = confirmations_list[0]
        result = await scorer.score(cand, conf, now.date())
        assert result.confirmation_bonus == 100.0

    async def test_position_sizing_with_multiplier(self):
        """Confirmed signals get larger position sizes, capped appropriately."""
        sizer = PositionSizer()

        # Normal position
        normal = sizer.calculate(
            entry_price=100.0,
            total_capital=100000.0,
            max_positions=8,
        )

        # 1.5x (double confirmed)
        double = sizer.calculate(
            entry_price=100.0,
            total_capital=100000.0,
            max_positions=8,
            multiplier=1.5,
        )

        # 2.0x (triple confirmed)
        triple = sizer.calculate(
            entry_price=100.0,
            total_capital=100000.0,
            max_positions=8,
            multiplier=2.0,
        )

        assert double.quantity > normal.quantity
        assert triple.quantity >= double.quantity

        # Verify caps
        assert double.capital_required <= 100000.0 * 0.20  # 20% cap
        assert triple.capital_required <= 100000.0 * 0.25  # 25% cap

    async def test_single_strategy_no_boost(self):
        """Single-strategy candidate gets no confirmation boost."""
        detector = ConfidenceDetector(signal_repo=None)
        scorer = CompositeScorer(signal_scorer=None, strategy_performance_repo=None)
        now = datetime.now(IST)

        candidates = [_make_candidate("TCS", "gap_go")]
        confirmations_list = await detector.detect_confirmations(candidates, now)

        _, conf = confirmations_list[0]
        assert conf.confirmation_level == "single"
        assert conf.star_boost == 0

        result = await scorer.score(candidates[0], conf, now.date())
        assert result.confirmation_bonus == 0.0
