# Task 2: Repository Layer

## Description
Implement `MarketRegimeRepository` and `RegimePerformanceRepository` following the existing repository pattern (async, `aiosqlite.Connection` in constructor), and update `SignalRepository._row_to_record()` to handle the three new regime columns on `signals`.

## Prerequisites
Task 1 (Data Models and Database Foundation)

## Requirement Coverage
REQ-MRD-029, REQ-MRD-030, REQ-MRD-031

## Files to Create
- `signalpilot/db/regime_repo.py`
- `signalpilot/db/regime_performance_repo.py`

## Files to Modify
- `signalpilot/db/signal_repo.py`

## Subtasks

### 2.1 Implement `backend/signalpilot/db/regime_repo.py`

- [ ] Create `MarketRegimeRepository` class accepting `aiosqlite.Connection` in constructor
- [ ] Implement `async def insert_classification(classification: RegimeClassification) -> int` that inserts a row into `market_regimes` with all inputs, scores, and derived values (strategy_weights serialized as JSON via `json.dumps()`), returns the inserted row ID
- [ ] Implement `async def get_today_classifications() -> list[dict]` returning all classifications for the current IST date ordered by `classification_time ASC`
- [ ] Implement `async def get_regime_history(days: int = 20) -> list[dict]` returning the latest classification per day for the last N days using a subquery (`MAX(classification_time)` per `regime_date`), ordered by `regime_date DESC`
- [ ] Write tests in `backend/tests/test_db/test_regime_repo.py` covering: insert and returned ID, get_today returns correct records in time order, get_regime_history returns one per day (latest), empty table returns empty list, multiple classifications per day returns only latest in history
- Requirement coverage: REQ-MRD-030

### 2.2 Implement `backend/signalpilot/db/regime_performance_repo.py`

- [ ] Create `RegimePerformanceRepository` class accepting `aiosqlite.Connection` in constructor
- [ ] Implement `async def insert_daily_performance(regime_date, regime, strategy, signals_generated, signals_taken, wins, losses, pnl) -> int` with automatic `win_rate` calculation (`wins / signals_taken * 100` if `signals_taken > 0` else `None`)
- [ ] Implement `async def get_performance_by_regime(regime: str, days: int = 30) -> list[dict]` returning aggregated performance (SUM of signals, wins, losses, pnl, computed win_rate) by strategy for the specified regime
- [ ] Implement `async def get_performance_summary(days: int = 30) -> list[dict]` returning grouped summary by regime and strategy
- [ ] Write tests in `backend/tests/test_db/test_regime_perf_repo.py` covering: insert with win rate calculation, insert with zero signals_taken (win_rate is None), get_performance_by_regime aggregation, get_performance_summary grouped results, empty table returns empty list
- Requirement coverage: REQ-MRD-031

### 2.3 Update `SignalRepository._row_to_record()` for new regime columns

- [ ] Handle backward compatibility for the three new nullable columns (`market_regime`, `regime_confidence`, `regime_weight_modifier`) using the existing Phase 3 optional-column pattern (index-based access with fallback to None)
- [ ] Ensure `insert_signal()` persists the new fields when present on `SignalRecord`
- [ ] Write tests verifying: old rows without regime columns are read correctly, new rows with regime metadata round-trip correctly
- Requirement coverage: REQ-MRD-029
