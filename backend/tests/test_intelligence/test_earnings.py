"""Tests for the EarningsCalendar CSV ingestion and refresh."""
import os
import tempfile
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from signalpilot.intelligence.earnings import EarningsCalendar


def _make_config(**overrides):
    """Create a minimal config-like object for EarningsCalendar."""
    defaults = {
        "news_earnings_csv_path": "data/earnings_calendar.csv",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestCSVIngestion:
    """Tests for earnings CSV ingestion."""

    async def test_ingest_valid_csv(self):
        """Should parse valid CSV and upsert all rows."""
        csv_content = (
            "stock_code,earnings_date,quarter,is_confirmed\n"
            "RELIANCE,2026-04-15,Q4FY26,true\n"
            "TCS,2026-04-10,Q4FY26,true\n"
            "INFY,2026-04-12,Q4FY26,false\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            f.flush()
            tmp_path = f.name

        try:
            repo = AsyncMock()
            config = _make_config(news_earnings_csv_path=tmp_path)
            calendar = EarningsCalendar(earnings_repo=repo, config=config)

            count = await calendar.ingest_from_csv()
            assert count == 3
            assert repo.upsert_earnings.await_count == 3

            # Verify first call arguments
            first_call = repo.upsert_earnings.call_args_list[0]
            assert first_call.kwargs["stock_code"] == "RELIANCE"
            assert first_call.kwargs["earnings_date"] == date(2026, 4, 15)
            assert first_call.kwargs["quarter"] == "Q4FY26"
            assert first_call.kwargs["source"] == "csv"
            assert first_call.kwargs["is_confirmed"] is True

            # Verify third call (is_confirmed=false)
            third_call = repo.upsert_earnings.call_args_list[2]
            assert third_call.kwargs["stock_code"] == "INFY"
            assert third_call.kwargs["is_confirmed"] is False
        finally:
            os.unlink(tmp_path)

    async def test_missing_csv_returns_zero(self):
        """Missing CSV file should return 0 without raising."""
        repo = AsyncMock()
        config = _make_config(news_earnings_csv_path="/nonexistent/path.csv")
        calendar = EarningsCalendar(earnings_repo=repo, config=config)

        count = await calendar.ingest_from_csv()
        assert count == 0
        repo.upsert_earnings.assert_not_awaited()

    async def test_csv_with_invalid_rows_skips_them(self):
        """Rows with missing or malformed fields should be skipped."""
        csv_content = (
            "stock_code,earnings_date,quarter,is_confirmed\n"
            "RELIANCE,2026-04-15,Q4FY26,true\n"
            "BAD_ROW,not-a-date,Q4FY26,true\n"
            "TCS,2026-04-10,Q4FY26,false\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            f.flush()
            tmp_path = f.name

        try:
            repo = AsyncMock()
            config = _make_config(news_earnings_csv_path=tmp_path)
            calendar = EarningsCalendar(earnings_repo=repo, config=config)

            count = await calendar.ingest_from_csv()
            # BAD_ROW should be skipped, so count is 2
            assert count == 2
            assert repo.upsert_earnings.await_count == 2
        finally:
            os.unlink(tmp_path)

    async def test_csv_custom_path(self):
        """ingest_from_csv should accept an explicit csv_path argument."""
        csv_content = (
            "stock_code,earnings_date,quarter,is_confirmed\n"
            "SBIN,2026-05-15,Q4FY26,false\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            f.flush()
            tmp_path = f.name

        try:
            repo = AsyncMock()
            config = _make_config(news_earnings_csv_path="/some/other/path.csv")
            calendar = EarningsCalendar(earnings_repo=repo, config=config)

            count = await calendar.ingest_from_csv(csv_path=tmp_path)
            assert count == 1
            call_kwargs = repo.upsert_earnings.call_args_list[0].kwargs
            assert call_kwargs["stock_code"] == "SBIN"
        finally:
            os.unlink(tmp_path)

    async def test_csv_is_confirmed_variants(self):
        """is_confirmed should accept 'true', '1', 'yes' as truthy."""
        csv_content = (
            "stock_code,earnings_date,quarter,is_confirmed\n"
            "A,2026-01-01,Q1,true\n"
            "B,2026-01-02,Q1,1\n"
            "C,2026-01-03,Q1,yes\n"
            "D,2026-01-04,Q1,false\n"
            "E,2026-01-05,Q1,no\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            f.flush()
            tmp_path = f.name

        try:
            repo = AsyncMock()
            config = _make_config(news_earnings_csv_path=tmp_path)
            calendar = EarningsCalendar(earnings_repo=repo, config=config)

            count = await calendar.ingest_from_csv()
            assert count == 5

            calls = repo.upsert_earnings.call_args_list
            assert calls[0].kwargs["is_confirmed"] is True   # "true"
            assert calls[1].kwargs["is_confirmed"] is True   # "1"
            assert calls[2].kwargs["is_confirmed"] is True   # "yes"
            assert calls[3].kwargs["is_confirmed"] is False  # "false"
            assert calls[4].kwargs["is_confirmed"] is False  # "no"
        finally:
            os.unlink(tmp_path)

    async def test_empty_csv(self):
        """CSV with only headers should return 0."""
        csv_content = "stock_code,earnings_date,quarter,is_confirmed\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            f.flush()
            tmp_path = f.name

        try:
            repo = AsyncMock()
            config = _make_config(news_earnings_csv_path=tmp_path)
            calendar = EarningsCalendar(earnings_repo=repo, config=config)

            count = await calendar.ingest_from_csv()
            assert count == 0
        finally:
            os.unlink(tmp_path)


class TestRefresh:
    """Tests for the refresh method."""

    async def test_refresh_calls_csv_and_screener(self):
        """refresh() should call both ingest_from_csv and ingest_from_screener."""
        repo = AsyncMock()
        config = _make_config(news_earnings_csv_path="/nonexistent/path.csv")
        calendar = EarningsCalendar(earnings_repo=repo, config=config)

        # Patch both methods
        calendar.ingest_from_csv = AsyncMock(return_value=3)
        calendar.ingest_from_screener = AsyncMock(return_value=2)

        total = await calendar.refresh()
        assert total == 5
        calendar.ingest_from_csv.assert_awaited_once()
        calendar.ingest_from_screener.assert_awaited_once()

    async def test_refresh_handles_csv_failure(self):
        """refresh() should continue even if CSV ingestion returns 0."""
        repo = AsyncMock()
        config = _make_config()
        calendar = EarningsCalendar(earnings_repo=repo, config=config)

        calendar.ingest_from_csv = AsyncMock(return_value=0)
        calendar.ingest_from_screener = AsyncMock(return_value=5)

        total = await calendar.refresh()
        assert total == 5

    async def test_refresh_handles_screener_failure(self):
        """refresh() should continue even if Screener.in ingestion returns 0."""
        repo = AsyncMock()
        config = _make_config()
        calendar = EarningsCalendar(earnings_repo=repo, config=config)

        calendar.ingest_from_csv = AsyncMock(return_value=3)
        calendar.ingest_from_screener = AsyncMock(return_value=0)

        total = await calendar.refresh()
        assert total == 3


class TestScreenerIngestion:
    """Tests for Screener.in scraping."""

    async def test_screener_error_returns_zero(self):
        """Network error during Screener.in scraping should return 0."""
        repo = AsyncMock()
        config = _make_config()
        calendar = EarningsCalendar(earnings_repo=repo, config=config)

        # Patch the local import of aiohttp by forcing an ImportError
        with patch.dict("sys.modules", {"aiohttp": None}):
            count = await calendar.ingest_from_screener()
            assert count == 0


class TestPlaceholderCSV:
    """Tests for the bundled placeholder CSV file."""

    def test_placeholder_csv_exists(self):
        """The placeholder earnings_calendar.csv should exist in data/."""
        import os
        csv_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..",
            "data", "earnings_calendar.csv"
        )
        assert os.path.exists(csv_path), f"Placeholder CSV not found at {csv_path}"

    def test_placeholder_csv_has_valid_content(self):
        """The placeholder CSV should have valid headers and at least one row."""
        import csv as csv_mod
        import os
        csv_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..",
            "data", "earnings_calendar.csv"
        )
        with open(csv_path) as f:
            reader = csv_mod.DictReader(f)
            rows = list(reader)

        assert len(rows) >= 1
        # Check required headers
        for row in rows:
            assert "stock_code" in row
            assert "earnings_date" in row
            # Validate date format
            date.fromisoformat(row["earnings_date"].strip())
