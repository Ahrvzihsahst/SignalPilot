# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SignalPilot is an intraday signal generation tool for Indian equity markets (NSE). It scans Nifty 500 stocks during market hours (9:15 AM - 3:30 PM IST), identifies Gap & Go, ORB (Opening Range Breakout), and VWAP Reversal setups, and delivers signals via Telegram with entry, stop loss, targets, and quantity.

## Commands

```bash
# Install (uses pip + setuptools)
pip install -e ".[dev]"

# Run all tests (730 tests, ~14s)
pytest tests/

# Run a single test file
pytest tests/test_db/test_signal_repo.py

# Run a single test by name
pytest tests/test_db/test_signal_repo.py::test_insert_and_retrieve_signal -v

# Run tests with coverage
pytest --cov=signalpilot tests/

# Lint
ruff check signalpilot/ tests/

# Type check
mypy signalpilot/

# Run the application
python -m signalpilot.main
```

## Architecture

### Data Flow (Pipeline)

```
Data Engine (Angel One WebSocket + yfinance fallback)
    → Strategy Engine (Gap & Go + ORB + VWAP Reversal, per-phase activation)
    → Duplicate Checker (cross-strategy same-day dedup)
    → Signal Ranker (multi-factor scoring, top-5 selection, 1-5 stars)
    → Risk Manager (position sizing, max 8 positions, capital allocation, price cap)
    → Telegram Bot (signal delivery, user commands, paper/live mode)
    → Exit Monitor (SL/target/trailing-SL/time-based exits, persists closures via trade_repo)
```

### Orchestration

`SignalPilotApp` (`signalpilot/scheduler/lifecycle.py`) is the central orchestrator. All 16 components are **dependency-injected** as keyword-only constructor parameters. This enables duck-typing and easy mocking in tests. The exit monitor receives active trades explicitly via `TradeRepository.get_active_trades()` rather than maintaining internal state. On exit events (SL/T2/time), the exit monitor persists trade closures to the DB via a `close_trade` callback wired to `TradeRepository.close_trade()`.

`MarketScheduler` (`signalpilot/scheduler/scheduler.py`) wraps APScheduler 3.x with 9 IST cron jobs: pre-market alert (9:00), start scanning (9:15), lock opening ranges (9:45), stop signals (14:30), exit reminder (15:00), mandatory exit (15:15), daily summary (15:30), shutdown (15:35), and weekly rebalance (Sundays 18:00). All weekday jobs use `day_of_week='mon-fri'` and a `_trading_day_guard` decorator that skips execution on NSE holidays.

### Market Phases

Defined in `signalpilot/utils/market_calendar.py` as `StrategyPhase` enum:
- `OPENING` (9:15-9:30) — Gap & Go gap detection, volume accumulation; opening range building for ORB
- `ENTRY_WINDOW` (9:30-9:45) — Gap & Go entry validation and signal generation; opening range continues building
- `CONTINUOUS` (9:45-14:30) — ORB breakout signals (until 11:00 via `ORB_WINDOW_END`), VWAP Reversal signals (from 10:00 via `VWAP_SCAN_START`), exit monitoring for active trades
- `WIND_DOWN` (14:30-15:30) — no new signals, mandatory close reminders, exit monitoring only

Key time constants in `signalpilot/utils/constants.py`:
- `OPENING_RANGE_LOCK = 9:45` — 30-min opening range finalized, ORB detection begins
- `VWAP_SCAN_START = 10:00` — VWAP Reversal strategy activates
- `ORB_WINDOW_END = 11:00` — ORB stops generating new signals
- `NEW_SIGNAL_CUTOFF = 14:30` — all signal generation stops

### Database Layer

SQLite via `aiosqlite` with WAL mode. Three tables: `signals`, `trades`, `user_config`. Repository pattern: `SignalRepository`, `TradeRepository`, `ConfigRepository`, `MetricsCalculator` — all accept an `aiosqlite.Connection`.

Signal status lifecycle: `"sent"` or `"paper"` → `"taken"` (via TAKEN command) or `"expired"` (after 30 min). Phase 2 strategies (ORB, VWAP Reversal) default to paper mode controlled by `orb_paper_mode` / `vwap_paper_mode` flags in user config.

### Data Models

All inter-component contracts are Python `dataclasses` in `signalpilot/db/models.py`. Key chain: `CandidateSignal` → `RankedSignal` → `FinalSignal` → `SignalRecord` (persisted).

### Logging

Structured logging with async context injection via `contextvars`. `SignalPilotFormatter` (`signalpilot/utils/logger.py`) injects `cycle_id`, `phase`, `symbol`, `job_name`, and `command` fields into every log record. Context is set/reset via `set_context()`/`reset_context()` helpers or the `log_context()` async context manager in `signalpilot/utils/log_context.py`. Logs rotate daily (7-day retention) via `TimedRotatingFileHandler`.

### Rate Limiting

`TokenBucketRateLimiter` (`signalpilot/utils/rate_limiter.py`) enforces per-second and optional per-minute caps for external API calls (primarily Angel One historical data API). Used in `signalpilot/data/historical.py`.

### Configuration

`AppConfig` (`signalpilot/config.py`) uses `pydantic-settings` to load from `.env` and environment variables. All strategy parameters (gap thresholds, volume thresholds, targets, scoring weights, trailing SL, retry counts) are configurable.

## Test Structure

- **Root `tests/conftest.py`** — shared fixtures: `db` (in-memory SQLite), `repos`, `app_config`, `sample_candidate`/`sample_ranked`/`sample_final_signal`, `sample_trades` (12 trades with verified P&L totals), `sample_instruments`, `sample_historical_refs`, `load_test_data()`
- **`tests/test_integration/conftest.py`** — integration-specific fixtures (overrides root `db`/`repos` via pytest locality), plus `make_signal_record()`, `make_final_signal()`, `make_trade_record()`, `make_app()` helpers
- **`tests/test_data/*.json`** — mock tick sequences, historical OHLCV, instrument master data
- **`asyncio_mode = "auto"`** in pyproject.toml — async tests just need `async def`

## Conventions

- **Timezone**: Always use `datetime.now(IST)` (from `signalpilot/utils/constants.py`), never naive `datetime.now()` or `date.today()`. All repo layers (`signal_repo`, `trade_repo`, `config_repo`, `metrics`) use IST-aware datetimes.
- **Async-first**: Database operations, API calls, bot interactions are all async
- **Retry decorator**: `@with_retry()` from `signalpilot/utils/retry.py` for external API calls
- **Rate limiting**: Use `TokenBucketRateLimiter` from `signalpilot/utils/rate_limiter.py` for external API throttling
- **Structured logging**: Use `set_context()`/`reset_context()` from `signalpilot/utils/log_context.py` to annotate log records with async-safe context
- **IST constant**: `IST = ZoneInfo("Asia/Kolkata")` in `signalpilot/utils/constants.py`
- **ExitMonitor wiring**: `ExitMonitor` receives a `close_trade` callback and per-strategy `trailing_configs` dict built from `AppConfig` ORB/VWAP trailing params (see `main.py:create_app`)
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

- **Phase 2 (ORB + VWAP Reversal — in development):** `.kiro/specs/signalpilot/phase2/`
  - `requirements.md` — Phase 2 requirements (42 requirements, REQ-P2-001 through REQ-P2-042)

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
