# Task 6: ORB Strategy Implementation

## Description
Implement `ORBStrategy(BaseStrategy)` in a new module. Covers opening range breakout detection, volume confirmation, gap exclusion, risk check, SL/target calculation, and per-session state management.

## Prerequisites
Task 0001 (Configuration and Constants), Task 0002 (Data Models), Task 0005 (MarketDataStore Extensions)

## Requirement Coverage
REQ-P2-001, REQ-P2-002, REQ-P2-003, REQ-P2-006

## Files to Create
- `signalpilot/strategy/orb.py`

## Subtasks

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
