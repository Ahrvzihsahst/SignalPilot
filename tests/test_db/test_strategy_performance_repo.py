"""Tests for StrategyPerformanceRepository."""

from datetime import date

import pytest

from signalpilot.db.models import StrategyPerformanceRecord
from signalpilot.db.strategy_performance_repo import StrategyPerformanceRepository


def _make_record(
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
async def perf_repo(db_manager):
    """StrategyPerformanceRepository backed by in-memory database."""
    return StrategyPerformanceRepository(db_manager.connection)


class TestUpsertDaily:
    async def test_insert_new_record(self, perf_repo) -> None:
        """Inserting a new record persists all fields."""
        record = _make_record(strategy="gap_go", d="2026-02-15")
        await perf_repo.upsert_daily(record)

        results = await perf_repo.get_by_date_range(
            date(2026, 2, 15), date(2026, 2, 15)
        )
        assert len(results) == 1
        assert results[0].strategy == "gap_go"
        assert results[0].date == "2026-02-15"
        assert results[0].signals_generated == 10
        assert results[0].signals_taken == 8
        assert results[0].wins == 5
        assert results[0].losses == 3
        assert results[0].total_pnl == pytest.approx(1200.0)
        assert results[0].win_rate == pytest.approx(62.5)
        assert results[0].avg_win == pytest.approx(400.0)
        assert results[0].avg_loss == pytest.approx(133.33)
        assert results[0].expectancy == pytest.approx(196.67)
        assert results[0].capital_weight_pct == pytest.approx(33.33)

    async def test_update_existing_record(self, perf_repo) -> None:
        """Upserting same strategy+date updates the existing record."""
        original = _make_record(strategy="ORB", d="2026-02-15", wins=3, losses=5)
        await perf_repo.upsert_daily(original)

        updated = _make_record(strategy="ORB", d="2026-02-15", wins=7, losses=3,
                               total_pnl=2500.0, win_rate=70.0)
        await perf_repo.upsert_daily(updated)

        results = await perf_repo.get_by_date_range(
            date(2026, 2, 15), date(2026, 2, 15)
        )
        # Should still be 1 record, not 2
        orb_records = [r for r in results if r.strategy == "ORB"]
        assert len(orb_records) == 1
        assert orb_records[0].wins == 7
        assert orb_records[0].losses == 3
        assert orb_records[0].total_pnl == pytest.approx(2500.0)
        assert orb_records[0].win_rate == pytest.approx(70.0)

    async def test_upsert_different_strategies_same_date(self, perf_repo) -> None:
        """Different strategies on the same date are separate records."""
        await perf_repo.upsert_daily(_make_record(strategy="gap_go", d="2026-02-15"))
        await perf_repo.upsert_daily(_make_record(strategy="ORB", d="2026-02-15"))
        await perf_repo.upsert_daily(
            _make_record(strategy="VWAP Reversal", d="2026-02-15")
        )

        results = await perf_repo.get_by_date_range(
            date(2026, 2, 15), date(2026, 2, 15)
        )
        assert len(results) == 3
        strategies = {r.strategy for r in results}
        assert strategies == {"gap_go", "ORB", "VWAP Reversal"}

    async def test_upsert_same_strategy_different_dates(self, perf_repo) -> None:
        """Same strategy on different dates creates separate records."""
        await perf_repo.upsert_daily(_make_record(strategy="gap_go", d="2026-02-14"))
        await perf_repo.upsert_daily(_make_record(strategy="gap_go", d="2026-02-15"))

        results = await perf_repo.get_by_date_range(
            date(2026, 2, 14), date(2026, 2, 15)
        )
        gap_records = [r for r in results if r.strategy == "gap_go"]
        assert len(gap_records) == 2


class TestGetPerformanceSummary:
    async def test_filters_by_strategy(self, perf_repo) -> None:
        """Only returns records for the specified strategy."""
        await perf_repo.upsert_daily(_make_record(strategy="gap_go", d="2026-02-15"))
        await perf_repo.upsert_daily(_make_record(strategy="ORB", d="2026-02-15"))

        results = await perf_repo.get_performance_summary(
            "gap_go", date(2026, 2, 14), date(2026, 2, 16)
        )
        assert len(results) == 1
        assert results[0].strategy == "gap_go"

    async def test_filters_by_date_range(self, perf_repo) -> None:
        """Only returns records within the date range."""
        await perf_repo.upsert_daily(_make_record(strategy="gap_go", d="2026-02-10"))
        await perf_repo.upsert_daily(_make_record(strategy="gap_go", d="2026-02-15"))
        await perf_repo.upsert_daily(_make_record(strategy="gap_go", d="2026-02-20"))

        results = await perf_repo.get_performance_summary(
            "gap_go", date(2026, 2, 12), date(2026, 2, 18)
        )
        assert len(results) == 1
        assert results[0].date == "2026-02-15"

    async def test_returns_ordered_by_date(self, perf_repo) -> None:
        """Results are ordered by date ascending."""
        await perf_repo.upsert_daily(_make_record(strategy="ORB", d="2026-02-18"))
        await perf_repo.upsert_daily(_make_record(strategy="ORB", d="2026-02-14"))
        await perf_repo.upsert_daily(_make_record(strategy="ORB", d="2026-02-16"))

        results = await perf_repo.get_performance_summary(
            "ORB", date(2026, 2, 13), date(2026, 2, 19)
        )
        dates = [r.date for r in results]
        assert dates == ["2026-02-14", "2026-02-16", "2026-02-18"]

    async def test_empty_range_returns_empty_list(self, perf_repo) -> None:
        """Date range with no records returns an empty list."""
        await perf_repo.upsert_daily(_make_record(strategy="gap_go", d="2026-02-15"))

        results = await perf_repo.get_performance_summary(
            "gap_go", date(2026, 3, 1), date(2026, 3, 31)
        )
        assert results == []

    async def test_nonexistent_strategy_returns_empty(self, perf_repo) -> None:
        """Querying a strategy with no records returns empty list."""
        await perf_repo.upsert_daily(_make_record(strategy="gap_go", d="2026-02-15"))

        results = await perf_repo.get_performance_summary(
            "nonexistent", date(2026, 2, 1), date(2026, 2, 28)
        )
        assert results == []


class TestGetByDateRange:
    async def test_returns_all_strategies_in_range(self, perf_repo) -> None:
        """Returns records for all strategies within the date range."""
        await perf_repo.upsert_daily(_make_record(strategy="gap_go", d="2026-02-15"))
        await perf_repo.upsert_daily(_make_record(strategy="ORB", d="2026-02-15"))
        await perf_repo.upsert_daily(
            _make_record(strategy="VWAP Reversal", d="2026-02-15")
        )

        results = await perf_repo.get_by_date_range(
            date(2026, 2, 14), date(2026, 2, 16)
        )
        assert len(results) == 3
        strategies = {r.strategy for r in results}
        assert strategies == {"gap_go", "ORB", "VWAP Reversal"}

    async def test_excludes_records_outside_range(self, perf_repo) -> None:
        """Records outside the date range are not returned."""
        await perf_repo.upsert_daily(_make_record(strategy="gap_go", d="2026-02-10"))
        await perf_repo.upsert_daily(_make_record(strategy="gap_go", d="2026-02-15"))
        await perf_repo.upsert_daily(_make_record(strategy="gap_go", d="2026-02-25"))

        results = await perf_repo.get_by_date_range(
            date(2026, 2, 12), date(2026, 2, 20)
        )
        assert len(results) == 1
        assert results[0].date == "2026-02-15"

    async def test_empty_range_returns_empty_list(self, perf_repo) -> None:
        """Date range with no records returns empty list."""
        results = await perf_repo.get_by_date_range(
            date(2026, 3, 1), date(2026, 3, 31)
        )
        assert results == []

    async def test_ordered_by_date_then_strategy(self, perf_repo) -> None:
        """Results are ordered by date, then by strategy."""
        await perf_repo.upsert_daily(_make_record(strategy="ORB", d="2026-02-16"))
        await perf_repo.upsert_daily(_make_record(strategy="gap_go", d="2026-02-16"))
        await perf_repo.upsert_daily(_make_record(strategy="gap_go", d="2026-02-14"))

        results = await perf_repo.get_by_date_range(
            date(2026, 2, 13), date(2026, 2, 17)
        )
        # date ascending, then strategy ascending within same date
        assert results[0].date == "2026-02-14"
        assert results[0].strategy == "gap_go"
        assert results[1].date == "2026-02-16"
        assert results[2].date == "2026-02-16"

    async def test_record_has_id(self, perf_repo) -> None:
        """Returned records have an auto-generated id."""
        await perf_repo.upsert_daily(_make_record(strategy="gap_go", d="2026-02-15"))

        results = await perf_repo.get_by_date_range(
            date(2026, 2, 15), date(2026, 2, 15)
        )
        assert len(results) == 1
        assert results[0].id is not None
        assert results[0].id > 0
