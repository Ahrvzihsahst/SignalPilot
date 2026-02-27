# SignalPilot

SignalPilot is a pure intraday signal generation tool for Indian equity markets (NSE). It scans Nifty 500 stocks during market hours, identifies high-probability trade setups using predefined technical strategies, and delivers actionable buy/sell signals via Telegram — complete with entry price, stop loss, target, and quantity.

## Features

- **Gap & Go Strategy** — detects stocks gapping up 3-5% at market open with strong volume confirmation
- **Multi-factor Signal Ranking** — scores candidates by gap %, volume ratio, and price distance; selects top 5 with 1-5 star ratings
- **Risk Management** — automatic position sizing, max 5 concurrent positions, per-trade capital allocation
- **Telegram Bot** — real-time signal delivery, interactive commands (TAKEN, STATUS, JOURNAL, CAPITAL, HELP)
- **Exit Monitoring** — stop loss, Target 1 (5%), Target 2 (7%), trailing stop loss, time-based exits
- **Trade Journal** — SQLite-backed logging with win rate, P&L, and risk-reward metrics
- **Market-Aware Scheduling** — automated lifecycle from 9:00 AM pre-market scan to 3:35 PM shutdown (IST)
- **Crash Recovery** — reloads active trades from database and resumes monitoring on restart


## Prerequisites

