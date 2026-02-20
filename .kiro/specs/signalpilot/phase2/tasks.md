# SignalPilot Phase 2 -- Implementation Tasks

## References
- Requirements: `/.kiro/specs/signalpilot/phase2/requirements.md`
- Design: `/.kiro/specs/signalpilot/phase2/design.md`
- Phase 2 PRD: `/PRD_Phase2_ORB_VWAP.md`

---

## 1. Configuration and Constants Updates

- [ ] 1.1 Add ORB strategy parameters to `AppConfig` in `signalpilot/config.py`
  - Add fields: `orb_range_min_pct` (default 0.5), `orb_range_max_pct` (default 3.0), `orb_volume_multiplier` (default 1.5), `orb_signal_window_end` (default "11:00"), `orb_target_1_pct` (default 1.5), `orb_target_2_pct` (default 2.5), `orb_breakeven_trigger_pct` (default 1.5), `orb_trail_trigger_pct` (default 2.0), `orb_trail_distance_pct` (default 1.0), `orb_gap_exclusion_pct` (default 3.0)
  - Requirement coverage: REQ-P2-006

- [ ] 1.2 Add ORB scoring weight fields to `AppConfig`
  - Add fields: `orb_scoring_volume_weight` (default 0.40), `orb_scoring_range_weight` (default 0.30), `orb_scoring_distance_weight` (default 0.30)
  - Requirement coverage: REQ-P2-006

- [ ] 1.3 Add VWAP strategy parameters to `AppConfig`
  - Add fields: `vwap_scan_start` (default "10:00"), `vwap_scan_end` (default "14:30"), `vwap_touch_threshold_pct` (default 0.3), `vwap_reclaim_volume_multiplier` (default 1.5), `vwap_pullback_volume_multiplier` (default 1.0), `vwap_max_signals_per_stock` (default 2), `vwap_cooldown_minutes` (default 60), `vwap_setup1_sl_below_vwap_pct` (default 0.5), `vwap_setup1_target1_pct` (default 1.0), `vwap_setup1_target2_pct` (default 1.5), `vwap_setup2_target1_pct` (default 1.5), `vwap_setup2_target2_pct` (default 2.0), `vwap_setup1_breakeven_trigger_pct` (default 1.0), `vwap_setup2_breakeven_trigger_pct` (default 1.5)
  - Requirement coverage: REQ-P2-011C

- [ ] 1.4 Add VWAP scoring weight fields to `AppConfig`
  - Add fields: `vwap_scoring_volume_weight` (default 0.35), `vwap_scoring_touch_weight` (default 0.35), `vwap_scoring_trend_weight` (default 0.30)
  - Requirement coverage: REQ-P2-011C

- [ ] 1.5 Add paper trading mode flags to `AppConfig`
  - Add fields: `orb_paper_mode` (default True), `vwap_paper_mode` (default True)
  - Requirement coverage: REQ-P2-036

- [ ] 1.6 Update `default_max_positions` from 5 to 8 in `AppConfig`
  - Requirement coverage: REQ-P2-015

- [ ] 1.7 Add `model_validator` for scoring weight sum validation
  - ORB weights must sum to 1.0 (tolerance 0.01), VWAP weights must sum to 1.0, Gap & Go weights must sum to 1.0
  - Application SHALL refuse to start if validation fails with clear error message
  - Requirement coverage: REQ-P2-041

- [ ] 1.8 Add Phase 2 time constants to `signalpilot/utils/constants.py`
  - Add: `ORB_WINDOW_END = time(11, 0)`, `VWAP_SCAN_START = time(10, 0)`, `OPENING_RANGE_LOCK = time(9, 45)`, `MAX_SIGNALS_PER_BATCH = 8`
  - Requirement coverage: REQ-P2-006, REQ-P2-011C

- [ ] 1.9 Update `.env.example` with all new Phase 2 fields
  - Requirement coverage: REQ-P2-006, REQ-P2-011C

- [ ] 1.10 Write tests for new config fields, defaults, and weight validation
  - Test all defaults load correctly, test invalid weight sums raise ValidationError, test env override works
  - Requirement coverage: REQ-P2-041

---

## 2. Data Model Updates

- [ ] 2.1 Extend `CandidateSignal` in `signalpilot/db/models.py`
  - Add `setup_type: str | None = None` (for VWAP: "uptrend_pullback" or "vwap_reclaim")
  - Add `strategy_specific_score: float | None = None`
  - Ensure `gap_pct` defaults to 0.0 for non-Gap & Go signals
  - Requirement coverage: REQ-P2-032

- [ ] 2.2 Extend `SignalRecord` in `signalpilot/db/models.py`
  - Add `setup_type: str | None = None`
  - Add `strategy_specific_score: float | None = None`
  - Requirement coverage: REQ-P2-032

- [ ] 2.3 Extend `TradeRecord` in `signalpilot/db/models.py`
  - Add `strategy: str = "gap_go"`
  - Requirement coverage: REQ-P2-033

- [ ] 2.4 Extend `UserConfig` in `signalpilot/db/models.py`
  - Add `gap_go_enabled: bool = True`, `orb_enabled: bool = True`, `vwap_enabled: bool = True`
  - Update `max_positions` default from 5 to 8
  - Requirement coverage: REQ-P2-023

- [ ] 2.5 Create `StrategyDaySummary` dataclass in `signalpilot/db/models.py`
  - Fields: `strategy_name: str`, `signals_generated: int`, `signals_taken: int`, `pnl: float`
  - Requirement coverage: REQ-P2-029

- [ ] 2.6 Extend `DailySummary` in `signalpilot/db/models.py`
  - Add `strategy_breakdown: dict[str, StrategyDaySummary] = field(default_factory=dict)`
  - Requirement coverage: REQ-P2-029

