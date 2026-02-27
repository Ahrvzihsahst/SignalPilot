"""Tests for ORBStrategy."""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from signalpilot.config import AppConfig
from signalpilot.data.market_data_store import MarketDataStore
from signalpilot.db.models import TickData
from signalpilot.strategy.orb import ORBStrategy
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
        # ORB-specific defaults
        orb_range_min_pct=0.5,
        orb_range_max_pct=3.0,
        orb_volume_multiplier=1.5,
        orb_signal_window_end="11:00",
        orb_target_1_pct=1.5,
        orb_target_2_pct=2.5,
        orb_gap_exclusion_pct=3.0,
        max_risk_pct=3.0,
    )
    defaults.update(overrides)
    return AppConfig(**defaults)


def _make_tick(
    symbol: str,
    ltp: float,
    volume: int = 5000,
) -> TickData:
    now = datetime.now()
    return TickData(
        symbol=symbol,
        ltp=ltp,
        open_price=ltp - 1,
        high=ltp + 2,
        low=ltp - 2,
        close=0.0,
        volume=volume,
        last_traded_timestamp=now,
        updated_at=now,
    )


async def _setup_valid_breakout(
    store: MarketDataStore,
    symbol: str = "SBIN",
    range_high: float = 100.0,
    range_low: float = 98.0,
    ltp: float = 101.0,
    avg_vol: float = 1000.0,
    current_vol: float = 2000.0,
) -> None:
    """Set up a valid ORB breakout scenario in the store.

    Creates a locked opening range, a current candle with sufficient volume,
    and completed candles for the average volume calculation.
    """
    # 1. Set opening range and lock it
    await store.update_opening_range(symbol, high=range_high, low=range_low)
    await store.lock_opening_ranges()

    # 2. Set tick data with ltp above range_high
    await store.update_tick(symbol, _make_tick(symbol, ltp=ltp))

    # 3. Build completed candles so get_avg_candle_volume returns avg_vol
    # We need at least 1 completed candle and 1 current candle
    base_ts = datetime(2026, 2, 20, 9, 45, 0, tzinfo=IST)

    # First candle in 9:45 bucket (will be completed when 10:00 tick arrives)
    await store.update_candle(symbol, price=99.0, volume=avg_vol, timestamp=base_ts)

    # Tick in 10:00 bucket completes the 9:45 candle and starts a new one
    ts2 = base_ts + timedelta(minutes=15, seconds=1)
    await store.update_candle(symbol, price=ltp, volume=current_vol, timestamp=ts2)


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
def strategy(config: AppConfig, store: MarketDataStore) -> ORBStrategy:
    return ORBStrategy(config, store)


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


def test_name(strategy: ORBStrategy) -> None:
    assert strategy.name == "ORB"


def test_active_phases(strategy: ORBStrategy) -> None:
    assert strategy.active_phases == [StrategyPhase.CONTINUOUS]


# ---------------------------------------------------------------------------
# Valid breakout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_breakout_generates_signal(
    strategy: ORBStrategy, store: MarketDataStore
) -> None:
    """Valid breakout: locked range, ltp > range_high, volume >= 1.5x,
    range 0.5-3%, risk <= 3% -> CandidateSignal produced."""
    await _setup_valid_breakout(
        store,
        symbol="SBIN",
        range_high=100.0,
        range_low=98.0,  # range_size_pct = (100-98)/98*100 = 2.04%
        ltp=101.0,
        avg_vol=1000.0,
        current_vol=2000.0,  # 2.0x > 1.5x
    )

    # Freeze time to within signal window (before 11:00)
    frozen_now = datetime(2026, 2, 20, 10, 30, 0, tzinfo=IST)
    with patch("signalpilot.strategy.orb.datetime") as mock_dt:
        mock_dt.now.return_value = frozen_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        signals = await strategy.evaluate(store, StrategyPhase.CONTINUOUS)

    assert len(signals) == 1
    sig = signals[0]
    assert sig.symbol == "SBIN"
    assert sig.strategy_name == "ORB"
    assert sig.entry_price == 101.0
    assert sig.stop_loss == 98.0  # range_low
    assert "ORB breakout" in sig.reason


