"""Allocation API routes -- capital allocation across strategies."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from signalpilot.dashboard.deps import get_config_repo, get_read_conn, get_write_conn
from signalpilot.dashboard.schemas import (
    AllocationHistoryItem,
    AllocationHistoryResponse,
    AllocationItem,
    AllocationOverrideRequest,
    AllocationResponse,
)
from signalpilot.utils.constants import IST

router = APIRouter()

_DEFAULT_STRATEGIES = ["gap_go", "ORB", "VWAP Reversal"]


@router.get("/current")
async def get_current_allocation(
    conn=Depends(get_read_conn),
    config_repo=Depends(get_config_repo),
) -> AllocationResponse:
    """Return the current capital allocation per strategy."""
    config = await config_repo.get_user_config()
    total_capital = config.total_capital if config else 50000.0

    # Get latest weights from strategy_performance
    cursor = await conn.execute(
        """
        SELECT strategy, capital_weight_pct
        FROM strategy_performance
        WHERE id IN (
            SELECT MAX(id) FROM strategy_performance GROUP BY strategy
        )
        """
    )
    rows = await cursor.fetchall()
    weights = {row["strategy"]: row["capital_weight_pct"] for row in rows}

    # If no performance data yet, distribute equally among default strategies
    if not weights:
        equal_weight = round(100.0 / len(_DEFAULT_STRATEGIES), 2)
        weights = {s: equal_weight for s in _DEFAULT_STRATEGIES}

    allocations = [
        AllocationItem(
            strategy=strat,
            weight_pct=round(w, 2),
            capital_allocated=round(total_capital * w / 100, 2),
        )
        for strat, w in weights.items()
    ]

    return AllocationResponse(total_capital=total_capital, allocations=allocations)


@router.get("/history")
async def get_allocation_history(
    conn=Depends(get_read_conn),
    days: int = Query(30, ge=1, le=365),
) -> AllocationHistoryResponse:
    """Return allocation weight changes over time from strategy_performance."""
    cursor = await conn.execute(
        """
        SELECT date, strategy, capital_weight_pct
        FROM strategy_performance
        ORDER BY date DESC
        LIMIT ?
        """,
        (days * 3,),
    )
    rows = await cursor.fetchall()

    data = [
        AllocationHistoryItem(
            date=row["date"],
            strategy=row["strategy"],
            weight_pct=round(row["capital_weight_pct"], 2),
        )
        for row in reversed(rows)
    ]

    return AllocationHistoryResponse(data=data)


@router.post("/override")
async def override_allocation(
    body: AllocationOverrideRequest,
    write_conn=Depends(get_write_conn),
):
    """Manually override allocation weight for a strategy.

    Requires a write connection shared from the main application.
    """
    if write_conn is None:
        raise HTTPException(status_code=503, detail="Write connection not available")

    now = datetime.now(IST)
    # Upsert into strategy_performance for today
    await write_conn.execute(
        """
        INSERT INTO strategy_performance (strategy, date, capital_weight_pct)
        VALUES (?, ?, ?)
        ON CONFLICT(strategy, date) DO UPDATE SET capital_weight_pct = excluded.capital_weight_pct
        """,
        (body.strategy, now.date().isoformat(), body.weight_pct),
    )
    await write_conn.commit()
    return {"ok": True, "strategy": body.strategy, "weight_pct": body.weight_pct}


@router.post("/reset")
async def reset_allocation(
    write_conn=Depends(get_write_conn),
):
    """Reset allocation weights to equal distribution."""
    if write_conn is None:
        raise HTTPException(status_code=503, detail="Write connection not available")

    now = datetime.now(IST)
    today = now.date().isoformat()
    equal_weight = round(100.0 / len(_DEFAULT_STRATEGIES), 2)

    for strat in _DEFAULT_STRATEGIES:
        await write_conn.execute(
            """
            INSERT INTO strategy_performance (strategy, date, capital_weight_pct)
            VALUES (?, ?, ?)
            ON CONFLICT(strategy, date) DO UPDATE SET capital_weight_pct = excluded.capital_weight_pct
            """,
            (strat, today, equal_weight),
        )
    await write_conn.commit()
    return {"ok": True, "weight_pct": equal_weight}
