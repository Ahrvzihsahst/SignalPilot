# Task 4: Repository Updates

## Description
Update existing repositories (`SignalRepository`, `TradeRepository`, `ConfigRepository`, `MetricsCalculator`) to support Phase 2 columns, new queries (duplicate check, per-strategy filtering), and new status values.

## Prerequisites
Task 0003 (Database Schema Migration)

## Requirement Coverage
REQ-P2-012, REQ-P2-019, REQ-P2-022, REQ-P2-023, REQ-P2-029

## Files to Modify
- `signalpilot/db/signal_repo.py`
- `signalpilot/db/trade_repo.py`
- `signalpilot/db/config_repo.py`
- `signalpilot/db/metrics.py`

## Subtasks

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
