# Phase 2 Requirements Document -- Opening Range Breakout (ORB) + VWAP Reversal

## Introduction

Phase 2 extends SignalPilot from a morning-only Gap & Go tool into a full-day scanning engine by adding two new intraday strategies: Opening Range Breakout (ORB) and VWAP Reversal. Together with the existing Gap & Go strategy, these cover trading windows from 9:15 AM through 2:30 PM IST.

Phase 2 also introduces multi-strategy orchestration, performance-based capital allocation, new Telegram commands (ALLOCATE, STRATEGY, PAUSE, RESUME), database schema changes (new columns and tables), and mandatory backtesting + paper trading validation before any new strategy goes live.

All requirements reference the Phase 2 PRD (`PRD_Phase2_ORB_VWAP.md`) and are designed to integrate with the existing Phase 1 architecture: `BaseStrategy` subclasses, `MarketDataStore`, `SignalRanker`, `RiskManager`, `ExitMonitor`, `SignalPilotApp` orchestrator, and the SQLite repository layer.

---

## 1. Opening Range Breakout (ORB) Strategy

### REQ-P2-001: Opening Range Calculation

**User Story:** As a trader, I want the system to compute the 30-minute opening range (HIGH and LOW) for each Nifty 500 stock between 9:15-9:45 AM, so that ORB breakout levels are defined for the day.

**Priority:** P0
**Dependencies:** Phase 1 `MarketDataStore`, `WebSocketClient` (tick data streaming)
**Components affected:** New `signalpilot/strategy/orb.py`, `MarketDataStore` (needs opening range storage)

#### Acceptance Criteria

- [ ] WHEN the market opens at 9:15 AM THEN the system SHALL begin recording the highest high and lowest low for each Nifty 500 stock from incoming tick data.
- [ ] WHEN 9:45 AM arrives THEN the system SHALL lock the opening range (range_high, range_low) for each stock and make it immutable for the rest of the session.
- [ ] WHEN the opening range is locked THEN the system SHALL calculate the range size as `((range_high - range_low) / range_low) * 100` for each stock.
- [ ] IF a stock's opening range size is less than 0.5% or greater than 3% of the stock price THEN the system SHALL exclude that stock from ORB scanning.
- [ ] WHEN the opening range is locked THEN the system SHALL persist range_high and range_low in `MarketDataStore` for access by the ORB strategy during the 9:45 AM - 11:00 AM window.

---

### REQ-P2-002: ORB Entry Conditions

**User Story:** As a trader, I want the system to detect breakouts above the opening range high with volume confirmation, so that I can enter high-momentum moves after the opening range is established.

**Priority:** P0
**Dependencies:** REQ-P2-001, REQ-P2-012 (duplicate prevention)
**Components affected:** New `ORBStrategy(BaseStrategy)` in `signalpilot/strategy/orb.py`

#### Acceptance Criteria

- [ ] WHEN the time is between 9:45 AM and 11:00 AM AND a stock's price breaks above its opening range high THEN the system SHALL evaluate the breakout candle for volume confirmation.
- [ ] WHEN a breakout occurs THEN the system SHALL verify that the volume on the breakout candle exceeds 1.5x the average candle volume; IF volume is below 1.5x THEN the system SHALL skip the signal.
- [ ] WHEN a breakout occurs THEN the system SHALL verify that the stock has NOT already gapped 3%+ at open (Gap & Go territory); IF the stock gapped 3%+ THEN the system SHALL exclude it from ORB scanning.
- [ ] WHEN a breakout occurs AND the stock has an active position or an existing signal today THEN the system SHALL skip the signal (duplicate prevention per REQ-P2-012).
- [ ] WHEN all entry conditions are met THEN the system SHALL generate a `CandidateSignal` with `strategy_name="ORB"` and appropriate entry price, stop loss, and targets.
- [ ] IF it is after 11:00 AM THEN the system SHALL NOT generate new ORB signals for the day.

---

### REQ-P2-003: ORB Stop Loss and Target Calculation

**User Story:** As a trader, I want ORB signals to include stop loss below the opening range low and conservative targets, so that I have clear risk-reward levels for each ORB trade.

**Priority:** P0
**Dependencies:** REQ-P2-001, REQ-P2-002
**Components affected:** `ORBStrategy` in `signalpilot/strategy/orb.py`

#### Acceptance Criteria

- [ ] WHEN an ORB BUY signal is generated THEN the system SHALL set the stop loss at the opening range low price.
- [ ] WHEN an ORB BUY signal is generated THEN the system SHALL calculate Target 1 as entry price + 1.5%.
- [ ] WHEN an ORB BUY signal is generated THEN the system SHALL calculate Target 2 as entry price + 2.5% (configurable up to 3%).
- [ ] IF the calculated risk (entry price - opening range low) exceeds 3% of entry price THEN the system SHALL skip the signal as risk-reward is unfavorable.

---

### REQ-P2-004: ORB Trailing Stop Loss

**User Story:** As a trader, I want the ORB trailing stop to tighten sooner than Gap & Go (breakeven after +1.5%, trail after +2%), so that the tighter targets are protected with a tighter trailing mechanism.

**Priority:** P1
**Dependencies:** REQ-P2-002, Phase 1 `ExitMonitor`
**Components affected:** `ExitMonitor` (needs per-strategy trailing SL config), `AppConfig`

#### Acceptance Criteria

- [ ] WHEN an ORB trade's current price moves 1.5% or more above entry THEN the system SHALL update the trailing stop loss to the entry price (breakeven) and notify the user.
- [ ] WHEN an ORB trade's current price moves 2% or more above entry THEN the system SHALL set a trailing stop at 1% below the current price and notify the user.
- [ ] WHEN the trailing stop is active at the 2%+ level THEN the system SHALL continuously update the trailing stop as the price moves higher (trail at current price - 1%), but SHALL NOT lower the trailing stop if price retraces.
- [ ] WHEN the ORB trailing SL is hit THEN the system SHALL generate an exit alert and log the trade as trailing_sl exit.

---

### REQ-P2-005: ORB Signal Strength Scoring

**User Story:** As a trader, I want ORB signals scored by breakout volume, range tightness, and proximity to breakout level, so that higher-quality ORB setups rank higher.

**Priority:** P1
**Dependencies:** REQ-P2-002, Phase 1 `SignalScorer`
**Components affected:** New `ORBScorer` or extended `SignalScorer`, `AppConfig` (new scoring weights)

#### Acceptance Criteria

- [ ] WHEN an ORB signal is generated THEN the system SHALL calculate a composite score using: breakout candle volume vs average (weight: 40%), opening range size -- tighter range scores higher (weight: 30%), distance from breakout level -- closer to range high scores higher (weight: 30%).
- [ ] WHEN the composite score is calculated THEN the system SHALL normalize it to [0.0, 1.0] and map it to a 1-5 star rating using the same thresholds as Phase 1.
- [ ] WHEN ORB signals compete with Gap & Go or VWAP signals THEN the system SHALL rank all signals by composite score regardless of strategy (cross-strategy ranking per REQ-P2-013).