- Python 3.11+
- [Angel One SmartAPI](https://smartapi.angelone.in/) account with API credentials
- Telegram bot (created via [@BotFather](https://t.me/BotFather))

## Setup

```bash
# Clone the repository
git clone https://github.com/your-username/SignalPilot.git
cd SignalPilot

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"

# Configure environment
cp .env.example .env
# Edit .env with your Angel One and Telegram credentials
```

## Configuration

All configuration is loaded from environment variables or a `.env` file. See [`.env.example`](.env.example) for the full list.

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
| `DEFAULT_MAX_POSITIONS` | `5` | Max simultaneous positions |
| `GAP_MIN_PCT` | `3.0` | Minimum gap % for Gap & Go |
| `GAP_MAX_PCT` | `5.0` | Maximum gap % |
| `VOLUME_THRESHOLD_PCT` | `50.0` | 15-min volume as % of 20-day ADV |
| `TARGET_1_PCT` | `5.0` | Target 1 from entry |
| `TARGET_2_PCT` | `7.0` | Target 2 from entry |
| `SIGNAL_EXPIRY_MINUTES` | `30` | Signal validity window |

## Usage

```bash
# Run the application
python -m signalpilot.main

To run SignalPilot continuously on EC2 (so it survives SSH disconnection), you have a few options:
# Simplest: nohup + background
```bash
nohup python -m signalpilot.main > log/signalpilot.log 2>&1 &


This keeps the process running after you close your terminal. Check it with ps aux | grep signalpilot.

SignalPilot runs autonomously during market hours:

| Time (IST) | Event |
|---|---|
| 9:00 AM | Pre-market alert sent via Telegram |
| 9:15 AM | Market opens — scanning begins, gap detection starts |
| 9:30 - 9:45 AM | Entry window — signals generated and delivered |
| 9:45 AM - 2:30 PM | Monitoring — exit logic active, no new signals |
| 2:30 PM | Signal generation stops |
| 3:00 PM | Exit reminder for open trades |
| 3:15 PM | Mandatory exit for all open positions |
| 3:30 PM | Daily summary sent |
| 3:35 PM | Graceful shutdown |

### Telegram Commands

| Command | Description |
|---|---|
| `TAKEN` | Mark the latest signal as taken — starts exit monitoring |
| `STATUS` | View active trades with current P&L |
| `JOURNAL` | Performance summary (win rate, total P&L, best/worst trades) |
| `CAPITAL 75000` | Update trading capital |
| `HELP` | List available commands |

## Architecture

```
signalpilot/
├── config.py           # Pydantic settings (env vars / .env)
├── main.py             # Entry point and signal handling
├── data/               # Data engine (Angel One auth, WebSocket, historical)
├── strategy/           # Gap & Go strategy implementation
├── ranking/            # Multi-factor signal scoring and ranking
├── risk/               # Position sizing and trade filtering
├── monitor/            # Exit monitoring (SL, targets, trailing SL)
├── telegram/           # Bot, message formatters, command handlers
├── db/                 # SQLite database, repositories, metrics
│   └── models.py       # Dataclass contracts between all components
├── scheduler/          # APScheduler jobs and lifecycle orchestrator
└── utils/              # Constants (IST), market calendar, retry, logger
```

**Signal pipeline:** Data Engine &rarr; Strategy Engine &rarr; Signal Ranker &rarr; Risk Manager &rarr; Telegram Bot &rarr; Exit Monitor

All components are dependency-injected into `SignalPilotApp` (the central orchestrator), enabling isolated testing and modular development.

## Development

```bash
# Run all tests
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

# What It Does

SignalPilot is an automated intraday trading signal engine for NSE (Indian markets). It scans the Nifty 500 universe during market hours, detects trade
setups, sizes positions, and delivers buy/sell signals via Telegram with entry, stop-loss, and targets.

---
Component Map

main.py (entry point)
└─ create_app()          — wires all 16 components via DI
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
            │    ├─ SignalScorer            — multi-factor score (gap%, volume ratio, price distance)
            │    └─ SignalRanker            — top-N selection, 1–5 star rating
            ├─ Risk Layer
            │    ├─ PositionSizer           — per-trade capital / qty
            │    └─ RiskManager            — max positions, capital gate
            ├─ Database Layer (SQLite/aiosqlite)
            │    ├─ SignalRepository        — signals table CRUD
            │    ├─ TradeRepository         — trades table CRUD
            │    ├─ ConfigRepository        — user_config table
            │    └─ MetricsCalculator       — aggregated P&L stats
            ├─ ExitMonitor                 — SL/target/trailing-SL/time exits
            └─ SignalPilotBot (Telegram)   — delivers signals & handles commands

---
Data Flow (per scan cycle, every second)

WebSocket tick → MarketDataStore (in-memory)
                        ↓
            Strategy.evaluate()      ← reads ticks + historical refs
                        ↓
            CandidateSignal[]
                        ↓
            DuplicateChecker         ← filters already-signalled symbols
                        ↓
            SignalRanker.rank()      → RankedSignal[] (scored, sorted, starred)
                        ↓
            RiskManager.filter_and_size() → FinalSignal[] (qty + capital)
                        ↓
            SignalRepository.insert()   ← persists to SQLite
                        ↓
            TelegramBot.send_signal()  ← delivers to user

In every cycle (even when not generating new signals), it also:
- Iterates active trades → ExitMonitor.check_trade() (SL/target/trailing-SL checks)
- Expires stale signals older than 30 min

---
Scheduling (IST cron jobs)

┌───────┬─────────────────────────────────────────────────────────┐
│ Time  │                         Action                          │
├───────┼─────────────────────────────────────────────────────────┤
│ 9:00  │ Pre-market alert                                        │
├───────┼─────────────────────────────────────────────────────────┤
│ 9:15  │ start_scanning() — WebSocket connects, scan loop begins │
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

---
Market Phases (StrategyPhase enum)

┌──────────────┬─────────────┬────────────────────────────────────┐
│    Phase     │   Window    │            What happens            │
├──────────────┼─────────────┼────────────────────────────────────┤
│ OPENING      │ 9:15–9:30   │ Gap detection, volume accumulation │
├──────────────┼─────────────┼────────────────────────────────────┤
│ ENTRY_WINDOW │ 9:30–9:45   │ Signal generation active           │
├──────────────┼─────────────┼────────────────────────────────────┤
│ CONTINUOUS   │ 9:45–14:30  │ Exit monitoring only               │
├──────────────┼─────────────┼────────────────────────────────────┤
│ WIND_DOWN    │ 14:30–15:30 │ Mandatory close reminders          │
└──────────────┴─────────────┴────────────────────────────────────┘

Each strategy declares its own active_phases — only called when the market is in the right phase.

---
Data Models (the inter-component contract)

All components talk via typed dataclasses in db/models.py:

CandidateSignal   ← produced by Strategy
    ↓
RankedSignal      ← produced by SignalRanker (adds score, rank, stars)
    ↓
FinalSignal       ← produced by RiskManager (adds qty, capital, expiry)
    ↓
SignalRecord      ← persisted to SQLite signals table
TradeRecord       ← persisted when user confirms via TAKEN command

---
Key Design Patterns

- Dependency injection — SignalPilotApp takes all 16 components as keyword-only constructor args, enabling full mockability in tests
- Async-first — everything is async def with aiosqlite and asyncio
- Repository pattern — DB tables hidden behind SignalRepository, TradeRepository, etc.
- Startup vs Recovery — if launched during market hours, recover() re-authenticates and restores active trades; otherwise startup() runs fresh
- Paper trading — Phase 2 strategies (ORB, VWAP) default to paper mode; signals are marked "paper" in DB and annotated in Telegram

---
Strategies (Phase 1 + Phase 2)

┌───────────────┬───────────────────────────┬───────────────────────────────────────────────────────────────────────┐
│   Strategy    │           File            │                                 Logic                                 │
├───────────────┼───────────────────────────┼───────────────────────────────────────────────────────────────────────┤
│ Gap & Go      │ strategy/gap_and_go.py    │ Detects stocks gapping >1% at open with 2x+ volume                    │
├───────────────┼───────────────────────────┼───────────────────────────────────────────────────────────────────────┤
│ ORB           │ strategy/orb.py           │ Opening range breakout — price breaks high/low of first 15 min candle │
├───────────────┼───────────────────────────┼───────────────────────────────────────────────────────────────────────┤
│ VWAP Reversal │ strategy/vwap_reversal.py │ Mean-reversion trade when price bounces off VWAP                      │
└───────────────┴───────────────────────────┴───────────────────────────────────────────────────────────────────────┘

All extend strategy/base.py and must implement evaluate(market_data, phase) → list[CandidateSignal].
## License

This project is for personal use. All rights reserved.
