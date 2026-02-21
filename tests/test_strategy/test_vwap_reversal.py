"""Tests for VWAPReversalStrategy."""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from signalpilot.config import AppConfig
from signalpilot.data.market_data_store import MarketDataStore
from signalpilot.db.models import TickData
from signalpilot.monitor.vwap_cooldown import VWAPCooldownTracker
from signalpilot.strategy.vwap_reversal import VWAPReversalStrategy
from signalpilot.utils.constants import IST
from signalpilot.utils.market_calendar import StrategyPhase

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(**overrides) -> AppConfig:
    """Build AppConfig with test defaults."""
    defaults = dict(
        angel_api_key="k",
        angel_client_id="c",
        angel_mpin="1234",
        angel_totp_secret="JBSWY3DPEHPK3PXP",
        telegram_bot_token="0:AAA",
        telegram_chat_id="1",
        vwap_scan_start="10:00",
        vwap_scan_end="14:30",
        vwap_touch_threshold_pct=0.3,
        vwap_reclaim_volume_multiplier=1.5,
        vwap_pullback_volume_multiplier=1.0,
        vwap_setup1_sl_below_vwap_pct=0.5,
        vwap_setup1_target1_pct=1.0,
        vwap_setup1_target2_pct=1.5,
        vwap_setup2_target1_pct=1.5,
        vwap_setup2_target2_pct=2.0,
    )
    defaults.update(overrides)
    return AppConfig(**defaults)


def _make_tick(symbol: str, ltp: float) -> TickData:
    now = datetime.now()
    return TickData(
        symbol=symbol,
        ltp=ltp,
        open_price=ltp - 1,
        high=ltp + 2,
        low=ltp - 2,
        close=0.0,
        volume=5000,
        last_traded_timestamp=now,
        updated_at=now,
    )


async def _build_candle_history(
    store: MarketDataStore,
    symbol: str,
    candle_data: list[dict],
    vwap: float,
    base_time: datetime | None = None,
) -> None:
    """Build a series of completed 15-min candles and set VWAP.

    candle_data is a list of dicts with keys: open, high, low, close, volume.
    Each candle is placed in successive 15-minute buckets.
    """
    if base_time is None:
        base_time = datetime(2026, 2, 20, 10, 0, 0, tzinfo=IST)

    for i, cd in enumerate(candle_data):
        bucket_start = base_time + timedelta(minutes=15 * i)
        # First tick in this bucket creates or opens a new candle
        ts_open = bucket_start + timedelta(seconds=1)
        await store.update_candle(symbol, price=cd["open"], volume=0, timestamp=ts_open)

        # Update high
        if cd["high"] > cd["open"]:
            ts_h = bucket_start + timedelta(seconds=2)
            await store.update_candle(symbol, price=cd["high"], volume=0, timestamp=ts_h)

        # Update low
        if cd["low"] < min(cd["open"], cd.get("high", cd["open"])):
            ts_l = bucket_start + timedelta(seconds=3)
            await store.update_candle(symbol, price=cd["low"], volume=0, timestamp=ts_l)

        # Close + volume
        ts_close = bucket_start + timedelta(seconds=4)
        await store.update_candle(
            symbol, price=cd["close"], volume=cd["volume"], timestamp=ts_close
        )

    # Now create one more tick in the next bucket to finalize the last candle
    final_bucket = base_time + timedelta(minutes=15 * len(candle_data))
    await store.update_candle(symbol, price=candle_data[-1]["close"], volume=0, timestamp=final_bucket)

    # Set the tick data so get_all_ticks finds this symbol
    await store.update_tick(symbol, _make_tick(symbol, ltp=candle_data[-1]["close"]))

    # Set VWAP
    await store.update_vwap(symbol, price=vwap, volume=1.0)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config() -> AppConfig:
    return _make_config()


@pytest.fixture
def store() -> MarketDataStore:
    return MarketDataStore()


@pytest.fixture
def cooldown() -> VWAPCooldownTracker:
    return VWAPCooldownTracker(max_signals_per_stock=2, cooldown_minutes=60)


@pytest.fixture
def strategy(
    config: AppConfig, store: MarketDataStore, cooldown: VWAPCooldownTracker
) -> VWAPReversalStrategy:
    return VWAPReversalStrategy(config, store, cooldown)


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


