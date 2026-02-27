"""Strategies API routes -- comparison, confirmed performance, P&L series."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from signalpilot.dashboard.deps import get_read_conn
from signalpilot.dashboard.schemas import (
    ConfirmedPerformanceResponse,
    StrategyComparisonResponse,
    StrategyMetricsSchema,
    StrategyPnlSeriesPoint,
    StrategyPnlSeriesResponse,
)

router = APIRouter()


@router.get("/comparison")
async def get_strategy_comparison(
    conn=Depends(get_read_conn),
) -> StrategyComparisonResponse:
    """Return per-strategy aggregate metrics across all closed trades."""
    # Signals count per strategy
    sig_cursor = await conn.execute(
        "SELECT strategy, COUNT(*) as cnt FROM signals GROUP BY strategy"
    )
    sig_rows = await sig_cursor.fetchall()
    signal_counts = {row["strategy"]: row["cnt"] for row in sig_rows}

    # Closed-trade metrics per strategy
    cursor = await conn.execute(
        """
        SELECT strategy,
               COUNT(*) as total,
               SUM(CASE WHEN pnl_amount > 0 THEN 1 ELSE 0 END) as wins,
               SUM(CASE WHEN pnl_amount <= 0 THEN 1 ELSE 0 END) as losses,
               COALESCE(SUM(pnl_amount), 0) as total_pnl,
               AVG(CASE WHEN pnl_amount > 0 THEN pnl_amount END) as avg_win,
               AVG(CASE WHEN pnl_amount <= 0 THEN pnl_amount END) as avg_loss
        FROM trades
        WHERE exited_at IS NOT NULL
        GROUP BY strategy
        """
    )
    rows = await cursor.fetchall()

    # Capital weight from strategy_performance (latest entry)
    weight_cursor = await conn.execute(
        """
        SELECT strategy, capital_weight_pct
        FROM strategy_performance
        WHERE id IN (
            SELECT MAX(id) FROM strategy_performance GROUP BY strategy
        )
        """
    )
    weight_rows = await weight_cursor.fetchall()
    weights = {row["strategy"]: row["capital_weight_pct"] for row in weight_rows}

    strategies: list[StrategyMetricsSchema] = []
    seen = set()
    for row in rows:
        strat = row["strategy"]
        seen.add(strat)
        total = row["total"] or 0
        wins = row["wins"] or 0
        losses = row["losses"] or 0
        avg_win = row["avg_win"] or 0.0
        avg_loss = row["avg_loss"] or 0.0
        win_rate = (wins / total * 100) if total > 0 else 0.0
        expectancy = (win_rate / 100 * avg_win) + ((1 - win_rate / 100) * avg_loss)
        strategies.append(
            StrategyMetricsSchema(
                strategy=strat,
                total_signals=signal_counts.get(strat, 0),
                total_trades=total,
                wins=wins,
                losses=losses,
                win_rate=round(win_rate, 2),
                total_pnl=round(row["total_pnl"] or 0.0, 2),
                avg_win=round(avg_win, 2),
                avg_loss=round(avg_loss, 2),
                expectancy=round(expectancy, 2),
                capital_weight_pct=weights.get(strat, 0.0),
            )
        )

    # Include strategies that have signals but no closed trades
    for strat, cnt in signal_counts.items():
        if strat not in seen:
            strategies.append(
                StrategyMetricsSchema(
                    strategy=strat,
                    total_signals=cnt,
                    capital_weight_pct=weights.get(strat, 0.0),
                )
            )

    return StrategyComparisonResponse(strategies=strategies)


@router.get("/confirmed")
async def get_confirmed_performance(
    conn=Depends(get_read_conn),
) -> ConfirmedPerformanceResponse:
    """Compare performance of multi-confirmed vs single-confirmed signals."""
    # Single confirmation signals
    single_cursor = await conn.execute(
        """
        SELECT COUNT(*) as cnt,
               AVG(CASE WHEN t.pnl_amount > 0 THEN 1.0 ELSE 0.0 END) * 100 as win_rate,
               AVG(t.pnl_amount) as avg_pnl
        FROM signals s
        JOIN trades t ON t.signal_id = s.id
        WHERE t.exited_at IS NOT NULL
          AND (s.confirmation_level IS NULL OR s.confirmation_level = 'single')
        """
    )
    single = await single_cursor.fetchone()

    # Multi confirmation signals
    multi_cursor = await conn.execute(
        """
        SELECT COUNT(*) as cnt,
               AVG(CASE WHEN t.pnl_amount > 0 THEN 1.0 ELSE 0.0 END) * 100 as win_rate,
               AVG(t.pnl_amount) as avg_pnl
        FROM signals s
        JOIN trades t ON t.signal_id = s.id
        WHERE t.exited_at IS NOT NULL
          AND s.confirmation_level IN ('double', 'triple')
        """
    )
    multi = await multi_cursor.fetchone()

    return ConfirmedPerformanceResponse(
        single_signals=single["cnt"] or 0,
        single_win_rate=round(single["win_rate"] or 0.0, 2),
        single_avg_pnl=round(single["avg_pnl"] or 0.0, 2),
        multi_signals=multi["cnt"] or 0,
        multi_win_rate=round(multi["win_rate"] or 0.0, 2),
        multi_avg_pnl=round(multi["avg_pnl"] or 0.0, 2),
    )


@router.get("/pnl-series")
async def get_strategy_pnl_series(
    conn=Depends(get_read_conn),
    days: int = Query(30, ge=1, le=365),
) -> StrategyPnlSeriesResponse:
    """Return daily P&L broken out by strategy."""
    cursor = await conn.execute(
        """
        SELECT date, strategy, COALESCE(SUM(pnl_amount), 0) as pnl
        FROM trades
        WHERE exited_at IS NOT NULL
        GROUP BY date, strategy
        ORDER BY date DESC
        LIMIT ?
        """,
        (days * 3,),  # up to 3 strategies per day
    )
    rows = await cursor.fetchall()

    data = [
        StrategyPnlSeriesPoint(date=row["date"], strategy=row["strategy"], pnl=round(row["pnl"], 2))
        for row in reversed(rows)
    ]

    return StrategyPnlSeriesResponse(data=data)
