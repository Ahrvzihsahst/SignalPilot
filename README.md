# SignalPilot

SignalPilot is a pure intraday signal generation tool for Indian equity markets (NSE). It scans Nifty 500 stocks during market hours, identifies high-probability trade setups using three technical strategies (Gap & Go, ORB, VWAP Reversal), and delivers actionable buy/sell signals via Telegram — complete with entry price, stop loss, target, and quantity. A web dashboard provides real-time visibility into signals, trades, and strategy performance.

## Features

- **Gap & Go Strategy** — detects stocks gapping up 3-5% at market open with strong volume confirmation
- **ORB Strategy** — opening range breakout detection after the first 30-minute candle is locked (9:45-11:00)
- **VWAP Reversal Strategy** — mean-reversion trades when price bounces off VWAP (from 10:00)
- **Multi-Strategy Confirmation** — detects when 2-3 strategies agree on the same stock within 15 minutes (single/double/triple confirmation)
- **Composite Hybrid Scoring** — 4-factor scoring: strategy strength (40%), win rate (30%), risk-reward (20%), confirmation bonus (10%)
- **Multi-factor Signal Ranking** — composite 4-factor scoring with strategy-specific and cross-strategy confirmation; selects top 5 with 1-5 star ratings
- **Risk Management** — automatic position sizing, max 8 concurrent positions, confirmation-based position sizing multipliers (1.0x/1.5x/2.0x), per-trade capital allocation with caps (20%/25%)
- **Circuit Breaker** — halts signal generation after N stop-losses in a day, with manual override via Telegram or dashboard
- **Adaptive Strategy Management** — automatically throttles or pauses underperforming strategies (NORMAL -> REDUCED -> PAUSED)
- **Telegram Bot** — real-time signal delivery with 13 interactive commands (TAKEN, STATUS, JOURNAL, CAPITAL, PAUSE, RESUME, ALLOCATE, STRATEGY, OVERRIDE, SCORE, ADAPT, REBALANCE, HELP)
- **Web Dashboard** — React + TypeScript + Tailwind dashboard with live signals, trade journal, performance charts, strategy comparison, capital allocation, and settings pages
- **Exit Monitoring** — stop loss, Target 1 (5%), Target 2 (7%), trailing stop loss, time-based exits
- **Trade Journal** — SQLite-backed logging with win rate, P&L, and risk-reward metrics
- **Market-Aware Scheduling** — automated lifecycle from 9:00 AM pre-market scan to 3:35 PM shutdown (IST), with NSE holiday awareness
- **Crash Recovery** — reloads active trades from database and resumes monitoring on restart


## Prerequisites

