# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SignalPilot is an intraday signal generation tool for Indian equity markets (NSE). It scans Nifty 500 stocks during market hours (9:15 AM - 3:30 PM IST), identifies Gap & Go, ORB (Opening Range Breakout), and VWAP Reversal setups, and delivers signals via Telegram with entry, stop loss, targets, and quantity.

## Repository Layout

```
SignalPilot/
├── backend/              ← Python backend (run all commands from here)
│   ├── signalpilot/      ← Python package
│   ├── tests/            ← Python tests
│   ├── pyproject.toml    ← Python project config
│   ├── data/             ← CSV data files
│   ├── .env.example      ← Example env config
│   └── uv.lock           ← Python lock file
├── frontend/             ← React/TypeScript/Vite dashboard (was dashboard/)
│   ├── src/              ← React source
│   ├── package.json      ← Node config
│   └── vite.config.ts    ← Vite config
├── CLAUDE.md
├── README.md
├── docs/
└── .kiro/
```

All backend commands should be run from the `backend/` directory.

## Commands

```bash
# Install (uses pip + setuptools)
cd backend && pip install -e ".[dev]"

# Run all tests (730 tests, ~14s)
cd backend && pytest tests/

# Run a single test file
cd backend && pytest tests/test_db/test_signal_repo.py

# Run a single test by name
cd backend && pytest tests/test_db/test_signal_repo.py::test_insert_and_retrieve_signal -v

# Run tests with coverage
cd backend && pytest --cov=signalpilot tests/

# Lint
cd backend && ruff check signalpilot/ tests/

# Type check
cd backend && mypy signalpilot/

# Run the application
cd backend && python -m signalpilot.main
```

## Architecture

### Data Flow (Composable Pipeline — 11 signal stages + 1 always stage)

The scan loop delegates all work to a `ScanPipeline` (`backend/signalpilot/pipeline/`). Each stage implements the `PipelineStage` protocol and transforms a shared `ScanContext`.

**Signal stages** (run when `accepting_signals=True` and phase in OPENING/ENTRY_WINDOW/CONTINUOUS):

```
 1. CircuitBreakerGateStage  — halt if SL limit exceeded
 2. StrategyEvalStage        — run Gap & Go / ORB / VWAP Reversal (phase-gated)
 3. GapStockMarkingStage     — exclude gap stocks from ORB/VWAP
 4. DeduplicationStage       — cross-strategy same-day dedup
 5. ConfidenceStage          — multi-strategy confirmation (Phase 3)
 6. CompositeScoringStage    — 4-factor hybrid scoring (Phase 3)
 7. AdaptiveFilterStage      — block paused strategies (Phase 3)
 8. RankingStage             — top-N selection, 1-5 stars
 9. RiskSizingStage          — position sizing, capital allocation
10. PersistAndDeliverStage   — DB insert + Telegram with inline buttons (Phase 4)
11. DiagnosticStage          — heartbeat logging
```

**Always stage** (runs every cycle): `ExitMonitoringStage` — SL/target/trailing-SL/time exits

### Orchestration

`SignalPilotApp` (`backend/signalpilot/scheduler/lifecycle.py`) is the central orchestrator. All 35+ components are **dependency-injected** via `create_app()` in `main.py` (22-stage wiring order). The scan loop runs `ScanPipeline.run(ctx)` every second. The exit monitor receives active trades explicitly via `TradeRepository.get_active_trades()` rather than maintaining internal state.

### Event Bus

`EventBus` (`backend/signalpilot/events.py`) provides decoupled cross-component communication. Components emit typed events; subscribers handle them without direct references. Four event types:
- `ExitAlertEvent` → `bot.send_exit_alert()` (exit monitor → Telegram)
- `StopLossHitEvent` → `circuit_breaker.on_sl_hit()` (exit monitor → circuit breaker)
- `TradeExitedEvent` → `adaptive_manager.on_trade_exit()` (exit monitor → adaptive manager)
- `AlertMessageEvent` → `bot.send_alert()` (circuit breaker/adaptive → Telegram)

### Phase 4: Quick Actions

Inline Telegram keyboards (`backend/signalpilot/telegram/keyboards.py`) replace text-based TAKEN flow:
- **Signal buttons**: `[ TAKEN ] [ SKIP ] [ WATCH ]` on every delivered signal
- **Skip reasons**: `[ No Capital ] [ Low Confidence ] [ Sector ] [ Other ]`
- **Exit buttons**: `[ Book 50% at T1 ]`, `[ Exit at T2 ]`, `[ Exit Now ] [ Hold ]`, `[ Take Profit ] [ Let Run ]`
- **9 callback handlers** in `telegram/handlers.py`: `handle_taken_callback`, `handle_skip_callback`, `handle_skip_reason_callback`, `handle_watch_callback`, `handle_partial_exit_callback`, `handle_exit_now_callback`, `handle_take_profit_callback`, `handle_hold_callback`, `handle_let_run_callback`
- **Analytics**: `SignalActionRepository` tracks action type, skip reason, response_time_ms per signal
- **Watchlist**: `WatchlistRepository` manages 5-day expiry watchlist entries added via WATCH button

