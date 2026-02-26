"""Tests for GapAndGoStrategy."""

from datetime import datetime

import pytest

from signalpilot.config import AppConfig
from signalpilot.data.market_data_store import MarketDataStore
from signalpilot.db.models import HistoricalReference, TickData
from signalpilot.strategy.gap_and_go import GapAndGoStrategy
from signalpilot.utils.market_calendar import StrategyPhase


def _make_config(**overrides) -> AppConfig:
    """Build AppConfig with test defaults."""
    defaults = dict(
        angel_api_key="k",
        angel_client_id="c",
        angel_mpin="1234",
        angel_totp_secret="JBSWY3DPEHPK3PXP",
        telegram_bot_token="0:AAA",
        telegram_chat_id="1",
        gap_min_pct=3.0,
        gap_max_pct=5.0,
        volume_threshold_pct=50.0,
        target_1_pct=5.0,
        target_2_pct=7.0,
        max_risk_pct=3.0,
    )
    defaults.update(overrides)
    return AppConfig(**defaults)


def _make_tick(
    symbol: str,
    ltp: float,
    open_price: float,
    volume: int = 5000,
) -> TickData:
    now = datetime.now()
    return TickData(
        symbol=symbol,
        ltp=ltp,
        open_price=open_price,
        high=open_price + 5,
        low=open_price - 1,
        close=0.0,
        volume=volume,
        last_traded_timestamp=now,
        updated_at=now,
    )


def _make_historical(
    prev_close: float,
    prev_high: float,
    adv: float = 10000.0,
) -> HistoricalReference:
    return HistoricalReference(
        previous_close=prev_close,
        previous_high=prev_high,
        average_daily_volume=adv,
    )


@pytest.fixture
def config() -> AppConfig:
    return _make_config()


@pytest.fixture
def strategy(config: AppConfig) -> GapAndGoStrategy:
    return GapAndGoStrategy(config)


@pytest.fixture
def store() -> MarketDataStore:
    return MarketDataStore()


# ── Properties ───────────────────────────────────────────────────


def test_name(strategy: GapAndGoStrategy) -> None:
    assert strategy.name == "Gap & Go"


def test_active_phases(strategy: GapAndGoStrategy) -> None:
    assert strategy.active_phases == [StrategyPhase.OPENING, StrategyPhase.ENTRY_WINDOW]


# ── Gap detection boundaries ─────────────────────────────────────


@pytest.mark.asyncio
async def test_gap_at_exact_3pct_boundary_included(
    strategy: GapAndGoStrategy, store: MarketDataStore
) -> None:
    """Stock with exactly 3% gap should be detected as a candidate."""
    prev_close = 100.0
    open_price = 103.0  # Exactly 3%
    prev_high = 102.0  # Open above prev high

    await store.update_tick("SBIN", _make_tick("SBIN", ltp=103.5, open_price=open_price))
    await store.set_historical("SBIN", _make_historical(prev_close, prev_high))

    await strategy.evaluate(store, StrategyPhase.OPENING)

    assert "SBIN" in strategy._gap_candidates


@pytest.mark.asyncio
async def test_gap_at_exact_5pct_boundary_included(
    strategy: GapAndGoStrategy, store: MarketDataStore
) -> None:
    """Stock with exactly 5% gap should be detected as a candidate."""
    prev_close = 100.0
    open_price = 105.0  # Exactly 5%
    prev_high = 104.0

    await store.update_tick("SBIN", _make_tick("SBIN", ltp=105.5, open_price=open_price))
    await store.set_historical("SBIN", _make_historical(prev_close, prev_high))

    await strategy.evaluate(store, StrategyPhase.OPENING)

    assert "SBIN" in strategy._gap_candidates


@pytest.mark.asyncio
async def test_gap_below_3pct_excluded(
    strategy: GapAndGoStrategy, store: MarketDataStore
) -> None:
    """Stock with 2.9% gap should be excluded."""
    prev_close = 100.0
    open_price = 102.9  # 2.9% — below threshold
    prev_high = 102.0

    await store.update_tick("SBIN", _make_tick("SBIN", ltp=103.0, open_price=open_price))
    await store.set_historical("SBIN", _make_historical(prev_close, prev_high))

    await strategy.evaluate(store, StrategyPhase.OPENING)

    assert "SBIN" not in strategy._gap_candidates


