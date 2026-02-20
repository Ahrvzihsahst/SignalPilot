# Task 3: Database Schema Migration

## Description
Add Phase 2 columns to existing tables (signals, trades, user_config), create new tables (strategy_performance, vwap_cooldown), and implement `StrategyPerformanceRepository`. All migrations must be idempotent and backward-compatible.

## Prerequisites
Task 0002 (Data Model Updates)

## Requirement Coverage
REQ-P2-019, REQ-P2-020, REQ-P2-021, REQ-P2-022, REQ-P2-023, REQ-P2-039

## Files to Modify
- `signalpilot/db/database.py`

## Files to Create
- `signalpilot/db/strategy_performance_repo.py`

## Subtasks

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