---

### REQ-P2-006: ORB Configuration Parameters

**User Story:** As a developer, I want all ORB strategy thresholds to be configurable via `AppConfig`, so that parameters can be tuned without code changes.

**Priority:** P1
**Dependencies:** Phase 1 `AppConfig`
**Components affected:** `signalpilot/config.py`

#### Acceptance Criteria

- [ ] WHEN Phase 2 is deployed THEN `AppConfig` SHALL include the following new fields: `orb_range_min_pct` (default 0.5), `orb_range_max_pct` (default 3.0), `orb_volume_multiplier` (default 1.5), `orb_signal_window_end` (default "11:00"), `orb_target_1_pct` (default 1.5), `orb_target_2_pct` (default 2.5), `orb_breakeven_trigger_pct` (default 1.5), `orb_trail_trigger_pct` (default 2.0), `orb_trail_distance_pct` (default 1.0), `orb_gap_exclusion_pct` (default 3.0).
- [ ] WHEN any ORB config parameter is changed via `.env` THEN the strategy SHALL use the updated value on the next application restart.
- [ ] WHEN scoring weights for ORB are needed THEN `AppConfig` SHALL include `orb_scoring_volume_weight` (default 0.40), `orb_scoring_range_weight` (default 0.30), `orb_scoring_distance_weight` (default 0.30).

---

## 2. VWAP Reversal Strategy

### REQ-P2-007: VWAP Calculation

**User Story:** As a trader, I want the system to compute a running VWAP for each Nifty 500 stock from tick data, so that VWAP-based reversal setups can be detected throughout the day.

**Priority:** P0
**Dependencies:** Phase 1 `MarketDataStore`, `WebSocketClient`
**Components affected:** `MarketDataStore` (needs VWAP storage and 15-min candle aggregation), new `signalpilot/strategy/vwap_reversal.py`

#### Acceptance Criteria

- [ ] WHEN tick data is received for a stock THEN the system SHALL maintain a running VWAP calculated as `cumulative(price * volume) / cumulative(volume)` using each tick's LTP and volume.
- [ ] WHEN VWAP is calculated THEN the system SHALL store the current VWAP value in `MarketDataStore` for each symbol, accessible via an async getter.
- [ ] WHEN the market opens at 9:15 AM THEN the system SHALL reset VWAP accumulators for all symbols for the new trading day.

---

### REQ-P2-008: 15-Minute Candle Aggregation

**User Story:** As a trader, I want the system to build 15-minute OHLCV candles from tick data, so that the VWAP Reversal strategy can evaluate candle-level patterns.

**Priority:** P0
**Dependencies:** Phase 1 `MarketDataStore`
**Components affected:** `MarketDataStore` (new candle aggregation logic)

#### Acceptance Criteria

- [ ] WHEN tick data is received THEN the system SHALL aggregate ticks into 15-minute candle buckets starting from 9:15 AM (9:15-9:30, 9:30-9:45, ..., 15:15-15:30).
- [ ] WHEN a 15-minute candle period ends THEN the system SHALL finalize the candle's OHLCV values and make them available as a completed candle.
- [ ] WHEN a candle is being built (in-progress) THEN the system SHALL provide the current partial candle data for real-time evaluation.
- [ ] WHEN the system calculates the average 15-minute candle volume THEN it SHALL use all completed candles from the current session (excluding the in-progress candle).

---

### REQ-P2-009: VWAP Reversal Setup 1 -- Uptrend Pullback

**User Story:** As a trader, I want the system to detect stocks in an uptrend that pull back to VWAP and bounce, so that I can enter at fair value during a trending day.

**Priority:** P0
**Dependencies:** REQ-P2-007, REQ-P2-008, REQ-P2-012
**Components affected:** New `VWAPReversalStrategy(BaseStrategy)` in `signalpilot/strategy/vwap_reversal.py`

#### Acceptance Criteria

- [ ] WHEN the time is between 10:00 AM and 2:30 PM THEN the system SHALL scan for VWAP Uptrend Pullback setups on each completed 15-minute candle.
- [ ] WHEN a stock was previously trading above VWAP (at least one completed 15-min candle closing above VWAP) AND the stock's price touches or dips below VWAP (within 0.3% of VWAP) AND the current 15-minute candle closes back above VWAP AND the bounce candle's volume exceeds the average 15-min candle volume THEN the system SHALL generate a `CandidateSignal` with `strategy_name="VWAP Reversal"` and `setup_type="uptrend_pullback"`.
- [ ] WHEN a Setup 1 signal is generated THEN the system SHALL set the stop loss at VWAP minus 0.5%.
- [ ] WHEN a Setup 1 signal is generated THEN the system SHALL set Target 1 at entry + 1% and Target 2 at entry + 1.5% (configurable up to 2%).

---

### REQ-P2-010: VWAP Reversal Setup 2 -- VWAP Reclaim from Below

**User Story:** As a trader, I want the system to detect stocks that cross above VWAP with strong volume after being below it, so that I can capture potential trend reversals (flagged as higher risk).

**Priority:** P0
**Dependencies:** REQ-P2-007, REQ-P2-008, REQ-P2-012
**Components affected:** `VWAPReversalStrategy` in `signalpilot/strategy/vwap_reversal.py`

#### Acceptance Criteria

- [ ] WHEN the time is between 10:00 AM and 2:30 PM THEN the system SHALL scan for VWAP Reclaim setups on each completed 15-minute candle.
- [ ] WHEN a stock was trading below VWAP AND the stock's 15-minute candle closes above VWAP AND the reclaim candle's volume exceeds 1.5x the average 15-min candle volume THEN the system SHALL generate a `CandidateSignal` with `strategy_name="VWAP Reversal"` and `setup_type="vwap_reclaim"`.
- [ ] WHEN a Setup 2 signal is generated THEN the signal reason text SHALL include a "Higher Risk" label to warn the user.
- [ ] WHEN a Setup 2 signal is generated THEN the system SHALL set the stop loss below the recent swing low (lowest low of the last 3 completed 15-min candles).
- [ ] WHEN a Setup 2 signal is generated THEN the system SHALL set Target 1 at entry + 1.5% and Target 2 at entry + 2% (configurable up to 2.5%).

---

### REQ-P2-011: VWAP Signal Guardrails

**User Story:** As a trader, I want VWAP signals capped at 2 per stock per day with a 60-minute cooldown, so that I avoid signal fatigue and diminishing-quality setups.

**Priority:** P0
**Dependencies:** REQ-P2-009, REQ-P2-010
**Components affected:** `VWAPReversalStrategy`, new `vwap_cooldown` table / in-memory tracker

#### Acceptance Criteria