`MarketScheduler` (`backend/signalpilot/scheduler/scheduler.py`) wraps APScheduler 3.x with 9 IST cron jobs: pre-market alert (9:00), start scanning (9:15), lock opening ranges (9:45), stop signals (14:30), exit reminder (15:00), mandatory exit (15:15), daily summary (15:30), shutdown (15:35), and weekly rebalance (Sundays 18:00). All weekday jobs use `day_of_week='mon-fri'` and a `_trading_day_guard` decorator that skips execution on NSE holidays.

### Market Phases

Defined in `backend/signalpilot/utils/market_calendar.py` as `StrategyPhase` enum:
- `OPENING` (9:15-9:30) — Gap & Go gap detection, volume accumulation; opening range building for ORB
- `ENTRY_WINDOW` (9:30-9:45) — Gap & Go entry validation and signal generation; opening range continues building
- `CONTINUOUS` (9:45-14:30) — ORB breakout signals (until 11:00 via `ORB_WINDOW_END`), VWAP Reversal signals (from 10:00 via `VWAP_SCAN_START`), exit monitoring for active trades
- `WIND_DOWN` (14:30-15:30) — no new signals, mandatory close reminders, exit monitoring only

Key time constants in `backend/signalpilot/utils/constants.py`:
- `OPENING_RANGE_LOCK = 9:45` — 30-min opening range finalized, ORB detection begins
- `VWAP_SCAN_START = 10:00` — VWAP Reversal strategy activates
- `ORB_WINDOW_END = 11:00` — ORB stops generating new signals
- `NEW_SIGNAL_CUTOFF = 14:30` — all signal generation stops

### Database Layer

SQLite via `aiosqlite` with WAL mode. **10 tables**: `signals`, `trades`, `user_config`, `strategy_performance`, `vwap_cooldown` (Phase 2), `hybrid_scores`, `circuit_breaker_log`, `adaptation_log` (Phase 3), `signal_actions`, `watchlist` (Phase 4). Repository pattern — all accept an `aiosqlite.Connection`:
- Core: `SignalRepository`, `TradeRepository`, `ConfigRepository`, `MetricsCalculator`
- Phase 2: `StrategyPerformanceRepository`
- Phase 3: `HybridScoreRepository`, `CircuitBreakerRepository`, `AdaptationLogRepository`
- Phase 4: `SignalActionRepository`, `WatchlistRepository`

Signal status lifecycle: `"sent"` or `"paper"` → `"taken"` (via TAKEN button/command) or `"expired"` (after 30 min). Phase 2 strategies (ORB, VWAP Reversal) default to paper mode controlled by `orb_paper_mode` / `vwap_paper_mode` flags in user config.

### Data Models

All inter-component contracts are Python `dataclasses` in `backend/signalpilot/db/models.py`. Key chain: `CandidateSignal` → `RankedSignal` → `FinalSignal` → `SignalRecord` (persisted) → `TradeRecord` (via TAKEN). Pipeline state bag: `ScanContext` (`backend/signalpilot/pipeline/context.py`). Phase 4 adds: `SignalActionRecord`, `WatchlistRecord`, `CallbackResult`.

### Logging

Structured logging with async context injection via `contextvars`. `SignalPilotFormatter` (`backend/signalpilot/utils/logger.py`) injects `cycle_id`, `phase`, `symbol`, `job_name`, and `command` fields into every log record. Context is set/reset via `set_context()`/`reset_context()` helpers or the `log_context()` async context manager in `backend/signalpilot/utils/log_context.py`. Logs rotate daily (7-day retention) via `TimedRotatingFileHandler`.

### Rate Limiting

`TokenBucketRateLimiter` (`backend/signalpilot/utils/rate_limiter.py`) enforces per-second and optional per-minute caps for external API calls (primarily Angel One historical data API). Used in `backend/signalpilot/data/historical.py`.

### Configuration

`AppConfig` (`backend/signalpilot/config.py`) uses `pydantic-settings` to load from `.env` and environment variables. All strategy parameters (gap thresholds, volume thresholds, targets, scoring weights, trailing SL, retry counts) are configurable.

## Test Structure

