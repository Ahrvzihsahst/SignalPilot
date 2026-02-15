"""Tests for HistoricalDataFetcher."""

from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from signalpilot.data.auth import SmartAPIAuthenticator
from signalpilot.data.historical import HistoricalDataFetcher
from signalpilot.data.instruments import InstrumentManager
from signalpilot.db.models import Instrument


def _make_instrument(symbol: str = "SBIN", token: str = "3045") -> Instrument:
    return Instrument(
        symbol=symbol,
        name=f"{symbol} Corp",
        angel_token=token,
        exchange="NSE",
        nse_symbol=f"{symbol}-EQ",
        yfinance_symbol=f"{symbol}.NS",
    )


@pytest.fixture
def mock_auth() -> MagicMock:
    auth = MagicMock(spec=SmartAPIAuthenticator)
    auth.smart_connect = MagicMock()
    return auth


@pytest.fixture
def mock_instruments() -> MagicMock:
    mgr = MagicMock(spec=InstrumentManager)
    mgr.symbols = ["SBIN"]
    mgr.get_instrument.return_value = _make_instrument()
    return mgr


@pytest.fixture
def fetcher(mock_auth: MagicMock, mock_instruments: MagicMock) -> HistoricalDataFetcher:
    return HistoricalDataFetcher(
        authenticator=mock_auth,
        instruments=mock_instruments,
        rate_limit=10,  # High limit for tests
    )


# ── fetch_previous_day_data (Angel One success) ─────────────────


@pytest.mark.asyncio
async def test_fetch_previous_day_data_angel_one_success(
    fetcher: HistoricalDataFetcher,
    mock_auth: MagicMock,
) -> None:
    """Angel One returns valid candle data → PreviousDayData is built."""
    mock_auth.smart_connect.getCandleData.return_value = {
        "status": True,
        "data": [
            # Candle: [timestamp, open, high, low, close, volume]
            ["2024-01-01", 100.0, 105.0, 98.0, 102.0, 50000],  # 2 days ago
            ["2024-01-02", 103.0, 108.0, 101.0, 106.0, 60000],  # prev day
            ["2024-01-03", 107.0, 110.0, 105.0, 109.0, 70000],  # today
        ],
    }

    results = await fetcher.fetch_previous_day_data()

    assert "SBIN" in results
    prev = results["SBIN"]
    assert prev.open == 103.0
    assert prev.high == 108.0
    assert prev.low == 101.0
    assert prev.close == 106.0
    assert prev.volume == 60000


# ── fetch_previous_day_data (Angel One failure → yfinance fallback)


@pytest.mark.asyncio
async def test_fetch_previous_day_data_falls_back_to_yfinance(
    fetcher: HistoricalDataFetcher,
    mock_auth: MagicMock,
) -> None:
    """Angel One fails → yfinance fallback returns data."""
    mock_auth.smart_connect.getCandleData.side_effect = Exception("API error")

    mock_hist = pd.DataFrame({
        "Open": [100.0, 103.0, 107.0],
        "High": [105.0, 108.0, 110.0],
        "Low": [98.0, 101.0, 105.0],
        "Close": [102.0, 106.0, 109.0],
        "Volume": [50000, 60000, 70000],
    })

    with patch("signalpilot.data.historical.yf.Ticker") as mock_ticker_cls:
        mock_ticker_cls.return_value.history.return_value = mock_hist
        results = await fetcher.fetch_previous_day_data()

    assert "SBIN" in results
    prev = results["SBIN"]
    assert prev.close == 106.0
    assert prev.volume == 60000


# ── fetch_previous_day_data (both sources fail → excluded) ───────


@pytest.mark.asyncio
async def test_fetch_previous_day_data_both_fail_excludes(
    fetcher: HistoricalDataFetcher,
    mock_auth: MagicMock,
) -> None:
    """Both Angel One and yfinance fail → instrument excluded."""
    mock_auth.smart_connect.getCandleData.side_effect = Exception("API error")

    with patch("signalpilot.data.historical.yf.Ticker") as mock_ticker_cls:
        mock_ticker_cls.return_value.history.side_effect = Exception("yfinance error")
        results = await fetcher.fetch_previous_day_data()

    assert "SBIN" not in results


# ── fetch_previous_day_data (Angel One returns empty/insufficient data)


