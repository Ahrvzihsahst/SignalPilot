"""Metrics calculator for performance reporting."""

from datetime import date

import aiosqlite

from signalpilot.db.models import DailySummary, PerformanceMetrics, StrategyDaySummary
from signalpilot.db.trade_repo import TradeRepository


class MetricsCalculator:
    """Aggregate queries for win rate, P&L, and daily summaries."""

    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._conn = connection
        self._trade_repo = TradeRepository(connection)

    async def calculate_performance_metrics(
        self,
        date_start: date | None = None,
        date_end: date | None = None,
    ) -> PerformanceMetrics:
        """Calculate aggregated performance metrics for closed trades.

        If date_start/date_end are None, calculates across all closed trades.
        A "win" is pnl_amount > 0, a "loss" is pnl_amount <= 0 (Req 30.3).
        """
        if date_start and date_end:
            query = """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN pnl_amount > 0 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN pnl_amount <= 0 THEN 1 ELSE 0 END) as losses,
                    COALESCE(SUM(pnl_amount), 0.0) as total_pnl,
                    AVG(CASE WHEN pnl_amount > 0 THEN pnl_amount END) as avg_win,
                    AVG(CASE WHEN pnl_amount <= 0 THEN pnl_amount END) as avg_loss,
                    MAX(pnl_amount) as best_pnl,
                    MIN(pnl_amount) as worst_pnl
                FROM trades
                WHERE exited_at IS NOT NULL AND date BETWEEN ? AND ?
            """
            cursor = await self._conn.execute(
                query, (date_start.isoformat(), date_end.isoformat())
            )
        else:
            query = """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN pnl_amount > 0 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN pnl_amount <= 0 THEN 1 ELSE 0 END) as losses,
                    COALESCE(SUM(pnl_amount), 0.0) as total_pnl,
                    AVG(CASE WHEN pnl_amount > 0 THEN pnl_amount END) as avg_win,
                    AVG(CASE WHEN pnl_amount <= 0 THEN pnl_amount END) as avg_loss,
                    MAX(pnl_amount) as best_pnl,
                    MIN(pnl_amount) as worst_pnl
                FROM trades
                WHERE exited_at IS NOT NULL
            """
            cursor = await self._conn.execute(query)

        row = await cursor.fetchone()

        total = row["total"] or 0
        wins = row["wins"] or 0
        losses = row["losses"] or 0
        total_pnl = row["total_pnl"] or 0.0
        avg_win = row["avg_win"] or 0.0
        avg_loss = row["avg_loss"] or 0.0
        best_pnl = row["best_pnl"] or 0.0
        worst_pnl = row["worst_pnl"] or 0.0

        win_rate = (wins / total * 100) if total > 0 else 0.0
        risk_reward = abs(avg_win / avg_loss) if avg_loss != 0 else 0.0

        # Find best/worst trade symbols (respecting date range)
        best_symbol = ""
        worst_symbol = ""
        if total > 0:
            if date_start and date_end:
                best_cursor = await self._conn.execute(
                    "SELECT symbol FROM trades WHERE exited_at IS NOT NULL AND date BETWEEN ? AND ? ORDER BY pnl_amount DESC LIMIT 1",
                    (date_start.isoformat(), date_end.isoformat()),
                )
            else:
                best_cursor = await self._conn.execute(
                    "SELECT symbol FROM trades WHERE exited_at IS NOT NULL ORDER BY pnl_amount DESC LIMIT 1"
                )
            best_row = await best_cursor.fetchone()
            if best_row:
                best_symbol = best_row["symbol"]

            if date_start and date_end:
                worst_cursor = await self._conn.execute(
                    "SELECT symbol FROM trades WHERE exited_at IS NOT NULL AND date BETWEEN ? AND ? ORDER BY pnl_amount ASC LIMIT 1",
                    (date_start.isoformat(), date_end.isoformat()),
                )
            else:
                worst_cursor = await self._conn.execute(
                    "SELECT symbol FROM trades WHERE exited_at IS NOT NULL ORDER BY pnl_amount ASC LIMIT 1"
                )
            worst_row = await worst_cursor.fetchone()
            if worst_row:
                worst_symbol = worst_row["symbol"]

        effective_start = date_start or date.today()
        effective_end = date_end or date.today()

        # Count total signals in the date range
        if date_start and date_end:
            sig_cursor = await self._conn.execute(
                "SELECT COUNT(*) FROM signals WHERE date BETWEEN ? AND ?",
                (date_start.isoformat(), date_end.isoformat()),
            )
        else:
            sig_cursor = await self._conn.execute("SELECT COUNT(*) FROM signals")
        sig_row = await sig_cursor.fetchone()
        total_signals = sig_row[0] or 0

        return PerformanceMetrics(
            date_range_start=effective_start,
            date_range_end=effective_end,
            total_signals=total_signals,
            trades_taken=total,
            wins=wins,
            losses=losses,
            win_rate=win_rate,
            total_pnl=total_pnl,
            avg_win=avg_win,
            avg_loss=avg_loss,
            risk_reward_ratio=risk_reward,
            best_trade_symbol=best_symbol,
            best_trade_pnl=best_pnl,
            worst_trade_symbol=worst_symbol,
            worst_trade_pnl=worst_pnl,
        )

    async def calculate_daily_summary(self, d: date) -> DailySummary:
        """Calculate the daily summary for the given date."""
        trades = await self._trade_repo.get_trades_by_date(d)

        # Count signals for the day
        sig_cursor = await self._conn.execute(
            "SELECT COUNT(*) FROM signals WHERE date = ?",
            (d.isoformat(),),
        )
        sig_row = await sig_cursor.fetchone()
        signals_sent = sig_row[0] or 0

        closed_trades = [t for t in trades if t.exited_at is not None]
        wins = sum(1 for t in closed_trades if t.pnl_amount is not None and t.pnl_amount > 0)
        losses = sum(1 for t in closed_trades if t.pnl_amount is not None and t.pnl_amount <= 0)
        total_pnl = sum(t.pnl_amount for t in closed_trades if t.pnl_amount is not None)

        # Cumulative P&L: sum of all closed trades up to and including this date
        cum_cursor = await self._conn.execute(
            """
            SELECT COALESCE(SUM(pnl_amount), 0.0) FROM trades
            WHERE exited_at IS NOT NULL AND date <= ?
            """,
            (d.isoformat(),),
        )
        cum_row = await cum_cursor.fetchone()
        cumulative_pnl = cum_row[0] or 0.0

        strategy_breakdown = await self.calculate_daily_summary_by_strategy(d)

        return DailySummary(
            date=d,
            signals_sent=signals_sent,
            trades_taken=len(trades),
            wins=wins,
            losses=losses,
            total_pnl=total_pnl,
            cumulative_pnl=cumulative_pnl,
            trades=trades,
            strategy_breakdown=strategy_breakdown if strategy_breakdown else None,
        )

    async def calculate_daily_summary_by_strategy(
        self, d: date
    ) -> dict[str, StrategyDaySummary]:
        """Calculate per-strategy breakdown for a given date."""
        # Count signals per strategy
        sig_cursor = await self._conn.execute(
            "SELECT strategy, COUNT(*) as cnt FROM signals WHERE date = ? GROUP BY strategy",
            (d.isoformat(),),
        )
        sig_rows = await sig_cursor.fetchall()
        signal_counts: dict[str, int] = {row["strategy"]: row["cnt"] for row in sig_rows}

        # Count trades per strategy
        trade_cursor = await self._conn.execute(
            """
            SELECT strategy,
                   COUNT(*) as taken,
                   COALESCE(SUM(CASE WHEN pnl_amount > 0 THEN pnl_amount ELSE 0 END), 0)
                   + COALESCE(SUM(CASE WHEN pnl_amount <= 0 THEN pnl_amount ELSE 0 END), 0) as pnl
            FROM trades WHERE date = ?
            GROUP BY strategy
            """,
            (d.isoformat(),),
        )
        trade_rows = await trade_cursor.fetchall()

        result: dict[str, StrategyDaySummary] = {}
        strategies = set(signal_counts.keys())
        for row in trade_rows:
            strategies.add(row["strategy"])

        for strategy in strategies:
            signals_generated = signal_counts.get(strategy, 0)
            # Find matching trade row
            trade_data = next(
                (r for r in trade_rows if r["strategy"] == strategy), None
            )
            signals_taken = trade_data["taken"] if trade_data else 0
            pnl = trade_data["pnl"] if trade_data else 0.0
            result[strategy] = StrategyDaySummary(
                strategy_name=strategy,
                signals_generated=signals_generated,
                signals_taken=signals_taken,
                pnl=pnl,
            )

        return result
