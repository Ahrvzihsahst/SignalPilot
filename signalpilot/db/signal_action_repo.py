"""Repository for signal action records (Phase 4: Quick Action Buttons)."""

from datetime import date, datetime, timedelta

import aiosqlite

from signalpilot.db.models import SignalActionRecord
from signalpilot.utils.constants import IST


class SignalActionRepository:
    """CRUD operations for the signal_actions table."""

    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._conn = connection

    async def insert_action(self, record: SignalActionRecord) -> int:
        """Insert a signal action record and return the new row ID."""
        acted_at = record.acted_at or datetime.now(IST)
        cursor = await self._conn.execute(
            """
            INSERT INTO signal_actions
                (signal_id, action, reason, response_time_ms, acted_at, message_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                record.signal_id,
                record.action,
                record.reason,
                record.response_time_ms,
                acted_at.isoformat(),
                record.message_id,
            ),
        )
        await self._conn.commit()
        row_id = cursor.lastrowid
        assert row_id is not None, "INSERT did not return a row ID"
        return row_id

    async def get_actions_for_signal(self, signal_id: int) -> list[SignalActionRecord]:
        """Return all actions for a given signal, ordered by acted_at."""
        cursor = await self._conn.execute(
            "SELECT * FROM signal_actions WHERE signal_id = ? ORDER BY acted_at",
            (signal_id,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    async def get_average_response_time(self, days: int = 30) -> float | None:
        """Return average response_time_ms within the last N days, or None if no data."""
        now = datetime.now(IST)
        cutoff = (now - timedelta(days=days)).isoformat()
        cursor = await self._conn.execute(
            """
            SELECT AVG(response_time_ms) FROM signal_actions
            WHERE acted_at >= ? AND response_time_ms IS NOT NULL
            """,
            (cutoff,),
        )
        row = await cursor.fetchone()
        return row[0] if row and row[0] is not None else None

    async def get_skip_reason_distribution(self, days: int = 30) -> dict[str, int]:
        """Return {reason_code: count} for skip actions within the last N days."""
        now = datetime.now(IST)
        cutoff = (now - timedelta(days=days)).isoformat()
        cursor = await self._conn.execute(
            """
            SELECT reason, COUNT(*) as cnt FROM signal_actions
            WHERE action = 'skip' AND acted_at >= ? AND reason IS NOT NULL
            GROUP BY reason
            """,
            (cutoff,),
        )
        rows = await cursor.fetchall()
        return {row["reason"]: row["cnt"] for row in rows}

    async def get_action_summary(self, d: date) -> dict[str, int]:
        """Return {"taken": N, "skip": N, "watch": N} for the given date."""
        date_str = d.isoformat()
        cursor = await self._conn.execute(
            """
            SELECT action, COUNT(*) as cnt FROM signal_actions
            WHERE acted_at LIKE ? || '%'
            GROUP BY action
            """,
            (date_str,),
        )
        rows = await cursor.fetchall()
        result: dict[str, int] = {}
        for row in rows:
            result[row["action"]] = row["cnt"]
        return result

    async def get_response_time_distribution(self, days: int = 30) -> list[tuple]:
        """Return (response_time_ms, action, date) tuples for the last N days."""
        now = datetime.now(IST)
        cutoff = (now - timedelta(days=days)).isoformat()
        cursor = await self._conn.execute(
            """
            SELECT response_time_ms, action, DATE(acted_at) as action_date
            FROM signal_actions
            WHERE acted_at >= ? AND response_time_ms IS NOT NULL
            ORDER BY acted_at
            """,
            (cutoff,),
        )
        rows = await cursor.fetchall()
        return [(row["response_time_ms"], row["action"], row["action_date"]) for row in rows]

    @staticmethod
    def _row_to_record(row: aiosqlite.Row) -> SignalActionRecord:
        """Convert a database row to a SignalActionRecord."""
        return SignalActionRecord(
            id=row["id"],
            signal_id=row["signal_id"],
            action=row["action"],
            reason=row["reason"],
            response_time_ms=row["response_time_ms"],
            acted_at=datetime.fromisoformat(row["acted_at"]),
            message_id=row["message_id"],
        )
