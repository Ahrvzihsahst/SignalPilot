# Task 1: Project Scaffolding and Configuration

## References
- Requirements: `/.kiro/specs/signalpilot/requirements.md`
- Design: `/.kiro/specs/signalpilot/design.md` (Sections 3, 7, 8, Appendix A/B)

---

## Subtasks

### 1.1 Create the project directory structure and `pyproject.toml`

- [ ] Create all package directories as defined in the design (Section 3):
  - `signalpilot/`
  - `signalpilot/data/`
  - `signalpilot/strategy/`
  - `signalpilot/ranking/`
  - `signalpilot/risk/`
  - `signalpilot/monitor/`
  - `signalpilot/telegram/`
  - `signalpilot/db/`
  - `signalpilot/scheduler/`
  - `signalpilot/utils/`
  - `data/`
  - `tests/`
- [ ] Add `__init__.py` files to all Python packages
- [ ] Create `pyproject.toml` with all dependencies from the design (Appendix A):
  - Runtime: `smartapi-python`, `pyotp`, `python-telegram-bot`, `apscheduler`, `aiosqlite`, `pandas`, `numpy`, `yfinance`, `pydantic`, `pydantic-settings`, `httpx`, `logzero`
  - Dev: `pytest`, `pytest-asyncio`, `pytest-mock`, `pytest-cov`, `ruff`, `mypy`
- [ ] Create `data/nifty500_list.csv` with a placeholder header row (Symbol, Company Name, Industry, ISIN)

**Requirement coverage:** Foundational for all requirements

---

### 1.2 Implement `signalpilot/utils/constants.py` with market time constants

- [ ] Define IST timezone using `zoneinfo.ZoneInfo("Asia/Kolkata")`
- [ ] Define all market time constants from the design (Appendix B):
  - `MARKET_OPEN` (9:15 AM)
  - `MARKET_CLOSE` (3:30 PM)
  - `PRE_MARKET_ALERT` (9:00 AM)
  - `GAP_SCAN_END` (9:30 AM)
  - `ENTRY_WINDOW_END` (9:45 AM)
  - `NEW_SIGNAL_CUTOFF` (2:30 PM)
  - `EXIT_REMINDER` (3:00 PM)
  - `MANDATORY_EXIT` (3:15 PM)
  - `DAILY_SUMMARY` (3:30 PM)
  - `APP_SHUTDOWN` (3:35 PM)
  - `APP_AUTO_START` (8:50 AM)
- [ ] Define strategy threshold constants: gap min/max percentages, volume threshold, target percentages, max risk percentage, signal expiry minutes

**Requirement coverage:** Req 6 (gap thresholds), Req 7 (volume threshold), Req 8 (entry window times), Req 9 (target percentages), Req 16 (trading time restrictions)

---

### 1.3 Implement `signalpilot/utils/logger.py` with logging configuration

- [ ] Implement `configure_logging()` function as specified in design (Section 8.4)
- [ ] Set up console handler (stdout) and rotating file handler (`signalpilot.log`, 10MB max, 5 backups)
- [ ] Use format: `%(asctime)s | %(levelname)-8s | %(name)s | %(message)s`

**Requirement coverage:** Supports observability across all requirements

---

### 1.4 Implement `signalpilot/utils/market_calendar.py` for trading day checks

- [ ] Implement `is_trading_day(d: date) -> bool` that returns False for weekends
- [ ] Implement `is_market_hours(dt: datetime) -> bool` that checks if time is between 9:15 AM and 3:30 PM IST
- [ ] Implement `get_current_phase(dt: datetime) -> StrategyPhase` to map current time to the correct phase
- [ ] Include a basic NSE holiday list for the current year
- [ ] Write tests in `tests/test_utils/test_market_calendar.py`:
  - Verify weekdays return True
  - Verify weekends return False
  - Verify holidays return False
  - Verify phase mapping is correct at boundary times

**Requirement coverage:** Req 32 (auto-start on weekdays), Req 33 (continuous scanning phases), Req 16 (time restrictions)

---

### 1.5 Implement `signalpilot/config.py` with Pydantic settings

- [ ] Create `AppConfig` class extending `BaseSettings` as specified in design (Section 7.1)
- [ ] Include all fields:
  - Angel One credentials (API key, client ID, password, TOTP secret)
  - Telegram config (bot token, chat ID)
  - DB path
  - Instrument paths (Nifty 500 CSV, instrument master URL)
  - Risk management defaults (total capital, max positions)
  - Strategy parameters (gap min/max, volume threshold)
  - Scoring weights
  - Trailing SL parameters
  - Retry/resilience settings
- [ ] Create `.env.example` with placeholder values from the design (Section 7.2)
- [ ] Add `.env` to `.gitignore`
- [ ] Write tests in `tests/test_config.py`:
  - Verify defaults load correctly
  - Verify required fields raise validation errors when missing

**Requirement coverage:** Req 1 (auth credentials), Req 2 (WebSocket config), Req 13 (capital defaults), Req 14 (max positions)

---

### 1.6 Implement `signalpilot/utils/retry.py` with the retry decorator

- [ ] Implement the `with_retry` async decorator as specified in design (Section 8.2)
- [ ] Support configurable max_retries, base_delay, max_delay, exponential backoff, and exception types
- [ ] Write tests in `tests/test_utils/test_retry.py`:
  - Verify retry count
  - Verify exponential backoff delays
  - Verify success on Nth attempt

**Requirement coverage:** Req 1.2 (auth retry), Req 2.3 (WebSocket reconnect), Req 4 (data fallback)
