# Task 1: Project Scaffolding and Configuration

**Status: COMPLETED**
**Branch:** `feat/0001-project-scaffolding`
**Tests:** 57 passed

## References
- Requirements: `/.kiro/specs/signalpilot/requirements.md`
- Design: `/.kiro/specs/signalpilot/design.md` (Sections 3, 7, 8, Appendix A/B)

---

## Subtasks

### 1.1 Create the project directory structure and `pyproject.toml`

- [x] Create all package directories as defined in the design (Section 3)
- [x] Add `__init__.py` files to all Python packages
- [x] Create `pyproject.toml` with all dependencies (removed unused `logzero` per code review)
- [x] Create `data/nifty500_list.csv` with a placeholder header row

### 1.2 Implement `signalpilot/utils/constants.py` with market time constants

- [x] Define IST timezone using `zoneinfo.ZoneInfo("Asia/Kolkata")`
- [x] Define all market time constants (MARKET_OPEN through APP_AUTO_START)
- [x] Strategy-tunable parameters moved to `AppConfig` only (single source of truth per code review)

### 1.3 Implement `signalpilot/utils/logger.py` with logging configuration

- [x] Implement `configure_logging()` with configurable log file path
- [x] Console handler (stdout) + optional rotating file handler (10MB, 5 backups)
- [x] Clears existing handlers on repeated calls (code review fix)
- [x] Validates log level input (code review fix)
- [x] Creates parent directories for log file path (code review fix)
- [x] Tests in `tests/test_utils/test_logger.py` (9 tests)

### 1.4 Implement `signalpilot/utils/market_calendar.py` for trading day checks

- [x] `is_trading_day()` — weekends + NSE holidays, raises ValueError for unsupported years (code review fix)
- [x] `is_market_hours()` — time-of-day check with clear docstring about trading day separation
- [x] `get_current_phase()` — maps datetime to StrategyPhase enum
- [x] NSE holidays indexed by year dict for extensibility (code review fix)
- [x] Tests in `tests/test_utils/test_market_calendar.py` (22 tests)

### 1.5 Implement `signalpilot/config.py` with Pydantic settings

- [x] `AppConfig(BaseSettings)` with all fields from design Section 7.1
- [x] `.env.example` with placeholder values
- [x] `.env` already in `.gitignore`
- [x] Shared `required_env` fixture in `tests/conftest.py` (code review fix)
- [x] Tests in `tests/test_config.py` (4 tests)

### 1.6 Implement `signalpilot/utils/retry.py` with the retry decorator

- [x] `with_retry` async decorator with exponential backoff
- [x] Guards against sync function misuse with TypeError (code review fix)
- [x] Tests in `tests/test_utils/test_retry.py` (10 tests)