- [ ] WHEN the system generates a VWAP signal for a stock THEN it SHALL check the daily signal count for that stock; IF the count is already 2 THEN the system SHALL suppress the signal.
- [ ] WHEN a VWAP signal is generated for a stock THEN the system SHALL record a cooldown timestamp; IF a new VWAP signal attempt occurs within 60 minutes of the previous signal for the same stock THEN the system SHALL suppress the signal.
- [ ] WHEN checking VWAP guardrails THEN the system SHALL also verify that no active position exists for the stock (duplicate prevention per REQ-P2-012).
- [ ] IF the time is after 2:30 PM THEN the system SHALL NOT generate any new VWAP signals.
- [ ] WHEN the cooldown and per-stock count are tracked THEN the system SHALL use the `vwap_cooldown` table (or in-memory state reset daily) to persist this state within a session.

---

### REQ-P2-011A: VWAP Trailing Stop Loss

**User Story:** As a trader, I want VWAP trades to have setup-specific trailing stop loss rules, so that the tighter targets of VWAP trades are protected appropriately.

**Priority:** P1
**Dependencies:** REQ-P2-009, REQ-P2-010, Phase 1 `ExitMonitor`
**Components affected:** `ExitMonitor` (per-strategy trailing SL config)

#### Acceptance Criteria

- [ ] WHEN a VWAP Uptrend Pullback (Setup 1) trade's price moves 1% or more above entry THEN the system SHALL update the trailing stop to the entry price (breakeven).
- [ ] WHEN a VWAP Reclaim (Setup 2) trade's price moves 1.5% or more above entry THEN the system SHALL update the trailing stop to the entry price (breakeven).
- [ ] WHEN the trailing SL is hit on a VWAP trade THEN the system SHALL generate an exit alert and log the trade as trailing_sl exit.

---

### REQ-P2-011B: VWAP Signal Strength Scoring

**User Story:** As a trader, I want VWAP signals scored by bounce volume, VWAP touch precision, and day trend alignment, so that cleaner setups rank higher.

**Priority:** P1
**Dependencies:** REQ-P2-009, REQ-P2-010
**Components affected:** New `VWAPScorer` or extended `SignalScorer`

#### Acceptance Criteria

- [ ] WHEN a VWAP signal is generated THEN the system SHALL calculate a composite score using: bounce/reclaim candle volume vs average (weight: 35%), precision of VWAP touch -- closer to VWAP scores higher (weight: 35%), overall day trend alignment -- price above VWAP for more candles scores higher (weight: 30%).
- [ ] WHEN the composite score is calculated THEN the system SHALL normalize it to [0.0, 1.0] and map it to a 1-5 star rating.

---

### REQ-P2-011C: VWAP Configuration Parameters

**User Story:** As a developer, I want all VWAP strategy thresholds configurable via `AppConfig`, so that parameters can be tuned without code changes.

**Priority:** P1
**Dependencies:** Phase 1 `AppConfig`
**Components affected:** `signalpilot/config.py`

#### Acceptance Criteria

- [ ] WHEN Phase 2 is deployed THEN `AppConfig` SHALL include: `vwap_scan_start` (default "10:00"), `vwap_scan_end` (default "14:30"), `vwap_touch_threshold_pct` (default 0.3), `vwap_reclaim_volume_multiplier` (default 1.5), `vwap_pullback_volume_multiplier` (default 1.0), `vwap_max_signals_per_stock` (default 2), `vwap_cooldown_minutes` (default 60), `vwap_setup1_sl_below_vwap_pct` (default 0.5), `vwap_setup1_target1_pct` (default 1.0), `vwap_setup1_target2_pct` (default 1.5), `vwap_setup2_target1_pct` (default 1.5), `vwap_setup2_target2_pct` (default 2.0), `vwap_setup1_breakeven_trigger_pct` (default 1.0), `vwap_setup2_breakeven_trigger_pct` (default 1.5).
- [ ] WHEN scoring weights for VWAP are needed THEN `AppConfig` SHALL include `vwap_scoring_volume_weight` (default 0.35), `vwap_scoring_touch_weight` (default 0.35), `vwap_scoring_trend_weight` (default 0.30).

---

## 3. Multi-Strategy Integration

### REQ-P2-012: Duplicate Prevention

**User Story:** As a trader, I want the system to prevent duplicate signals for the same stock on the same day across all strategies, so that I never receive conflicting recommendations for the same stock.

**Priority:** P0
**Dependencies:** REQ-P2-002, REQ-P2-009, REQ-P2-010
**Components affected:** `SignalPilotApp._scan_loop()`, `SignalRepository` (new query), new duplicate checker

#### Acceptance Criteria

- [ ] WHEN a strategy generates a signal for a stock THEN the system SHALL check the signals table: IF a signal already exists for that stock on the same date (any strategy, any status) THEN the system SHALL suppress the new signal.
- [ ] WHEN a stock has an active TAKEN trade THEN no strategy SHALL generate a new signal for that stock until the trade is closed.
- [ ] WHEN a stock already triggered a Gap & Go signal (gapped 3%+) THEN ORB SHALL NOT generate a signal for that stock on the same day.
- [ ] WHEN checking duplicates THEN the check SHALL execute before scoring/ranking, so that duplicate candidates are removed from the ranking pool.

---

### REQ-P2-013: Cross-Strategy Signal Ranking

**User Story:** As a trader, I want signals from all strategies ranked together by signal strength, so that when multiple strategies fire simultaneously I get the best setups regardless of strategy origin.

**Priority:** P0
**Dependencies:** REQ-P2-005, REQ-P2-011B, Phase 1 `SignalRanker`
**Components affected:** `SignalRanker.rank()`, `SignalPilotApp._scan_loop()`

#### Acceptance Criteria

- [ ] WHEN signals from multiple strategies arrive in the same scan cycle THEN the system SHALL combine all `CandidateSignal` objects into a single list before ranking.
- [ ] WHEN the combined list is ranked THEN the system SHALL sort by composite score descending, regardless of which strategy produced the signal.
- [ ] WHEN position slots are limited THEN the system SHALL allocate slots to the highest-ranked signals across all strategies.
- [ ] WHEN all position slots are full THEN the system SHALL tag any remaining signals as "position_full" in the database and optionally display them as reference-only in Telegram.

---

### REQ-P2-014: Multi-Strategy Scanning Loop

**User Story:** As a developer, I want the scanning loop to orchestrate multiple strategies based on their active phases, so that each strategy runs only during its designated time window.

**Priority:** P0
**Dependencies:** Phase 1 `SignalPilotApp._scan_loop()`, `BaseStrategy`
**Components affected:** `SignalPilotApp` (now accepts a list of strategies instead of a single strategy)

#### Acceptance Criteria

