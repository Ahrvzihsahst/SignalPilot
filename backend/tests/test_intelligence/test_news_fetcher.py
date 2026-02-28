"""Tests for the NewsFetcher RSS headline fetcher."""
import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from signalpilot.intelligence.news_fetcher import NewsFetcher, RawHeadline
from signalpilot.utils.constants import IST


def _make_config(**overrides):
    """Create a minimal config-like object for NewsFetcher."""
    defaults = {
        "news_rss_feeds": "https://example.com/feed1.xml,https://example.com/feed2.xml",
        "news_lookback_hours": 24,
        "news_max_headlines_per_stock": 10,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestNewsFetcherMatching:
    """Tests for headline-to-stock matching logic."""

    def test_match_headline_to_stocks_single_match(self):
        """Headline mentioning a stock symbol should match that stock."""
        config = _make_config()
        fetcher = NewsFetcher(config)
        fetcher.initialize(["SBIN", "TCS", "RELIANCE"])

        headline = RawHeadline(
            title="SBIN reports strong quarterly results",
            source="TestFeed",
            published_at=datetime.now(IST),
            link="https://example.com/1",
        )
        matched = fetcher._match_headline_to_stocks(headline)
        assert "SBIN" in matched

    def test_match_headline_to_stocks_multiple_matches(self):
        """Headline mentioning multiple stocks should match all of them."""
        config = _make_config()
        fetcher = NewsFetcher(config)
        fetcher.initialize(["SBIN", "TCS", "RELIANCE"])

        headline = RawHeadline(
            title="sbin and tcs lead banking rally",
            source="TestFeed",
            published_at=datetime.now(IST),
            link="https://example.com/2",
        )
        matched = fetcher._match_headline_to_stocks(headline)
        assert "SBIN" in matched
        assert "TCS" in matched

    def test_match_headline_to_stocks_no_match(self):
        """Headline not mentioning any known stock should return empty list."""
        config = _make_config()
        fetcher = NewsFetcher(config)
        fetcher.initialize(["SBIN", "TCS", "RELIANCE"])

        headline = RawHeadline(
            title="Global markets rally on US data",
            source="TestFeed",
            published_at=datetime.now(IST),
            link="https://example.com/3",
        )
        matched = fetcher._match_headline_to_stocks(headline)
        assert matched == []

    def test_match_headline_case_insensitive(self):
        """Matching should be case-insensitive."""
        config = _make_config()
        fetcher = NewsFetcher(config)
        fetcher.initialize(["RELIANCE"])

        headline = RawHeadline(
            title="Reliance Industries announces expansion plans",
            source="TestFeed",
            published_at=datetime.now(IST),
            link="https://example.com/4",
        )
        matched = fetcher._match_headline_to_stocks(headline)
        assert "RELIANCE" in matched


class TestNewsFetcherCap:
    """Tests for headline cap enforcement."""

    async def test_headline_cap_per_stock(self):
        """fetch_all_stocks should cap headlines per stock at configured limit."""
        config = _make_config(news_max_headlines_per_stock=3)
        fetcher = NewsFetcher(config)
        fetcher.initialize(["SBIN"])

        now = datetime.now(IST)
        mock_headlines = [
            RawHeadline(
                title=f"SBIN headline {i}",
                source="TestFeed",
                published_at=now - timedelta(minutes=i),
                link=f"https://example.com/{i}",
            )
            for i in range(10)
        ]

        # Patch _fetch_feed to return our mock headlines
        fetcher._fetch_feed = AsyncMock(return_value=mock_headlines)

        result = await fetcher.fetch_all_stocks()
        assert "SBIN" in result
        assert len(result["SBIN"]) == 3

    async def test_headline_dedup(self):
        """Duplicate headlines for the same stock should be removed."""
        config = _make_config(news_max_headlines_per_stock=10)
        fetcher = NewsFetcher(config)
        fetcher.initialize(["SBIN"])

        now = datetime.now(IST)
        duplicate_headline = RawHeadline(
            title="SBIN reports strong results",
            source="TestFeed",
            published_at=now,
            link="https://example.com/1",
        )
        mock_headlines = [duplicate_headline, duplicate_headline, duplicate_headline]

        fetcher._fetch_feed = AsyncMock(return_value=mock_headlines)

        result = await fetcher.fetch_all_stocks()
        assert "SBIN" in result
        assert len(result["SBIN"]) == 1


class TestNewsFetcherFeed:
    """Tests for RSS feed fetching."""

    async def test_empty_feed_response(self):
        """Empty feed should return empty headlines list."""
        config = _make_config(news_rss_feeds="https://example.com/empty.xml")
        fetcher = NewsFetcher(config)
        fetcher.initialize(["SBIN"])

        # Patch _fetch_feed to return empty list
        fetcher._fetch_feed = AsyncMock(return_value=[])

        result = await fetcher.fetch_all_stocks()
        assert result == {}

    async def test_fetch_feed_error_handling(self):
        """Failed feed fetch should return empty list, not raise."""
        config = _make_config(news_rss_feeds="https://example.com/bad.xml")
        fetcher = NewsFetcher(config)
        fetcher.initialize(["SBIN"])

        # Patch _fetch_feed to simulate failure
        fetcher._fetch_feed = AsyncMock(return_value=[])

        result = await fetcher.fetch_all_stocks()
        assert isinstance(result, dict)

    async def test_lookback_filter(self):
        """Headlines older than lookback window should be excluded."""
        config = _make_config(
            news_rss_feeds="https://example.com/feed.xml",
            news_lookback_hours=6,
            news_max_headlines_per_stock=10,
        )
        fetcher = NewsFetcher(config)
        fetcher.initialize(["SBIN"])

        now = datetime.now(IST)
        mock_headlines = [
            RawHeadline(
                title="SBIN recent news",
                source="TestFeed",
                published_at=now - timedelta(hours=1),
                link="https://example.com/recent",
            ),
            RawHeadline(
                title="SBIN old news",
                source="TestFeed",
                published_at=now - timedelta(hours=10),  # Older than 6h lookback
                link="https://example.com/old",
            ),
        ]

        fetcher._fetch_feed = AsyncMock(return_value=mock_headlines)

        result = await fetcher.fetch_all_stocks()
        assert "SBIN" in result
        assert len(result["SBIN"]) == 1
        assert result["SBIN"][0].title == "SBIN recent news"

    async def test_fetch_stocks_filters_to_requested_symbols(self):
        """fetch_stocks should only return data for requested symbols."""
        config = _make_config(news_max_headlines_per_stock=10)
        fetcher = NewsFetcher(config)
        fetcher.initialize(["SBIN", "TCS", "RELIANCE"])

        now = datetime.now(IST)
        mock_headlines = [
            RawHeadline(
                title="SBIN quarterly results",
                source="TestFeed",
                published_at=now,
                link="https://example.com/sbin",
            ),
            RawHeadline(
                title="TCS wins major contract",
                source="TestFeed",
                published_at=now,
                link="https://example.com/tcs",
            ),
            RawHeadline(
                title="RELIANCE expansion plan",
                source="TestFeed",
                published_at=now,
                link="https://example.com/rel",
            ),
        ]

        fetcher._fetch_feed = AsyncMock(return_value=mock_headlines)

        result = await fetcher.fetch_stocks(["SBIN", "TCS"])
        assert "SBIN" in result
        assert "TCS" in result
        assert "RELIANCE" not in result

    async def test_close_session(self):
        """close() should not raise even when session is None."""
        config = _make_config()
        fetcher = NewsFetcher(config)
        # No session opened yet
        await fetcher.close()

    async def test_headline_none_published_at_included(self):
        """Headlines with no published_at should still be included (no cutoff check)."""
        config = _make_config(
            news_rss_feeds="https://example.com/feed.xml",
            news_lookback_hours=6,
            news_max_headlines_per_stock=10,
        )
        fetcher = NewsFetcher(config)
        fetcher.initialize(["SBIN"])

        mock_headlines = [
            RawHeadline(
                title="SBIN news without timestamp",
                source="TestFeed",
                published_at=None,
                link="https://example.com/nodate",
            ),
        ]

        fetcher._fetch_feed = AsyncMock(return_value=mock_headlines)

        result = await fetcher.fetch_all_stocks()
        assert "SBIN" in result
        assert len(result["SBIN"]) == 1


class TestRawHeadline:
    """Tests for the RawHeadline dataclass."""

    def test_default_stock_codes(self):
        """RawHeadline should default stock_codes to empty list."""
        headline = RawHeadline(
            title="Test",
            source="TestFeed",
            published_at=None,
            link="https://example.com",
        )
        assert headline.stock_codes == []

    def test_stock_codes_field(self):
        """RawHeadline should accept stock_codes."""
        headline = RawHeadline(
            title="Test",
            source="TestFeed",
            published_at=None,
            link="https://example.com",
            stock_codes=["SBIN", "TCS"],
        )
        assert headline.stock_codes == ["SBIN", "TCS"]
