"""Signals API routes."""

from __future__ import annotations

import math
from datetime import datetime

from fastapi import APIRouter, Depends, Query

from signalpilot.dashboard.deps import get_config_repo, get_read_conn, get_signal_repo
from signalpilot.dashboard.schemas import (
    CircuitBreakerStatus,
    LiveSignalsResponse,
    PaginationInfo,
    SignalHistoryResponse,
    SignalItem,
)
from signalpilot.utils.constants import IST

router = APIRouter()


def _row_to_signal_item(row, rank: int) -> SignalItem:
    """Convert a database row to a SignalItem schema."""
    return SignalItem(
        id=row["id"],
        rank=rank,
        symbol=row["symbol"],
        strategy=row["strategy"],
        entry_price=row["entry_price"],
        stop_loss=row["stop_loss"],
        target_1=row["target_1"],
        target_2=row["target_2"],
        quantity=row["quantity"] or 0,
        capital_required=row["capital_required"] or 0,
        signal_strength=row["signal_strength"] or 0,
        composite_score=row["composite_score"] if "composite_score" in row.keys() else None,
        confirmation_level=(
            row["confirmation_level"]
            if "confirmation_level" in row.keys() and row["confirmation_level"]
            else "single"
        ),
        confirmed_by=row["confirmed_by"] if "confirmed_by" in row.keys() else None,
        position_size_multiplier=(
            row["position_size_multiplier"]
            if "position_size_multiplier" in row.keys()
            and row["position_size_multiplier"] is not None
            else 1.0
        ),
        status=row["status"],
        current_price=None,
        pnl_amount=None,
        pnl_pct=None,
        reason=row["reason"] or "",
        setup_type=row["setup_type"] if "setup_type" in row.keys() else None,
        adaptation_status=(
            row["adaptation_status"]
            if "adaptation_status" in row.keys() and row["adaptation_status"]
            else "normal"
        ),
        created_at=row["created_at"] or "",
    )


@router.get("/live")
async def get_live_signals(
    signal_repo=Depends(get_signal_repo),
    config_repo=Depends(get_config_repo),
) -> LiveSignalsResponse:
    """Return today's signals split into active and expired, plus market context."""
    now = datetime.now(IST)
    today = now.date()

    conn = signal_repo._conn
    cursor = await conn.execute(
        """SELECT * FROM signals WHERE date = ?
           ORDER BY composite_score DESC NULLS LAST, created_at DESC""",
        (today.isoformat(),),
    )
    rows = await cursor.fetchall()

    active_signals: list[SignalItem] = []
    expired_signals: list[SignalItem] = []
    for i, row in enumerate(rows):
        item = _row_to_signal_item(row, rank=i + 1)
        if row["status"] in ("expired", "position_full"):
            expired_signals.append(item)
        else:
            active_signals.append(item)

    # User config for capital / positions
    config = await config_repo.get_user_config()

    # Count taken positions today (open trades)
    cursor2 = await conn.execute(
        "SELECT COUNT(*) FROM trades WHERE date = ? AND exited_at IS NULL",
        (today.isoformat(),),
    )
    row2 = await cursor2.fetchone()
    positions_used = row2[0] if row2 else 0

    # Today's P&L from closed trades
    cursor3 = await conn.execute(
        "SELECT COALESCE(SUM(pnl_amount), 0) FROM trades WHERE date = ? AND exited_at IS NOT NULL",
        (today.isoformat(),),
    )
    row3 = await cursor3.fetchone()
    today_pnl = row3[0] if row3 else 0.0

    total_capital = config.total_capital if config else 50000.0
    today_pnl_pct = (today_pnl / total_capital * 100) if total_capital > 0 else 0.0

    # Market status based on IST time
    hour = now.hour
    minute = now.minute
    market_open = 9 * 60 + 15
    market_close = 15 * 60 + 30
    current_minutes = hour * 60 + minute
    market_status = "open" if market_open <= current_minutes <= market_close else "closed"

    # Simple circuit breaker status
    cb_status = CircuitBreakerStatus(
        sl_count=0,
        sl_limit=config.circuit_breaker_limit if config else 3,
        is_active=False,
        is_overridden=False,
        triggered_at=None,
    )

    return LiveSignalsResponse(
        market_status=market_status,
        current_time=now.isoformat(),
        capital=total_capital,
        positions_used=positions_used,
        positions_max=config.max_positions if config else 8,
        today_pnl=today_pnl,
        today_pnl_pct=round(today_pnl_pct, 2),
        circuit_breaker=cb_status,
        active_signals=active_signals,
        expired_signals=expired_signals,
    )


@router.get("/history")
async def get_signal_history(
    conn=Depends(get_read_conn),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    strategy: str | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
) -> SignalHistoryResponse:
    """Return paginated, filterable signal history."""
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
    if status:
        conditions.append("status = ?")
        params.append(status)

    where = " AND ".join(conditions) if conditions else "1=1"

    # Total count
    count_cursor = await conn.execute(
        f"SELECT COUNT(*) FROM signals WHERE {where}", params
    )
    total_row = await count_cursor.fetchone()
    total_items = total_row[0]
    total_pages = max(1, math.ceil(total_items / page_size))

    offset = (page - 1) * page_size
    cursor = await conn.execute(
        f"SELECT * FROM signals WHERE {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params + [page_size, offset],
    )
    rows = await cursor.fetchall()

    signals = [_row_to_signal_item(row, rank=offset + i + 1) for i, row in enumerate(rows)]

    return SignalHistoryResponse(
        signals=signals,
        pagination=PaginationInfo(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
        ),
    )