def test_name(strategy: VWAPReversalStrategy) -> None:
    assert strategy.name == "VWAP Reversal"


def test_active_phases(strategy: VWAPReversalStrategy) -> None:
    assert strategy.active_phases == [StrategyPhase.CONTINUOUS]


# ══════════════════════════════════════════════════════════════════
# Setup 1: Uptrend Pullback
# ══════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_setup1_valid_uptrend_pullback(
    strategy: VWAPReversalStrategy, store: MarketDataStore
) -> None:
    """Setup 1: prior candle above VWAP, touch VWAP, bounce above, volume OK -> signal."""
    vwap = 100.0
    candles = [
        # Prior candle: close above VWAP
        {"open": 101.0, "high": 103.0, "low": 100.5, "close": 102.0, "volume": 1000.0},
        # Current candle: low touches VWAP (within 0.3%), closes above VWAP
        {"open": 101.5, "high": 102.5, "low": 99.8, "close": 101.0, "volume": 1200.0},
    ]

    await _build_candle_history(store, "SBIN", candles, vwap=vwap)

    frozen_now = datetime(2026, 2, 20, 10, 45, 0, tzinfo=IST)
    with patch("signalpilot.strategy.vwap_reversal.datetime") as mock_dt:
        mock_dt.now.return_value = frozen_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        signals = await strategy.evaluate(store, StrategyPhase.CONTINUOUS)

    assert len(signals) == 1
    sig = signals[0]
    assert sig.symbol == "SBIN"
    assert sig.strategy_name == "VWAP Reversal"
    assert sig.setup_type == "uptrend_pullback"
    assert "VWAP pullback" in sig.reason


@pytest.mark.asyncio
async def test_setup1_rejection_no_prior_above_vwap(
    strategy: VWAPReversalStrategy, store: MarketDataStore
) -> None:
    """Setup 1 rejected when prior candle closes below VWAP."""
    vwap = 100.0
    candles = [
        # Prior candle: close BELOW VWAP
        {"open": 99.0, "high": 100.5, "low": 98.5, "close": 99.5, "volume": 1000.0},
        # Current candle: touches VWAP, closes above
        {"open": 99.5, "high": 101.0, "low": 99.8, "close": 100.5, "volume": 1200.0},
    ]

    await _build_candle_history(store, "SBIN", candles, vwap=vwap)

    frozen_now = datetime(2026, 2, 20, 10, 45, 0, tzinfo=IST)
    with patch("signalpilot.strategy.vwap_reversal.datetime") as mock_dt:
        mock_dt.now.return_value = frozen_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        signals = await strategy.evaluate(store, StrategyPhase.CONTINUOUS)

    # Prior below VWAP fails setup 1; could match setup 2 if volume is high enough
    # With 1.2x volume and 1.5x threshold, setup 2 also fails
    setup1_signals = [s for s in signals if s.setup_type == "uptrend_pullback"]
    assert len(setup1_signals) == 0


@pytest.mark.asyncio
async def test_setup1_rejection_no_vwap_touch(
    strategy: VWAPReversalStrategy, store: MarketDataStore
) -> None:
    """Setup 1 rejected when candle low is far from VWAP (no touch)."""
    vwap = 100.0
    candles = [
        # Prior candle: close above VWAP
        {"open": 102.0, "high": 104.0, "low": 101.5, "close": 103.0, "volume": 1000.0},
        # Current candle: low = 102.0 -> distance from VWAP = 2% >> 0.3% threshold
        {"open": 103.0, "high": 104.0, "low": 102.0, "close": 103.5, "volume": 1200.0},
    ]

    await _build_candle_history(store, "SBIN", candles, vwap=vwap)

    frozen_now = datetime(2026, 2, 20, 10, 45, 0, tzinfo=IST)
    with patch("signalpilot.strategy.vwap_reversal.datetime") as mock_dt:
        mock_dt.now.return_value = frozen_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        signals = await strategy.evaluate(store, StrategyPhase.CONTINUOUS)

    setup1_signals = [s for s in signals if s.setup_type == "uptrend_pullback"]
    assert len(setup1_signals) == 0


