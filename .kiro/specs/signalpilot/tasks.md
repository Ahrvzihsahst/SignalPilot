# SignalPilot -- Implementation Tasks

## References
- Requirements: `/.kiro/specs/signalpilot/requirements.md`
- Design: `/.kiro/specs/signalpilot/design.md`

---

## 1. Project Scaffolding and Configuration

- [ ] 1.1 Create the project directory structure and `pyproject.toml`
  - Create all package directories as defined in the design (Section 3): `signalpilot/`, `signalpilot/data/`, `signalpilot/strategy/`, `signalpilot/ranking/`, `signalpilot/risk/`, `signalpilot/monitor/`, `signalpilot/telegram/`, `signalpilot/db/`, `signalpilot/scheduler/`, `signalpilot/utils/`, `data/`, `tests/`
  - Add `__init__.py` files to all Python packages
  - Create `pyproject.toml` with all dependencies from the design (Appendix A): `smartapi-python`, `pyotp`, `python-telegram-bot`, `apscheduler`, `aiosqlite`, `pandas`, `numpy`, `yfinance`, `pydantic`, `pydantic-settings`, `httpx`, `logzero`
  - Add dev dependencies: `pytest`, `pytest-asyncio`, `pytest-mock`, `pytest-cov`, `ruff`, `mypy`
  - Create `data/nifty500_list.csv` with a placeholder header row (Symbol, Company Name, Industry, ISIN)
  - Requirement coverage: foundational for all requirements

- [ ] 1.2 Implement `signalpilot/utils/constants.py` with market time constants
  - Define IST timezone using `zoneinfo.ZoneInfo("Asia/Kolkata")`
  - Define all market time constants from the design (Appendix B): `MARKET_OPEN`, `MARKET_CLOSE`, `PRE_MARKET_ALERT`, `GAP_SCAN_END`, `ENTRY_WINDOW_END`, `NEW_SIGNAL_CUTOFF`, `EXIT_REMINDER`, `MANDATORY_EXIT`, `DAILY_SUMMARY`, `APP_SHUTDOWN`, `APP_AUTO_START`
  - Define strategy threshold constants: gap min/max percentages, volume threshold, target percentages, max risk percentage, signal expiry minutes
  - Requirement coverage: Req 6 (gap thresholds), Req 7 (volume threshold), Req 8 (entry window times), Req 9 (target percentages), Req 16 (trading time restrictions)

- [ ] 1.3 Implement `signalpilot/utils/logger.py` with logging configuration
  - Implement `configure_logging()` function as specified in design (Section 8.4)
  - Set up console handler (stdout) and rotating file handler (`signalpilot.log`, 10MB max, 5 backups)
  - Use format: `%(asctime)s | %(levelname)-8s | %(name)s | %(message)s`
  - Requirement coverage: supports observability across all requirements

- [ ] 1.4 Implement `signalpilot/utils/market_calendar.py` for trading day checks
  - Implement `is_trading_day(d: date) -> bool` that returns False for weekends
  - Implement `is_market_hours(dt: datetime) -> bool` that checks if time is between 9:15 AM and 3:30 PM IST
  - Implement `get_current_phase(dt: datetime) -> StrategyPhase` to map current time to the correct phase
  - Include a basic NSE holiday list for the current year
  - Write tests in `tests/test_utils/test_market_calendar.py`: verify weekdays return True, weekends return False, holidays return False, phase mapping is correct at boundary times
  - Requirement coverage: Req 32 (auto-start on weekdays), Req 33 (continuous scanning phases), Req 16 (time restrictions)

- [ ] 1.5 Implement `signalpilot/config.py` with Pydantic settings
  - Create `AppConfig` class extending `BaseSettings` as specified in design (Section 7.1)
  - Include all fields: Angel One credentials, Telegram config, DB path, instrument paths, risk management defaults, strategy parameters, scoring weights, trailing SL params, retry/resilience settings
  - Create `.env.example` with placeholder values from the design (Section 7.2)
  - Add `.env` to `.gitignore`
  - Write tests in `tests/test_config.py`: verify defaults load correctly, verify required fields raise validation errors when missing
  - Requirement coverage: Req 1 (auth credentials), Req 2 (WebSocket config), Req 13 (capital defaults), Req 14 (max positions)

