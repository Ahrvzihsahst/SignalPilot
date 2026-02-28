"""Tests for News Sentiment Filter database migration."""

import pytest

from signalpilot.db.database import DatabaseManager


class TestNewsSentimentMigration:
    """Tests for the news_sentiment and earnings_calendar tables and signal columns."""

    async def test_news_sentiment_table_created(self, db):
        cursor = await db.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='news_sentiment'"
        )
        row = await cursor.fetchone()
        assert row is not None

    async def test_earnings_calendar_table_created(self, db):
        cursor = await db.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='earnings_calendar'"
        )
        row = await cursor.fetchone()
        assert row is not None

    async def test_news_sentiment_table_columns(self, db):
        cursor = await db.connection.execute("PRAGMA table_info(news_sentiment)")
        columns = {row["name"] for row in await cursor.fetchall()}
        expected = {
            "id", "stock_code", "headline", "source", "published_at",
            "positive_score", "negative_score", "neutral_score",
            "composite_score", "sentiment_label", "fetched_at", "model_used",
        }
        assert columns == expected

    async def test_earnings_calendar_table_columns(self, db):
        cursor = await db.connection.execute("PRAGMA table_info(earnings_calendar)")
        columns = {row["name"] for row in await cursor.fetchall()}
        expected = {
            "id", "stock_code", "earnings_date", "quarter",
            "source", "is_confirmed", "updated_at",
        }
        assert columns == expected

    async def test_news_sentiment_indexes_created(self, db):
        cursor = await db.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name"
        )
        indexes = {row["name"] for row in await cursor.fetchall()}
        expected = {"idx_news_stock_date", "idx_news_fetched_at"}
        assert expected.issubset(indexes)

    async def test_earnings_calendar_indexes_created(self, db):
        cursor = await db.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name"
        )
        indexes = {row["name"] for row in await cursor.fetchall()}
        expected = {"idx_earnings_date", "idx_earnings_stock_date"}
        assert expected.issubset(indexes)

    async def test_signals_news_columns_added(self, db):
        cursor = await db.connection.execute("PRAGMA table_info(signals)")
        columns = {row["name"] for row in await cursor.fetchall()}
        news_columns = {
            "news_sentiment_score", "news_sentiment_label",
            "news_top_headline", "news_action", "original_star_rating",
        }
        assert news_columns.issubset(columns)

    async def test_signals_news_columns_default_null(self, db):
        """New news columns default to NULL for existing rows."""
        conn = db.connection
        await conn.execute(
            "INSERT INTO signals "
            "(date, symbol, strategy, entry_price, stop_loss, target_1, target_2, "
            "quantity, capital_required, signal_strength, gap_pct, volume_ratio, "
            "reason, created_at, expires_at, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "2026-02-28", "SBIN", "Gap & Go", 500.0, 485.0,
                525.0, 535.0, 30, 15000.0, 4, 4.0, 1.2,
                "Gap up", "2026-02-28T09:35:00", "2026-02-28T10:05:00", "sent",
            ),
        )
        await conn.commit()

        cursor = await conn.execute(
            "SELECT news_sentiment_score, news_sentiment_label, news_top_headline, "
            "news_action, original_star_rating FROM signals WHERE id = 1"
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] is None  # news_sentiment_score
        assert row[1] is None  # news_sentiment_label
        assert row[2] is None  # news_top_headline
        assert row[3] is None  # news_action
        assert row[4] is None  # original_star_rating

    async def test_migration_is_idempotent(self, db):
        """Running migration twice does not error."""
        await db._run_news_sentiment_migration()
        # Verify tables still exist
        cursor = await db.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN ('news_sentiment', 'earnings_calendar')"
        )
        rows = await cursor.fetchall()
        assert len(rows) == 2

    async def test_news_sentiment_unique_constraint(self, db):
        """news_sentiment table enforces UNIQUE(stock_code, headline, source)."""
        conn = db.connection

        await conn.execute(
            "INSERT INTO news_sentiment "
            "(stock_code, headline, source, fetched_at) "
            "VALUES (?, ?, ?, ?)",
            ("SBIN", "SBI profit rises", "MoneyControl", "2026-02-28T08:30:00"),
        )
        await conn.commit()

        # Duplicate should trigger UNIQUE constraint
        with pytest.raises(Exception):
            await conn.execute(
                "INSERT INTO news_sentiment "
                "(stock_code, headline, source, fetched_at) "
                "VALUES (?, ?, ?, ?)",
                ("SBIN", "SBI profit rises", "MoneyControl", "2026-02-28T09:00:00"),
            )
        await conn.rollback()

    async def test_earnings_calendar_unique_constraint(self, db):
        """earnings_calendar table enforces UNIQUE(stock_code, earnings_date)."""
        conn = db.connection

        await conn.execute(
            "INSERT INTO earnings_calendar "
            "(stock_code, earnings_date, updated_at) "
            "VALUES (?, ?, ?)",
            ("INFY", "2026-04-15", "2026-02-28T08:00:00"),
        )
        await conn.commit()

        # Duplicate should trigger UNIQUE constraint
        with pytest.raises(Exception):
            await conn.execute(
                "INSERT INTO earnings_calendar "
                "(stock_code, earnings_date, updated_at) "
                "VALUES (?, ?, ?)",
                ("INFY", "2026-04-15", "2026-02-28T09:00:00"),
            )
        await conn.rollback()

    async def test_existing_data_intact_after_migration(self, db):
        """Pre-existing signal data survives news sentiment migration."""
        conn = db.connection

        await conn.execute(
            "INSERT INTO signals "
            "(date, symbol, strategy, entry_price, stop_loss, target_1, target_2, "
            "quantity, capital_required, signal_strength, gap_pct, volume_ratio, "
            "reason, created_at, expires_at, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "2026-02-28", "TCS", "ORB", 3500.0, 3450.0,
                3550.0, 3600.0, 3, 10500.0, 3, 0.0, 2.0,
                "ORB breakout", "2026-02-28T10:00:00", "2026-02-28T10:30:00", "sent",
            ),
        )
        await conn.commit()

        # Re-run migration
        await db._run_news_sentiment_migration()

        # Signal still present
        cursor = await conn.execute(
            "SELECT symbol, strategy FROM signals WHERE id = 1"
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == "TCS"
        assert row[1] == "ORB"
