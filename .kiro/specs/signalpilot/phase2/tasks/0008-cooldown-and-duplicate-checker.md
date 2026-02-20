# Task 8: VWAP Cooldown Tracker and Duplicate Checker

## Description
Create `VWAPCooldownTracker` (in-memory per-stock signal count and cooldown enforcement) and `DuplicateChecker` (cross-strategy deduplication via DB queries).

## Prerequisites
Task 0002 (Data Models), Task 0003 (Database Schema Migration)

## Requirement Coverage
REQ-P2-011, REQ-P2-012, REQ-P2-021

## Files to Create
- `signalpilot/monitor/vwap_cooldown.py`
- `signalpilot/monitor/duplicate_checker.py`

## Subtasks

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