- [ ] 1.6 Implement `signalpilot/utils/retry.py` with the retry decorator
  - Implement the `with_retry` async decorator as specified in design (Section 8.2)
  - Support configurable max_retries, base_delay, max_delay, exponential backoff, and exception types
  - Write tests in `tests/test_utils/test_retry.py`: verify retry count, verify exponential backoff delays, verify success on Nth attempt
  - Requirement coverage: Req 1.2 (auth retry), Req 2.3 (WebSocket reconnect), Req 4 (data fallback)

## 2. Data Models

- [ ] 2.1 Implement `signalpilot/db/models.py` with all core dataclasses
  - Implement all dataclasses from the design (Section 5.1): `Instrument`, `TickData`, `HistoricalReference`, `PreviousDayData`, `SignalDirection` enum, `CandidateSignal`, `RankedSignal`, `PositionSize`, `FinalSignal`, `SignalRecord`, `TradeRecord`, `UserConfig`, `ExitType` enum, `ExitAlert`, `PerformanceMetrics`, `DailySummary`
  - Also implement `StrategyPhase` enum and `ScoringWeights` dataclass
  - Write tests in `tests/test_db/test_models.py`: verify dataclass instantiation, default values, enum values
  - Requirement coverage: Req 28 (schema fields map to these models), Req 9 (SL/target fields), Req 10 (scoring fields), Req 19 (ExitType enum)

## 3. Database Layer

- [ ] 3.1 Implement `signalpilot/db/database.py` with DatabaseManager
  - Implement `DatabaseManager` class as specified in design (Section 4.7.1)
  - `initialize()`: open aiosqlite connection, enable WAL mode and foreign keys, execute schema SQL
  - `close()`: close connection
  - `_create_tables()`: execute the full schema SQL from design (Section 6.1) -- signals, trades, user_config tables with all indexes
  - Write tests in `tests/test_db/test_database.py`: verify tables are created with correct columns, verify WAL mode is enabled, verify idempotent table creation
  - Requirement coverage: Req 28.1 (create SQLite with three tables), Req 28.2 (signals columns), Req 28.3 (trades columns), Req 28.4 (user_config columns)

- [ ] 3.2 Implement `signalpilot/db/signal_repo.py` with SignalRepository
  - Implement `insert_signal(signal: SignalRecord) -> int` -- insert and return the new ID
  - Implement `update_status(signal_id: int, status: str)` -- update to "expired"
  - Implement `get_active_signals(date: date) -> list[SignalRecord]` -- non-expired, non-taken signals for today (query from Section 6.2)
  - Implement `get_signals_by_date(date: date) -> list[SignalRecord]`
  - Implement `expire_stale_signals()` -- bulk update using query from Section 6.2
  - Implement `get_latest_active_signal() -> SignalRecord | None` -- for TAKEN command
  - Write tests in `tests/test_db/test_signal_repo.py`: insert and retrieve, status updates, expiry logic, date filtering
  - Requirement coverage: Req 29.1 (insert signal), Req 29.2 (expire signals), Req 15 (signal expiry)

- [ ] 3.3 Implement `signalpilot/db/trade_repo.py` with TradeRepository
  - Implement `insert_trade(trade: TradeRecord) -> int`
  - Implement `close_trade(trade_id: int, exit_price: float, pnl_amount: float, pnl_pct: float, exit_reason: str)` -- update query from Section 6.2
  - Implement `get_active_trades() -> list[TradeRecord]` -- where exited_at IS NULL
  - Implement `get_active_trade_count() -> int` -- count query from Section 6.2
  - Implement `get_trades_by_date(date: date) -> list[TradeRecord]`
  - Implement `get_all_closed_trades() -> list[TradeRecord]` -- for JOURNAL
  - Write tests in `tests/test_db/test_trade_repo.py`: insert and retrieve, close trade updates, active count, filtering
  - Requirement coverage: Req 29.3 (insert on TAKEN), Req 29.4 (update on exit), Req 14.1-14.2 (active count for position limits)

