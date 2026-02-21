# Task 10: Scheduler and Application Lifecycle

## References
- Requirements: `/.kiro/specs/signalpilot/requirements.md` (Req 16, 27, 32-35)
- Design: `/.kiro/specs/signalpilot/design.md` (Section 4.8)

---

## Subtasks

### 10.1 Implement `signalpilot/scheduler/scheduler.py` with MarketScheduler

- [x] Implement `MarketScheduler` class as specified in design (Section 4.8.1)
- [x] Use `AsyncIOScheduler` from APScheduler 3.x with IST timezone
- [x] `configure_jobs(app: SignalPilotApp)`:
  - Register all scheduled jobs using CronTrigger:

  | Time | Job | Callback | Requirement |
  |------|-----|----------|-------------|
  | 9:00 AM | Pre-market alert | `app.send_pre_market_alert()` | Req 27.1 |
  | 9:15 AM | Start scanning | `app.start_scanning()` | Req 33.1 |
  | 2:30 PM | Stop new signals | `app.stop_new_signals()` | Req 16.1, Req 27.2 |
  | 3:00 PM | Exit reminder | `app.trigger_exit_reminder()` | Req 16.2, Req 20.1, Req 27.3 |
  | 3:15 PM | Mandatory exit | `app.trigger_mandatory_exit()` | Req 16.5, Req 20.3 |
  | 3:30 PM | Daily summary | `app.send_daily_summary()` | Req 27.4, Req 31 |
  | 3:35 PM | Shutdown | `app.shutdown()` | Req 34.1 |

- [x] `start()`: start the AsyncIOScheduler
- [x] `shutdown()`: gracefully shutdown the scheduler
- [x] Write tests in `tests/test_scheduler/test_scheduler.py`:
  - Verify all 7 jobs are registered
  - Verify each job's trigger time matches specification
  - Verify IST timezone is configured

**Requirement coverage:** Req 16 (time restrictions), Req 27 (scheduled alerts), Req 34 (auto-shutdown)

---

### 10.2 Implement `signalpilot/scheduler/lifecycle.py` with SignalPilotApp orchestrator

- [x] Implement `SignalPilotApp` class as specified in design (Section 4.8.2)
- [x] `__init__(config: AppConfig)`:
  - Wire all components together:
    - `DatabaseManager(config.db_path)`
    - `SmartAPIAuthenticator(config)`
    - `InstrumentManager(config)`
    - `MarketDataStore()`
    - `HistoricalDataFetcher(authenticator, instrument_manager, market_data_store)`
    - `WebSocketClient(authenticator, instrument_manager, market_data_store)`
    - `GapAndGoStrategy(market_data_store)`
    - `SignalScorer(config.scoring_weights)`
    - `SignalRanker(scorer)`
    - `PositionSizer()`
    - `RiskManager(position_sizer, trade_repo)`
    - `ExitMonitor(market_data_store, trade_repo, alert_callback)`
    - `SignalPilotBot(config, repos, market_data_store, exit_monitor, metrics)`
    - `MarketScheduler()`
  - State flags: `_scanning: bool`, `_accepting_signals: bool`
- [x] `startup()`:
  - Initialize DB (create tables if needed)
  - Authenticate with Angel One
  - Load instrument list
  - Fetch historical data (prev close, prev high, 20-day ADV)
  - Set historical references in MarketDataStore
  - Start Telegram bot
  - Configure and start scheduler
- [x] `start_scanning()`:
  - Connect WebSocket
  - Set `_scanning = True`
  - Create asyncio task for `_scan_loop()`
- [x] `_scan_loop()`:
  - While `_scanning`:
    - Determine current phase via `_determine_phase()`
    - If OPENING or ENTRY_WINDOW:
      - Evaluate Gap & Go strategy -> get candidates
      - If candidates exist:
        - Rank signals via SignalRanker
        - Filter and size via RiskManager
        - For each FinalSignal: save to DB, send via Telegram
    - If any phase with active trades:
      - Call `exit_monitor.check_all_trades()`
    - Call `_expire_stale_signals()`
    - `await asyncio.sleep(1)` (1-second scan interval)