- [ ] 2.7 Create `StrategyPerformanceRecord` dataclass in `signalpilot/db/models.py`
  - Fields: `id: int | None`, `strategy: str`, `date: str`, `signals_generated: int`, `signals_taken: int`, `wins: int`, `losses: int`, `total_pnl: float`, `win_rate: float`, `avg_win: float`, `avg_loss: float`, `expectancy: float`, `capital_weight_pct: float`
  - Requirement coverage: REQ-P2-020

- [ ] 2.8 Update `__all__` exports in `signalpilot/db/models.py`
  - Requirement coverage: foundational

- [ ] 2.9 Verify backward compatibility -- existing Phase 1 code works with new defaults
  - Requirement coverage: REQ-P2-039

- [ ] 2.10 Write tests for all new dataclass fields and defaults in `tests/test_db/test_models.py`
  - Test instantiation with defaults, test optional fields, test backward compat
  - Requirement coverage: REQ-P2-032, REQ-P2-033

---

## 3. Database Schema Migration

- [ ] 3.1 Implement `_run_phase2_migration()` in `signalpilot/db/database.py`
  - Use `PRAGMA table_info()` to check column existence before adding (SQLite lacks `ADD COLUMN IF NOT EXISTS`)
  - Must be idempotent -- running twice has no effect
  - Requirement coverage: REQ-P2-019, REQ-P2-039

- [ ] 3.2 Add `setup_type TEXT` and `strategy_specific_score REAL` columns to signals table
  - Both nullable, no default needed (NULL for Phase 1 signals)
  - Requirement coverage: REQ-P2-019

- [ ] 3.3 Add `strategy TEXT NOT NULL DEFAULT 'gap_go'` column to trades table
  - Default ensures existing Phase 1 trades are valid without backfill
  - Requirement coverage: REQ-P2-022

- [ ] 3.4 Add `gap_go_enabled INTEGER NOT NULL DEFAULT 1`, `orb_enabled INTEGER NOT NULL DEFAULT 1`, `vwap_enabled INTEGER NOT NULL DEFAULT 1` columns to user_config table
  - Requirement coverage: REQ-P2-023

- [ ] 3.5 Create `strategy_performance` table with `CREATE TABLE IF NOT EXISTS`
  - Columns: `id INTEGER PRIMARY KEY`, `strategy TEXT NOT NULL`, `date TEXT NOT NULL`, `signals_generated INTEGER`, `signals_taken INTEGER`, `wins INTEGER`, `losses INTEGER`, `total_pnl REAL`, `win_rate REAL`, `avg_win REAL`, `avg_loss REAL`, `expectancy REAL`, `capital_weight_pct REAL`
  - Add UNIQUE constraint on `(strategy, date)` for upsert support
  - Requirement coverage: REQ-P2-020

- [ ] 3.6 Create `vwap_cooldown` table with `CREATE TABLE IF NOT EXISTS`
  - Columns: `id INTEGER PRIMARY KEY`, `symbol TEXT NOT NULL`, `last_signal_at TEXT NOT NULL`, `signal_count_today INTEGER NOT NULL DEFAULT 0`
  - Requirement coverage: REQ-P2-021

- [ ] 3.7 Update `_create_tables()` to call `_run_phase2_migration()` after Phase 1 schema
  - Requirement coverage: REQ-P2-039

- [ ] 3.8 Implement `StrategyPerformanceRepository` in new `signalpilot/db/strategy_performance_repo.py`
  - `upsert_daily(record: StrategyPerformanceRecord)` -- INSERT ON CONFLICT DO UPDATE on (strategy, date)
  - `get_performance_summary(strategy: str, start_date: date, end_date: date) -> list[StrategyPerformanceRecord]`
  - `get_by_date_range(start_date: date, end_date: date) -> list[StrategyPerformanceRecord]`
  - `_row_to_record()` helper
  - Requirement coverage: REQ-P2-020

- [ ] 3.9 Write migration tests in `tests/test_db/test_migration.py`
  - Test new columns exist after migration, test new tables exist, test idempotency (run twice safely), test existing data preserved
  - Requirement coverage: REQ-P2-039

- [ ] 3.10 Write `StrategyPerformanceRepository` tests in `tests/test_db/test_strategy_performance_repo.py`
  - Test upsert and retrieve, query by date range, conflict resolution (same strategy+date updates)
  - Requirement coverage: REQ-P2-020

---

## 4. Repository Updates

- [ ] 4.1 Update `SignalRepository.insert_signal()` in `signalpilot/db/signal_repo.py`
  - Include `setup_type` and `strategy_specific_score` columns in INSERT
  - Requirement coverage: REQ-P2-019

- [ ] 4.2 Add `has_signal_for_stock_today(symbol: str, today: date) -> bool` to `SignalRepository`
  - Query signals table for any signal with matching symbol and date (any strategy, any status)
  - Requirement coverage: REQ-P2-012

- [ ] 4.3 Expand `_VALID_STATUSES` in `SignalRepository` to include `"paper"` and `"position_full"`
  - Requirement coverage: REQ-P2-019

- [ ] 4.4 Update `SignalRepository._row_to_record()` for new columns
  - Requirement coverage: REQ-P2-019

- [ ] 4.5 Update `TradeRepository.insert_trade()` in `signalpilot/db/trade_repo.py` for `strategy` column
  - Populate from the corresponding signal's strategy name
  - Requirement coverage: REQ-P2-022

- [ ] 4.6 Add `get_trades_by_strategy(strategy: str) -> list[TradeRecord]` to `TradeRepository`
  - Requirement coverage: REQ-P2-022

- [ ] 4.7 Update `TradeRepository._row_to_record()` for `strategy` column
  - Requirement coverage: REQ-P2-022