- [ ] 3.4 Implement `signalpilot/db/config_repo.py` with ConfigRepository
  - Implement `get_user_config() -> UserConfig` -- return current config or create default
  - Implement `update_capital(total_capital: float)` -- update capital and updated_at
  - Implement `update_max_positions(max_positions: int)`
  - Implement `initialize_default(telegram_chat_id: str, total_capital: float, max_positions: int)` -- upsert default config
  - Write tests in `tests/test_db/test_config_repo.py`: default creation, capital update, retrieval
  - Requirement coverage: Req 25 (CAPITAL command updates config), Req 13 (position sizing uses config)

- [ ] 3.5 Implement `signalpilot/db/metrics.py` with MetricsCalculator
  - Implement `calculate_performance_metrics() -> PerformanceMetrics` -- aggregate query from Section 6.2 (win rate, total P&L, avg win, avg loss, best/worst trade)
  - Implement `calculate_daily_summary(date: date) -> DailySummary` -- daily summary query from Section 6.2
  - A "win" is `pnl_amount > 0`, a "loss" is `pnl_amount <= 0` (Req 30.3)
  - Write tests in `tests/test_db/test_metrics.py`: verify metrics with known trade data, verify edge cases (no trades, all wins, all losses)
  - Requirement coverage: Req 30 (performance metrics), Req 31 (daily summary), Req 24 (JOURNAL data)

## 4. Data Engine

- [ ] 4.1 Implement `signalpilot/data/market_data_store.py` with MarketDataStore
  - Implement `MarketDataStore` class as specified in design (Section 4.1.5)
  - Use `asyncio.Lock` for thread-safe access
  - Implement all methods: `update_tick`, `get_tick`, `set_historical`, `get_historical`, `accumulate_volume`, `get_accumulated_volume`, `get_all_ticks`
  - Volume accumulation tracks cumulative day volume per symbol (no candle aggregation needed per design decision 10.8)
  - Write tests in `tests/test_data/test_market_data_store.py`: verify tick updates, historical data storage, volume accumulation, concurrent access safety
  - Requirement coverage: Req 2.5 (update in-memory store within 1s), Req 3.4 (store historical data), Req 7 (volume accumulation)

- [ ] 4.2 Implement `signalpilot/data/instruments.py` with InstrumentManager
  - Implement `InstrumentManager` class as specified in design (Section 4.1.4)
  - `load()`: read Nifty 500 CSV, fetch Angel One instrument master JSON, cross-reference to build token mappings
  - Filter instrument master for NSE equity (`exch_seg == "NSE"`, symbol ends with `-EQ`)
  - Build `_instruments` dict (symbol -> Instrument) and `_token_map` dict (angel_token -> symbol)
  - Log warnings for symbols not found in instrument master (Req 5.3)
  - Implement `get_all_tokens()`, `get_symbol_by_token()`, `get_instrument()`, `symbols` property
  - Write tests in `tests/test_data/test_instruments.py` with mock CSV and mock instrument master: verify cross-reference, token mappings, missing symbol warnings
  - Requirement coverage: Req 5.1 (load instrument list), Req 5.2 (use for subscription), Req 5.3 (log missing instruments)

- [ ] 4.3 Implement `signalpilot/data/auth.py` with SmartAPIAuthenticator
  - Implement `SmartAPIAuthenticator` class as specified in design (Section 4.1.1)
  - `authenticate()`: generate TOTP via `pyotp`, call SmartConnect.generateSession, store tokens (auth_token, feed_token, refresh_token). Run in `asyncio.to_thread` since SmartConnect is synchronous
  - Apply `@with_retry(max_retries=3)` decorator for retry with exponential backoff
  - `refresh_session()`: re-authenticate using stored credentials when session expires
  - Properties for `auth_token`, `feed_token`, `smart_connect` that raise if not authenticated
  - Write tests in `tests/test_data/test_auth.py` with mocked SmartConnect: verify successful auth stores tokens, verify retry on failure, verify re-auth flow
  - Requirement coverage: Req 1.1 (authenticate on startup), Req 1.2 (retry 3x), Req 1.3 (store session), Req 1.4 (auto re-auth)