@pytest.mark.asyncio
async def test_gap_above_5pct_excluded(
    strategy: GapAndGoStrategy, store: MarketDataStore
) -> None:
    """Stock with 5.1% gap should be excluded."""
    prev_close = 100.0
    open_price = 105.1  # 5.1% — above max
    prev_high = 104.0

    await store.update_tick("SBIN", _make_tick("SBIN", ltp=106.0, open_price=open_price))
    await store.set_historical("SBIN", _make_historical(prev_close, prev_high))

    await strategy.evaluate(store, StrategyPhase.OPENING)

    assert "SBIN" not in strategy._gap_candidates


@pytest.mark.asyncio
async def test_open_at_or_below_prev_high_excluded(
    strategy: GapAndGoStrategy, store: MarketDataStore
) -> None:
    """Stock where open <= prev high should be excluded even with valid gap."""
    prev_close = 100.0
    open_price = 104.0  # 4% gap — valid
    prev_high = 104.0  # open == prev_high → excluded

    await store.update_tick("SBIN", _make_tick("SBIN", ltp=104.5, open_price=open_price))
    await store.set_historical("SBIN", _make_historical(prev_close, prev_high))

    await strategy.evaluate(store, StrategyPhase.OPENING)

    assert "SBIN" not in strategy._gap_candidates


# ── Volume validation ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_volume_validation_pass(
    strategy: GapAndGoStrategy, store: MarketDataStore
) -> None:
    """Volume > 50% of ADV should pass validation."""
    prev_close = 100.0
    open_price = 104.0  # 4% gap
    prev_high = 103.0
    adv = 10000.0

    await store.update_tick("SBIN", _make_tick("SBIN", ltp=104.5, open_price=open_price))
    await store.set_historical("SBIN", _make_historical(prev_close, prev_high, adv))
    await store.accumulate_volume("SBIN", 6000)  # 60% of ADV

    await strategy.evaluate(store, StrategyPhase.OPENING)

    assert "SBIN" in strategy._gap_candidates
    assert "SBIN" in strategy._volume_validated


@pytest.mark.asyncio
async def test_volume_validation_fail(
    strategy: GapAndGoStrategy, store: MarketDataStore
) -> None:
    """Volume < 50% of ADV should not pass validation."""
    prev_close = 100.0
    open_price = 104.0  # 4% gap
    prev_high = 103.0
    adv = 10000.0

    await store.update_tick("SBIN", _make_tick("SBIN", ltp=104.5, open_price=open_price))
    await store.set_historical("SBIN", _make_historical(prev_close, prev_high, adv))
    await store.accumulate_volume("SBIN", 4000)  # 40% of ADV — below 50%

    await strategy.evaluate(store, StrategyPhase.OPENING)

    assert "SBIN" in strategy._gap_candidates
    assert "SBIN" not in strategy._volume_validated


@pytest.mark.asyncio
async def test_volume_validation_on_second_evaluation(
    strategy: GapAndGoStrategy, store: MarketDataStore
) -> None:
    """Volume that increases between evaluations should validate on second pass."""
    prev_close = 100.0
    open_price = 104.0
    prev_high = 103.0
    adv = 10000.0

    await store.update_tick("SBIN", _make_tick("SBIN", ltp=104.5, open_price=open_price))
    await store.set_historical("SBIN", _make_historical(prev_close, prev_high, adv))
    await store.accumulate_volume("SBIN", 4000)  # 40% — too low

    await strategy.evaluate(store, StrategyPhase.OPENING)
    assert "SBIN" not in strategy._volume_validated

    # Volume increases
    await store.accumulate_volume("SBIN", 6000)  # 60% — now passes
    await strategy.evaluate(store, StrategyPhase.OPENING)

    assert "SBIN" in strategy._volume_validated


# ── Volume validation in ENTRY_WINDOW (extended window) ──────────


@pytest.mark.asyncio
async def test_volume_validated_during_entry_window_generates_signal(
    strategy: GapAndGoStrategy, store: MarketDataStore
) -> None:
    """Candidate not volume-validated in OPENING, reaches 50% during ENTRY_WINDOW -> signal."""
    prev_close = 100.0
    open_price = 104.0
    prev_high = 103.0
    adv = 10000.0

    await store.update_tick("SBIN", _make_tick("SBIN", ltp=104.5, open_price=open_price))
    await store.set_historical("SBIN", _make_historical(prev_close, prev_high, adv))
    await store.accumulate_volume("SBIN", 4000)  # 40% — below threshold

    # OPENING phase — detects gap but volume too low
    await strategy.evaluate(store, StrategyPhase.OPENING)
    assert "SBIN" in strategy._gap_candidates
    assert "SBIN" not in strategy._volume_validated

    # Volume increases between phases
    await store.accumulate_volume("SBIN", 6000)  # 60% — now above threshold

    # ENTRY_WINDOW phase — should validate volume AND generate signal
    signals = await strategy.evaluate(store, StrategyPhase.ENTRY_WINDOW)

    assert "SBIN" in strategy._volume_validated
    assert len(signals) == 1
    assert signals[0].symbol == "SBIN"


