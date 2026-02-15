# Task 7: Risk Manager

## References
- Requirements: `/.kiro/specs/signalpilot/requirements.md` (Req 12-15)
- Design: `/.kiro/specs/signalpilot/design.md` (Section 4.4)

---

## Subtasks

### 7.1 Implement `signalpilot/risk/position_sizer.py` with PositionSizer

- [ ] Implement `PositionSizer` class as specified in design (Section 4.4.1)
- [ ] `calculate(entry_price: float, total_capital: float, max_positions: int) -> PositionSize`:
  - `per_trade_capital = total_capital / max_positions`
  - `quantity = floor(per_trade_capital / entry_price)`
  - `capital_required = quantity * entry_price`
  - Return `PositionSize(quantity, capital_required, per_trade_capital)`
- [ ] Write tests in `tests/test_risk/test_position_sizer.py`:
  - Capital=50000, max_positions=5, entry=645 -> per_trade=10000, qty=15, capital_req=9675
  - Capital=50000, max_positions=5, entry=2450 -> per_trade=10000, qty=4, capital_req=9800
  - Capital=50000, max_positions=5, entry=120000 -> qty=0 (stock too expensive)
  - Verify floor rounding (not ceil or round)

**Requirement coverage:** Req 13.1 (per-trade capital), Req 13.2 (quantity calc), Req 13.3 (include quantity in signal), Req 13.4 (suppress if qty=0)

---

### 7.2 Implement `signalpilot/risk/risk_manager.py` with RiskManager

- [ ] Implement `RiskManager` class as specified in design (Section 4.4.2)
- [ ] `filter_and_size(ranked_signals: list[RankedSignal], user_config: UserConfig, active_trade_count: int) -> list[FinalSignal]`:
  - Check `active_trade_count` against `user_config.max_positions` (Req 14.1)
  - If at limit, return empty list and log (Req 14.3)
  - Calculate available slots = max_positions - active_trade_count
  - For each ranked signal (up to available slots):
    - Calculate position size using PositionSizer
    - If quantity = 0, auto-skip and log reason (Req 12.1-12.3)
    - Otherwise, create FinalSignal with all fields
    - Set `expires_at = generated_at + timedelta(minutes=30)` (Req 15.1)
  - Return list of FinalSignal
- [ ] Write tests in `tests/test_risk/test_risk_manager.py`:
  - Test position limit enforcement: active_trade_count=5, max_positions=5 -> returns empty
  - Test auto-skip: entry_price > per_trade_capital -> signal skipped, logged
  - Test normal flow: signal passes through with correct sizing and expiry
  - Test partial slots: active_trade_count=3, max_positions=5 -> max 2 signals returned
  - Test expiry timestamp: verify it is exactly 30 minutes after generated_at

**Requirement coverage:** Req 12 (auto-skip expensive), Req 14 (max position limits), Req 15.1 (signal expiry)