- [ ] 4.4 Implement `signalpilot/data/historical.py` with HistoricalDataFetcher
  - Implement `HistoricalDataFetcher` as specified in design (Section 4.1.3)
  - `fetch_previous_day_data()`: fetch prev close and prev high for all Nifty 500 via Angel One API, batched with `asyncio.Semaphore` for rate limiting (~3 req/s)
  - `fetch_average_daily_volume(lookback_days=20)`: fetch 20-day ADV for each stock
  - `_fetch_from_angel_one()`: use SmartConnect.getCandleData()
  - `_fetch_from_yfinance()`: use yfinance with `.NS` suffix as fallback, log warning (Req 4.2)
  - If both sources fail for an instrument, exclude it and log (Req 3.3, Req 4.3)
  - Write tests in `tests/test_data/test_historical.py`: mock Angel One API success, mock fallback to yfinance, mock total failure for exclusion
  - Requirement coverage: Req 3.1 (prev close/high), Req 3.2 (20-day ADV), Req 3.3 (exclude on failure), Req 4.1 (yfinance fallback), Req 4.2 (log warning), Req 4.3 (alert on both fail)

- [ ] 4.5 Implement `signalpilot/data/websocket_client.py` with WebSocketClient
  - Implement `WebSocketClient` as specified in design (Section 4.1.2)
  - `connect()`: create SmartWebSocketV2 instance, register callbacks (`_on_data`, `_on_close`, `_on_error`), subscribe to all Nifty 500 tokens
  - `_on_data()`: parse binary tick data, bridge into asyncio loop via `call_soon_threadsafe`, update MarketDataStore
  - `_on_close()`: trigger reconnection logic with up to 3 retries
  - `_on_error()`: log errors, trigger disconnect alert callback after retries exhausted
  - `disconnect()`: gracefully close WebSocket
  - Write tests in `tests/test_data/test_websocket_client.py`: mock WebSocket, verify subscription, verify tick parsing updates store, verify reconnection attempts, verify alert on failure
  - Requirement coverage: Req 2.1 (establish WebSocket), Req 2.2 (receive LTP/OHLCV), Req 2.3 (auto-reconnect), Req 2.4 (alert on failure), Req 2.5 (update store)

## 5. Strategy Engine

- [ ] 5.1 Implement `signalpilot/strategy/base.py` with abstract base class
  - Implement `StrategyPhase` enum, `SignalDirection` enum, `CandidateSignal` dataclass, and `BaseStrategy` ABC as specified in design (Section 4.2.1)
  - Define abstract methods: `name` property, `active_phases` property, `evaluate()` async method
  - Write a trivial test to verify ABC cannot be instantiated directly
  - Requirement coverage: Req 33 (extensible scanning architecture)

- [ ] 5.2 Implement `signalpilot/strategy/gap_and_go.py` with GapAndGoStrategy
  - Implement `GapAndGoStrategy(BaseStrategy)` as specified in design (Section 4.2.2)
  - Phase-dependent evaluation: OPENING phase (9:15-9:30) for gap detection + volume accumulation, ENTRY_WINDOW phase (9:30-9:45) for price hold validation + signal generation
  - `_detect_gaps_and_accumulate_volume()`: scan all symbols, calculate gap % = ((open - prev_close) / prev_close) * 100, flag candidates with 3-5% gap AND open > prev high (Req 6.1-6.4)
  - Volume check at 9:30: cumulative volume > 50% of 20-day ADV (Req 7.1-7.3)
  - `_validate_and_generate_signals()`: check current price > opening price (Req 8.2), disqualify if price drops below open (Req 8.3)
  - `_calculate_stop_loss()`: SL = opening price, capped at entry - 3% (Req 9.1, 9.4)
  - `_calculate_targets()`: T1 = entry + 5%, T2 = entry + 7% (Req 9.2, 9.3)
  - Track state per candidate: `_gap_candidates`, `_volume_validated`, `_disqualified`, `_signals_generated` sets
  - Write tests in `tests/test_strategy/test_gap_and_go.py`:
    - Test gap detection at exact 3% and 5% boundaries
    - Test exclusion when gap < 3% or > 5%
    - Test exclusion when open <= prev high
    - Test volume validation pass/fail
    - Test price hold validation and disqualification
    - Test SL calculation and 3% cap
    - Test target calculations
    - Test no signal after 9:45 AM (Req 8.4)
  - Requirement coverage: Req 6 (gap detection), Req 7 (volume validation), Req 8 (entry timing), Req 9 (SL/target calc)