# ---------------------------------------------------------------------------
# Range not locked -> no signal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_range_not_locked_no_signal(
    strategy: ORBStrategy, store: MarketDataStore
) -> None:
    """If opening range is not locked, no signals should be generated."""
    # Set opening range but do NOT lock
    await store.update_opening_range("SBIN", high=100.0, low=98.0)
    await store.update_tick("SBIN", _make_tick("SBIN", ltp=101.0))

    frozen_now = datetime(2026, 2, 20, 10, 30, 0, tzinfo=IST)
    with patch("signalpilot.strategy.orb.datetime") as mock_dt:
        mock_dt.now.return_value = frozen_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        signals = await strategy.evaluate(store, StrategyPhase.CONTINUOUS)

    assert len(signals) == 0


# ---------------------------------------------------------------------------
# Range too small (< 0.5%)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_range_too_small_no_signal(
    strategy: ORBStrategy, store: MarketDataStore
) -> None:
    """Range size below min threshold (< 0.5%) should skip the stock."""
    # range_size_pct = (100.3 - 100.0)/100.0 * 100 = 0.3%
    await _setup_valid_breakout(
        store,
        symbol="SBIN",
        range_high=100.3,
        range_low=100.0,
        ltp=101.0,
        avg_vol=1000.0,
        current_vol=2000.0,
    )

    frozen_now = datetime(2026, 2, 20, 10, 30, 0, tzinfo=IST)
    with patch("signalpilot.strategy.orb.datetime") as mock_dt:
        mock_dt.now.return_value = frozen_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        signals = await strategy.evaluate(store, StrategyPhase.CONTINUOUS)

    assert len(signals) == 0


# ---------------------------------------------------------------------------
# Range too large (> 3%)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_range_too_large_no_signal(
    strategy: ORBStrategy, store: MarketDataStore
) -> None:
    """Range size above max threshold (> 3%) should skip the stock."""
    # range_size_pct = (110 - 106)/106 * 100 = 3.77%
    await _setup_valid_breakout(
        store,
        symbol="SBIN",
        range_high=110.0,
        range_low=106.0,
        ltp=111.0,
        avg_vol=1000.0,
        current_vol=2000.0,
    )

    frozen_now = datetime(2026, 2, 20, 10, 30, 0, tzinfo=IST)
    with patch("signalpilot.strategy.orb.datetime") as mock_dt:
        mock_dt.now.return_value = frozen_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        signals = await strategy.evaluate(store, StrategyPhase.CONTINUOUS)

    assert len(signals) == 0


# ---------------------------------------------------------------------------
# Gap excluded stock
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gap_excluded_stock_no_signal(
    strategy: ORBStrategy, store: MarketDataStore
) -> None:
    """A stock marked as gap-excluded by Gap & Go should not generate an ORB signal."""
    await _setup_valid_breakout(store, symbol="SBIN")

    strategy.mark_gap_stock("SBIN")

    frozen_now = datetime(2026, 2, 20, 10, 30, 0, tzinfo=IST)
    with patch("signalpilot.strategy.orb.datetime") as mock_dt:
        mock_dt.now.return_value = frozen_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        signals = await strategy.evaluate(store, StrategyPhase.CONTINUOUS)

    assert len(signals) == 0


# ---------------------------------------------------------------------------
# Volume below 1.5x
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_volume_below_threshold_no_signal(
    strategy: ORBStrategy, store: MarketDataStore
) -> None:
    """Volume below 1.5x average should not produce a signal."""
    await _setup_valid_breakout(
        store,
        symbol="SBIN",
        range_high=100.0,
        range_low=98.0,
        ltp=101.0,
        avg_vol=1000.0,
        current_vol=1200.0,  # 1.2x < 1.5x
    )

    frozen_now = datetime(2026, 2, 20, 10, 30, 0, tzinfo=IST)
    with patch("signalpilot.strategy.orb.datetime") as mock_dt:
        mock_dt.now.return_value = frozen_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        signals = await strategy.evaluate(store, StrategyPhase.CONTINUOUS)

    assert len(signals) == 0