@pytest.mark.asyncio
async def test_volume_still_below_threshold_in_entry_window_no_signal(
    strategy: GapAndGoStrategy, store: MarketDataStore
) -> None:
    """Candidate still below 50% ADV during ENTRY_WINDOW -> no signal."""
    prev_close = 100.0
    open_price = 104.0
    prev_high = 103.0
    adv = 10000.0

    await store.update_tick("SBIN", _make_tick("SBIN", ltp=104.5, open_price=open_price))
    await store.set_historical("SBIN", _make_historical(prev_close, prev_high, adv))
    await store.accumulate_volume("SBIN", 4000)  # 40% — below threshold

    # OPENING phase — detects gap but volume too low
    await strategy.evaluate(store, StrategyPhase.OPENING)
    assert "SBIN" in strategy._gap_candidates
    assert "SBIN" not in strategy._volume_validated

    # Volume stays below threshold (no change)
    # ENTRY_WINDOW phase — volume check fails, no signal
    signals = await strategy.evaluate(store, StrategyPhase.ENTRY_WINDOW)

    assert "SBIN" not in strategy._volume_validated
    assert len(signals) == 0


@pytest.mark.asyncio
async def test_disqualified_candidate_not_rechecked_in_entry_window(
    strategy: GapAndGoStrategy, store: MarketDataStore
) -> None:
    """A disqualified candidate should not be volume-rechecked in ENTRY_WINDOW."""
    prev_close = 100.0
    open_price = 104.0
    prev_high = 103.0
    adv = 10000.0

    await store.update_tick("SBIN", _make_tick("SBIN", ltp=104.5, open_price=open_price))
    await store.set_historical("SBIN", _make_historical(prev_close, prev_high, adv))
    await store.accumulate_volume("SBIN", 6000)  # 60% — above threshold

    # OPENING phase — detect and validate
    await strategy.evaluate(store, StrategyPhase.OPENING)
    assert "SBIN" in strategy._volume_validated

    # Price drops below open — disqualifies in ENTRY_WINDOW
    await store.update_tick("SBIN", _make_tick("SBIN", ltp=103.0, open_price=open_price))
    signals = await strategy.evaluate(store, StrategyPhase.ENTRY_WINDOW)

    assert "SBIN" in strategy._disqualified
    assert len(signals) == 0

    # Even with more volume, disqualified candidate should not be re-validated
    await store.accumulate_volume("SBIN", 8000)
    signals = await strategy.evaluate(store, StrategyPhase.ENTRY_WINDOW)
    assert len(signals) == 0


# ── Price hold validation and signal generation ──────────────────


@pytest.mark.asyncio
async def test_price_above_open_generates_signal(
    strategy: GapAndGoStrategy, store: MarketDataStore
) -> None:
    """Price above open in ENTRY_WINDOW should generate a signal."""
    prev_close = 100.0
    open_price = 104.0
    prev_high = 103.0
    adv = 10000.0

    await store.update_tick("SBIN", _make_tick("SBIN", ltp=104.5, open_price=open_price))
    await store.set_historical("SBIN", _make_historical(prev_close, prev_high, adv))
    await store.accumulate_volume("SBIN", 6000)

    # OPENING phase — detect gap and validate volume
    await strategy.evaluate(store, StrategyPhase.OPENING)
    assert "SBIN" in strategy._volume_validated

    # ENTRY_WINDOW phase — price holds above open
    signals = await strategy.evaluate(store, StrategyPhase.ENTRY_WINDOW)

    assert len(signals) == 1
    sig = signals[0]
    assert sig.symbol == "SBIN"
    assert sig.direction.value == "BUY"
    assert sig.strategy_name == "Gap & Go"
    assert sig.entry_price == 104.5
    assert "SBIN" in strategy._signals_generated


