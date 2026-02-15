"""Tests for InstrumentManager."""

import csv
import logging
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from signalpilot.data.instruments import InstrumentManager


def _write_csv(path: Path, symbols: list[dict[str, str]]) -> None:
    """Write a Nifty 500-style CSV file."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["Symbol", "Company Name"])
        writer.writeheader()
        for s in symbols:
            writer.writerow(s)


def _make_angel_master(entries: list[dict]) -> list[dict]:
    """Build a minimal Angel One instrument master list."""
    return entries


# ── Loading & cross-reference ────────────────────────────────────


@pytest.mark.asyncio
async def test_load_builds_instruments_and_token_map() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "nifty500.csv"
        _write_csv(csv_path, [
            {"Symbol": "SBIN", "Company Name": "State Bank of India"},
            {"Symbol": "RELIANCE", "Company Name": "Reliance Industries"},
        ])

        angel_master = _make_angel_master([
            {"exch_seg": "NSE", "symbol": "SBIN-EQ", "token": "3045"},
            {"exch_seg": "NSE", "symbol": "RELIANCE-EQ", "token": "2885"},
            {"exch_seg": "BSE", "symbol": "SBIN-EQ", "token": "9999"},  # BSE ignored
        ])

        mgr = InstrumentManager(nifty500_csv_path=str(csv_path))
        with patch.object(mgr, "_fetch_instrument_master", new_callable=AsyncMock, return_value=angel_master):
            await mgr.load()

        assert len(mgr.symbols) == 2
        assert "SBIN" in mgr.symbols
        assert "RELIANCE" in mgr.symbols


@pytest.mark.asyncio
async def test_get_instrument_returns_correct_data() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "nifty500.csv"
        _write_csv(csv_path, [{"Symbol": "SBIN", "Company Name": "State Bank of India"}])

        angel_master = [{"exch_seg": "NSE", "symbol": "SBIN-EQ", "token": "3045"}]

        mgr = InstrumentManager(nifty500_csv_path=str(csv_path))
        with patch.object(mgr, "_fetch_instrument_master", new_callable=AsyncMock, return_value=angel_master):
            await mgr.load()

        inst = mgr.get_instrument("SBIN")
        assert inst is not None
        assert inst.angel_token == "3045"
        assert inst.nse_symbol == "SBIN-EQ"
        assert inst.yfinance_symbol == "SBIN.NS"
        assert inst.exchange == "NSE"


@pytest.mark.asyncio
async def test_get_instrument_returns_none_for_unknown() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "nifty500.csv"
        _write_csv(csv_path, [{"Symbol": "SBIN", "Company Name": "SBI"}])

        angel_master = [{"exch_seg": "NSE", "symbol": "SBIN-EQ", "token": "3045"}]
        mgr = InstrumentManager(nifty500_csv_path=str(csv_path))
        with patch.object(mgr, "_fetch_instrument_master", new_callable=AsyncMock, return_value=angel_master):
            await mgr.load()

        assert mgr.get_instrument("UNKNOWN") is None


# ── Token operations ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_all_tokens_returns_correct_format() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "nifty500.csv"
        _write_csv(csv_path, [
            {"Symbol": "SBIN", "Company Name": "SBI"},
            {"Symbol": "RELIANCE", "Company Name": "Reliance"},
        ])

        angel_master = [
            {"exch_seg": "NSE", "symbol": "SBIN-EQ", "token": "3045"},
            {"exch_seg": "NSE", "symbol": "RELIANCE-EQ", "token": "2885"},
        ]

        mgr = InstrumentManager(nifty500_csv_path=str(csv_path))
        with patch.object(mgr, "_fetch_instrument_master", new_callable=AsyncMock, return_value=angel_master):
            await mgr.load()

        token_list = mgr.get_all_tokens()
        assert len(token_list) == 1
        assert token_list[0]["exchangeType"] == 1
        assert set(token_list[0]["tokens"]) == {"3045", "2885"}


@pytest.mark.asyncio
async def test_get_symbol_by_token() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "nifty500.csv"
        _write_csv(csv_path, [{"Symbol": "SBIN", "Company Name": "SBI"}])

        angel_master = [{"exch_seg": "NSE", "symbol": "SBIN-EQ", "token": "3045"}]
        mgr = InstrumentManager(nifty500_csv_path=str(csv_path))
        with patch.object(mgr, "_fetch_instrument_master", new_callable=AsyncMock, return_value=angel_master):
            await mgr.load()

        assert mgr.get_symbol_by_token("3045") == "SBIN"
        assert mgr.get_symbol_by_token("9999") is None


# ── Missing symbol warning ───────────────────────────────────────


@pytest.mark.asyncio
async def test_missing_symbol_logs_warning_and_is_excluded(caplog: pytest.LogCaptureFixture) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "nifty500.csv"
        _write_csv(csv_path, [
            {"Symbol": "SBIN", "Company Name": "SBI"},
            {"Symbol": "MISSING_STOCK", "Company Name": "Does Not Exist"},
        ])

        # Only SBIN exists in master — MISSING_STOCK is absent
        angel_master = [{"exch_seg": "NSE", "symbol": "SBIN-EQ", "token": "3045"}]

        mgr = InstrumentManager(nifty500_csv_path=str(csv_path))
        with patch.object(mgr, "_fetch_instrument_master", new_callable=AsyncMock, return_value=angel_master):
            with caplog.at_level(logging.WARNING, logger="signalpilot.data.instruments"):
                await mgr.load()

        assert len(mgr.symbols) == 1
        assert "SBIN" in mgr.symbols
        assert "MISSING_STOCK" not in mgr.symbols
        assert any("MISSING_STOCK" in msg for msg in caplog.messages)


# ── CSV file not found ───────────────────────────────────────────


def test_load_csv_raises_on_missing_file() -> None:
    mgr = InstrumentManager(nifty500_csv_path="/nonexistent/path.csv")
    with pytest.raises(FileNotFoundError):
        mgr._load_csv()


# ── Filters BSE and non-EQ instruments ───────────────────────────


@pytest.mark.asyncio
async def test_filters_bse_and_non_eq_instruments() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "nifty500.csv"
        _write_csv(csv_path, [{"Symbol": "SBIN", "Company Name": "SBI"}])

        angel_master = [
            {"exch_seg": "NSE", "symbol": "SBIN-EQ", "token": "3045"},
            {"exch_seg": "BSE", "symbol": "SBIN-EQ", "token": "9999"},  # BSE
            {"exch_seg": "NSE", "symbol": "SBIN-FUT", "token": "8888"},  # Futures
        ]

        mgr = InstrumentManager(nifty500_csv_path=str(csv_path))
        with patch.object(mgr, "_fetch_instrument_master", new_callable=AsyncMock, return_value=angel_master):
            await mgr.load()

        # Should only have the NSE-EQ entry
        assert mgr.get_instrument("SBIN") is not None
        assert mgr.get_instrument("SBIN").angel_token == "3045"
        tokens = mgr.get_all_tokens()[0]["tokens"]
        assert "9999" not in tokens
        assert "8888" not in tokens


# ── Alternative CSV column headers ───────────────────────────────


@pytest.mark.asyncio
async def test_load_csv_with_lowercase_columns() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "nifty500.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["symbol", "name"])
            writer.writeheader()
            writer.writerow({"symbol": "TCS", "name": "Tata Consultancy"})

        angel_master = [{"exch_seg": "NSE", "symbol": "TCS-EQ", "token": "1234"}]
        mgr = InstrumentManager(nifty500_csv_path=str(csv_path))
        with patch.object(mgr, "_fetch_instrument_master", new_callable=AsyncMock, return_value=angel_master):
            await mgr.load()

        assert "TCS" in mgr.symbols


# ── Empty state ──────────────────────────────────────────────────


def test_symbols_empty_before_load() -> None:
    mgr = InstrumentManager()
    assert mgr.symbols == []
    assert mgr.get_all_tokens() == [{"exchangeType": 1, "tokens": []}]