- [ ] WHEN `SignalPilotApp` is constructed THEN it SHALL accept a list of `BaseStrategy` instances (via the `strategies` keyword parameter, replacing the single `strategy` parameter).
- [ ] WHEN the scan loop evaluates strategies THEN it SHALL iterate over all registered strategies, calling `evaluate()` only on those whose `active_phases` include the current `StrategyPhase`.
- [ ] WHEN strategies produce candidates in the same cycle THEN all candidates SHALL be merged, deduplicated (REQ-P2-012), and ranked together (REQ-P2-013).
- [ ] WHEN the ORB strategy is evaluated THEN its active phases SHALL include `StrategyPhase.CONTINUOUS` (9:45 AM - 2:30 PM), but it SHALL self-limit to its 9:45-11:00 AM window internally.
- [ ] WHEN the VWAP strategy is evaluated THEN its active phases SHALL include `StrategyPhase.CONTINUOUS` (9:45 AM - 2:30 PM), but it SHALL self-limit to its 10:00 AM - 2:30 PM window internally.

---

### REQ-P2-015: Updated Max Positions

**User Story:** As a trader, I want the maximum simultaneous positions increased from 5 to 8, so that capital is deployed across more setups from three strategies.

**Priority:** P0
**Dependencies:** Phase 1 `UserConfig`, `RiskManager`, `PositionSizer`
**Components affected:** `AppConfig` (new default), `UserConfig`, `RiskManager`, `PositionSizer`, Telegram signal format

#### Acceptance Criteria

- [ ] WHEN Phase 2 is deployed THEN the default `max_positions` in `AppConfig` SHALL change from 5 to 8.
- [ ] WHEN position sizing is calculated THEN per-trade capital SHALL be `total_capital / 8` (or the configured `max_positions`).
- [ ] WHEN the user has 8 active trades (TAKEN) THEN the system SHALL NOT send new signals until an existing position is closed.
- [ ] WHEN a signal is sent via Telegram THEN the "Positions open" field SHALL display "X/8" (reflecting the new max).

---

## 4. Capital Allocation

### REQ-P2-016: Performance-Based Capital Allocation

**User Story:** As a trader, I want capital distributed across strategies based on each strategy's historical win rate and expectancy, so that better-performing strategies get more capital.

**Priority:** P1
**Dependencies:** REQ-P2-020 (strategy_performance table), REQ-P2-015
**Components affected:** New `signalpilot/risk/capital_allocator.py`, `RiskManager`

#### Acceptance Criteria

- [ ] WHEN the system calculates capital allocation THEN it SHALL compute each strategy's weight as: `(WinRate * AvgWin) - ((1 - WinRate) * AvgLoss)` divided by the sum of all strategy weights.
- [ ] WHEN capital weights are calculated THEN the system SHALL allocate max positions per strategy as: `max_total_positions * strategy_weight` (rounded, minimum 1).
- [ ] WHEN capital allocation is calculated THEN the system SHALL always reserve 20% of total capital (1 position slot) as a buffer for exceptional signals (5-star strength).
- [ ] IF a strategy has no historical data (first week of live trading) THEN the system SHALL use equal allocation across all active strategies as the default.

---

### REQ-P2-017: Weekly Rebalancing

**User Story:** As a trader, I want capital allocation recalculated every Sunday based on trailing 30-day performance, so that allocation adapts to changing strategy effectiveness.

**Priority:** P1
**Dependencies:** REQ-P2-016, REQ-P2-020
**Components affected:** `capital_allocator.py`, `MarketScheduler` (new weekly job)

#### Acceptance Criteria

- [ ] WHEN Sunday arrives (or the first trading day after Sunday) THEN the system SHALL recalculate strategy weights from the trailing 30-day closed trade performance data.
- [ ] WHEN weights are recalculated THEN the system SHALL update the `strategy_performance` table with the new `capital_weight_pct` for each strategy.
- [ ] WHEN rebalancing completes THEN the system SHALL send a Telegram summary showing the new allocation percentages and position counts per strategy.
- [ ] WHEN a strategy's allocation changes by more than 10% from the previous week THEN the system SHALL log a warning for review.

---

### REQ-P2-018: Auto-Pause Underperforming Strategy

**User Story:** As a trader, I want a strategy automatically paused if its win rate drops below 40% over 30 days, so that capital is protected from consistently losing strategies.

**Priority:** P1
**Dependencies:** REQ-P2-016, REQ-P2-020, REQ-P2-024 (PAUSE command)
**Components affected:** `capital_allocator.py`, `user_config` table, Telegram bot

#### Acceptance Criteria

- [ ] WHEN weekly rebalancing runs THEN the system SHALL check each strategy's 30-day win rate.
- [ ] IF a strategy's trailing 30-day win rate is below 40% AND the sample size is at least 10 trades THEN the system SHALL automatically pause that strategy.
- [ ] WHEN a strategy is auto-paused THEN the system SHALL send a Telegram notification: "Strategy [NAME] auto-paused: win rate [X%] below 40% threshold over 30 days."
- [ ] WHEN a strategy is paused THEN the system SHALL set the corresponding enabled flag to 0 in `user_config` and stop generating signals from that strategy.
- [ ] WHEN a strategy is auto-paused THEN the user SHALL be able to resume it via the RESUME command (REQ-P2-025).

---

## 5. Database Schema Updates

### REQ-P2-019: Signals Table Schema Update

**User Story:** As a developer, I want the signals table to include strategy and setup_type columns with new status values, so that Phase 2 signals are properly categorized.

**Priority:** P0
**Dependencies:** Phase 1 `database.py`, `SignalRepository`
**Components affected:** `signalpilot/db/database.py` (schema migration), `SignalRecord`, `SignalRepository`

#### Acceptance Criteria

- [ ] WHEN the Phase 2 schema is applied THEN the signals table SHALL include a `setup_type` column (TEXT, nullable -- only populated for VWAP signals: "uptrend_pullback" or "vwap_reclaim").
- [ ] WHEN the Phase 2 schema is applied THEN the signals table SHALL include a `strategy_specific_score` column (REAL, nullable) for strategy-level scoring distinct from the cross-strategy composite score.
- [ ] WHEN the schema is applied THEN the `status` column's valid values SHALL expand to include "paper" (for paper trading signals) and "position_full" (for signals suppressed due to position limits).
- [ ] WHEN the Phase 2 database initializes THEN it SHALL run an idempotent migration that adds new columns to the existing signals table without data loss (using `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` or equivalent check).

---

### REQ-P2-020: Strategy Performance Table

**User Story:** As a developer, I want a `strategy_performance` table to track per-strategy metrics over time, so that performance-based allocation has a data source.

**Priority:** P0
**Dependencies:** Phase 1 `database.py`
**Components affected:** `signalpilot/db/database.py`, new `signalpilot/db/strategy_performance_repo.py`

#### Acceptance Criteria