- [x] `_determine_phase(dt: datetime) -> StrategyPhase`:
  - Map current time to the correct strategy phase
- [x] `stop_new_signals()`:
  - Set `_accepting_signals = False`
  - Send Telegram: "No new signals. Monitoring existing positions only."
- [x] `send_pre_market_alert()`:
  - Send Telegram: "Pre-market scan running. Signals coming shortly."
- [x] `trigger_exit_reminder()`:
  - Call `exit_monitor.trigger_time_exit_check(is_mandatory=False)`
  - Send Telegram: "Close all intraday positions in the next 15 minutes."
- [x] `trigger_mandatory_exit()`:
  - Call `exit_monitor.trigger_time_exit_check(is_mandatory=True)`
- [x] `send_daily_summary()`:
  - Calculate daily summary via MetricsCalculator
  - Format and send via Telegram
- [x] `shutdown()`:
  - Set `_scanning = False`
  - Disconnect WebSocket
  - Shutdown scheduler
  - Stop Telegram bot
  - Close DB connection
- [x] `recover()` (for crash recovery):
  - Re-authenticate with Angel One
  - Re-establish WebSocket connection
  - Reload today's signals and active trades from SQLite
  - Resume exit monitoring for all active trades
  - Send Telegram: "System recovered from interruption. Monitoring resumed."
- [x] `_expire_stale_signals()`:
  - Query signals where `expires_at < now` and `status = 'sent'`
  - Update status to 'expired'
  - Send Telegram notification for each expired signal
- [x] Write tests in `tests/test_scheduler/test_lifecycle.py`:
  - Verify startup calls all initialization methods in correct order
  - Verify scan loop evaluates strategy during correct phases
  - Verify scan loop checks exits on every iteration
  - Verify shutdown calls all cleanup methods
  - Verify recovery reloads state and resumes monitoring

**Requirement coverage:** Req 32 (auto-start), Req 33 (continuous scanning), Req 34 (auto-shutdown), Req 35 (crash recovery)

---

### 10.3 Implement `signalpilot/main.py` as the application entry point

- [x] Create asyncio entry point:
  ```python
  async def main():
      config = AppConfig()
      app = SignalPilotApp(config)
      if is_market_hours(datetime.now(IST)):
          await app.recover()  # crash recovery mode
      else:
          await app.startup()  # normal startup
  ```
- [x] Handle SIGINT/SIGTERM for graceful shutdown:
  - Register signal handlers that call `app.shutdown()`
- [x] Add `if __name__ == "__main__":` block with `asyncio.run(main())`
- [x] Write test in `tests/test_main.py`:
  - Verify entry point creates AppConfig and SignalPilotApp
  - Verify normal startup vs crash recovery detection

**Requirement coverage:** Req 32.2 (full startup sequence), Req 35.1-35.5 (crash recovery)

---

## Status: COMPLETED

All subtasks implemented and tested. 38 tests passing (12 scheduler, 23 lifecycle, 3 main).

### Code Review Summary

**Fixes applied:**
- MAIN-01 (Critical): Added idempotent signal handler to prevent double shutdown on repeated Ctrl+C
- LCY-02 + MAIN-03 (High): Added `is_trading_day()` check to prevent recovery on weekends/holidays
- LCY-03 (High): Added circuit-breaker to scan loop (stops after 10 consecutive errors, sends alert)
- LCY-08 (High): Recovery now checks current phase and disables signals if past entry window
- LCY-06 (Medium): Shutdown wraps each cleanup step in try/except for resilience
- LCY-07 (Medium): Changed `date.today()` to `datetime.now(IST).date()` for IST-aware dates
- SCH-02 (Low): Added `replace_existing=True` for idempotent job registration

**Deferred (low risk):**
- MAIN-02: create_app passes None for unmerged components (by design, full wiring after branch merge)
- MAIN-04: Logging configuration (project has utils/logger.py, will be called in full wiring)
- SCH-01: Protocol type for app parameter (duck typing is consistent with codebase style)
- SCH-03: day_of_week constraint (app only runs on trading days via scheduler)
- LCY-04: asyncio.Event vs bool (safe in single-threaded asyncio)
- LCY-05: Startup idempotency guard (low risk, single entry point)
