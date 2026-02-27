"""Repository for circuit breaker log records."""

from datetime import date, datetime

import aiosqlite

from signalpilot.db.models import CircuitBreakerRecord
from signalpilot.utils.constants import IST


class CircuitBreakerRepository:
    """CRUD operations for the circuit_breaker_log table."""

    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._conn = connection

    async def log_activation(
        self, today: date, sl_count: int, triggered_at: datetime,
    ) -> int:
        """Insert a circuit breaker activation record and return the new row ID."""
        cursor = await self._conn.execute(
            """
            INSERT INTO circuit_breaker_log
                (date, sl_count, triggered_at)
            VALUES (?, ?, ?)
            """,
            (
                today.isoformat(),
                sl_count,
                triggered_at.isoformat(),
            ),
        )
        await self._conn.commit()
        row_id = cursor.lastrowid
        assert row_id is not None, "INSERT did not return a row ID"
        return row_id

    async def log_override(self, today: date, override_at: datetime) -> None:
        """Update today's record with manual override."""
        cursor = await self._conn.execute(
            """
            UPDATE circuit_breaker_log
            SET manual_override = 1, override_at = ?
            WHERE date = ?
            """,
            (override_at.isoformat(), today.isoformat()),
        )
        await self._conn.commit()
        if cursor.rowcount == 0:
            raise ValueError(f"No circuit breaker record found for {today.isoformat()}")

    async def log_resume(self, today: date, resumed_at: datetime) -> None:
        """Update today's record with resume timestamp."""
        cursor = await self._conn.execute(
            """
            UPDATE circuit_breaker_log
            SET resumed_at = ?
            WHERE date = ?
            """,
            (resumed_at.isoformat(), today.isoformat()),
        )
        await self._conn.commit()
        if cursor.rowcount == 0:
            raise ValueError(f"No circuit breaker record found for {today.isoformat()}")

    async def get_today_status(self, today: date) -> CircuitBreakerRecord | None:
        """Return today's circuit breaker record, or None if not triggered."""
        cursor = await self._conn.execute(
            """
            SELECT id, date, sl_count, triggered_at, resumed_at,
                   manual_override, override_at
            FROM circuit_breaker_log
            WHERE date = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (today.isoformat(),),
        )
        row = await cursor.fetchone()
        return self._row_to_record(row) if row else None

    async def get_history(self, limit: int = 30) -> list[CircuitBreakerRecord]:
        """Return recent circuit breaker records, ordered by date descending."""
        cursor = await self._conn.execute(
            """
            SELECT id, date, sl_count, triggered_at, resumed_at,
                   manual_override, override_at
            FROM circuit_breaker_log
            ORDER BY date DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    @staticmethod
    def _row_to_record(row: aiosqlite.Row) -> CircuitBreakerRecord:
        """Convert a database row to a CircuitBreakerRecord."""

        def _parse_dt(val: str | None) -> datetime | None:
            if val is None:
                return None
            dt = datetime.fromisoformat(val)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=IST)
            return dt

        return CircuitBreakerRecord(
            id=row["id"],
            date=date.fromisoformat(row["date"]),
            sl_count=row["sl_count"],
            triggered_at=_parse_dt(row["triggered_at"]),
            resumed_at=_parse_dt(row["resumed_at"]),
            manual_override=bool(row["manual_override"]),
            override_at=_parse_dt(row["override_at"]),
        )