- [ ] 4.8 Add strategy enabled flag methods to `ConfigRepository` in `signalpilot/db/config_repo.py`
  - `get_strategy_enabled(config_field: str) -> bool`
  - `set_strategy_enabled(config_field: str, enabled: bool)`
  - Requirement coverage: REQ-P2-023

- [ ] 4.9 Update `ConfigRepository.get_user_config()` to include strategy enabled flags
  - Requirement coverage: REQ-P2-023

- [ ] 4.10 Add per-strategy metric calculation to `MetricsCalculator` in `signalpilot/db/metrics.py`
  - `calculate_daily_summary_by_strategy(today: date) -> dict[str, StrategyDaySummary]`
  - `calculate_performance_metrics(strategy: str | None = None, ...)` -- optional strategy filter
  - Requirement coverage: REQ-P2-029

- [ ] 4.11 Write tests for all new repository methods
  - Extend existing test files: `test_signal_repo.py`, `test_trade_repo.py`, `test_config_repo.py`, `test_metrics.py`
  - Requirement coverage: REQ-P2-012, REQ-P2-019, REQ-P2-022, REQ-P2-023, REQ-P2-029

---

## 5. MarketDataStore Extensions

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

---

## 6. ORB Strategy Implementation

- [ ] 6.1 Create `signalpilot/strategy/orb.py` with `ORBStrategy(BaseStrategy)`
  - `name = "ORB"`, `active_phases = [StrategyPhase.CONTINUOUS]`
  - Constructor accepts `AppConfig` and `MarketDataStore`
  - Per-session state: `_signals_generated: set[str]`, `_excluded_stocks: set[str]`
  - Requirement coverage: REQ-P2-002

- [ ] 6.2 Implement `evaluate(symbols, market_data, now) -> list[CandidateSignal]`
  - Time-window check: only before `orb_signal_window_end` (11:00 AM)
  - Check opening range is locked before evaluating
  - Delegate to `_scan_for_breakouts()`
  - Requirement coverage: REQ-P2-002

- [ ] 6.3 Implement `_scan_for_breakouts()` with all entry conditions
  - Range size filter: 0.5% to 3% (`orb_range_min_pct`, `orb_range_max_pct`)
  - Breakout detection: `tick.ltp > opening_range.range_high`
  - Volume confirmation: `current_candle.volume >= avg_candle_vol * orb_volume_multiplier` (1.5x)
  - Gap exclusion: skip if stock gapped >= `orb_gap_exclusion_pct` (3%) -- check `_excluded_stocks`
  - Skip if stock already in `_signals_generated` (no duplicate ORB signals for same stock)
  - Requirement coverage: REQ-P2-002

- [ ] 6.4 Implement risk check and SL/target calculation
  - SL at `opening_range.range_low`
  - Risk cap: `(entry - range_low) / entry * 100 <= 3%` -- skip if exceeded
  - Target 1: `entry * (1 + orb_target_1_pct / 100)`
  - Target 2: `entry * (1 + orb_target_2_pct / 100)`
  - Requirement coverage: REQ-P2-003

- [ ] 6.5 Implement `mark_gap_stock(symbol)` for cross-strategy exclusion
  - Called by `SignalPilotApp` when Gap & Go detects a 3%+ gap, adds to `_excluded_stocks`
  - Requirement coverage: REQ-P2-002 (gap exclusion rule)

- [ ] 6.6 Implement `reset()` for daily state clear
  - Clear `_signals_generated` and `_excluded_stocks`
  - Requirement coverage: foundational

- [ ] 6.7 Write tests: valid breakout generates signal in `tests/test_strategy/test_orb.py`
  - Breakout above range_high with volume >= 1.5x, range size in 0.5-3%, no gap exclusion -> produces CandidateSignal
  - Requirement coverage: REQ-P2-002

- [ ] 6.8 Write tests: rejection conditions
  - No signal if range not locked, range size < 0.5% excluded, range size > 3% excluded, gap 3%+ excluded, volume below 1.5x rejected, risk > 3% rejected, no signals after 11:00 AM, no duplicate for same stock
  - Requirement coverage: REQ-P2-001, REQ-P2-002, REQ-P2-003

- [ ] 6.9 Write tests: SL at range low, T1/T2 calculations correct
  - Requirement coverage: REQ-P2-003

- [ ] 6.10 Write tests: `reset()` clears state, `mark_gap_stock()` excludes correctly
  - Requirement coverage: REQ-P2-002

---

## 7. VWAP Reversal Strategy Implementation

- [ ] 7.1 Create `signalpilot/strategy/vwap_reversal.py` with `VWAPReversalStrategy(BaseStrategy)`
  - `name = "VWAP Reversal"`, `active_phases = [StrategyPhase.CONTINUOUS]`
  - Constructor accepts `AppConfig`, `MarketDataStore`, and `VWAPCooldownTracker`
  - Track `_last_evaluated_candle: dict[str, datetime]` to avoid re-evaluation
  - Requirement coverage: REQ-P2-009, REQ-P2-010

- [ ] 7.2 Implement `evaluate(symbols, market_data, now) -> list[CandidateSignal]`
  - Time-window check: only between 10:00 AM and 2:30 PM
  - Iterate all symbols, get completed 15-min candles, delegate to `_scan_for_setups()`
  - Requirement coverage: REQ-P2-009, REQ-P2-010

- [ ] 7.3 Implement `_check_uptrend_pullback()` (Setup 1)
  - Prior candle(s) closed above VWAP (established uptrend)
  - Price touched or dipped below VWAP (within 0.3% of VWAP)
  - Current 15-min candle closes back above VWAP
  - Volume on bounce candle >= average 15-min candle volume
  - Generate CandidateSignal with `strategy_name="VWAP Reversal"`, `setup_type="uptrend_pullback"`
  - SL at VWAP minus 0.5%
  - Target 1 at entry + 1%, Target 2 at entry + 1.5%
  - Requirement coverage: REQ-P2-009