- [ ] WHEN Phase 2 schema is applied THEN the system SHALL create a `strategy_performance` table with columns: `id` (INTEGER PRIMARY KEY), `strategy` (TEXT NOT NULL), `date` (TEXT NOT NULL), `signals_generated` (INTEGER), `signals_taken` (INTEGER), `wins` (INTEGER), `losses` (INTEGER), `total_pnl` (REAL), `win_rate` (REAL), `avg_win` (REAL), `avg_loss` (REAL), `expectancy` (REAL), `capital_weight_pct` (REAL).
- [ ] WHEN the daily summary runs at 3:30 PM THEN the system SHALL insert or update a row in `strategy_performance` for each active strategy with that day's metrics.
- [ ] WHEN the weekly rebalancing runs THEN the system SHALL query the trailing 30-day data from this table to compute allocation weights.
- [ ] WHEN querying performance THEN the repository SHALL support filtering by strategy name and date range.

---

### REQ-P2-021: VWAP Cooldown Table

**User Story:** As a developer, I want a `vwap_cooldown` table (or equivalent in-memory state) to track per-stock VWAP signal counts and cooldowns, so that VWAP guardrails (REQ-P2-011) are enforced reliably.

**Priority:** P1
**Dependencies:** REQ-P2-011
**Components affected:** `signalpilot/db/database.py`, `VWAPReversalStrategy`

#### Acceptance Criteria

- [ ] WHEN Phase 2 schema is applied THEN the system SHALL create a `vwap_cooldown` table with columns: `id` (INTEGER PRIMARY KEY), `symbol` (TEXT NOT NULL), `last_signal_at` (TEXT NOT NULL), `signal_count_today` (INTEGER NOT NULL DEFAULT 0).
- [ ] WHEN a VWAP signal is generated for a stock THEN the system SHALL upsert a row in `vwap_cooldown` incrementing `signal_count_today` and updating `last_signal_at`.
- [ ] WHEN the trading day starts THEN the system SHALL reset all `signal_count_today` values to 0 (or truncate the table).
- [ ] WHEN checking VWAP guardrails THEN the system SHALL query `vwap_cooldown` for the stock to check count (<2) and time elapsed (>60 min since `last_signal_at`).

---

### REQ-P2-022: Trades Table Schema Update

**User Story:** As a developer, I want the trades table to include a strategy column, so that per-strategy performance can be calculated from trade data.

**Priority:** P0
**Dependencies:** Phase 1 `database.py`, `TradeRepository`
**Components affected:** `signalpilot/db/database.py`, `TradeRecord`, `TradeRepository`

#### Acceptance Criteria

- [ ] WHEN Phase 2 schema is applied THEN the trades table SHALL include a `strategy` column (TEXT NOT NULL DEFAULT 'gap_go').
- [ ] WHEN a trade is inserted via `TradeRepository.insert_trade()` THEN the `strategy` column SHALL be populated from the corresponding signal's strategy name.
- [ ] WHEN querying trades for performance metrics THEN the `MetricsCalculator` SHALL support filtering by strategy name.

---

### REQ-P2-023: User Config Schema Update

**User Story:** As a developer, I want the user_config table to include per-strategy enabled flags, so that users can selectively enable/disable strategies.

**Priority:** P1
**Dependencies:** Phase 1 `database.py`, `ConfigRepository`
**Components affected:** `signalpilot/db/database.py`, `UserConfig`, `ConfigRepository`

#### Acceptance Criteria

- [ ] WHEN Phase 2 schema is applied THEN the user_config table SHALL include: `gap_go_enabled` (INTEGER NOT NULL DEFAULT 1), `orb_enabled` (INTEGER NOT NULL DEFAULT 1), `vwap_enabled` (INTEGER NOT NULL DEFAULT 1).
- [ ] WHEN `ConfigRepository.get_user_config()` returns a `UserConfig` THEN it SHALL include the three strategy enabled flags.
- [ ] WHEN the scan loop evaluates strategies THEN it SHALL skip any strategy whose enabled flag is 0 in `user_config`.

---

## 6. Telegram Bot Updates

### REQ-P2-024: PAUSE Command

**User Story:** As a trader, I want to temporarily pause a specific strategy via Telegram, so that I can stop receiving signals from a strategy without disabling the entire system.

**Priority:** P1
**Dependencies:** REQ-P2-023, Phase 1 Telegram handlers
**Components affected:** `signalpilot/telegram/handlers.py`, `ConfigRepository`

#### Acceptance Criteria

- [ ] WHEN the user sends "PAUSE GAP" or "PAUSE ORB" or "PAUSE VWAP" THEN the system SHALL set the corresponding strategy's enabled flag to 0 in `user_config`.
- [ ] WHEN a strategy is paused THEN the system SHALL respond with: "[Strategy Name] paused. No signals will be generated from this strategy."
- [ ] IF the user sends "PAUSE" without a strategy name THEN the system SHALL respond with usage instructions: "Usage: PAUSE GAP / PAUSE ORB / PAUSE VWAP".
- [ ] IF the specified strategy is already paused THEN the system SHALL respond: "[Strategy Name] is already paused."

---

### REQ-P2-025: RESUME Command

**User Story:** As a trader, I want to resume a paused strategy via Telegram, so that I can restart signal generation for a previously paused strategy.

**Priority:** P1
**Dependencies:** REQ-P2-023, REQ-P2-024
**Components affected:** `signalpilot/telegram/handlers.py`, `ConfigRepository`

#### Acceptance Criteria

- [ ] WHEN the user sends "RESUME GAP" or "RESUME ORB" or "RESUME VWAP" THEN the system SHALL set the corresponding strategy's enabled flag to 1 in `user_config`.
- [ ] WHEN a strategy is resumed THEN the system SHALL respond with: "[Strategy Name] resumed. Signals will be generated when conditions are met."
- [ ] IF the user sends "RESUME" without a strategy name THEN the system SHALL respond with usage instructions.
- [ ] IF the specified strategy is already active THEN the system SHALL respond: "[Strategy Name] is already active."

---

### REQ-P2-026: ALLOCATE Command

**User Story:** As a trader, I want to view and manually override capital allocation percentages per strategy, so that I can adjust allocation if I disagree with the automatic weights.

**Priority:** P2
**Dependencies:** REQ-P2-016, REQ-P2-020
**Components affected:** `signalpilot/telegram/handlers.py`, `capital_allocator.py`

#### Acceptance Criteria

- [ ] WHEN the user sends "ALLOCATE" THEN the system SHALL respond with the current capital allocation: per-strategy weight percentage, allocated capital amount, max positions per strategy, and the reserve buffer.
- [ ] WHEN the user sends "ALLOCATE GAP 40 ORB 20 VWAP 20" (with percentages summing to <= 80, since 20% is reserved) THEN the system SHALL update the allocation weights accordingly.
- [ ] IF the provided percentages exceed 80% (accounting for the 20% reserve) THEN the system SHALL reject the update and inform the user.
- [ ] WHEN allocation is manually overridden THEN the system SHALL skip automatic rebalancing until the user issues another ALLOCATE command or sends "ALLOCATE AUTO" to re-enable automatic rebalancing.

