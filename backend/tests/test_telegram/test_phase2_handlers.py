"""Tests for Phase 2 Telegram command handlers (PAUSE, RESUME, ALLOCATE, STRATEGY)."""

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

from signalpilot.db.models import StrategyPerformanceRecord, UserConfig
from signalpilot.telegram.handlers import (
    handle_allocate,
    handle_pause,
    handle_resume,
    handle_strategy,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _AllocationResult:
    """Lightweight stand-in for capital allocator allocation output."""

    strategy_name: str
    weight_pct: float
    allocated_capital: float
    max_positions: int


def _make_user_config(
    total_capital: float = 100_000.0,
    max_positions: int = 8,
) -> UserConfig:
    return UserConfig(
        id=1,
        telegram_chat_id="123",
        total_capital=total_capital,
        max_positions=max_positions,
    )


# ========================================================================
# handle_pause
# ========================================================================


@pytest.mark.asyncio
async def test_pause_orb() -> None:
    """PAUSE ORB -> pauses ORB strategy, returns confirmation."""
    config_repo = AsyncMock()
    config_repo.get_strategy_enabled.return_value = True
    config_repo.set_strategy_enabled = AsyncMock()

    result = await handle_pause(config_repo, "pause orb")

    assert "ORB paused" in result
    assert "No signals will be generated" in result
    config_repo.set_strategy_enabled.assert_called_once_with("orb_enabled", False)


@pytest.mark.asyncio
async def test_pause_gap() -> None:
    """PAUSE GAP -> pauses Gap & Go strategy."""
    config_repo = AsyncMock()
    config_repo.get_strategy_enabled.return_value = True
    config_repo.set_strategy_enabled = AsyncMock()

    result = await handle_pause(config_repo, "pause gap")

    assert "Gap & Go paused" in result
    config_repo.set_strategy_enabled.assert_called_once_with("gap_go_enabled", False)


@pytest.mark.asyncio
async def test_pause_vwap() -> None:
    """PAUSE VWAP -> pauses VWAP Reversal strategy."""
    config_repo = AsyncMock()
    config_repo.get_strategy_enabled.return_value = True
    config_repo.set_strategy_enabled = AsyncMock()

    result = await handle_pause(config_repo, "pause vwap")

    assert "VWAP Reversal paused" in result
    config_repo.set_strategy_enabled.assert_called_once_with("vwap_enabled", False)


@pytest.mark.asyncio
async def test_pause_already_paused() -> None:
    """PAUSE ORB when ORB is already paused -> 'already paused' message."""
    config_repo = AsyncMock()
    config_repo.get_strategy_enabled.return_value = False  # Already paused

    result = await handle_pause(config_repo, "pause orb")

    assert "already paused" in result


@pytest.mark.asyncio
async def test_pause_unknown_strategy() -> None:
    """PAUSE MACD -> error for unknown strategy."""
    config_repo = AsyncMock()

    result = await handle_pause(config_repo, "pause macd")

    assert "Unknown strategy" in result
    assert "MACD" in result


@pytest.mark.asyncio
async def test_pause_missing_strategy() -> None:
    """PAUSE (no strategy) -> usage instructions."""
    config_repo = AsyncMock()

    result = await handle_pause(config_repo, "pause")

    assert "Usage:" in result
    assert "PAUSE" in result


# ========================================================================
# handle_resume
# ========================================================================


@pytest.mark.asyncio
async def test_resume_orb() -> None:
    """RESUME ORB -> resumes ORB strategy, returns confirmation."""
    config_repo = AsyncMock()
    config_repo.get_strategy_enabled.return_value = False  # Currently paused
    config_repo.set_strategy_enabled = AsyncMock()

    result = await handle_resume(config_repo, "resume orb")

    assert "ORB resumed" in result
    assert "Signals will be generated" in result
    config_repo.set_strategy_enabled.assert_called_once_with("orb_enabled", True)


@pytest.mark.asyncio
async def test_resume_already_active() -> None:
    """RESUME ORB when already active -> 'already active' message."""
    config_repo = AsyncMock()
    config_repo.get_strategy_enabled.return_value = True  # Already active

    result = await handle_resume(config_repo, "resume orb")

    assert "already active" in result


@pytest.mark.asyncio
async def test_resume_unknown_strategy() -> None:
    """RESUME MACD -> error for unknown strategy."""
    config_repo = AsyncMock()

    result = await handle_resume(config_repo, "resume macd")

    assert "Unknown strategy" in result
    assert "MACD" in result


@pytest.mark.asyncio
async def test_resume_missing_strategy() -> None:
    """RESUME (no strategy) -> usage instructions."""
    config_repo = AsyncMock()

    result = await handle_resume(config_repo, "resume")

    assert "Usage:" in result
    assert "RESUME" in result


# ========================================================================
# handle_allocate
# ========================================================================


@pytest.mark.asyncio
async def test_allocate_show_current() -> None:
    """ALLOCATE alone -> shows current allocation from capital_allocator."""
    config_repo = AsyncMock()
    config_repo.get_user_config.return_value = _make_user_config()

    capital_allocator = AsyncMock()
    capital_allocator.calculate_allocations.return_value = {
        "Gap & Go": _AllocationResult(
            strategy_name="Gap & Go",
            weight_pct=40.0,
            allocated_capital=40_000.0,
            max_positions=3,
        ),
        "ORB": _AllocationResult(
            strategy_name="ORB",
            weight_pct=20.0,
            allocated_capital=20_000.0,
            max_positions=2,
        ),
        "VWAP Reversal": _AllocationResult(
            strategy_name="VWAP Reversal",
            weight_pct=20.0,
            allocated_capital=20_000.0,
            max_positions=2,
        ),
    }

    result = await handle_allocate(capital_allocator, config_repo, "allocate")

    assert "Current Allocation" in result
    assert "Gap & Go" in result
    assert "ORB" in result
    assert "VWAP Reversal" in result
    assert "40%" in result
    assert "Reserve" in result


@pytest.mark.asyncio
async def test_allocate_manual_valid() -> None:
    """ALLOCATE GAP 40 ORB 20 VWAP 20 -> sets manual allocation (sum=80%)."""
    config_repo = AsyncMock()
    capital_allocator = MagicMock()
    capital_allocator.set_manual_allocation = MagicMock()

    result = await handle_allocate(
        capital_allocator, config_repo, "allocate gap 40 orb 20 vwap 20"
    )

    assert "Manual allocation set" in result
    assert "80%" in result
    assert "reserve" in result.lower()
    capital_allocator.set_manual_allocation.assert_called_once()

    # Verify the weights dict passed
    weights_arg = capital_allocator.set_manual_allocation.call_args[0][0]
    assert weights_arg["Gap & Go"] == pytest.approx(0.40)
    assert weights_arg["ORB"] == pytest.approx(0.20)
    assert weights_arg["VWAP Reversal"] == pytest.approx(0.20)


@pytest.mark.asyncio
async def test_allocate_manual_exceeds_80pct() -> None:
    """ALLOCATE GAP 50 ORB 30 VWAP 20 -> rejects (sum=100% > 80%)."""
    config_repo = AsyncMock()
    capital_allocator = MagicMock()

    result = await handle_allocate(
        capital_allocator, config_repo, "allocate gap 50 orb 30 vwap 20"
    )

    assert "exceeds 80%" in result
    assert "100%" in result


@pytest.mark.asyncio
async def test_allocate_auto() -> None:
    """ALLOCATE AUTO -> re-enables auto allocation."""
    config_repo = AsyncMock()
    capital_allocator = MagicMock()
    capital_allocator.enable_auto_allocation = MagicMock()

    result = await handle_allocate(capital_allocator, config_repo, "allocate auto")

    assert "Auto allocation re-enabled" in result
    capital_allocator.enable_auto_allocation.assert_called_once()


@pytest.mark.asyncio
async def test_allocate_no_capital_allocator() -> None:
    """ALLOCATE when no capital_allocator is configured -> error message."""
    config_repo = AsyncMock()

    result = await handle_allocate(None, config_repo, "allocate")

    assert "not configured" in result.lower()


@pytest.mark.asyncio
async def test_allocate_auto_no_capital_allocator() -> None:
    """ALLOCATE AUTO when no capital_allocator -> error message."""
    config_repo = AsyncMock()

    result = await handle_allocate(None, config_repo, "allocate auto")

    assert "not configured" in result.lower()


# ========================================================================
# handle_strategy
# ========================================================================


@pytest.mark.asyncio
async def test_strategy_with_performance_data() -> None:
    """STRATEGY with performance data -> formatted report."""
    records = [
        StrategyPerformanceRecord(
            strategy="Gap & Go",
            date="2025-01-06",
            signals_generated=5,
            signals_taken=3,
            wins=2,
            losses=1,
            total_pnl=1500.0,
            win_rate=66.7,
            avg_win=900.0,
            avg_loss=-300.0,
            capital_weight_pct=40.0,
        ),
        StrategyPerformanceRecord(
            strategy="ORB",
            date="2025-01-06",
            signals_generated=3,
            signals_taken=2,
            wins=1,
            losses=1,
            total_pnl=200.0,
            win_rate=50.0,
            avg_win=500.0,
            avg_loss=-300.0,
            capital_weight_pct=20.0,
        ),
    ]
    strategy_repo = AsyncMock()
    strategy_repo.get_by_date_range.return_value = records

    result = await handle_strategy(strategy_repo)

    assert "Strategy Performance" in result
    assert "Gap & Go" in result
    assert "ORB" in result
    assert "Win Rate" in result


@pytest.mark.asyncio
async def test_strategy_no_data() -> None:
    """STRATEGY with no data -> 'No strategy performance data available' message."""
    strategy_repo = AsyncMock()
    strategy_repo.get_by_date_range.return_value = []

    result = await handle_strategy(strategy_repo)

    assert "No strategy performance data available" in result


@pytest.mark.asyncio
async def test_strategy_no_repo_configured() -> None:
    """STRATEGY with no repo -> 'not configured' message."""
    result = await handle_strategy(None)

    assert "not configured" in result.lower()