## 6. Signal Ranker

- [ ] 6.1 Implement `signalpilot/ranking/scorer.py` with SignalScorer
  - Implement `ScoringWeights` dataclass and `SignalScorer` class as specified in design (Section 4.3.1)
  - `_normalize_gap()`: 3% -> 0.0, 5% -> 1.0, linear interpolation
  - `_normalize_volume_ratio()`: 0.5 -> 0.0, 3.0 -> 1.0
  - `_normalize_price_distance()`: 0% -> 0.0, 3%+ -> 1.0
  - `score()`: weighted composite = (normalized_gap * w1) + (normalized_volume * w2) + (normalized_price_distance * w3)
  - Write tests in `tests/test_ranking/test_scorer.py`: verify normalization functions at boundaries and mid-range, verify composite scoring with known weights
  - Requirement coverage: Req 10.1 (multi-factor scoring with configurable weights)

- [ ] 6.2 Implement `signalpilot/ranking/ranker.py` with SignalRanker
  - Implement `RankedSignal` dataclass and `SignalRanker` class as specified in design (Section 4.3.2)
  - `rank()`: score all candidates, sort descending, assign star ratings via `_score_to_stars()`, return top N (default 5)
  - `_score_to_stars()`: map 0.0-0.2 -> 1 star, ..., 0.8-1.0 -> 5 stars
  - Write tests in `tests/test_ranking/test_ranker.py`: verify ranking order, verify top-5 cutoff, verify star rating assignment, verify fewer than 5 candidates returns all
  - Requirement coverage: Req 10.2 (rank descending), Req 10.3 (star rating), Req 11.1 (top 5 selection), Req 11.2 (fewer than 5)

## 7. Risk Manager

- [ ] 7.1 Implement `signalpilot/risk/position_sizer.py` with PositionSizer
  - Implement `PositionSize` dataclass and `PositionSizer` class as specified in design (Section 4.4.1)
  - `calculate()`: per_trade_capital = total_capital / max_positions, quantity = floor(per_trade_capital / entry_price), capital_required = quantity * entry_price
  - Write tests in `tests/test_risk/test_position_sizer.py`: verify calculation with sample values, verify quantity=0 when stock price exceeds allocation, verify floor rounding
  - Requirement coverage: Req 13.1 (per-trade capital), Req 13.2 (quantity calc), Req 13.3 (include quantity in signal), Req 13.4 (suppress if qty=0)

- [ ] 7.2 Implement `signalpilot/risk/risk_manager.py` with RiskManager
  - Implement `FinalSignal` dataclass and `RiskManager` class as specified in design (Section 4.4.2)
  - `filter_and_size()`: check active trade count against max positions (Req 14.1), calculate position size for each ranked signal, auto-skip if quantity=0 and log reason (Req 12.1-12.3), set expiry to generated_at + 30 minutes (Req 15.1)
  - Return list of `FinalSignal` capped by available position slots
  - Write tests in `tests/test_risk/test_risk_manager.py`:
    - Test position limit enforcement (5 active trades -> no new signals)
    - Test auto-skip expensive stock (price > per-trade allocation)
    - Test normal signal passes through with correct sizing
    - Test expiry timestamp is set correctly
  - Requirement coverage: Req 12 (auto-skip expensive), Req 14 (max position limits), Req 15.1 (signal expiry)

## 8. Exit Monitor