---

### REQ-P2-027: STRATEGY Command

**User Story:** As a trader, I want to view per-strategy performance over the last 30 days, so that I can evaluate which strategies are working best.

**Priority:** P1
**Dependencies:** REQ-P2-020, Phase 1 `MetricsCalculator`
**Components affected:** `signalpilot/telegram/handlers.py`, `signalpilot/telegram/formatters.py`, `MetricsCalculator`

#### Acceptance Criteria

- [ ] WHEN the user sends "STRATEGY" THEN the system SHALL respond with a performance breakdown for each strategy over the trailing 30 days: strategy name, win rate, total trades, average win, average loss, net P&L, and current capital allocation percentage.
- [ ] WHEN the response is formatted THEN it SHALL follow the template defined in the Phase 2 PRD (Section 5.5).
- [ ] WHEN the response is generated THEN it SHALL include the next rebalancing date (next Sunday).
- [ ] IF a strategy has no trades in the last 30 days THEN it SHALL show "No trades" with its current allocation.

---

### REQ-P2-028: Updated Signal Format

**User Story:** As a trader, I want the Telegram signal message to show the strategy name, setup type, and updated position count (X/8), so that I can distinguish signals from different strategies.

**Priority:** P0
**Dependencies:** REQ-P2-015, Phase 1 `formatters.py`
**Components affected:** `signalpilot/telegram/formatters.py`, `FinalSignal` / `CandidateSignal` model

#### Acceptance Criteria

- [ ] WHEN a signal is formatted for Telegram THEN the "Strategy" field SHALL display the strategy name with setup type (e.g., "VWAP Reversal (Uptrend Pullback)" or "VWAP Reversal -- Higher Risk").
- [ ] WHEN a signal is formatted THEN "Positions open: X/8" SHALL replace "X/5" (reflecting the new max of 8).
- [ ] WHEN a signal is from a VWAP Reclaim (Setup 2) THEN the message SHALL include a "Higher Risk" warning label.
- [ ] WHEN a signal is tagged as "position_full" THEN the Telegram message SHALL display: "Position full -- signal for reference only" instead of the TAKEN prompt.

---

### REQ-P2-029: Updated Daily Summary

**User Story:** As a trader, I want the daily summary at 3:30 PM to include a per-strategy breakdown, so that I can see how each strategy performed that day.

**Priority:** P1
**Dependencies:** REQ-P2-022, Phase 1 `MetricsCalculator`, `formatters.py`
**Components affected:** `signalpilot/telegram/formatters.py`, `MetricsCalculator`, `DailySummary` model

#### Acceptance Criteria

- [ ] WHEN the daily summary is generated THEN it SHALL include a "BY STRATEGY" section listing each active strategy with: signal count, trades taken, and P&L for the day.
- [ ] WHEN the daily summary is formatted THEN it SHALL follow the template in Phase 2 PRD (Section 5.4) with per-strategy rows followed by totals.
- [ ] WHEN the daily summary includes totals THEN it SHALL show: signals sent, trades taken, skipped, wins, losses, net P&L, and updated capital amount.
- [ ] WHEN the `DailySummary` model is updated THEN it SHALL include a `strategy_breakdown: dict[str, StrategyDaySummary]` field (or equivalent) mapping strategy name to that strategy's daily stats.

---

### REQ-P2-030: Updated HELP Command

**User Story:** As a trader, I want the HELP command to list all Phase 2 commands alongside the existing ones, so that I know the full set of available commands.

**Priority:** P2
**Dependencies:** REQ-P2-024, REQ-P2-025, REQ-P2-026, REQ-P2-027
**Components affected:** `signalpilot/telegram/handlers.py`

#### Acceptance Criteria

- [ ] WHEN the user sends "HELP" THEN the response SHALL include all Phase 1 commands (TAKEN, STATUS, JOURNAL, CAPITAL, HELP) plus Phase 2 commands (ALLOCATE, STRATEGY, PAUSE, RESUME) with brief descriptions.

---

## 7. Market Phase Updates

### REQ-P2-031: Extended Strategy Phase Support

**User Story:** As a developer, I want the `StrategyPhase.CONTINUOUS` phase to properly support ORB and VWAP strategies scanning beyond the Gap & Go entry window, so that Phase 2 strategies operate in their designated time windows.

**Priority:** P0
**Dependencies:** Phase 1 `market_calendar.py`, `SignalPilotApp._scan_loop()`
**Components affected:** `SignalPilotApp._scan_loop()`, `market_calendar.py`

#### Acceptance Criteria

- [ ] WHEN the current phase is `StrategyPhase.CONTINUOUS` (9:45 AM - 2:30 PM) THEN the scan loop SHALL evaluate ORB and VWAP strategies (in addition to monitoring exits for existing trades).
- [ ] WHEN evaluating strategies during CONTINUOUS phase THEN `self._accepting_signals` SHALL remain True until 2:30 PM (it is currently set to True but the scan loop only evaluated strategies during OPENING and ENTRY_WINDOW in Phase 1).
- [ ] WHEN the scan loop processes the CONTINUOUS phase THEN it SHALL call `evaluate()` on each strategy whose `active_phases` include `StrategyPhase.CONTINUOUS`.

---

## 8. Data Model Updates

### REQ-P2-032: CandidateSignal Model Extension

**User Story:** As a developer, I want the `CandidateSignal` dataclass to support strategy-specific fields (setup_type, strategy-specific metrics), so that ORB and VWAP signals carry the right metadata.

**Priority:** P0
**Dependencies:** Phase 1 `signalpilot/db/models.py`
**Components affected:** `CandidateSignal`, `SignalRecord`, `SignalScorer`

#### Acceptance Criteria

- [ ] WHEN a `CandidateSignal` is created THEN it SHALL support an optional `setup_type` field (str | None, default None) for VWAP setup classification.
- [ ] WHEN a `CandidateSignal` is created THEN it SHALL support an optional `strategy_specific_score` field (float | None, default None) for strategy-level scoring.
- [ ] WHEN the `gap_pct` field is not applicable (ORB and VWAP signals) THEN it SHALL default to 0.0.
- [ ] WHEN `CandidateSignal` is converted to `SignalRecord` THEN the `setup_type` and `strategy_specific_score` fields SHALL be persisted in the signals table.

---

### REQ-P2-033: TradeRecord Model Extension

**User Story:** As a developer, I want the `TradeRecord` dataclass to include a strategy field, so that trade performance can be attributed to the originating strategy.

**Priority:** P0
**Dependencies:** Phase 1 `signalpilot/db/models.py`, REQ-P2-022
**Components affected:** `TradeRecord`, `TradeRepository`

