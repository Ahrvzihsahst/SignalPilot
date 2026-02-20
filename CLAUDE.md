# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SignalPilot is an intraday signal generation tool for Indian equity markets (NSE). It scans Nifty 500 stocks during market hours (9:15 AM - 3:30 PM IST), identifies Gap & Go setups, and delivers signals via Telegram with entry, stop loss, targets, and quantity.

## Commands

```bash
# Install (uses pip + setuptools)
pip install -e ".[dev]"

# Run all tests (456 tests, ~1s)
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
    → Strategy Engine (Gap & Go: gap %, volume, price-hold checks)
    → Signal Ranker (multi-factor scoring, top-5 selection, 1-5 stars)
    → Risk Manager (position sizing, max 5 positions, capital allocation)
    → Telegram Bot (signal delivery, user commands)
    → Exit Monitor (SL/target/trailing-SL/time-based exits)
```

### Orchestration

`SignalPilotApp` (`signalpilot/scheduler/lifecycle.py`) is the central orchestrator. All 16 components are **dependency-injected** as keyword-only constructor parameters. This enables duck-typing and easy mocking in tests. The exit monitor receives active trades explicitly via `TradeRepository.get_active_trades()` rather than maintaining internal state.

`MarketScheduler` (`signalpilot/scheduler/scheduler.py`) wraps APScheduler 3.x with 7 IST cron jobs: pre-market alert (9:00), start scanning (9:15), stop signals (14:30), exit reminder (15:00), mandatory exit (15:15), daily summary (15:30), shutdown (15:35).

### Market Phases

Defined in `signalpilot/utils/market_calendar.py` as `StrategyPhase` enum:
- `OPENING` (9:15-9:30) — gap detection, volume accumulation
- `ENTRY_WINDOW` (9:30-9:45) — entry validation, signal generation
- `CONTINUOUS` (9:45-14:30) — exit monitoring only, no new signals
- `WIND_DOWN` (14:30-15:30) — mandatory close reminders

### Database Layer

SQLite via `aiosqlite` with WAL mode. Three tables: `signals`, `trades`, `user_config`. Repository pattern: `SignalRepository`, `TradeRepository`, `ConfigRepository`, `MetricsCalculator` — all accept an `aiosqlite.Connection`.

Signal status lifecycle: `"sent"` → `"taken"` (via TAKEN command) or `"expired"` (after 30 min).

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

- **Timezone**: Always use `datetime.now(IST)` (from `signalpilot/utils/constants.py`), never naive `datetime.now()` or `date.today()`
- **Async-first**: Database operations, API calls, bot interactions are all async
- **Retry decorator**: `@with_retry()` from `signalpilot/utils/retry.py` for external API calls
- **Rate limiting**: Use `TokenBucketRateLimiter` from `signalpilot/utils/rate_limiter.py` for external API throttling
- **Structured logging**: Use `set_context()`/`reset_context()` from `signalpilot/utils/log_context.py` to annotate log records with async-safe context
- **IST constant**: `IST = ZoneInfo("Asia/Kolkata")` in `signalpilot/utils/constants.py`

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