- [ ] 8.1 Implement `signalpilot/monitor/exit_monitor.py` with ExitMonitor
  - Implement `TrailingStopState` dataclass, `ExitMonitor` class as specified in design (Section 4.5.1)
  - `check_all_trades()`: iterate all active trades, check each against exit conditions
  - `_check_trade()`: get current tick, update highest price, check trailing SL updates, check SL hit, check T2 (exit), check T1 (alert only)
  - `_update_trailing_stop()`: at +2% above entry -> move SL to entry (breakeven) + notify (Req 19.1), at +4% above entry -> trail at current_price - 2% + notify (Req 19.2), never move trailing SL down (Req 19.3)
  - `_trigger_exit()`: calculate P&L, call `db.close_trade()`, invoke alert callback, cleanup trailing state
  - `trigger_time_exit_check()`: handle 3:00 PM and 3:15 PM time-based exits (Req 20)
  - Write tests in `tests/test_monitor/test_exit_monitor.py`:
    - Test SL hit detection and alert (Req 18.1-18.3)
    - Test T1 hit sends advisory alert, not exit (Req 17.1, 17.3)
    - Test T2 hit triggers full exit (Req 17.2)
    - Test trailing SL at +2% moves to breakeven (Req 19.1)
    - Test trailing SL at +4% trails at price - 2% (Req 19.2)
    - Test trailing SL never moves down on price retrace (Req 19.3)
    - Test trailing SL hit triggers exit (Req 19.4)
    - Test time-based exit at 3:00 PM and 3:15 PM (Req 20.1-20.3)
    - Test T1 alert only fires once per trade
  - Requirement coverage: Req 17 (target alerts), Req 18 (SL alerts), Req 19 (trailing SL), Req 20 (time exit)

## 9. Telegram Bot

- [ ] 9.1 Implement `signalpilot/telegram/formatters.py` with message formatting functions
  - Implement `format_signal_message(signal: FinalSignal) -> str` as specified in design (Section 4.6.2) -- include all fields: direction, symbol, entry, SL with risk %, T1, T2, quantity, capital required, signal strength stars, strategy, reason, expiry, "Reply TAKEN" instruction
  - Implement `star_rating(strength: int) -> str` -- star display with label
  - Implement `format_exit_alert(alert: ExitAlert) -> str` -- SL hit, target hit, trailing SL update messages
  - Implement `format_status_message(signals, trades) -> str` -- active signals and TAKEN trades with live P&L
  - Implement `format_journal_message(metrics: PerformanceMetrics) -> str` -- performance summary
  - Implement `format_daily_summary(summary: DailySummary) -> str` -- end-of-day summary
  - Write tests in `tests/test_telegram/test_formatters.py`: verify all fields present in output, verify star ratings for 1-5, verify SL/target messages, verify empty state messages
  - Requirement coverage: Req 21.1 (signal format fields), Req 21.2 (template formatting), Req 21.3 (TAKEN instruction), Req 23.2-23.4 (STATUS format), Req 24.1 (JOURNAL format), Req 31.2 (daily summary format)

- [ ] 9.2 Implement `signalpilot/telegram/handlers.py` with command handler logic
  - Implement `handle_taken(signal_repo, trade_repo, exit_monitor, context)`: find latest active signal, create trade record, start exit monitoring, respond with confirmation (Req 22.1-22.4)
  - Implement `handle_status(signal_repo, trade_repo, market_data, context)`: query active signals and open trades, calculate live P&L, respond with formatted status (Req 23.1-23.4)
  - Implement `handle_journal(metrics_calculator, context)`: calculate performance metrics, respond with formatted journal (Req 24.1-24.3)
  - Implement `handle_capital(config_repo, context, amount)`: parse amount, update capital, respond with confirmation including new per-trade allocation (Req 25.1-25.4)
  - Implement `handle_help(context)`: respond with command list (Req 26.1)
  - Handle edge cases: TAKEN when no active signal, TAKEN when signal expired (Req 15.4), CAPITAL with invalid input
  - Write tests in `tests/test_telegram/test_handlers.py` with mocked DB and bot context: verify each command's response and side effects
  - Requirement coverage: Req 22 (TAKEN), Req 23 (STATUS), Req 24 (JOURNAL), Req 25 (CAPITAL), Req 26 (HELP), Req 15.4 (expired signal)

