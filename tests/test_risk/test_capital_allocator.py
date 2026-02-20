"""Tests for CapitalAllocator."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from signalpilot.db.models import StrategyPerformanceRecord
from signalpilot.risk.capital_allocator import (
    RESERVE_PCT,
    STRATEGY_NAMES,
    CapitalAllocator,
    StrategyAllocation,
)


def _make_perf_record(
    strategy: str = "gap_go",
    d: str = "2026-02-15",
    signals_generated: int = 10,
    signals_taken: int = 8,
    wins: int = 5,
    losses: int = 3,
    total_pnl: float = 1200.0,
    win_rate: float = 62.5,
    avg_win: float = 400.0,
    avg_loss: float = 133.33,
    expectancy: float = 196.67,
    capital_weight_pct: float = 33.33,
) -> StrategyPerformanceRecord:
    return StrategyPerformanceRecord(
        strategy=strategy,
        date=d,
        signals_generated=signals_generated,
        signals_taken=signals_taken,
        wins=wins,
        losses=losses,
        total_pnl=total_pnl,
        win_rate=win_rate,
        avg_win=avg_win,
        avg_loss=avg_loss,
        expectancy=expectancy,
        capital_weight_pct=capital_weight_pct,
    )


@pytest.fixture
def perf_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.get_by_date_range = AsyncMock(return_value=[])
    repo.get_performance_summary = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def config_repo() -> MagicMock:
    return MagicMock()


@pytest.fixture
def allocator(perf_repo, config_repo) -> CapitalAllocator:
    return CapitalAllocator(perf_repo, config_repo)


TODAY = date(2026, 2, 20)
TOTAL_CAPITAL = 300_000.0
MAX_POSITIONS = 15


# -- Equal allocation when no historical data --


async def test_equal_allocation_no_history(allocator, perf_repo) -> None:
    """With no performance records, each strategy gets an equal share of 80%."""
    perf_repo.get_by_date_range.return_value = []

    result = await allocator.calculate_allocations(TOTAL_CAPITAL, MAX_POSITIONS, TODAY)

    assert len(result) == len(STRATEGY_NAMES)
    expected_weight = (1.0 - RESERVE_PCT) / len(STRATEGY_NAMES)
    for strategy_name in STRATEGY_NAMES:
        alloc = result[strategy_name]
        assert isinstance(alloc, StrategyAllocation)
        assert alloc.weight_pct == pytest.approx(expected_weight * 100)
        assert alloc.allocated_capital == pytest.approx(TOTAL_CAPITAL * expected_weight)
        assert alloc.max_positions >= 1


async def test_equal_allocation_sums_to_80_pct(allocator, perf_repo) -> None:
    """Total weights sum to (1 - RESERVE_PCT) = 80%."""
    perf_repo.get_by_date_range.return_value = []

    result = await allocator.calculate_allocations(TOTAL_CAPITAL, MAX_POSITIONS, TODAY)

    total_weight = sum(a.weight_pct for a in result.values())
    assert total_weight == pytest.approx(80.0)


# -- Weighted allocation with known performance data --


async def test_weighted_allocation_with_performance(allocator, perf_repo) -> None:
    """Strategies with higher expectancy get proportionally more capital."""
    records = [
        # gap_go: high expectancy
        _make_perf_record(strategy="gap_go", signals_taken=10, wins=7, losses=3,
                          avg_win=500.0, avg_loss=100.0),
        # ORB: moderate expectancy
        _make_perf_record(strategy="ORB", signals_taken=10, wins=5, losses=5,
                          avg_win=300.0, avg_loss=200.0),
        # VWAP Reversal: low expectancy
        _make_perf_record(strategy="VWAP Reversal", signals_taken=10, wins=4, losses=6,
                          avg_win=250.0, avg_loss=100.0),
    ]
    perf_repo.get_by_date_range.return_value = records

    result = await allocator.calculate_allocations(TOTAL_CAPITAL, MAX_POSITIONS, TODAY)

    # gap_go should get the largest allocation
    assert result["gap_go"].weight_pct > result["ORB"].weight_pct
    assert result["ORB"].weight_pct > result["VWAP Reversal"].weight_pct


async def test_weighted_allocation_sums_to_80_pct(allocator, perf_repo) -> None:
    """Even with performance data, total weights sum to 80%."""
    records = [
        _make_perf_record(strategy="gap_go", signals_taken=10, wins=7, losses=3,
                          avg_win=500.0, avg_loss=100.0),
        _make_perf_record(strategy="ORB", signals_taken=10, wins=5, losses=5,
                          avg_win=300.0, avg_loss=200.0),
    ]
    perf_repo.get_by_date_range.return_value = records

    result = await allocator.calculate_allocations(TOTAL_CAPITAL, MAX_POSITIONS, TODAY)

    total_weight = sum(a.weight_pct for a in result.values())
    assert total_weight == pytest.approx(80.0)


# -- Auto-pause trigger: win rate < 40% with >= 10 trades --


async def test_auto_pause_low_win_rate(allocator, perf_repo) -> None:
    """Strategy with win rate < 40% and >= 10 trades triggers auto-pause."""
    # Only gap_go has bad performance
    async def mock_summary(strategy, start, end):
        if strategy == "gap_go":
            return [_make_perf_record(
                strategy="gap_go", signals_taken=12, wins=3, losses=9,
            )]
        return []

    perf_repo.get_performance_summary.side_effect = mock_summary

    paused = await allocator.check_auto_pause(TODAY)

    assert "gap_go" in paused


async def test_auto_pause_not_triggered_above_40pct(allocator, perf_repo) -> None:
    """Strategy with win rate >= 40% does NOT trigger auto-pause."""
    async def mock_summary(strategy, start, end):
        if strategy == "gap_go":
            return [_make_perf_record(
                strategy="gap_go", signals_taken=10, wins=5, losses=5,
            )]
        return []

    perf_repo.get_performance_summary.side_effect = mock_summary

    paused = await allocator.check_auto_pause(TODAY)

    assert "gap_go" not in paused


async def test_auto_pause_not_triggered_under_10_trades(allocator, perf_repo) -> None:
    """Strategy with < 10 trades does NOT trigger auto-pause regardless of win rate."""
    async def mock_summary(strategy, start, end):
        if strategy == "gap_go":
            return [_make_perf_record(
                strategy="gap_go", signals_taken=5, wins=1, losses=4,
            )]
        return []

    perf_repo.get_performance_summary.side_effect = mock_summary

    paused = await allocator.check_auto_pause(TODAY)

    assert "gap_go" not in paused


async def test_auto_pause_multiple_strategies(allocator, perf_repo) -> None:
    """Multiple strategies can be paused simultaneously."""
    async def mock_summary(strategy, start, end):
        if strategy in ("gap_go", "ORB"):
            return [_make_perf_record(
                strategy=strategy, signals_taken=15, wins=3, losses=12,
            )]
        return []

    perf_repo.get_performance_summary.side_effect = mock_summary

    paused = await allocator.check_auto_pause(TODAY)

    assert "gap_go" in paused
    assert "ORB" in paused
    assert "VWAP Reversal" not in paused


async def test_auto_pause_empty_records(allocator, perf_repo) -> None:
    """No records for any strategy means nothing is paused."""
    perf_repo.get_performance_summary.return_value = []

    paused = await allocator.check_auto_pause(TODAY)

    assert paused == []


# -- Manual override --


async def test_set_manual_allocation(allocator, perf_repo) -> None:
    """Manual allocation weights are used instead of auto-calculated ones."""
    manual_weights = {"gap_go": 0.50, "ORB": 0.20, "VWAP Reversal": 0.10}
    allocator.set_manual_allocation(manual_weights)

    result = await allocator.calculate_allocations(TOTAL_CAPITAL, MAX_POSITIONS, TODAY)

    assert result["gap_go"].weight_pct == pytest.approx(50.0)
    assert result["ORB"].weight_pct == pytest.approx(20.0)
    assert result["VWAP Reversal"].weight_pct == pytest.approx(10.0)
    # Performance repo should not have been called
    perf_repo.get_by_date_range.assert_not_awaited()


async def test_set_manual_allocation_capital(allocator) -> None:
    """Manual weights correctly map to capital amounts."""
    manual_weights = {"gap_go": 0.40, "ORB": 0.30, "VWAP Reversal": 0.10}
    allocator.set_manual_allocation(manual_weights)

    result = await allocator.calculate_allocations(TOTAL_CAPITAL, MAX_POSITIONS, TODAY)

    assert result["gap_go"].allocated_capital == pytest.approx(TOTAL_CAPITAL * 0.40)
    assert result["ORB"].allocated_capital == pytest.approx(TOTAL_CAPITAL * 0.30)
    assert result["VWAP Reversal"].allocated_capital == pytest.approx(TOTAL_CAPITAL * 0.10)


async def test_enable_auto_allocation_clears_manual(allocator, perf_repo) -> None:
    """enable_auto_allocation clears manual weights and reverts to auto mode."""
    manual_weights = {"gap_go": 0.60, "ORB": 0.10, "VWAP Reversal": 0.10}
    allocator.set_manual_allocation(manual_weights)

    allocator.enable_auto_allocation()

    # Now it should use auto mode (equal fallback since no data)
    perf_repo.get_by_date_range.return_value = []
    result = await allocator.calculate_allocations(TOTAL_CAPITAL, MAX_POSITIONS, TODAY)

    expected_weight = (1.0 - RESERVE_PCT) / len(STRATEGY_NAMES)
    for name in STRATEGY_NAMES:
        assert result[name].weight_pct == pytest.approx(expected_weight * 100)


# -- Reserve enforcement --


async def test_reserve_enforcement(allocator, perf_repo) -> None:
    """Allocations always sum to at most 80% (leaving 20% reserve)."""
    records = [
        _make_perf_record(strategy="gap_go", signals_taken=20, wins=15, losses=5,
                          avg_win=1000.0, avg_loss=200.0),
        _make_perf_record(strategy="ORB", signals_taken=20, wins=12, losses=8,
                          avg_win=800.0, avg_loss=300.0),
        _make_perf_record(strategy="VWAP Reversal", signals_taken=20, wins=10, losses=10,
                          avg_win=500.0, avg_loss=200.0),
    ]
    perf_repo.get_by_date_range.return_value = records

    result = await allocator.calculate_allocations(TOTAL_CAPITAL, MAX_POSITIONS, TODAY)

    total_weight = sum(a.weight_pct for a in result.values())
    assert total_weight == pytest.approx(80.0)
    total_capital_alloc = sum(a.allocated_capital for a in result.values())
    assert total_capital_alloc == pytest.approx(TOTAL_CAPITAL * 0.80)


# -- Zero-expectancy strategies --


async def test_zero_expectancy_falls_back_to_equal(allocator, perf_repo) -> None:
    """If all strategies have zero expectancy, fall back to equal allocation."""
    records = [
        # Losses equal wins in expectancy (net zero or negative, clamped to 0)
        _make_perf_record(strategy="gap_go", signals_taken=10, wins=2, losses=8,
                          avg_win=100.0, avg_loss=100.0),
        _make_perf_record(strategy="ORB", signals_taken=10, wins=2, losses=8,
                          avg_win=100.0, avg_loss=100.0),
        _make_perf_record(strategy="VWAP Reversal", signals_taken=10, wins=2, losses=8,
                          avg_win=100.0, avg_loss=100.0),
    ]
    perf_repo.get_by_date_range.return_value = records

    result = await allocator.calculate_allocations(TOTAL_CAPITAL, MAX_POSITIONS, TODAY)

    # All should get equal allocation since all have zero (clamped) expectancy
    expected_weight = (1.0 - RESERVE_PCT) / len(STRATEGY_NAMES)
    for name in STRATEGY_NAMES:
        assert result[name].weight_pct == pytest.approx(expected_weight * 100)


async def test_positions_at_least_one(allocator, perf_repo) -> None:
    """Every strategy gets at least 1 position slot."""
    perf_repo.get_by_date_range.return_value = []

    result = await allocator.calculate_allocations(TOTAL_CAPITAL, MAX_POSITIONS, TODAY)

    for alloc in result.values():
        assert alloc.max_positions >= 1


async def test_strategy_allocation_dataclass(allocator, perf_repo) -> None:
    """Return values are StrategyAllocation dataclass instances."""
    perf_repo.get_by_date_range.return_value = []

    result = await allocator.calculate_allocations(TOTAL_CAPITAL, MAX_POSITIONS, TODAY)

    for alloc in result.values():
        assert isinstance(alloc, StrategyAllocation)
        assert hasattr(alloc, "strategy_name")
        assert hasattr(alloc, "weight_pct")
        assert hasattr(alloc, "allocated_capital")
        assert hasattr(alloc, "max_positions")
