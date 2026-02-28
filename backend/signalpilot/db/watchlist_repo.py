"""Repository for watchlist records (Phase 4: Quick Action Buttons)."""

from datetime import datetime

import aiosqlite

from signalpilot.db.models import WatchlistRecord
from signalpilot.utils.constants import IST


class WatchlistRepository:
    """CRUD operations for the watchlist table."""

    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._conn = connection

    async def add_to_watchlist(self, record: WatchlistRecord) -> int:
        """Insert a watchlist entry and return the new row ID."""
        added_at = record.added_at or datetime.now(IST)
        expires_at = record.expires_at or datetime.now(IST)
        cursor = await self._conn.execute(
            """
            INSERT INTO watchlist
                (symbol, signal_id, strategy, entry_price, added_at, expires_at,
                 triggered_count, last_triggered_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.symbol,
                record.signal_id,
                record.strategy,
                record.entry_price,
                added_at.isoformat(),
                expires_at.isoformat(),
                record.triggered_count,
                record.last_triggered_at.isoformat() if record.last_triggered_at else None,
            ),
        )
        await self._conn.commit()
        row_id = cursor.lastrowid
        assert row_id is not None, "INSERT did not return a row ID"
        return row_id

    async def get_active_watchlist(self, now: datetime) -> list[WatchlistRecord]:
        """Return active (non-expired) watchlist entries, ordered by added_at DESC."""
        cursor = await self._conn.execute(
            """
            SELECT * FROM watchlist
            WHERE expires_at > ?
            ORDER BY added_at DESC
            """,
            (now.isoformat(),),
        )
        rows = await cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    async def is_on_watchlist(self, symbol: str, now: datetime) -> bool:
        """Return True if an active watchlist entry exists for the symbol."""
        cursor = await self._conn.execute(
            """
            SELECT COUNT(*) FROM watchlist
            WHERE symbol = ? AND expires_at > ?
            """,
            (symbol, now.isoformat()),
        )
        row = await cursor.fetchone()
        return row[0] > 0

    async def remove_from_watchlist(self, symbol: str) -> int:
        """Delete all entries for a symbol. Return count of deleted rows."""
        cursor = await self._conn.execute(
            "DELETE FROM watchlist WHERE symbol = ?",
            (symbol,),
        )
        await self._conn.commit()
        return cursor.rowcount

    async def increment_trigger(self, symbol: str, now: datetime) -> None:
        """Increment triggered_count and set last_triggered_at for active entries."""
        await self._conn.execute(
            """
            UPDATE watchlist
            SET triggered_count = triggered_count + 1,
                last_triggered_at = ?
            WHERE symbol = ? AND expires_at > ?
            """,
            (now.isoformat(), symbol, now.isoformat()),
        )
        await self._conn.commit()

    async def cleanup_expired(self, now: datetime) -> int:
        """Delete expired watchlist entries. Return count of deleted rows."""
        cursor = await self._conn.execute(
            "DELETE FROM watchlist WHERE expires_at <= ?",
            (now.isoformat(),),
        )
        await self._conn.commit()
        return cursor.rowcount

    @staticmethod
    def _row_to_record(row: aiosqlite.Row) -> WatchlistRecord:
        """Convert a database row to a WatchlistRecord."""
        return WatchlistRecord(
            id=row["id"],
            symbol=row["symbol"],
            signal_id=row["signal_id"],
            strategy=row["strategy"],
            entry_price=row["entry_price"],
            added_at=datetime.fromisoformat(row["added_at"]),
            expires_at=datetime.fromisoformat(row["expires_at"]),
            triggered_count=row["triggered_count"],
            last_triggered_at=(
                datetime.fromisoformat(row["last_triggered_at"])
                if row["last_triggered_at"]
                else None
            ),
        )
