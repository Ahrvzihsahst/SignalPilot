"""Tests for DatabaseManager."""

import pytest

from signalpilot.db.database import DatabaseManager


class TestDatabaseManager:
    async def test_initialize_creates_tables(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        manager = DatabaseManager(db_path)
        await manager.initialize()
        try:
            conn = manager.connection
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = [row[0] for row in await cursor.fetchall()]
            assert "signals" in tables
            assert "trades" in tables
            assert "user_config" in tables
        finally:
            await manager.close()

    async def test_signals_table_columns(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        manager = DatabaseManager(db_path)
        await manager.initialize()
        try:
            cursor = await manager.connection.execute("PRAGMA table_info(signals)")
            columns = {row[1] for row in await cursor.fetchall()}
            expected = {
                "id", "date", "symbol", "strategy", "entry_price", "stop_loss",
                "target_1", "target_2", "quantity", "capital_required",
                "signal_strength", "gap_pct", "volume_ratio", "reason",
                "created_at", "expires_at", "status",
            }
            assert columns == expected
        finally:
            await manager.close()

    async def test_trades_table_columns(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        manager = DatabaseManager(db_path)
        await manager.initialize()
        try:
            cursor = await manager.connection.execute("PRAGMA table_info(trades)")
            columns = {row[1] for row in await cursor.fetchall()}
            expected = {
                "id", "signal_id", "date", "symbol", "entry_price", "exit_price",
                "stop_loss", "target_1", "target_2", "quantity", "pnl_amount",
                "pnl_pct", "exit_reason", "taken_at", "exited_at",
            }
            assert columns == expected
        finally:
            await manager.close()

    async def test_user_config_table_columns(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        manager = DatabaseManager(db_path)
        await manager.initialize()
        try:
            cursor = await manager.connection.execute("PRAGMA table_info(user_config)")
            columns = {row[1] for row in await cursor.fetchall()}
            expected = {
                "id", "telegram_chat_id", "total_capital", "max_positions",
                "created_at", "updated_at",
            }
            assert columns == expected
        finally:
            await manager.close()

    async def test_wal_mode_enabled(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        manager = DatabaseManager(db_path)
        await manager.initialize()
        try:
            cursor = await manager.connection.execute("PRAGMA journal_mode")
            row = await cursor.fetchone()
            assert row[0] == "wal"
        finally:
            await manager.close()

    async def test_foreign_keys_enabled(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        manager = DatabaseManager(db_path)
        await manager.initialize()
        try:
            cursor = await manager.connection.execute("PRAGMA foreign_keys")
            row = await cursor.fetchone()
            assert row[0] == 1
        finally:
            await manager.close()

    async def test_idempotent_initialization(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        manager = DatabaseManager(db_path)
        await manager.initialize()
        # Should not raise when called again
        await manager._create_tables()
        try:
            cursor = await manager.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='signals'"
            )
            row = await cursor.fetchone()
            assert row is not None
        finally:
            await manager.close()

    async def test_connection_property_raises_before_init(self):
        manager = DatabaseManager("unused.db")
        with pytest.raises(RuntimeError, match="Database not initialized"):
            _ = manager.connection

    async def test_close_sets_connection_to_none(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        manager = DatabaseManager(db_path)
        await manager.initialize()
        await manager.close()
        assert manager._connection is None

    async def test_indexes_created(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        manager = DatabaseManager(db_path)
        await manager.initialize()
        try:
            cursor = await manager.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name"
            )
            indexes = {row[0] for row in await cursor.fetchall()}
            expected_indexes = {
                "idx_signals_date",
                "idx_signals_status",
                "idx_signals_date_status",
                "idx_trades_date",
                "idx_trades_signal_id",
                "idx_trades_exited_at",
            }
            assert expected_indexes.issubset(indexes)
        finally:
            await manager.close()
