"""Trades API routes."""

from __future__ import annotations

import csv
import io
import math

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from signalpilot.dashboard.deps import get_read_conn
from signalpilot.dashboard.schemas import (
    PaginationInfo,
    TradeItem,
    TradesResponse,
    TradeSummarySchema,
)

router = APIRouter()


def _row_to_trade_item(row) -> TradeItem:
    """Convert a database row to a TradeItem schema."""
    return TradeItem(
        id=row["id"],
        signal_id=row["signal_id"],
        symbol=row["symbol"],
        strategy=row["strategy"] if "strategy" in row.keys() else "gap_go",
        entry_price=row["entry_price"],
        exit_price=row["exit_price"],
        stop_loss=row["stop_loss"],
        target_1=row["target_1"],
        target_2=row["target_2"],
        quantity=row["quantity"],
        pnl_amount=row["pnl_amount"],
        pnl_pct=row["pnl_pct"],
        exit_reason=row["exit_reason"],
        date=row["date"],
        taken_at=row["taken_at"] or "",
        exited_at=row["exited_at"],
    )


@router.get("")
async def get_trades(
    conn=Depends(get_read_conn),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    strategy: str | None = Query(None),
    status: str | None = Query(None, description="open or closed"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
) -> TradesResponse:
    """Return paginated, filterable trade list with summary statistics."""
    conditions: list[str] = []
    params: list = []

    if date_from:
        conditions.append("date >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("date <= ?")
        params.append(date_to)
    if strategy:
        conditions.append("strategy = ?")
        params.append(strategy)
    if status == "open":
        conditions.append("exited_at IS NULL")
    elif status == "closed":
        conditions.append("exited_at IS NOT NULL")

    where = " AND ".join(conditions) if conditions else "1=1"

    # Total count
    count_cursor = await conn.execute(
        f"SELECT COUNT(*) FROM trades WHERE {where}", params
    )
    total_row = await count_cursor.fetchone()
    total_items = total_row[0]
    total_pages = max(1, math.ceil(total_items / page_size))

    # Paginated results
    offset = (page - 1) * page_size
    cursor = await conn.execute(
        f"SELECT * FROM trades WHERE {where} ORDER BY taken_at DESC LIMIT ? OFFSET ?",
        params + [page_size, offset],
    )
    rows = await cursor.fetchall()
    trades = [_row_to_trade_item(row) for row in rows]

    # Summary: computed over the full filtered set (not just the page)
    summary_cursor = await conn.execute(
        f"""SELECT
                COUNT(*) as total,
                SUM(CASE WHEN exited_at IS NULL THEN 1 ELSE 0 END) as open_count,
                SUM(CASE WHEN exited_at IS NOT NULL THEN 1 ELSE 0 END) as closed_count,
                COALESCE(SUM(CASE WHEN exited_at IS NOT NULL THEN pnl_amount ELSE 0 END), 0) as total_pnl,
                SUM(CASE WHEN exited_at IS NOT NULL AND pnl_amount > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN exited_at IS NOT NULL AND pnl_amount <= 0 THEN 1 ELSE 0 END) as losses,
                COALESCE(MAX(CASE WHEN exited_at IS NOT NULL THEN pnl_amount END), 0) as best_pnl,
                COALESCE(MIN(CASE WHEN exited_at IS NOT NULL THEN pnl_amount END), 0) as worst_pnl
            FROM trades WHERE {where}""",
        params,
    )
    srow = await summary_cursor.fetchone()
    total_trades = srow["total"] or 0
    closed_count = srow["closed_count"] or 0
    wins = srow["wins"] or 0
    losses = srow["losses"] or 0
    win_rate = (wins / closed_count * 100) if closed_count > 0 else 0.0

    summary = TradeSummarySchema(
        total_trades=total_trades,
        open_trades=srow["open_count"] or 0,
        closed_trades=closed_count,
        total_pnl=srow["total_pnl"] or 0.0,
        wins=wins,
        losses=losses,
        win_rate=round(win_rate, 2),
        best_trade_pnl=srow["best_pnl"] or 0.0,
        worst_trade_pnl=srow["worst_pnl"] or 0.0,
    )

    return TradesResponse(
        trades=trades,
        summary=summary,
        pagination=PaginationInfo(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
        ),
    )


@router.get("/export")
async def export_trades_csv(
    conn=Depends(get_read_conn),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    strategy: str | None = Query(None),
):
    """Export trades as a CSV file download."""
    conditions: list[str] = []
    params: list = []

    if date_from:
        conditions.append("date >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("date <= ?")
        params.append(date_to)
    if strategy:
        conditions.append("strategy = ?")
        params.append(strategy)

    where = " AND ".join(conditions) if conditions else "1=1"

    cursor = await conn.execute(
        f"SELECT * FROM trades WHERE {where} ORDER BY taken_at DESC", params
    )
    rows = await cursor.fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id", "symbol", "strategy", "entry_price", "exit_price",
        "stop_loss", "target_1", "target_2", "quantity",
        "pnl_amount", "pnl_pct", "exit_reason", "date", "taken_at", "exited_at",
    ])
    for row in rows:
        writer.writerow([
            row["id"], row["symbol"],
            row["strategy"] if "strategy" in row.keys() else "gap_go",
            row["entry_price"], row["exit_price"],
            row["stop_loss"], row["target_1"], row["target_2"], row["quantity"],
            row["pnl_amount"], row["pnl_pct"], row["exit_reason"],
            row["date"], row["taken_at"], row["exited_at"],
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=trades.csv"},
    )
