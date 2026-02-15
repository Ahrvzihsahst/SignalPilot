# Task 2: Data Models

## References
- Requirements: `/.kiro/specs/signalpilot/requirements.md` (Req 28, 9, 10, 19)
- Design: `/.kiro/specs/signalpilot/design.md` (Section 5.1)

---

## Subtasks

### 2.1 Implement `signalpilot/db/models.py` with all core dataclasses

- [ ] Implement all dataclasses from the design (Section 5.1):
  - `Instrument` — symbol, name, angel_token, isin, exchange_segment
  - `TickData` — symbol, ltp, open, high, low, close, volume, timestamp
  - `HistoricalReference` — symbol, prev_close, prev_high, avg_daily_volume
  - `PreviousDayData` — close, high, volume
  - `CandidateSignal` — symbol, strategy, direction, entry_price, stop_loss, target_1, target_2, gap_pct, volume_ratio, distance_from_open, reason
  - `RankedSignal` — candidate fields + composite_score, star_rating
  - `PositionSize` — quantity, capital_required, per_trade_capital
  - `FinalSignal` — ranked signal fields + position size fields + generated_at, expires_at
  - `SignalRecord` — all fields for DB persistence (id, date, symbol, strategy, entry_price, stop_loss, target_1, target_2, quantity, capital_required, signal_strength, gap_pct, volume_ratio, reason, created_at, expires_at, status)
  - `TradeRecord` — all fields for DB persistence (id, signal_id, date, symbol, entry_price, exit_price, stop_loss, quantity, pnl_amount, pnl_pct, exit_reason, taken_at, exited_at)
  - `UserConfig` — id, telegram_chat_id, total_capital, max_positions, created_at, updated_at
  - `ExitAlert` — symbol, exit_type, message, current_price, pnl_amount, pnl_pct
  - `PerformanceMetrics` — date_range, total_signals, trades_taken, win_rate, total_pnl, avg_win, avg_loss, risk_reward_ratio, best_trade, worst_trade
  - `DailySummary` — date, signals_generated, signals_taken, wins, losses, total_pnl, cumulative_pnl, trade_details
- [ ] Implement enums:
  - `SignalDirection` — BUY, SELL
  - `ExitType` — SL_HIT, T1_HIT, T2_HIT, TRAILING_SL, TIME_EXIT
  - `StrategyPhase` — PRE_MARKET, OPENING, ENTRY_WINDOW, MONITORING, NO_NEW_SIGNALS, EXIT_WINDOW, POST_MARKET
- [ ] Implement `ScoringWeights` dataclass — gap_weight, volume_weight, price_distance_weight
- [ ] Write tests in `tests/test_db/test_models.py`:
  - Verify dataclass instantiation with all required fields
  - Verify default values where applicable
  - Verify enum values are correct

**Requirement coverage:** Req 28 (schema fields map to these models), Req 9 (SL/target fields), Req 10 (scoring fields), Req 19 (ExitType enum)