- [ ] 7.4 Implement `_check_vwap_reclaim()` (Setup 2)
  - Prior candle(s) closed below VWAP
  - Current 15-min candle closes above VWAP
  - Volume on reclaim candle >= 1.5x average 15-min candle volume (higher threshold)
  - Generate CandidateSignal with `strategy_name="VWAP Reversal"`, `setup_type="vwap_reclaim"`
  - Reason text includes "Higher Risk" label
  - SL below recent swing low (lowest low of last 3 completed 15-min candles)
  - Target 1 at entry + 1.5%, Target 2 at entry + 2%
  - Requirement coverage: REQ-P2-010

- [ ] 7.5 Integrate `VWAPCooldownTracker` guardrails
  - Before generating signal, call `cooldown_tracker.can_signal(symbol, now)`
  - After generating signal, call `cooldown_tracker.record_signal(symbol, now)`
  - Requirement coverage: REQ-P2-011

- [ ] 7.6 Implement `reset()` for daily state clear
  - Clear `_last_evaluated_candle`, reset cooldown tracker
  - Requirement coverage: foundational

- [ ] 7.7 Write tests: Setup 1 valid conditions generate signal in `tests/test_strategy/test_vwap_reversal.py`
  - Prior candle above VWAP + price touches VWAP + bounce above + volume OK -> produces signal with setup_type="uptrend_pullback"
  - Requirement coverage: REQ-P2-009

- [ ] 7.8 Write tests: Setup 1 rejection conditions
  - No prior candle above VWAP, price did not touch VWAP, candle closes below VWAP, volume insufficient
  - Requirement coverage: REQ-P2-009

- [ ] 7.9 Write tests: Setup 2 valid conditions generate signal with "Higher Risk"
  - Prior below VWAP + reclaim above + volume 1.5x -> signal with setup_type="vwap_reclaim" and Higher Risk in reason
  - Requirement coverage: REQ-P2-010

- [ ] 7.10 Write tests: Setup 2 rejection conditions
  - Volume below 1.5x, already above VWAP
  - Requirement coverage: REQ-P2-010

- [ ] 7.11 Write tests: time window enforcement, guardrails, SL calculations
  - No signals before 10:00 AM or after 2:30 PM, max 2 signals/stock/day, 60-min cooldown, correct SL for both setups
  - Requirement coverage: REQ-P2-011

---

## 8. VWAP Cooldown Tracker and Duplicate Checker

- [ ] 8.1 Create `signalpilot/monitor/vwap_cooldown.py` with `VWAPCooldownTracker`
  - Internal `_CooldownEntry` dataclass: `signal_count: int`, `last_signal_at: datetime`
  - `_entries: dict[str, _CooldownEntry]` -- keyed by symbol
  - Configurable `max_signals_per_stock` (default 2) and `cooldown_minutes` (default 60)
  - Requirement coverage: REQ-P2-011, REQ-P2-021

- [ ] 8.2 Implement `can_signal(symbol: str, now: datetime) -> bool`
  - Return False if `signal_count >= max_signals_per_stock`
  - Return False if `now - last_signal_at < timedelta(minutes=cooldown_minutes)`
  - Return True otherwise (or if symbol has no entry yet)
  - Requirement coverage: REQ-P2-011

- [ ] 8.3 Implement `record_signal(symbol: str, now: datetime)`
  - Upsert entry: increment count, update `last_signal_at`
  - Requirement coverage: REQ-P2-011

- [ ] 8.4 Implement `reset()`, `get_state()`, `restore_state()`
  - `reset()` clears all entries (called at start of each trading day)
  - `get_state()` / `restore_state()` for crash recovery (serialize to/from `vwap_cooldown` table)
  - Requirement coverage: REQ-P2-021

- [ ] 8.5 Create `signalpilot/monitor/duplicate_checker.py` with `DuplicateChecker`
  - Constructor accepts `SignalRepository` and `TradeRepository`
  - Requirement coverage: REQ-P2-012

- [ ] 8.6 Implement `filter_duplicates(candidates: list[CandidateSignal], today: date) -> list[CandidateSignal]`
  - For each candidate, check `signal_repo.has_signal_for_stock_today(symbol, today)` -- remove if exists
  - Check `trade_repo.get_active_trades()` for active position in same stock -- remove if exists
  - Log suppression reason for each removed candidate
  - Requirement coverage: REQ-P2-012

- [ ] 8.7 Write VWAP cooldown tests in `tests/test_monitor/test_vwap_cooldown.py`
  - can_signal True initially, False after max signals, False within cooldown window, True after cooldown expires, reset clears all, get_state/restore_state round-trip
  - Requirement coverage: REQ-P2-011

- [ ] 8.8 Write duplicate checker tests in `tests/test_monitor/test_duplicate_checker.py`
  - Existing signal blocks new, active trade blocks new, different stock passes, empty input returns empty
  - Requirement coverage: REQ-P2-012

---

## 9. Signal Scoring Updates

- [ ] 9.1 Create `signalpilot/ranking/orb_scorer.py` with `ORBScorer`
  - `score(signal, avg_candle_volume, range_size_pct) -> float`
  - Volume normalization: 1.5x -> 0.0, 4.0x -> 1.0 (linear interpolation)
  - Range tightness normalization: 3% -> 0.0, 0.5% -> 1.0 (inverse -- tighter = better)
  - Distance from breakout normalization: further -> lower score
  - Weighted composite: volume (40%) + range (30%) + distance (30%)
  - Output normalized to [0.0, 1.0]
  - Requirement coverage: REQ-P2-005

