# Task 7: VWAP Reversal Strategy Implementation

## Description
Implement `VWAPReversalStrategy(BaseStrategy)` with two setups: Uptrend Pullback (Setup 1) and VWAP Reclaim from Below (Setup 2). Includes 15-min candle evaluation, VWAP touch detection, guardrail integration, and "Higher Risk" labeling.

## Prerequisites
Task 0001 (Configuration and Constants), Task 0002 (Data Models), Task 0005 (MarketDataStore Extensions), Task 0008 (VWAP Cooldown Tracker)

## Requirement Coverage
REQ-P2-009, REQ-P2-010, REQ-P2-011, REQ-P2-011C

## Files to Create
- `signalpilot/strategy/vwap_reversal.py`

## Subtasks

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
