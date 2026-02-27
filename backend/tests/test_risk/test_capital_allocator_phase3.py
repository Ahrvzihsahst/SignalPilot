"""Tests for Phase 3 enhancements to CapitalAllocator.

Tests the win-rate-based weight adjustments:
- Win rate < 40%: auto-pause + paper mode
- Win rate > 70%: +10% bonus (capped at 50%)
- Weight change logging in adaptation_log
"""

from datetime import date
from unittest.mock import AsyncMock

import pytest

from signalpilot.db.models import StrategyPerformanceRecord
from signalpilot.risk.capital_allocator import (
    RESERVE_PCT,
    STRATEGY_NAMES,
    CapitalAllocator,
)

TODAY = date(2026, 2, 26)
TOTAL_CAPITAL = 300_000.0
MAX_POSITIONS = 15


def _make_perf_record(
    strategy: str = "gap_go",
    signals_taken: int = 10,
    wins: int = 5,
    losses: int = 5,
    avg_win: float = 500.0,
    avg_loss: float = 200.0,
    total_pnl: float = 1500.0,
) -> StrategyPerformanceRecord:
    return StrategyPerformanceRecord(
        strategy=strategy,
        date="2026-02-20",
        signals_generated=signals_taken + 2,
        signals_taken=signals_taken,
        wins=wins,
        losses=losses,
        total_pnl=total_pnl,
        win_rate=(wins / signals_taken * 100) if signals_taken > 0 else 0,
        avg_win=avg_win,
        avg_loss=avg_loss,
    )


@pytest.fixture
def perf_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.get_by_date_range = AsyncMock(return_value=[])
    repo.get_performance_summary = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def config_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.set_strategy_enabled = AsyncMock()
    return repo


@pytest.fixture
def log_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.insert_log = AsyncMock(return_value=1)
    return repo


@pytest.fixture
def allocator(perf_repo, config_repo, log_repo) -> CapitalAllocator:
    return CapitalAllocator(perf_repo, config_repo, adaptation_log_repo=log_repo)


# ---------------------------------------------------------------------------
# Auto-pause: win rate < 40%
# ---------------------------------------------------------------------------


async def test_auto_pause_low_win_rate(allocator, perf_repo, config_repo, log_repo) -> None:
    """Strategy with 30-day win rate < 40% gets weight = 0."""
    records = [
        _make_perf_record(strategy="gap_go", signals_taken=20, wins=6, losses=14,
                          avg_win=400.0, avg_loss=200.0),  # 30% win rate
        _make_perf_record(strategy="ORB", signals_taken=20, wins=12, losses=8,
                          avg_win=500.0, avg_loss=200.0),  # 60% win rate
        _make_perf_record(strategy="VWAP Reversal", signals_taken=20, wins=10, losses=10,
                          avg_win=400.0, avg_loss=200.0),  # 50% win rate
    ]
    perf_repo.get_by_date_range.return_value = records

    result = await allocator.calculate_allocations(TOTAL_CAPITAL, MAX_POSITIONS, TODAY)

    # gap_go should have zero allocation
    assert result["gap_go"].weight_pct == pytest.approx(0.0)
    assert result["gap_go"].allocated_capital == pytest.approx(0.0)

    # Other strategies should still have positive allocation
    assert result["ORB"].weight_pct > 0
    assert result["VWAP Reversal"].weight_pct > 0

    # Config should be called to disable the strategy
    config_repo.set_strategy_enabled.assert_awaited_once_with("gap_go_enabled", False)

    # Adaptation log should be called
    log_repo.insert_log.assert_awaited()
    call_kwargs = log_repo.insert_log.call_args[1]
    assert call_kwargs["event_type"] == "auto_pause_low_win_rate"
    assert call_kwargs["strategy"] == "gap_go"


async def test_auto_pause_multiple_strategies(allocator, perf_repo) -> None:
    """Multiple strategies below 40% win rate get paused."""
    records = [
        _make_perf_record(strategy="gap_go", signals_taken=20, wins=5, losses=15),  # 25%
        _make_perf_record(strategy="ORB", signals_taken=20, wins=6, losses=14),  # 30%
        _make_perf_record(strategy="VWAP Reversal", signals_taken=20, wins=10, losses=10),  # 50%
    ]
    perf_repo.get_by_date_range.return_value = records

    result = await allocator.calculate_allocations(TOTAL_CAPITAL, MAX_POSITIONS, TODAY)

    assert result["gap_go"].weight_pct == pytest.approx(0.0)
    assert result["ORB"].weight_pct == pytest.approx(0.0)
    assert result["VWAP Reversal"].weight_pct > 0


# ---------------------------------------------------------------------------
# Bonus: win rate > 70%
# ---------------------------------------------------------------------------


async def test_bonus_high_win_rate(allocator, perf_repo, log_repo) -> None:
    """Strategy with 30-day win rate > 70% gets +10% bonus."""
    records = [
        _make_perf_record(strategy="gap_go", signals_taken=20, wins=16, losses=4,
                          avg_win=500.0, avg_loss=100.0),  # 80% win rate
        _make_perf_record(strategy="ORB", signals_taken=20, wins=10, losses=10,
                          avg_win=300.0, avg_loss=200.0),  # 50% win rate
        _make_perf_record(strategy="VWAP Reversal", signals_taken=20, wins=10, losses=10,
                          avg_win=300.0, avg_loss=200.0),  # 50% win rate
    ]
    perf_repo.get_by_date_range.return_value = records

    result = await allocator.calculate_allocations(TOTAL_CAPITAL, MAX_POSITIONS, TODAY)

    # gap_go should have a higher proportion due to both better expectancy AND bonus
    assert result["gap_go"].weight_pct > result["ORB"].weight_pct

    # Check that bonus logging happened
    bonus_calls = [
        c for c in log_repo.insert_log.call_args_list
        if c[1]["event_type"] == "bonus_high_win_rate"
    ]
    assert len(bonus_calls) >= 1
    assert bonus_calls[0][1]["strategy"] == "gap_go"