- **Root `backend/tests/conftest.py`** — shared fixtures: `db` (in-memory SQLite), `repos`, `app_config`, `sample_candidate`/`sample_ranked`/`sample_final_signal`, `sample_trades` (12 trades with verified P&L totals), `sample_instruments`, `sample_historical_refs`, `load_test_data()`
- **`backend/tests/test_integration/conftest.py`** — integration-specific fixtures (overrides root `db`/`repos` via pytest locality), plus `make_signal_record()`, `make_final_signal()`, `make_trade_record()`, `make_app()` helpers
- **`backend/tests/test_data/*.json`** — mock tick sequences, historical OHLCV, instrument master data
- **`asyncio_mode = "auto"`** in pyproject.toml — async tests just need `async def`

## Conventions

- **Timezone**: Always use `datetime.now(IST)` (from `signalpilot/utils/constants.py`), never naive `datetime.now()` or `date.today()`. All repo layers (`signal_repo`, `trade_repo`, `config_repo`, `metrics`) use IST-aware datetimes.
- **Async-first**: Database operations, API calls, bot interactions are all async
- **Retry decorator**: `@with_retry()` from `signalpilot/utils/retry.py` for external API calls
- **Rate limiting**: Use `TokenBucketRateLimiter` from `signalpilot/utils/rate_limiter.py` for external API throttling
- **Structured logging**: Use `set_context()`/`reset_context()` from `signalpilot/utils/log_context.py` to annotate log records with async-safe context
- **IST constant**: `IST = ZoneInfo("Asia/Kolkata")` in `signalpilot/utils/constants.py`
- **ExitMonitor wiring**: `ExitMonitor` receives `close_trade` callback, per-strategy `trailing_configs` dict, and `EventBus` for emitting `ExitAlertEvent`/`StopLossHitEvent`/`TradeExitedEvent` (see `main.py:create_app`)
- **WebSocket reconnection**: Uses a `_reconnecting` guard flag to prevent `_on_error` and `_on_close` from both triggering reconnection for the same disconnect event
- **Crash recovery**: `recover()` keeps `_accepting_signals=True` during OPENING, ENTRY_WINDOW, and CONTINUOUS phases; only disables during WIND_DOWN/POST_MARKET

## Branch Strategy

All feature branches (`feat/0001` through `feat/0012`) have been merged into `main`. New work uses descriptive branches (e.g., `fix/rate-limit-historical-api`) merged back into `main` when complete.

## Spec System

Specs are organized by phase under `.kiro/specs/signalpilot/`:

- **Phase 1 (Gap & Go — complete):** `.kiro/specs/signalpilot/phase1/`
  - `requirements.md` — Phase 1 requirements
  - `design.md` — Phase 1 technical design
  - `tasks.md` — Phase 1 implementation tasks summary
  - `tasks/0001-*` through `tasks/0012-*` — individual task specs with checkboxes and requirement coverage

- **Phase 2 (ORB + VWAP Reversal — complete):** `.kiro/specs/signalpilot/phase2/`
  - `requirements.md`, `design.md`, `tasks.md`, `tasks/0001-*` through `tasks/0016-*`

- **Phase 4 (Quick Action Buttons — complete):** `.kiro/specs/signalpilot/phase4/quick-action-buttons/`
  - `requirements.md`, `design.md`, `tasks.md`, `tasks/0001-*` through `tasks/0042-*`

## Resolved Bug Fixes (Feb 2026)

11-bug batch fix across exit monitoring, Telegram commands, crash recovery, WebSocket, scheduler, datetime handling, and metrics:

1. **ExitMonitor now closes trades in DB** — `_persist_exit()` calls `trade_repo.close_trade()` on SL/T2/time exits
2. **JOURNAL command** — fixed method name: `calculate_performance_metrics()` (was `calculate()`)
3. **STATUS command** — `get_current_prices` wrapper converts `list[str]→dict[str,float]` (was passing list to single-str `get_tick`)
4. **Crash recovery** — `recover()` keeps signals enabled during CONTINUOUS phase (ORB/VWAP active)
5. **WebSocket** — `_reconnecting` guard prevents double reconnection from `_on_error` + `_on_close`
6. **Naive datetime** — all `datetime.now()` replaced with `datetime.now(IST)` in `trade_repo`, `signal_repo`, `metrics`
7. **CAPITAL command** — reads `max_positions` from `config_repo` (was hardcoded to 5, config has 8)
8. **Scheduler** — `day_of_week='mon-fri'` + `_trading_day_guard` for NSE holidays
9. **ExitMonitor trailing configs** — per-strategy configs (ORB/VWAP) built from `AppConfig` and passed to constructor
10. **Metrics** — `calculate_daily_summary_by_strategy` excludes open trades (`AND exited_at IS NOT NULL`)
