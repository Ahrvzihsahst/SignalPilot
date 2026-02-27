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
                # Phase 2
                "setup_type", "strategy_specific_score",
                # Phase 3
                "composite_score", "confirmation_level", "confirmed_by",
                "position_size_multiplier", "adaptation_status",
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
                "id", "signal_id", "date", "symbol", "strategy",
                "entry_price", "exit_price",
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
                # Phase 2
                "gap_go_enabled", "orb_enabled", "vwap_enabled",
                # Phase 3
                "circuit_breaker_limit", "confidence_boost_enabled",
                "adaptive_learning_enabled", "auto_rebalance_enabled",
                "adaptation_mode",
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
                # Phase 3
                "idx_hybrid_scores_signal_id",
                "idx_hybrid_scores_created_at",
                "idx_circuit_breaker_date",
                "idx_adaptation_log_date",
                "idx_adaptation_log_strategy",
            }
            assert expected_indexes.issubset(indexes)
        finally:
            await manager.close()


class TestPhase3Migration:
    """Tests for Phase 3 database schema migration."""

    async def test_phase3_tables_created_on_fresh_db(self, tmp_path):
        """New hybrid_scores, circuit_breaker_log, and adaptation_log tables exist."""
        db_path = str(tmp_path / "test.db")
        manager = DatabaseManager(db_path)
        await manager.initialize()
        try:
            cursor = await manager.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = {row[0] for row in await cursor.fetchall()}
            assert "hybrid_scores" in tables
            assert "circuit_breaker_log" in tables
            assert "adaptation_log" in tables
        finally:
            await manager.close()

    async def test_hybrid_scores_table_columns(self, tmp_path):
        """hybrid_scores table has correct columns."""
        db_path = str(tmp_path / "test.db")
        manager = DatabaseManager(db_path)
        await manager.initialize()
        try:
            cursor = await manager.connection.execute("PRAGMA table_info(hybrid_scores)")
            columns = {row[1] for row in await cursor.fetchall()}
            expected = {
                "id", "signal_id", "composite_score", "strategy_strength_score",
                "win_rate_score", "risk_reward_score", "confirmation_bonus",
                "confirmed_by", "confirmation_level", "position_size_multiplier",
                "created_at",
            }
            assert columns == expected
        finally:
            await manager.close()

    async def test_circuit_breaker_log_table_columns(self, tmp_path):
        """circuit_breaker_log table has correct columns."""
        db_path = str(tmp_path / "test.db")
        manager = DatabaseManager(db_path)
        await manager.initialize()
        try:
            cursor = await manager.connection.execute(
                "PRAGMA table_info(circuit_breaker_log)"
            )
            columns = {row[1] for row in await cursor.fetchall()}
            expected = {
                "id", "date", "sl_count", "triggered_at", "resumed_at",
                "manual_override", "override_at",
            }
            assert columns == expected
        finally:
            await manager.close()

    async def test_adaptation_log_table_columns(self, tmp_path):
        """adaptation_log table has correct columns."""
        db_path = str(tmp_path / "test.db")
        manager = DatabaseManager(db_path)
        await manager.initialize()
        try:
            cursor = await manager.connection.execute("PRAGMA table_info(adaptation_log)")
            columns = {row[1] for row in await cursor.fetchall()}
            expected = {
                "id", "date", "strategy", "event_type", "details",
                "old_weight", "new_weight", "created_at",
            }
            assert columns == expected
        finally:
            await manager.close()

    async def test_signals_phase3_columns_added(self, tmp_path):
        """signals table has all 5 Phase 3 columns."""
        db_path = str(tmp_path / "test.db")
        manager = DatabaseManager(db_path)
        await manager.initialize()
        try:
            cursor = await manager.connection.execute("PRAGMA table_info(signals)")
            columns = {row[1] for row in await cursor.fetchall()}
            phase3_columns = {
                "composite_score", "confirmation_level", "confirmed_by",
                "position_size_multiplier", "adaptation_status",
            }
            assert phase3_columns.issubset(columns)
        finally:
            await manager.close()

    async def test_user_config_phase3_columns_added(self, tmp_path):
        """user_config table has all 5 Phase 3 columns."""
        db_path = str(tmp_path / "test.db")
        manager = DatabaseManager(db_path)
        await manager.initialize()
        try:
            cursor = await manager.connection.execute("PRAGMA table_info(user_config)")
            columns = {row[1] for row in await cursor.fetchall()}
            phase3_columns = {
                "circuit_breaker_limit", "confidence_boost_enabled",
                "adaptive_learning_enabled", "auto_rebalance_enabled",
                "adaptation_mode",
            }
            assert phase3_columns.issubset(columns)
        finally:
            await manager.close()

    async def test_phase3_indexes_created(self, tmp_path):
        """All 5 Phase 3 indexes are created."""
        db_path = str(tmp_path / "test.db")
        manager = DatabaseManager(db_path)
        await manager.initialize()
        try:
            cursor = await manager.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name"
            )
            indexes = {row[0] for row in await cursor.fetchall()}
            phase3_indexes = {
                "idx_hybrid_scores_signal_id",
                "idx_hybrid_scores_created_at",
                "idx_circuit_breaker_date",
                "idx_adaptation_log_date",
                "idx_adaptation_log_strategy",
            }
            assert phase3_indexes.issubset(indexes)
        finally:
            await manager.close()

    async def test_migration_is_idempotent(self, tmp_path):
        """Running Phase 3 migration twice does not error."""
        db_path = str(tmp_path / "test.db")
        manager = DatabaseManager(db_path)
        await manager.initialize()
        try:
            # Run migration again explicitly -- should not raise
            await manager._run_phase3_migration()
            # Verify tables still exist
            cursor = await manager.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = {row[0] for row in await cursor.fetchall()}
            assert "hybrid_scores" in tables
            assert "circuit_breaker_log" in tables
            assert "adaptation_log" in tables
        finally:
            await manager.close()

    async def test_existing_data_intact_after_migration(self, tmp_path):
        """Pre-existing Phase 1/2 data survives Phase 3 migration."""
        db_path = str(tmp_path / "test.db")
        manager = DatabaseManager(db_path)
        await manager.initialize()
        conn = manager.connection
        try:
            # Insert a signal (Phase 1 columns only)
            await conn.execute(
                "INSERT INTO signals "
                "(date, symbol, strategy, entry_price, stop_loss, target_1, target_2, "
                "quantity, capital_required, signal_strength, gap_pct, volume_ratio, "
                "reason, created_at, expires_at, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "2025-01-15", "SBIN", "Gap & Go", 500.0, 485.0,
                    525.0, 535.0, 30, 15000.0, 4, 4.0, 1.2,
                    "Gap up", "2025-01-15T09:35:00", "2025-01-15T10:05:00", "sent",
                ),
            )
            # Insert a user_config row
            await conn.execute(
                "INSERT INTO user_config "
                "(telegram_chat_id, total_capital, max_positions, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                ("12345", 100000.0, 5, "2025-01-15T09:00:00", "2025-01-15T09:00:00"),
            )
            await conn.commit()

            # Re-run migration to verify it does not destroy data
            await manager._run_phase3_migration()

            # Signal still present
            cursor = await conn.execute("SELECT symbol, strategy FROM signals WHERE id = 1")
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] == "SBIN"
            assert row[1] == "Gap & Go"

            # User config still present
            cursor = await conn.execute(
                "SELECT telegram_chat_id, total_capital FROM user_config WHERE id = 1"
            )
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] == "12345"
            assert row[1] == 100000.0
        finally:
            await manager.close()

    async def test_signals_phase3_default_values(self, tmp_path):
        """Existing signal rows get correct defaults for Phase 3 columns."""
        db_path = str(tmp_path / "test.db")
        manager = DatabaseManager(db_path)
        await manager.initialize()
        conn = manager.connection
        try:
            # Insert a signal before querying defaults
            await conn.execute(
                "INSERT INTO signals "
                "(date, symbol, strategy, entry_price, stop_loss, target_1, target_2, "
                "quantity, capital_required, signal_strength, gap_pct, volume_ratio, "
                "reason, created_at, expires_at, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "2025-01-15", "TCS", "ORB", 3500.0, 3450.0,
                    3550.0, 3600.0, 3, 10500.0, 3, 0.0, 2.0,
                    "ORB breakout", "2025-01-15T10:00:00", "2025-01-15T10:30:00", "sent",
                ),
            )
            await conn.commit()

            cursor = await conn.execute(
                "SELECT composite_score, confirmation_level, confirmed_by, "
                "position_size_multiplier, adaptation_status "
                "FROM signals WHERE id = 1"
            )
            row = await cursor.fetchone()
            assert row is not None
            # composite_score has no DEFAULT -> NULL
            assert row[0] is None
            # confirmation_level has no DEFAULT -> NULL
            assert row[1] is None
            # confirmed_by has no DEFAULT -> NULL
            assert row[2] is None
            # position_size_multiplier DEFAULT 1.0
            assert row[3] == 1.0
            # adaptation_status DEFAULT 'normal'
            assert row[4] == "normal"
        finally:
            await manager.close()

    async def test_user_config_phase3_default_values(self, tmp_path):
        """Existing user_config rows get correct defaults for Phase 3 columns."""
        db_path = str(tmp_path / "test.db")
        manager = DatabaseManager(db_path)
        await manager.initialize()
        conn = manager.connection
        try:
            await conn.execute(
                "INSERT INTO user_config "
                "(telegram_chat_id, total_capital, max_positions, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                ("67890", 50000.0, 8, "2025-01-15T09:00:00", "2025-01-15T09:00:00"),
            )
            await conn.commit()

            cursor = await conn.execute(
                "SELECT circuit_breaker_limit, confidence_boost_enabled, "
                "adaptive_learning_enabled, auto_rebalance_enabled, adaptation_mode "
                "FROM user_config WHERE id = 1"
            )
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] == 3         # circuit_breaker_limit DEFAULT 3
            assert row[1] == 1         # confidence_boost_enabled DEFAULT 1
            assert row[2] == 1         # adaptive_learning_enabled DEFAULT 1
            assert row[3] == 1         # auto_rebalance_enabled DEFAULT 1
            assert row[4] == "aggressive"  # adaptation_mode DEFAULT 'aggressive'
        finally:
            await manager.close()

    async def test_hybrid_scores_foreign_key(self, tmp_path):
        """hybrid_scores table enforces foreign key to signals table."""
        db_path = str(tmp_path / "test.db")
        manager = DatabaseManager(db_path)
        await manager.initialize()
        conn = manager.connection
        try:
            # Insert a signal first
            await conn.execute(
                "INSERT INTO signals "
                "(date, symbol, strategy, entry_price, stop_loss, target_1, target_2, "
                "quantity, capital_required, signal_strength, gap_pct, volume_ratio, "
                "reason, created_at, expires_at, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "2025-01-15", "SBIN", "Gap & Go", 500.0, 485.0,
                    525.0, 535.0, 30, 15000.0, 4, 4.0, 1.2,
                    "Gap up", "2025-01-15T09:35:00", "2025-01-15T10:05:00", "sent",
                ),
            )
            await conn.commit()

            # Insert valid hybrid_score referencing existing signal
            await conn.execute(
                "INSERT INTO hybrid_scores "
                "(signal_id, composite_score, strategy_strength_score, win_rate_score, "
                "risk_reward_score, confirmation_bonus, confirmation_level, "
                "position_size_multiplier, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (1, 0.85, 0.30, 0.25, 0.20, 0.10, "dual", 1.2, "2025-01-15T09:36:00"),
            )
            await conn.commit()

            cursor = await conn.execute(
                "SELECT signal_id, composite_score FROM hybrid_scores WHERE id = 1"
            )
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] == 1
            assert row[1] == 0.85
        finally:
            await manager.close()