- Python 3.11+
- Node.js 18+ (for the web dashboard)
- [Angel One SmartAPI](https://smartapi.angelone.in/) account with API credentials
- Telegram bot (created via [@BotFather](https://t.me/BotFather))

## Setup

```bash
# Clone the repository
git clone https://github.com/your-username/SignalPilot.git
cd SignalPilot

# Set up the backend
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Configure environment
cp .env.example .env
# Edit .env with your Angel One and Telegram credentials

# (Optional) Install dashboard frontend
cd ../frontend
npm install
npm run build
```

## Configuration

All configuration is loaded from environment variables or a `.env` file. See [`backend/.env.example`](backend/.env.example) for the full list.

**Required:**

| Variable | Description |
|---|---|
| `ANGEL_API_KEY` | Angel One SmartAPI key |
| `ANGEL_CLIENT_ID` | Angel One client ID |
| `ANGEL_MPIN` | Angel One MPIN |
| `ANGEL_TOTP_SECRET` | TOTP secret for 2FA (32 chars) |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API token |
| `TELEGRAM_CHAT_ID` | Telegram chat ID for signal delivery |

**Optional (with sensible defaults):**

| Variable | Default | Description |
|---|---|---|
| `DB_PATH` | `signalpilot.db` | SQLite database path |
| `DEFAULT_CAPITAL` | `50000` | Trading capital (INR) |
| `DEFAULT_MAX_POSITIONS` | `8` | Max simultaneous positions |
| `GAP_MIN_PCT` | `3.0` | Minimum gap % for Gap & Go |
| `GAP_MAX_PCT` | `5.0` | Maximum gap % |
| `VOLUME_THRESHOLD_PCT` | `50.0` | 15-min volume as % of 20-day ADV |
| `TARGET_1_PCT` | `5.0` | Target 1 from entry |
| `TARGET_2_PCT` | `7.0` | Target 2 from entry |
| `SIGNAL_EXPIRY_MINUTES` | `30` | Signal validity window |

**Phase 3 — Scoring, Confirmation, and Intelligence:**

| Variable | Default | Description |
|---|---|---|
| `COMPOSITE_WEIGHT_STRATEGY` | `0.4` | Strategy strength weight in composite score |
| `COMPOSITE_WEIGHT_WIN_RATE` | `0.3` | Win rate weight |
| `COMPOSITE_WEIGHT_RISK_REWARD` | `0.2` | Risk-reward weight |
| `COMPOSITE_WEIGHT_CONFIRMATION` | `0.1` | Confirmation bonus weight |
| `CONFIRMATION_WINDOW_MINUTES` | `15` | Window for cross-strategy confirmation |
| `CIRCUIT_BREAKER_SL_LIMIT` | `3` | SL hits before circuit breaker triggers |
| `ADAPTIVE_CONSECUTIVE_LOSS_THROTTLE` | `3` | Losses before throttling strategy |
| `ADAPTIVE_CONSECUTIVE_LOSS_PAUSE` | `5` | Losses before pausing strategy |
| `CONFIRMED_DOUBLE_CAP_PCT` | `20.0` | Max capital % for double-confirmed signals |
| `CONFIRMED_TRIPLE_CAP_PCT` | `25.0` | Max capital % for triple-confirmed signals |
| `DASHBOARD_ENABLED` | `true` | Enable/disable web dashboard |
| `DASHBOARD_PORT` | `8000` | Dashboard server port |
| `DASHBOARD_HOST` | `127.0.0.1` | Dashboard bind address |

## Usage

```bash
# Run the application (from backend/ directory)
cd backend
python -m signalpilot.main
```

To run SignalPilot continuously on EC2 (so it survives SSH disconnection):

```bash
# Simplest: nohup + background (from backend/ directory)
cd backend
nohup python -m signalpilot.main > logs/signalpilot.log 2>&1 &
```

This keeps the process running after you close your terminal. Check it with `ps aux | grep signalpilot`.

SignalPilot runs autonomously during market hours:

| Time (IST) | Event |
|---|---|
| 9:00 AM | Pre-market alert sent via Telegram |
| 9:15 AM | Market opens — scanning begins, gap detection starts |
| 9:30 - 9:45 AM | Entry window — Gap & Go signals generated and delivered; ORB range continues building |
| 9:45 AM - 2:30 PM | ORB breakout signals (until 11:00), VWAP Reversal signals (from 10:00), multi-strategy confirmation detection, exit monitoring |
| 2:30 PM | Signal generation stops |
| 3:00 PM | Exit reminder for open trades |
| 3:15 PM | Mandatory exit for all open positions |
| 3:30 PM | Daily summary sent |
| 3:35 PM | Graceful shutdown |

### Telegram Commands

| Command | Description |
|---|---|
| `TAKEN` or `TAKEN 5` | Mark latest (or specific signal ID) as taken -- starts exit monitoring |
| `STATUS` | View active trades with current P&L + circuit breaker status |
| `JOURNAL` | Performance summary with per-strategy breakdown |
| `CAPITAL 75000` | Update trading capital |
| `PAUSE GAP` | Pause a strategy (GAP/ORB/VWAP) |
| `RESUME GAP` | Resume a paused strategy |
| `ALLOCATE` | View/set capital allocation (AUTO or manual percentages) |
| `STRATEGY` | 30-day per-strategy performance breakdown |
| `OVERRIDE` | Override active circuit breaker to resume signals |
| `SCORE SBIN` | Show composite score breakdown for a symbol |
| `ADAPT` | View adaptive strategy status (normal/throttled/paused) |
| `REBALANCE` | Trigger immediate capital rebalance |
| `HELP` | List all available commands |

## Architecture

```
backend/
├── signalpilot/
│   ├── config.py             # Pydantic settings (env vars / .env)
│   ├── main.py               # Entry point and signal handling
│   ├── data/                 # Data engine (Angel One auth, WebSocket, historical)
│   ├── strategy/             # Gap & Go, ORB, VWAP Reversal implementations
│   ├── ranking/              # Multi-factor scoring, composite scorer, confirmation detector
│   ├── risk/                 # Position sizing, capital allocation, risk filtering
│   ├── monitor/              # Exit monitor, circuit breaker, adaptive manager, duplicate checker
│   ├── telegram/             # Bot, message formatters, command handlers
│   ├── db/                   # SQLite database, repositories, metrics
│   │   └── models.py         # Dataclass contracts between all components
│   ├── scheduler/            # APScheduler jobs and lifecycle orchestrator
│   ├── dashboard/            # FastAPI dashboard API + Pydantic schemas
│   └── utils/                # Constants (IST), market calendar, retry, logger
├── tests/                    # Python test suite
├── data/                     # CSV data files (nifty500_list.csv)
└── pyproject.toml

frontend/                     # React + TypeScript frontend (Vite, Tailwind, React Query)
├── src/
│   ├── pages/                # LiveSignals, TradeJournal, PerformanceCharts,
│   │                         # StrategyComparison, CapitalAllocation, Settings
│   ├── components/           # Shared UI components
│   ├── api/                  # API client hooks
│   └── types/                # TypeScript type definitions
└── vite.config.ts
```

**Signal pipeline:**

Data Engine &rarr; Strategy Engine &rarr; Confirmation Detector &rarr; Composite Scorer &rarr; Duplicate Checker &rarr; Signal Ranker &rarr; Circuit Breaker Gate &rarr; Adaptive Filter &rarr; Risk Manager &rarr; Telegram Bot &rarr; Exit Monitor &rarr; Dashboard

All components are dependency-injected into `SignalPilotApp` (the central orchestrator), enabling isolated testing and modular development.

## Development

All development commands should be run from the `backend/` directory:

```bash
cd backend

# Run all tests (1060+ tests)
pytest tests/

# Run a specific test file
pytest tests/test_db/test_signal_repo.py -v

# Run a single test
pytest tests/test_db/test_signal_repo.py::test_insert_and_retrieve_signal -v

# Coverage
pytest --cov=signalpilot tests/

# Lint
ruff check signalpilot/ tests/

# Type check
mypy signalpilot/
```

## How It Works

### What It Does

SignalPilot is an automated intraday trading signal engine for NSE (Indian markets). It scans the Nifty 500 universe during market hours, detects trade setups across three strategies, sizes positions with confirmation-based multipliers, and delivers buy/sell signals via Telegram with entry, stop-loss, and targets. A web dashboard provides live visibility into all signals, trades, and performance metrics.

---

### Component Map

```
main.py (entry point)
└─ create_app()          — wires all components via DI
        └─ SignalPilotApp   — central orchestrator (lifecycle.py)
            ├─ MarketScheduler   — APScheduler cron jobs (scheduler.py)
            ├─ Data Layer
            │    ├─ SmartAPIAuthenticator   — Angel One OAuth
            │    ├─ InstrumentManager       — Nifty 500 CSV → Instrument list
            │    ├─ WebSocketClient         — real-time tick feed
            │    ├─ MarketDataStore         — in-memory tick cache (symbol → TickData)
            │    └─ HistoricalDataFetcher   — prev-day OHLCV + avg volume
            ├─ Strategy Layer
            │    ├─ GapAndGoStrategy        — Phase 1 gap + volume detection
            │    ├─ ORBStrategy             — Phase 2 opening range breakout
            │    └─ VWAPReversalStrategy    — Phase 2 VWAP mean-reversion
            ├─ Ranking Layer
            │    ├─ ConfidenceDetector      — multi-strategy confirmation (single/double/triple)
            │    ├─ CompositeScorer         — 4-factor hybrid scoring
            │    ├─ SignalScorer            — per-strategy factor scoring
            │    └─ SignalRanker            — top-N selection, 1–5 star rating
            ├─ Intelligence Layer
            │    ├─ CircuitBreaker          — halt signals after N SL hits/day
            │    └─ AdaptiveManager         — throttle/pause underperforming strategies
            ├─ Risk Layer
            │    ├─ PositionSizer           — per-trade capital / qty
            │    ├─ CapitalAllocator        — strategy-level capital allocation
            │    └─ RiskManager             — max positions, capital gate, confirmation sizing
            ├─ Database Layer (SQLite/aiosqlite)
            │    ├─ SignalRepository            — signals table CRUD
            │    ├─ TradeRepository             — trades table CRUD
            │    ├─ ConfigRepository            — user_config table
            │    ├─ MetricsCalculator           — aggregated P&L stats
            │    ├─ HybridScoreRepository       — hybrid_scores table
            │    ├─ CircuitBreakerRepository    — circuit_breaker_log table
            │    ├─ AdaptationLogRepository     — adaptation_log table
            │    └─ StrategyPerformanceRepository — strategy performance tracking
            ├─ ExitMonitor                 — SL/target/trailing-SL/time exits
            ├─ SignalPilotBot (Telegram)   — delivers signals & handles 13 commands
            └─ Dashboard
                 ├─ FastAPI backend        — REST API (signalpilot/dashboard/)
                 └─ React frontend         — Vite + Tailwind (frontend/)
```

---

### Data Flow (per scan cycle, every second)

```
WebSocket tick → MarketDataStore (in-memory)
                        ↓
            Strategy.evaluate()      ← reads ticks + historical refs
                        ↓
            CandidateSignal[]
                        ↓
            ConfidenceDetector       ← detects multi-strategy agreement
                        ↓
            CompositeScorer          ← 4-factor hybrid score
                        ↓
            DuplicateChecker         ← filters already-signalled symbols
                        ↓
            SignalRanker.rank()      → RankedSignal[] (scored, sorted, starred)
                        ↓
            CircuitBreaker.check()   ← blocks if SL limit hit
                        ↓
            AdaptiveManager.filter() ← removes paused/throttled strategy signals
                        ↓
            RiskManager.filter_and_size() → FinalSignal[] (qty + capital)
                        ↓
            SignalRepository.insert()   ← persists to SQLite
                        ↓
            TelegramBot.send_signal()  ← delivers to user
                        ↓
            Dashboard (live update)    ← visible on web UI
```

In every cycle (even when not generating new signals), it also:
- Iterates active trades via ExitMonitor.check_trade() (SL/target/trailing-SL checks)
- Expires stale signals older than 30 min

---

### Scheduling (IST cron jobs)

```
┌───────┬─────────────────────────────────────────────────────────┐
│ Time  │                         Action                          │
├───────┼─────────────────────────────────────────────────────────┤
│ 9:00  │ Pre-market alert                                        │
├───────┼─────────────────────────────────────────────────────────┤
│ 9:15  │ start_scanning() — WebSocket connects, scan loop begins │
├───────┼─────────────────────────────────────────────────────────┤
│ 9:45  │ lock_opening_range() — ORB range finalized              │
├───────┼─────────────────────────────────────────────────────────┤
│ 14:30 │ stop_new_signals() — no more entries                    │
├───────┼─────────────────────────────────────────────────────────┤
│ 15:00 │ Exit reminder to user                                   │
├───────┼─────────────────────────────────────────────────────────┤
│ 15:15 │ Mandatory exit trigger                                  │
├───────┼─────────────────────────────────────────────────────────┤
│ 15:30 │ Daily summary (P&L, wins/losses) sent via Telegram      │
├───────┼─────────────────────────────────────────────────────────┤
│ 15:35 │ Shutdown                                                │
└───────┴─────────────────────────────────────────────────────────┘
```

All weekday jobs use `day_of_week='mon-fri'` and a `_trading_day_guard` that skips execution on NSE holidays.

---

### Market Phases (StrategyPhase enum)

```
┌──────────────┬─────────────┬─────────────────────────────────────────────────────────────────┐
│    Phase     │   Window    │                         What happens                            │
├──────────────┼─────────────┼─────────────────────────────────────────────────────────────────┤
│ OPENING      │ 9:15–9:30   │ Gap detection, volume accumulation, ORB range building          │
├──────────────┼─────────────┼─────────────────────────────────────────────────────────────────┤
│ ENTRY_WINDOW │ 9:30–9:45   │ Gap & Go signal generation, ORB range continues                 │
├──────────────┼─────────────┼─────────────────────────────────────────────────────────────────┤
│ CONTINUOUS   │ 9:45–14:30  │ ORB breakouts (until 11:00), VWAP reversals (from 10:00),       │
│              │             │ multi-strategy confirmation, exit monitoring                     │
├──────────────┼─────────────┼─────────────────────────────────────────────────────────────────┤
│ WIND_DOWN    │ 14:30–15:30 │ No new signals, mandatory close reminders, exit monitoring only  │
└──────────────┴─────────────┴─────────────────────────────────────────────────────────────────┘
```

Each strategy declares its own `active_phases` — only called when the market is in the right phase.

---

### Data Models (the inter-component contract)

All components talk via typed dataclasses in `db/models.py`:

```
CandidateSignal   ← produced by Strategy
    ↓
RankedSignal      ← produced by SignalRanker (adds score, rank, stars)
    ↓
FinalSignal       ← produced by RiskManager (adds qty, capital, expiry)
    ↓
SignalRecord      ← persisted to SQLite signals table
TradeRecord       ← persisted when user confirms via TAKEN command
```

---

### Key Design Patterns

- **Dependency injection** — `SignalPilotApp` takes all components as keyword-only constructor args, enabling full mockability in tests
- **Async-first** — everything is `async def` with `aiosqlite` and `asyncio`
- **Repository pattern** — DB tables hidden behind `SignalRepository`, `TradeRepository`, `HybridScoreRepository`, etc.
- **Startup vs Recovery** — if launched during market hours, `recover()` re-authenticates and restores active trades; otherwise `startup()` runs fresh
- **Paper trading** — Phase 2 strategies (ORB, VWAP) default to paper mode; signals are marked "paper" in DB and annotated in Telegram
- **Confirmation-based sizing** — position size multiplied by 1.0x (single), 1.5x (double), or 2.0x (triple confirmation), with per-tier capital caps
- **Circuit breaker** — halts all signal generation after N stop-losses in a day; resumes next day or via manual OVERRIDE command
- **Adaptive management** — strategies transition through NORMAL -> REDUCED -> PAUSED based on consecutive loss streaks

---

### Strategies (Phase 1 + Phase 2 + Phase 3 Intelligence)

```
┌───────────────┬───────────────────────────┬───────────────────────────────────────────────────────────────────────┐
│   Strategy    │           File            │                                 Logic                                 │
├───────────────┼───────────────────────────┼───────────────────────────────────────────────────────────────────────┤
│ Gap & Go      │ strategy/gap_and_go.py    │ Detects stocks gapping >1% at open with 2x+ volume                    │
├───────────────┼───────────────────────────┼───────────────────────────────────────────────────────────────────────┤
│ ORB           │ strategy/orb.py           │ Opening range breakout — price breaks high/low of first 30-min candle │
├───────────────┼───────────────────────────┼───────────────────────────────────────────────────────────────────────┤
│ VWAP Reversal │ strategy/vwap_reversal.py │ Mean-reversion trade when price bounces off VWAP                      │
└───────────────┴───────────────────────────┴───────────────────────────────────────────────────────────────────────┘
```

All extend `strategy/base.py` and must implement `evaluate(market_data, phase) -> list[CandidateSignal]`.

## License

This project is for personal use. All rights reserved.
