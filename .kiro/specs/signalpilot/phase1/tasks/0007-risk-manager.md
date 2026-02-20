# Task 7: Risk Manager

## Status: COMPLETED

## References
- Requirements: `/.kiro/specs/signalpilot/requirements.md` (Req 12-15)
- Design: `/.kiro/specs/signalpilot/design.md` (Section 4.4)

---

## Subtasks

### 7.1 Implement `signalpilot/risk/position_sizer.py` with PositionSizer

- [x] Implement `PositionSizer` class as specified in design (Section 4.4.1)
- [x] `calculate(entry_price: float, total_capital: float, max_positions: int) -> PositionSize`:
  - `per_trade_capital = total_capital / max_positions`
  - `quantity = floor(per_trade_capital / entry_price)`
  - `capital_required = quantity * entry_price`
  - Return `PositionSize(quantity, capital_required, per_trade_capital)`
- [x] Input validation: raises ValueError for max_positions <= 0 or entry_price <= 0
- [x] Write tests in `tests/test_risk/test_position_sizer.py` (12 tests):
  - Capital=50000, max_positions=5, entry=645 -> per_trade=10000, qty=15, capital_req=9675
  - Capital=50000, max_positions=5, entry=2450 -> per_trade=10000, qty=4, capital_req=9800
  - Capital=50000, max_positions=5, entry=120000 -> qty=0 (stock too expensive)
  - Verify floor rounding (not ceil or round)
  - Input validation tests (zero/negative max_positions and entry_price)

**Requirement coverage:** Req 13.1 (per-trade capital), Req 13.2 (quantity calc), Req 13.3 (include quantity in signal), Req 13.4 (suppress if qty=0)

---

### 7.2 Implement `signalpilot/risk/risk_manager.py` with RiskManager

- [x] Implement `RiskManager` class as specified in design (Section 4.4.2)
- [x] `filter_and_size(ranked_signals: list[RankedSignal], user_config: UserConfig, active_trade_count: int) -> list[FinalSignal]`:
  - Check `active_trade_count` against `user_config.max_positions` (Req 14.1)
  - If at limit, return empty list and log (Req 14.3)
  - Calculate available slots = max_positions - active_trade_count
  - For each ranked signal (up to available slots):
    - Calculate position size using PositionSizer
    - If quantity = 0, auto-skip and log reason (Req 12.1-12.3)
    - Otherwise, create FinalSignal with all fields
    - Set `expires_at = generated_at + timedelta(minutes=30)` (Req 15.1)
  - Return list of FinalSignal
- [x] Write tests in `tests/test_risk/test_risk_manager.py` (13 tests):
  - Test position limit enforcement: active_trade_count=5, max_positions=5 -> returns empty
  - Test over max positions also returns empty
  - Test auto-skip: entry_price > per_trade_capital -> signal skipped, logged
  - Test auto-skip logs reason with symbol and price
  - Test normal flow: signal passes through with correct sizing and expiry
  - Test normal flow with multiple signals
  - Test partial slots: active_trade_count=3, max_positions=5 -> max 2 signals returned
  - Test partial slots with expensive skip
  - Test expiry timestamp: verify it is exactly 30 minutes after generated_at
  - Test different generation times get individual expiries
  - Test empty ranked returns empty
  - Test position limit logging message
  - Test mixed affordable and expensive signals

**Requirement coverage:** Req 12 (auto-skip expensive), Req 14 (max position limits), Req 15.1 (signal expiry)

---

## Code Review Result
- **No Critical or High issues found** — approved for production
- Medium: Removed unused `IST` import (fixed)
- Medium: Added input validation for division-by-zero in PositionSizer (fixed)
- Low: PositionSizer is stateless — acceptable per design spec for DI extensibility
- Low: Synchronous `filter_and_size` (correct — no I/O in implementation)