@pytest.mark.asyncio
async def test_fetch_previous_day_data_insufficient_candles(
    fetcher: HistoricalDataFetcher,
    mock_auth: MagicMock,
) -> None:
    """Angel One returns fewer than 2 candles → falls back to yfinance."""
    mock_auth.smart_connect.getCandleData.return_value = {
        "status": True,
        "data": [["2024-01-03", 107.0, 110.0, 105.0, 109.0, 70000]],
    }

    mock_hist = pd.DataFrame({
        "Open": [100.0, 103.0],
        "High": [105.0, 108.0],
        "Low": [98.0, 101.0],
        "Close": [102.0, 106.0],
        "Volume": [50000, 60000],
    })

    with patch("signalpilot.data.historical.yf.Ticker") as mock_ticker_cls:
        mock_ticker_cls.return_value.history.return_value = mock_hist
        results = await fetcher.fetch_previous_day_data()

    assert "SBIN" in results
    assert results["SBIN"].close == 102.0  # iloc[-2]


# ── fetch_average_daily_volume (Angel One success) ───────────────


@pytest.mark.asyncio
async def test_fetch_adv_angel_one_success(
    fetcher: HistoricalDataFetcher,
    mock_auth: MagicMock,
) -> None:
    """ADV from Angel One returns correct average."""
    candles = [
        [f"2024-01-{i:02d}", 100.0, 105.0, 98.0, 102.0, 10000 * i]
        for i in range(1, 21)
    ]
    mock_auth.smart_connect.getCandleData.return_value = {
        "status": True,
        "data": candles,
    }

    results = await fetcher.fetch_average_daily_volume(lookback_days=20)

    assert "SBIN" in results
    expected_avg = sum(10000 * i for i in range(1, 21)) / 20
    assert results["SBIN"] == pytest.approx(expected_avg)


# ── fetch_average_daily_volume (fallback to yfinance) ────────────


@pytest.mark.asyncio
async def test_fetch_adv_falls_back_to_yfinance(
    fetcher: HistoricalDataFetcher,
    mock_auth: MagicMock,
) -> None:
    mock_auth.smart_connect.getCandleData.side_effect = Exception("API error")

    volumes = [10000 * i for i in range(1, 21)]
    mock_hist = pd.DataFrame({"Volume": volumes})

    with patch("signalpilot.data.historical.yf.Ticker") as mock_ticker_cls:
        mock_ticker_cls.return_value.history.return_value = mock_hist
        results = await fetcher.fetch_average_daily_volume(lookback_days=20)

    assert "SBIN" in results
    expected_avg = sum(volumes) / 20
    assert results["SBIN"] == pytest.approx(expected_avg)


# ── build_historical_references ──────────────────────────────────


@pytest.mark.asyncio
async def test_build_historical_references(
    fetcher: HistoricalDataFetcher,
    mock_auth: MagicMock,
) -> None:
    """Combines prev day data + ADV into HistoricalReference."""
    # Angel One returns candles for both calls
    mock_auth.smart_connect.getCandleData.return_value = {
        "status": True,
        "data": [
            ["2024-01-01", 100.0, 105.0, 98.0, 102.0, 50000],
            ["2024-01-02", 103.0, 108.0, 101.0, 106.0, 60000],
            ["2024-01-03", 107.0, 110.0, 105.0, 109.0, 70000],
        ],
    }

    refs = await fetcher.build_historical_references()

    assert "SBIN" in refs
    assert refs["SBIN"].previous_close == 106.0
    assert refs["SBIN"].previous_high == 108.0
    assert refs["SBIN"].average_daily_volume > 0


# ── Missing instrument excluded ──────────────────────────────────


@pytest.mark.asyncio
async def test_missing_instrument_returns_none(mock_auth: MagicMock) -> None:
    """When instrument is not found, returns None."""
    mock_instruments = MagicMock(spec=InstrumentManager)
    mock_instruments.symbols = ["UNKNOWN"]
    mock_instruments.get_instrument.return_value = None

    fetcher = HistoricalDataFetcher(
        authenticator=mock_auth,
        instruments=mock_instruments,
        rate_limit=10,
    )

    results = await fetcher.fetch_previous_day_data()
    assert "UNKNOWN" not in results


# ── Angel One API status False ───────────────────────────────────


@pytest.mark.asyncio
async def test_angel_one_status_false_falls_back(
    fetcher: HistoricalDataFetcher,
    mock_auth: MagicMock,
) -> None:
    """Angel One returns status=False → fallback to yfinance."""
    mock_auth.smart_connect.getCandleData.return_value = {
        "status": False,
        "message": "Invalid token",
    }

    mock_hist = pd.DataFrame({
        "Open": [100.0, 103.0],
        "High": [105.0, 108.0],
        "Low": [98.0, 101.0],
        "Close": [102.0, 106.0],
        "Volume": [50000, 60000],
    })

    with patch("signalpilot.data.historical.yf.Ticker") as mock_ticker_cls:
        mock_ticker_cls.return_value.history.return_value = mock_hist
        results = await fetcher.fetch_previous_day_data()

    assert "SBIN" in results
