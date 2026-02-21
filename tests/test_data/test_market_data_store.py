"""Tests for MarketDataStore."""

import asyncio
from datetime import datetime

import pytest

from signalpilot.data.market_data_store import MarketDataStore
from signalpilot.db.models import HistoricalReference, TickData


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


# ══════════════════════════════════════════════════════════════════
# Phase 2 — Opening Range tracking
# ══════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_update_opening_range_creates_new(store: MarketDataStore) -> None:
    """First update_opening_range creates a new entry with given high/low."""
    await store.update_opening_range("SBIN", high=105.0, low=100.0)
    rng = await store.get_opening_range("SBIN")
    assert rng is not None
    assert rng.range_high == 105.0
    assert rng.range_low == 100.0
    assert rng.locked is False


@pytest.mark.asyncio
async def test_update_opening_range_extends_high_low(store: MarketDataStore) -> None:
    """Subsequent updates should widen the range (max high, min low)."""
    await store.update_opening_range("SBIN", high=105.0, low=100.0)
    await store.update_opening_range("SBIN", high=108.0, low=101.0)  # new high
    await store.update_opening_range("SBIN", high=106.0, low=98.0)   # new low

    rng = await store.get_opening_range("SBIN")
    assert rng is not None
    assert rng.range_high == 108.0
    assert rng.range_low == 98.0


@pytest.mark.asyncio
async def test_lock_opening_ranges_marks_locked_and_calculates_pct(
    store: MarketDataStore,
) -> None:
    """lock_opening_ranges sets locked=True and computes range_size_pct."""
    await store.update_opening_range("SBIN", high=110.0, low=100.0)
    await store.lock_opening_ranges()

    rng = await store.get_opening_range("SBIN")
    assert rng is not None
    assert rng.locked is True
    # range_size_pct = (110 - 100) / 100 * 100 = 10.0
    assert rng.range_size_pct == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_lock_opening_ranges_multiple_symbols(store: MarketDataStore) -> None:
    """All symbols should be locked in a single call."""
    await store.update_opening_range("SBIN", high=105.0, low=100.0)
    await store.update_opening_range("TCS", high=3600.0, low=3500.0)

    await store.lock_opening_ranges()

    for sym in ("SBIN", "TCS"):
        rng = await store.get_opening_range(sym)
        assert rng is not None
        assert rng.locked is True
        assert rng.range_size_pct > 0


@pytest.mark.asyncio
async def test_updates_rejected_after_lock(store: MarketDataStore) -> None:
    """Once locked, update_opening_range should not change high/low."""
    await store.update_opening_range("SBIN", high=105.0, low=100.0)
    await store.lock_opening_ranges()

    # Try to widen the range — should be silently ignored
    await store.update_opening_range("SBIN", high=200.0, low=50.0)

    rng = await store.get_opening_range("SBIN")
    assert rng is not None
    assert rng.range_high == 105.0
    assert rng.range_low == 100.0


@pytest.mark.asyncio
async def test_get_opening_range_returns_none_for_unknown(store: MarketDataStore) -> None:
    """get_opening_range returns None for a symbol never seen."""
    result = await store.get_opening_range("UNKNOWN")
    assert result is None


# ══════════════════════════════════════════════════════════════════
# Phase 2 — VWAP calculation
# ══════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_update_vwap_single_update(store: MarketDataStore) -> None:
    """Single VWAP update: vwap = price."""
    await store.update_vwap("SBIN", price=100.0, volume=10.0)
    vwap = await store.get_vwap("SBIN")
    assert vwap == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_update_vwap_accumulates_correctly(store: MarketDataStore) -> None:
    """VWAP = sum(price*volume) / sum(volume).

    price=100, vol=10 and price=200, vol=20 -> (1000+4000)/30 = 166.67
    """
    await store.update_vwap("SBIN", price=100.0, volume=10.0)
    await store.update_vwap("SBIN", price=200.0, volume=20.0)

    vwap = await store.get_vwap("SBIN")
    expected = (100.0 * 10.0 + 200.0 * 20.0) / (10.0 + 20.0)
    assert vwap == pytest.approx(expected, rel=1e-2)
    assert vwap == pytest.approx(166.67, rel=1e-2)


@pytest.mark.asyncio
async def test_reset_vwap_clears_state(store: MarketDataStore) -> None:
    """reset_vwap should clear all VWAP accumulators."""
    await store.update_vwap("SBIN", price=100.0, volume=10.0)
    await store.update_vwap("TCS", price=3500.0, volume=5.0)

    await store.reset_vwap()

    assert await store.get_vwap("SBIN") is None
    assert await store.get_vwap("TCS") is None


@pytest.mark.asyncio
async def test_get_vwap_returns_none_for_unknown(store: MarketDataStore) -> None:
    """get_vwap returns None for a symbol with no updates."""
    result = await store.get_vwap("UNKNOWN")
    assert result is None


# ══════════════════════════════════════════════════════════════════
# Phase 2 — 15-minute candle aggregation
# ══════════════════════════════════════════════════════════════════

from datetime import timedelta

from signalpilot.utils.constants import IST


