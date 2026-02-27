"""Settings API routes -- read/update user configuration."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from signalpilot.dashboard.deps import get_config_repo, get_write_conn
from signalpilot.dashboard.schemas import (
    SettingsResponse,
    SettingsUpdateRequest,
    StrategyToggleRequest,
)
from signalpilot.db.config_repo import ConfigRepository

router = APIRouter()


@router.get("")
async def get_settings(
    config_repo=Depends(get_config_repo),
) -> SettingsResponse:
    """Return current user settings."""
    config = await config_repo.get_user_config()
    if config is None:
        return SettingsResponse()

    return SettingsResponse(
        total_capital=config.total_capital,
        max_positions=config.max_positions,
        gap_go_enabled=config.gap_go_enabled,
        orb_enabled=config.orb_enabled,
        vwap_enabled=config.vwap_enabled,
        circuit_breaker_limit=config.circuit_breaker_limit,
        confidence_boost_enabled=config.confidence_boost_enabled,
        adaptive_learning_enabled=config.adaptive_learning_enabled,
        auto_rebalance_enabled=config.auto_rebalance_enabled,
        adaptation_mode=config.adaptation_mode,
    )


@router.put("")
async def update_settings(
    body: SettingsUpdateRequest,
    write_conn=Depends(get_write_conn),
):
    """Update general settings (requires write connection)."""
    if write_conn is None:
        raise HTTPException(status_code=503, detail="Write connection not available")

    config_repo = ConfigRepository(write_conn)

    if body.total_capital is not None:
        await config_repo.update_capital(body.total_capital)
    if body.max_positions is not None:
        await config_repo.update_max_positions(body.max_positions)

    # Phase 3 fields
    phase3_updates = {}
    if body.circuit_breaker_limit is not None:
        phase3_updates["circuit_breaker_limit"] = body.circuit_breaker_limit
    if body.confidence_boost_enabled is not None:
        phase3_updates["confidence_boost_enabled"] = body.confidence_boost_enabled
    if body.adaptive_learning_enabled is not None:
        phase3_updates["adaptive_learning_enabled"] = body.adaptive_learning_enabled
    if body.auto_rebalance_enabled is not None:
        phase3_updates["auto_rebalance_enabled"] = body.auto_rebalance_enabled
    if body.adaptation_mode is not None:
        phase3_updates["adaptation_mode"] = body.adaptation_mode

    if phase3_updates:
        await config_repo.update_user_config(**phase3_updates)

    return {"ok": True}


@router.put("/strategies")
async def update_strategy_toggles(
    body: StrategyToggleRequest,
    write_conn=Depends(get_write_conn),
):
    """Toggle strategies on/off (requires write connection)."""
    if write_conn is None:
        raise HTTPException(status_code=503, detail="Write connection not available")

    config_repo = ConfigRepository(write_conn)

    if body.gap_go_enabled is not None:
        await config_repo.set_strategy_enabled("gap_go_enabled", body.gap_go_enabled)
    if body.orb_enabled is not None:
        await config_repo.set_strategy_enabled("orb_enabled", body.orb_enabled)
    if body.vwap_enabled is not None:
        await config_repo.set_strategy_enabled("vwap_enabled", body.vwap_enabled)

    return {"ok": True}
