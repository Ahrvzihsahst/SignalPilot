"""Repository for adaptation log records."""

from datetime import date, datetime

import aiosqlite

from signalpilot.db.models import AdaptationLogRecord
from signalpilot.utils.constants import IST
from signalpilot.utils.datetime_utils import parse_ist_datetime


class AdaptationLogRepository:
    """CRUD operations for the adaptation_log table."""

    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._conn = connection

    async def insert_log(
        self,
        today: date,
        strategy: str,
        event_type: str,
        details: str,
        old_weight: float | None,
        new_weight: float | None,
    ) -> int:
        """Insert an adaptation log entry and return the new row ID."""
        cursor = await self._conn.execute(
            """
            INSERT INTO adaptation_log
                (date, strategy, event_type, details, old_weight, new_weight, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                today.isoformat(),
                strategy,
                event_type,
                details,
                old_weight,
                new_weight,
                datetime.now(IST).isoformat(),
            ),
        )
        await self._conn.commit()
        row_id = cursor.lastrowid
        assert row_id is not None, "INSERT did not return a row ID"
        return row_id

    async def get_by_date(self, d: date) -> list[AdaptationLogRecord]:
        """Return all adaptation logs for a given date, ordered by created_at DESC."""
        cursor = await self._conn.execute(
            """
            SELECT id, date, strategy, event_type, details,
                   old_weight, new_weight, created_at
            FROM adaptation_log
            WHERE date = ?
            ORDER BY created_at DESC
            """,
            (d.isoformat(),),
        )
        rows = await cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    async def get_by_strategy(
        self, strategy: str, limit: int = 30,
    ) -> list[AdaptationLogRecord]:
        """Return adaptation logs for a specific strategy."""
        cursor = await self._conn.execute(
            """
            SELECT id, date, strategy, event_type, details,
                   old_weight, new_weight, created_at
            FROM adaptation_log
            WHERE strategy = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (strategy, limit),
        )
        rows = await cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    async def get_recent(self, limit: int = 50) -> list[AdaptationLogRecord]:
        """Return the most recent adaptation log entries."""
        cursor = await self._conn.execute(
            """
            SELECT id, date, strategy, event_type, details,
                   old_weight, new_weight, created_at
            FROM adaptation_log
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    async def get_by_event_type(
        self, event_type: str, limit: int = 30,
    ) -> list[AdaptationLogRecord]:
        """Return adaptation logs for a specific event type."""
        cursor = await self._conn.execute(
            """
            SELECT id, date, strategy, event_type, details,
                   old_weight, new_weight, created_at
            FROM adaptation_log
            WHERE event_type = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (event_type, limit),
        )
        rows = await cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    @staticmethod
    def _row_to_record(row: aiosqlite.Row) -> AdaptationLogRecord:
        """Convert a database row to an AdaptationLogRecord."""
        return AdaptationLogRecord(
            id=row["id"],
            date=date.fromisoformat(row["date"]),
            strategy=row["strategy"],
            event_type=row["event_type"],
            details=row["details"],
            old_weight=row["old_weight"],
            new_weight=row["new_weight"],
            created_at=parse_ist_datetime(row["created_at"]),
        )