def test_get_candle_bucket_aligns_to_15min() -> None:
    """_get_candle_bucket should snap to 15-min boundaries."""
    # 9:15 bucket
    ts = datetime(2026, 2, 20, 9, 17, 30, tzinfo=IST)
    bucket = MarketDataStore._get_candle_bucket(ts)
    assert bucket.minute == 15
    assert bucket.second == 0
    assert bucket.microsecond == 0

    # 9:30 bucket
    ts2 = datetime(2026, 2, 20, 9, 35, 0, tzinfo=IST)
    bucket2 = MarketDataStore._get_candle_bucket(ts2)
    assert bucket2.minute == 30

    # 10:00 bucket
    ts3 = datetime(2026, 2, 20, 10, 14, 59, tzinfo=IST)
    bucket3 = MarketDataStore._get_candle_bucket(ts3)
    assert bucket3.minute == 0
    assert bucket3.hour == 10

    # 9:45 exact
    ts4 = datetime(2026, 2, 20, 9, 45, 0, tzinfo=IST)
    bucket4 = MarketDataStore._get_candle_bucket(ts4)
    assert bucket4.minute == 45


@pytest.mark.asyncio
async def test_update_candle_creates_candle(store: MarketDataStore) -> None:
    """First tick in a bucket creates a new candle with OHLC = price."""
    ts = datetime(2026, 2, 20, 9, 17, 0, tzinfo=IST)
    await store.update_candle("SBIN", price=100.0, volume=500.0, timestamp=ts)

    current = await store.get_current_candle("SBIN")
    assert current is not None
    assert current.open == 100.0
    assert current.high == 100.0
    assert current.low == 100.0
    assert current.close == 100.0
    assert current.volume == 500.0
    assert current.is_complete is False


@pytest.mark.asyncio
async def test_update_candle_updates_within_bucket(store: MarketDataStore) -> None:
    """Subsequent ticks within the same bucket update high/low/close/volume."""
    base_ts = datetime(2026, 2, 20, 9, 16, 0, tzinfo=IST)
    await store.update_candle("SBIN", price=100.0, volume=500.0, timestamp=base_ts)

    ts2 = datetime(2026, 2, 20, 9, 18, 0, tzinfo=IST)  # same 9:15 bucket
    await store.update_candle("SBIN", price=105.0, volume=300.0, timestamp=ts2)

    ts3 = datetime(2026, 2, 20, 9, 20, 0, tzinfo=IST)  # same 9:15 bucket
    await store.update_candle("SBIN", price=98.0, volume=200.0, timestamp=ts3)

    current = await store.get_current_candle("SBIN")
    assert current is not None
    assert current.open == 100.0
    assert current.high == 105.0
    assert current.low == 98.0
    assert current.close == 98.0
    assert current.volume == pytest.approx(1000.0)


@pytest.mark.asyncio
async def test_candle_completion_on_new_bucket(store: MarketDataStore) -> None:
    """When a tick arrives in a new bucket, the previous candle is finalized."""
    ts1 = datetime(2026, 2, 20, 9, 16, 0, tzinfo=IST)  # bucket: 9:15
    await store.update_candle("SBIN", price=100.0, volume=500.0, timestamp=ts1)

    ts2 = datetime(2026, 2, 20, 9, 31, 0, tzinfo=IST)  # bucket: 9:30 -> completes 9:15
    await store.update_candle("SBIN", price=110.0, volume=600.0, timestamp=ts2)

    completed = await store.get_completed_candles("SBIN")
    assert len(completed) == 1
    assert completed[0].is_complete is True
    assert completed[0].open == 100.0
    assert completed[0].start_time.minute == 15

    # Current candle is the new one
    current = await store.get_current_candle("SBIN")
    assert current is not None
    assert current.open == 110.0
    assert current.start_time.minute == 30


@pytest.mark.asyncio
async def test_get_current_candle_returns_none_for_unknown(store: MarketDataStore) -> None:
    """get_current_candle returns None for a symbol with no candles."""
    assert await store.get_current_candle("UNKNOWN") is None


@pytest.mark.asyncio
async def test_get_avg_candle_volume_excludes_current(store: MarketDataStore) -> None:
    """Average candle volume should only include completed candles."""
    # Build 3 completed candles + 1 in progress
    base = datetime(2026, 2, 20, 9, 15, 0, tzinfo=IST)
    for i in range(4):
        ts = base + timedelta(minutes=15 * i + 1)
        volume = (i + 1) * 100.0  # 100, 200, 300, 400
        await store.update_candle("SBIN", price=100.0, volume=volume, timestamp=ts)

    # 3 completed candles with volumes 100, 200, 300. Current (400) excluded.
    completed = await store.get_completed_candles("SBIN")
    assert len(completed) == 3

    avg = await store.get_avg_candle_volume("SBIN")
    assert avg == pytest.approx(200.0)  # (100+200+300)/3


@pytest.mark.asyncio
async def test_get_avg_candle_volume_no_completed(store: MarketDataStore) -> None:
    """Returns 0.0 when there are no completed candles."""
    ts = datetime(2026, 2, 20, 9, 16, 0, tzinfo=IST)
    await store.update_candle("SBIN", price=100.0, volume=500.0, timestamp=ts)

    avg = await store.get_avg_candle_volume("SBIN")
    assert avg == 0.0


@pytest.mark.asyncio
async def test_clear_also_clears_phase2_data(store: MarketDataStore) -> None:
    """clear() should remove opening ranges, VWAP state, and candles."""
    await store.update_opening_range("SBIN", high=105.0, low=100.0)
    await store.update_vwap("SBIN", price=100.0, volume=10.0)
    ts = datetime(2026, 2, 20, 9, 16, 0, tzinfo=IST)
    await store.update_candle("SBIN", price=100.0, volume=500.0, timestamp=ts)

    await store.clear()

    assert await store.get_opening_range("SBIN") is None
    assert await store.get_vwap("SBIN") is None
    assert await store.get_current_candle("SBIN") is None
    assert await store.get_completed_candles("SBIN") == []