- [ ] 9.3 Implement `signalpilot/telegram/bot.py` with SignalPilotBot
  - Implement `SignalPilotBot` class as specified in design (Section 4.6.1)
  - `start()`: build Application with bot token, register message handlers (TAKEN, STATUS, JOURNAL, CAPITAL, HELP) with regex filters, initialize and start polling
  - `stop()`: gracefully stop updater, application, and shutdown
  - `send_signal(signal: FinalSignal)`: format and send signal message to configured chat_id with HTML parse mode
  - `send_alert(text: str)`: send plain alert message
  - `send_exit_alert(alert: ExitAlert)`: format and send exit alert
  - Track signal delivery latency and log warning if > 30 seconds (Req 21.4)
  - Write tests in `tests/test_telegram/test_bot.py` with mocked Application: verify handlers are registered, verify message sending, verify latency warning
  - Requirement coverage: Req 21 (signal delivery), Req 22-26 (command handling), Req 27 (scheduled alerts via send_alert)

## 10. Scheduler and Application Lifecycle

- [ ] 10.1 Implement `signalpilot/scheduler/scheduler.py` with MarketScheduler
  - Implement `MarketScheduler` class as specified in design (Section 4.8.1)
  - Use `AsyncIOScheduler` with IST timezone
  - `configure_jobs(app)`: register all scheduled jobs from the design table:
    - 9:00 AM: pre-market alert (Req 27.1)
    - 9:15 AM: start scanning (Req 33.1)
    - 2:30 PM: stop new signals (Req 16.1, Req 27.2)
    - 3:00 PM: exit reminder (Req 16.2, Req 20.1, Req 27.3)
    - 3:15 PM: mandatory exit (Req 16.5, Req 20.3)
    - 3:30 PM: daily summary (Req 27.4, Req 31)
    - 3:35 PM: shutdown (Req 34.1)
  - `start()` and `shutdown()` methods
  - Write tests in `tests/test_scheduler/test_scheduler.py`: verify all jobs are registered with correct times
  - Requirement coverage: Req 16 (time restrictions), Req 27 (scheduled alerts), Req 34 (auto-shutdown)

- [ ] 10.2 Implement `signalpilot/scheduler/lifecycle.py` with SignalPilotApp orchestrator
  - Implement `SignalPilotApp` class as specified in design (Section 4.8.2)
  - Wire all components together in `__init__()`: DatabaseManager, SmartAPIAuthenticator, InstrumentManager, MarketDataStore, HistoricalDataFetcher, WebSocketClient, GapAndGoStrategy, SignalScorer, SignalRanker, PositionSizer, RiskManager, ExitMonitor, SignalPilotBot, MarketScheduler
  - `startup()`: initialize DB, authenticate, load instruments, fetch historical data, set historical references in market data store, start bot, configure and start scheduler
  - `start_scanning()`: connect WebSocket, set scanning flag, create scan loop task
  - `_scan_loop()`: determine phase, evaluate strategy during OPENING/ENTRY_WINDOW, rank and filter signals, send via Telegram, check exits on every tick, expire stale signals, sleep 1 second
  - `_determine_phase()`: map time to StrategyPhase
  - `shutdown()`: stop scanning, disconnect WebSocket, shutdown scheduler, stop bot, close DB (Req 34.2-34.3)
  - `recover()`: re-authenticate, reconnect, reload today's signals/trades, resume monitoring, send recovery alert (Req 35.2-35.4)
  - Implement `_expire_stale_signals()`: check and expire signals past their expiry time, send Telegram notification (Req 15.2, 15.3)
  - Write tests in `tests/test_scheduler/test_lifecycle.py`: verify startup sequence calls, verify scan loop phase determination, verify shutdown sequence, verify recovery reloads state
  - Requirement coverage: Req 32 (auto-start), Req 33 (continuous scanning), Req 34 (auto-shutdown), Req 35 (crash recovery)

- [ ] 10.3 Implement `signalpilot/main.py` as the application entry point
  - Create the asyncio entry point that instantiates `AppConfig`, creates `SignalPilotApp`, and runs `startup()`
  - Detect if starting during market hours for crash recovery mode vs normal startup (Req 35.2)
  - Handle SIGINT/SIGTERM for graceful shutdown
  - Write test in `tests/test_main.py`: verify entry point creates app and calls startup
  - Requirement coverage: Req 32.2 (full startup sequence), Req 35.1-35.5 (crash recovery)

