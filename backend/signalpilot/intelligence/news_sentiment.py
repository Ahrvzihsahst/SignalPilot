"""News Sentiment Service -- orchestrator for fetch, analyze, and cache."""
import logging
import math
from datetime import datetime

from signalpilot.db.models import NewsSentimentRecord, SentimentResult
from signalpilot.utils.constants import IST

logger = logging.getLogger(__name__)

# Half-life decay constant: lambda = ln(2) / 6 hours
_DECAY_LAMBDA = math.log(2) / 6.0


class NewsSentimentService:
    """Orchestrates news fetching, sentiment analysis, and caching."""

    def __init__(self, news_fetcher, sentiment_engine, news_sentiment_repo, earnings_repo, config) -> None:
        self._news_fetcher = news_fetcher
        self._sentiment_engine = sentiment_engine
        self._news_sentiment_repo = news_sentiment_repo
        self._earnings_repo = earnings_repo
        self._config = config
        self._unsuppress_overrides: set[str] = set()

    async def fetch_and_analyze_all(self) -> int:
        """Fetch all stocks, analyze, cache. Return headline count."""
        raw_headlines = await self._news_fetcher.fetch_all_stocks()
        total = 0
        for stock_code, headlines in raw_headlines.items():
            records = self._analyze_headlines(stock_code, headlines)
            count = await self._news_sentiment_repo.upsert_headlines(stock_code, records)
            total += count
        logger.info("Pre-market news fetch complete: %d headlines across %d stocks", total, len(raw_headlines))
        return total

    async def fetch_and_analyze_stocks(self, symbols: list[str] | None = None) -> int:
        """Fetch specific stocks, analyze, cache. Return headline count."""
        if symbols:
            raw_headlines = await self._news_fetcher.fetch_stocks(symbols)
        else:
            raw_headlines = await self._news_fetcher.fetch_all_stocks()
        total = 0
        for stock_code, headlines in raw_headlines.items():
            records = self._analyze_headlines(stock_code, headlines)
            count = await self._news_sentiment_repo.upsert_headlines(stock_code, records)
            total += count
        return total

    def _analyze_headlines(self, stock_code, raw_headlines) -> list[NewsSentimentRecord]:
        """Run sentiment engine on raw headlines and convert to records."""
        records = []
        now = datetime.now(IST)
        for rh in raw_headlines:
            scored = self._sentiment_engine.analyze(rh.title)
            label = self._classify_label(scored.compound_score)
            records.append(NewsSentimentRecord(
                stock_code=stock_code,
                headline=rh.title,
                source=rh.source,
                published_at=rh.published_at,
                positive_score=scored.positive_score,
                negative_score=scored.negative_score,
                neutral_score=scored.neutral_score,
                composite_score=scored.compound_score,
                sentiment_label=label,
                fetched_at=now,
                model_used=scored.model_used,
            ))
        return records

    async def get_sentiment_for_stock(self, stock_code: str, lookback_hours: int | None = None) -> SentimentResult:
        """Get composite sentiment for a stock from cached data."""
        lookback = lookback_hours or self._config.news_lookback_hours
        headlines = await self._news_sentiment_repo.get_stock_sentiment(stock_code, lookback)
        if not headlines:
            return SentimentResult(
                score=0.0, label="NO_NEWS", headline=None, action="PASS",
                headline_count=0, top_negative_headline=None,
                model_used=self._sentiment_engine.model_name,
            )

        score, label = self._compute_composite_score(headlines)
        top_neg = await self._news_sentiment_repo.get_top_negative_headline(stock_code, lookback)

        # Determine action
        if label == "STRONG_NEGATIVE":
            action = "SUPPRESSED"
        elif label == "MILD_NEGATIVE":
            action = "DOWNGRADED"
        else:
            action = "PASS"

        return SentimentResult(
            score=score,
            label=label,
            headline=headlines[0].headline if headlines else None,
            action=action,
            headline_count=len(headlines),
            top_negative_headline=top_neg,
            model_used=headlines[0].model_used if headlines else self._sentiment_engine.model_name,
        )

    async def get_sentiment_batch(self, symbols: list[str]) -> dict[str, SentimentResult]:
        """Get sentiment for multiple stocks."""
        results = {}
        for sym in symbols:
            results[sym] = await self.get_sentiment_for_stock(sym)
        return results

    def _compute_composite_score(self, headlines: list[NewsSentimentRecord]) -> tuple[float, str]:
        """Compute recency-weighted composite score and label."""
        now = datetime.now(IST)
        total_weight = 0.0
        weighted_sum = 0.0

        for h in headlines:
            if h.published_at:
                age_hours = (now - h.published_at).total_seconds() / 3600.0
            else:
                age_hours = 12.0  # Default age if unknown
            weight = math.exp(-_DECAY_LAMBDA * age_hours)
            weighted_sum += weight * h.composite_score
            total_weight += weight

        composite = weighted_sum / total_weight if total_weight > 0 else 0.0
        label = self._classify_label(composite)
        return composite, label

    def _classify_label(self, score: float) -> str:
        """Classify a composite score into a sentiment label."""
        if score < self._config.strong_negative_threshold:
            return "STRONG_NEGATIVE"
        elif score < self._config.mild_negative_threshold:
            return "MILD_NEGATIVE"
        elif score <= self._config.positive_threshold:
            return "NEUTRAL"
        else:
            return "POSITIVE"

    def add_unsuppress_override(self, stock_code: str) -> None:
        """Add a stock to the session-scoped unsuppress override list."""
        self._unsuppress_overrides.add(stock_code)

    def is_unsuppressed(self, stock_code: str) -> bool:
        """Check if a stock has an active unsuppress override."""
        return stock_code in self._unsuppress_overrides

    def clear_unsuppress_overrides(self) -> None:
        """Clear all unsuppress overrides (called at end of day)."""
        self._unsuppress_overrides.clear()

    async def purge_old_entries(self, older_than_hours: int = 48) -> int:
        """Purge old entries from the cache."""
        return await self._news_sentiment_repo.purge_old_entries(older_than_hours)