# ---------------------------------------------------------------------------
# Risk exceeding 3%
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_risk_exceeding_max_no_signal(
    strategy: ORBStrategy, store: MarketDataStore
) -> None:
    """Risk (entry - range_low) / entry > 3% should reject the breakout."""
    # range_low=90.0, ltp=101.0 -> risk = (101-90)/101*100 = 10.89%
    await _setup_valid_breakout(
        store,
        symbol="SBIN",
        range_high=100.0,
        range_low=90.0,
        ltp=101.0,
        avg_vol=1000.0,
        current_vol=2000.0,
    )
    # range_size_pct = (100-90)/90*100 = 11.11% which is > 3%, already filtered
    # Let's use a more realistic scenario where range is OK but risk is high
    # Actually the range filter catches this first. Let's set max_risk_pct very low.
    config = _make_config(max_risk_pct=1.0)
    strat = ORBStrategy(config, store)

    # Need range within 0.5-3% but risk > 1%
    store2 = MarketDataStore()
    await _setup_valid_breakout(
        store2,
        symbol="TCS",
        range_high=100.0,
        range_low=98.0,  # range = 2.04% (OK), risk = (101-98)/101*100 = 2.97% > 1%
        ltp=101.0,
        avg_vol=1000.0,
        current_vol=2000.0,
    )

    frozen_now = datetime(2026, 2, 20, 10, 30, 0, tzinfo=IST)
    with patch("signalpilot.strategy.orb.datetime") as mock_dt:
        mock_dt.now.return_value = frozen_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        signals = await strat.evaluate(store2, StrategyPhase.CONTINUOUS)

    assert len(signals) == 0


# ---------------------------------------------------------------------------
# After 11:00 AM -> no signal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_after_signal_window_end_no_signal(
    strategy: ORBStrategy, store: MarketDataStore
) -> None:
    """No signals should be generated after 11:00 AM."""
    await _setup_valid_breakout(store, symbol="SBIN")

    frozen_now = datetime(2026, 2, 20, 11, 0, 0, tzinfo=IST)
    with patch("signalpilot.strategy.orb.datetime") as mock_dt:
        mock_dt.now.return_value = frozen_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        signals = await strategy.evaluate(store, StrategyPhase.CONTINUOUS)

    assert len(signals) == 0


@pytest.mark.asyncio
async def test_after_signal_window_end_11_30_no_signal(
    strategy: ORBStrategy, store: MarketDataStore
) -> None:
    """No signals after 11:30 AM either."""
    await _setup_valid_breakout(store, symbol="SBIN")

    frozen_now = datetime(2026, 2, 20, 11, 30, 0, tzinfo=IST)
    with patch("signalpilot.strategy.orb.datetime") as mock_dt:
        mock_dt.now.return_value = frozen_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        signals = await strategy.evaluate(store, StrategyPhase.CONTINUOUS)

    assert len(signals) == 0


# ---------------------------------------------------------------------------
# SL and target calculations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sl_at_range_low_and_targets_correct(
    strategy: ORBStrategy, store: MarketDataStore
) -> None:
    """SL should be at range_low, T1 = entry*(1+1.5%), T2 = entry*(1+2.5%)."""
    await _setup_valid_breakout(
        store,
        symbol="SBIN",
        range_high=100.0,
        range_low=98.0,
        ltp=101.0,
        avg_vol=1000.0,
        current_vol=2000.0,
    )

    frozen_now = datetime(2026, 2, 20, 10, 30, 0, tzinfo=IST)
    with patch("signalpilot.strategy.orb.datetime") as mock_dt:
        mock_dt.now.return_value = frozen_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        signals = await strategy.evaluate(store, StrategyPhase.CONTINUOUS)

    assert len(signals) == 1
    sig = signals[0]
    assert sig.stop_loss == 98.0  # range_low
    assert sig.target_1 == pytest.approx(101.0 * 1.015)  # 1.5%
    assert sig.target_2 == pytest.approx(101.0 * 1.025)  # 2.5%


# ---------------------------------------------------------------------------
# mark_gap_stock excludes correctly
# ---------------------------------------------------------------------------


