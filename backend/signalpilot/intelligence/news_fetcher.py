"""Async RSS news fetcher for financial headlines."""
import logging
import time as time_mod
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import aiohttp
import feedparser

from signalpilot.utils.constants import IST

logger = logging.getLogger(__name__)


@dataclass
class RawHeadline:
    """A raw headline from an RSS feed before sentiment analysis."""
    title: str
    source: str
    published_at: datetime | None
    link: str
    stock_codes: list[str] = field(default_factory=list)


class NewsFetcher:
    """Fetches and matches financial news headlines from RSS feeds."""

    def __init__(self, config) -> None:
        self._config = config
        self._feed_urls: list[str] = [
            url.strip() for url in config.news_rss_feeds.split(",") if url.strip()
        ]
        self._symbol_index: dict[str, str] = {}  # lowercase name/code -> symbol
        self._session: aiohttp.ClientSession | None = None

    def initialize(self, symbols: list[str]) -> None:
        """Build symbol matching index from instrument list."""
        # Map both stock codes and common names
        for sym in symbols:
            self._symbol_index[sym.lower()] = sym

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )
        return self._session

    async def _fetch_feed(self, url: str) -> list[RawHeadline]:
        """Fetch and parse a single RSS feed."""
        try:
            session = await self._get_session()
            async with session.get(url) as response:
                content = await response.text()
            feed = feedparser.parse(content)
            headlines = []
            source = feed.feed.get("title", url)
            for entry in feed.entries:
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime.fromtimestamp(
                        time_mod.mktime(entry.published_parsed), tz=IST
                    )
                headlines.append(RawHeadline(
                    title=entry.get("title", ""),
                    source=source,
                    published_at=published,
                    link=entry.get("link", ""),
                ))
            return headlines
        except Exception:
            logger.warning("Failed to fetch feed %s", url, exc_info=True)
            return []

    def _match_headline_to_stocks(self, headline: RawHeadline) -> list[str]:
        """Match headline text to stock codes using case-insensitive substring matching."""
        title_lower = headline.title.lower()
        matched = []
        for key, symbol in self._symbol_index.items():
            if key in title_lower:
                matched.append(symbol)
        return matched

    async def fetch_all_stocks(self) -> dict[str, list[RawHeadline]]:
        """Fetch all feeds, match to stocks, filter by lookback, cap per stock."""
        all_headlines: list[RawHeadline] = []
        for url in self._feed_urls:
            feed_headlines = await self._fetch_feed(url)
            all_headlines.extend(feed_headlines)

        # Filter by lookback window
        cutoff = datetime.now(IST) - timedelta(hours=self._config.news_lookback_hours)
        result: dict[str, list[RawHeadline]] = {}

        for headline in all_headlines:
            if headline.published_at and headline.published_at < cutoff:
                continue
            matched_stocks = self._match_headline_to_stocks(headline)
            for stock in matched_stocks:
                headline_copy = RawHeadline(
                    title=headline.title,
                    source=headline.source,
                    published_at=headline.published_at,
                    link=headline.link,
                    stock_codes=[stock],
                )
                if stock not in result:
                    result[stock] = []
                # Dedup near-identical headlines
                if not any(h.title == headline_copy.title for h in result[stock]):
                    result[stock].append(headline_copy)

        # Cap per stock
        max_per_stock = self._config.news_max_headlines_per_stock
        for stock in result:
            result[stock] = result[stock][:max_per_stock]

        return result

    async def fetch_stocks(self, symbols: list[str]) -> dict[str, list[RawHeadline]]:
        """Fetch all feeds but only return results for specified symbols."""
        all_results = await self.fetch_all_stocks()
        return {sym: all_results.get(sym, []) for sym in symbols if sym in all_results}

    async def close(self) -> None:
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
