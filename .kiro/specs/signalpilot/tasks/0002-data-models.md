# Task 2: Data Models

**Status: COMPLETED**
**Branch:** `feat/0002-data-models`
**Tests:** 39 passed

## References
- Requirements: `/.kiro/specs/signalpilot/requirements.md` (Req 28, 9, 10, 19)
- Design: `/.kiro/specs/signalpilot/design.md` (Section 5.1)

---

## Subtasks

### 2.1 Implement `signalpilot/db/models.py` with all core dataclasses

- [x] Implement all dataclasses from the design (Section 5.1):
  - `Instrument` — symbol, name, angel_token, exchange, nse_symbol, yfinance_symbol, lot_size
  - `TickData` — symbol, ltp, open_price, high, low, close, volume, last_traded_timestamp, updated_at
  - `HistoricalReference` — previous_close, previous_high, average_daily_volume
  - `PreviousDayData` — close, high, low, open, volume
  - `CandidateSignal` — symbol, direction, strategy_name, entry_price, stop_loss, target_1, target_2, gap_pct, volume_ratio, price_distance_from_open_pct, reason, generated_at
  - `RankedSignal` — wraps CandidateSignal + composite_score, rank, signal_strength
  - `PositionSize` — quantity, capital_required, per_trade_capital
  - `FinalSignal` — wraps RankedSignal + quantity, capital_required, expires_at
  - `SignalRecord` — all DB fields with defaults for easy row construction
  - `TradeRecord` — all DB fields with defaults for easy row construction
  - `UserConfig` — id, telegram_chat_id, total_capital, max_positions, timestamps
  - `ExitAlert` — trade, exit_type, current_price, pnl_pct, is_alert_only, trailing_sl_update
  - `PerformanceMetrics` — date_range, totals, win_rate, pnl, risk_reward, best/worst trades
  - `DailySummary` — date, counts, pnl, trades list (default_factory=list)
- [x] Implement enums:
  - `SignalDirection` — BUY, SELL
  - `ExitType` — SL_HIT, T1_HIT, T2_HIT, TRAILING_SL_HIT, TIME_EXIT
  - `StrategyPhase` — re-exported from `market_calendar.py` (PRE_MARKET through POST_MARKET)
- [x] Implement `ScoringWeights` dataclass — gap_pct_weight, volume_ratio_weight, price_distance_weight (renamed per code review to match spec)
- [x] Write tests in `tests/test_db/test_models.py` (39 tests):
  - Verify dataclass instantiation with all required fields
  - Verify default values where applicable
  - Verify enum values are correct
  - Verify equality semantics (code review fix)
  - Verify mutable default isolation for DailySummary.trades (code review fix)
  - Verify ScoringWeights defaults sum to 1.0 (code review fix)

**Requirement coverage:** Req 28 (schema fields map to these models), Req 9 (SL/target fields), Req 10 (scoring fields), Req 19 (ExitType enum)
