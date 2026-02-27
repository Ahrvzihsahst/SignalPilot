"""Circuit Breaker API routes."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from signalpilot.dashboard.deps import get_circuit_breaker_repo, get_config_repo, get_write_conn
from signalpilot.dashboard.schemas import (
    CircuitBreakerDetailResponse,
    CircuitBreakerHistoryItem,
    CircuitBreakerHistoryResponse,
    CircuitBreakerOverrideRequest,
)
from signalpilot.db.circuit_breaker_repo import CircuitBreakerRepository
from signalpilot.utils.constants import IST

router = APIRouter()


@router.get("")
async def get_circuit_breaker_status(
    cb_repo=Depends(get_circuit_breaker_repo),
    config_repo=Depends(get_config_repo),
) -> CircuitBreakerDetailResponse:
    """Return today's circuit breaker status."""
    today = datetime.now(IST).date()
    record = await cb_repo.get_today_status(today)
    config = await config_repo.get_user_config()
    sl_limit = config.circuit_breaker_limit if config else 3

    if record is None:
        return CircuitBreakerDetailResponse(
            date=today.isoformat(),
            sl_count=0,
            sl_limit=sl_limit,
            is_active=False,
            is_overridden=False,
        )

    is_active = record.triggered_at is not None and record.resumed_at is None
    is_overridden = record.manual_override

    return CircuitBreakerDetailResponse(
        date=record.date.isoformat(),
        sl_count=record.sl_count,
        sl_limit=sl_limit,
        is_active=is_active and not is_overridden,
        is_overridden=is_overridden,
        triggered_at=record.triggered_at.isoformat() if record.triggered_at else None,
        resumed_at=record.resumed_at.isoformat() if record.resumed_at else None,
        override_at=record.override_at.isoformat() if record.override_at else None,
    )


@router.post("/override")
async def override_circuit_breaker(
    body: CircuitBreakerOverrideRequest,
    write_conn=Depends(get_write_conn),
):
    """Override (resume) or reset the circuit breaker for today."""
    if write_conn is None:
        raise HTTPException(status_code=503, detail="Write connection not available")

    today = datetime.now(IST).date()
    now = datetime.now(IST)
    cb_repo = CircuitBreakerRepository(write_conn)

    if body.action == "override":
        await cb_repo.log_override(today, now)
        return {"ok": True, "action": "override"}
    elif body.action == "reset":
        await cb_repo.log_resume(today, now)
        return {"ok": True, "action": "reset"}

    raise HTTPException(status_code=400, detail="Invalid action")


@router.get("/history")
async def get_circuit_breaker_history(
    cb_repo=Depends(get_circuit_breaker_repo),
    limit: int = Query(30, ge=1, le=100),
) -> CircuitBreakerHistoryResponse:
    """Return recent circuit breaker events."""
    records = await cb_repo.get_history(limit)

    data = [
        CircuitBreakerHistoryItem(
            date=r.date.isoformat(),
            sl_count=r.sl_count,
            triggered_at=r.triggered_at.isoformat() if r.triggered_at else None,
            resumed_at=r.resumed_at.isoformat() if r.resumed_at else None,
            manual_override=r.manual_override,
            override_at=r.override_at.isoformat() if r.override_at else None,
        )
        for r in records
    ]

    return CircuitBreakerHistoryResponse(data=data)
