"""Tests for MarketDataStore."""

import asyncio

import pytest

from signalpilot.data.market_data_store import MarketDataStore
from signalpilot.db.models import HistoricalReference, TickData
from datetime import datetime


@pytest.fixture
def store() -> MarketDataStore:
    return MarketDataStore()


def _make_tick(symbol: str = "SBIN", ltp: float = 100.0, volume: int = 1000) -> TickData:
    now = datetime.now()
    return TickData(
        symbol=symbol,
        ltp=ltp,
        open_price=99.0,
        high=101.0,
        low=98.0,
        close=97.0,
        volume=volume,
        last_traded_timestamp=now,
        updated_at=now,
    )


def _make_historical(
    prev_close: float = 95.0, prev_high: float = 100.0, adv: float = 50000.0
) -> HistoricalReference:
    return HistoricalReference(
        previous_close=prev_close,
        previous_high=prev_high,
        average_daily_volume=adv,
    )


# ── Tick operations ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_and_get_tick(store: MarketDataStore) -> None:
    tick = _make_tick("SBIN", ltp=105.0)
    await store.update_tick("SBIN", tick)
    result = await store.get_tick("SBIN")
    assert result is not None
    assert result.ltp == 105.0
    assert result.symbol == "SBIN"


@pytest.mark.asyncio
async def test_get_tick_returns_none_for_unknown(store: MarketDataStore) -> None:
    result = await store.get_tick("UNKNOWN")
    assert result is None


@pytest.mark.asyncio
async def test_update_tick_overwrites_previous(store: MarketDataStore) -> None:
    await store.update_tick("SBIN", _make_tick("SBIN", ltp=100.0))
    await store.update_tick("SBIN", _make_tick("SBIN", ltp=110.0))
    result = await store.get_tick("SBIN")
    assert result is not None
    assert result.ltp == 110.0


@pytest.mark.asyncio
async def test_get_all_ticks_returns_snapshot(store: MarketDataStore) -> None:
    await store.update_tick("SBIN", _make_tick("SBIN", ltp=100.0))
    await store.update_tick("RELIANCE", _make_tick("RELIANCE", ltp=200.0))
    snapshot = await store.get_all_ticks()
    assert len(snapshot) == 2
    assert "SBIN" in snapshot
    assert "RELIANCE" in snapshot


@pytest.mark.asyncio
async def test_get_all_ticks_returns_copy(store: MarketDataStore) -> None:
    await store.update_tick("SBIN", _make_tick("SBIN"))
    snapshot = await store.get_all_ticks()
    snapshot["NEW"] = _make_tick("NEW")
    # Internal state should be unaffected
    snapshot2 = await store.get_all_ticks()
    assert "NEW" not in snapshot2


# ── Historical operations ────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_and_get_historical(store: MarketDataStore) -> None:
    ref = _make_historical(prev_close=95.0)
    await store.set_historical("SBIN", ref)
    result = await store.get_historical("SBIN")
    assert result is not None
    assert result.previous_close == 95.0


@pytest.mark.asyncio
async def test_get_historical_returns_none_for_unknown(store: MarketDataStore) -> None:
    result = await store.get_historical("UNKNOWN")
    assert result is None


# ── Volume accumulation ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_accumulate_volume(store: MarketDataStore) -> None:
    await store.accumulate_volume("SBIN", 5000)
    result = await store.get_accumulated_volume("SBIN")
    assert result == 5000


@pytest.mark.asyncio
async def test_accumulate_volume_overwrites(store: MarketDataStore) -> None:
    """Angel One provides cumulative volume, so each update replaces the previous."""
    await store.accumulate_volume("SBIN", 5000)
    await store.accumulate_volume("SBIN", 12000)
    result = await store.get_accumulated_volume("SBIN")
    assert result == 12000


@pytest.mark.asyncio
async def test_get_accumulated_volume_default_zero(store: MarketDataStore) -> None:
    result = await store.get_accumulated_volume("UNKNOWN")
    assert result == 0


# ── Clear ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_clear_removes_all_data(store: MarketDataStore) -> None:
    await store.update_tick("SBIN", _make_tick("SBIN"))
    await store.set_historical("SBIN", _make_historical())
    await store.accumulate_volume("SBIN", 5000)

    await store.clear()

    assert await store.get_tick("SBIN") is None
    assert await store.get_historical("SBIN") is None
    assert await store.get_accumulated_volume("SBIN") == 0


# ── Concurrent access ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_concurrent_tick_updates(store: MarketDataStore) -> None:
    """Verify concurrent updates don't raise or corrupt data."""

    async def _update(symbol: str, ltp: float) -> None:
        for _ in range(50):
            await store.update_tick(symbol, _make_tick(symbol, ltp=ltp))

    await asyncio.gather(
        _update("SBIN", 100.0),
        _update("RELIANCE", 200.0),
        _update("TCS", 300.0),
    )

    snapshot = await store.get_all_ticks()
    assert len(snapshot) == 3
    assert snapshot["SBIN"].ltp == 100.0
    assert snapshot["RELIANCE"].ltp == 200.0
    assert snapshot["TCS"].ltp == 300.0
