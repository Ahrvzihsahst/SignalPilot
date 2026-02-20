"""Repository for user configuration."""

from datetime import datetime

import aiosqlite

from signalpilot.db.models import UserConfig


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
        now = datetime.now().isoformat()
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
        now = datetime.now().isoformat()
        cursor = await self._conn.execute(
            "UPDATE user_config SET total_capital = ?, updated_at = ? WHERE id = (SELECT MIN(id) FROM user_config)",
            (total_capital, now),
        )
        await self._conn.commit()
        if cursor.rowcount == 0:
            raise RuntimeError("No user config exists. Call initialize_default() first.")

    async def update_max_positions(self, max_positions: int) -> None:
        """Update the maximum number of simultaneous positions."""
        now = datetime.now().isoformat()
        cursor = await self._conn.execute(
            "UPDATE user_config SET max_positions = ?, updated_at = ? WHERE id = (SELECT MIN(id) FROM user_config)",
            (max_positions, now),
        )
        await self._conn.commit()
        if cursor.rowcount == 0:
            raise RuntimeError("No user config exists. Call initialize_default() first.")

    _STRATEGY_FIELDS = frozenset({"gap_go_enabled", "orb_enabled", "vwap_enabled"})

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
        now = datetime.now().isoformat()
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
        )