- [ ] 9.2 Create `signalpilot/ranking/vwap_scorer.py` with `VWAPScorer`
  - `score(signal, avg_candle_volume, vwap_touch_pct, candles_above_vwap_ratio) -> float`
  - Volume normalization: 1.0x -> 0.0, 3.0x -> 1.0
  - VWAP touch precision normalization: 0.3% -> 0.0, 0% (exact touch) -> 1.0
  - Trend alignment normalization: ratio of candles above VWAP
  - Weighted composite: volume (35%) + touch precision (35%) + trend alignment (30%)
  - Output normalized to [0.0, 1.0]
  - Requirement coverage: REQ-P2-011B

- [ ] 9.3 Update `SignalScorer` in `signalpilot/ranking/scorer.py`
  - Update `__init__()` to accept `orb_scorer: ORBScorer | None` and `vwap_scorer: VWAPScorer | None`
  - Update `score()` to dispatch based on `signal.strategy_name`: "ORB" -> ORBScorer, "VWAP Reversal" -> VWAPScorer, default -> existing Gap & Go scoring
  - Preserve `_score_gap_and_go()` as the default path (no change to Phase 1 behavior)
  - Requirement coverage: REQ-P2-013

- [ ] 9.4 Update `SignalRanker` in `signalpilot/ranking/ranker.py`
  - Update `max_signals` default from 5 to 8 for cross-strategy ranking
  - Requirement coverage: REQ-P2-013

- [ ] 9.5 Write ORB scorer tests in `tests/test_ranking/test_orb_scorer.py`
  - Test normalization at boundaries (min/max), mid-range values, weighted output in [0,1]
  - Requirement coverage: REQ-P2-005

- [ ] 9.6 Write VWAP scorer tests in `tests/test_ranking/test_vwap_scorer.py`
  - Test normalization at boundaries, mid-range values, trend alignment, weighted output in [0,1]
  - Requirement coverage: REQ-P2-011B

- [ ] 9.7 Extend `tests/test_ranking/test_scorer.py` with strategy dispatch tests
  - Correct scorer called for each strategy name, unknown strategy falls back to Gap & Go
  - Requirement coverage: REQ-P2-013

---

## 10. Multi-Strategy Integration (Scan Loop and Lifecycle)

- [ ] 10.1 Update `SignalPilotApp.__init__()` in `signalpilot/scheduler/lifecycle.py`
  - Change `strategy` parameter to `strategies: list` (list of `BaseStrategy` instances)
  - Add `duplicate_checker: DuplicateChecker` parameter
  - Add `capital_allocator: CapitalAllocator | None = None` parameter
  - Add `strategy_performance_repo: StrategyPerformanceRepository | None = None` parameter
  - Requirement coverage: REQ-P2-014

- [ ] 10.2 Update `_scan_loop()` for multi-strategy evaluation
  - Iterate all registered strategies, call `evaluate()` only on those whose `active_phases` include the current `StrategyPhase`
  - Filter out strategies whose enabled flag is False in `user_config` (via `_get_enabled_strategies()`)
  - Keep `_accepting_signals = True` during `StrategyPhase.CONTINUOUS` phase (was previously only OPENING/ENTRY_WINDOW)
  - Requirement coverage: REQ-P2-014, REQ-P2-031

- [ ] 10.3 Integrate deduplication and cross-strategy ranking
  - Merge all candidates from all strategies in the same scan cycle
  - Call `DuplicateChecker.filter_duplicates()` before ranking
  - Rank the combined, deduplicated list via `SignalRanker.rank()`
  - Requirement coverage: REQ-P2-012, REQ-P2-013

- [ ] 10.4 Update `_signal_to_record()` to include `setup_type` and `strategy_specific_score`
  - Requirement coverage: REQ-P2-032

- [ ] 10.5 Update `send_daily_summary()` to include per-strategy breakdown
  - Query `MetricsCalculator.calculate_daily_summary_by_strategy()` and pass to formatter
  - Requirement coverage: REQ-P2-029

- [ ] 10.6 Add `_get_enabled_strategies(user_config: UserConfig) -> list[BaseStrategy]`
  - Static method that filters `self._strategies` by the corresponding enabled flag in user_config
  - Requirement coverage: REQ-P2-023

- [ ] 10.7 Write tests in `tests/test_scheduler/test_lifecycle.py`
  - Multi-strategy evaluation during CONTINUOUS phase, strategy skipped when disabled, deduplication removes same-stock signals across strategies, scan loop handles no candidates gracefully
  - Requirement coverage: REQ-P2-014, REQ-P2-031, REQ-P2-038

---

## 11. Exit Monitor Updates (Per-Strategy Trailing SL)

- [ ] 11.1 Add `TrailingStopConfig` dataclass to `signalpilot/monitor/exit_monitor.py`
  - Fields: `breakeven_trigger_pct: float`, `trail_trigger_pct: float | None`, `trail_distance_pct: float | None`
  - Requirement coverage: REQ-P2-004, REQ-P2-011A

- [ ] 11.2 Define `DEFAULT_TRAILING_CONFIGS` mapping strategy name to `TrailingStopConfig`
  - Gap & Go: breakeven at 2.0%, trail at 4.0% with 2.0% distance
  - ORB: breakeven at 1.5%, trail at 2.0% with 1.0% distance
  - VWAP Reversal (Setup 1): breakeven at 1.0%, no trailing (None/None)
  - VWAP Reversal (Setup 2): breakeven at 1.5%, no trailing (None/None)
  - Requirement coverage: REQ-P2-004, REQ-P2-011A

- [ ] 11.3 Update `ExitMonitor.__init__()` to accept `trailing_configs: dict[str, TrailingStopConfig] | None`
  - Requirement coverage: REQ-P2-004

- [ ] 11.4 Implement `_get_config_for_trade(trade: TradeRecord) -> TrailingStopConfig`
  - Look up config by `trade.strategy`, fall back to Gap & Go defaults for unknown strategies
  - For VWAP trades, further distinguish by `setup_type` if available
  - Requirement coverage: REQ-P2-004, REQ-P2-011A

