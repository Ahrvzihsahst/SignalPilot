"""Integration tests for the News Sentiment Filter pipeline flow.

These tests exercise the NewsSentimentStage within the full pipeline context,
verifying that suppression, downgrade, pass-through, earnings blackout,
cache miss, and feature-disabled flows work end-to-end.
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from signalpilot.db.models import (
    CandidateSignal,
    FinalSignal,
    RankedSignal,
    SentimentResult,
    SignalDirection,
    SuppressedSignal,
    UserConfig,
)
from signalpilot.pipeline.context import ScanContext
from signalpilot.pipeline.stages.news_sentiment import NewsSentimentStage
from signalpilot.pipeline.stages.persist_and_deliver import PersistAndDeliverStage
from signalpilot.pipeline.stages.risk_sizing import RiskSizingStage
from signalpilot.utils.constants import IST
from signalpilot.utils.market_calendar import StrategyPhase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(**overrides):
    defaults = {
        "news_enabled": True,
        "earnings_blackout_enabled": True,
        "strong_negative_threshold": -0.5,
        "mild_negative_threshold": -0.2,
        "positive_threshold": 0.3,
        "news_lookback_hours": 24,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_ranked(symbol="SBIN", strength=4, strategy="Gap & Go"):
    candidate = CandidateSignal(
        symbol=symbol,
        direction=SignalDirection.BUY,
        strategy_name=strategy,
        entry_price=100.0,
        stop_loss=97.0,
        target_1=105.0,
        target_2=107.0,
        gap_pct=4.0,
        volume_ratio=2.0,
        reason="Test signal",
        generated_at=datetime(2025, 1, 15, 9, 35, tzinfo=IST),
    )
    return RankedSignal(
        candidate=candidate,
        composite_score=0.8,
        rank=1,
        signal_strength=strength,
    )


def _make_sentiment(label="NEUTRAL", score=0.0, action="PASS"):
    return SentimentResult(
        score=score,
        label=label,
        headline="Test headline",
        action=action,
        headline_count=3,
        top_negative_headline="Negative headline",
        model_used="vader",
    )


def _make_mock_risk_sizing():
    """Create a mock RiskSizingStage that passes signals through."""
    stage = MagicMock()
    stage.name = "risk_sizing"

    async def process(ctx):
        ctx.final_signals = [
            FinalSignal(
                ranked_signal=rs,
                quantity=10,
                capital_required=1000.0,
                expires_at=datetime(2025, 1, 15, 10, 5, tzinfo=IST),
            )
            for rs in ctx.ranked_signals
        ]
        return ctx

    stage.process = process
    return stage


def _make_mock_persist_deliver():
    """Create a mock PersistAndDeliverStage that records calls."""
    stage = MagicMock()
    stage.name = "persist_and_deliver"
    stage.delivered_signals = []
    stage.suppression_notifications = []

    async def process(ctx):
        stage.delivered_signals.extend(ctx.final_signals)
        stage.suppression_notifications.extend(ctx.suppressed_signals)
        return ctx

    stage.process = process
    return stage


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestNewsSentimentPipelineIntegration:
    """Integration tests exercising NewsSentimentStage in a pipeline context."""

    async def test_suppress_flow_end_to_end(self):
        """STRONG_NEGATIVE suppresses signal and produces suppression notification."""
        config = _make_config()
        service = AsyncMock()
        service.get_sentiment_batch.return_value = {
            "SBIN": _make_sentiment("STRONG_NEGATIVE", -0.72, "SUPPRESSED"),
        }
        service.is_unsuppressed = MagicMock(return_value=False)
        earnings = AsyncMock()
        earnings.has_earnings_today.return_value = False

        nsf_stage = NewsSentimentStage(service, earnings, config)
        persist = _make_mock_persist_deliver()

        # Run NSF stage then persist
        ctx = ScanContext(phase=StrategyPhase.OPENING)
        ctx.ranked_signals = [_make_ranked()]

        ctx = await nsf_stage.process(ctx)
        assert len(ctx.ranked_signals) == 0
        assert len(ctx.suppressed_signals) == 1

        # Persist stage should see suppressed signals
        ctx = await persist.process(ctx)
        assert len(persist.suppression_notifications) == 1
        assert persist.suppression_notifications[0].symbol == "SBIN"
        assert len(persist.delivered_signals) == 0

    async def test_downgrade_flow_reduces_star_rating(self):
        """MILD_NEGATIVE downgrades from 4 to 3 stars, signal still delivered."""
        config = _make_config()
        service = AsyncMock()
        service.get_sentiment_batch.return_value = {
            "SBIN": _make_sentiment("MILD_NEGATIVE", -0.35, "DOWNGRADED"),
        }
        service.is_unsuppressed = MagicMock(return_value=False)
        earnings = AsyncMock()
        earnings.has_earnings_today.return_value = False

        nsf_stage = NewsSentimentStage(service, earnings, config)
        risk_sizing = _make_mock_risk_sizing()
        persist = _make_mock_persist_deliver()

        ctx = ScanContext(phase=StrategyPhase.OPENING)
        ctx.ranked_signals = [_make_ranked(strength=4)]

        ctx = await nsf_stage.process(ctx)
        assert len(ctx.ranked_signals) == 1
        assert ctx.ranked_signals[0].signal_strength == 3

        ctx = await risk_sizing.process(ctx)
        assert len(ctx.final_signals) == 1

        ctx = await persist.process(ctx)
        assert len(persist.delivered_signals) == 1
        assert len(persist.suppression_notifications) == 0

    async def test_positive_sentiment_passes_through(self):
        """POSITIVE sentiment passes signal through unchanged."""
        config = _make_config()
        service = AsyncMock()
        service.get_sentiment_batch.return_value = {
            "SBIN": _make_sentiment("POSITIVE", 0.5, "PASS"),
        }
        service.is_unsuppressed = MagicMock(return_value=False)
        earnings = AsyncMock()
        earnings.has_earnings_today.return_value = False

        nsf_stage = NewsSentimentStage(service, earnings, config)

        ctx = ScanContext(phase=StrategyPhase.OPENING)
        ctx.ranked_signals = [_make_ranked(strength=4)]

        ctx = await nsf_stage.process(ctx)
        assert len(ctx.ranked_signals) == 1
        assert ctx.ranked_signals[0].signal_strength == 4
        assert ctx.sentiment_results["SBIN"].label == "POSITIVE"

    async def test_earnings_blackout_overrides_positive(self):
        """Earnings blackout suppresses signal even with POSITIVE sentiment."""
        config = _make_config()
        service = AsyncMock()
        service.get_sentiment_batch.return_value = {
            "SBIN": _make_sentiment("POSITIVE", 0.8, "PASS"),
        }
        service.is_unsuppressed = MagicMock(return_value=False)
        earnings = AsyncMock()
        earnings.has_earnings_today.return_value = True

        nsf_stage = NewsSentimentStage(service, earnings, config)

        ctx = ScanContext(phase=StrategyPhase.OPENING)
        ctx.ranked_signals = [_make_ranked()]

        ctx = await nsf_stage.process(ctx)
        assert len(ctx.ranked_signals) == 0
        assert len(ctx.suppressed_signals) == 1
        assert ctx.suppressed_signals[0].sentiment_label == "EARNINGS_BLACKOUT"

    async def test_cache_miss_passes_through(self):
        """Symbol not in sentiment batch results passes through as NO_NEWS."""
        config = _make_config()
        service = AsyncMock()
        service.get_sentiment_batch.return_value = {}  # No data
        service.is_unsuppressed = MagicMock(return_value=False)
        earnings = AsyncMock()
        earnings.has_earnings_today.return_value = False

        nsf_stage = NewsSentimentStage(service, earnings, config)

        ctx = ScanContext(phase=StrategyPhase.OPENING)
        ctx.ranked_signals = [_make_ranked()]

        ctx = await nsf_stage.process(ctx)
        assert len(ctx.ranked_signals) == 1

    async def test_feature_disabled_passes_all(self):
        """news_enabled=False passes all signals through unchanged."""
        config = _make_config(news_enabled=False)
        service = AsyncMock()
        earnings = AsyncMock()

        nsf_stage = NewsSentimentStage(service, earnings, config)

        ctx = ScanContext(phase=StrategyPhase.OPENING)
        ctx.ranked_signals = [_make_ranked("SBIN"), _make_ranked("TCS")]

        ctx = await nsf_stage.process(ctx)
        assert len(ctx.ranked_signals) == 2
        service.get_sentiment_batch.assert_not_awaited()

    async def test_mixed_signals_pipeline(self):
        """Multiple signals with different sentiments flow through pipeline correctly."""
        config = _make_config()
        service = AsyncMock()
        service.get_sentiment_batch.return_value = {
            "SBIN": _make_sentiment("STRONG_NEGATIVE", -0.72, "SUPPRESSED"),
            "TCS": _make_sentiment("MILD_NEGATIVE", -0.35, "DOWNGRADED"),
            "RELIANCE": _make_sentiment("POSITIVE", 0.5, "PASS"),
            "INFY": _make_sentiment("NO_NEWS", 0.0, "PASS"),
        }
        service.is_unsuppressed = MagicMock(return_value=False)
        earnings = AsyncMock()
        earnings.has_earnings_today.return_value = False

        nsf_stage = NewsSentimentStage(service, earnings, config)
        risk_sizing = _make_mock_risk_sizing()
        persist = _make_mock_persist_deliver()

        ctx = ScanContext(phase=StrategyPhase.OPENING)
        ctx.ranked_signals = [
            _make_ranked("SBIN", 4),
            _make_ranked("TCS", 3),
            _make_ranked("RELIANCE", 5),
            _make_ranked("INFY", 4),
        ]

        # NSF stage
        ctx = await nsf_stage.process(ctx)
        assert len(ctx.ranked_signals) == 3  # SBIN suppressed
        assert len(ctx.suppressed_signals) == 1
        assert ctx.suppressed_signals[0].symbol == "SBIN"

        # Check TCS downgraded
        tcs = next(rs for rs in ctx.ranked_signals if rs.candidate.symbol == "TCS")
        assert tcs.signal_strength == 2  # 3 -> 2

        # RELIANCE and INFY unchanged
        rel = next(rs for rs in ctx.ranked_signals if rs.candidate.symbol == "RELIANCE")
        assert rel.signal_strength == 5
        infy = next(rs for rs in ctx.ranked_signals if rs.candidate.symbol == "INFY")
        assert infy.signal_strength == 4

        # Risk sizing
        ctx = await risk_sizing.process(ctx)
        assert len(ctx.final_signals) == 3

        # Persist
        ctx = await persist.process(ctx)
        assert len(persist.delivered_signals) == 3
        assert len(persist.suppression_notifications) == 1

    async def test_unsuppress_override_in_pipeline(self):
        """Unsuppress override allows STRONG_NEGATIVE signal through."""
        config = _make_config()
        service = AsyncMock()
        service.get_sentiment_batch.return_value = {
            "SBIN": _make_sentiment("STRONG_NEGATIVE", -0.72, "SUPPRESSED"),
        }
        service.is_unsuppressed = MagicMock(return_value=True)
        earnings = AsyncMock()
        earnings.has_earnings_today.return_value = False

        nsf_stage = NewsSentimentStage(service, earnings, config)

        ctx = ScanContext(phase=StrategyPhase.OPENING)
        ctx.ranked_signals = [_make_ranked()]

        ctx = await nsf_stage.process(ctx)
        assert len(ctx.ranked_signals) == 1
        assert len(ctx.suppressed_signals) == 0
        assert ctx.sentiment_results["SBIN"].action == "UNSUPPRESSED"

    async def test_sentiment_results_populated_in_context(self):
        """All sentiment results are available in ctx.sentiment_results after processing."""
        config = _make_config()
        service = AsyncMock()
        service.get_sentiment_batch.return_value = {
            "SBIN": _make_sentiment("NEUTRAL", 0.05, "PASS"),
            "TCS": _make_sentiment("POSITIVE", 0.6, "PASS"),
        }
        service.is_unsuppressed = MagicMock(return_value=False)
        earnings = AsyncMock()
        earnings.has_earnings_today.return_value = False

        nsf_stage = NewsSentimentStage(service, earnings, config)

        ctx = ScanContext(phase=StrategyPhase.OPENING)
        ctx.ranked_signals = [_make_ranked("SBIN"), _make_ranked("TCS")]

        ctx = await nsf_stage.process(ctx)
        assert "SBIN" in ctx.sentiment_results
        assert "TCS" in ctx.sentiment_results
        assert ctx.sentiment_results["SBIN"].label == "NEUTRAL"
        assert ctx.sentiment_results["TCS"].label == "POSITIVE"

    async def test_earnings_blackout_disabled_ignores_earnings(self):
        """When earnings_blackout_enabled=False, earnings day does not suppress."""
        config = _make_config(earnings_blackout_enabled=False)
        service = AsyncMock()
        service.get_sentiment_batch.return_value = {
            "SBIN": _make_sentiment("NEUTRAL", 0.0, "PASS"),
        }
        service.is_unsuppressed = MagicMock(return_value=False)
        earnings = AsyncMock()
        earnings.has_earnings_today.return_value = True

        nsf_stage = NewsSentimentStage(service, earnings, config)

        ctx = ScanContext(phase=StrategyPhase.OPENING)
        ctx.ranked_signals = [_make_ranked()]

        ctx = await nsf_stage.process(ctx)
        assert len(ctx.ranked_signals) == 1
        assert len(ctx.suppressed_signals) == 0