@pytest.mark.asyncio
async def test_price_below_open_disqualifies(
    strategy: GapAndGoStrategy, store: MarketDataStore
) -> None:
    """Price dropping below open should disqualify the candidate."""
    prev_close = 100.0
    open_price = 104.0
    prev_high = 103.0
    adv = 10000.0

    await store.update_tick("SBIN", _make_tick("SBIN", ltp=104.5, open_price=open_price))
    await store.set_historical("SBIN", _make_historical(prev_close, prev_high, adv))
    await store.accumulate_volume("SBIN", 6000)

    # OPENING phase
    await strategy.evaluate(store, StrategyPhase.OPENING)

    # Price drops below open
    await store.update_tick("SBIN", _make_tick("SBIN", ltp=103.5, open_price=open_price))

    # ENTRY_WINDOW phase
    signals = await strategy.evaluate(store, StrategyPhase.ENTRY_WINDOW)

    assert len(signals) == 0
    assert "SBIN" in strategy._disqualified


@pytest.mark.asyncio
async def test_price_equal_to_open_disqualifies(
    strategy: GapAndGoStrategy, store: MarketDataStore
) -> None:
    """Price exactly at open should not generate a signal (spec: must hold ABOVE)."""
    prev_close = 100.0
    open_price = 104.0
    prev_high = 103.0
    adv = 10000.0

    await store.update_tick("SBIN", _make_tick("SBIN", ltp=104.5, open_price=open_price))
    await store.set_historical("SBIN", _make_historical(prev_close, prev_high, adv))
    await store.accumulate_volume("SBIN", 6000)

    # OPENING phase
    await strategy.evaluate(store, StrategyPhase.OPENING)

    # Price drops to exactly open
    await store.update_tick("SBIN", _make_tick("SBIN", ltp=104.0, open_price=open_price))

    # ENTRY_WINDOW phase
    signals = await strategy.evaluate(store, StrategyPhase.ENTRY_WINDOW)

    assert len(signals) == 0
    assert "SBIN" in strategy._disqualified


@pytest.mark.asyncio
async def test_no_duplicate_signals(
    strategy: GapAndGoStrategy, store: MarketDataStore
) -> None:
    """Once a signal is generated, no duplicate should be produced."""
    prev_close = 100.0
    open_price = 104.0
    prev_high = 103.0
    adv = 10000.0

    await store.update_tick("SBIN", _make_tick("SBIN", ltp=104.5, open_price=open_price))
    await store.set_historical("SBIN", _make_historical(prev_close, prev_high, adv))
    await store.accumulate_volume("SBIN", 6000)

    await strategy.evaluate(store, StrategyPhase.OPENING)

    signals_1 = await strategy.evaluate(store, StrategyPhase.ENTRY_WINDOW)
    assert len(signals_1) == 1

    signals_2 = await strategy.evaluate(store, StrategyPhase.ENTRY_WINDOW)
    assert len(signals_2) == 0


# ── Stop loss calculation ────────────────────────────────────────


def test_sl_at_opening_price(strategy: GapAndGoStrategy) -> None:
    """SL should be at opening price when risk is within 3%."""
    entry = 104.0
    open_price = 102.0  # ~1.9% risk — within cap
    sl = strategy._calculate_stop_loss(entry, open_price)
    assert sl == open_price


def test_sl_capped_at_max_risk(strategy: GapAndGoStrategy) -> None:
    """SL should be capped at 3% below entry when gap is large."""
    entry = 110.0
    open_price = 100.0  # ~9% risk — exceeds 3% cap
    sl = strategy._calculate_stop_loss(entry, open_price)
    expected_max_sl = entry * 0.97  # 106.7
    assert sl == pytest.approx(expected_max_sl)
    assert sl > open_price  # SL raised above opening price


def test_sl_at_boundary(strategy: GapAndGoStrategy) -> None:
    """When risk is exactly 3%, SL should equal both opening price and cap."""
    entry = 103.0
    open_price = entry * 0.97  # Exactly 3% below
    sl = strategy._calculate_stop_loss(entry, open_price)
    assert sl == pytest.approx(open_price)


# ── Target calculation ───────────────────────────────────────────


def test_targets(strategy: GapAndGoStrategy) -> None:
    """T1 = entry + 5%, T2 = entry + 7%."""
    entry = 100.0
    t1, t2 = strategy._calculate_targets(entry)
    assert t1 == pytest.approx(105.0)
    assert t2 == pytest.approx(107.0)


