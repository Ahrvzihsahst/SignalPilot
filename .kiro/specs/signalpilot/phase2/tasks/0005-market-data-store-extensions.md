# Task 5: MarketDataStore Extensions

## Description
Extend `MarketDataStore` with three new subsystems: opening range tracking (30-min high/low per stock), running VWAP calculation, and 15-minute candle aggregation from tick data.

## Prerequisites
Task 0001 (Configuration and Constants)

## Requirement Coverage
REQ-P2-001, REQ-P2-007, REQ-P2-008, REQ-P2-038

## Files to Modify
- `signalpilot/data/market_data_store.py`

## Subtasks

- [ ] 5.1 Add `OpeningRange` dataclass to `signalpilot/data/market_data_store.py`
  - Fields: `range_high: float`, `range_low: float`, `locked: bool = False`, `range_size_pct: float = 0.0`
  - Requirement coverage: REQ-P2-001

- [ ] 5.2 Add `VWAPState` dataclass
  - Fields: `cumulative_price_volume: float = 0.0`, `cumulative_volume: float = 0.0`, `current_vwap: float = 0.0`
  - Requirement coverage: REQ-P2-007

- [ ] 5.3 Add `Candle15Min` dataclass
  - Fields: `symbol: str`, `open: float`, `high: float`, `low: float`, `close: float`, `volume: float`, `start_time: datetime`, `end_time: datetime`, `is_complete: bool = False`
  - Requirement coverage: REQ-P2-008

- [ ] 5.4 Implement opening range tracking methods
  - `update_opening_range(symbol, high, low)` -- update range_high/range_low from tick data (only before lock)
  - `lock_opening_ranges()` -- lock all ranges (called at 9:45 AM), calculate range_size_pct, make immutable
  - `get_opening_range(symbol) -> OpeningRange | None`
  - Requirement coverage: REQ-P2-001

- [ ] 5.5 Implement VWAP calculation methods
  - `update_vwap(symbol, price, volume)` -- update running VWAP: `cum_price_vol += price * volume`, `cum_vol += volume`, `current_vwap = cum_price_vol / cum_vol`
  - `get_vwap(symbol) -> float | None`
  - `reset_vwap()` -- reset all VWAP accumulators (called at session start)
  - Requirement coverage: REQ-P2-007

- [ ] 5.6 Implement 15-minute candle aggregation methods
  - `update_candle(symbol, price, volume, timestamp)` -- aggregate into 15-min candle bucket
  - `get_completed_candles(symbol) -> list[Candle15Min]` -- return all finalized candles
  - `get_current_candle(symbol) -> Candle15Min | None` -- return in-progress candle
  - `get_avg_candle_volume(symbol) -> float` -- average volume of completed candles (excluding current)
  - `_get_candle_bucket(timestamp) -> datetime` -- snap timestamp to 15-min boundary (static method)
  - Requirement coverage: REQ-P2-008

- [ ] 5.7 Update `clear()` to reset all new state dictionaries
  - Reset `_opening_ranges`, `_vwap_state`, `_candles_15m`, `_current_candle`
  - Requirement coverage: foundational

- [ ] 5.8 Write opening range tests in `tests/test_data/test_market_data_store.py`
  - Test range tracking updates correctly, test locking makes range immutable, test range_size_pct calculation, test updates rejected after lock
  - Requirement coverage: REQ-P2-001

- [ ] 5.9 Write VWAP calculation tests
  - Test VWAP accumulation with known values, test reset clears state, test zero-volume handling
  - Requirement coverage: REQ-P2-007

- [ ] 5.10 Write 15-minute candle aggregation tests
  - Test candle boundaries (9:15-9:30, 9:30-9:45, etc.), test candle completion, test partial candle access, test average volume excludes in-progress candle
  - Requirement coverage: REQ-P2-008

- [ ] 5.11 Performance test: 500 stocks VWAP update under 500ms
  - Requirement coverage: REQ-P2-038
