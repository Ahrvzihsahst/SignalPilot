"""Repository for strategy performance records."""

from datetime import date

import aiosqlite

from signalpilot.db.models import StrategyPerformanceRecord


class StrategyPerformanceRepository:
    """CRUD operations for the strategy_performance table."""

    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._conn = connection

    async def upsert_daily(self, record: StrategyPerformanceRecord) -> None:
        """Insert or update a daily strategy performance record."""
        await self._conn.execute(
            """
            INSERT INTO strategy_performance
                (strategy, date, signals_generated, signals_taken, wins, losses,
                 total_pnl, win_rate, avg_win, avg_loss, expectancy, capital_weight_pct)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(strategy, date) DO UPDATE SET
                signals_generated = excluded.signals_generated,
                signals_taken = excluded.signals_taken,
                wins = excluded.wins,
                losses = excluded.losses,
                total_pnl = excluded.total_pnl,
                win_rate = excluded.win_rate,
                avg_win = excluded.avg_win,
                avg_loss = excluded.avg_loss,
                expectancy = excluded.expectancy,
                capital_weight_pct = excluded.capital_weight_pct
            """,
            (
                record.strategy,
                record.date,
                record.signals_generated,
                record.signals_taken,
                record.wins,
                record.losses,
                record.total_pnl,
                record.win_rate,
                record.avg_win,
                record.avg_loss,
                record.expectancy,
                record.capital_weight_pct,
            ),
        )
        await self._conn.commit()

    async def get_performance_summary(
        self,
        strategy: str,
        start_date: date,
        end_date: date,
    ) -> list[StrategyPerformanceRecord]:
        """Get performance records for a strategy within a date range."""
        cursor = await self._conn.execute(
            """
            SELECT * FROM strategy_performance
            WHERE strategy = ? AND date BETWEEN ? AND ?
            ORDER BY date
            """,
            (strategy, start_date.isoformat(), end_date.isoformat()),
        )
        rows = await cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    async def get_by_date_range(
        self,
        start_date: date,
        end_date: date,
    ) -> list[StrategyPerformanceRecord]:
        """Get all strategy performance records within a date range."""
        cursor = await self._conn.execute(
            """
            SELECT * FROM strategy_performance
            WHERE date BETWEEN ? AND ?
            ORDER BY date, strategy
            """,
            (start_date.isoformat(), end_date.isoformat()),
        )
        rows = await cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    @staticmethod
    def _row_to_record(row: aiosqlite.Row) -> StrategyPerformanceRecord:
        """Convert a database row to a StrategyPerformanceRecord."""
        return StrategyPerformanceRecord(
            id=row["id"],
            strategy=row["strategy"],
            date=row["date"],
            signals_generated=row["signals_generated"],
            signals_taken=row["signals_taken"],
            wins=row["wins"],
            losses=row["losses"],
            total_pnl=row["total_pnl"],
            win_rate=row["win_rate"],
            avg_win=row["avg_win"],
            avg_loss=row["avg_loss"],
            expectancy=row["expectancy"],
            capital_weight_pct=row["capital_weight_pct"],
        )