#### Acceptance Criteria

- [ ] WHEN a `TradeRecord` is created THEN it SHALL include a `strategy` field (str, default "gap_go").
- [ ] WHEN a trade is logged via the TAKEN command THEN the `strategy` field SHALL be populated from the corresponding signal's strategy name.
- [ ] WHEN existing Phase 1 trades are queried THEN they SHALL return with `strategy="gap_go"` (from the default column value).

---

## 9. Backtesting

### REQ-P2-034: Backtest Framework

**User Story:** As a developer, I want a backtesting framework that replays historical data through the ORB and VWAP strategies, so that strategy performance can be validated before live deployment.

**Priority:** P0
**Dependencies:** REQ-P2-002, REQ-P2-009, REQ-P2-010
**Components affected:** New `signalpilot/backtest/` module

#### Acceptance Criteria

- [ ] WHEN a backtest is initiated THEN the system SHALL load at least 1 year of historical OHLCV data for Nifty 500 stocks from Angel One or yfinance.
- [ ] WHEN the backtest runs THEN it SHALL simulate the strategy logic (opening range calculation for ORB, VWAP calculation and candle evaluation for VWAP) on each historical trading day.
- [ ] WHEN the backtest generates simulated signals THEN it SHALL apply the same position sizing, stop loss, target, and trailing stop loss rules as the live system.
- [ ] WHEN the backtest completes THEN it SHALL produce a report containing: total signals, win rate, total P&L, average win, average loss, expectancy, max consecutive losses, and max drawdown.

---

### REQ-P2-035: Backtest Validation Criteria

**User Story:** As a trader, I want each Phase 2 strategy to pass minimum performance thresholds in backtesting before going live, so that only validated strategies trade with real capital.

**Priority:** P0
**Dependencies:** REQ-P2-034
**Components affected:** Backtest report / validation logic

#### Acceptance Criteria

- [ ] WHEN a backtest completes THEN the system SHALL validate the results against these minimum thresholds: win rate > 55%, positive expectancy (net profitable), max consecutive losses <= 8, max drawdown <= 15% of capital, minimum 100 signal occurrences in the backtest period.
- [ ] IF any threshold is not met THEN the system SHALL report which criteria failed and the actual values.
- [ ] WHEN all thresholds are met THEN the system SHALL output "PASS" with a recommendation to proceed to paper trading.
- [ ] WHEN the ORB backtest runs THEN the expected win rate target is >= 60% on 1-year Nifty 500 data.
- [ ] WHEN the VWAP backtest runs THEN the expected win rate target is >= 65% on 1-year Nifty 500 data.

---

## 10. Paper Trading

### REQ-P2-036: Paper Trading Mode

**User Story:** As a trader, I want a 2-week paper trading phase where new strategies generate signals marked as "PAPER TRADE", so that I can validate strategy performance with live market data before committing real capital.

**Priority:** P0
**Dependencies:** REQ-P2-034, REQ-P2-019 (status = "paper"), Phase 1 Telegram bot
**Components affected:** `SignalPilotApp`, `SignalRepository`, `signalpilot/telegram/formatters.py`, `AppConfig`

#### Acceptance Criteria

- [ ] WHEN a strategy is in paper trading mode THEN all generated signals SHALL be persisted with `status = "paper"` in the signals table.
- [ ] WHEN a paper trade signal is sent via Telegram THEN the message SHALL be prefixed with "PAPER TRADE" and include a note that this is not a live signal.
- [ ] WHEN paper trade signals are generated THEN the system SHALL track what would have happened (SL hit, target hit, etc.) using the same exit monitor logic as live trades.
- [ ] WHEN the 2-week paper trading period ends THEN the system SHALL generate a paper trading report comparing results to backtest expectations.
- [ ] IF paper trading results are within 10% variance of backtest results THEN the system SHALL recommend going live.
- [ ] IF paper trading results deviate by more than 10% from backtest results THEN the system SHALL flag the strategy for re-calibration.
- [ ] WHEN `AppConfig` is loaded THEN it SHALL include `orb_paper_mode` (default True) and `vwap_paper_mode` (default True) flags to control paper trading per strategy.

---

### REQ-P2-037: Paper Trading Report

**User Story:** As a trader, I want a comparison report between paper trading results and backtest expectations after the 2-week paper period, so that I can make an informed decision about going live.

**Priority:** P1
**Dependencies:** REQ-P2-036, REQ-P2-035
**Components affected:** New report generation logic, Telegram formatters

#### Acceptance Criteria

- [ ] WHEN the paper trading period ends THEN the system SHALL generate a report containing: paper trade win rate vs backtest win rate, paper trade P&L vs expected P&L, variance percentage, and a PASS/FAIL recommendation.
- [ ] WHEN the report is generated THEN it SHALL be sent via Telegram.
- [ ] WHEN variance is within 10% THEN the report SHALL state "WITHIN TOLERANCE -- Ready for live deployment."
- [ ] WHEN variance exceeds 10% THEN the report SHALL state "OUTSIDE TOLERANCE -- Review and re-calibrate before going live."

---

## 11. Non-Functional Requirements

### REQ-P2-038: Performance -- 500 Stocks x 3 Strategies

**User Story:** As a developer, I want the system to process 500 stocks across 3 strategies without latency degradation, so that signal delivery remains under 30 seconds.

**Priority:** P0
**Dependencies:** All strategy requirements
**Components affected:** `SignalPilotApp._scan_loop()`, `MarketDataStore`

#### Acceptance Criteria

- [ ] WHEN 3 strategies are active and processing 500 stocks THEN the scan loop iteration SHALL complete in under 5 seconds.
- [ ] WHEN VWAP is calculated for 500 stocks THEN the total VWAP computation SHALL not add more than 500ms per scan cycle.
- [ ] WHEN 15-minute candles are aggregated for 500 stocks THEN the in-memory storage SHALL not exceed 100 MB (estimated: 500 stocks * 25 candles/day * ~200 bytes/candle = ~2.5 MB, well within limits).
- [ ] WHEN signal delivery latency is measured from condition trigger to Telegram delivery THEN it SHALL remain under 30 seconds (same as Phase 1 requirement).

---

### REQ-P2-039: Data Model Backward Compatibility

**User Story:** As a developer, I want all database schema changes to be backward-compatible with existing Phase 1 data, so that no data is lost during the Phase 2 migration.

**Priority:** P0
**Dependencies:** REQ-P2-019, REQ-P2-022, REQ-P2-023
**Components affected:** `signalpilot/db/database.py`

#### Acceptance Criteria

- [ ] WHEN Phase 2 schema migration runs THEN all existing signals, trades, and user_config records SHALL remain intact and accessible.
- [ ] WHEN new columns are added to existing tables THEN they SHALL have default values (e.g., `strategy DEFAULT 'gap_go'`) so existing rows are valid without data backfill.
- [ ] WHEN new tables (`strategy_performance`, `vwap_cooldown`) are created THEN the migration SHALL use `CREATE TABLE IF NOT EXISTS` for idempotency.
- [ ] WHEN the application starts THEN the migration SHALL run automatically and complete before any strategy evaluation begins.

