"""Repository for news sentiment records."""

import math
from datetime import datetime, timedelta

import aiosqlite

from signalpilot.db.models import NewsSentimentRecord
from signalpilot.utils.constants import IST

# Half-life decay constant: lambda = ln(2) / 6 hours
_DECAY_LAMBDA = math.log(2) / 6.0


class NewsSentimentRepository:
    """CRUD operations for the news_sentiment table."""

    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._conn = connection

    async def upsert_headlines(
        self, stock_code: str, headlines: list[NewsSentimentRecord],
    ) -> int:
        """Insert or replace headlines. Return count of rows upserted."""
        count = 0
        for h in headlines:
            await self._conn.execute(
                """
                INSERT OR REPLACE INTO news_sentiment
                    (stock_code, headline, source, published_at,
                     positive_score, negative_score, neutral_score,
                     composite_score, sentiment_label, fetched_at, model_used)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stock_code,
                    h.headline,
                    h.source,
                    h.published_at.isoformat() if h.published_at else None,
                    h.positive_score,
                    h.negative_score,
                    h.neutral_score,
                    h.composite_score,
                    h.sentiment_label,
                    h.fetched_at.isoformat() if h.fetched_at else datetime.now(IST).isoformat(),
                    h.model_used,
                ),
            )
            count += 1
        await self._conn.commit()
        return count

    async def get_stock_sentiment(
        self, stock_code: str, lookback_hours: int = 24,
    ) -> list[NewsSentimentRecord]:
        """Get headlines within lookback window, ordered by published_at DESC."""
        cutoff = datetime.now(IST) - timedelta(hours=lookback_hours)
        cursor = await self._conn.execute(
            """
            SELECT * FROM news_sentiment
            WHERE stock_code = ? AND fetched_at >= ?
            ORDER BY published_at DESC
            """,
            (stock_code, cutoff.isoformat()),
        )
        rows = await cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    async def get_composite_score(
        self, stock_code: str, lookback_hours: int = 24,
    ) -> tuple[float, str, int] | None:
        """Return (recency-weighted composite score, label, headline count).

        Uses exponential decay weighting: weight = exp(-lambda * age_hours)
        where lambda = ln(2) / 6 (half-life of 6 hours).
        """
        headlines = await self.get_stock_sentiment(stock_code, lookback_hours)
        if not headlines:
            return None

        now = datetime.now(IST)
        total_weight = 0.0
        weighted_sum = 0.0

        for h in headlines:
            if h.published_at:
                age_hours = (now - h.published_at).total_seconds() / 3600.0
            else:
                age_hours = 12.0  # Default age if unknown
            weight = math.exp(-_DECAY_LAMBDA * max(age_hours, 0.0))
            weighted_sum += weight * h.composite_score
            total_weight += weight

        composite = weighted_sum / total_weight if total_weight > 0 else 0.0

        # Determine dominant label from composite score
        if composite < -0.5:
            label = "STRONG_NEGATIVE"
        elif composite < -0.2:
            label = "MILD_NEGATIVE"
        elif composite <= 0.3:
            label = "NEUTRAL"
        else:
            label = "POSITIVE"

        return (composite, label, len(headlines))

    async def get_top_negative_headline(
        self, stock_code: str, lookback_hours: int = 24,
    ) -> str | None:
        """Return headline with lowest composite_score in lookback window."""
        cutoff = datetime.now(IST) - timedelta(hours=lookback_hours)
        cursor = await self._conn.execute(
            """
            SELECT headline FROM news_sentiment
            WHERE stock_code = ? AND fetched_at >= ?
            ORDER BY composite_score ASC
            LIMIT 1
            """,
            (stock_code, cutoff.isoformat()),
        )
        row = await cursor.fetchone()
        return row["headline"] if row else None

    async def purge_old_entries(self, older_than_hours: int = 48) -> int:
        """Delete entries where fetched_at exceeds threshold. Return count."""
        cutoff = datetime.now(IST) - timedelta(hours=older_than_hours)
        cursor = await self._conn.execute(
            "DELETE FROM news_sentiment WHERE fetched_at < ?",
            (cutoff.isoformat(),),
        )
        await self._conn.commit()
        return cursor.rowcount

    async def get_all_stock_sentiments(
        self, lookback_hours: int = 24,
    ) -> dict[str, tuple[float, str, int]]:
        """Return dict of stock_code -> (composite_score, label, count)."""
        cutoff = datetime.now(IST) - timedelta(hours=lookback_hours)
        cursor = await self._conn.execute(
            """
            SELECT stock_code, AVG(composite_score) as avg_score,
                   COUNT(*) as cnt
            FROM news_sentiment
            WHERE fetched_at >= ?
            GROUP BY stock_code
            """,
            (cutoff.isoformat(),),
        )
        rows = await cursor.fetchall()
        result: dict[str, tuple[float, str, int]] = {}
        for row in rows:
            score = row["avg_score"]
            count = row["cnt"]
            if score < -0.5:
                label = "STRONG_NEGATIVE"
            elif score < -0.2:
                label = "MILD_NEGATIVE"
            elif score <= 0.3:
                label = "NEUTRAL"
            else:
                label = "POSITIVE"
            result[row["stock_code"]] = (score, label, count)
        return result

    @staticmethod
    def _row_to_record(row: aiosqlite.Row) -> NewsSentimentRecord:
        """Convert a database row to a NewsSentimentRecord."""
        return NewsSentimentRecord(
            id=row["id"],
            stock_code=row["stock_code"],
            headline=row["headline"],
            source=row["source"],
            published_at=(
                datetime.fromisoformat(row["published_at"])
                if row["published_at"]
                else None
            ),
            positive_score=row["positive_score"],
            negative_score=row["negative_score"],
            neutral_score=row["neutral_score"],
            composite_score=row["composite_score"],
            sentiment_label=row["sentiment_label"],
            fetched_at=(
                datetime.fromisoformat(row["fetched_at"])
                if row["fetched_at"]
                else None
            ),
            model_used=row["model_used"],
        )