- [ ] 11.5 Update `_update_trailing_stop()` to use per-trade config
  - Replace class-level scalar thresholds with config from `_get_config_for_trade()`
  - Maintain backward compatibility (Phase 1 trades still work correctly)
  - Requirement coverage: REQ-P2-004, REQ-P2-011A

- [ ] 11.6 Write tests in `tests/test_monitor/test_exit_monitor.py`
  - ORB: breakeven at +1.5%, trail at +2% with 1% distance
  - VWAP Setup 1: breakeven at +1.0%, no trailing beyond breakeven
  - VWAP Setup 2: breakeven at +1.5%, no trailing beyond breakeven
  - Gap & Go: unchanged behavior (2.0%/4.0%/2.0%)
  - Unknown strategy: falls back to Gap & Go config
  - Requirement coverage: REQ-P2-004, REQ-P2-011A

---

## 12. Risk Manager and Capital Allocator

- [ ] 12.1 Create `signalpilot/risk/capital_allocator.py` with `CapitalAllocator`
  - Constructor accepts `StrategyPerformanceRepository` and `ConfigRepository`
  - Define `StrategyAllocation` dataclass: `strategy_name`, `weight_pct`, `allocated_capital`, `max_positions`
  - Define `STRATEGY_NAMES = ["gap_go", "ORB", "VWAP Reversal"]` and `RESERVE_PCT = 0.20`
  - Requirement coverage: REQ-P2-016

- [ ] 12.2 Implement `calculate_allocations(total_capital: float, max_positions: int, today: date) -> dict[str, StrategyAllocation]`
  - Formula: `weight = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)` per strategy
  - Normalize weights to sum to (1 - RESERVE_PCT) = 0.80
  - Allocate positions per strategy: `max_positions * strategy_weight` (rounded, min 1)
  - Reserve 20% (1 position slot) as buffer for 5-star exceptional signals
  - Fallback: equal allocation when no historical data (first week)
  - Requirement coverage: REQ-P2-016

- [ ] 12.3 Implement `check_auto_pause(today: date) -> list[str]`
  - Query trailing 30-day performance for each strategy
  - If win rate < 40% AND sample size >= 10 trades -> return strategy name for auto-pause
  - Requirement coverage: REQ-P2-018

- [ ] 12.4 Implement `set_manual_allocation(allocations: dict[str, float])` and `enable_auto_allocation()`
  - Manual override sets static weights, disables auto-rebalancing
  - `enable_auto_allocation()` re-enables auto mode
  - Requirement coverage: REQ-P2-026

- [ ] 12.5 Update `RiskManager` in `signalpilot/risk/risk_manager.py`
  - Accept optional `CapitalAllocator` in constructor
  - Support strategy-aware position sizing: per-trade capital from allocator if available
  - Update per-trade capital from `total_capital / 8` (new max positions)
  - Requirement coverage: REQ-P2-015

- [ ] 12.6 Add weekly rebalancing cron job to `MarketScheduler` in `signalpilot/scheduler/scheduler.py`
  - Schedule on Sunday (or first trading day after) to recalculate strategy weights
  - Send Telegram summary of new allocation
  - Log warning if any strategy's allocation changes > 10%
  - Requirement coverage: REQ-P2-017

- [ ] 12.7 Write tests in `tests/test_risk/test_capital_allocator.py`
  - Equal allocation with no historical data, weighted allocation with known performance data, auto-pause trigger (win rate < 40%, >= 10 trades), manual override and auto re-enable, reserve buffer enforcement (20% always reserved)
  - Requirement coverage: REQ-P2-016, REQ-P2-017, REQ-P2-018

---

## 13. Telegram Bot Updates

- [ ] 13.1 Implement `handle_pause()` in `signalpilot/telegram/handlers.py`
  - Parse "PAUSE GAP" / "PAUSE ORB" / "PAUSE VWAP"
  - Map to `config_repo.set_strategy_enabled(field, False)`
  - Respond: "[Strategy Name] paused. No signals will be generated from this strategy."
  - Handle: no strategy name -> usage instructions, already paused -> "already paused"
  - Requirement coverage: REQ-P2-024

- [ ] 13.2 Implement `handle_resume()` in `signalpilot/telegram/handlers.py`
  - Parse "RESUME GAP" / "RESUME ORB" / "RESUME VWAP"
  - Map to `config_repo.set_strategy_enabled(field, True)`
  - Respond: "[Strategy Name] resumed. Signals will be generated when conditions are met."
  - Handle: no strategy name -> usage instructions, already active -> "already active"
  - Requirement coverage: REQ-P2-025

- [ ] 13.3 Implement `handle_allocate()` in `signalpilot/telegram/handlers.py`
  - "ALLOCATE" alone -> show current allocation per strategy (weight %, capital, positions, reserve)
  - "ALLOCATE GAP 40 ORB 20 VWAP 20" -> set manual allocation (reject if sum > 80%)
  - "ALLOCATE AUTO" -> re-enable automatic rebalancing
  - Requirement coverage: REQ-P2-026

- [ ] 13.4 Implement `handle_strategy()` in `signalpilot/telegram/handlers.py`
  - Query `StrategyPerformanceRepository` for trailing 30-day data per strategy
  - Format response per PRD template (Section 5.5): strategy name, win rate, trades, avg win/loss, net P&L, allocation %
  - Include next rebalancing date (next Sunday)
  - Handle: no trades for a strategy -> show "No trades" with allocation
  - Requirement coverage: REQ-P2-027

- [ ] 13.5 Update `handle_help()` with Phase 2 commands
  - Add ALLOCATE, STRATEGY, PAUSE, RESUME with brief descriptions
  - Requirement coverage: REQ-P2-030