---

### REQ-P2-040: Test Coverage

**User Story:** As a developer, I want all Phase 2 components covered by unit and integration tests, so that regressions are caught before deployment.

**Priority:** P0
**Dependencies:** All Phase 2 requirements
**Components affected:** `tests/` directory

#### Acceptance Criteria

- [ ] WHEN Phase 2 is complete THEN there SHALL be unit tests for: ORB strategy logic (range calculation, breakout detection, entry conditions, SL/target calculation), VWAP strategy logic (VWAP calculation, Setup 1, Setup 2, guardrails, cooldown), multi-strategy ranking (cross-strategy scoring, deduplication), capital allocation (weight calculation, weekly rebalancing, auto-pause), all new Telegram command handlers (PAUSE, RESUME, ALLOCATE, STRATEGY), database migration (new columns, new tables, backward compatibility), and paper trading mode (signal tagging, exit tracking).
- [ ] WHEN all tests run THEN the test suite SHALL pass with 0 failures.
- [ ] WHEN Phase 2 integration tests run THEN they SHALL cover: full scan loop with 3 strategies, duplicate prevention across strategies, position limit enforcement at 8, daily summary with per-strategy breakdown, and strategy pause/resume flow.

---

### REQ-P2-041: Configuration Validation

**User Story:** As a developer, I want all new Phase 2 configuration parameters validated at startup, so that misconfiguration is caught early.

**Priority:** P1
**Dependencies:** REQ-P2-006, REQ-P2-011C
**Components affected:** `signalpilot/config.py`

#### Acceptance Criteria

- [ ] WHEN `AppConfig` is loaded THEN all percentage parameters SHALL be validated as >= 0.
- [ ] WHEN ORB scoring weights are loaded THEN their sum SHALL equal 1.0 (with 0.01 tolerance).
- [ ] WHEN VWAP scoring weights are loaded THEN their sum SHALL equal 1.0 (with 0.01 tolerance).
- [ ] IF any validation fails THEN the application SHALL log an error and refuse to start, providing a clear message about which parameter is invalid.

---

### REQ-P2-042: Logging for Phase 2 Components

**User Story:** As a developer, I want structured logging for all Phase 2 components with strategy context, so that debugging and monitoring are straightforward.

**Priority:** P1
**Dependencies:** Phase 1 logging infrastructure (`log_context.py`, `logger.py`)
**Components affected:** All new Phase 2 modules

#### Acceptance Criteria

- [ ] WHEN a Phase 2 strategy evaluates a stock THEN log records SHALL include `strategy` and `setup_type` context fields via `set_context()`.
- [ ] WHEN an ORB breakout is detected THEN the log SHALL include: symbol, range_high, range_low, breakout price, volume ratio.
- [ ] WHEN a VWAP touch is detected THEN the log SHALL include: symbol, VWAP value, touch price, touch proximity percentage, candle volume ratio.
- [ ] WHEN a signal is suppressed (duplicate, cooldown, position full) THEN the log SHALL include the suppression reason.

---

## Component Impact Summary

### New Components to Create

| Component | Path | Description |
|-----------|------|-------------|
| ORB Strategy | `signalpilot/strategy/orb.py` | `ORBStrategy(BaseStrategy)` -- opening range calculation, breakout detection |
| VWAP Reversal Strategy | `signalpilot/strategy/vwap_reversal.py` | `VWAPReversalStrategy(BaseStrategy)` -- VWAP calc, Setup 1 & 2, guardrails |
| Capital Allocator | `signalpilot/risk/capital_allocator.py` | Performance-based allocation, weekly rebalancing, auto-pause |
| Strategy Performance Repo | `signalpilot/db/strategy_performance_repo.py` | CRUD for `strategy_performance` table |
| Backtest Module | `signalpilot/backtest/` | Backtest runner, data loader, report generator |
| ORB Tests | `tests/test_strategy/test_orb.py` | Unit tests for ORB strategy |
| VWAP Tests | `tests/test_strategy/test_vwap_reversal.py` | Unit tests for VWAP strategy |
| Capital Allocator Tests | `tests/test_risk/test_capital_allocator.py` | Unit tests for allocation logic |
| New Handler Tests | `tests/test_telegram/test_phase2_handlers.py` | Tests for PAUSE, RESUME, ALLOCATE, STRATEGY |

### Existing Components to Modify

| Component | Path | Changes |
|-----------|------|---------|
| AppConfig | `signalpilot/config.py` | Add ORB, VWAP, and allocation config fields |
| CandidateSignal | `signalpilot/db/models.py` | Add `setup_type`, `strategy_specific_score` fields |
| TradeRecord | `signalpilot/db/models.py` | Add `strategy` field |
| SignalRecord | `signalpilot/db/models.py` | Add `setup_type`, `strategy_specific_score` fields |
| UserConfig | `signalpilot/db/models.py` | Add `gap_go_enabled`, `orb_enabled`, `vwap_enabled` fields |
| DailySummary | `signalpilot/db/models.py` | Add `strategy_breakdown` field |
| Database Schema | `signalpilot/db/database.py` | Migration for new columns and tables |
| SignalRepository | `signalpilot/db/signal_repo.py` | New queries for dedup, paper status |
| TradeRepository | `signalpilot/db/trade_repo.py` | Strategy-aware queries |
| MetricsCalculator | `signalpilot/db/metrics.py` | Per-strategy metric calculation |
| MarketDataStore | `signalpilot/data/market_data_store.py` | VWAP storage, 15-min candle aggregation, opening range storage |
| SignalScorer | `signalpilot/ranking/scorer.py` | Strategy-aware scoring (or compose with per-strategy scorers) |
| SignalRanker | `signalpilot/ranking/ranker.py` | Cross-strategy ranking support |
| RiskManager | `signalpilot/risk/risk_manager.py` | Updated max positions, strategy-aware allocation |
| ExitMonitor | `signalpilot/monitor/exit_monitor.py` | Per-strategy trailing SL configuration |
| SignalPilotApp | `signalpilot/scheduler/lifecycle.py` | Multi-strategy scan loop, dedup, CONTINUOUS phase support |
| MarketScheduler | `signalpilot/scheduler/scheduler.py` | Weekly rebalancing job |
| Telegram Handlers | `signalpilot/telegram/handlers.py` | PAUSE, RESUME, ALLOCATE, STRATEGY commands |
| Telegram Formatters | `signalpilot/telegram/formatters.py` | Updated signal format, daily summary, strategy report |
| Constants | `signalpilot/utils/constants.py` | New time constants (ORB window end, VWAP scan start) |