@pytest.mark.asyncio
async def test_setup1_rejection_close_below_vwap(
    strategy: VWAPReversalStrategy, store: MarketDataStore
) -> None:
    """Setup 1 rejected when current candle closes below VWAP (no bounce)."""
    vwap = 100.0
    candles = [
        {"open": 101.0, "high": 103.0, "low": 100.5, "close": 102.0, "volume": 1000.0},
        # Current: touches VWAP but closes below
        {"open": 101.0, "high": 101.5, "low": 99.8, "close": 99.5, "volume": 1200.0},
    ]

    await _build_candle_history(store, "SBIN", candles, vwap=vwap)

    frozen_now = datetime(2026, 2, 20, 10, 45, 0, tzinfo=IST)
    with patch("signalpilot.strategy.vwap_reversal.datetime") as mock_dt:
        mock_dt.now.return_value = frozen_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        signals = await strategy.evaluate(store, StrategyPhase.CONTINUOUS)

    assert len(signals) == 0


@pytest.mark.asyncio
async def test_setup1_rejection_insufficient_volume(
    strategy: VWAPReversalStrategy, store: MarketDataStore
) -> None:
    """Setup 1 rejected when bounce volume < avg (pullback_volume_multiplier = 1.0)."""
    vwap = 100.0
    candles = [
        # First two candles provide avg volume = 1000
        {"open": 101.0, "high": 103.0, "low": 100.5, "close": 102.0, "volume": 1000.0},
        # Current candle: valid setup but volume = 500 < avg 1000
        {"open": 101.5, "high": 102.5, "low": 99.8, "close": 101.0, "volume": 500.0},
    ]

    await _build_candle_history(store, "SBIN", candles, vwap=vwap)

    frozen_now = datetime(2026, 2, 20, 10, 45, 0, tzinfo=IST)
    with patch("signalpilot.strategy.vwap_reversal.datetime") as mock_dt:
        mock_dt.now.return_value = frozen_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        signals = await strategy.evaluate(store, StrategyPhase.CONTINUOUS)

    setup1_signals = [s for s in signals if s.setup_type == "uptrend_pullback"]
    assert len(setup1_signals) == 0


# ══════════════════════════════════════════════════════════════════
# Setup 2: VWAP Reclaim
# ══════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_setup2_valid_vwap_reclaim(
    strategy: VWAPReversalStrategy, store: MarketDataStore
) -> None:
    """Setup 2: prior below VWAP, close above, volume >= 1.5x -> signal with Higher Risk.

    Note: avg_vol is computed across ALL completed candles (including the one being
    analysed). We need 3 candles so the average stays low enough for the reclaim
    candle's volume to clear the 1.5x threshold.
    """
    vwap = 100.0
    candles = [
        # Early candle: brings avg volume down
        {"open": 98.0, "high": 99.5, "low": 97.5, "close": 98.5, "volume": 600.0},
        # Prior candle: close below VWAP
        {"open": 99.0, "high": 100.0, "low": 98.0, "close": 99.0, "volume": 600.0},
        # Reclaim candle: closes above VWAP, volume = 2400 >= 1.5 * avg(600,600,2400)=1200
        {"open": 99.5, "high": 101.5, "low": 99.0, "close": 101.0, "volume": 2400.0},
    ]

    await _build_candle_history(store, "SBIN", candles, vwap=vwap)

    frozen_now = datetime(2026, 2, 20, 10, 45, 0, tzinfo=IST)
    with patch("signalpilot.strategy.vwap_reversal.datetime") as mock_dt:
        mock_dt.now.return_value = frozen_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        signals = await strategy.evaluate(store, StrategyPhase.CONTINUOUS)

    assert len(signals) == 1
    sig = signals[0]
    assert sig.setup_type == "vwap_reclaim"
    assert "Higher Risk" in sig.reason
    assert sig.entry_price == 101.0


@pytest.mark.asyncio
async def test_setup2_rejection_volume_below_1_5x(
    strategy: VWAPReversalStrategy, store: MarketDataStore
) -> None:
    """Setup 2 rejected when volume < 1.5x average."""
    vwap = 100.0
    candles = [
        {"open": 99.0, "high": 100.0, "low": 98.0, "close": 99.0, "volume": 1000.0},
        # Volume 1200 = 1.2x < 1.5x
        {"open": 99.5, "high": 101.5, "low": 99.0, "close": 101.0, "volume": 1200.0},
    ]

    await _build_candle_history(store, "SBIN", candles, vwap=vwap)

    frozen_now = datetime(2026, 2, 20, 10, 45, 0, tzinfo=IST)
    with patch("signalpilot.strategy.vwap_reversal.datetime") as mock_dt:
        mock_dt.now.return_value = frozen_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        signals = await strategy.evaluate(store, StrategyPhase.CONTINUOUS)

    assert len(signals) == 0


