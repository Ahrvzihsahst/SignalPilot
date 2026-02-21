# Task 3: Database Layer

**Status: COMPLETED**
**Branch:** `feat/0003-database-layer`
**Tests:** 89 new (146 total passing)

## References
- Requirements: `/.kiro/specs/signalpilot/requirements.md` (Req 28-31, 15, 25, 13, 14, 24, 29)
- Design: `/.kiro/specs/signalpilot/design.md` (Sections 4.7, 6)

---

## Subtasks

### 3.1 Implement `signalpilot/db/database.py` with DatabaseManager

- [x] `DatabaseManager` class with `db_path` and `connection` property (raises RuntimeError if not initialized)
- [x] `initialize()`: open aiosqlite connection, enable WAL mode and foreign keys, create tables; closes existing connection on re-init (code review fix)
- [x] `close()`: close connection, set to None first for idempotent error safety (code review fix)
- [x] `_create_tables()`: execute full schema SQL (signals, trades, user_config + all indexes)
- [x] Tests in `tests/test_db/test_database.py` (10 tests):
  - Tables created with correct columns, WAL mode, FK enforcement, idempotent creation, indexes, connection lifecycle

### 3.2 Implement `signalpilot/db/signal_repo.py` with SignalRepository

- [x] `insert_signal()` with `assert lastrowid` (code review fix)
- [x] `update_status()` with status validation against `_VALID_STATUSES` frozenset + rowcount check (code review fix)
- [x] `get_active_signals()` with parameterized `now` arg instead of `datetime('now')` (code review fix — avoids UTC/local time mismatch)
- [x] `get_signals_by_date()`
- [x] `expire_stale_signals()` with parameterized `now` arg
- [x] `get_latest_active_signal()` with parameterized `now` arg
- [x] Tests in `tests/test_db/test_signal_repo.py` (10 tests):
  - Insert/retrieve, status update, invalid status raises, nonexistent ID raises, active filtering, stale expiry, date filtering, latest active, round-trip

### 3.3 Implement `signalpilot/db/trade_repo.py` with TradeRepository

- [x] `insert_trade()` with `assert lastrowid`
- [x] `close_trade()` with exit_reason validation against `ExitType` enum values + rowcount check (code review fix)
- [x] `get_active_trades()`, `get_active_trade_count()`, `get_trades_by_date()`, `get_all_closed_trades()`
- [x] Tests in `tests/test_db/test_trade_repo.py` (10 tests):
  - Insert/retrieve, close trade, nonexistent ID raises, invalid exit_reason raises, FK enforcement, active count, active trades, date filtering, closed trades, round-trip

### 3.4 Implement `signalpilot/db/config_repo.py` with ConfigRepository

- [x] `get_user_config()` — returns None if empty
- [x] `initialize_default()` — create or upsert config
- [x] `update_capital()` / `update_max_positions()` with rowcount check — raises RuntimeError if no config exists (code review fix)
- [x] Tests in `tests/test_db/test_config_repo.py` (10 tests):
  - Empty returns None, create default, custom values, upsert, update capital/positions, retrieval, updated_at changes, update-without-config raises

### 3.5 Implement `signalpilot/db/metrics.py` with MetricsCalculator

- [x] `calculate_performance_metrics()` with optional date range, win/loss defined per Req 30.3
- [x] Best/worst trade symbol queries respect date range filter (code review fix)
- [x] `calculate_daily_summary()` with cumulative P&L
- [x] Tests in `tests/test_db/test_metrics.py` (10 tests):
  - No trades, mixed wins/losses, all wins, all losses, zero P&L as loss, daily summary basic/empty/cumulative, date range filtering, date-range best/worst symbols

### Shared test fixtures
- [x] `tests/test_db/conftest.py` with `db_manager`, `signal_repo`, `trade_repo`, `config_repo`, `metrics` fixtures (code review fix — deduplicated from 4 test files)

**Requirement coverage:** Req 28 (schema), Req 29 (signal/trade CRUD), Req 30 (metrics), Req 31 (daily summary), Req 15 (signal expiry), Req 25 (capital config), Req 13-14 (position sizing/limits), Req 24 (JOURNAL data)
