"""Tests for NEWS, EARNINGS, and UNSUPPRESS command handlers."""

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from signalpilot.db.models import SentimentResult
from signalpilot.telegram.handlers import (
    handle_earnings_command,
    handle_news_command,
    handle_unsuppress_command,
)


def _make_sentiment(
    score=0.0, label="NEUTRAL", action="PASS", headline_count=3,
    headline="Test headline", top_negative_headline=None, model_used="vader",
):
    return SentimentResult(
        score=score,
        label=label,
        headline=headline,
        action=action,
        headline_count=headline_count,
        top_negative_headline=top_negative_headline,
        model_used=model_used,
    )


class TestHandleNewsCommand:
    """Tests for handle_news_command."""

    async def test_invalid_input_returns_usage(self):
        service = AsyncMock()
        result = await handle_news_command(service, "NEWSX")
        assert "Usage:" in result

    async def test_single_stock(self):
        service = AsyncMock()
        service.get_sentiment_for_stock.return_value = _make_sentiment(
            score=-0.35, label="MILD_NEGATIVE", action="DOWNGRADED",
            headline_count=5, headline="SBIN faces scrutiny",
            top_negative_headline="SBIN fraud allegation",
            model_used="vader",
        )
        result = await handle_news_command(service, "NEWS SBIN")
        assert "SBIN" in result
        assert "-0.35" in result
        assert "MILD_NEGATIVE" in result
        assert "DOWNGRADED" in result
        assert "5" in result
        assert "vader" in result
        assert "SBIN fraud allegation" in result

    async def test_single_stock_lowercase(self):
        service = AsyncMock()
        service.get_sentiment_for_stock.return_value = _make_sentiment()
        result = await handle_news_command(service, "news sbin")
        service.get_sentiment_for_stock.assert_awaited_once_with("SBIN")

    async def test_news_all_summary(self):
        service = AsyncMock()
        service._news_sentiment_repo = AsyncMock()
        service._news_sentiment_repo.get_all_stock_sentiments.return_value = {
            "SBIN": (-0.72, "STRONG_NEGATIVE", 5),
            "TCS": (0.4, "POSITIVE", 3),
        }
        result = await handle_news_command(service, "NEWS ALL")
        assert "Summary" in result
        assert "SBIN" in result
        assert "TCS" in result
        assert "STRONG_NEGATIVE" in result
        assert "POSITIVE" in result

    async def test_news_no_args_shows_summary(self):
        service = AsyncMock()
        service._news_sentiment_repo = AsyncMock()
        service._news_sentiment_repo.get_all_stock_sentiments.return_value = {}
        result = await handle_news_command(service, "NEWS")
        assert "No news sentiment data" in result

    async def test_no_top_negative_headline(self):
        service = AsyncMock()
        service.get_sentiment_for_stock.return_value = _make_sentiment(
            headline="Good news", top_negative_headline=None,
        )
        result = await handle_news_command(service, "NEWS SBIN")
        assert "Good news" in result
        assert "Most Negative" not in result

    async def test_same_headline_and_negative_no_duplicate(self):
        service = AsyncMock()
        service.get_sentiment_for_stock.return_value = _make_sentiment(
            headline="Bad headline", top_negative_headline="Bad headline",
        )
        result = await handle_news_command(service, "NEWS TCS")
        # Should show "Top:" but not "Most Negative:" since they are the same
        assert "Bad headline" in result
        assert "Most Negative" not in result


class TestHandleEarningsCommand:
    """Tests for handle_earnings_command."""

    async def test_no_upcoming_earnings(self):
        repo = AsyncMock()
        repo.get_upcoming_earnings.return_value = []
        result = await handle_earnings_command(repo)
        assert "No upcoming earnings" in result

    async def test_upcoming_earnings_grouped_by_date(self):
        e1 = SimpleNamespace(
            stock_code="SBIN", earnings_date=date(2025, 1, 20),
            quarter="Q3 FY25", is_confirmed=True,
        )
        e2 = SimpleNamespace(
            stock_code="TCS", earnings_date=date(2025, 1, 20),
            quarter="Q3 FY25", is_confirmed=False,
        )
        e3 = SimpleNamespace(
            stock_code="RELIANCE", earnings_date=date(2025, 1, 22),
            quarter="Q3 FY25", is_confirmed=True,
        )
        repo = AsyncMock()
        repo.get_upcoming_earnings.return_value = [e1, e2, e3]

        result = await handle_earnings_command(repo)
        assert "Upcoming Earnings" in result
        assert "SBIN" in result
        assert "TCS" in result
        assert "RELIANCE" in result
        assert "Confirmed" in result
        assert "Tentative" in result
        assert "2025-01-20" in result
        assert "2025-01-22" in result

    async def test_custom_days_parameter(self):
        repo = AsyncMock()
        repo.get_upcoming_earnings.return_value = []
        await handle_earnings_command(repo, days=14)
        repo.get_upcoming_earnings.assert_awaited_once_with(14)


class TestHandleUnsuppressCommand:
    """Tests for handle_unsuppress_command."""

    async def test_invalid_input_returns_usage(self):
        service = AsyncMock()
        result = await handle_unsuppress_command(service, "UNSUPPRESS")
        assert "Usage:" in result

    async def test_valid_unsuppress(self):
        service = AsyncMock()
        service.get_sentiment_for_stock.return_value = _make_sentiment(
            score=-0.72, label="STRONG_NEGATIVE",
        )
        service.add_unsuppress_override = lambda sym: None

        result = await handle_unsuppress_command(service, "UNSUPPRESS SBIN")
        assert "Override added" in result
        assert "SBIN" in result
        assert "STRONG_NEGATIVE" in result
        assert "-0.72" in result
        assert "pass through" in result

    async def test_unsuppress_lowercase(self):
        service = AsyncMock()
        service.get_sentiment_for_stock.return_value = _make_sentiment()
        service.add_unsuppress_override = lambda sym: None

        result = await handle_unsuppress_command(service, "unsuppress sbin")
        service.get_sentiment_for_stock.assert_awaited_once_with("SBIN")
        assert "SBIN" in result