@pytest.mark.asyncio
async def test_setup2_rejection_already_above_vwap(
    strategy: VWAPReversalStrategy, store: MarketDataStore
) -> None:
    """Setup 2 rejected when prior candle already above VWAP (not a reclaim)."""
    vwap = 100.0
    candles = [
        # Prior candle close ABOVE VWAP -> not a reclaim scenario
        {"open": 101.0, "high": 103.0, "low": 100.5, "close": 102.0, "volume": 1000.0},
        {"open": 102.0, "high": 103.0, "low": 101.5, "close": 102.5, "volume": 1800.0},
    ]

    await _build_candle_history(store, "SBIN", candles, vwap=vwap)

    frozen_now = datetime(2026, 2, 20, 10, 45, 0, tzinfo=IST)
    with patch("signalpilot.strategy.vwap_reversal.datetime") as mock_dt:
        mock_dt.now.return_value = frozen_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        signals = await strategy.evaluate(store, StrategyPhase.CONTINUOUS)

    setup2_signals = [s for s in signals if s.setup_type == "vwap_reclaim"]
    assert len(setup2_signals) == 0


# ══════════════════════════════════════════════════════════════════
# Time window checks
# ══════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_no_signals_before_10am(
    strategy: VWAPReversalStrategy, store: MarketDataStore
) -> None:
    """No signals should be generated before 10:00 AM scan start."""
    vwap = 100.0
    candles = [
        {"open": 101.0, "high": 103.0, "low": 100.5, "close": 102.0, "volume": 1000.0},
        {"open": 101.5, "high": 102.5, "low": 99.8, "close": 101.0, "volume": 1200.0},
    ]
    await _build_candle_history(store, "SBIN", candles, vwap=vwap)

    frozen_now = datetime(2026, 2, 20, 9, 55, 0, tzinfo=IST)
    with patch("signalpilot.strategy.vwap_reversal.datetime") as mock_dt:
        mock_dt.now.return_value = frozen_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        signals = await strategy.evaluate(store, StrategyPhase.CONTINUOUS)

    assert len(signals) == 0


@pytest.mark.asyncio
async def test_no_signals_after_1430(
    strategy: VWAPReversalStrategy, store: MarketDataStore
) -> None:
    """No signals should be generated at or after 14:30."""
    vwap = 100.0
    candles = [
        {"open": 101.0, "high": 103.0, "low": 100.5, "close": 102.0, "volume": 1000.0},
        {"open": 101.5, "high": 102.5, "low": 99.8, "close": 101.0, "volume": 1200.0},
    ]
    await _build_candle_history(store, "SBIN", candles, vwap=vwap)

    frozen_now = datetime(2026, 2, 20, 14, 30, 0, tzinfo=IST)
    with patch("signalpilot.strategy.vwap_reversal.datetime") as mock_dt:
        mock_dt.now.return_value = frozen_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        signals = await strategy.evaluate(store, StrategyPhase.CONTINUOUS)

    assert len(signals) == 0


# ══════════════════════════════════════════════════════════════════
# Cooldown integration
# ══════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cooldown_blocks_signal(
    config: AppConfig, store: MarketDataStore
) -> None:
    """Cooldown tracker should prevent signals during cooldown period."""
    cooldown = VWAPCooldownTracker(max_signals_per_stock=2, cooldown_minutes=60)

    # Record a signal for SBIN at 10:30 so cooldown is active until 11:30
    t_signal = datetime(2026, 2, 20, 10, 30, 0, tzinfo=IST)
    cooldown.record_signal("SBIN", t_signal)

    strategy = VWAPReversalStrategy(config, store, cooldown)

    vwap = 100.0
    candles = [
        {"open": 101.0, "high": 103.0, "low": 100.5, "close": 102.0, "volume": 1000.0},
        {"open": 101.5, "high": 102.5, "low": 99.8, "close": 101.0, "volume": 1200.0},
    ]
    await _build_candle_history(store, "SBIN", candles, vwap=vwap)

    # Evaluate at 10:45 -> within cooldown window
    frozen_now = datetime(2026, 2, 20, 10, 45, 0, tzinfo=IST)
    with patch("signalpilot.strategy.vwap_reversal.datetime") as mock_dt:
        mock_dt.now.return_value = frozen_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        signals = await strategy.evaluate(store, StrategyPhase.CONTINUOUS)

    assert len(signals) == 0


