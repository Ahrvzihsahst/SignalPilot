"""Repository for user configuration."""

from datetime import datetime

import aiosqlite

from signalpilot.db.models import UserConfig
from signalpilot.utils.constants import IST


class ConfigRepository:
    """CRUD operations for the user_config table."""

    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._conn = connection

    async def get_user_config(self) -> UserConfig | None:
        """Return the current user config, or None if no config exists."""
        cursor = await self._conn.execute(
            "SELECT * FROM user_config ORDER BY id LIMIT 1",
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_config(row)

    async def initialize_default(
        self,
        telegram_chat_id: str,
        total_capital: float = 50000.0,
        max_positions: int = 5,
    ) -> UserConfig:
        """Create or update default config. Returns the config."""
        now = datetime.now(IST).isoformat()
        existing = await self.get_user_config()
        if existing is None:
            await self._conn.execute(
                """
                INSERT INTO user_config
                    (telegram_chat_id, total_capital, max_positions, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (telegram_chat_id, total_capital, max_positions, now, now),
            )
        else:
            await self._conn.execute(
                """
                UPDATE user_config
                SET telegram_chat_id = ?, total_capital = ?, max_positions = ?, updated_at = ?
                WHERE id = ?
                """,
                (telegram_chat_id, total_capital, max_positions, now, existing.id),
            )
        await self._conn.commit()
        return await self.get_user_config()

    async def update_capital(self, total_capital: float) -> None:
        """Update the total trading capital."""
        now = datetime.now(IST).isoformat()
        cursor = await self._conn.execute(
            "UPDATE user_config SET total_capital = ?, updated_at = ? WHERE id = (SELECT MIN(id) FROM user_config)",
            (total_capital, now),
        )
        await self._conn.commit()
        if cursor.rowcount == 0:
            raise RuntimeError("No user config exists. Call initialize_default() first.")

    async def update_max_positions(self, max_positions: int) -> None:
        """Update the maximum number of simultaneous positions."""
        now = datetime.now(IST).isoformat()
        cursor = await self._conn.execute(
            "UPDATE user_config SET max_positions = ?, updated_at = ? WHERE id = (SELECT MIN(id) FROM user_config)",
            (max_positions, now),
        )
        await self._conn.commit()
        if cursor.rowcount == 0:
            raise RuntimeError("No user config exists. Call initialize_default() first.")

    _PHASE3_FIELDS = frozenset({
        "circuit_breaker_limit", "confidence_boost_enabled",
        "adaptive_learning_enabled", "auto_rebalance_enabled", "adaptation_mode",
    })

    async def update_user_config(self, **kwargs: object) -> None:
        """Update one or more Phase 3 config fields.

        Accepted fields: circuit_breaker_limit, confidence_boost_enabled,
        adaptive_learning_enabled, auto_rebalance_enabled, adaptation_mode.
        Boolean fields are stored as INTEGER (0/1).
        """
        invalid = set(kwargs) - self._PHASE3_FIELDS
        if invalid:
            raise ValueError(f"Invalid config field(s): {invalid}")
        if not kwargs:
            return

        now = datetime.now(IST).isoformat()
        set_clauses = []
        values: list[object] = []
        for field_name, value in kwargs.items():
            set_clauses.append(f"{field_name} = ?")
            # Boolean fields are stored as integers in SQLite
            if isinstance(value, bool):
                values.append(1 if value else 0)
            else:
                values.append(value)
        set_clauses.append("updated_at = ?")
        values.append(now)

        sql = f"UPDATE user_config SET {', '.join(set_clauses)} WHERE id = (SELECT MIN(id) FROM user_config)"
        cursor = await self._conn.execute(sql, values)
        await self._conn.commit()
        if cursor.rowcount == 0:
            raise RuntimeError("No user config exists. Call initialize_default() first.")

    _STRATEGY_FIELDS = frozenset({
        "gap_go_enabled", "orb_enabled", "vwap_enabled",
    })

    async def get_strategy_enabled(self, field: str) -> bool:
        """Return whether a strategy is enabled.

        field is one of gap_go_enabled, orb_enabled, vwap_enabled.
        Defaults to True if not explicitly set.
        """
        if field not in self._STRATEGY_FIELDS:
            raise ValueError(f"Invalid strategy field: {field!r}")
        config = await self.get_user_config()
        if config is None:
            return True
        return getattr(config, field, True)

    async def set_strategy_enabled(self, field: str, enabled: bool) -> None:
        """Enable or disable a strategy.

        field is one of gap_go_enabled, orb_enabled, vwap_enabled.
        """
        if field not in self._STRATEGY_FIELDS:
            raise ValueError(f"Invalid strategy field: {field!r}")
        now = datetime.now(IST).isoformat()
        value = 1 if enabled else 0
        cursor = await self._conn.execute(
            f"UPDATE user_config SET {field} = ?, updated_at = ? WHERE id = (SELECT MIN(id) FROM user_config)",
            (value, now),
        )
        await self._conn.commit()
        if cursor.rowcount == 0:
            raise RuntimeError("No user config exists. Call initialize_default() first.")

    @staticmethod
    def _row_to_config(row: aiosqlite.Row) -> UserConfig:
        """Convert a database row to a UserConfig."""
        keys = row.keys()
        return UserConfig(
            id=row["id"],
            telegram_chat_id=row["telegram_chat_id"],
            total_capital=row["total_capital"],
            max_positions=row["max_positions"],
            gap_go_enabled=bool(row["gap_go_enabled"]) if "gap_go_enabled" in keys else True,
            orb_enabled=bool(row["orb_enabled"]) if "orb_enabled" in keys else True,
            vwap_enabled=bool(row["vwap_enabled"]) if "vwap_enabled" in keys else True,
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
            # Phase 3 fields with safe defaults for pre-existing rows
            circuit_breaker_limit=(
                row["circuit_breaker_limit"]
                if "circuit_breaker_limit" in keys and row["circuit_breaker_limit"] is not None
                else 3
            ),
            confidence_boost_enabled=(
                bool(row["confidence_boost_enabled"])
                if "confidence_boost_enabled" in keys and row["confidence_boost_enabled"] is not None
                else True
            ),
            adaptive_learning_enabled=(
                bool(row["adaptive_learning_enabled"])
                if "adaptive_learning_enabled" in keys and row["adaptive_learning_enabled"] is not None
                else True
            ),
            auto_rebalance_enabled=(
                bool(row["auto_rebalance_enabled"])
                if "auto_rebalance_enabled" in keys and row["auto_rebalance_enabled"] is not None
                else True
            ),
            adaptation_mode=(
                row["adaptation_mode"]
                if "adaptation_mode" in keys and row["adaptation_mode"] is not None
                else "aggressive"
            ),
        )
