# Task 8: Exit Monitor

## Status: COMPLETED

## References
- Requirements: `/.kiro/specs/signalpilot/requirements.md` (Req 17-20)
- Design: `/.kiro/specs/signalpilot/design.md` (Section 4.5)

---

## Subtasks

### 8.1 Implement `signalpilot/monitor/exit_monitor.py` with ExitMonitor

- [x] Implement `TrailingStopState` dataclass:
  - `trade_id: int`
  - `original_sl: float`
  - `current_sl: float`
  - `highest_price: float`
  - `breakeven_triggered: bool`
  - `trailing_active: bool`
  - `t1_alerted: bool`
- [x] Implement `ExitMonitor` class as specified in design (Section 4.5.1)
- [x] Constructor takes: `market_data_store`, `trade_repo`, `alert_callback` (async callable for sending alerts)
- [x] `start_monitoring(trade: TradeRecord)`:
  - Initialize TrailingStopState for this trade
  - Add to `_active_states` dict (trade_id -> TrailingStopState)
- [x] `stop_monitoring(trade_id: int)`:
  - Remove from `_active_states`
- [x] `check_all_trades()`:
  - Get all active trades from trade_repo
  - For each active trade, call `_check_trade(trade, state)`
- [x] `_check_trade(trade: TradeRecord, state: TrailingStopState)`:
  - Get current tick from market_data_store
  - If no tick data, skip
  - Update `state.highest_price` if current price is higher
  - Call `_update_trailing_stop(trade, state, current_price)`
  - Check SL hit: `current_price <= state.current_sl` -> trigger exit with `ExitType.SL_HIT` or `ExitType.TRAILING_SL`
  - Check T2 hit: `current_price >= trade.target_2` -> trigger exit with `ExitType.T2_HIT`
  - Check T1 hit (alert only, once): `current_price >= trade.target_1` AND `not state.t1_alerted` -> send advisory alert, set `state.t1_alerted = True`
- [x] `_update_trailing_stop(trade, state, current_price)`:
  - Calculate move_pct = `(current_price - trade.entry_price) / trade.entry_price * 100`
  - **At +2% above entry** (Req 19.1):
    - If `move_pct >= 2.0` and `not state.breakeven_triggered`:
      - Set `state.current_sl = trade.entry_price` (breakeven)
      - Set `state.breakeven_triggered = True`
      - Send Telegram alert: "SL moved to breakeven at [entry_price]"
  - **At +4% above entry** (Req 19.2):
    - If `move_pct >= 4.0`:
      - Set `state.trailing_active = True`
      - Calculate new_sl = `current_price * 0.98` (2% below current price)
      - If `new_sl > state.current_sl`: update `state.current_sl = new_sl` (Req 19.3: never move down)
      - Send Telegram alert: "Trailing SL updated to [new_sl]"
- [x] `_trigger_exit(trade, exit_type, current_price)`:
  - Calculate P&L: `pnl_amount = (current_price - trade.entry_price) * trade.quantity`
  - Calculate P&L %: `pnl_pct = (current_price - trade.entry_price) / trade.entry_price * 100`
  - Call `trade_repo.close_trade(trade.id, current_price, pnl_amount, pnl_pct, exit_type.value)`
  - Create ExitAlert and invoke alert_callback
  - Call `stop_monitoring(trade.id)`
- [x] `trigger_time_exit_check(is_mandatory: bool)`:
  - Get all active trades
  - For each trade:
    - Get current price from market_data_store
    - Calculate unrealized P&L
    - If `is_mandatory` (3:15 PM): trigger exit with `ExitType.TIME_EXIT` for all
    - If not mandatory (3:00 PM): send advisory alert with current P&L, recommend exit
- [x] Write tests in `tests/test_monitor/test_exit_monitor.py`:
  - **SL hit**: entry=100, SL=97, price drops to 97 -> exit triggered, alert sent (Req 18.1-18.3)
  - **T1 hit**: entry=100, T1=105, price reaches 105 -> advisory alert sent, trade stays open (Req 17.1, 17.3)
  - **T1 alert fires only once**: price oscillates around T1 -> only one alert
  - **T2 hit**: entry=100, T2=107, price reaches 107 -> full exit triggered (Req 17.2)
  - **Trailing SL +2%**: entry=100, price reaches 102 -> SL moves to 100 (breakeven) (Req 19.1)
  - **Trailing SL +4%**: entry=100, price reaches 104 -> trailing SL at 101.92 (104*0.98) (Req 19.2)
  - **Trail moves up**: price 104->106 -> trailing SL moves from 101.92 to 103.88
  - **Trail never moves down**: price 106->103 -> trailing SL stays at 103.88 (Req 19.3)
  - **Trailing SL hit**: price drops to trailing SL -> exit triggered (Req 19.4)
  - **Time exit 3:00 PM**: open trades get advisory alert with P&L (Req 20.1-20.2)
  - **Time exit 3:15 PM**: mandatory exit for all open trades (Req 20.3)

**Requirement coverage:** Req 17 (target alerts), Req 18 (SL alerts), Req 19 (trailing SL), Req 20 (time exit)

---

## Code Review Result
- **No Critical issues found** — approved for production
- H1: Made trailing stop thresholds configurable (breakeven_trigger_pct, trail_trigger_pct, trail_distance_pct) instead of hardcoded (fixed)
- H2: Documented long-only assumption in class docstring (Phase 1 BUY only)
- M1: Added INFO-level logging for all exit events, trailing SL updates, start/stop monitoring (fixed)
- M5: Deduplicated PnL formula in `_build_exit_alert` to use `_calc_pnl_pct` (fixed)
- L1: Removed dead `TradeRepoProtocol` alias (fixed)
- L4: Added test for direct jump past breakeven to trailing (fixed)
- Bug fix: When jumping directly to +4%, set `breakeven_triggered=True` to prevent breakeven branch firing on price pullback
- Bug fix: `trailing_active` only set when trail SL actually moves (not just when move_pct >= threshold)