## 11. Integration Tests

- [ ] 11.1 Write full signal pipeline integration test
  - Create `tests/test_integration/test_signal_pipeline.py`
  - Feed mock tick data through the entire pipeline: MarketDataStore -> GapAndGoStrategy -> SignalRanker -> RiskManager -> formatted output
  - Verify a valid gap-up stock (4% gap, high volume, price holds above open) produces a correctly formatted FinalSignal with SL, targets, quantity, and star rating
  - Verify a stock that fails any condition (gap too small, low volume, price drops below open) produces no signal
  - Requirement coverage: Req 6-11 (full signal generation flow)

- [ ] 11.2 Write signal expiry integration test
  - Create test in `tests/test_integration/test_signal_expiry.py`
  - Generate a signal, simulate 30 minutes passing, verify signal status changes to "expired" in DB, verify expiry notification is sent
  - Verify TAKEN after expiry returns "signal no longer valid" message
  - Requirement coverage: Req 15 (signal expiry), Req 15.4 (TAKEN after expiry)

- [ ] 11.3 Write TAKEN-to-exit flow integration test
  - Create test in `tests/test_integration/test_trade_lifecycle.py`
  - Generate signal -> simulate TAKEN command -> feed price ticks that hit SL -> verify trade record updated with exit_price, pnl, exit_reason="sl_hit", verify alert sent
  - Same flow but with price hitting T1 (verify advisory alert, trade stays open) then T2 (verify exit)
  - Requirement coverage: Req 22 (TAKEN), Req 17 (target alerts), Req 18 (SL alert), Req 29.3-29.4 (trade logging)

- [ ] 11.4 Write trailing SL progression integration test
  - Create test in `tests/test_integration/test_trailing_sl.py`
  - Generate signal, TAKEN, feed price ticks: entry, +2% (verify SL moves to breakeven), +4% (verify trailing SL at price-2%), +5% (verify trail moves up), retrace to +3% (verify trail doesn't move down), hit trailing SL (verify exit)
  - Requirement coverage: Req 19.1-19.4 (trailing SL full lifecycle)

- [ ] 11.5 Write position limit enforcement integration test
  - Create test in `tests/test_integration/test_position_limits.py`
  - Generate 5 signals, TAKEN all, verify a 6th signal is suppressed. Close one trade, verify next signal is allowed
  - Requirement coverage: Req 14.1-14.3 (max position enforcement)

- [ ] 11.6 Write time-based exit integration test
  - Create test in `tests/test_integration/test_time_exits.py`
  - Have open trades, simulate 3:00 PM -> verify exit reminders with P&L, simulate 3:15 PM -> verify mandatory exit alerts
  - Requirement coverage: Req 16.2-16.5 (time-based restrictions), Req 20.1-20.3 (time exits)

- [ ] 11.7 Write crash recovery integration test
  - Create test in `tests/test_integration/test_crash_recovery.py`
  - Populate DB with today's signals and active trades, start app in recovery mode, verify it resumes monitoring active trades, verify recovery alert is sent
  - Requirement coverage: Req 35.2-35.4 (crash recovery)

## 12. Test Infrastructure and Fixtures

- [ ] 12.1 Create `tests/conftest.py` with shared test fixtures
  - Create fixture for in-memory SQLite database (initialized with schema)
  - Create fixture for MarketDataStore pre-populated with sample tick and historical data
  - Create fixture for sample CandidateSignal, RankedSignal, FinalSignal objects
  - Create fixture for AppConfig with test values
  - Create sample trade data fixtures for metrics testing
  - Requirement coverage: supports all test tasks

- [ ] 12.2 Create `tests/test_data/` with mock data fixtures
  - Create JSON file with sample tick sequences for gap-up stocks (valid and invalid scenarios)
  - Create JSON file with sample historical data (prev close, prev high, 20-day volumes)
  - Create JSON file with mock Angel One instrument master entries
  - Requirement coverage: supports test_strategy, test_integration tests
