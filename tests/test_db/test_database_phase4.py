"""Tests for Phase 4 database migration."""

import pytest

from signalpilot.db.database import DatabaseManager


class TestPhase4Migration:
    async def test_phase4_tables_created(self, db):
        conn = db.connection
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        rows = await cursor.fetchall()
        tables = {row["name"] for row in rows}
        assert "signal_actions" in tables
        assert "watchlist" in tables

    async def test_phase4_migration_idempotent(self, db):
        # Running migration again should not raise
        await db._run_phase4_migration()
        # Verify tables still exist
        cursor = await db.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('signal_actions', 'watchlist')"
        )
        rows = await cursor.fetchall()
        assert len(rows) == 2

    async def test_existing_tables_unchanged(self, db):
        conn = db.connection
        # Verify signals table still has expected columns
        cursor = await conn.execute("PRAGMA table_info(signals)")
        cols = {row["name"] for row in await cursor.fetchall()}
        assert "id" in cols
        assert "symbol" in cols
        assert "status" in cols

        # Verify trades table still has expected columns
        cursor = await conn.execute("PRAGMA table_info(trades)")
        cols = {row["name"] for row in await cursor.fetchall()}
        assert "id" in cols
        assert "signal_id" in cols
        assert "strategy" in cols

        # Verify user_config unchanged
        cursor = await conn.execute("PRAGMA table_info(user_config)")
        cols = {row["name"] for row in await cursor.fetchall()}
        assert "telegram_chat_id" in cols