# ══════════════════════════════════════════════════════════════════
# Reset
# ══════════════════════════════════════════════════════════════════


def test_reset_clears_state(strategy: VWAPReversalStrategy) -> None:
    """reset() should clear last_evaluated_candle and cooldown tracker."""
    strategy._last_evaluated_candle["SBIN"] = datetime(2026, 2, 20, 10, 0, 0, tzinfo=IST)
    strategy.reset()

    assert len(strategy._last_evaluated_candle) == 0


# ══════════════════════════════════════════════════════════════════
# Target / SL verification for Setup 1
# ══════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_setup1_targets_and_sl(
    strategy: VWAPReversalStrategy, store: MarketDataStore
) -> None:
    """Verify T1, T2 and SL calculations for Setup 1."""
    vwap = 100.0
    candles = [
        {"open": 101.0, "high": 103.0, "low": 100.5, "close": 102.0, "volume": 1000.0},
        {"open": 101.5, "high": 102.5, "low": 99.8, "close": 101.0, "volume": 1200.0},
    ]
    await _build_candle_history(store, "SBIN", candles, vwap=vwap)

    frozen_now = datetime(2026, 2, 20, 10, 45, 0, tzinfo=IST)
    with patch("signalpilot.strategy.vwap_reversal.datetime") as mock_dt:
        mock_dt.now.return_value = frozen_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        signals = await strategy.evaluate(store, StrategyPhase.CONTINUOUS)

    assert len(signals) == 1
    sig = signals[0]
    entry = sig.entry_price

    # SL = vwap * (1 - 0.5/100) = 100 * 0.995 = 99.5
    assert sig.stop_loss == pytest.approx(vwap * 0.995)
    # T1 = entry * (1 + 1.0/100)
    assert sig.target_1 == pytest.approx(entry * 1.01)
    # T2 = entry * (1 + 1.5/100)
    assert sig.target_2 == pytest.approx(entry * 1.015)


# ══════════════════════════════════════════════════════════════════
# Target / SL verification for Setup 2
# ══════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_setup2_targets(
    strategy: VWAPReversalStrategy, store: MarketDataStore
) -> None:
    """Verify T1, T2 and SL calculations for Setup 2."""
    vwap = 100.0
    candles = [
        # Early candle: brings avg vol down so reclaim candle's 2400 >= 1.5x avg
        {"open": 98.0, "high": 99.5, "low": 97.0, "close": 98.5, "volume": 600.0},
        # Prior candle: close below VWAP
        {"open": 99.0, "high": 100.0, "low": 98.0, "close": 99.0, "volume": 600.0},
        # Reclaim candle: close above VWAP, vol = 2400 >= 1.5 * 1200
        {"open": 99.5, "high": 101.5, "low": 99.0, "close": 101.0, "volume": 2400.0},
    ]
    await _build_candle_history(store, "SBIN", candles, vwap=vwap)

    frozen_now = datetime(2026, 2, 20, 10, 45, 0, tzinfo=IST)
    with patch("signalpilot.strategy.vwap_reversal.datetime") as mock_dt:
        mock_dt.now.return_value = frozen_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        signals = await strategy.evaluate(store, StrategyPhase.CONTINUOUS)

    assert len(signals) == 1
    sig = signals[0]
    entry = sig.entry_price  # 101.0

    # T1 = entry * (1 + 1.5/100)
    assert sig.target_1 == pytest.approx(entry * 1.015)
    # T2 = entry * (1 + 2.0/100)
    assert sig.target_2 == pytest.approx(entry * 1.02)

    # SL = min of last 3 candle lows: min(97.0, 98.0, 99.0) = 97.0
    assert sig.stop_loss == pytest.approx(97.0)