def test_mark_gap_stock(strategy: ORBStrategy) -> None:
    """mark_gap_stock should add symbol to exclusion set."""
    strategy.mark_gap_stock("SBIN")
    strategy.mark_gap_stock("TCS")

    assert "SBIN" in strategy._excluded_stocks
    assert "TCS" in strategy._excluded_stocks
    assert "RELIANCE" not in strategy._excluded_stocks


# ---------------------------------------------------------------------------
# reset() clears state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reset_clears_state(
    strategy: ORBStrategy, store: MarketDataStore
) -> None:
    """reset() should clear signals_generated and excluded_stocks."""
    await _setup_valid_breakout(store, symbol="SBIN")
    strategy.mark_gap_stock("TCS")

    frozen_now = datetime(2026, 2, 20, 10, 30, 0, tzinfo=IST)
    with patch("signalpilot.strategy.orb.datetime") as mock_dt:
        mock_dt.now.return_value = frozen_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        signals = await strategy.evaluate(store, StrategyPhase.CONTINUOUS)

    assert len(signals) == 1
    assert "SBIN" in strategy._signals_generated
    assert "TCS" in strategy._excluded_stocks

    strategy.reset()

    assert len(strategy._signals_generated) == 0
    assert len(strategy._excluded_stocks) == 0


# ---------------------------------------------------------------------------
# No duplicate ORB signal for same stock in same session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_duplicate_signal_same_session(
    strategy: ORBStrategy, store: MarketDataStore
) -> None:
    """Once an ORB signal is generated for a stock, no second signal in the same session."""
    await _setup_valid_breakout(store, symbol="SBIN")

    frozen_now = datetime(2026, 2, 20, 10, 30, 0, tzinfo=IST)
    with patch("signalpilot.strategy.orb.datetime") as mock_dt:
        mock_dt.now.return_value = frozen_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        signals_1 = await strategy.evaluate(store, StrategyPhase.CONTINUOUS)

    assert len(signals_1) == 1

    with patch("signalpilot.strategy.orb.datetime") as mock_dt:
        mock_dt.now.return_value = frozen_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        signals_2 = await strategy.evaluate(store, StrategyPhase.CONTINUOUS)

    assert len(signals_2) == 0


# ---------------------------------------------------------------------------
# Price at range_high exactly (no breakout)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ltp_at_range_high_no_signal(
    strategy: ORBStrategy, store: MarketDataStore
) -> None:
    """ltp exactly at range_high is not a breakout (must be strictly above)."""
    await _setup_valid_breakout(
        store,
        symbol="SBIN",
        range_high=100.0,
        range_low=98.0,
        ltp=100.0,  # exactly at range_high
        avg_vol=1000.0,
        current_vol=2000.0,
    )

    frozen_now = datetime(2026, 2, 20, 10, 30, 0, tzinfo=IST)
    with patch("signalpilot.strategy.orb.datetime") as mock_dt:
        mock_dt.now.return_value = frozen_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        signals = await strategy.evaluate(store, StrategyPhase.CONTINUOUS)

    assert len(signals) == 0


# ---------------------------------------------------------------------------
# Multiple stocks can generate signals
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multiple_stocks_generate_signals(
    config: AppConfig,
) -> None:
    """Multiple stocks meeting criteria should all produce signals."""
    store = MarketDataStore()
    strategy = ORBStrategy(config, store)

    for sym in ("SBIN", "TCS"):
        await _setup_valid_breakout(
            store,
            symbol=sym,
            range_high=100.0,
            range_low=98.0,
            ltp=101.0,
            avg_vol=1000.0,
            current_vol=2000.0,
        )

    frozen_now = datetime(2026, 2, 20, 10, 30, 0, tzinfo=IST)
    with patch("signalpilot.strategy.orb.datetime") as mock_dt:
        mock_dt.now.return_value = frozen_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        signals = await strategy.evaluate(store, StrategyPhase.CONTINUOUS)

    assert len(signals) == 2
    symbols = {s.symbol for s in signals}
    assert symbols == {"SBIN", "TCS"}