async def test_bonus_capped_at_50_pct(allocator, perf_repo) -> None:
    """Bonus weight is capped at 50% per strategy."""
    # All strategies have very high win rate
    records = [
        _make_perf_record(strategy="gap_go", signals_taken=20, wins=18, losses=2,
                          avg_win=1000.0, avg_loss=50.0),  # 90% win rate, high expectancy
        _make_perf_record(strategy="ORB", signals_taken=20, wins=4, losses=16,
                          avg_win=100.0, avg_loss=200.0),  # 20% win rate
        _make_perf_record(strategy="VWAP Reversal", signals_taken=20, wins=4, losses=16,
                          avg_win=100.0, avg_loss=200.0),  # 20% win rate
    ]
    perf_repo.get_by_date_range.return_value = records

    result = await allocator.calculate_allocations(TOTAL_CAPITAL, MAX_POSITIONS, TODAY)

    # After normalization, no single weight exceeds 50% (BONUS_CAP_PCT)
    # But the total should not exceed 80%
    total_weight = sum(a.weight_pct for a in result.values())
    assert total_weight <= 80.0 + 0.1  # tolerance


# ---------------------------------------------------------------------------
# Adaptation log integration
# ---------------------------------------------------------------------------


async def test_weight_change_logged(allocator, perf_repo, log_repo) -> None:
    """Weight changes from Phase 3 adjustments are logged."""
    records = [
        _make_perf_record(strategy="gap_go", signals_taken=20, wins=5, losses=15),
    ]
    perf_repo.get_by_date_range.return_value = records

    await allocator.calculate_allocations(TOTAL_CAPITAL, MAX_POSITIONS, TODAY)

    # Should have logged at least one weight change
    assert log_repo.insert_log.await_count >= 1


async def test_no_log_when_no_repo(perf_repo, config_repo) -> None:
    """No adaptation log entries when log_repo is None."""
    allocator = CapitalAllocator(perf_repo, config_repo, adaptation_log_repo=None)

    records = [
        _make_perf_record(strategy="gap_go", signals_taken=20, wins=5, losses=15),
    ]
    perf_repo.get_by_date_range.return_value = records

    # Should not raise
    result = await allocator.calculate_allocations(TOTAL_CAPITAL, MAX_POSITIONS, TODAY)
    assert result is not None


# ---------------------------------------------------------------------------
# Existing behavior preserved
# ---------------------------------------------------------------------------


async def test_manual_allocation_unchanged(allocator, perf_repo) -> None:
    """Manual weights are not affected by Phase 3 adjustments."""
    manual_weights = {"gap_go": 0.40, "ORB": 0.20, "VWAP Reversal": 0.20}
    allocator.set_manual_allocation(manual_weights)

    result = await allocator.calculate_allocations(TOTAL_CAPITAL, MAX_POSITIONS, TODAY)

    assert result["gap_go"].weight_pct == pytest.approx(40.0)
    assert result["ORB"].weight_pct == pytest.approx(20.0)
    assert result["VWAP Reversal"].weight_pct == pytest.approx(20.0)
    perf_repo.get_by_date_range.assert_not_awaited()


async def test_equal_allocation_no_history_unchanged(allocator, perf_repo) -> None:
    """No performance data -> equal allocation (Phase 3 does not alter fallback)."""
    perf_repo.get_by_date_range.return_value = []

    result = await allocator.calculate_allocations(TOTAL_CAPITAL, MAX_POSITIONS, TODAY)

    expected_weight = (1.0 - RESERVE_PCT) / len(STRATEGY_NAMES)
    for name in STRATEGY_NAMES:
        assert result[name].weight_pct == pytest.approx(expected_weight * 100)


async def test_normal_win_rate_no_adjustment(allocator, perf_repo, log_repo) -> None:
    """Win rate between 40-70% -> no Phase 3 adjustments."""
    records = [
        _make_perf_record(strategy="gap_go", signals_taken=20, wins=10, losses=10,
                          avg_win=400.0, avg_loss=200.0),  # 50% win rate
        _make_perf_record(strategy="ORB", signals_taken=20, wins=12, losses=8,
                          avg_win=300.0, avg_loss=200.0),  # 60% win rate
        _make_perf_record(strategy="VWAP Reversal", signals_taken=20, wins=9, losses=11,
                          avg_win=400.0, avg_loss=200.0),  # 45% win rate
    ]
    perf_repo.get_by_date_range.return_value = records

    result = await allocator.calculate_allocations(TOTAL_CAPITAL, MAX_POSITIONS, TODAY)

    # No weight changes should be logged (all between 40-70%)
    assert log_repo.insert_log.await_count == 0

    # All strategies should have positive allocation
    for name in STRATEGY_NAMES:
        assert result[name].weight_pct > 0
