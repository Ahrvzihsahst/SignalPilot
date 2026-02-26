# SignalPilot — End-to-End How It Works

> A step-by-step walkthrough of every stage in the signal lifecycle,
> from cold boot to Telegram delivery and trade exit.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Step 1 — Configuration & Startup](#2-step-1--configuration--startup)
3. [Step 2 — Authentication (Angel One SmartAPI)](#3-step-2--authentication-angel-one-smartapi)
4. [Step 3 — Pre-Market Data Fetch](#4-step-3--pre-market-data-fetch)
5. [Step 4 — Market Scheduling](#5-step-4--market-scheduling)
6. [Step 5 — Real-Time Data (WebSocket)](#6-step-5--real-time-data-websocket)
7. [Step 6 — Market Data Store](#7-step-6--market-data-store)
8. [Step 7 — Strategy Evaluation](#8-step-7--strategy-evaluation)
   - [7a. Gap & Go Strategy](#7a-gap--go-strategy)
   - [7b. ORB Strategy](#7b-orb-strategy)
   - [7c. VWAP Reversal Strategy](#7c-vwap-reversal-strategy)
9. [Step 8 — Duplicate Checking](#9-step-8--duplicate-checking)
10. [Step 9 — Signal Ranking & Scoring](#10-step-9--signal-ranking--scoring)
11. [Step 10 — Risk Management & Position Sizing](#11-step-10--risk-management--position-sizing)
12. [Step 11 — Capital Allocation](#12-step-11--capital-allocation)
13. [Step 12 — Database Persistence](#13-step-12--database-persistence)
14. [Step 13 — Telegram Delivery](#14-step-13--telegram-delivery)
15. [Step 14 — Exit Monitoring](#15-step-14--exit-monitoring)
16. [Step 15 — Telegram Commands (User Interaction)](#16-step-15--telegram-commands-user-interaction)
17. [Step 16 — Daily Wind-Down & Summary](#17-step-16--daily-wind-down--summary)
18. [Step 17 — Shutdown & Crash Recovery](#18-step-17--shutdown--crash-recovery)
19. [Data Model Chain](#19-data-model-chain)
20. [Logging & Observability](#20-logging--observability)
21. [Rate Limiting & Retry](#21-rate-limiting--retry)
22. [Complete Scan Loop Iteration](#22-complete-scan-loop-iteration)
23. [Summary: A Complete Trading Day](#23-summary-a-complete-trading-day)

---

## 1. Architecture Overview

SignalPilot is an **async-first, dependency-injected** Python application. All
components are wired together once at boot via `create_app()` and communicate
through typed `dataclass` contracts. No global state; every component receives
its dependencies via constructor parameters.

```
[.env / environment]
        |
        v
   AppConfig (pydantic-settings)
        |
        v
   create_app()          <-- wires 20+ components in dependency order
        |
        |-- DatabaseManager --> SignalRepository
        |                   --> TradeRepository
        |                   --> ConfigRepository
        |                   --> MetricsCalculator
        |                   --> StrategyPerformanceRepository
        |
        |-- SmartAPIAuthenticator --> Angel One SmartAPI (TOTP-based 2FA)
        |
        |-- InstrumentManager  --> nifty500_list.csv
        |
        |-- HistoricalDataFetcher (Angel One + yfinance fallback)
        |       |-- TokenBucketRateLimiter (3 req/s, 170 req/min)
        |
        |-- MarketDataStore  <-- receives ticks from WebSocket
        |       |-- TickData (per symbol)
        |       |-- OpeningRange (per symbol, locked at 9:45)
        |       |-- VWAPState (cumulative price*volume / volume)
        |       |-- Candle15Min (aggregated 15-min candles)
        |       |-- HistoricalReference (prev close, prev high, 20-day ADV)
        |
        |-- WebSocketClient --> Angel One WebSocket feed
        |       |-- _reconnecting guard flag
        |       |-- Exponential backoff: 2s, 4s, 8s
        |
        |-- GapAndGoStrategy  |
        |-- ORBStrategy       |-- strategies evaluate MarketDataStore
        |-- VWAPReversalStrategy |
        |       |-- VWAPCooldownTracker (max 2/stock/day, 60-min cooldown)
        |
        |-- DuplicateChecker (cross-strategy same-day dedup)
        |
        |-- SignalRanker (SignalScorer --> ORBScorer / VWAPScorer)
        |
        |-- RiskManager (PositionSizer)
        |
        |-- CapitalAllocator (StrategyPerformanceRepository)
        |       |-- 20% reserve, expectancy-weighted allocation
        |       |-- Auto-pause: win_rate < 40% after 10+ trades
        |
        |-- ExitMonitor --> reads MarketDataStore, fires Telegram alerts
        |       |-- Per-strategy TrailingStopConfig
        |       |-- close_trade callback --> TradeRepository
        |
        |-- SignalPilotBot (Telegram, python-telegram-bot)
        |       |-- 9 commands: TAKEN, STATUS, JOURNAL, CAPITAL, PAUSE,
        |       |   RESUME, ALLOCATE, STRATEGY, HELP
        |
        +-- MarketScheduler (APScheduler 3.x, 9 IST cron jobs)
                |
                +-- SignalPilotApp._scan_loop()  <-- runs every 1 second
```

The **central orchestrator** is `SignalPilotApp`
(`signalpilot/scheduler/lifecycle.py`). It owns the main scanning loop and
calls each stage in sequence on every 1-second tick.

---

## 2. Step 1 — Configuration & Startup

### File: `signalpilot/config.py`

All configuration is loaded from a `.env` file (or real environment variables)
using **pydantic-settings**. There is no hardcoded configuration.

#### Complete Field Reference

**Required (no defaults):**

| Field | Type | Description |
|-------|------|-------------|
| `angel_api_key` | `str` | Angel One SmartAPI key |
| `angel_client_id` | `str` | Angel One client ID |
| `angel_mpin` | `str` | Angel One MPIN |
| `angel_totp_secret` | `str` | TOTP secret key (base32, 32 chars) |
| `telegram_bot_token` | `str` | Telegram Bot API token |
| `telegram_chat_id` | `str` | Telegram chat ID for delivery |

**Logging:**

| Field | Default | Description |
|-------|---------|-------------|
| `log_level` | `"INFO"` | DEBUG, INFO, WARNING, ERROR |
| `log_file` | `"log/signalpilot.log"` | Log file path |

**Database & Data:**

| Field | Default | Description |
|-------|---------|-------------|
| `db_path` | `"signalpilot.db"` | SQLite database path |
| `nifty500_csv_path` | `"data/nifty500_list.csv"` | Nifty 500 instrument list |

**Risk Management:**

| Field | Default | Description |
|-------|---------|-------------|
| `default_capital` | `50000.0` | Starting trading capital (INR) |
| `default_max_positions` | `8` | Max signals per cycle (used by ranker); DB `user_config.max_positions` defaults to `5` for actual position limits |

**Gap & Go Strategy:**

| Field | Default | Description |
|-------|---------|-------------|
| `gap_min_pct` | `3.0` | Min gap % from prev close |
| `gap_max_pct` | `5.0` | Max gap % from prev close |
| `volume_threshold_pct` | `50.0` | Min 15-min vol as % of 20-day ADV |
| `target_1_pct` | `5.0` | Target 1 from entry |
| `target_2_pct` | `7.0` | Target 2 from entry |
| `max_risk_pct` | `3.0` | Max SL risk % from entry |
| `signal_expiry_minutes` | `30` | Signal validity window |

**Gap & Go Scoring Weights:**

| Field | Default | Description |
|-------|---------|-------------|
| `scoring_gap_weight` | `0.40` | Gap size importance |
| `scoring_volume_weight` | `0.35` | Volume importance |
| `scoring_price_distance_weight` | `0.25` | Distance from open importance |

**Gap & Go Trailing Stop Loss:**

| Field | Default | Description |
|-------|---------|-------------|
| `trailing_sl_breakeven_trigger_pct` | `2.0` | SL moves to entry price |
| `trailing_sl_trail_trigger_pct` | `4.0` | Trailing SL activates |
| `trailing_sl_trail_distance_pct` | `2.0` | SL trails this % below peak |

**ORB Strategy:**

| Field | Default | Description |
|-------|---------|-------------|
| `orb_range_min_pct` | `0.5` | Min opening range size % |
| `orb_range_max_pct` | `3.0` | Max opening range size % |
| `orb_volume_multiplier` | `1.5` | Min volume multiplier for breakout |
| `orb_signal_window_end` | `"11:00"` | Stop generating ORB signals |
| `orb_target_1_pct` | `1.5` | Target 1 from entry |
| `orb_target_2_pct` | `2.5` | Target 2 from entry |
| `orb_breakeven_trigger_pct` | `1.5` | SL moves to entry |
| `orb_trail_trigger_pct` | `2.0` | Trailing SL activates |
| `orb_trail_distance_pct` | `1.0` | Trail distance below peak |
| `orb_gap_exclusion_pct` | `3.0` | Exclude stocks gapping >= this % |

**ORB Scoring Weights:**

| Field | Default | Description |
|-------|---------|-------------|
| `orb_scoring_volume_weight` | `0.40` | Volume importance |
| `orb_scoring_range_weight` | `0.30` | Range size importance |
| `orb_scoring_distance_weight` | `0.30` | Distance from breakout |

**VWAP Reversal Strategy:**

| Field | Default | Description |
|-------|---------|-------------|
| `vwap_scan_start` | `"10:00"` | VWAP scanning start time |
| `vwap_scan_end` | `"14:30"` | VWAP scanning end time |
| `vwap_touch_threshold_pct` | `0.3` | Max distance to VWAP for "touch" |
| `vwap_reclaim_volume_multiplier` | `1.5` | Volume multiplier for reclaim |
| `vwap_pullback_volume_multiplier` | `1.0` | Volume multiplier for pullback |
| `vwap_max_signals_per_stock` | `2` | Max VWAP signals per stock per day |
| `vwap_cooldown_minutes` | `60` | Min gap between signals per stock |
| `vwap_setup1_sl_below_vwap_pct` | `0.5` | Setup 1 SL below VWAP |
| `vwap_setup1_target1_pct` | `1.0` | Setup 1 Target 1 |
| `vwap_setup1_target2_pct` | `1.5` | Setup 1 Target 2 |
| `vwap_setup2_target1_pct` | `1.5` | Setup 2 Target 1 |
| `vwap_setup2_target2_pct` | `2.0` | Setup 2 Target 2 |
| `vwap_setup1_breakeven_trigger_pct` | `1.0` | Setup 1 breakeven trigger |
| `vwap_setup2_breakeven_trigger_pct` | `1.5` | Setup 2 breakeven trigger |

**VWAP Scoring Weights:**

| Field | Default | Description |
|-------|---------|-------------|
| `vwap_scoring_volume_weight` | `0.35` | Volume importance |
| `vwap_scoring_touch_weight` | `0.35` | VWAP touch precision |
| `vwap_scoring_trend_weight` | `0.30` | Trend confirmation importance |

**Paper Trading Mode:**

| Field | Default | Description |
|-------|---------|-------------|
| `orb_paper_mode` | `True` | ORB signals are paper-only by default |
| `vwap_paper_mode` | `True` | VWAP signals are paper-only by default |

**Retry & Resilience:**

| Field | Default | Description |
|-------|---------|-------------|
| `auth_max_retries` | `3` | Auth retry attempts |
| `ws_max_reconnect_attempts` | `3` | WebSocket reconnect attempts |
| `historical_api_rate_limit` | `3` | Requests per second |
| `max_crashes_per_session` | `3` | Max crash recoveries per session |

**Validators:**

A `@model_validator` enforces that each of the three scoring weight groups
(Gap & Go, ORB, VWAP) sums to `1.0 +/- 0.01` tolerance. The app won't start
with invalid weights.

### Entry Point: `signalpilot/main.py`

```python
async def main() -> None:
    config = AppConfig()                     # load .env
    configure_logging(level=config.log_level, log_file=config.log_file)
    app = await create_app(config)           # wire 20+ components

    # Setup SIGINT/SIGTERM handlers (once via shutting_down flag)
    now = datetime.now(IST)
    if is_market_hours(now) and is_trading_day(now.date()):
        await app.recover()                  # crash-recovery path
    else:
        await app.startup()                  # normal startup

    while True:
        await asyncio.sleep(1)               # keep event loop alive
```

#### `create_app()` Wiring Order (13 stages)

1. **Database** — `DatabaseManager(db_path)` + `initialize()` (WAL mode, foreign keys, phase 2 migration)
2. **Repositories** — `SignalRepository`, `TradeRepository`, `ConfigRepository`, `MetricsCalculator`, `StrategyPerformanceRepository` (all sharing the same `aiosqlite.Connection`)
3. **Auth** — `SmartAPIAuthenticator(config)`
4. **Data** — `InstrumentManager(csv_path)`, `MarketDataStore()`, `HistoricalDataFetcher(authenticator, instruments, rate_limit)`
5. **Strategies** — `GapAndGoStrategy(config)`, `ORBStrategy(config, market_data)`, `VWAPCooldownTracker(max_signals=2, cooldown=60)` + `VWAPReversalStrategy(config, market_data, cooldown_tracker)`
6. **Duplicate Checker** — `DuplicateChecker(signal_repo, trade_repo)`
7. **Ranking** — `ScoringWeights(...)` + `ORBScorer(...)` + `VWAPScorer(...)` + `SignalScorer(weights, orb_scorer, vwap_scorer)` + `SignalRanker(scorer, max_signals=8)`
8. **Capital Allocation** — `CapitalAllocator(strategy_performance_repo, config_repo)`
9. **Risk** — `PositionSizer()` + `RiskManager(position_sizer)`
10. **Exit Monitor** — `ExitMonitor(get_tick, alert_callback, trailing_configs, close_trade=trade_repo.close_trade)` with per-strategy `TrailingStopConfig` dict (6 entries for Gap & Go, ORB, VWAP setups)
11. **Telegram Bot** — `SignalPilotBot(...)` with `_get_current_prices` wrapper (converts `list[str]` to `dict[str, float]` via `market_data.get_tick()`)
12. **WebSocket** — `WebSocketClient(authenticator, instruments, market_data_store, on_disconnect_alert, max_reconnect_attempts)`
13. **Scheduler** — `MarketScheduler()`

The bot and exit monitor have a circular dependency (exit alerts are sent via
the bot). This is resolved with a `bot_ref: list[SignalPilotBot | None]`
closure that is filled after the bot is constructed.

There are two startup paths:
- **Normal** (`app.startup()`): pre-market boot, authenticate, fetch historical data, start the scheduler.
- **Crash recovery** (`app.recover()`): re-authenticate, reload active trades from DB, resume monitoring immediately.

---

## 3. Step 2 — Authentication (Angel One SmartAPI)

### File: `signalpilot/data/auth.py`

SignalPilot authenticates with Angel One's SmartAPI using **TOTP-based 2FA**.

```python
@with_retry(max_retries=3, base_delay=2.0, exceptions=(Exception,))
async def authenticate(self) -> bool:
    totp = pyotp.TOTP(self._totp_secret).now()    # fresh 6-digit TOTP
    smart_connect = SmartConnect(api_key=self._api_key, timeout=15)

    data = await asyncio.to_thread(
        smart_connect.generateSession, self._client_id, self._mpin, totp
    )

    # Extract tokens from response
    self._auth_token = data["data"]["jwtToken"]      # JWT for API calls
    self._feed_token = data["data"]["feedToken"]      # WebSocket feed token
    self._refresh_token = data["data"]["refreshToken"]
```

**Tokens obtained:**
- `jwtToken` — used for REST API calls (historical data)
- `feedToken` — used for WebSocket subscription
- `refreshToken` — stored for session refresh

The `@with_retry` decorator retries up to 3 times with exponential backoff
(2s, 4s, 8s delays) before raising `AuthenticationError`.

---

## 4. Step 3 — Pre-Market Data Fetch

### File: `signalpilot/data/historical.py`

Before the market opens, SignalPilot needs two reference datasets for every
Nifty 500 stock:

| Dataset | Used for |
|---------|----------|
| **Previous day close & high** | Gap % calculation, above-prev-high check |
| **20-day Average Daily Volume (ADV)** | Volume ratio calculation |

```python
# Inside SignalPilotApp._load_historical_data()
await self._historical.fetch_previous_day_data()
await asyncio.sleep(5)                           # 5s cooldown between passes
await self._historical.fetch_average_daily_volume()
```

Each fetch processes stocks in **batches of 3** with a 1.2s inter-batch delay
to respect the Angel One API rate limit (3 req/s, 170 req/min).

```python
# signalpilot/data/historical.py
_BATCH_SIZE = 3       # symbols per concurrent batch
_BATCH_DELAY = 1.2    # seconds between batches
_RATE_LIMIT_RETRIES = 3
_RATE_LIMIT_BASE_DELAY = 2.0

async def fetch_previous_day_data(self) -> dict[str, PreviousDayData]:
    for i in range(0, len(symbols), _BATCH_SIZE):
        batch = symbols[i : i + _BATCH_SIZE]
        tasks = [self._fetch_single_previous_day(s) for s in batch]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.sleep(_BATCH_DELAY)
```

**Fallback chain** for every symbol:

```
1. Angel One SmartAPI  (getCandleData, ONE_DAY interval, run_in_thread)
        | fails?
        v
2. yfinance            (ticker.history)
        | fails?
        v
   Symbol excluded from today's universe
```

**Rate-limited call with exponential backoff:**

```python
async def _rate_limited_call(self, func, *args, **kwargs):
    for attempt in range(_RATE_LIMIT_RETRIES + 1):  # 0, 1, 2, 3
        await self._limiter.acquire()                # blocks until token available
        try:
            async with self._semaphore:              # max 3 concurrent
                return await func(*args, **kwargs)
        except Exception as exc:
            # Detect retryable: "exceeding access rate", "403", timeouts
            if is_retryable and attempt < _RATE_LIMIT_RETRIES:
                delay = 2.0 * (2 ** attempt)         # 2s, 4s, 8s
                await asyncio.sleep(delay)
                continue
            raise
```

**`build_historical_references()`** combines both fetches into
`HistoricalReference` objects (previous_close, previous_high, average_daily_volume)
and stores them in `MarketDataStore.set_historical(symbol, ref)`. Symbols
missing either prev-day or ADV data are excluded with a logged warning.

---

## 5. Step 4 — Market Scheduling

### File: `signalpilot/scheduler/scheduler.py`

`MarketScheduler` wraps **APScheduler 3.x** with **9 IST cron jobs** registered
against `SignalPilotApp` methods:

| Time (IST) | Job ID | Action |
|-----------|--------|--------|
| 09:00 Mon-Fri | `pre_market_alert` | Send "Signals coming at 9:15" Telegram alert |
| 09:15 Mon-Fri | `start_scanning` | Open WebSocket, reset session, begin 1-second scan loop |
| 09:45 Mon-Fri | `lock_opening_ranges` | Finalize 30-min opening range for ORB detection |
| 14:30 Mon-Fri | `stop_new_signals` | Set `_accepting_signals = False` |
| 15:00 Mon-Fri | `exit_reminder` | Advisory exit alerts for open positions |
| 15:15 Mon-Fri | `mandatory_exit` | Forced exit for all remaining open trades |
| 15:30 Mon-Fri | `daily_summary` | Calculate metrics and send end-of-day report |
| 15:35 Mon-Fri | `shutdown` | Graceful shutdown |
| Sunday 18:00 | `weekly_rebalance` | Capital rebalancing across strategies |

All weekday jobs use `day_of_week='mon-fri'` and a `_trading_day_guard`
decorator.

#### `_trading_day_guard` Decorator

Every weekday job callback is wrapped with this decorator that:
1. Gets the current date in IST
2. Calls `is_trading_day(today)` from `market_calendar.py`
3. If `False` (weekend or NSE holiday) — logs skip and returns early
4. If `True` — executes the job normally
5. If holiday data is missing for the year — logs warning and runs anyway (failsafe)

#### NSE Holidays

`NSE_HOLIDAYS` in `market_calendar.py` stores holidays as
`dict[int, frozenset[date]]` keyed by year. For 2026, there are **19 trading
holidays** including Republic Day, Holi, Diwali, Independence Day, etc.

#### Market Phases

Determined at runtime by `get_current_phase(dt)`:

```python
class StrategyPhase(Enum):
    PRE_MARKET  = "pre_market"    # before 9:15
    OPENING     = "opening"       # 9:15 - 9:30
    ENTRY_WINDOW= "entry_window"  # 9:30 - 9:45
    CONTINUOUS  = "continuous"    # 9:45 - 14:30
    WIND_DOWN   = "wind_down"     # 14:30 - 15:30
    POST_MARKET = "post_market"   # after 15:30
```

**Time constants** (`signalpilot/utils/constants.py`):

| Constant | Value | Description |
|----------|-------|-------------|
| `MARKET_OPEN` | `time(9, 15)` | Market opens |
| `MARKET_CLOSE` | `time(15, 30)` | Market closes |
| `PRE_MARKET_ALERT` | `time(9, 0)` | Pre-market notification |
| `GAP_SCAN_END` | `time(9, 30)` | End of OPENING phase |
| `ENTRY_WINDOW_END` | `time(9, 45)` | End of ENTRY_WINDOW, locks ORB range |
| `OPENING_RANGE_LOCK` | `time(9, 45)` | 30-min opening range finalized |
| `VWAP_SCAN_START` | `time(10, 0)` | VWAP Reversal activates |
| `ORB_WINDOW_END` | `time(11, 0)` | ORB stops generating new signals |
| `NEW_SIGNAL_CUTOFF` | `time(14, 30)` | All signal generation stops |
| `EXIT_REMINDER` | `time(15, 0)` | Exit advisory |
| `MANDATORY_EXIT` | `time(15, 15)` | Forced exit |
| `DAILY_SUMMARY` | `time(15, 30)` | Daily report |
| `APP_SHUTDOWN` | `time(15, 35)` | Graceful shutdown |
| `APP_AUTO_START` | `time(8, 50)` | Auto-start time |
| `MAX_SIGNALS_PER_BATCH` | `8` | Max signals per cycle |

---

## 6. Step 5 — Real-Time Data (WebSocket)

### File: `signalpilot/data/websocket_client.py`

At 9:15 AM, `app.start_scanning()` opens an Angel One WebSocket connection
and subscribes to live tick feeds for all Nifty 500 tokens.

```python
await self._websocket.connect()
self._scan_task = asyncio.create_task(self._scan_loop())
```

#### Connection Flow

1. Close any previous WebSocket (prevents duplicate threads)
2. Create `SmartWebSocketV2` with auth tokens (API key, client ID, feed token)
3. Register callbacks: `on_data`, `on_close`, `on_error`, `on_open`
4. Launch in background thread: `loop.run_in_executor(None, self._ws.connect)`
5. Wait for `_on_open` event with 30s timeout

#### `_on_open(ws)` — Subscription

1. Set `_connected = True`
2. Subscribe to all tokens: `self._ws.subscribe("abc123", 3, token_list)` (Mode 3 = Snap Quote)
3. Reset reconnect counter and `_reconnecting` guard
4. Signal asyncio side via `call_soon_threadsafe`

#### Data Flow per Tick (`_on_data`)

Each incoming tick triggers this update chain in `MarketDataStore`:

```
1. update_tick(symbol, tick)           -- store latest TickData
2. accumulate_volume(symbol, volume)   -- cumulative volume
3. update_vwap(symbol, price, delta_vol)  -- running VWAP calc
4. update_candle(symbol, price, delta_vol, timestamp)  -- 15-min candle aggregation
5. update_opening_range(symbol, high, low)  -- opening range (only if not locked)
```

Delta volume is computed as: `delta_vol = tick.volume - prev_volume[symbol]`

#### Reconnection Logic

```
_reconnecting guard flag:
  - Prevents BOTH _on_error() AND _on_close() from triggering reconnection
    for the same disconnect event
  - Whichever fires first sets _reconnecting = True
  - The second callback sees the flag and returns immediately

Exponential backoff:
  Attempt 1: 2 * 2^0 = 2 seconds
  Attempt 2: 2 * 2^1 = 4 seconds
  Attempt 3: 2 * 2^2 = 8 seconds
  (max_reconnect_attempts = 3 by default)

After all attempts exhausted:
  - Sends disconnect alert via bot.send_alert()
```

---

## 7. Step 6 — Market Data Store

### File: `signalpilot/data/market_data_store.py`

`MarketDataStore` is the central in-memory data hub. All strategies and the
exit monitor read from it; the WebSocket client writes to it.

#### Data Structures

**TickData** (per symbol, updated on every tick):
```python
@dataclass
class TickData:
    symbol: str
    ltp: float          # Last Traded Price
    open_price: float
    high: float
    low: float
    close: float        # Previous day close (from feed)
    volume: int         # Cumulative volume for the day
    last_traded_timestamp: datetime
    updated_at: datetime
```

**OpeningRange** (per symbol, built 9:15-9:45, locked at 9:45):
```python
@dataclass
class OpeningRange:
    range_high: float
    range_low: float
    locked: bool = False
    range_size_pct: float = 0.0   # calculated on lock
```

**VWAPState** (per symbol, running calculation):
```python
@dataclass
class VWAPState:
    cumulative_price_volume: float = 0.0
    cumulative_volume: float = 0.0
    current_vwap: float = 0.0
```

**Candle15Min** (per symbol, aggregated 15-min candles):
```python
@dataclass
class Candle15Min:
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    start_time: datetime
    end_time: datetime
    is_complete: bool = False
```

#### VWAP Calculation

```python
async def update_vwap(self, symbol: str, price: float, volume: float) -> None:
    state.cumulative_price_volume += price * volume
    state.cumulative_volume += volume
    if state.cumulative_volume > 0:
        state.current_vwap = state.cumulative_price_volume / state.cumulative_volume
```

VWAP = sum(price * volume) / sum(volume), computed incrementally on every tick.

#### Key Accessors

| Method | Returns | Used by |
|--------|---------|---------|
| `get_tick(symbol)` | `TickData \| None` | Strategies, ExitMonitor |
| `get_all_ticks()` | `dict[str, TickData]` | Scan loop |
| `get_opening_range(symbol)` | `OpeningRange \| None` | ORB strategy |
| `lock_opening_ranges()` | void | Called at 9:45, calculates `range_size_pct` |
| `get_vwap(symbol)` | `float \| None` | VWAP strategy |
| `get_completed_candles(symbol)` | `list[Candle15Min]` | VWAP strategy |
| `get_current_candle(symbol)` | `Candle15Min \| None` | ORB strategy |
| `get_avg_candle_volume(symbol)` | `float` | ORB, VWAP strategies |
| `get_historical(symbol)` | `HistoricalReference \| None` | Gap & Go |
| `clear_session()` | void | Reset intraday data, preserve historical refs |

---

## 8. Step 7 — Strategy Evaluation

The scan loop runs every second and calls `strategy.evaluate(market_data, phase)`.
Each strategy implements `BaseStrategy` (abstract class with `name`, `active_phases`,
and `evaluate()`) and declares which phases it is active in.

```python
# Inside SignalPilotApp._scan_loop()
for strat in enabled_strategies:
    if phase in strat.active_phases:
        candidates = await strat.evaluate(self._market_data, phase)
        all_candidates.extend(candidates)
```

All three strategies produce `CandidateSignal` objects.

### 7a. Gap & Go Strategy

**File:** `signalpilot/strategy/gap_and_go.py`

Active phases: `OPENING` (9:15-9:30) and `ENTRY_WINDOW` (9:30-9:45).

#### Internal State (reset daily via `reset()`)

```python
_gap_candidates: dict[str, _GapCandidate] = {}    # candidates identified in OPENING
_volume_validated: set[str] = set()                # passed volume check
_disqualified: set[str] = set()                    # failed price hold
_signals_generated: set[str] = set()               # one signal per stock per day
```

```python
@dataclass
class _GapCandidate:
    symbol: str
    open_price: float
    prev_close: float
    prev_high: float
    gap_pct: float
```

#### Phase 1 — OPENING: Gap Detection (9:15-9:30)

```python
# For each tick received:

# 1. Calculate gap %
gap_pct = ((open_price - prev_close) / prev_close) * 100

# 2. Filter: gap must be within [3%, 5%]
if gap_pct < 3.0 or gap_pct > 5.0:
    continue

# 3. Open must be ABOVE the previous day's high
if open_price <= prev_high:
    continue

# 4. Track as gap candidate
self._gap_candidates[symbol] = _GapCandidate(...)

# 5. Check volume immediately and continuously
volume_ratio = (accumulated_volume / average_daily_volume) * 100
if volume_ratio >= 50.0:                       # 50% of 20-day ADV
    self._volume_validated.add(symbol)
```

#### Phase 2 — ENTRY_WINDOW: Signal Generation (9:30-9:45)

```python
for symbol in self._volume_validated:
    if symbol in self._signals_generated:
        continue                                # one signal per stock per day

    tick = await market_data.get_tick(symbol)

    # Price must hold STRICTLY ABOVE the opening price
    if tick.ltp <= candidate.open_price:
        self._disqualified.add(symbol)          # failed to hold -- skip
        continue

    # All checks passed -- create CandidateSignal
    entry_price = tick.ltp
    sl = opening_price
    max_sl = entry_price * (1 - 3.0 / 100)     # cap risk at 3%
    stop_loss = max(sl, max_sl)                 # whichever is higher (tighter)

    target_1 = entry_price * (1 + 5.0 / 100)   # +5%
    target_2 = entry_price * (1 + 7.0 / 100)   # +7%

    signal = CandidateSignal(
        symbol=symbol,
        direction=SignalDirection.BUY,
        strategy_name="Gap & Go",
        entry_price=entry_price,
        stop_loss=stop_loss,
        target_1=target_1,
        target_2=target_2,
        gap_pct=candidate.gap_pct,
        volume_ratio=volume / adv,
        price_distance_from_open_pct=((entry_price - open_price) / open_price) * 100,
        reason=f"Gap up {gap_pct:.1f}% above prev close ...",
        generated_at=datetime.now(IST),
    )
    self._signals_generated.add(symbol)
```

**Decision tree:**

```
Open price vs. prev_close --> gap_pct in [3%, 5%]?
    +--YES --> open > prev_high?
        +--YES --> accumulated_volume > 50% ADV?
            +--YES --> candidate stored
                 +-- (at 9:30) ltp > open_price?
                     +--YES --> CandidateSignal emitted
                     +--NO  --> disqualified
```

### 7b. ORB Strategy

**File:** `signalpilot/strategy/orb.py`

Active phase: `CONTINUOUS` (9:45-14:30, but signals only generated until 11:00 AM).

#### Internal State (reset daily)

```python
_signals_generated: set[str] = set()     # one ORB signal per stock per day
_excluded_stocks: set[str] = set()       # Gap & Go stocks (3%+ gap excluded)
```

#### How `_excluded_stocks` Gets Populated

After all strategies evaluate in the scan loop, the orchestrator identifies
Gap & Go candidates and marks them in ORB/VWAP:

```python
gap_symbols = {c.symbol for c in all_candidates if c.strategy_name == "Gap & Go"}
for strat in strategies:
    if hasattr(strat, "mark_gap_stock"):
        for sym in gap_symbols:
            strat.mark_gap_stock(sym)
```

#### Breakout Detection Conditions

```
Opening Range = [range_high, range_low] of first 30-minute window (9:15-9:45)
               Locked at 9:45 by MarketScheduler --> lock_opening_ranges()

Breakout signal triggers when ALL conditions are met:
  1. opening_range.locked == True
  2. range_size_pct >= 0.5% AND <= 3.0%
  3. current_price > range_high  (bullish breakout only)
  4. current_candle.volume >= avg_candle_volume * 1.5
  5. risk_pct <= 3.0%  (SL is at range_low, must not exceed max risk)
  6. current_time < 11:00 AM
  7. symbol not in _excluded_stocks (gap stocks excluded)
  8. symbol not in _signals_generated (one per day)
```

#### Target/SL Calculation

```python
stop_loss = opening_range.range_low
target_1  = entry_price * (1 + 1.5 / 100)    # +1.5%
target_2  = entry_price * (1 + 2.5 / 100)    # +2.5%
risk_pct  = (entry_price - stop_loss) / entry_price * 100
```

#### CandidateSignal Fields

```python
CandidateSignal(
    symbol=symbol,
    direction=SignalDirection.BUY,
    strategy_name="ORB",
    entry_price=tick.ltp,
    stop_loss=opening_range.range_low,
    target_1=calculated_t1,
    target_2=calculated_t2,
    gap_pct=opening_range.range_size_pct,       # reused field for range size
    volume_ratio=current_candle.volume / avg_vol,
    price_distance_from_open_pct=((entry - range_high) / range_high) * 100,
    reason=<formatted string>,
    generated_at=now,
)
```

### 7c. VWAP Reversal Strategy

**File:** `signalpilot/strategy/vwap_reversal.py`

Active phase: `CONTINUOUS` (10:00 AM-2:30 PM, respects `_scan_start` and `_scan_end`).

#### Data Requirements

- At least 2 completed 15-min candles
- Valid VWAP value (> 0)
- Valid average candle volume (> 0)

#### Two Setup Types

**Setup 1 — Uptrend Pullback:**

| Check | Condition |
|-------|-----------|
| Prior candle trend | `prior_candle.close > vwap` |
| VWAP touch | `abs(current.low - vwap) / vwap * 100 <= 0.3%` OR `current.low <= vwap` |
| Bounce above VWAP | `current_candle.close > vwap` |
| Volume on bounce | `current_candle.volume >= avg_candle_volume * 1.0` |

```python
entry     = current_candle.close
stop_loss = vwap * (1 - 0.5 / 100)       # 0.5% below VWAP
target_1  = entry * (1 + 1.0 / 100)      # +1.0%
target_2  = entry * (1 + 1.5 / 100)      # +1.5%
```

**Setup 2 — VWAP Reclaim:**

| Check | Condition |
|-------|-----------|
| Prior candle below VWAP | `prior_candle.close < vwap` |
| Reclaim above VWAP | `current_candle.close > vwap` |
| Higher volume threshold | `current_candle.volume >= avg_candle_volume * 1.5` |

```python
entry     = current_candle.close
stop_loss = min([candles[-3:].low])       # lowest low of last 3 candles
target_1  = entry * (1 + 1.5 / 100)      # +1.5%
target_2  = entry * (1 + 2.0 / 100)      # +2.0%
```

#### Rate Controls

**VWAPCooldownTracker** (`signalpilot/monitor/vwap_cooldown.py`):

```python
@dataclass
class _CooldownEntry:
    signal_count: int
    last_signal_at: datetime
```

- `can_signal(symbol, now)` returns `True` if signal_count < 2 AND
  time since last >= 60 minutes
- `record_signal(symbol, now)` increments count and updates timestamp
- `reset()` clears all entries daily
- `get_state()` / `restore_state()` for crash recovery serialization

Additional dedup: per-candle evaluation tracking via `_last_evaluated_candle[symbol]`
prevents re-evaluating the same 15-min candle.

#### CandidateSignal Fields

```python
CandidateSignal(
    ...,
    strategy_name="VWAP Reversal",
    gap_pct=trend_ratio,              # reused: candles_above / total_candles
    volume_ratio=current.volume / avg_vol,
    price_distance_from_open_pct=touch_pct,  # reused: abs distance to VWAP %
    setup_type="uptrend_pullback" | "vwap_reclaim",
)
```

---

## 9. Step 8 — Duplicate Checking

### File: `signalpilot/monitor/duplicate_checker.py`

`DuplicateChecker` filters candidates using two cross-strategy checks
(runs after all strategies evaluate):

**Check 1 — Active Trade Check (Primary):**
- Fetches all active trades from `trade_repo.get_active_trades()`
- Suppresses any candidate whose symbol has an open trade
- Reason: "Duplicate suppressed: {symbol} has active trade"

**Check 2 — Same-Day Signal Check (Secondary):**
- For each remaining candidate, queries `signal_repo.has_signal_for_stock_today(symbol, today)`
- Suppresses any candidate with an existing signal today (any strategy, any status)
- Reason: "Duplicate suppressed: {symbol} already signaled today"

This prevents the same stock from receiving signals from multiple strategies
on the same day.

---

## 10. Step 9 — Signal Ranking & Scoring

### Files: `signalpilot/ranking/scorer.py`, `ranker.py`, `orb_scorer.py`, `vwap_scorer.py`

All `CandidateSignal` objects are pooled and ranked.

#### Scoring Dispatch

`SignalScorer` routes to the correct scorer per strategy:
- `"Gap & Go"` — default scoring (in `scorer.py`)
- `"ORB"` — delegates to `ORBScorer`
- `"VWAP Reversal"` — delegates to `VWAPScorer`

#### Gap & Go Scoring

Three factors normalized to [0.0, 1.0] with clamping:

```python
norm_gap  = clamp((gap_pct - 3.0) / 2.0)         # 3% -> 0.0, 5% -> 1.0
norm_vol  = clamp((volume_ratio - 0.5) / 2.5)     # 0.5x -> 0.0, 3.0x -> 1.0
norm_dist = clamp(distance_pct / 3.0)              # 0% -> 0.0, 3%+ -> 1.0

score = (norm_gap  * 0.40       # gap weight
       + norm_vol  * 0.35       # volume weight
       + norm_dist * 0.25)      # distance weight
```

#### ORB Scoring

```python
norm_vol   = clamp((ratio - 1.5) / 2.5)           # 1.5x -> 0.0, 4.0x -> 1.0
norm_range = clamp((3.0 - range_pct) / 2.5)       # INVERSE: 3% -> 0.0, 0.5% -> 1.0
norm_dist  = clamp(1.0 - distance_pct / 3.0)      # INVERSE: 0% -> 1.0, 3%+ -> 0.0

score = (norm_vol   * 0.40      # volume weight
       + norm_range * 0.30      # range weight (tighter = better)
       + norm_dist  * 0.30)     # distance weight (closer = better)
```

#### VWAP Scoring

```python
norm_vol   = clamp((ratio - 1.0) / 2.0)           # 1.0x -> 0.0, 3.0x -> 1.0
norm_touch = clamp(1.0 - touch_pct / 0.3)         # INVERSE: 0.3% -> 0.0, 0% -> 1.0
norm_trend = clamp(candles_above_ratio)            # direct clamping to [0, 1]

score = (norm_vol   * 0.35      # volume weight
       + norm_touch * 0.35      # touch precision (exact touch = better)
       + norm_trend * 0.30)     # trend confirmation weight
```

#### Normalization Summary

| Factor | Strategy | Min (0.0) | Max (1.0) | Direction |
|--------|----------|-----------|-----------|-----------|
| Gap % | Gap & Go | 3% | 5% | Linear |
| Volume Ratio | Gap & Go | 0.5x | 3.0x | Linear |
| Price Distance | Gap & Go | 0% | 3% | Linear |
| Volume Ratio | ORB | 1.5x | 4.0x | Linear |
| Range Size | ORB | 3% | 0.5% | **Inverse** |
| Breakout Distance | ORB | 3% | 0% | **Inverse** |
| Volume Ratio | VWAP | 1.0x | 3.0x | Linear |
| VWAP Touch | VWAP | 0.3% | 0% | **Inverse** |
| Candles Above | VWAP | 0% | 100% | Direct |

#### Ranking

```python
class SignalRanker:
    def rank(self, candidates: list[CandidateSignal]) -> list[RankedSignal]:
        scored = [(c, self._scorer.score(c)) for c in candidates]
        scored.sort(key=lambda x: x[1], reverse=True)   # highest first

        return [
            RankedSignal(
                candidate=candidate,
                composite_score=score,
                rank=i + 1,
                signal_strength=self._score_to_stars(score),
            )
            for i, (candidate, score) in enumerate(scored[:max_signals])
        ]
```

**Star Rating Mapping:**

| Score Range | Stars | Label |
|-------------|-------|-------|
| [0.0, 0.2) | 1 | Weak |
| [0.2, 0.4) | 2 | Fair |
| [0.4, 0.6) | 3 | Moderate |
| [0.6, 0.8) | 4 | Strong |
| [0.8, 1.0] | 5 | Very Strong |

`max_signals` defaults to 8 (from `default_max_positions`). Output is a sorted
list of `RankedSignal` objects.

---

## 11. Step 10 — Risk Management & Position Sizing

### Files: `signalpilot/risk/risk_manager.py`, `position_sizer.py`

#### Filtering Pipeline (in order)

**1. Position Slot Availability:**

```python
available_slots = user_config.max_positions - active_trade_count
if available_slots <= 0:
    return []   # no room for new positions
```

**2. Candidate Limiting:**

Takes only top N ranked signals where N = `available_slots`.

**3. Position Sizing (equal allocation):**

```python
per_trade_capital = total_capital / max_positions
quantity = int(per_trade_capital // entry_price)    # floor division, whole shares
capital_required = quantity * entry_price
```

**Example** with 50,000 capital, 5 max positions (from `user_config`), stock at 1,200:

```
per_trade_capital = 50,000 / 5 = 10,000
quantity          = floor(10,000 / 1,200) = 8 shares
capital_required  = 8 x 1,200 = 9,600
```

> **Note on `default_max_positions` vs `user_config.max_positions`:**
> `AppConfig.default_max_positions` (8) controls how many signals the *ranker*
> evaluates per cycle. The database `user_config.max_positions` (default 5)
> controls the actual *position limit* enforced by the risk manager. These are
> independent: the ranker can score up to 8 candidates, but the risk manager
> only passes signals through if open trades are below the DB limit.

**4. Price Affordability Filter:**

If `quantity == 0` (stock price exceeds per-trade allocation), the signal is
silently skipped with a log: "Auto-skipped {symbol}: price {entry} exceeds
per-trade allocation {per_trade_capital}".

**5. Expiry Assignment:**

`expires_at = generated_at + 30 minutes` (configurable via `signal_expiry_minutes`)

**Output:** `list[FinalSignal]`

```python
@dataclass
class FinalSignal:
    ranked_signal: RankedSignal
    quantity: int
    capital_required: float
    expires_at: datetime
```

---

## 12. Step 11 — Capital Allocation

### File: `signalpilot/risk/capital_allocator.py`

Capital is allocated across strategies using performance-weighted logic.

#### Reserve

```python
RESERVE_PCT = 0.20    # 20% held in reserve, 80% available for allocation
```

#### Auto Mode (Default) — Expectancy-Weighted Allocation

Uses 30-day historical performance:

```python
# Per-strategy expectancy
win_rate   = total_wins / signals_taken
avg_win    = total_pnl_wins / total_wins       (0 if no wins)
avg_loss   = total_pnl_losses / total_losses   (0 if no losses)
expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
weight     = max(expectancy, 0.0)              # floor at 0

# Normalize across strategies
weight_normalized = (weight / total_weight) * (1.0 - RESERVE_PCT)

# If no historical data: equal weights
equal_weight = (1.0 - RESERVE_PCT) / 3        # 0.2667 per strategy
```

#### Manual Mode

User can override via `ALLOCATE GAP 40 ORB 20 VWAP 20` command.
Total must be <= 80% (20% reserved).

#### Auto-Pause Feature

Monitors 30-day performance per strategy. Triggers pause recommendation if:
- `signals_taken >= 10` AND
- `win_rate < 40%`

#### Weekly Rebalance (Sunday 18:00 IST)

The `weekly_rebalance` cron job calls `capital_allocator.calculate_allocations()`
and `check_auto_pause()`, then sends allocation summary and pause
recommendations to Telegram.

---

## 13. Step 12 — Database Persistence

### File: `signalpilot/db/database.py`

SQLite with **WAL mode** and **foreign keys** enabled via pragma. Uses
`aiosqlite` with `Row` factory for named column access.

### Five Tables

#### `signals` table

```sql
CREATE TABLE signals (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    date                    TEXT    NOT NULL,
    symbol                  TEXT    NOT NULL,
    strategy                TEXT    NOT NULL,
    entry_price             REAL    NOT NULL,
    stop_loss               REAL    NOT NULL,
    target_1                REAL    NOT NULL,
    target_2                REAL    NOT NULL,
    quantity                INTEGER NOT NULL,
    capital_required        REAL    NOT NULL,
    signal_strength         INTEGER NOT NULL,
    gap_pct                 REAL    NOT NULL,
    volume_ratio            REAL    NOT NULL,
    reason                  TEXT    NOT NULL,
    created_at              TEXT    NOT NULL,
    expires_at              TEXT    NOT NULL,
    status                  TEXT    NOT NULL DEFAULT 'sent',
    setup_type              TEXT,              -- Phase 2: "uptrend_pullback" / "vwap_reclaim"
    strategy_specific_score REAL               -- Phase 2: composite score
);
-- Indexes: idx_signals_date, idx_signals_status, idx_signals_date_status
```

#### `trades` table

```sql
CREATE TABLE trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id       INTEGER NOT NULL REFERENCES signals(id),
    date            TEXT    NOT NULL,
    symbol          TEXT    NOT NULL,
    entry_price     REAL    NOT NULL,
    exit_price      REAL,
    stop_loss       REAL    NOT NULL,
    target_1        REAL    NOT NULL,
    target_2        REAL    NOT NULL,
    quantity        INTEGER NOT NULL,
    pnl_amount      REAL,
    pnl_pct         REAL,
    exit_reason     TEXT,
    taken_at        TEXT    NOT NULL,
    exited_at       TEXT,
    strategy        TEXT    NOT NULL DEFAULT 'gap_go'  -- Phase 2
);
-- Indexes: idx_trades_date, idx_trades_signal_id, idx_trades_exited_at
```

#### `user_config` table

```sql
CREATE TABLE user_config (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_chat_id TEXT   NOT NULL,
    total_capital   REAL    NOT NULL DEFAULT 50000.0,
    max_positions   INTEGER NOT NULL DEFAULT 5,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    gap_go_enabled  INTEGER NOT NULL DEFAULT 1,   -- Phase 2
    orb_enabled     INTEGER NOT NULL DEFAULT 1,   -- Phase 2
    vwap_enabled    INTEGER NOT NULL DEFAULT 1    -- Phase 2
);
```

#### `strategy_performance` table (Phase 2)

```sql
CREATE TABLE strategy_performance (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy            TEXT    NOT NULL,
    date                TEXT    NOT NULL,
    signals_generated   INTEGER NOT NULL DEFAULT 0,
    signals_taken       INTEGER NOT NULL DEFAULT 0,
    wins                INTEGER NOT NULL DEFAULT 0,
    losses              INTEGER NOT NULL DEFAULT 0,
    total_pnl           REAL    NOT NULL DEFAULT 0.0,
    win_rate            REAL    NOT NULL DEFAULT 0.0,
    avg_win             REAL    NOT NULL DEFAULT 0.0,
    avg_loss            REAL    NOT NULL DEFAULT 0.0,
    expectancy          REAL    NOT NULL DEFAULT 0.0,
    capital_weight_pct  REAL    NOT NULL DEFAULT 0.0,
    UNIQUE(strategy, date)
);
```

#### `vwap_cooldown` table (Phase 2)

```sql
CREATE TABLE vwap_cooldown (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol              TEXT    NOT NULL,
    last_signal_at      TEXT    NOT NULL,
    signal_count_today  INTEGER NOT NULL DEFAULT 0
);
```

#### Phase 2 Migration

`DatabaseManager._run_phase2_migration()` is idempotent. It uses
`PRAGMA table_info()` to check column existence before adding new columns
(`setup_type`, `strategy_specific_score` to signals; `strategy` to trades;
`gap_go_enabled`, `orb_enabled`, `vwap_enabled` to user_config) and creates
the `strategy_performance` and `vwap_cooldown` tables.

### Signal Status Lifecycle

Valid statuses: `frozenset({"sent", "taken", "expired", "paper", "position_full"})`

```
"sent"           <-- signal delivered in live mode
  |-- "taken"       user replies TAKEN
  +-- "expired"     30 minutes elapsed without user action

"paper"          <-- strategy is in paper-trading mode (ORB/VWAP by default)
  |-- "taken"       user replies TAKEN (paper trades can also be taken)
  +-- "expired"     30 minutes elapsed

"position_full"  <-- max positions reached (signal not delivered)
```

### Repository Methods

**SignalRepository** (`signal_repo.py`):

| Method | Description |
|--------|-------------|
| `insert_signal(record)` | Insert signal (18 fields), returns row ID |
| `has_signal_for_stock_today(symbol, date)` | Check if any signal exists for stock today |
| `update_status(signal_id, status)` | Update status (validates against valid set) |
| `get_active_signals(date, now)` | Non-expired signals: status IN (sent, paper) AND expires_at > now |
| `get_signals_by_date(date)` | All signals for date, ordered by created_at DESC |
| `expire_stale_signals(now)` | Bulk-update expired signals, returns count |
| `get_latest_active_signal(now)` | Most recent active signal (for TAKEN command) |

**TradeRepository** (`trade_repo.py`):

| Method | Description |
|--------|-------------|
| `insert_trade(trade)` | Insert trade (15 fields), returns row ID |
| `close_trade(id, exit_price, pnl_amount, pnl_pct, exit_reason)` | Close trade, sets exited_at to now(IST) |
| `get_active_trades()` | All open trades (exited_at IS NULL) |
| `get_active_trade_count()` | Count of open trades |
| `get_trades_by_date(date)` | All trades for date |
| `get_all_closed_trades()` | All closed trades (exited_at IS NOT NULL) |
| `get_trades_by_strategy(strategy)` | All trades for strategy |

**ConfigRepository** (`config_repo.py`):

| Method | Description |
|--------|-------------|
| `get_user_config()` | Current config or None |
| `initialize_default(chat_id, capital, positions)` | Create/update default config |
| `update_capital(amount)` | Update trading capital |
| `update_max_positions(n)` | Update max positions |
| `get_strategy_enabled(field)` | Check if strategy enabled (defaults True) |
| `set_strategy_enabled(field, enabled)` | Enable/disable strategy |

**MetricsCalculator** (`metrics.py`):

| Method | Description |
|--------|-------------|
| `calculate_performance_metrics(start, end)` | Aggregated metrics for closed trades in range |
| `calculate_daily_summary(date)` | Daily summary with cumulative P&L |
| `calculate_daily_summary_by_strategy(date)` | Per-strategy breakdown (excludes open trades) |

---

## 14. Step 13 — Telegram Delivery

### Files: `signalpilot/telegram/bot.py`, `formatters.py`

`SignalPilotBot.send_signal()` formats the `FinalSignal` into an HTML Telegram
message and sends it to the configured `chat_id`. All handlers are restricted
to the configured `chat_id` via `filters.Chat(chat_id=int(self._chat_id))`.

#### Signal Message Format

```
BUY SIGNAL -- RELIANCE

Entry Price: 2,850.00
Stop Loss:  2,764.50 (3.0% risk)
Target 1:   2,992.50 (5.0%)
Target 2:   3,049.50 (7.0%)
Quantity:   2 shares
Capital Required: 5,700
Signal Strength: ****- (Strong)
Strategy: Gap & Go
Positions open: 1/8
Reason: Gap up 3.8% above prev close (2,742.00), ...

Valid Until: 10:05 AM (auto-expires)
==============================
Reply TAKEN to log this trade
```

**Paper mode:** Adds `PAPER TRADE` prefix so the user knows it is a simulation.

**VWAP Reclaim:** Adds a `Higher Risk` warning for the riskier setup type.

**Strategy display:** Shows setup type when available, e.g.,
"VWAP Reversal (Uptrend Pullback)".

**Latency check:** A warning is logged if delivery takes more than 30 seconds
from signal generation time.

#### Exit Alert Formats

| Exit Type | Header | Body |
|-----------|--------|------|
| `SL_HIT` | "STOP LOSS HIT -- {symbol}" | "Exit immediately." + P&L |
| `TRAILING_SL_HIT` | "TRAILING SL HIT -- {symbol}" | "Exit immediately." + P&L |
| `T1_HIT` | "TARGET 1 HIT -- {symbol}" | "Consider booking partial profit." |
| `T2_HIT` | "TARGET 2 HIT -- {symbol}" | "Full exit recommended." + P&L |
| `TIME_EXIT` (advisory) | "TIME EXIT REMINDER" | "Market closing soon. Consider closing." |
| `TIME_EXIT` (mandatory) | "MANDATORY EXIT" | "Position closed at X (market closing)." |
| Trailing SL Update | "TRAILING SL UPDATE" | "New SL: X" + current price + P&L |

#### Star Rating Display

```
1 star:  *---- (Weak)
2 stars: **--- (Fair)
3 stars: ***-- (Moderate)
4 stars: ****- (Strong)
5 stars: ***** (Very Strong)
```

---

## 15. Step 14 — Exit Monitoring

### File: `signalpilot/monitor/exit_monitor.py`

On every scan-loop iteration, **after** strategy evaluation:

```python
active_trades = await self._trade_repo.get_active_trades()
for trade in active_trades:
    await self._exit_monitor.check_trade(trade)
```

#### `check_trade()` — Sequential Priority Checks

```
1. Get tick data for trade symbol
2. Update highest_price: max(state.highest_price, current_price)
3. Update trailing stop (breakeven / trail adjustment)
4. Check: current_price <= current_sl?  --> SL_HIT or TRAILING_SL_HIT
5. Check: current_price >= target_2?    --> T2_HIT (full exit)
6. Check: current_price >= target_1 and not t1_alerted? --> T1_HIT (advisory)
7. Send trailing SL update alert if one occurred in step 3
```

#### `_persist_exit()` — Trade Closure

When an exit triggers (SL, T2, mandatory time exit):

```python
pnl_amount = (exit_price - trade.entry_price) * trade.quantity
await self._close_trade(trade.id, exit_price, pnl_amount, pnl_pct, exit_reason)
# close_trade is wired to trade_repo.close_trade() via callback
```

The trade is then removed from the monitoring map.

#### Per-Strategy Trailing Stop Configs

```python
TrailingStopConfig = {
    "Gap & Go": TrailingStopConfig(
        breakeven_trigger_pct=2.0,     # SL -> entry at +2%
        trail_trigger_pct=4.0,         # trailing starts at +4%
        trail_distance_pct=2.0         # SL trails 2% below peak
    ),
    "gap_go": <same as Gap & Go>,

    "ORB": TrailingStopConfig(
        breakeven_trigger_pct=1.5,     # SL -> entry at +1.5%
        trail_trigger_pct=2.0,         # trailing starts at +2%
        trail_distance_pct=1.0         # SL trails 1% below peak
    ),

    "VWAP Reversal": TrailingStopConfig(
        breakeven_trigger_pct=1.0,     # SL -> entry at +1%
        trail_trigger_pct=None,        # NO trailing
        trail_distance_pct=None
    ),
    "VWAP Reversal:uptrend_pullback": TrailingStopConfig(
        breakeven_trigger_pct=1.0,     # same as base
        trail_trigger_pct=None,
        trail_distance_pct=None
    ),
    "VWAP Reversal:vwap_reclaim": TrailingStopConfig(
        breakeven_trigger_pct=1.5,     # slightly higher for riskier setup
        trail_trigger_pct=None,
        trail_distance_pct=None
    ),
}
```

Config lookup uses a 3-tier fallback:
1. Try `strategy:setup_type` key (e.g., `"VWAP Reversal:vwap_reclaim"`)
2. Fall back to strategy name (e.g., `"VWAP Reversal"`)
3. Use constructor-level defaults

#### Trailing Stop State (per trade)

```python
@dataclass
class TrailingStopState:
    trade_id: int
    original_sl: float
    current_sl: float           # moves up over time, never down
    highest_price: float        # peak price seen since entry
    strategy: str = "gap_go"
    breakeven_triggered: bool = False
    trailing_active: bool = False
    t1_alerted: bool = False    # T1 advisory sent once only
```

#### `_update_trailing_stop()` Logic

```python
move_pct = (current_price - entry_price) / entry_price * 100

# Phase 1: Breakeven
if move_pct >= breakeven_trigger_pct and not breakeven_triggered:
    current_sl = entry_price                 # SL moves to entry
    breakeven_triggered = True
    alert: "SL moved to breakeven"

# Phase 2: Trailing (only if trail_trigger_pct is not None)
if move_pct >= trail_trigger_pct:
    new_sl = current_price * (1.0 - trail_distance_pct / 100.0)
    if new_sl > current_sl:                  # never moves down
        current_sl = new_sl
        trailing_active = True
        alert: "Trailing SL updated to {new_sl}"
```

#### Time-Based Exits

| Time | Method | Behavior |
|------|--------|----------|
| 15:00 | `trigger_time_exit(trades, is_mandatory=False)` | Advisory alerts only |
| 15:15 | `trigger_time_exit(trades, is_mandatory=True)` | Persist exits, stop monitoring |

#### Exit Summary Table

| Exit Type | Persists to DB? | Stops Monitoring? | Alert Type |
|-----------|----------------|-------------------|------------|
| SL_HIT | Yes | Yes | Exit alert |
| TRAILING_SL_HIT | Yes | Yes | Exit alert |
| T2_HIT | Yes | Yes | Exit alert |
| T1_HIT | No | No | Advisory |
| Trailing SL Update | No | No | Advisory |
| TIME_EXIT (advisory) | No | No | Advisory |
| TIME_EXIT (mandatory) | Yes | Yes | Exit alert |

---

## 16. Step 15 — Telegram Commands (User Interaction)

### File: `signalpilot/telegram/handlers.py`

The bot listens for text messages in the configured chat and dispatches to
handler functions. All commands are case-insensitive.

| Command | Regex Pattern | Action |
|---------|--------------|--------|
| `TAKEN [FORCE] [id]` | `(?i)^/?taken(?:\s+force)?(?:\s+(\d+))?$` | Mark a signal as a trade (optionally by signal ID); FORCE overrides position limit |
| `STATUS` | `(?i)^status$` | Show active signals and open trades with live P&L |
| `JOURNAL` | `(?i)^journal$` | Display performance metrics (win rate, P&L, risk-reward) |
| `CAPITAL <amt>` | `(?i)^capital\s+\d+(?:\.\d+)?$` | Update total trading capital |
| `PAUSE <strat>` | `(?i)^pause\s+\w+$` | Disable a strategy (GAP/ORB/VWAP) |
| `RESUME <strat>` | `(?i)^resume\s+\w+$` | Re-enable a paused strategy |
| `ALLOCATE` | `(?i)^allocate` | Show/set capital allocation (AUTO or manual) |
| `STRATEGY` | `(?i)^strategy$` | Show 30-day per-strategy performance breakdown |
| `HELP` | `(?i)^help$` | List all commands |

#### TAKEN Flow

The `TAKEN` command accepts an optional `FORCE` keyword and signal ID. If an ID
is provided, it takes that specific signal; otherwise it takes the most recent
active signal.

**Position limit enforcement:** Before creating a trade, the handler checks
`active_trade_count >= max_positions`. If the limit is reached, it returns a
soft warning: `"Position limit reached (5/5). Use TAKEN FORCE to override."`
The `FORCE` keyword bypasses this check, allowing users to intentionally exceed
the limit.

```python
_TAKEN_PATTERN = re.compile(r"(?i)^/?taken(?:\s+force)?(?:\s+(\d+))?$")

async def handle_taken(signal_repo, trade_repo, config_repo, exit_monitor, text, now=None):
    match = _TAKEN_PATTERN.match(text)
    requested_id = int(match.group(1)) if match.group(1) else None

    if requested_id:
        signal = await signal_repo.get_active_signal_by_id(requested_id, now)
    else:
        signal = await signal_repo.get_latest_active_signal(now)

    if not signal:
        return "No active signal to take."

    # Position limit check (soft block unless FORCE)
    force = text and re.search(r"(?i)\bforce\b", text)
    if not force:
        user_config = await config_repo.get_user_config()
        active_count = await trade_repo.get_active_trade_count()
        if user_config and active_count >= user_config.max_positions:
            return f"Position limit reached ({active_count}/{user_config.max_positions}). Use TAKEN FORCE to override."

    trade = TradeRecord(...)
    trade_id = await trade_repo.insert_trade(trade)
    await signal_repo.update_status(signal.id, "taken")
    exit_monitor.start_monitoring(trade)        # begin tick-by-tick monitoring
    return f"Trade logged. Tracking {signal.symbol}."
```

Once `start_monitoring()` is called, `TrailingStopState` is initialised for
the trade and it enters the exit-monitoring loop on every subsequent tick.

> **Note:** Position limits are now enforced as a soft warning in the TAKEN handler.
> Users can override with `TAKEN FORCE` when they intentionally want to exceed
> `max_positions`. The risk manager also independently gates *new signal generation*
> at the same limit.

#### CAPITAL Flow

```python
async def handle_capital(config_repo, text: str):
    amount = float(re.match(r"(?i)^capital\s+(\d+(?:\.\d+)?)", text).group(1))
    await config_repo.update_capital(amount)
    user_config = await config_repo.get_user_config()
    per_trade = amount / user_config.max_positions
    return f"Capital updated to {amount:,.0f}. Per-trade allocation is now {per_trade:,.0f}."
```

#### PAUSE / RESUME Strategy Map

```python
_STRATEGY_MAP = {
    "GAP":  ("gap_go_enabled", "Gap & Go"),
    "ORB":  ("orb_enabled", "ORB"),
    "VWAP": ("vwap_enabled", "VWAP Reversal"),
}
```

#### ALLOCATE Sub-Commands

| Command | Action |
|---------|--------|
| `ALLOCATE` (no args) | Show current allocation per strategy with reserve |
| `ALLOCATE AUTO` | Re-enable automatic expectancy-weighted allocation |
| `ALLOCATE GAP 40 ORB 20 VWAP 20` | Manual allocation (total must be <= 80%) |

---

## 17. Step 16 — Daily Wind-Down & Summary

### Wind-Down Phase (14:30-15:35)

| Time | Event |
|------|-------|
| 14:30 | `stop_new_signals()` — `_accepting_signals = False`; scan loop continues for exit monitoring only |
| 15:00 | `trigger_exit_reminder()` — advisory alerts per open trade with unrealized P&L |
| 15:15 | `trigger_mandatory_exit()` — forced exit for all remaining open trades (persists to DB) |
| 15:30 | `send_daily_summary()` — calculates metrics and sends daily report |
| 15:35 | `shutdown()` — graceful teardown |

#### Daily Summary Format

```
Daily Summary -- 2026-02-23

Signals Generated: 6
Trades Taken: 3
Wins: 2 | Losses: 1
Today's P&L: +4,500
Cumulative P&L: +28,300

BY STRATEGY
  Gap & Go: 4 signals, 2 taken, P&L +4,500
  ORB: 2 signals, 1 taken, P&L 0 (paper)

Trade Details
  RELIANCE: t2_hit | P&L: +3,200
  INFY: sl_hit | P&L: -1,500
  TCS: t1_hit | P&L: +2,800
```

The `calculate_daily_summary_by_strategy()` method only counts **closed trades**
(`exited_at IS NOT NULL`) to exclude open trades with NULL P&L values.

Cumulative P&L is calculated as:
`SUM(pnl_amount) WHERE exited_at IS NOT NULL AND date <= today`

---

## 18. Step 17 — Shutdown & Crash Recovery

### Graceful Shutdown

At 15:35 IST (or on `SIGINT`/`SIGTERM`, guarded by a `shutting_down` flag
to prevent double-shutdown):

```python
async def shutdown(self):
    self._scanning = False
    if self._scan_task:
        self._scan_task.cancel()

    await self._websocket.disconnect()     # WebSocket first
    await self._bot.stop()                 # Telegram bot
    await self._db.close()                 # Database last
    self._scheduler.shutdown()
```

### Crash Recovery

If the process restarts during market hours, `recover()` runs instead of
`startup()`:

```python
async def recover(self):
    # 1. Re-initialize infrastructure
    await self._db.initialize()
    await self._authenticator.authenticate()
    await self._instruments.load()
    await self._load_historical_data()

    # 2. Reload active trades from DB -- no data is lost
    active_trades = await self._trade_repo.get_active_trades()
    for trade in active_trades:
        self._exit_monitor.start_monitoring(trade)

    # 3. Restart services
    await self._bot.start()
    await self._bot.send_alert("System recovered. Monitoring resumed.")
    self._scheduler.configure_jobs(self)
    self._scheduler.start()
    await self.start_scanning()

    # 4. Honour time: respect signal cutoff based on current phase
    phase = get_current_phase(datetime.now(IST))
    if phase not in (StrategyPhase.OPENING, StrategyPhase.ENTRY_WINDOW,
                     StrategyPhase.CONTINUOUS):
        self._accepting_signals = False    # WIND_DOWN / POST_MARKET
```

Key detail: `_accepting_signals` stays `True` during OPENING, ENTRY_WINDOW,
and CONTINUOUS phases — this allows ORB and VWAP strategies to resume
signal generation after a mid-day crash.

---

## 19. Data Model Chain

The journey of a signal from detection to database:

```
TickData (WebSocket)
    |
    v
CandidateSignal          <-- produced by GapAndGoStrategy / ORBStrategy / VWAPReversalStrategy
    | symbol, direction, entry, SL, T1, T2, gap_pct, volume_ratio,
    | price_distance_from_open_pct, reason, generated_at, setup_type
    v
  [DuplicateChecker]     <-- filter: active trades + same-day signals
    v
RankedSignal             <-- produced by SignalRanker
    | candidate, composite_score, rank (1-N), signal_strength (1-5 stars)
    v
FinalSignal              <-- produced by RiskManager
    | ranked_signal, quantity, capital_required, expires_at
    v
SignalRecord             <-- persisted to `signals` table (18 fields)
    | id, date, symbol, strategy, entry_price, stop_loss, T1, T2,
    | quantity, capital_required, signal_strength, gap_pct, volume_ratio,
    | reason, created_at, expires_at, status, setup_type, strategy_specific_score
    v
TradeRecord              <-- created when user replies TAKEN (15 fields)
    | signal_id, date, symbol, strategy, entry_price, stop_loss, T1, T2,
    | quantity, taken_at, exit_price, pnl_amount, pnl_pct, exit_reason, exited_at
```

### All Dataclasses

| Dataclass | Module | Key Fields |
|-----------|--------|------------|
| `Instrument` | `db/models.py` | symbol, name, angel_token, exchange, nse_symbol, yfinance_symbol, lot_size |
| `TickData` | `db/models.py` | symbol, ltp, open_price, high, low, close, volume, timestamps |
| `HistoricalReference` | `db/models.py` | previous_close, previous_high, average_daily_volume |
| `PreviousDayData` | `db/models.py` | close, high, low, open, volume |
| `CandidateSignal` | `db/models.py` | symbol, direction, strategy_name, entry/SL/T1/T2, gap_pct, volume_ratio, setup_type |
| `ScoringWeights` | `db/models.py` | gap_pct_weight, volume_ratio_weight, price_distance_weight |
| `RankedSignal` | `db/models.py` | candidate, composite_score, rank, signal_strength |
| `PositionSize` | `db/models.py` | quantity, capital_required, per_trade_capital |
| `FinalSignal` | `db/models.py` | ranked_signal, quantity, capital_required, expires_at |
| `SignalRecord` | `db/models.py` | 18 fields matching signals table |
| `TradeRecord` | `db/models.py` | 15 fields matching trades table |
| `UserConfig` | `db/models.py` | total_capital, max_positions, strategy enable flags |
| `ExitAlert` | `db/models.py` | trade, exit_type, current_price, pnl_pct, is_alert_only, trailing_sl_update |
| `TrailingStopState` | `exit_monitor.py` | trade_id, original_sl, current_sl, highest_price, strategy, flags |
| `TrailingStopConfig` | `exit_monitor.py` | breakeven_trigger_pct, trail_trigger_pct, trail_distance_pct |
| `PerformanceMetrics` | `db/models.py` | 15 fields: win_rate, total_pnl, avg_win/loss, best/worst trade |
| `DailySummary` | `db/models.py` | date, signals_sent, trades_taken, wins, losses, pnl, cumulative_pnl, strategy_breakdown |
| `StrategyDaySummary` | `db/models.py` | strategy_name, signals_generated, signals_taken, pnl |
| `StrategyPerformanceRecord` | `db/models.py` | strategy, date, signals, wins, losses, pnl, win_rate, expectancy, capital_weight_pct |
| `OpeningRange` | `market_data_store.py` | range_high, range_low, locked, range_size_pct |
| `VWAPState` | `market_data_store.py` | cumulative_price_volume, cumulative_volume, current_vwap |
| `Candle15Min` | `market_data_store.py` | symbol, OHLCV, start_time, end_time, is_complete |

### Enums

| Enum | Values |
|------|--------|
| `SignalDirection` | `BUY`, `SELL` |
| `ExitType` | `SL_HIT`, `T1_HIT`, `T2_HIT`, `TRAILING_SL_HIT`, `TIME_EXIT` |
| `StrategyPhase` | `PRE_MARKET`, `OPENING`, `ENTRY_WINDOW`, `CONTINUOUS`, `WIND_DOWN`, `POST_MARKET` |

---

## 20. Logging & Observability

### Files: `signalpilot/utils/logger.py`, `log_context.py`

#### Structured Logging

Every log record is enriched with async-safe context fields via `contextvars`:

```python
# Set context at the start of each scan cycle
set_context(cycle_id="a3f9b2c1", phase="entry_window")

# Or use the async context manager (token-based, preserves outer context)
async with log_context(symbol="RELIANCE"):
    ...     # symbol is set; outer context restored on exit
```

#### Context Fields

| Field | Example | Set by |
|-------|---------|--------|
| `cycle_id` | `a3f9b2c1` | `_scan_loop()` — unique 8-char hex per second |
| `phase` | `entry_window` | `_scan_loop()` from `get_current_phase()` |
| `symbol` | `RELIANCE` | Strategy evaluation, exit monitor |
| `job_name` | `start_scanning` | Scheduler job callbacks |
| `command` | `TAKEN` | Telegram command handlers |

#### Log Format

```
%(asctime)s [%(cycle_id)s] [%(phase)s] [%(symbol)s] [%(levelname)s] [%(name)s] %(message)s
```

Example:
```
2026-02-23 09:31:05 [a3f9b2c1] [entry_window] [RELIANCE] [INFO] [gap_and_go]
  Signal generated: RELIANCE entry=2850.00 SL=2764.50 T1=2992.50 T2=3049.50
```

#### Log Rotation & Suppression

- **File handler:** `TimedRotatingFileHandler` rotating at midnight, 7-day retention
- **Console handler:** stderr, ERROR level only
- **Suppressed loggers** (set to WARNING): `apscheduler`, `telegram`, `httpx`,
  `SmartApi`, `yfinance`, `urllib3`, `asyncio`

#### Circuit Breaker

If the scan loop encounters 10 consecutive errors without recovery:

```python
if consecutive_errors >= self._max_consecutive_errors:  # 10
    self._scanning = False
    await self._bot.send_alert(
        "ALERT: Scan loop stopped due to repeated errors. "
        "Manual intervention required."
    )
```

#### Diagnostic Heartbeat

Every 60 scan cycles (~1 minute), the loop logs a heartbeat with phase,
enabled strategy count, WebSocket connection status, and candidate count.

---

## 21. Rate Limiting & Retry

### Token Bucket Rate Limiter

**File:** `signalpilot/utils/rate_limiter.py`

`TokenBucketRateLimiter` enforces both per-second and per-minute caps.

```python
limiter = TokenBucketRateLimiter(rate=3, per_minute=170)
await limiter.acquire()    # blocks until a token is available
```

**Algorithm:**

1. **Token refill** (continuous): `tokens = min(rate, tokens + elapsed * rate)`
   — burst capacity equals the per-second rate
2. **Per-token wait**: If `tokens < 1`, sleep for `deficit / rate` seconds, then refill
3. **Per-minute window**: If `minute_count >= per_minute`, sleep until 60s window resets
4. **Decrement**: `tokens -= 1`, `minute_count += 1`

All operations are protected by an `asyncio.Lock` to prevent concurrent depletion.

The `reset_minute_counter()` method is called between independent API fetch
passes (prev-day and ADV) to prevent one pass from exhausting the other's
per-minute budget.

### Retry Decorator

**File:** `signalpilot/utils/retry.py`

```python
@with_retry(max_retries=3, base_delay=1.0, max_delay=30.0, exponential=True)
async def some_api_call():
    ...
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_retries` | `3` | Retry attempts (total calls = 4) |
| `base_delay` | `1.0` | Initial delay (seconds) |
| `max_delay` | `30.0` | Cap on exponential backoff |
| `exponential` | `True` | Exponential vs constant delay |
| `exceptions` | `(Exception,)` | Exception types to catch |

**Backoff sequence** (default params):
- Attempt 0: immediate (no delay)
- Attempt 1: fail -> sleep min(1 * 2^0, 30) = 1s
- Attempt 2: fail -> sleep min(1 * 2^1, 30) = 2s
- Attempt 3: fail -> sleep min(1 * 2^2, 30) = 4s
- All exhausted: re-raise exception

---

## 22. Complete Scan Loop Iteration

### File: `signalpilot/scheduler/lifecycle.py` — `_scan_loop()`

```
WHILE scanning == True:
  |
  |-- a. Generate 8-char hex cycle_id
  |-- b. set_context(cycle_id, phase)
  |
  |-- c. IF _accepting_signals AND phase IN (OPENING, ENTRY_WINDOW, CONTINUOUS):
  |   |-- Fetch user_config from config_repo
  |   |-- Filter strategies by enabled flags (gap_go_enabled, orb_enabled, vwap_enabled)
  |   |-- FOR each enabled strategy WHERE phase IN strategy.active_phases:
  |   |     +-- candidates += await strategy.evaluate(market_data, phase)
  |   |
  |   |-- d. Cross-strategy gap marking:
  |   |     gap_symbols = {c.symbol for c in candidates if strategy_name == "Gap & Go"}
  |   |     FOR each strategy with mark_gap_stock():
  |   |       FOR sym in gap_symbols: strategy.mark_gap_stock(sym)
  |   |
  |   |-- e. IF candidates AND duplicate_checker:
  |   |     candidates = await duplicate_checker.filter_duplicates(candidates, today)
  |   |
  |   |-- f. IF candidates:
  |   |     ranked = ranker.rank(candidates)
  |   |     active_count = await trade_repo.get_active_trade_count()
  |   |     final_signals = risk_manager.filter_and_size(ranked, config, active_count)
  |   |
  |   |     g. FOR each signal in final_signals:
  |   |       |-- record = _signal_to_record(signal, now)
  |   |       |-- is_paper = _is_paper_mode(signal, app_config)
  |   |       |-- IF is_paper: record.status = "paper"
  |   |       |-- signal_id = await signal_repo.insert_signal(record)
  |   |       +-- await bot.send_signal(signal, is_paper)
  |   |
  |   +-- h. Heartbeat every 60 cycles (~1 min)
  |
  |-- i. Exit Monitoring (ALWAYS, every iteration):
  |     active_trades = await trade_repo.get_active_trades()
  |     FOR trade in active_trades:
  |       await exit_monitor.check_trade(trade)
  |
  |-- j. Expire stale signals (30-min window):
  |     count = await signal_repo.expire_stale_signals(now)
  |
  |-- k. On success: consecutive_errors = 0
  |
  |-- EXCEPT any exception:
  |     consecutive_errors += 1
  |     IF consecutive_errors >= 10: --> circuit breaker, stop loop
  |
  |-- FINALLY: reset_context()
  |
  +-- await asyncio.sleep(1)
```

---

## 23. Summary: A Complete Trading Day

```
08:00  App boots --> AppConfig loaded, logging configured
08:00  create_app() wires 20+ components
08:00  SmartAPIAuthenticator.authenticate() (TOTP-based 2FA)
08:01  InstrumentManager.load() (Nifty 500 from CSV)
08:01  historical.fetch_previous_day_data()    <-- 499 stocks, batches of 3
08:10  (5s cooldown between API passes)
08:10  historical.fetch_average_daily_volume() <-- 20-day ADV
08:20  ConfigRepository.initialize_default()
08:20  bot.start() --> Telegram polling begins
08:20  MarketScheduler.start() --> 9 cron jobs registered

09:00  [CRON] send_pre_market_alert()
         --> "Signals coming shortly after 9:15 AM"

09:15  [CRON] start_scanning()
         |   _reset_session() --> clear intraday data, reset strategies
         |   websocket.connect() --> subscribe all 500 tokens (Mode 3)
         +-> _scan_loop() starts (every 1 second)
               |
               |-- phase = OPENING (9:15-9:30)
               |    +-- GapAndGoStrategy: detect gaps [3%-5%], open > prev_high,
               |        volume >= 50% ADV --> _gap_candidates, _volume_validated
               |    +-- ORB: opening range building (update_opening_range per tick)
               |
               |-- phase = ENTRY_WINDOW (9:30-9:45)
               |    +-- GapAndGoStrategy: validate ltp > open_price
               |        --> CandidateSignal (SL=open or 3% cap, T1=+5%, T2=+7%)
               |    +-- ORB: opening range still building
               |
               |-- [9:45 CRON] lock_opening_ranges()
               |    +-- OpeningRange.locked = True, range_size_pct calculated
               |
               |-- phase = CONTINUOUS (9:45-14:30)
               |    +-- ORBStrategy (until 11:00): breakout above range_high
               |        + volume >= 1.5x avg + range in [0.5%, 3.0%]
               |        --> CandidateSignal (SL=range_low, T1=+1.5%, T2=+2.5%)
               |    +-- VWAPReversalStrategy (from 10:00): uptrend_pullback / vwap_reclaim
               |        + 0.3% VWAP touch + volume confirmation
               |        --> CandidateSignal (Setup 1: T1=+1%, T2=+1.5% / Setup 2: T1=+1.5%, T2=+2%)
               |
               +-- (every pipeline iteration, all phases):
               |    |-- DuplicateChecker: filter active trades + same-day signals
               |    |-- SignalRanker: score + rank --> RankedSignal (1-5 stars)
               |    |-- RiskManager: position limits + sizing --> FinalSignal
               |    |-- Paper mode check (ORB/VWAP)
               |    |-- SignalRepo: INSERT INTO signals
               |    +-- Bot: send_signal() --> Telegram HTML message
               |
               +-- (every tick, all phases 9:15-15:15):
                    ExitMonitor.check_trade() for each active trade:
                      |-- SL/trailing SL hit?  --> persist + alert + stop monitoring
                      |-- T2 hit?              --> persist + alert + stop monitoring
                      |-- T1 hit?              --> advisory alert (once)
                      +-- Trailing SL update?  --> advisory alert

14:30  [CRON] stop_new_signals()
         --> _accepting_signals = False (scan loop continues for exits)

15:00  [CRON] trigger_exit_reminder()
         --> advisory alerts per open trade (TIME_EXIT, is_alert_only=True)

15:15  [CRON] trigger_mandatory_exit()
         --> forced exit for all open trades (persist + alert)

15:30  [CRON] send_daily_summary()
         --> MetricsCalculator.calculate_daily_summary(today)
         --> Per-strategy breakdown (closed trades only)
         --> Cumulative P&L

15:35  [CRON] shutdown()
         --> WebSocket disconnect, bot stop, DB close, scheduler shutdown

Sunday 18:00  [CRON] weekly_rebalance()
         --> CapitalAllocator.calculate_allocations()
         --> check_auto_pause() (warn if win_rate < 40% after 10+ trades)
         --> Send allocation summary to Telegram
```
