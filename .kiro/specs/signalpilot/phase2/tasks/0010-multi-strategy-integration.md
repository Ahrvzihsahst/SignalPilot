# Task 10: Multi-Strategy Integration (Scan Loop and Lifecycle)

## Description
Refactor `SignalPilotApp` from single-strategy to multi-strategy orchestration. Update the scan loop to iterate strategies by phase, integrate deduplication, enable cross-strategy ranking, and support CONTINUOUS phase evaluation.

## Prerequisites
Task 0004 (Repository Updates), Task 0005 (MarketDataStore Extensions), Task 0006 (ORB Strategy), Task 0007 (VWAP Strategy), Task 0008 (Cooldown & Duplicate Checker), Task 0009 (Scoring Updates)

## Requirement Coverage
REQ-P2-012, REQ-P2-013, REQ-P2-014, REQ-P2-023, REQ-P2-029, REQ-P2-031, REQ-P2-032, REQ-P2-038

## Files to Modify
- `signalpilot/scheduler/lifecycle.py`

## Subtasks

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
