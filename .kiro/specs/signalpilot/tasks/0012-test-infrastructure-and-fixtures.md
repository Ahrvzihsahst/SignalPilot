# Task 12: Test Infrastructure and Fixtures

## References
- Requirements: `/.kiro/specs/signalpilot/requirements.md` (supports all test tasks)
- Design: `/.kiro/specs/signalpilot/design.md` (Section 9)

---

## Subtasks

### 12.1 Create `tests/conftest.py` with shared test fixtures

- [ ] Create fixture for in-memory SQLite database:
  - Initialize with full schema (signals, trades, user_config tables)
  - Use `aiosqlite.connect(":memory:")` for test isolation
  - Auto-cleanup after each test
- [ ] Create fixture for `MarketDataStore` pre-populated with sample data:
  - Sample tick data for 5-10 stocks with realistic prices
  - Sample historical references (prev_close, prev_high, avg_daily_volume)
- [ ] Create fixture for sample signal objects:
  - `CandidateSignal` — valid Gap & Go candidate (4% gap, 60% volume ratio)
  - `RankedSignal` — scored and ranked with 4-star rating
  - `FinalSignal` — fully sized with quantity and expiry
- [ ] Create fixture for `AppConfig` with test values:
  - Use dummy credentials for Angel One and Telegram
  - Set test-appropriate defaults (small capital, relaxed timeouts)
- [ ] Create sample trade data fixtures for metrics testing:
  - Mix of winning and losing trades
  - Various exit types (SL hit, T1, T2, trailing SL, time exit)
  - Known totals for verification (e.g., 7 wins, 5 losses, total P&L = +2340)

**Requirement coverage:** Supports all test tasks

---

### 12.2 Create `tests/test_data/` with mock data fixtures

- [ ] Create `tests/test_data/mock_ticks.json`:
  - Sample tick sequences for gap-up stocks (valid scenario: 4% gap, high volume, price holds)
  - Sample tick sequences for invalid scenarios (gap too small, low volume, price drops below open)
  - Tick sequences for exit monitoring (price hitting SL, T1, T2, trailing SL progression)
- [ ] Create `tests/test_data/mock_historical.json`:
  - Previous day OHLCV data for 10 sample stocks
  - 20-day volume history for ADV calculation
- [ ] Create `tests/test_data/mock_instrument_master.json`:
  - Sample Angel One instrument master entries for NSE equity stocks
  - Include `-EQ` suffix format and `exch_seg: "NSE"` field
  - Include some entries that won't match Nifty 500 CSV (to test exclusion)

**Requirement coverage:** Supports test_strategy, test_integration tests