- [ ] 13.6 Update `format_signal_message()` in `signalpilot/telegram/formatters.py`
  - Include strategy name with setup type (e.g., "VWAP Reversal (Uptrend Pullback)")
  - Show "Positions open: X/8" (updated from X/5)
  - Add "Higher Risk" warning for VWAP Reclaim (setup_type="vwap_reclaim") signals
  - Show "Position full -- signal for reference only" when status is "position_full"
  - Requirement coverage: REQ-P2-028

- [ ] 13.7 Update `format_daily_summary()` in `signalpilot/telegram/formatters.py`
  - Add "BY STRATEGY" section with per-strategy rows: strategy icon, name, signal count, taken count, P&L
  - Follow PRD template (Section 5.4)
  - Requirement coverage: REQ-P2-029

- [ ] 13.8 Add `format_strategy_report()` for STRATEGY command output
  - Follow PRD template (Section 5.5)
  - Requirement coverage: REQ-P2-027

- [ ] 13.9 Add `format_allocation_summary()` for weekly rebalance notification
  - Requirement coverage: REQ-P2-017

- [ ] 13.10 Register new command handlers in `signalpilot/telegram/bot.py`
  - Register PAUSE, RESUME, ALLOCATE, STRATEGY with regex filters
  - Requirement coverage: REQ-P2-024, REQ-P2-025, REQ-P2-026, REQ-P2-027

- [ ] 13.11 Write handler tests in `tests/test_telegram/test_phase2_handlers.py`
  - PAUSE: happy path, already paused, no strategy name
  - RESUME: happy path, already active, no strategy name
  - ALLOCATE: show, set manual, AUTO, over 80% rejection
  - STRATEGY: with data, no trades, next rebalance date
  - Requirement coverage: REQ-P2-024, REQ-P2-025, REQ-P2-026, REQ-P2-027

- [ ] 13.12 Write formatter tests in `tests/test_telegram/test_formatters.py`
  - Updated signal format with strategy name/setup type, X/8, Higher Risk label, position_full display, daily summary with per-strategy breakdown
  - Requirement coverage: REQ-P2-028, REQ-P2-029

---

## 14. Backtesting Framework

- [ ] 14.1 Create `signalpilot/backtest/__init__.py`
  - Requirement coverage: foundational

- [ ] 14.2 Create `signalpilot/backtest/data_loader.py` with `BacktestDataLoader`
  - `load_historical_data(symbols, period="1y") -> dict[str, DataFrame]` -- fetch 1 year OHLCV via yfinance with local caching
  - Convert to `Candle15Min` and tick-equivalent data structures for strategy replay
  - Requirement coverage: REQ-P2-034

- [ ] 14.3 Create `signalpilot/backtest/runner.py` with `BacktestRunner`
  - `run(strategy_class, data, config) -> BacktestResult`
  - Replay historical data day by day: simulate opening range calculation (ORB), VWAP calculation (VWAP), candle evaluation
  - Apply same position sizing, SL, target, and trailing SL rules as live system
  - Collect all simulated signals and trades
  - Requirement coverage: REQ-P2-034

- [ ] 14.4 Create `signalpilot/backtest/reporter.py` with `BacktestReporter`
  - `validate(result: BacktestResult) -> BacktestReport`
  - Calculate: total signals, win rate, total P&L, avg win, avg loss, expectancy, max consecutive losses, max drawdown
  - Validate against thresholds: win rate > 55%, positive expectancy, max consecutive losses <= 8, max drawdown <= 15%, min 100 signals
  - ORB-specific target: win rate >= 60%
  - VWAP-specific target: win rate >= 65%
  - Output PASS/FAIL with details
  - Requirement coverage: REQ-P2-035

- [ ] 14.5 Write backtest runner tests in `tests/test_backtest/test_runner.py`
  - Test with mock historical data produces expected signal count, test position sizing applied, test SL/target logic simulated
  - Requirement coverage: REQ-P2-034

- [ ] 14.6 Write reporter validation tests in `tests/test_backtest/test_reporter.py`
  - Test PASS scenario (all thresholds met), test FAIL scenario (win rate below 55%), test individual threshold failures
  - Requirement coverage: REQ-P2-035

---

## 15. Paper Trading Mode

- [ ] 15.1 Add paper mode check in scan loop in `signalpilot/scheduler/lifecycle.py`
  - Check `config.orb_paper_mode` / `config.vwap_paper_mode` flags
  - For paper-mode strategies, set `status="paper"` on generated signals
  - Requirement coverage: REQ-P2-036

- [ ] 15.2 Track paper trades through exit monitor
  - Paper signals with status="paper" should still be tracked by exit monitor identically to live trades (SL/target/trailing SL evaluation)
  - Requirement coverage: REQ-P2-036

- [ ] 15.3 Add "PAPER TRADE" prefix in `signalpilot/telegram/formatters.py`
  - Paper signals sent via Telegram prefixed with "PAPER TRADE" and note: "This is not a live signal"
  - Requirement coverage: REQ-P2-036

- [ ] 15.4 Implement paper trading report generation
  - After 2-week paper period, generate comparison report: paper win rate vs backtest win rate, paper P&L vs expected, variance %, PASS/FAIL recommendation
  - "WITHIN TOLERANCE -- Ready for live deployment" if variance <= 10%
  - "OUTSIDE TOLERANCE -- Review and re-calibrate before going live" if variance > 10%
  - Send report via Telegram
  - Requirement coverage: REQ-P2-037

- [ ] 15.5 Write paper trading tests
  - Paper signal gets `status="paper"`, paper signal formatted with prefix, paper trade tracked through exit monitor, report within tolerance shows PASS, report outside tolerance shows FAIL
  - Requirement coverage: REQ-P2-036, REQ-P2-037

