"""Tests for the NewsSentimentStage pipeline stage."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from signalpilot.db.models import (
    CandidateSignal,
    RankedSignal,
    SentimentResult,
    SignalDirection,
)
from signalpilot.pipeline.context import ScanContext
from signalpilot.pipeline.stages.news_sentiment import NewsSentimentStage
from signalpilot.utils.market_calendar import StrategyPhase


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


def _make_ranked_signal(symbol="SBIN", strength=4, strategy="Gap & Go"):
    from datetime import datetime
    from signalpilot.utils.constants import IST
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


class TestNewsSentimentStage:
    """Tests for the NewsSentimentStage."""

    async def test_kill_switch_returns_unchanged(self):
        """news_enabled=False returns ctx unchanged."""
        config = _make_config(news_enabled=False)
        service = AsyncMock()
        earnings = AsyncMock()

        stage = NewsSentimentStage(service, earnings, config)
        ctx = ScanContext(phase=StrategyPhase.OPENING)
        ctx.ranked_signals = [_make_ranked_signal()]

        result = await stage.process(ctx)
        assert len(result.ranked_signals) == 1
        service.get_sentiment_batch.assert_not_awaited()

    async def test_empty_signals_returns_immediately(self):
        """Empty ranked_signals returns immediately."""
        config = _make_config()
        service = AsyncMock()
        earnings = AsyncMock()

        stage = NewsSentimentStage(service, earnings, config)
        ctx = ScanContext(phase=StrategyPhase.OPENING)
        ctx.ranked_signals = []

        result = await stage.process(ctx)
        assert len(result.ranked_signals) == 0
        service.get_sentiment_batch.assert_not_awaited()

    async def test_strong_negative_suppresses_signal(self):
        """STRONG_NEGATIVE removes signal, adds to suppressed_signals."""
        config = _make_config()
        service = AsyncMock()
        service.get_sentiment_batch.return_value = {
            "SBIN": _make_sentiment("STRONG_NEGATIVE", -0.72, "SUPPRESSED"),
        }
        service.is_unsuppressed = MagicMock(return_value=False)
        earnings = AsyncMock()
        earnings.has_earnings_today.return_value = False

        stage = NewsSentimentStage(service, earnings, config)
        ctx = ScanContext(phase=StrategyPhase.OPENING)
        ctx.ranked_signals = [_make_ranked_signal()]

        result = await stage.process(ctx)
        assert len(result.ranked_signals) == 0
        assert len(result.suppressed_signals) == 1
        assert result.suppressed_signals[0].symbol == "SBIN"
        assert result.suppressed_signals[0].sentiment_label == "STRONG_NEGATIVE"

    async def test_earnings_blackout_suppresses(self):
        """Earnings today suppresses regardless of sentiment."""
        config = _make_config()
        service = AsyncMock()
        service.get_sentiment_batch.return_value = {
            "SBIN": _make_sentiment("POSITIVE", 0.5, "PASS"),
        }
        service.is_unsuppressed = MagicMock(return_value=False)
        earnings = AsyncMock()
        earnings.has_earnings_today.return_value = True

        stage = NewsSentimentStage(service, earnings, config)
        ctx = ScanContext(phase=StrategyPhase.OPENING)
        ctx.ranked_signals = [_make_ranked_signal()]

        result = await stage.process(ctx)
        assert len(result.ranked_signals) == 0
        assert len(result.suppressed_signals) == 1
        assert result.suppressed_signals[0].sentiment_label == "EARNINGS_BLACKOUT"

    async def test_earnings_overrides_positive_sentiment(self):
        """Earnings blackout overrides positive sentiment."""
        config = _make_config()
        service = AsyncMock()
        service.get_sentiment_batch.return_value = {
            "SBIN": _make_sentiment("POSITIVE", 0.8, "PASS"),
        }
        service.is_unsuppressed = MagicMock(return_value=False)
        earnings = AsyncMock()
        earnings.has_earnings_today.return_value = True

        stage = NewsSentimentStage(service, earnings, config)
        ctx = ScanContext(phase=StrategyPhase.OPENING)
        ctx.ranked_signals = [_make_ranked_signal()]

        result = await stage.process(ctx)
        assert len(result.ranked_signals) == 0
        assert len(result.suppressed_signals) == 1

    async def test_mild_negative_downgrades_star_rating(self):
        """MILD_NEGATIVE reduces star rating by 1."""
        config = _make_config()
        service = AsyncMock()
        service.get_sentiment_batch.return_value = {
            "SBIN": _make_sentiment("MILD_NEGATIVE", -0.35, "DOWNGRADED"),
        }
        service.is_unsuppressed = MagicMock(return_value=False)
        earnings = AsyncMock()
        earnings.has_earnings_today.return_value = False

        stage = NewsSentimentStage(service, earnings, config)
        ctx = ScanContext(phase=StrategyPhase.OPENING)
        ctx.ranked_signals = [_make_ranked_signal(strength=4)]

        result = await stage.process(ctx)
        assert len(result.ranked_signals) == 1
        assert result.ranked_signals[0].signal_strength == 3  # 4 -> 3

    async def test_downgrade_minimum_stays_at_1(self):
        """1-star signal stays at 1 after downgrade."""
        config = _make_config()
        service = AsyncMock()
        service.get_sentiment_batch.return_value = {
            "SBIN": _make_sentiment("MILD_NEGATIVE", -0.35, "DOWNGRADED"),
        }
        service.is_unsuppressed = MagicMock(return_value=False)
        earnings = AsyncMock()
        earnings.has_earnings_today.return_value = False

        stage = NewsSentimentStage(service, earnings, config)
        ctx = ScanContext(phase=StrategyPhase.OPENING)
        ctx.ranked_signals = [_make_ranked_signal(strength=1)]

        result = await stage.process(ctx)
        assert len(result.ranked_signals) == 1
        assert result.ranked_signals[0].signal_strength == 1

    async def test_neutral_passes_through(self):
        """NEUTRAL passes signal unchanged."""
        config = _make_config()
        service = AsyncMock()
        service.get_sentiment_batch.return_value = {
            "SBIN": _make_sentiment("NEUTRAL", 0.0, "PASS"),
        }
        service.is_unsuppressed = MagicMock(return_value=False)
        earnings = AsyncMock()
        earnings.has_earnings_today.return_value = False

        stage = NewsSentimentStage(service, earnings, config)
        ctx = ScanContext(phase=StrategyPhase.OPENING)
        ctx.ranked_signals = [_make_ranked_signal(strength=4)]

        result = await stage.process(ctx)
        assert len(result.ranked_signals) == 1
        assert result.ranked_signals[0].signal_strength == 4

    async def test_positive_passes_through(self):
        """POSITIVE passes signal unchanged."""
        config = _make_config()
        service = AsyncMock()
        service.get_sentiment_batch.return_value = {
            "SBIN": _make_sentiment("POSITIVE", 0.5, "PASS"),
        }
        service.is_unsuppressed = MagicMock(return_value=False)
        earnings = AsyncMock()
        earnings.has_earnings_today.return_value = False

        stage = NewsSentimentStage(service, earnings, config)
        ctx = ScanContext(phase=StrategyPhase.OPENING)
        ctx.ranked_signals = [_make_ranked_signal(strength=4)]

        result = await stage.process(ctx)
        assert len(result.ranked_signals) == 1
        assert result.ranked_signals[0].signal_strength == 4

    async def test_no_news_passes_through(self):
        """NO_NEWS passes signal unchanged."""
        config = _make_config()
        service = AsyncMock()
        service.get_sentiment_batch.return_value = {
            "SBIN": _make_sentiment("NO_NEWS", 0.0, "PASS"),
        }
        service.is_unsuppressed = MagicMock(return_value=False)
        earnings = AsyncMock()
        earnings.has_earnings_today.return_value = False

        stage = NewsSentimentStage(service, earnings, config)
        ctx = ScanContext(phase=StrategyPhase.OPENING)
        ctx.ranked_signals = [_make_ranked_signal(strength=4)]

        result = await stage.process(ctx)
        assert len(result.ranked_signals) == 1

    async def test_cache_miss_treated_as_no_news(self):
        """Unknown stock not in batch results passes through."""
        config = _make_config()
        service = AsyncMock()
        service.get_sentiment_batch.return_value = {}  # No data
        service.is_unsuppressed = MagicMock(return_value=False)
        earnings = AsyncMock()
        earnings.has_earnings_today.return_value = False

        stage = NewsSentimentStage(service, earnings, config)
        ctx = ScanContext(phase=StrategyPhase.OPENING)
        ctx.ranked_signals = [_make_ranked_signal()]

        result = await stage.process(ctx)
        assert len(result.ranked_signals) == 1

    async def test_unsuppress_override_passes_through(self):
        """Unsuppressed stock passes through with UNSUPPRESSED action."""
        config = _make_config()
        service = AsyncMock()
        service.get_sentiment_batch.return_value = {
            "SBIN": _make_sentiment("STRONG_NEGATIVE", -0.72, "SUPPRESSED"),
        }
        service.is_unsuppressed = MagicMock(return_value=True)
        earnings = AsyncMock()
        earnings.has_earnings_today.return_value = False

        stage = NewsSentimentStage(service, earnings, config)
        ctx = ScanContext(phase=StrategyPhase.OPENING)
        ctx.ranked_signals = [_make_ranked_signal()]

        result = await stage.process(ctx)
        assert len(result.ranked_signals) == 1
        assert result.sentiment_results["SBIN"].action == "UNSUPPRESSED"

    async def test_multiple_signals_mixed_actions(self):
        """Mix of suppress/downgrade/pass in single batch."""
        config = _make_config()
        service = AsyncMock()
        service.get_sentiment_batch.return_value = {
            "SBIN": _make_sentiment("STRONG_NEGATIVE", -0.72, "SUPPRESSED"),
            "TCS": _make_sentiment("MILD_NEGATIVE", -0.35, "DOWNGRADED"),
            "RELIANCE": _make_sentiment("POSITIVE", 0.5, "PASS"),
        }
        service.is_unsuppressed = MagicMock(return_value=False)
        earnings = AsyncMock()
        earnings.has_earnings_today.return_value = False

        stage = NewsSentimentStage(service, earnings, config)
        ctx = ScanContext(phase=StrategyPhase.OPENING)
        ctx.ranked_signals = [
            _make_ranked_signal("SBIN", 4),
            _make_ranked_signal("TCS", 3),
            _make_ranked_signal("RELIANCE", 5),
        ]

        result = await stage.process(ctx)
        assert len(result.ranked_signals) == 2  # SBIN suppressed
        assert len(result.suppressed_signals) == 1
        symbols = [rs.candidate.symbol for rs in result.ranked_signals]
        assert "SBIN" not in symbols
        assert "TCS" in symbols
        assert "RELIANCE" in symbols
        # TCS should be downgraded
        tcs = [rs for rs in result.ranked_signals if rs.candidate.symbol == "TCS"][0]
        assert tcs.signal_strength == 2  # 3 -> 2

    async def test_sentiment_results_populated(self):
        """sentiment_results populated for every processed symbol."""
        config = _make_config()
        service = AsyncMock()
        service.get_sentiment_batch.return_value = {
            "SBIN": _make_sentiment("NEUTRAL", 0.0, "PASS"),
        }
        service.is_unsuppressed = MagicMock(return_value=False)
        earnings = AsyncMock()
        earnings.has_earnings_today.return_value = False

        stage = NewsSentimentStage(service, earnings, config)
        ctx = ScanContext(phase=StrategyPhase.OPENING)
        ctx.ranked_signals = [_make_ranked_signal()]

        result = await stage.process(ctx)
        assert "SBIN" in result.sentiment_results
        assert result.sentiment_results["SBIN"].label == "NEUTRAL"

    async def test_none_config_skips_processing(self):
        """Stage with None config skips processing."""
        stage = NewsSentimentStage(None, None, None)
        ctx = ScanContext(phase=StrategyPhase.OPENING)
        ctx.ranked_signals = [_make_ranked_signal()]

        result = await stage.process(ctx)
        assert len(result.ranked_signals) == 1

    async def test_stage_name(self):
        """name property returns 'NewsSentiment'."""
        stage = NewsSentimentStage(None, None, None)
        assert stage.name == "NewsSentiment"
