"""Tests for RegimePerformanceRepository."""

from datetime import date, datetime

import pytest

from signalpilot.db.database import DatabaseManager
from signalpilot.db.regime_performance_repo import RegimePerformanceRepository
from signalpilot.utils.constants import IST


@pytest.fixture
async def perf_db():
    """In-memory database with full schema for regime performance tests."""
    manager = DatabaseManager(":memory:")
    await manager.initialize()
    yield manager
    await manager.close()


@pytest.fixture
async def perf_repo(perf_db):
    """RegimePerformanceRepository backed by in-memory database."""
    return RegimePerformanceRepository(perf_db.connection)


class TestInsertAndRetrieve:
    """Tests for inserting and retrieving performance records."""

    async def test_insert_and_retrieve(self, perf_repo):
        """Insert a performance record and verify it can be retrieved."""
        today = datetime.now(IST).date()
        row_id = await perf_repo.insert_daily_performance(
            regime_date=today,
            regime="TRENDING",
            strategy="Gap & Go",
            signals_generated=10,
            signals_taken=5,
            wins=3,
            losses=2,
            pnl=1500.0,
        )

        assert row_id is not None
        assert row_id > 0

        # Retrieve by regime
        records = await perf_repo.get_performance_by_regime("TRENDING", days=1)
        assert len(records) == 1
        record = records[0]
        assert record["strategy"] == "Gap & Go"
        assert record["total_signals"] == 10
        assert record["total_taken"] == 5
        assert record["total_wins"] == 3
        assert record["total_losses"] == 2
        assert record["total_pnl"] == 1500.0
        assert record["agg_win_rate"] == pytest.approx(60.0, abs=0.1)

    async def test_insert_with_no_taken(self, perf_repo):
        """Win rate should be None when no signals were taken."""
        today = datetime.now(IST).date()
        await perf_repo.insert_daily_performance(
            regime_date=today,
            regime="RANGING",
            strategy="ORB",
            signals_generated=5,
            signals_taken=0,
            wins=0,
            losses=0,
            pnl=0.0,
        )

        records = await perf_repo.get_performance_by_regime("RANGING", days=1)
        assert len(records) == 1
        assert records[0]["agg_win_rate"] is None


class TestGetPerformanceByRegime:
    """Tests for get_performance_by_regime."""

    async def test_get_performance_by_regime(self, perf_repo):
        """Should return aggregated performance for a specific regime."""
        today = datetime.now(IST).date()

        # Insert two records for TRENDING
        await perf_repo.insert_daily_performance(
            regime_date=today,
            regime="TRENDING",
            strategy="Gap & Go",
            signals_generated=10,
            signals_taken=5,
            wins=3,
            losses=2,
            pnl=1500.0,
        )
        await perf_repo.insert_daily_performance(
            regime_date=today,
            regime="TRENDING",
            strategy="ORB",
            signals_generated=8,
            signals_taken=4,
            wins=2,
            losses=2,
            pnl=500.0,
        )

        records = await perf_repo.get_performance_by_regime("TRENDING", days=30)
        assert len(records) == 2

        # Find Gap & Go record
        gap_go = next(r for r in records if r["strategy"] == "Gap & Go")
        assert gap_go["total_signals"] == 10
        assert gap_go["total_pnl"] == 1500.0

        # Find ORB record
        orb = next(r for r in records if r["strategy"] == "ORB")
        assert orb["total_signals"] == 8
        assert orb["total_pnl"] == 500.0

    async def test_get_performance_by_regime_empty(self, perf_repo):
        """Should return empty list when no records exist for the regime."""
        records = await perf_repo.get_performance_by_regime("VOLATILE", days=30)
        assert records == []

    async def test_get_performance_by_regime_filters_by_regime(self, perf_repo):
        """Should only return records for the specified regime."""
        today = datetime.now(IST).date()

        await perf_repo.insert_daily_performance(
            regime_date=today,
            regime="TRENDING",
            strategy="Gap & Go",
            signals_generated=10,
            signals_taken=5,
            wins=3,
            losses=2,
            pnl=1500.0,
        )
        await perf_repo.insert_daily_performance(
            regime_date=today,
            regime="VOLATILE",
            strategy="Gap & Go",
            signals_generated=3,
            signals_taken=1,
            wins=0,
            losses=1,
            pnl=-200.0,
        )

        trending = await perf_repo.get_performance_by_regime("TRENDING", days=30)
        assert len(trending) == 1
        assert trending[0]["total_pnl"] == 1500.0

        volatile = await perf_repo.get_performance_by_regime("VOLATILE", days=30)
        assert len(volatile) == 1
        assert volatile[0]["total_pnl"] == -200.0


class TestGetPerformanceSummary:
    """Tests for get_performance_summary."""

    async def test_get_performance_summary(self, perf_repo):
        """Should return performance grouped by regime and strategy."""
        today = datetime.now(IST).date()

        await perf_repo.insert_daily_performance(
            regime_date=today,
            regime="TRENDING",
            strategy="Gap & Go",
            signals_generated=10,
            signals_taken=5,
            wins=3,
            losses=2,
            pnl=1500.0,
        )
        await perf_repo.insert_daily_performance(
            regime_date=today,
            regime="TRENDING",
            strategy="ORB",
            signals_generated=8,
            signals_taken=4,
            wins=2,
            losses=2,
            pnl=500.0,
        )
        await perf_repo.insert_daily_performance(
            regime_date=today,
            regime="VOLATILE",
            strategy="Gap & Go",
            signals_generated=3,
            signals_taken=1,
            wins=0,
            losses=1,
            pnl=-200.0,
        )

        summary = await perf_repo.get_performance_summary(days=30)
        assert len(summary) == 3

        # Should be ordered by regime, strategy
        regimes = [r["regime"] for r in summary]
        strategies = [r["strategy"] for r in summary]
        assert regimes == sorted(regimes)

    async def test_get_performance_summary_empty(self, perf_repo):
        """Should return empty list when no records exist."""
        summary = await perf_repo.get_performance_summary(days=30)
        assert summary == []

    async def test_get_performance_summary_aggregates(self, perf_repo):
        """Summary should aggregate multiple days for the same regime+strategy."""
        today = datetime.now(IST).date()

        # Insert same regime+strategy twice (simulating two days)
        await perf_repo.insert_daily_performance(
            regime_date=today,
            regime="TRENDING",
            strategy="Gap & Go",
            signals_generated=10,
            signals_taken=5,
            wins=3,
            losses=2,
            pnl=1500.0,
        )
        await perf_repo.insert_daily_performance(
            regime_date=today,
            regime="TRENDING",
            strategy="Gap & Go",
            signals_generated=8,
            signals_taken=4,
            wins=4,
            losses=0,
            pnl=2000.0,
        )

        summary = await perf_repo.get_performance_summary(days=30)
        assert len(summary) == 1  # Aggregated into one row
        assert summary[0]["total_signals"] == 18
        assert summary[0]["total_taken"] == 9
        assert summary[0]["total_wins"] == 7
        assert summary[0]["total_pnl"] == 3500.0
        assert summary[0]["agg_win_rate"] == pytest.approx(7 / 9 * 100, abs=0.1)