---

## 16. Phase 2 Integration Tests

- [ ] 16.1 Add Phase 2 sample fixtures to `tests/conftest.py`
  - `sample_orb_candidate` -- ORB CandidateSignal with valid breakout data
  - `sample_vwap_candidate` -- VWAP Uptrend Pullback CandidateSignal
  - `sample_vwap_reclaim_candidate` -- VWAP Reclaim CandidateSignal with Higher Risk
  - Requirement coverage: REQ-P2-040

- [ ] 16.2 Update `tests/test_integration/conftest.py`
  - Update `make_app()` to accept `strategies` list parameter
  - Add `make_signal_record()` overloads for ORB/VWAP signal types
  - Add Phase 2 helpers: `make_orb_signal()`, `make_vwap_signal()`
  - Requirement coverage: REQ-P2-040

- [ ] 16.3 Write multi-strategy scan loop integration test in `tests/test_integration/test_multi_strategy_scan.py`
  - 3 strategies active, feed mock data, verify correct phase-based evaluation, verify candidates merged and ranked across strategies
  - Requirement coverage: REQ-P2-014, REQ-P2-031

- [ ] 16.4 Write cross-strategy deduplication test in `tests/test_integration/test_dedup_cross_strategy.py`
  - Gap & Go signal for stock A, then ORB should NOT signal stock A same day, VWAP should NOT signal stock A same day
  - Requirement coverage: REQ-P2-012

- [ ] 16.5 Write position limit at 8 test in `tests/test_integration/test_position_limit_8.py`
  - With 8 active trades, no new signals sent. With 7, one allowed. Position-full signals tagged correctly
  - Requirement coverage: REQ-P2-015

- [ ] 16.6 Write daily summary with per-strategy breakdown test in `tests/test_integration/test_daily_summary_phase2.py`
  - Daily summary includes BY STRATEGY section, totals are correct across all strategies
  - Requirement coverage: REQ-P2-029

- [ ] 16.7 Write strategy pause/resume flow test in `tests/test_integration/test_pause_resume_flow.py`
  - PAUSE ORB -> scan loop skips ORB -> RESUME ORB -> ORB evaluates again
  - Requirement coverage: REQ-P2-024, REQ-P2-025

- [ ] 16.8 Add structured logging context assertions for Phase 2 components
  - Verify `strategy` and `setup_type` context fields set via `set_context()` during Phase 2 strategy evaluation
  - Requirement coverage: REQ-P2-042

- [ ] 16.9 Verify all tests pass with 0 failures
  - Run full test suite: `pytest tests/` -- all Phase 1 + Phase 2 tests pass
  - Requirement coverage: REQ-P2-040

---

## Dependency Graph

```
Task 1 (Config & Constants)
    |
    +---> Task 2 (Data Models)
    |         |
    |         +---> Task 3 (Schema Migration)
    |         |         |
    |         |         +---> Task 4 (Repository Updates)
    |         |         |         |
    |         |         |         +---> Task 10 (Multi-Strategy Integration)
    |         |         |         +---> Task 12 (Capital Allocator)
    |         |         |         +---> Task 13 (Telegram Updates)
    |         |         |
    |         |         +---> Task 8 (Cooldown & Duplicate Checker)
    |         |                   |
    |         |                   +---> Task 7 (VWAP Strategy)
    |         |
    |         +---> Task 9 (Scoring Updates)
    |         +---> Task 11 (Exit Monitor Updates)
    |
    +---> Task 5 (MarketDataStore Extensions)
              |
              +---> Task 6 (ORB Strategy)
              +---> Task 7 (VWAP Strategy)

Task 6 + 7 -------> Task 14 (Backtesting)
Task 10 + 14 -----> Task 15 (Paper Trading)
All tasks --------> Task 16 (Integration Tests)
```

---

## Requirement Coverage Matrix

| Task | Requirements Covered |
|------|---------------------|
| 1 | REQ-P2-006, REQ-P2-011C, REQ-P2-015, REQ-P2-036, REQ-P2-041 |
| 2 | REQ-P2-020, REQ-P2-023, REQ-P2-029, REQ-P2-032, REQ-P2-033, REQ-P2-039 |
| 3 | REQ-P2-019, REQ-P2-020, REQ-P2-021, REQ-P2-022, REQ-P2-023, REQ-P2-039 |
| 4 | REQ-P2-012, REQ-P2-019, REQ-P2-022, REQ-P2-023, REQ-P2-029 |
| 5 | REQ-P2-001, REQ-P2-007, REQ-P2-008, REQ-P2-038 |
| 6 | REQ-P2-001, REQ-P2-002, REQ-P2-003, REQ-P2-006 |
| 7 | REQ-P2-009, REQ-P2-010, REQ-P2-011, REQ-P2-011C |
| 8 | REQ-P2-011, REQ-P2-012, REQ-P2-021 |
| 9 | REQ-P2-005, REQ-P2-011B, REQ-P2-013 |
| 10 | REQ-P2-012, REQ-P2-013, REQ-P2-014, REQ-P2-023, REQ-P2-029, REQ-P2-031, REQ-P2-032, REQ-P2-038 |
| 11 | REQ-P2-004, REQ-P2-011A |
| 12 | REQ-P2-015, REQ-P2-016, REQ-P2-017, REQ-P2-018, REQ-P2-026 |
| 13 | REQ-P2-024, REQ-P2-025, REQ-P2-026, REQ-P2-027, REQ-P2-028, REQ-P2-029, REQ-P2-030 |
| 14 | REQ-P2-034, REQ-P2-035 |
| 15 | REQ-P2-036, REQ-P2-037 |
| 16 | REQ-P2-040, REQ-P2-042 |

All 42 requirements (REQ-P2-001 through REQ-P2-042) are covered by at least one task.
