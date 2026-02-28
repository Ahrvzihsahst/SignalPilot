"""Repository for the regime_performance table."""

from __future__ import annotations

import logging
from datetime import date, datetime

import aiosqlite

from signalpilot.utils.constants import IST

logger = logging.getLogger(__name__)


class RegimePerformanceRepository:
    """Repository for the regime_performance table."""

    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._conn = connection

    async def insert_daily_performance(
        self,
        regime_date: date,
        regime: str,
        strategy: str,
        signals_generated: int,
        signals_taken: int,
        wins: int,
        losses: int,
        pnl: float,
    ) -> int:
        """Insert a daily performance record for a strategy under a regime."""
        win_rate = (wins / signals_taken * 100) if signals_taken > 0 else None
        now = datetime.now(IST).isoformat()
        cursor = await self._conn.execute(
            """
            INSERT INTO regime_performance (
                regime_date, regime, strategy,
                signals_generated, signals_taken, wins, losses, pnl, win_rate,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                regime_date.isoformat(), regime, strategy,
                signals_generated, signals_taken, wins, losses, pnl, win_rate,
                now,
            ),
        )
        await self._conn.commit()
        return cursor.lastrowid

    async def get_performance_by_regime(self, regime: str, days: int = 30) -> list[dict]:
        """Return aggregated performance for a specific regime."""
        cursor = await self._conn.execute(
            """
            SELECT strategy,
                   SUM(signals_generated) as total_signals,
                   SUM(signals_taken) as total_taken,
                   SUM(wins) as total_wins,
                   SUM(losses) as total_losses,
                   SUM(pnl) as total_pnl,
                   CASE WHEN SUM(signals_taken) > 0
                        THEN CAST(SUM(wins) AS REAL) / SUM(signals_taken) * 100
                        ELSE NULL END as agg_win_rate
            FROM regime_performance
            WHERE regime = ?
              AND regime_date >= date('now', ? || ' days')
            GROUP BY strategy
            """,
            (regime, f"-{days}"),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_performance_summary(self, days: int = 30) -> list[dict]:
        """Return performance summary grouped by regime and strategy."""
        cursor = await self._conn.execute(
            """
            SELECT regime, strategy,
                   SUM(signals_generated) as total_signals,
                   SUM(signals_taken) as total_taken,
                   SUM(wins) as total_wins,
                   SUM(losses) as total_losses,
                   SUM(pnl) as total_pnl,
                   CASE WHEN SUM(signals_taken) > 0
                        THEN CAST(SUM(wins) AS REAL) / SUM(signals_taken) * 100
                        ELSE NULL END as agg_win_rate
            FROM regime_performance
            WHERE regime_date >= date('now', ? || ' days')
            GROUP BY regime, strategy
            ORDER BY regime, strategy
            """,
            (f"-{days}",),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
