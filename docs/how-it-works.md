# SignalPilot — End-to-End How It Works

> A step-by-step walkthrough of every stage in the signal lifecycle,
> from cold boot to Telegram delivery and trade exit.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Step 1 — Configuration & Startup](#2-step-1--configuration--startup)
3. [Step 2 — Pre-Market Data Fetch](#3-step-2--pre-market-data-fetch)
4. [Step 3 — Market Scheduling](#4-step-3--market-scheduling)
5. [Step 4 — Real-Time Data (WebSocket)](#5-step-4--real-time-data-websocket)
6. [Step 5 — Strategy Evaluation](#6-step-5--strategy-evaluation)
   - [5a. Gap & Go Strategy](#5a-gap--go-strategy)
   - [5b. ORB Strategy](#5b-orb-strategy)
   - [5c. VWAP Reversal Strategy](#5c-vwap-reversal-strategy)
7. [Step 6 — Signal Ranking & Scoring](#7-step-6--signal-ranking--scoring)
8. [Step 7 — Risk Management & Position Sizing](#8-step-7--risk-management--position-sizing)
9. [Step 8 — Database Persistence](#9-step-8--database-persistence)
10. [Step 9 — Telegram Delivery](#10-step-9--telegram-delivery)
11. [Step 10 — Exit Monitoring](#11-step-10--exit-monitoring)
12. [Step 11 — Telegram Commands (User Interaction)](#12-step-11--telegram-commands-user-interaction)
13. [Step 12 — Daily Wind-Down & Summary](#13-step-12--daily-wind-down--summary)
14. [Step 13 — Shutdown & Crash Recovery](#14-step-13--shutdown--crash-recovery)
15. [Data Model Chain](#15-data-model-chain)
16. [Logging & Observability](#16-logging--observability)

---

## 1. Architecture Overview

SignalPilot is an **async-first, dependency-injected** Python application. All 16
components are wired together once at boot and communicate through typed
`dataclass` contracts. No global state; every component receives its
dependencies via constructor parameters.

```
[.env / environment]
        │
        ▼
   AppConfig (pydantic-settings)
        │
        ▼
   create_app()          ← wires all 16 components
        │
        ├─► DatabaseManager ──► SignalRepository
        │                  ──► TradeRepository
        │                  ──► ConfigRepository
        │                  ──► MetricsCalculator
        │
        ├─► SmartAPIAuthenticator ──► Angel One SmartAPI
        │
        ├─► InstrumentManager  ──► nifty500_list.csv
        │
        ├─► HistoricalDataFetcher (Angel One + yfinance fallback)
        │
        ├─► MarketDataStore  ← receives ticks from WebSocket
        │
        ├─► WebSocketClient  ──► Angel One WebSocket feed
        │
        ├─► GapAndGoStrategy │
        ├─► ORBStrategy      ├─► strategies evaluate MarketDataStore
        ├─► VWAPReversal     │
        │
        ├─► SignalRanker (SignalScorer ──► ORBScorer / VWAPScorer)
        │
        ├─► RiskManager (PositionSizer)
        │
        ├─► ExitMonitor  ──► reads MarketDataStore, fires Telegram alerts
        │
        ├─► SignalPilotBot (Telegram)
        │
        └─► MarketScheduler (APScheduler cron jobs)
                │
                └─► SignalPilotApp._scan_loop()  ← runs every second
```

The **central orchestrator** is `SignalPilotApp`
(`signalpilot/scheduler/lifecycle.py`). It owns the main scanning loop and
calls each stage in sequence on every 1-second tick.

---

## 2. Step 1 — Configuration & Startup

### File: `signalpilot/config.py`

All configuration is loaded from a `.env` file (or real environment variables)
using **pydantic-settings**. There is no hardcoded configuration.

```python
# signalpilot/config.py  (simplified)
class AppConfig(BaseSettings):
    angel_api_key: str          # Angel One SmartAPI key
    angel_client_id: str
    angel_mpin: str
    angel_totp_secret: str      # TOTP seed for 2FA

    telegram_bot_token: str
    telegram_chat_id: str

    db_path: str = "signalpilot.db"
    nifty500_csv_path: str = "data/nifty500_list.csv"

    default_capital: float = 50000.0
    default_max_positions: int = 8

    gap_min_pct: float = 3.0    # Gap & Go: min gap %
    gap_max_pct: float = 5.0    # Gap & Go: max gap %
    target_1_pct: float = 5.0   # Target 1 from entry
    target_2_pct: float = 7.0   # Target 2 from entry
    max_risk_pct: float = 3.0   # Max stop-loss %

    model_config = {"env_file": ".env"}
```

A `@model_validator` enforces that scoring weights sum to 1.0 for each strategy
group (Gap & Go, ORB, VWAP). Config is validated on startup — the app won't
start with invalid weights.

### Entry Point: `signalpilot/main.py`

```python
async def main() -> None:
    config = AppConfig()                     # load .env
    configure_logging(...)
    app = await create_app(config)           # wire all components

    now = datetime.now(IST)
    if is_market_hours(now) and is_trading_day(now.date()):
        await app.recover()                  # crash-recovery path
    else:
        await app.startup()                  # normal startup

    while True:
        await asyncio.sleep(1)               # keep event loop alive
```

There are two startup paths:
- **Normal** (`app.startup()`): pre-market boot, fetch historical data, start
  the scheduler.
- **Crash recovery** (`app.recover()`): re-authenticate, reload active trades
  from DB, resume monitoring immediately.

---

## 3. Step 2 — Pre-Market Data Fetch

### File: `signalpilot/data/historical.py`

Before the market opens, SignalPilot needs two reference datasets for every
Nifty 500 stock:

| Dataset | Used for |
|---------|----------|
| **Previous day close & high** | Gap % calculation, above-prev-high check |
| **20-day Average Daily Volume (ADV)** | Volume ratio calculation |

```python
# Inside SignalPilotApp.startup()
await self._historical.fetch_previous_day_data()
await self._historical.fetch_average_daily_volume()  # 20-day lookback
```

Each fetch processes stocks in **batches of 3** with a 1.2 s inter-batch delay
to respect the Angel One API rate limit (3 req/s, 170 req/min).

```python
# signalpilot/data/historical.py  (simplified)
async def fetch_previous_day_data(self) -> dict[str, PreviousDayData]:
    for i in range(0, len(symbols), _BATCH_SIZE):   # batches of 3
        batch = symbols[i : i + _BATCH_SIZE]
        tasks = [self._fetch_single_previous_day(s) for s in batch]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.sleep(_BATCH_DELAY)            # 1.2 s between batches
```

**Fallback chain** for every symbol:

```
1. Angel One SmartAPI  (getCandleData, ONE_DAY interval)
        │ fails?
        ▼
2. yfinance            (ticker.history)
        │ fails?
        ▼
   Symbol excluded from today's universe
```

The `TokenBucketRateLimiter` (`signalpilot/utils/rate_limiter.py`) enforces
both per-second and per-minute caps internally.

```python
# Rate-limited call pattern
await self._limiter.acquire()          # blocks until a token is available
async with self._semaphore:            # max 3 concurrent requests
    return await func(*args, **kwargs)
```

Fetched data is stored in `MarketDataStore`, keyed by symbol.

---

## 4. Step 3 — Market Scheduling

### File: `signalpilot/scheduler/scheduler.py`

`MarketScheduler` wraps **APScheduler 3.x** with 7 IST cron jobs registered
against `SignalPilotApp` methods:

| Time (IST) | Job | Action |
|-----------|-----|--------|
| 09:00 | `pre_market_alert` | Send "Signals coming at 9:15" Telegram alert |
| 09:15 | `start_scanning` | Open WebSocket, begin 1-second scan loop |
| 14:30 | `stop_new_signals` | Stop generating new signals |
| 15:00 | `exit_reminder` | Send advisory exit alerts for open positions |
| 15:15 | `mandatory_exit` | Trigger mandatory exit for all open trades |
| 15:30 | `daily_summary` | Generate and send end-of-day report |
| 15:35 | `shutdown` | Graceful shutdown |
| Sunday 18:00 | `weekly_rebalance` | Capital rebalancing across strategies |

```python
# signalpilot/scheduler/scheduler.py  (simplified)
jobs = [
    ("pre_market_alert", 9,  0,  app.send_pre_market_alert),
    ("start_scanning",   9,  15, app.start_scanning),
    ("stop_new_signals", 14, 30, app.stop_new_signals),
    ("exit_reminder",    15, 0,  app.trigger_exit_reminder),
    ("mandatory_exit",   15, 15, app.trigger_mandatory_exit),
    ("daily_summary",    15, 30, app.send_daily_summary),
    ("shutdown",         15, 35, app.shutdown),
]
for job_id, hour, minute, callback in jobs:
    self._scheduler.add_job(
        callback,
        CronTrigger(hour=hour, minute=minute, timezone=IST),
    )
```

Market phases are determined at runtime using `get_current_phase()`:

```python
# signalpilot/utils/market_calendar.py
class StrategyPhase(Enum):
    PRE_MARKET  = "pre_market"    # before 9:15
    OPENING     = "opening"       # 9:15 – 9:30
    ENTRY_WINDOW= "entry_window"  # 9:30 – 9:45
    CONTINUOUS  = "continuous"    # 9:45 – 14:30
    WIND_DOWN   = "wind_down"     # 14:30 – 15:30
    POST_MARKET = "post_market"   # after 15:30
```

---

## 5. Step 4 — Real-Time Data (WebSocket)

### File: `signalpilot/data/websocket_client.py`

At 9:15 AM, `app.start_scanning()` opens an Angel One WebSocket connection
and subscribes to live tick feeds for all Nifty 500 tokens.

```python
await self._websocket.connect()
self._scan_task = asyncio.create_task(self._scan_loop())
```

Each incoming tick is parsed and stored in `MarketDataStore` as a `TickData`:

```python
# signalpilot/db/models.py
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

`MarketDataStore` provides these async accessors to strategies:
- `get_tick(symbol)` → `TickData | None`
- `get_all_ticks()` → `dict[str, TickData]`
- `get_accumulated_volume(symbol)` → `int`
- `get_historical(symbol)` → `HistoricalReference | None`

---

## 6. Step 5 — Strategy Evaluation

The scan loop runs every second and calls `strategy.evaluate(market_data, phase)`.
Each strategy implements `BaseStrategy` and declares which phases it is active in.

```python
# Inside SignalPilotApp._scan_loop()
for strat in enabled_strategies:
    if phase in strat.active_phases:
        candidates = await strat.evaluate(self._market_data, phase)
        all_candidates.extend(candidates)
```

All three strategies produce `CandidateSignal` objects.

### 5a. Gap & Go Strategy

**File:** `signalpilot/strategy/gap_and_go.py`

Active phases: `OPENING` (9:15–9:30) and `ENTRY_WINDOW` (9:30–9:45).

#### Phase 1 — OPENING: Gap Detection

```python
# For each tick received:

# 1. Calculate gap %
gap_pct = (open_price - prev_close) / prev_close * 100

# 2. Filter: gap must be within [3%, 5%]
if gap_pct < 3.0 or gap_pct > 5.0:
    continue

# 3. Open must be ABOVE the previous day's high
if open_price <= prev_high:
    continue

# 4. Track as gap candidate
self._gap_candidates[symbol] = _GapCandidate(...)

# 5. Check volume immediately
volume_ratio = accumulated_volume / average_daily_volume * 100
if volume_ratio >= 50%:
    self._volume_validated.add(symbol)
```

#### Phase 2 — ENTRY_WINDOW: Signal Generation

```python
for symbol in self._volume_validated:
    tick = await market_data.get_tick(symbol)

    # Price must hold ABOVE the opening price
    if tick.ltp <= candidate.open_price:
        self._disqualified.add(symbol)   # failed to hold — skip
        continue

    # All checks passed — create CandidateSignal
    entry_price = tick.ltp
    stop_loss   = max(open_price, entry_price * (1 - max_risk_pct / 100))
    target_1    = entry_price * (1 + 5.0 / 100)   # +5%
    target_2    = entry_price * (1 + 7.0 / 100)   # +7%

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
        reason=f"Gap up {gap_pct:.1f}% above prev close ...",
    )
```

**Decision tree:**

```
Open price vs. prev_close → gap_pct in [3%, 5%]?
    └─YES → open > prev_high?
        └─YES → accumulated_volume > 50% ADV?
            └─YES → candidate stored
                 └─ (at 9:30) ltp > open_price?
                     └─YES → CandidateSignal emitted ✓
                     └─NO  → disqualified ✗
```

### 5b. ORB Strategy

**File:** `signalpilot/strategy/orb.py`

Active phases: `OPENING` (builds the 15-min opening range) and
`ENTRY_WINDOW` / `CONTINUOUS` (monitors breakouts until 11:00 AM).

```
Opening Range = [high, low] of first 15-minute candle (9:15–9:30)

Breakout signal triggers when:
  - Current price > range_high  (bullish breakout)
  - Volume at breakout > 1.5× ADV
  - Gap exclusion: stocks gapping >= 3% are excluded
  - Range size within [0.5%, 3.0%]
```

Targets and stop-loss are tighter than Gap & Go:
- Target 1: +1.5% from entry
- Target 2: +2.5% from entry
- Breakeven trigger at +1.5%
- Trailing SL at +2.0% (1.0% trail distance)

### 5c. VWAP Reversal Strategy

**File:** `signalpilot/strategy/vwap_reversal.py`

Active phase: `CONTINUOUS` (10:00 AM–2:30 PM). Scans for stocks
pulling back to or reclaiming VWAP with high volume.

Two setup types:

| Setup | Trigger | SL | T1 | T2 |
|-------|---------|----|----|-----|
| `uptrend_pullback` | Price touches VWAP from above with rising trend | Below VWAP | +1.0% | +1.5% |
| `vwap_reclaim` | Price was below VWAP, now crosses back above | Below recent low | +1.5% | +2.0% |

Rate controls:
- Max 2 VWAP signals per stock per day
- 60-minute cooldown between signals per stock (`VWAPCooldown` table)

---

## 7. Step 6 — Signal Ranking & Scoring

### Files: `signalpilot/ranking/scorer.py`, `ranker.py`

All `CandidateSignal` objects from every strategy are pooled together and
de-duplicated (by symbol, via `DuplicateChecker`), then ranked.

#### Multi-Factor Scoring

`SignalScorer` dispatches to the correct scorer per strategy:

**Gap & Go scoring** (default):

```python
# Three factors normalized to [0.0, 1.0]
norm_gap  = (gap_pct - 3.0) / 2.0          # 3% → 0.0, 5% → 1.0
norm_vol  = (volume_ratio - 0.5) / 2.5     # 0.5x → 0.0, 3x → 1.0
norm_dist = distance_from_open_pct / 3.0   # 0% → 0.0, 3%+ → 1.0

# Weighted composite
score = (norm_gap  * 0.40      # gap weight
       + norm_vol  * 0.35      # volume weight
       + norm_dist * 0.25)     # distance weight
```

**ORB scoring** (`ORBScorer`):
```python
score = (volume_ratio_norm * 0.40    # volume is most important for ORB
       + range_size_norm  * 0.30     # tighter range = better quality
       + distance_norm    * 0.30)    # distance from breakout level
```

**VWAP scoring** (`VWAPScorer`):
```python
score = (volume_ratio_norm  * 0.35   # breakout volume
       + vwap_touch_norm    * 0.35   # proximity of touch to VWAP
       + candles_above_norm * 0.30)  # trend confirmation
```

#### Ranking

```python
# signalpilot/ranking/ranker.py
class SignalRanker:
    def rank(self, candidates: list[CandidateSignal]) -> list[RankedSignal]:
        scored = [(c, self._scorer.score(c)) for c in candidates]
        scored.sort(key=lambda x: x[1], reverse=True)   # highest first

        return [
            RankedSignal(
                candidate=candidate,
                composite_score=score,
                rank=i + 1,
                signal_strength=self._score_to_stars(score),  # 1–5 stars
            )
            for i, (candidate, score) in enumerate(scored[:max_signals])
        ]

    @staticmethod
    def _score_to_stars(score: float) -> int:
        if score >= 0.8: return 5   # Very Strong
        if score >= 0.6: return 4   # Strong
        if score >= 0.4: return 3   # Moderate
        if score >= 0.2: return 2   # Fair
        return 1                    # Weak
```

The output is a list of `RankedSignal` objects, sorted by composite score.

---

## 8. Step 7 — Risk Management & Position Sizing

### Files: `signalpilot/risk/risk_manager.py`, `position_sizer.py`

#### Position Limit Check

```python
# signalpilot/risk/risk_manager.py
def filter_and_size(self, ranked_signals, user_config, active_trade_count):
    available_slots = user_config.max_positions - active_trade_count
    if available_slots <= 0:
        return []   # No room for new positions
```

#### Position Sizing

```python
# signalpilot/risk/position_sizer.py
def calculate(self, entry_price, total_capital, max_positions) -> PositionSize:
    per_trade_capital = total_capital / max_positions   # equal allocation
    quantity = int(per_trade_capital // entry_price)    # whole shares only
    capital_required = quantity * entry_price

    return PositionSize(
        quantity=quantity,
        capital_required=capital_required,
        per_trade_capital=per_trade_capital,
    )
```

**Example** with ₹50,000 capital, 8 max positions, stock at ₹1,200:

```
per_trade_capital = 50,000 / 8 = ₹6,250
quantity          = floor(6,250 / 1,200) = 5 shares
capital_required  = 5 × 1,200 = ₹6,000
```

If `quantity == 0` (stock is too expensive for the allocation), the signal is
silently skipped.

The output is a `FinalSignal`:

```python
@dataclass
class FinalSignal:
    ranked_signal: RankedSignal
    quantity: int
    capital_required: float
    expires_at: datetime          # generated_at + 30 minutes
```

---

## 9. Step 8 — Database Persistence

### File: `signalpilot/db/database.py`

SQLite with **WAL mode** and **foreign keys** enabled. Three core tables:

```sql
-- Every signal generated
CREATE TABLE signals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT,
    symbol          TEXT,
    strategy        TEXT,
    entry_price     REAL,
    stop_loss       REAL,
    target_1        REAL,
    target_2        REAL,
    quantity        INTEGER,
    capital_required REAL,
    signal_strength INTEGER,
    gap_pct         REAL,
    volume_ratio    REAL,
    reason          TEXT,
    created_at      TEXT,
    expires_at      TEXT,
    status          TEXT DEFAULT 'sent'   -- sent | taken | expired | paper
);

-- Trades the user explicitly confirmed
CREATE TABLE trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id       INTEGER REFERENCES signals(id),
    symbol          TEXT,
    entry_price     REAL,
    exit_price      REAL,
    stop_loss       REAL,
    quantity        INTEGER,
    pnl_amount      REAL,
    pnl_pct         REAL,
    exit_reason     TEXT,
    taken_at        TEXT,
    exited_at       TEXT
);

-- User preferences
CREATE TABLE user_config (
    total_capital   REAL  DEFAULT 50000.0,
    max_positions   INTEGER DEFAULT 8,
    gap_go_enabled  INTEGER DEFAULT 1,
    orb_enabled     INTEGER DEFAULT 1,
    vwap_enabled    INTEGER DEFAULT 1,
    ...
);
```

Signal status lifecycle:

```
"sent"
  ├─► "taken"          user replies TAKEN to the Telegram message
  ├─► "expired"        30 minutes elapsed without user action
  └─► "paper"          strategy is in paper-trading mode (ORB/VWAP by default)
```

After a signal is persisted:

```python
signal_id = await self._signal_repo.insert_signal(record)
record.id = signal_id
await self._bot.send_signal(signal, is_paper=is_paper)
```

---

## 10. Step 9 — Telegram Delivery

### Files: `signalpilot/telegram/bot.py`, `formatters.py`

`SignalPilotBot.send_signal()` formats the `FinalSignal` into an HTML Telegram
message and sends it to the configured `chat_id`.

#### Signal Message Format

```
BUY SIGNAL — RELIANCE

Entry Price: 2,850.00
Stop Loss:  2,764.50 (3.0% risk)
Target 1:   2,992.50 (5.0%)
Target 2:   3,049.50 (7.0%)
Quantity:   2 shares
Capital Required: 5,700
Signal Strength: ★★★★☆ (Strong)
Strategy: Gap & Go
Positions open: 1/8
Reason: Gap up 3.8% above prev close (2,742.00), ...

Valid Until: 10:05 AM (auto-expires)
==============================
Reply TAKEN to log this trade
```

Paper-trading mode adds a `PAPER TRADE` prefix so the user knows it is
a simulation (ORB and VWAP are in paper mode by default until validated).

A latency warning is logged if delivery takes more than 30 seconds from
signal generation time.

---

## 11. Step 10 — Exit Monitoring

### File: `signalpilot/monitor/exit_monitor.py`

On every scan-loop iteration, **after** strategy evaluation:

```python
# Inside SignalPilotApp._scan_loop()
active_trades = await self._trade_repo.get_active_trades()
for trade in active_trades:
    await self._exit_monitor.check_trade(trade)
```

`ExitMonitor.check_trade()` checks four conditions **in priority order**:

```
1. SL or Trailing SL hit? → ExitType.SL_HIT / TRAILING_SL_HIT
2. Target 2 hit?          → ExitType.T2_HIT (full exit)
3. Target 1 hit?          → ExitType.T1_HIT (advisory only, once per trade)
4. Trailing SL update?    → alert with updated SL value
```

#### Trailing Stop Logic (per-strategy)

```python
# Gap & Go defaults
breakeven_trigger = 2.0%   # SL moves to entry when trade is +2%
trail_trigger     = 4.0%   # trailing SL activates when trade is +4%
trail_distance    = 2.0%   # SL trails 2% below highest price

# ORB (tighter)
breakeven_trigger = 1.5%
trail_trigger     = 2.0%
trail_distance    = 1.0%

# VWAP Reversal (no trailing, breakeven only)
breakeven_trigger = 1.0%   # (1.5% for vwap_reclaim)
trail_trigger     = None
```

State per trade (`TrailingStopState`):

```python
@dataclass
class TrailingStopState:
    trade_id: int
    original_sl: float
    current_sl: float       # moves up over time, never down
    highest_price: float    # peak price seen since entry
    breakeven_triggered: bool
    trailing_active: bool
    t1_alerted: bool        # T1 advisory sent once only
```

Exit alerts trigger an immediate Telegram message:

```
STOP LOSS HIT — RELIANCE
Stop Loss hit at 2,764.50. Exit immediately.
P&L: -3.0%
```

---

## 12. Step 11 — Telegram Commands (User Interaction)

### File: `signalpilot/telegram/handlers.py`

The bot listens for text messages in the configured chat and dispatches to
handler functions. All commands are restricted to the configured `chat_id`.

| Command | Pattern | Action |
|---------|---------|--------|
| `TAKEN` | `^taken$` | Mark most-recent "sent" signal as a trade |
| `STATUS` | `^status$` | Show active signals and open positions with live P&L |
| `JOURNAL` | `^journal$` | Display 30-day win rate, P&L, risk-reward stats |
| `CAPITAL <amount>` | `^capital \d+` | Update total trading capital |
| `PAUSE <strategy>` | `^pause \w+` | Disable a strategy (Gap & Go/ORB/VWAP) |
| `RESUME <strategy>` | `^resume \w+` | Re-enable a paused strategy |
| `ALLOCATE` | `^allocate` | Show current capital allocation per strategy |
| `STRATEGY` | `^strategy$` | Show 30-day per-strategy performance breakdown |
| `HELP` | `^help$` | List all commands |

#### TAKEN flow

```python
# handle_taken() in handlers.py
signal = await signal_repo.get_latest_sent_signal()   # most recent unactioned signal
if signal:
    trade = TradeRecord(
        signal_id=signal.id,
        symbol=signal.symbol,
        entry_price=signal.entry_price,
        stop_loss=signal.stop_loss,
        ...
        taken_at=datetime.now(IST),
    )
    trade_id = await trade_repo.insert_trade(trade)
    await signal_repo.update_status(signal.id, "taken")
    exit_monitor.start_monitoring(trade)              # begin tick-by-tick monitoring
    return f"Trade logged: {signal.symbol} @ {signal.entry_price}"
```

Once `start_monitoring()` is called, `TrailingStopState` is initialised for
the trade and it enters the exit-monitoring loop on every subsequent tick.

---

## 13. Step 12 — Daily Wind-Down & Summary

### Wind-Down Phase (14:30–15:30)

| Time | Event |
|------|-------|
| 14:30 | `stop_new_signals()` — scan loop still runs for exit monitoring, but no new signals emitted |
| 15:00 | `trigger_exit_reminder()` — sends advisory for each open trade with unrealized P&L |
| 15:15 | `trigger_mandatory_exit()` — sends forced-exit alert for all remaining open trades |
| 15:30 | `send_daily_summary()` — calculates metrics and sends the daily report |

#### Daily Summary Format

```
Daily Summary — 2026-02-23

Signals Generated: 6
Trades Taken: 3
Wins: 2 | Losses: 1
Today's P&L: +4,500
Cumulative P&L: +28,300

BY STRATEGY
  📈 Gap & Go: 4 signals, 2 taken, P&L +4,500
  📊 ORB: 2 signals, 1 taken, P&L 0 (paper)

Trade Details
  RELIANCE: t2_hit | P&L: +3,200
  INFY: sl_hit | P&L: -1,500
  TCS: t1_hit | P&L: +2,800
```

---

## 14. Step 13 — Shutdown & Crash Recovery

### Graceful Shutdown

At 15:35 IST (or on `SIGINT`/`SIGTERM`):

```python
async def shutdown(self):
    self._scanning = False
    self._scan_task.cancel()

    await self._websocket.disconnect()
    await self._bot.stop()
    await self._db.close()
    self._scheduler.shutdown()
```

### Crash Recovery

If the process restarts during market hours, `recover()` runs instead of
`startup()`:

```python
async def recover(self):
    await self._db.initialize()
    await self._authenticator.authenticate()          # re-auth
    await self._instruments.load()

    # Reload active trades from DB — no data is lost
    active_trades = await self._trade_repo.get_active_trades()
    for trade in active_trades:
        self._exit_monitor.start_monitoring(trade)    # resume monitoring

    await self._bot.send_alert("System recovered. Monitoring resumed.")
    self._scheduler.configure_jobs(self)
    self._scheduler.start()
    await self.start_scanning()

    # Honour time: if recovery is after entry window, block new signals
    if phase not in (OPENING, ENTRY_WINDOW):
        self._accepting_signals = False
```

---

## 15. Data Model Chain

The journey of a signal from detection to database:

```
TickData (WebSocket)
    │
    ▼
CandidateSignal          ← produced by GapAndGoStrategy / ORBStrategy / VWAPReversal
    │ symbol, direction, entry, SL, T1, T2, gap_pct, volume_ratio
    ▼
RankedSignal             ← produced by SignalRanker
    │ candidate, composite_score, rank (1-N), signal_strength (1-5 stars)
    ▼
FinalSignal              ← produced by RiskManager
    │ ranked_signal, quantity, capital_required, expires_at
    ▼
SignalRecord             ← persisted to `signals` table
    │ id, date, symbol, strategy, entry_price, stop_loss, T1, T2,
    │ quantity, capital_required, signal_strength, gap_pct, volume_ratio,
    │ reason, created_at, expires_at, status="sent"
    ▼
TradeRecord              ← created when user replies TAKEN
    │ signal_id, entry_price, stop_loss, T1, T2, quantity,
    │ taken_at, exit_price, pnl_amount, pnl_pct, exit_reason, exited_at
```

---

## 16. Logging & Observability

### File: `signalpilot/utils/logger.py`, `log_context.py`

Every log record is enriched with async-safe context fields via `contextvars`:

```python
# Set context at the start of each scan cycle
set_context(cycle_id="a3f9b2c1", phase="entry_window")

# Or use the async context manager
async with log_context(symbol="RELIANCE"):
    ...
```

Custom fields injected into each log line:

| Field | Example | Set by |
|-------|---------|--------|
| `cycle_id` | `a3f9b2c1` | `_scan_loop()` — unique per second |
| `phase` | `entry_window` | `_scan_loop()` from `get_current_phase()` |
| `symbol` | `RELIANCE` | Strategy evaluation, exit monitor |
| `job_name` | `start_scanning` | Scheduler job callbacks |
| `command` | `TAKEN` | Telegram command handlers |

Log files rotate daily with a 7-day retention window (`TimedRotatingFileHandler`).
Logs are stored at `log/signalpilot.log` by default.

```
# Example structured log line
2026-02-23 09:31:05 INFO [cycle=a3f9b2c1 phase=entry_window symbol=RELIANCE]
  Signal generated: RELIANCE entry=2850.00 SL=2764.50 T1=2992.50 T2=3049.50
```

### Circuit Breaker

If the scan loop encounters 10 consecutive errors without recovery, it
self-terminates and sends a Telegram alert:

```python
if consecutive_errors >= self._max_consecutive_errors:
    self._scanning = False
    await self._bot.send_alert(
        "ALERT: Scan loop stopped due to repeated errors. "
        "Manual intervention required."
    )
```

---

## Summary: A Complete Trading Day

```
08:00  App boots → AppConfig loaded, logging configured
08:00  historical.fetch_previous_day_data()    ← 499 stocks, batched
08:10  historical.fetch_average_daily_volume() ← 20-day ADV
08:15  MarketScheduler.start()
08:15  bot.start() → Telegram polling begins

09:00  [CRON] send_pre_market_alert()
09:15  [CRON] start_scanning()
         │   websocket.connect()
         └─► _scan_loop() starts (every 1 second)
               ├─ phase = OPENING (9:15–9:30)
               │    └─ GapAndGoStrategy: detect gaps, accumulate volume
               ├─ phase = ENTRY_WINDOW (9:30–9:45)
               │    └─ GapAndGoStrategy: validate price hold → CandidateSignal
               │    └─ ORBStrategy: detect breakouts → CandidateSignal
               ├─ SignalRanker: score + rank candidates → RankedSignal list
               ├─ RiskManager: apply position limits + size → FinalSignal list
               ├─ SignalRepo: INSERT INTO signals
               ├─ Bot: send_signal() → Telegram HTML message
               │
               └─ (every tick, all phases 9:15–15:15)
                    ExitMonitor.check_trade() for each active trade:
                      ├─ SL hit?  → alert + stop monitoring
                      ├─ T2 hit?  → alert + stop monitoring
                      ├─ T1 hit?  → advisory alert (once)
                      └─ Trailing SL update? → alert

               [CONTINUOUS 9:45–14:30]
               └─ VWAPReversal: scan for VWAP touches → CandidateSignal

14:30  [CRON] stop_new_signals()
15:00  [CRON] trigger_exit_reminder()  → advisory alerts per open trade
15:15  [CRON] trigger_mandatory_exit() → forced exit alerts
15:30  [CRON] send_daily_summary()     → P&L report to Telegram
15:35  [CRON] shutdown()               → graceful teardown
```
