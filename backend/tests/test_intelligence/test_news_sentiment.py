"""Tests for the NewsSentimentService orchestrator."""
import math
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from signalpilot.db.models import NewsSentimentRecord, SentimentResult
from signalpilot.intelligence.news_sentiment import NewsSentimentService, _DECAY_LAMBDA
from signalpilot.utils.constants import IST


def _make_config(**overrides):
    """Create a minimal config-like object for NewsSentimentService."""
    defaults = {
        "news_lookback_hours": 24,
        "strong_negative_threshold": -0.5,
        "mild_negative_threshold": -0.2,
        "positive_threshold": 0.3,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_scored_headline(compound_score=0.0, model_used="vader"):
    """Create a mock ScoredHeadline-like object."""
    return SimpleNamespace(
        title="Test headline",
        source="TestFeed",
        published_at=None,
        positive_score=max(0, compound_score),
        negative_score=max(0, -compound_score),
        neutral_score=0.5,
        compound_score=compound_score,
        model_used=model_used,
    )


def _make_sentiment_engine(compound_score=0.0, model_name="vader"):
    """Create a mock sentiment engine."""
    engine = MagicMock()
    engine.model_name = model_name
    engine.analyze.return_value = _make_scored_headline(compound_score, model_name)
    return engine


def _make_raw_headline(title="Test headline", published_at=None):
    """Create a mock RawHeadline-like object."""
    return SimpleNamespace(
        title=title,
        source="TestFeed",
        published_at=published_at or datetime.now(IST),
        link="https://example.com",
        stock_codes=[],
    )


def _make_news_sentiment_record(
    stock_code="SBIN",
    headline="Test headline",
    composite_score=0.0,
    published_at=None,
    model_used="vader",
):
    """Create a NewsSentimentRecord for testing."""
    now = datetime.now(IST)
    return NewsSentimentRecord(
        stock_code=stock_code,
        headline=headline,
        source="TestFeed",
        published_at=published_at or now,
        positive_score=max(0, composite_score),
        negative_score=max(0, -composite_score),
        neutral_score=0.5,
        composite_score=composite_score,
        sentiment_label="NEUTRAL",
        fetched_at=now,
        model_used=model_used,
    )


class TestGetSentimentForStock:
    """Tests for get_sentiment_for_stock method."""

    async def test_returns_correct_sentiment_result(self):
        """Should return a SentimentResult with correct fields."""
        config = _make_config()
        engine = _make_sentiment_engine(compound_score=-0.3)
        repo = AsyncMock()
        now = datetime.now(IST)
        headlines = [
            _make_news_sentiment_record("SBIN", "Bad news for SBIN", -0.3, now),
        ]
        repo.get_stock_sentiment.return_value = headlines
        repo.get_top_negative_headline.return_value = "Bad news for SBIN"

        service = NewsSentimentService(
            news_fetcher=MagicMock(),
            sentiment_engine=engine,
            news_sentiment_repo=repo,
            earnings_repo=AsyncMock(),
            config=config,
        )

        result = await service.get_sentiment_for_stock("SBIN")
        assert isinstance(result, SentimentResult)
        assert result.headline_count == 1
        assert result.headline == "Bad news for SBIN"
        assert result.model_used == "vader"

    async def test_no_news_returns_no_news_label(self):
        """Unknown stock with no headlines should return NO_NEWS label."""
        config = _make_config()
        engine = _make_sentiment_engine()
        repo = AsyncMock()
        repo.get_stock_sentiment.return_value = []

        service = NewsSentimentService(
            news_fetcher=MagicMock(),
            sentiment_engine=engine,
            news_sentiment_repo=repo,
            earnings_repo=AsyncMock(),
            config=config,
        )

        result = await service.get_sentiment_for_stock("UNKNOWN")
        assert result.label == "NO_NEWS"
        assert result.score == 0.0
        assert result.action == "PASS"
        assert result.headline is None
        assert result.headline_count == 0

    async def test_strong_negative_suppresses(self):
        """Stock with strong negative sentiment should get SUPPRESSED action."""
        config = _make_config(strong_negative_threshold=-0.5)
        engine = _make_sentiment_engine(compound_score=-0.8)
        repo = AsyncMock()
        now = datetime.now(IST)
        headlines = [
            _make_news_sentiment_record("SBIN", "SEBI probe into SBIN fraud", -0.8, now),
        ]
        repo.get_stock_sentiment.return_value = headlines
        repo.get_top_negative_headline.return_value = "SEBI probe into SBIN fraud"

        service = NewsSentimentService(
            news_fetcher=MagicMock(),
            sentiment_engine=engine,
            news_sentiment_repo=repo,
            earnings_repo=AsyncMock(),
            config=config,
        )

        result = await service.get_sentiment_for_stock("SBIN")
        assert result.label == "STRONG_NEGATIVE"
        assert result.action == "SUPPRESSED"

    async def test_mild_negative_downgrades(self):
        """Stock with mild negative sentiment should get DOWNGRADED action."""
        config = _make_config(
            strong_negative_threshold=-0.5,
            mild_negative_threshold=-0.2,
        )
        engine = _make_sentiment_engine(compound_score=-0.35)
        repo = AsyncMock()
        now = datetime.now(IST)
        headlines = [
            _make_news_sentiment_record("SBIN", "Minor concern at SBIN", -0.35, now),
        ]
        repo.get_stock_sentiment.return_value = headlines
        repo.get_top_negative_headline.return_value = "Minor concern at SBIN"

        service = NewsSentimentService(
            news_fetcher=MagicMock(),
            sentiment_engine=engine,
            news_sentiment_repo=repo,
            earnings_repo=AsyncMock(),
            config=config,
        )

        result = await service.get_sentiment_for_stock("SBIN")
        assert result.label == "MILD_NEGATIVE"
        assert result.action == "DOWNGRADED"

    async def test_neutral_passes(self):
        """Stock with neutral sentiment should get PASS action."""
        config = _make_config()
        engine = _make_sentiment_engine(compound_score=0.0)
        repo = AsyncMock()
        now = datetime.now(IST)
        headlines = [
            _make_news_sentiment_record("SBIN", "SBIN holds AGM", 0.0, now),
        ]
        repo.get_stock_sentiment.return_value = headlines
        repo.get_top_negative_headline.return_value = None

        service = NewsSentimentService(
            news_fetcher=MagicMock(),
            sentiment_engine=engine,
            news_sentiment_repo=repo,
            earnings_repo=AsyncMock(),
            config=config,
        )

        result = await service.get_sentiment_for_stock("SBIN")
        assert result.action == "PASS"

    async def test_positive_passes(self):
        """Stock with positive sentiment should get PASS action."""
        config = _make_config(positive_threshold=0.3)
        engine = _make_sentiment_engine(compound_score=0.6)
        repo = AsyncMock()
        now = datetime.now(IST)
        headlines = [
            _make_news_sentiment_record("SBIN", "SBIN record revenue", 0.6, now),
        ]
        repo.get_stock_sentiment.return_value = headlines
        repo.get_top_negative_headline.return_value = None

        service = NewsSentimentService(
            news_fetcher=MagicMock(),
            sentiment_engine=engine,
            news_sentiment_repo=repo,
            earnings_repo=AsyncMock(),
            config=config,
        )

        result = await service.get_sentiment_for_stock("SBIN")
        assert result.label == "POSITIVE"
        assert result.action == "PASS"


class TestCompositeScoreWithRecencyWeighting:
    """Tests for the recency-weighted composite score computation."""

    async def test_recent_headline_weighted_more(self):
        """More recent headlines should have higher weight in composite score."""
        config = _make_config()
        engine = _make_sentiment_engine()
        repo = AsyncMock()
        now = datetime.now(IST)

        # Two headlines: one recent (negative), one old (positive)
        headlines = [
            _make_news_sentiment_record("SBIN", "Bad news", -0.8, now - timedelta(hours=1)),
            _make_news_sentiment_record("SBIN", "Good news", 0.8, now - timedelta(hours=20)),
        ]
        repo.get_stock_sentiment.return_value = headlines
        repo.get_top_negative_headline.return_value = "Bad news"

        service = NewsSentimentService(
            news_fetcher=MagicMock(),
            sentiment_engine=engine,
            news_sentiment_repo=repo,
            earnings_repo=AsyncMock(),
            config=config,
        )

        result = await service.get_sentiment_for_stock("SBIN")
        # The recent headline (negative) should dominate due to recency weighting
        assert result.score < 0.0

    async def test_unknown_published_at_uses_default_age(self):
        """Headlines with None published_at should use 12h default age."""
        config = _make_config()
        engine = _make_sentiment_engine()
        repo = AsyncMock()

        headlines = [
            _make_news_sentiment_record("SBIN", "News", -0.5, published_at=None),
        ]
        # Override published_at to None after creation
        headlines[0].published_at = None
        repo.get_stock_sentiment.return_value = headlines
        repo.get_top_negative_headline.return_value = "News"

        service = NewsSentimentService(
            news_fetcher=MagicMock(),
            sentiment_engine=engine,
            news_sentiment_repo=repo,
            earnings_repo=AsyncMock(),
            config=config,
        )

        result = await service.get_sentiment_for_stock("SBIN")
        # Should still compute a score (not crash)
        assert isinstance(result.score, float)

    def test_decay_lambda_value(self):
        """Decay constant should be ln(2)/6 for 6-hour half-life."""
        expected = math.log(2) / 6.0
        assert abs(_DECAY_LAMBDA - expected) < 1e-10


class TestLabelClassification:
    """Tests for label classification at threshold boundaries."""

    def _make_service(self, **config_overrides):
        config = _make_config(**config_overrides)
        return NewsSentimentService(
            news_fetcher=MagicMock(),
            sentiment_engine=_make_sentiment_engine(),
            news_sentiment_repo=AsyncMock(),
            earnings_repo=AsyncMock(),
            config=config,
        )

    def test_strong_negative_below_threshold(self):
        """Score below strong_negative_threshold should be STRONG_NEGATIVE."""
        service = self._make_service(strong_negative_threshold=-0.5)
        label = service._classify_label(-0.6)
        assert label == "STRONG_NEGATIVE"

    def test_strong_negative_at_boundary(self):
        """Score exactly at strong_negative_threshold is not STRONG_NEGATIVE (uses <)."""
        service = self._make_service(strong_negative_threshold=-0.5)
        label = service._classify_label(-0.5)
        # -0.5 < -0.5 is False, so it falls through to MILD_NEGATIVE check
        assert label == "MILD_NEGATIVE"

    def test_mild_negative_between_thresholds(self):
        """Score between strong and mild thresholds should be MILD_NEGATIVE."""
        service = self._make_service(
            strong_negative_threshold=-0.5,
            mild_negative_threshold=-0.2,
        )
        label = service._classify_label(-0.3)
        assert label == "MILD_NEGATIVE"

    def test_mild_negative_at_boundary(self):
        """Score exactly at mild_negative_threshold is not MILD_NEGATIVE (uses <)."""
        service = self._make_service(mild_negative_threshold=-0.2)
        label = service._classify_label(-0.2)
        # -0.2 < -0.2 is False, so it falls through to NEUTRAL check
        assert label == "NEUTRAL"

    def test_neutral_in_range(self):
        """Score between mild_negative and positive thresholds should be NEUTRAL."""
        service = self._make_service(
            mild_negative_threshold=-0.2,
            positive_threshold=0.3,
        )
        label = service._classify_label(0.1)
        assert label == "NEUTRAL"

    def test_positive_above_threshold(self):
        """Score above positive_threshold should be POSITIVE."""
        service = self._make_service(positive_threshold=0.3)
        label = service._classify_label(0.5)
        assert label == "POSITIVE"

    def test_positive_at_boundary(self):
        """Score exactly at positive_threshold is NEUTRAL (uses <=)."""
        service = self._make_service(positive_threshold=0.3)
        label = service._classify_label(0.3)
        assert label == "NEUTRAL"

    def test_zero_score_is_neutral(self):
        """Zero score should be NEUTRAL."""
        service = self._make_service()
        label = service._classify_label(0.0)
        assert label == "NEUTRAL"


class TestUnsuppressOverride:
    """Tests for unsuppress override management."""

    def test_add_and_check_override(self):
        """Adding an override should make is_unsuppressed return True."""
        service = NewsSentimentService(
            news_fetcher=MagicMock(),
            sentiment_engine=_make_sentiment_engine(),
            news_sentiment_repo=AsyncMock(),
            earnings_repo=AsyncMock(),
            config=_make_config(),
        )
        assert service.is_unsuppressed("SBIN") is False
        service.add_unsuppress_override("SBIN")
        assert service.is_unsuppressed("SBIN") is True

    def test_clear_overrides(self):
        """clear_unsuppress_overrides should remove all overrides."""
        service = NewsSentimentService(
            news_fetcher=MagicMock(),
            sentiment_engine=_make_sentiment_engine(),
            news_sentiment_repo=AsyncMock(),
            earnings_repo=AsyncMock(),
            config=_make_config(),
        )
        service.add_unsuppress_override("SBIN")
        service.add_unsuppress_override("TCS")
        service.clear_unsuppress_overrides()
        assert service.is_unsuppressed("SBIN") is False
        assert service.is_unsuppressed("TCS") is False

    def test_multiple_overrides(self):
        """Multiple stocks can be unsuppressed independently."""
        service = NewsSentimentService(
            news_fetcher=MagicMock(),
            sentiment_engine=_make_sentiment_engine(),
            news_sentiment_repo=AsyncMock(),
            earnings_repo=AsyncMock(),
            config=_make_config(),
        )
        service.add_unsuppress_override("SBIN")
        service.add_unsuppress_override("TCS")
        assert service.is_unsuppressed("SBIN") is True
        assert service.is_unsuppressed("TCS") is True
        assert service.is_unsuppressed("RELIANCE") is False


class TestPurge:
    """Tests for purge delegation."""

    async def test_purge_delegates_to_repo(self):
        """purge_old_entries should delegate to the repository."""
        repo = AsyncMock()
        repo.purge_old_entries.return_value = 5

        service = NewsSentimentService(
            news_fetcher=MagicMock(),
            sentiment_engine=_make_sentiment_engine(),
            news_sentiment_repo=repo,
            earnings_repo=AsyncMock(),
            config=_make_config(),
        )

        result = await service.purge_old_entries(older_than_hours=48)
        assert result == 5
        repo.purge_old_entries.assert_awaited_once_with(48)

    async def test_purge_default_hours(self):
        """purge_old_entries without argument should use default 48 hours."""
        repo = AsyncMock()
        repo.purge_old_entries.return_value = 0

        service = NewsSentimentService(
            news_fetcher=MagicMock(),
            sentiment_engine=_make_sentiment_engine(),
            news_sentiment_repo=repo,
            earnings_repo=AsyncMock(),
            config=_make_config(),
        )

        await service.purge_old_entries()
        repo.purge_old_entries.assert_awaited_once_with(48)


class TestBatchQuery:
    """Tests for batch sentiment query."""

    async def test_batch_query_returns_dict(self):
        """get_sentiment_batch should return a dict keyed by symbol."""
        config = _make_config()
        engine = _make_sentiment_engine()
        repo = AsyncMock()
        repo.get_stock_sentiment.return_value = []

        service = NewsSentimentService(
            news_fetcher=MagicMock(),
            sentiment_engine=engine,
            news_sentiment_repo=repo,
            earnings_repo=AsyncMock(),
            config=config,
        )

        result = await service.get_sentiment_batch(["SBIN", "TCS"])
        assert isinstance(result, dict)
        assert "SBIN" in result
        assert "TCS" in result
        assert all(isinstance(v, SentimentResult) for v in result.values())

    async def test_batch_query_empty_list(self):
        """get_sentiment_batch with empty list should return empty dict."""
        service = NewsSentimentService(
            news_fetcher=MagicMock(),
            sentiment_engine=_make_sentiment_engine(),
            news_sentiment_repo=AsyncMock(),
            earnings_repo=AsyncMock(),
            config=_make_config(),
        )

        result = await service.get_sentiment_batch([])
        assert result == {}


class TestFetchAndAnalyze:
    """Tests for the fetch_and_analyze methods."""

    async def test_fetch_and_analyze_all(self):
        """fetch_and_analyze_all should fetch, analyze, and upsert all headlines."""
        config = _make_config()
        engine = _make_sentiment_engine(compound_score=0.5)

        fetcher = AsyncMock()
        fetcher.fetch_all_stocks.return_value = {
            "SBIN": [_make_raw_headline("SBIN good news")],
            "TCS": [_make_raw_headline("TCS contract win")],
        }

        repo = AsyncMock()
        repo.upsert_headlines.return_value = 1

        service = NewsSentimentService(
            news_fetcher=fetcher,
            sentiment_engine=engine,
            news_sentiment_repo=repo,
            earnings_repo=AsyncMock(),
            config=config,
        )

        total = await service.fetch_and_analyze_all()
        assert total == 2
        assert repo.upsert_headlines.await_count == 2

    async def test_fetch_and_analyze_stocks(self):
        """fetch_and_analyze_stocks with specific symbols should use fetch_stocks."""
        config = _make_config()
        engine = _make_sentiment_engine()

        fetcher = AsyncMock()
        fetcher.fetch_stocks.return_value = {
            "SBIN": [_make_raw_headline("SBIN news")],
        }

        repo = AsyncMock()
        repo.upsert_headlines.return_value = 1

        service = NewsSentimentService(
            news_fetcher=fetcher,
            sentiment_engine=engine,
            news_sentiment_repo=repo,
            earnings_repo=AsyncMock(),
            config=config,
        )

        total = await service.fetch_and_analyze_stocks(symbols=["SBIN"])
        assert total == 1
        fetcher.fetch_stocks.assert_awaited_once_with(["SBIN"])

    async def test_fetch_and_analyze_stocks_no_symbols(self):
        """fetch_and_analyze_stocks with no symbols should use fetch_all_stocks."""
        config = _make_config()
        engine = _make_sentiment_engine()

        fetcher = AsyncMock()
        fetcher.fetch_all_stocks.return_value = {}

        repo = AsyncMock()

        service = NewsSentimentService(
            news_fetcher=fetcher,
            sentiment_engine=engine,
            news_sentiment_repo=repo,
            earnings_repo=AsyncMock(),
            config=config,
        )

        total = await service.fetch_and_analyze_stocks(symbols=None)
        assert total == 0
        fetcher.fetch_all_stocks.assert_awaited_once()
