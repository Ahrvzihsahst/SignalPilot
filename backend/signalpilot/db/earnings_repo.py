"""Repository for earnings calendar records."""

from datetime import date, datetime, timedelta

import aiosqlite

from signalpilot.db.models import EarningsCalendarRecord
from signalpilot.utils.constants import IST


class EarningsCalendarRepository:
    """CRUD operations for the earnings_calendar table."""

    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._conn = connection

    async def has_earnings_today(self, stock_code: str) -> bool:
        """Check if a stock has earnings scheduled for today (IST)."""
        today = datetime.now(IST).date().isoformat()
        cursor = await self._conn.execute(
            "SELECT COUNT(*) FROM earnings_calendar WHERE stock_code = ? AND earnings_date = ?",
            (stock_code, today),
        )
        row = await cursor.fetchone()
        return row[0] > 0

    async def get_upcoming_earnings(self, days_ahead: int = 7) -> list[EarningsCalendarRecord]:
        """Return earnings within the next N days, ordered by date ASC."""
        today = datetime.now(IST).date()
        end_date = today + timedelta(days=days_ahead)
        cursor = await self._conn.execute(
            """
            SELECT * FROM earnings_calendar
            WHERE earnings_date >= ? AND earnings_date <= ?
            ORDER BY earnings_date ASC
            """,
            (today.isoformat(), end_date.isoformat()),
        )
        rows = await cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    async def upsert_earnings(
        self,
        stock_code: str,
        earnings_date: date,
        quarter: str,
        source: str,
        is_confirmed: bool,
    ) -> None:
        """Insert or replace an earnings calendar entry."""
        now = datetime.now(IST)
        await self._conn.execute(
            """
            INSERT OR REPLACE INTO earnings_calendar
                (stock_code, earnings_date, quarter, source, is_confirmed, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                stock_code,
                earnings_date.isoformat(),
                quarter,
                source,
                1 if is_confirmed else 0,
                now.isoformat(),
            ),
        )
        await self._conn.commit()

    async def get_today_earnings_stocks(self) -> list[str]:
        """Return list of stock codes with earnings today."""
        today = datetime.now(IST).date().isoformat()
        cursor = await self._conn.execute(
            "SELECT stock_code FROM earnings_calendar WHERE earnings_date = ?",
            (today,),
        )
        rows = await cursor.fetchall()
        return [row["stock_code"] for row in rows]

    @staticmethod
    def _row_to_record(row: aiosqlite.Row) -> EarningsCalendarRecord:
        """Convert a database row to an EarningsCalendarRecord."""
        return EarningsCalendarRecord(
            id=row["id"],
            stock_code=row["stock_code"],
            earnings_date=date.fromisoformat(row["earnings_date"]),
            quarter=row["quarter"],
            source=row["source"],
            is_confirmed=bool(row["is_confirmed"]),
            updated_at=(
                datetime.fromisoformat(row["updated_at"])
                if row["updated_at"]
                else None
            ),
        )
