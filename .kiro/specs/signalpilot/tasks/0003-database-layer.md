# Task 3: Database Layer

## References
- Requirements: `/.kiro/specs/signalpilot/requirements.md` (Req 28-31, 15, 25, 13, 14, 24, 29)
- Design: `/.kiro/specs/signalpilot/design.md` (Sections 4.7, 6)

---

## Subtasks

### 3.1 Implement `signalpilot/db/database.py` with DatabaseManager

- [ ] Implement `DatabaseManager` class as specified in design (Section 4.7.1)
- [ ] `initialize()`: open aiosqlite connection, enable WAL mode and foreign keys, execute schema SQL
- [ ] `close()`: close connection
- [ ] `_create_tables()`: execute the full schema SQL from design (Section 6.1):
  - `signals` table with columns: id, date, symbol, strategy, entry_price, stop_loss, target_1, target_2, quantity, capital_required, signal_strength, gap_pct, volume_ratio, reason, created_at, expires_at, status
  - `trades` table with columns: id, signal_id (FK to signals), date, symbol, entry_price, exit_price, stop_loss, quantity, pnl_amount, pnl_pct, exit_reason, taken_at, exited_at
  - `user_config` table with columns: id, telegram_chat_id, total_capital, max_positions, created_at, updated_at
  - All indexes from Section 6.1
- [ ] Write tests in `tests/test_db/test_database.py`:
  - Verify tables are created with correct columns
  - Verify WAL mode is enabled
  - Verify idempotent table creation (running twice doesn't error)

**Requirement coverage:** Req 28.1 (create SQLite with three tables), Req 28.2 (signals columns), Req 28.3 (trades columns), Req 28.4 (user_config columns)

---

### 3.2 Implement `signalpilot/db/signal_repo.py` with SignalRepository

- [ ] Implement `insert_signal(signal: SignalRecord) -> int` — insert and return the new ID
- [ ] Implement `update_status(signal_id: int, status: str)` — update to "expired"
- [ ] Implement `get_active_signals(date: date) -> list[SignalRecord]` — non-expired, non-taken signals for today (query from Section 6.2)
- [ ] Implement `get_signals_by_date(date: date) -> list[SignalRecord]`
- [ ] Implement `expire_stale_signals()` — bulk update using query from Section 6.2
- [ ] Implement `get_latest_active_signal() -> SignalRecord | None` — for TAKEN command
- [ ] Write tests in `tests/test_db/test_signal_repo.py`:
  - Insert and retrieve a signal
  - Status update from "sent" to "expired"
  - Expiry logic (stale signals get bulk updated)
  - Date filtering returns only today's signals

**Requirement coverage:** Req 29.1 (insert signal), Req 29.2 (expire signals), Req 15 (signal expiry)

---

### 3.3 Implement `signalpilot/db/trade_repo.py` with TradeRepository

- [ ] Implement `insert_trade(trade: TradeRecord) -> int`
- [ ] Implement `close_trade(trade_id: int, exit_price: float, pnl_amount: float, pnl_pct: float, exit_reason: str)` — update query from Section 6.2
- [ ] Implement `get_active_trades() -> list[TradeRecord]` — where exited_at IS NULL
- [ ] Implement `get_active_trade_count() -> int` — count query from Section 6.2
- [ ] Implement `get_trades_by_date(date: date) -> list[TradeRecord]`
- [ ] Implement `get_all_closed_trades() -> list[TradeRecord]` — for JOURNAL command
- [ ] Write tests in `tests/test_db/test_trade_repo.py`:
  - Insert and retrieve a trade
  - Close trade updates exit_price, pnl, exit_reason, exited_at
  - Active trade count is correct before and after closing
  - Date filtering works correctly

**Requirement coverage:** Req 29.3 (insert on TAKEN), Req 29.4 (update on exit), Req 14.1-14.2 (active count for position limits)

---

### 3.4 Implement `signalpilot/db/config_repo.py` with ConfigRepository

- [ ] Implement `get_user_config() -> UserConfig` — return current config or create default
- [ ] Implement `update_capital(total_capital: float)` — update capital and updated_at
- [ ] Implement `update_max_positions(max_positions: int)`
- [ ] Implement `initialize_default(telegram_chat_id: str, total_capital: float, max_positions: int)` — upsert default config
- [ ] Write tests in `tests/test_db/test_config_repo.py`:
  - Default creation when no config exists
  - Capital update persists correctly
  - Retrieval returns updated values

**Requirement coverage:** Req 25 (CAPITAL command updates config), Req 13 (position sizing uses config)

---

### 3.5 Implement `signalpilot/db/metrics.py` with MetricsCalculator

- [ ] Implement `calculate_performance_metrics() -> PerformanceMetrics` — aggregate query from Section 6.2:
  - Win rate (wins / total trades)
  - Total P&L
  - Average win amount
  - Average loss amount
  - Risk-reward ratio
  - Best trade (highest pnl_amount)
  - Worst trade (lowest pnl_amount)
- [ ] Implement `calculate_daily_summary(date: date) -> DailySummary` — daily summary query from Section 6.2
- [ ] A "win" is defined as `pnl_amount > 0`, a "loss" is `pnl_amount <= 0` (Req 30.3)
- [ ] Write tests in `tests/test_db/test_metrics.py`:
  - Verify metrics with known trade data (e.g., 7 wins, 5 losses)
  - Verify edge case: no trades returns zero/empty metrics
  - Verify edge case: all wins
  - Verify edge case: all losses

**Requirement coverage:** Req 30 (performance metrics), Req 31 (daily summary), Req 24 (JOURNAL data)
