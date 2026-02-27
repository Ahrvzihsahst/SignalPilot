"""Adaptation API routes -- adaptive learning status and log."""

from __future__ import annotations

import math

from fastapi import APIRouter, Depends, Query

from signalpilot.dashboard.deps import get_config_repo, get_read_conn
from signalpilot.dashboard.schemas import (
    AdaptationLogItem,
    AdaptationLogResponse,
    AdaptationStatusResponse,
    AdaptationStrategyStatus,
    PaginationInfo,
)

router = APIRouter()


@router.get("/status")
async def get_adaptation_status(
    conn=Depends(get_read_conn),
    config_repo=Depends(get_config_repo),
) -> AdaptationStatusResponse:
    """Return adaptation mode and per-strategy status."""
    config = await config_repo.get_user_config()

    mode = config.adaptation_mode if config else "aggressive"
    auto_rebalance = config.auto_rebalance_enabled if config else True
    adaptive_learning = config.adaptive_learning_enabled if config else True

    # Get latest weight and win rate per strategy from strategy_performance
    cursor = await conn.execute(
        """
        SELECT sp.strategy, sp.capital_weight_pct, sp.win_rate
        FROM strategy_performance sp
        WHERE sp.id IN (
            SELECT MAX(id) FROM strategy_performance GROUP BY strategy
        )
        """
    )
    rows = await cursor.fetchall()

    strategy_map = {
        "gap_go": config.gap_go_enabled if config else True,
        "ORB": config.orb_enabled if config else True,
        "VWAP Reversal": config.vwap_enabled if config else True,
    }

    strategies: list[AdaptationStrategyStatus] = []
    seen = set()
    for row in rows:
        strat = row["strategy"]
        seen.add(strat)
        strategies.append(
            AdaptationStrategyStatus(
                strategy=strat,
                enabled=strategy_map.get(strat, True),
                current_weight_pct=round(row["capital_weight_pct"], 2),
                recent_win_rate=round(row["win_rate"], 2),
                adaptation_status="normal",
            )
        )

    # Include strategies without performance data
    for strat, enabled in strategy_map.items():
        if strat not in seen:
            strategies.append(
                AdaptationStrategyStatus(strategy=strat, enabled=enabled)
            )

    return AdaptationStatusResponse(
        mode=mode,
        auto_rebalance_enabled=auto_rebalance,
        adaptive_learning_enabled=adaptive_learning,
        strategies=strategies,
    )


@router.get("/log")
async def get_adaptation_log(
    conn=Depends(get_read_conn),
    strategy: str | None = Query(None),
    event_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
) -> AdaptationLogResponse:
    """Return paginated adaptation log entries."""
    conditions: list[str] = []
    params: list = []

    if strategy:
        conditions.append("strategy = ?")
        params.append(strategy)
    if event_type:
        conditions.append("event_type = ?")
        params.append(event_type)

    where = " AND ".join(conditions) if conditions else "1=1"

    # Count
    count_cursor = await conn.execute(
        f"SELECT COUNT(*) FROM adaptation_log WHERE {where}", params
    )
    total_row = await count_cursor.fetchone()
    total_items = total_row[0]
    total_pages = max(1, math.ceil(total_items / page_size))

    offset = (page - 1) * page_size
    cursor = await conn.execute(
        f"""SELECT * FROM adaptation_log WHERE {where}
            ORDER BY created_at DESC LIMIT ? OFFSET ?""",
        params + [page_size, offset],
    )
    rows = await cursor.fetchall()

    data = [
        AdaptationLogItem(
            id=row["id"],
            date=row["date"],
            strategy=row["strategy"],
            event_type=row["event_type"],
            details=row["details"] or "",
            old_weight=row["old_weight"],
            new_weight=row["new_weight"],
            created_at=row["created_at"] or "",
        )
        for row in rows
    ]

    return AdaptationLogResponse(
        data=data,
        pagination=PaginationInfo(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
        ),
    )