def test_targets_with_actual_price(strategy: GapAndGoStrategy) -> None:
    entry = 523.5
    t1, t2 = strategy._calculate_targets(entry)
    assert t1 == pytest.approx(523.5 * 1.05)
    assert t2 == pytest.approx(523.5 * 1.07)


# ── No signals in other phases ───────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", [
    StrategyPhase.PRE_MARKET,
    StrategyPhase.CONTINUOUS,
    StrategyPhase.WIND_DOWN,
    StrategyPhase.POST_MARKET,
])
async def test_no_signals_in_inactive_phases(
    strategy: GapAndGoStrategy, store: MarketDataStore, phase: StrategyPhase
) -> None:
    """Evaluate returns empty list for all phases outside OPENING/ENTRY_WINDOW."""
    signals = await strategy.evaluate(store, phase)
    assert signals == []


# ── Reset ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reset_clears_state(
    strategy: GapAndGoStrategy, store: MarketDataStore
) -> None:
    """Reset should clear all per-session state."""
    prev_close = 100.0
    open_price = 104.0
    prev_high = 103.0
    adv = 10000.0

    await store.update_tick("SBIN", _make_tick("SBIN", ltp=104.5, open_price=open_price))
    await store.set_historical("SBIN", _make_historical(prev_close, prev_high, adv))
    await store.accumulate_volume("SBIN", 6000)

    await strategy.evaluate(store, StrategyPhase.OPENING)
    assert len(strategy._gap_candidates) > 0

    strategy.reset()

    assert len(strategy._gap_candidates) == 0
    assert len(strategy._volume_validated) == 0
    assert len(strategy._disqualified) == 0
    assert len(strategy._signals_generated) == 0


# ── Signal content validation ────────────────────────────────────


@pytest.mark.asyncio
async def test_signal_contains_correct_fields(
    strategy: GapAndGoStrategy, store: MarketDataStore
) -> None:
    """Verify all fields of the generated CandidateSignal."""
    prev_close = 100.0
    open_price = 104.0
    prev_high = 103.0
    adv = 10000.0

    await store.update_tick("SBIN", _make_tick("SBIN", ltp=105.0, open_price=open_price))
    await store.set_historical("SBIN", _make_historical(prev_close, prev_high, adv))
    await store.accumulate_volume("SBIN", 6000)

    await strategy.evaluate(store, StrategyPhase.OPENING)
    signals = await strategy.evaluate(store, StrategyPhase.ENTRY_WINDOW)

    assert len(signals) == 1
    sig = signals[0]

    assert sig.entry_price == 105.0
    assert sig.stop_loss == pytest.approx(max(open_price, 105.0 * 0.97))
    assert sig.target_1 == pytest.approx(105.0 * 1.05)
    assert sig.target_2 == pytest.approx(105.0 * 1.07)
    assert sig.gap_pct == pytest.approx(4.0)
    assert sig.volume_ratio == pytest.approx(0.6)  # 6000 / 10000
    assert sig.price_distance_from_open_pct == pytest.approx(
        ((105.0 - 104.0) / 104.0) * 100
    )
    assert "Gap up" in sig.reason
    assert sig.generated_at is not None


# ── Multiple candidates ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_multiple_candidates(
    strategy: GapAndGoStrategy, store: MarketDataStore
) -> None:
    """Multiple stocks can generate signals in the same session."""
    for symbol, open_px, prev_c, prev_h in [
        ("SBIN", 104.0, 100.0, 103.0),
        ("RELIANCE", 206.0, 200.0, 205.0),
    ]:
        await store.update_tick(symbol, _make_tick(symbol, ltp=open_px + 1, open_price=open_px))
        await store.set_historical(symbol, _make_historical(prev_c, prev_h, 10000.0))
        await store.accumulate_volume(symbol, 6000)

    await strategy.evaluate(store, StrategyPhase.OPENING)
    signals = await strategy.evaluate(store, StrategyPhase.ENTRY_WINDOW)

    assert len(signals) == 2
    symbols = {s.symbol for s in signals}
    assert symbols == {"SBIN", "RELIANCE"}


# ── No historical data ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_symbol_without_historical_data_skipped(
    strategy: GapAndGoStrategy, store: MarketDataStore
) -> None:
    """Symbols without historical data should be silently skipped."""
    await store.update_tick("SBIN", _make_tick("SBIN", ltp=104.5, open_price=104.0))
    # No historical data set

    await strategy.evaluate(store, StrategyPhase.OPENING)

    assert "SBIN" not in strategy._gap_candidates
