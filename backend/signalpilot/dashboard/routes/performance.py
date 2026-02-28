"""Performance API routes -- equity curve, daily P&L, win rate, monthly summary."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from signalpilot.dashboard.deps import get_read_conn
from signalpilot.dashboard.schemas import (
    DailyPnlPoint,
    DailyPnlResponse,
    EquityCurvePoint,
    EquityCurveResponse,
    MonthlySummaryResponse,
    MonthlySummaryRow,
    WinRatePoint,
    WinRateResponse,
)

router = APIRouter()


@router.get("/equity-curve")
async def get_equity_curve(
    conn=Depends(get_read_conn),
    days: int = Query(30, ge=1, le=365),
) -> EquityCurveResponse:
    """Return cumulative P&L per day for the equity curve chart."""
    cursor = await conn.execute(
        """
        SELECT date, COALESCE(SUM(pnl_amount), 0) as daily_pnl
        FROM trades
        WHERE exited_at IS NOT NULL
        GROUP BY date
        ORDER BY date DESC
        LIMIT ?
        """,
        (days,),
    )
    rows = await cursor.fetchall()
    rows = list(reversed(rows))  # oldest first for cumulative calc

    cumulative = 0.0
    data: list[EquityCurvePoint] = []
    for row in rows:
        cumulative += row["daily_pnl"]
        data.append(EquityCurvePoint(date=row["date"], cumulative_pnl=round(cumulative, 2)))

    return EquityCurveResponse(data=data)


@router.get("/daily-pnl")
async def get_daily_pnl(
    conn=Depends(get_read_conn),
    days: int = Query(30, ge=1, le=365),
) -> DailyPnlResponse:
    """Return per-day P&L and trade count."""
    cursor = await conn.execute(
        """
        SELECT date,
               COALESCE(SUM(pnl_amount), 0) as pnl,
               COUNT(*) as trades_count
        FROM trades
        WHERE exited_at IS NOT NULL
        GROUP BY date
        ORDER BY date DESC
        LIMIT ?
        """,
        (days,),
    )
    rows = await cursor.fetchall()

    data = [
        DailyPnlPoint(date=row["date"], pnl=round(row["pnl"], 2), trades_count=row["trades_count"])
        for row in reversed(rows)
    ]

    return DailyPnlResponse(data=data)


@router.get("/win-rate")
async def get_win_rate(
    conn=Depends(get_read_conn),
    days: int = Query(30, ge=1, le=365),
) -> WinRateResponse:
    """Return per-day win rate (rolling by date)."""
    cursor = await conn.execute(
        """
        SELECT date,
               COUNT(*) as trades_count,
               SUM(CASE WHEN pnl_amount > 0 THEN 1 ELSE 0 END) as wins
        FROM trades
        WHERE exited_at IS NOT NULL
        GROUP BY date
        ORDER BY date DESC
        LIMIT ?
        """,
        (days,),
    )
    rows = await cursor.fetchall()

    data = [
        WinRatePoint(
            date=row["date"],
            win_rate=round((row["wins"] / row["trades_count"]) * 100, 2)
            if row["trades_count"] > 0
            else 0.0,
            trades_count=row["trades_count"],
        )
        for row in reversed(rows)
    ]

    return WinRateResponse(data=data)


@router.get("/monthly")
async def get_monthly_summary(
    conn=Depends(get_read_conn),
) -> MonthlySummaryResponse:
    """Return per-month aggregated trade statistics."""
    cursor = await conn.execute(
        """
        SELECT
            SUBSTR(date, 1, 7) as month,
            COALESCE(SUM(pnl_amount), 0) as total_pnl,
            COUNT(*) as trades_count,
            SUM(CASE WHEN pnl_amount > 0 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN pnl_amount <= 0 THEN 1 ELSE 0 END) as losses
        FROM trades
        WHERE exited_at IS NOT NULL
        GROUP BY month
        ORDER BY month
        """
    )
    rows = await cursor.fetchall()

    data = [
        MonthlySummaryRow(
            month=row["month"],
            total_pnl=round(row["total_pnl"], 2),
            trades_count=row["trades_count"],
            wins=row["wins"] or 0,
            losses=row["losses"] or 0,
            win_rate=round((row["wins"] / row["trades_count"]) * 100, 2)
            if row["trades_count"] > 0
            else 0.0,
        )
        for row in rows
    ]

    return MonthlySummaryResponse(data=data)
