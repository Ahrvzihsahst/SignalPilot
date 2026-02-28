# SignalPilot — End-to-End How It Works

> A step-by-step walkthrough of every stage in the signal lifecycle,
> from cold boot to Telegram delivery and trade exit.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Step 1 — Configuration & Startup](#2-step-1--configuration--startup)
   - [Event Bus — Cross-Component Communication](#event-bus--cross-component-communication)
3. [Step 2 — Authentication (Angel One SmartAPI)](#3-step-2--authentication-angel-one-smartapi)
4. [Step 3 — Pre-Market Data Fetch](#4-step-3--pre-market-data-fetch)
5. [Step 4 — Market Scheduling](#5-step-4--market-scheduling)
6. [Step 5 — Real-Time Data (WebSocket)](#6-step-5--real-time-data-websocket)
7. [Step 6 — Market Data Store](#7-step-6--market-data-store)
8. [Step 7 — Strategy Evaluation & Pipeline Architecture](#8-step-7--strategy-evaluation)
   - [Composable Pipeline Architecture](#composable-pipeline-architecture)
   - [7a. Gap & Go Strategy](#7a-gap--go-strategy)
   - [7b. ORB Strategy](#7b-orb-strategy)
   - [7c. VWAP Reversal Strategy](#7c-vwap-reversal-strategy)
9. [Step 8 — Duplicate Checking](#9-step-8--duplicate-checking)
10. [Step 8.5 — Multi-Strategy Confirmation Detection (Phase 3)](#10-step-85--multi-strategy-confirmation-detection-phase-3)
11. [Step 9 — Signal Ranking & Scoring](#11-step-9--signal-ranking--scoring)
12. [Step 9.5 — Composite Hybrid Scoring (Phase 3)](#12-step-95--composite-hybrid-scoring-phase-3)
13. [Step 10 — Risk Management & Position Sizing](#13-step-10--risk-management--position-sizing)
14. [Step 10.5 — Circuit Breaker Gate (Phase 3)](#14-step-105--circuit-breaker-gate-phase-3)
15. [Step 10.6 — Adaptive Strategy Management (Phase 3)](#15-step-106--adaptive-strategy-management-phase-3)
16. [Step 10.7 — News Sentiment Filter (Phase 4 NSF)](#16-step-107--news-sentiment-filter-phase-4-nsf)
17. [Step 10.8 — Market Regime Detection (Phase 4 MRD)](#17-step-108--market-regime-detection-phase-4-mrd)
18. [Step 11 — Capital Allocation](#18-step-11--capital-allocation)
19. [Step 12 — Database Persistence](#19-step-12--database-persistence)
20. [Step 13 — Telegram Delivery](#20-step-13--telegram-delivery)
21. [Step 14 — Exit Monitoring](#21-step-14--exit-monitoring)
22. [Step 15 — Telegram Commands (User Interaction)](#22-step-15--telegram-commands-user-interaction)
23. [Step 15.5 — Inline Button Callbacks & Quick Actions (Phase 4)](#23-step-155--inline-button-callbacks--quick-actions-phase-4)
24. [Step 16 — Daily Wind-Down & Summary](#24-step-16--daily-wind-down--summary)
25. [Step 17 — Shutdown & Crash Recovery](#25-step-17--shutdown--crash-recovery)
26. [Step 18 — Dashboard (Phase 3)](#26-step-18--dashboard-phase-3)
27. [Data Model Chain](#27-data-model-chain)
28. [Logging & Observability](#28-logging--observability)
29. [Rate Limiting & Retry](#29-rate-limiting--retry)
30. [Complete Scan Loop Iteration](#30-complete-scan-loop-iteration)
31. [Summary: A Complete Trading Day](#31-summary-a-complete-trading-day)

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
   create_app()          <-- wires 40+ components in dependency order
        |
        |-- DatabaseManager --> SignalRepository
        |                   --> TradeRepository
        |                   --> ConfigRepository
        |                   --> MetricsCalculator
        |                   --> StrategyPerformanceRepository
        |                   --> SignalActionRepository       (Phase 4)
        |                   --> WatchlistRepository          (Phase 4)
        |                   --> NewsSentimentRepository      (Phase 4 NSF)
        |                   --> EarningsCalendarRepository   (Phase 4 NSF)
        |                   --> MarketRegimeRepository       (Phase 4 MRD)
        |                   --> RegimePerformanceRepository  (Phase 4 MRD)
        |                   --> HybridScoreRepository       (Phase 3)
        |                   --> CircuitBreakerRepository     (Phase 3)
        |                   --> AdaptationLogRepository      (Phase 3)
        |
        |-- EventBus (in-process async event dispatch)
        |       |-- ExitAlertEvent      --> bot.send_exit_alert()
        |       |-- StopLossHitEvent    --> circuit_breaker.on_sl_hit()
        |       |-- TradeExitedEvent    --> adaptive_manager.on_trade_exit()
        |       |-- AlertMessageEvent   --> bot.send_alert()
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
        |-- ScanPipeline (composable 13-stage signal pipeline + 1 always stage)
        |       |-- Signal stages (run when accepting_signals=True):
        |       |     CircuitBreakerGateStage --> RegimeContextStage -->
        |       |     StrategyEvalStage --> GapStockMarkingStage -->
        |       |     DeduplicationStage --> ConfidenceStage -->
        |       |     CompositeScoringStage --> AdaptiveFilterStage -->
        |       |     RankingStage --> NewsSentimentStage -->
        |       |     RiskSizingStage --> PersistAndDeliverStage -->
        |       |     DiagnosticStage
        |       |-- Always stages (run every cycle):
        |       |     ExitMonitoringStage
        |       +-- ScanContext (mutable state bag passed through all stages)
        |
        |-- DuplicateChecker (cross-strategy same-day dedup)
        |
        |-- SignalRanker (SignalScorer --> ORBScorer / VWAPScorer)
        |       |-- ConfidenceDetector     (Phase 3) — multi-strategy confirmation detection
        |       |-- CompositeScorer        (Phase 3) — 4-factor hybrid scoring
        |
        |-- RiskManager (PositionSizer)
        |
        |-- CapitalAllocator (StrategyPerformanceRepository)
        |       |-- 20% reserve, expectancy-weighted allocation
        |       |-- Auto-pause: win_rate < 40% after 10+ trades
        |
        |-- Intelligence Layer (Phase 3)
        |       |-- CircuitBreaker           — halt signals after N SL hits/day
        |       |-- AdaptiveManager          — throttle/pause underperforming strategies
        |       |-- ConfidenceDetector       — cross-strategy confirmation (single/double/triple)
        |
        |-- Intelligence Module (Phase 4 NSF) — signalpilot/intelligence/
        |       |-- VADERSentimentAnalyzer   — VADER + financial lexicon overlay
        |       |   +-- Optional FinBERTSentimentEngine (transformer-based)
        |       |-- RSSNewsFetcher           — Google News RSS + MoneyControl RSS
        |       |   +-- Recency weighting: weight = exp(-lambda * age_hours)
        |       |-- NewsSentimentService     — orchestrates fetcher + engine, batch processing
        |       |   +-- Labels: STRONG_NEGATIVE / MILD_NEGATIVE / NEUTRAL / POSITIVE / NO_NEWS
        |       |-- EarningsCalendar         — CSV + optional screener API ingest
        |
        |-- Intelligence Module (Phase 4 MRD) — signalpilot/intelligence/
        |       |-- RegimeDataCollector      — VIX, gap, range, alignment data gathering
        |       |-- MarketRegimeClassifier   — composite scoring, classify/reclassify, modifiers
        |       |-- MorningBriefGenerator    — pre-market brief with global cues + regime prediction
        |
        |-- ExitMonitor --> reads MarketDataStore, emits events via EventBus
        |       |-- Per-strategy TrailingStopConfig
        |       |-- close_trade callback --> TradeRepository
        |       |-- emits ExitAlertEvent, StopLossHitEvent, TradeExitedEvent
        |
        |-- SignalPilotBot (Telegram, python-telegram-bot)
        |       |-- 21 text commands: TAKEN, STATUS, JOURNAL, CAPITAL, PAUSE,
        |       |   RESUME, ALLOCATE, STRATEGY, OVERRIDE, SCORE, ADAPT,
        |       |   REBALANCE, NEWS, EARNINGS, UNSUPPRESS, REGIME,
        |       |   REGIME HISTORY, REGIME OVERRIDE, VIX, MORNING, HELP
        |       |-- 7 inline keyboards (Phase 4): signal actions, skip reasons,
        |       |   T1/T2 targets, SL approaching, near-T2
        |       |-- 9 callback handlers (Phase 4): taken, skip, skip_reason,
        |       |   watch, partial_exit, exit_now, take_profit, hold, let_run
        |
        |-- Dashboard (Phase 3)
        |       |-- FastAPI backend          — 10 route modules (/api/signals, /trades, etc.)
        |       |-- React frontend/          — Vite + TypeScript + Tailwind + React Query
        |
        +-- MarketScheduler (APScheduler 3.x, 17 IST cron jobs)
                |
                +-- SignalPilotApp._scan_loop()  <-- runs every 1 second
                        via ScanPipeline.run(ctx)
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

**Phase 3 — Composite Scoring:**

| Field | Default | Description |
|-------|---------|-------------|
| `composite_weight_strategy` | `0.4` | Strategy strength weight |
| `composite_weight_win_rate` | `0.3` | Win rate weight |
| `composite_weight_risk_reward` | `0.2` | Risk-reward ratio weight |
| `composite_weight_confirmation` | `0.1` | Confirmation bonus weight |
| `confirmation_window_minutes` | `15` | Window for cross-strategy confirmation |

**Phase 3 — Circuit Breaker:**

| Field | Default | Description |
|-------|---------|-------------|
| `circuit_breaker_sl_limit` | `3` | SL hits before circuit breaker activates |

**Phase 3 — Adaptive Learning:**

| Field | Default | Description |
|-------|---------|-------------|
| `adaptive_consecutive_loss_throttle` | `3` | Consecutive losses to trigger throttle |
| `adaptive_consecutive_loss_pause` | `5` | Consecutive losses to trigger pause |
| `adaptive_5d_warn_threshold` | `35.0` | 5-day win rate warning threshold % |
| `adaptive_10d_pause_threshold` | `30.0` | 10-day win rate pause threshold % |

**Phase 3 — Confirmed Signal Caps:**

| Field | Default | Description |
|-------|---------|-------------|
| `confirmed_double_cap_pct` | `20.0` | Max capital % for double-confirmed signals |
| `confirmed_triple_cap_pct` | `25.0` | Max capital % for triple-confirmed signals |

**Phase 3 — Dashboard:**

| Field | Default | Description |
|-------|---------|-------------|
| `dashboard_enabled` | `True` | Enable web dashboard |
| `dashboard_port` | `8000` | Dashboard server port |
| `dashboard_host` | `"127.0.0.1"` | Dashboard bind address |

**Phase 4 — News Sentiment Filter:**

| Field | Default | Description |
|-------|---------|-------------|
| `news_enabled` | `False` | Enable news sentiment filtering |
| `earnings_blackout_enabled` | `False` | Enable earnings blackout suppression |
| `strong_negative_threshold` | `-0.5` | Score below this triggers signal suppression |
| `mild_negative_threshold` | `-0.2` | Score below this triggers star rating downgrade |
| `positive_threshold` | `0.3` | Score above this adds positive badge |
| `news_lookback_hours` | `24` | Hours of news history to consider |
| `news_rss_feeds` | `""` | Comma-separated RSS feed URLs (Google News, MoneyControl) |
| `news_sentiment_model` | `"vader"` | Sentiment model: `"vader"` or `"finbert"` |

**Retry & Resilience:**

| Field | Default | Description |
|-------|---------|-------------|
| `auth_max_retries` | `3` | Auth retry attempts |
| `ws_max_reconnect_attempts` | `3` | WebSocket reconnect attempts |
| `historical_api_rate_limit` | `3` | Requests per second |
| `max_crashes_per_session` | `3` | Max crash recoveries per session |

**Validators:**

A `@model_validator` enforces that each of the three scoring weight groups
(Gap & Go, ORB, VWAP) sums to `1.0 +/- 0.01` tolerance. A separate
`@model_validator` enforces that the four composite scoring weights
(`composite_weight_strategy`, `composite_weight_win_rate`,
`composite_weight_risk_reward`, `composite_weight_confirmation`) sum to
`1.0`. The app won't start with invalid weights.

### Entry Point: `signalpilot/main.py`

```python
async def main() -> None:
    config = AppConfig()                     # load .env
    configure_logging(level=config.log_level, log_file=config.log_file)
    app = await create_app(config)           # wire 40+ components

    # Setup SIGINT/SIGTERM handlers (once via shutting_down flag)
    now = datetime.now(IST)
    if is_market_hours(now) and is_trading_day(now.date()):
        await app.recover()                  # crash-recovery path
    else:
        await app.startup()                  # normal startup

    while True:
        await asyncio.sleep(1)               # keep event loop alive
```

#### `create_app()` Wiring Order (31 stages)

1. **Database** — `DatabaseManager(db_path)` + `initialize()` (WAL mode, foreign keys, phase 2 migration, phase 3 migration, phase 4 NSF migration, phase 4 MRD migration)
2. **Repositories** — `SignalRepository`, `TradeRepository`, `ConfigRepository`, `MetricsCalculator`, `StrategyPerformanceRepository`, `SignalActionRepository`, `WatchlistRepository`, `NewsSentimentRepository`, `EarningsCalendarRepository`, `HybridScoreRepository`, `CircuitBreakerRepository`, `AdaptationLogRepository`, `MarketRegimeRepository`, `RegimePerformanceRepository` (all sharing the same `aiosqlite.Connection`)
3. **Event Bus** — `EventBus()` (in-process async event dispatch for decoupled cross-component communication)
4. **Auth** — `SmartAPIAuthenticator(config)`
5. **Data** — `InstrumentManager(csv_path)`, `MarketDataStore()`, `HistoricalDataFetcher(authenticator, instruments, rate_limit)`
6. **Strategies** — `GapAndGoStrategy(config)`, `ORBStrategy(config, market_data)`, `VWAPCooldownTracker(max_signals=2, cooldown=60)` + `VWAPReversalStrategy(config, market_data, cooldown_tracker)`
7. **Duplicate Checker** — `DuplicateChecker(signal_repo, trade_repo)`
8. **Ranking** — `ScoringWeights(...)` + `ORBScorer(...)` + `VWAPScorer(...)` + `SignalScorer(weights, orb_scorer, vwap_scorer)` + `SignalRanker(scorer, max_signals=8)`
9. **Capital Allocation** — `CapitalAllocator(strategy_performance_repo, config_repo)`
10. **Risk** — `PositionSizer()` + `RiskManager(position_sizer)`
11. **Exit Monitor** — `ExitMonitor(get_tick, event_bus, trailing_configs, close_trade=trade_repo.close_trade)` with per-strategy `TrailingStopConfig` dict (6 entries for Gap & Go, ORB, VWAP setups)
12. **Sentiment Engine** (Phase 4 NSF) — `VADERSentimentAnalyzer(financial_lexicon_path)` or `FinBERTSentimentEngine()` based on `config.news_sentiment_model`
13. **News Fetcher** (Phase 4 NSF) — `RSSNewsFetcher(config.news_rss_feeds)` — Google News + MoneyControl RSS feeds
14. **News Sentiment Service** (Phase 4 NSF) — `NewsSentimentService(fetcher, engine, news_sentiment_repo, config)` — orchestrates batch processing, labeling, caching
15. **Earnings Calendar** (Phase 4 NSF) — `EarningsCalendar(earnings_repo, csv_path="data/earnings_calendar.csv")` — optional screener API ingest
16. **Regime Data Collector** (Phase 4 MRD) — `RegimeDataCollector(config)` — gathers VIX, gap, range, alignment data
17. **Regime Classifier** (Phase 4 MRD) — `MarketRegimeClassifier(config)` — composite scoring and classification engine
18. **Morning Brief** (Phase 4 MRD) — `MorningBriefGenerator(regime_data_collector, watchlist_repo, config)` — pre-market briefing
19. **Telegram Bot** — `SignalPilotBot(...)` with `_get_current_prices` wrapper, `news_sentiment_service`, `earnings_repo`, `regime_classifier`, `regime_repo`, `regime_perf_repo`, `regime_data_collector`, `morning_brief` injected
20. **WebSocket** — `WebSocketClient(authenticator, instruments, market_data_store, on_disconnect_alert, max_reconnect_attempts)`
21. **Scheduler** — `MarketScheduler()`
22. **Confidence Detector** (Phase 3) — `ConfidenceDetector(signal_repo, confirmation_window_minutes=15)`
23. **Composite Scorer** (Phase 3) — `CompositeScorer(strategy_performance_repo, config)` with 4 weighted factors
24. **Circuit Breaker** (Phase 3) — `CircuitBreaker(circuit_breaker_repo, config_repo, event_bus, sl_limit=3)`
25. **Adaptive Manager** (Phase 3) — `AdaptiveManager(adaptation_log_repo, config_repo, strategy_performance_repo, event_bus)`
26. **Event Bus Subscriptions** — wires all cross-component events:
    - `ExitAlertEvent` → `bot.send_exit_alert()`
    - `StopLossHitEvent` → `circuit_breaker.on_sl_hit()`
    - `TradeExitedEvent` → `adaptive_manager.on_trade_exit()`
    - `AlertMessageEvent` → `bot.send_alert()`
27. **Pipeline** — `ScanPipeline(signal_stages=[13 stages], always_stages=[ExitMonitoringStage])`
28. **Dashboard** (Phase 3) — `create_dashboard_app(db_path, write_connection)` (if `dashboard_enabled`)
29. **SignalPilotApp** — orchestrator wired with all components + pipeline (includes `news_sentiment_service`, `earnings_calendar`, `regime_classifier`, `regime_data_collector`, `morning_brief` for scheduled jobs)

The bot and exit monitor have a circular dependency (exit alerts are sent via
the bot). The `EventBus` eliminates this: the exit monitor emits
`ExitAlertEvent` objects, and the bot subscribes to them. No direct reference
needed.

#### Event Bus — Cross-Component Communication

**File:** `signalpilot/events.py`

The `EventBus` is a lightweight in-process async event dispatcher. Components
publish events without knowing who receives them, and subscribers handle events
without knowing who sent them. All dispatch is sequential per event, with error
isolation (one handler failure does not block others).

**Event Types** (frozen dataclasses):

| Event | Emitted by | Handled by | Purpose |
|-------|-----------|------------|---------|
| `ExitAlertEvent(alert)` | ExitMonitor | Bot (`send_exit_alert`) | Deliver exit alerts to Telegram |
| `StopLossHitEvent(symbol, strategy, pnl_amount)` | ExitMonitor | CircuitBreaker (`on_sl_hit`) | Feed daily SL counter |
| `TradeExitedEvent(strategy_name, is_loss)` | ExitMonitor | AdaptiveManager (`on_trade_exit`) | Track consecutive wins/losses |
| `AlertMessageEvent(message)` | CircuitBreaker, AdaptiveManager | Bot (`send_alert`) | General Telegram alerts |

**EventBus API:**

```python
class EventBus:
    def subscribe(self, event_type: type, handler: EventHandler) -> None: ...
    def unsubscribe(self, event_type: type, handler: EventHandler) -> None: ...
    async def emit(self, event: object) -> None: ...
    def handler_count(self, event_type: type) -> int: ...
```

**Wiring** (in `create_app()`):

```python
event_bus = EventBus()
event_bus.subscribe(ExitAlertEvent, bot.send_exit_alert)
event_bus.subscribe(StopLossHitEvent, circuit_breaker.on_sl_hit)
event_bus.subscribe(TradeExitedEvent, adaptive_manager.on_trade_exit)
event_bus.subscribe(AlertMessageEvent, bot.send_alert)
```

This replaces the previous closure-based callback wiring (`bot_ref`,
`on_sl_hit_callback`, `on_trade_exit_callback`) with a type-safe, decoupled
event pattern.

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

`MarketScheduler` wraps **APScheduler 3.x** with **17 IST cron jobs** registered
against `SignalPilotApp` methods:

| Time (IST) | Job ID | Action |
|-----------|--------|--------|
| 08:30 Mon-Fri | `pre_market_news` | Batch-fetch news sentiment for watchlist + Nifty 500 (Phase 4 NSF) |
| 08:45 Mon-Fri | `morning_brief` | Generate & send pre-market morning brief with global cues, India context, regime prediction, watchlist alerts (Phase 4 MRD) |
| 09:00 Mon-Fri | `pre_market_alert` | Send "Signals coming at 9:15" Telegram alert |
| 09:15 Mon-Fri | `start_scanning` | Open WebSocket, reset session, begin 1-second scan loop |
| 09:30 Mon-Fri | `regime_classify` | Initial market regime classification for the day (Phase 4 MRD) |
| 09:45 Mon-Fri | `lock_opening_ranges` | Finalize 30-min opening range for ORB detection |
| 11:00 Mon-Fri | `regime_reclass_11` | Re-classification check: VIX spike (Phase 4 MRD) |
| 11:15 Mon-Fri | `news_cache_refresh_1` | Refresh stale news sentiment cache entries (Phase 4 NSF) |
| 13:00 Mon-Fri | `regime_reclass_13` | Re-classification check: direction reversal (Phase 4 MRD) |
| 13:15 Mon-Fri | `news_cache_refresh_2` | Refresh stale news sentiment cache entries (Phase 4 NSF) |
| 14:30 Mon-Fri | `regime_reclass_1430` | Re-classification check: round-trip (Phase 4 MRD) |
| 14:30 Mon-Fri | `stop_new_signals` | Set `_accepting_signals = False` |
| 15:00 Mon-Fri | `exit_reminder` | Advisory exit alerts for open positions |
| 15:15 Mon-Fri | `mandatory_exit` | Forced exit for all remaining open trades |
| 15:30 Mon-Fri | `daily_summary` | Calculate metrics, send end-of-day report; purge old sentiment cache, clear unsuppress overrides |
| 15:35 Mon-Fri | `shutdown` | Graceful shutdown |
| Sunday 18:00 | `weekly_rebalance` | Capital rebalancing across strategies; refresh earnings calendar |

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

### Composable Pipeline Architecture

**Files:** `signalpilot/pipeline/stage.py`, `context.py`, `stages/*.py`

The scan loop uses a **composable pipeline** — a sequence of independent stages
that each transform a shared `ScanContext`. This replaces inline orchestration
code with pluggable, testable stages.

#### Pipeline Protocol

```python
class PipelineStage(Protocol):
    @property
    def name(self) -> str: ...
    async def process(self, ctx: ScanContext) -> ScanContext: ...
```

#### ScanContext — Mutable State Bag

```python
@dataclass
class ScanContext:
    cycle_id: str = ""
    now: datetime | None = None
    phase: StrategyPhase = StrategyPhase.OPENING
    accepting_signals: bool = True

    # Set by StrategyEvalStage
    user_config: UserConfig | None = None
    enabled_strategies: list = field(default_factory=list)
    all_candidates: list[CandidateSignal] = field(default_factory=list)

    # Set by ConfidenceStage (Phase 3)
    confirmation_map: dict | None = None

    # Set by CompositeScoringStage (Phase 3)
    composite_scores: dict | None = None

    # Set by RankingStage
    ranked_signals: list[RankedSignal] = field(default_factory=list)

    # Set by RegimeContextStage (Phase 4 MRD)
    regime: str | None = None
    regime_confidence: float = 0.0
    regime_min_stars: int = 3
    regime_position_modifier: float = 1.0
    regime_max_positions: int | None = None
    regime_strategy_weights: dict | None = None

    # Set by NewsSentimentStage (Phase 4 NSF)
    sentiment_results: dict[str, SentimentResult] = field(default_factory=dict)
    suppressed_signals: list[SuppressedSignal] = field(default_factory=list)

    # Set by RiskSizingStage
    final_signals: list[FinalSignal] = field(default_factory=list)
    active_trade_count: int = 0
```

#### Pipeline Execution

```python
class ScanPipeline:
    def __init__(self, signal_stages: list[PipelineStage],
                 always_stages: list[PipelineStage]) -> None: ...

    async def run(self, ctx: ScanContext) -> ScanContext:
        if ctx.accepting_signals and ctx.phase in {OPENING, ENTRY_WINDOW, CONTINUOUS}:
            for stage in self._signal_stages:
                ctx = await stage.process(ctx)
        for stage in self._always_stages:
            ctx = await stage.process(ctx)
        return ctx
```

#### 13 Signal Stages (in order)

| # | Stage | File | Purpose |
|---|-------|------|---------|
| 1 | `CircuitBreakerGateStage` | `circuit_breaker_gate.py` | Sets `ctx.accepting_signals = False` if circuit breaker is active |
| 2 | `RegimeContextStage` | `regime_context.py` | Reads cached regime classification, sets strategy weights and position modifiers on ScanContext (Phase 4 MRD) |
| 3 | `StrategyEvalStage` | `strategy_eval.py` | Loads user config, filters enabled strategies, runs `evaluate()` on each |
| 4 | `GapStockMarkingStage` | `gap_stock_marking.py` | Marks Gap & Go symbols for ORB/VWAP exclusion via `mark_gap_stock()` |
| 5 | `DeduplicationStage` | `deduplication.py` | Filters active-trade and same-day signal duplicates |
| 6 | `ConfidenceStage` | `confidence.py` | Detects multi-strategy confirmations (Phase 3) |
| 7 | `CompositeScoringStage` | `composite_scoring.py` | 4-factor hybrid scoring (Phase 3) |
| 8 | `AdaptiveFilterStage` | `adaptive_filter.py` | Removes signals from paused/throttled strategies (Phase 3) |
| 9 | `RankingStage` | `ranking.py` | Top-K selection by composite score, assigns 1-5 stars + regime min-stars filter (Phase 4 MRD) |
| 10 | `NewsSentimentStage` | `news_sentiment.py` | News sentiment filter: suppress, downgrade, or badge signals (Phase 4 NSF) |
| 11 | `RiskSizingStage` | `risk_sizing.py` | Position sizing, capital allocation + regime position modifier (Phase 4 MRD) |
| 12 | `PersistAndDeliverStage` | `persist_and_deliver.py` | Save signals to DB with regime metadata, deliver via Telegram with inline keyboards + regime badge; send suppression notifications (Phase 4 MRD) |
| 13 | `DiagnosticStage` | `diagnostic.py` | Heartbeat logging, WebSocket health checks |

#### 1 Always Stage (runs every cycle, regardless of signal acceptance)

| # | Stage | File | Purpose |
|---|-------|------|---------|
| 1 | `ExitMonitoringStage` | `exit_monitoring.py` | Check all active trades for SL/target/time exits |

### Strategy Evaluation (Stage 3 Detail)

Each strategy implements `BaseStrategy` (abstract class with `name`, `active_phases`,
and `evaluate()`) and declares which phases it is active in.

```python
# Inside StrategyEvalStage.process():
for strat in enabled_strategies:
    if phase in strat.active_phases:
        candidates = await strat.evaluate(self._market_data, phase)
        ctx.all_candidates.extend(candidates)
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

**Phase 3 exception:** Symbols with multi-strategy confirmation (detected by
`ConfidenceDetector`) bypass the same-day signal dedup check, allowing
confirmed setups to generate signals even if a prior strategy already signaled
the stock.

---

## 10. Step 8.5 — Multi-Strategy Confirmation Detection (Phase 3)

### File: `signalpilot/ranking/confidence.py`

The `ConfidenceDetector` identifies when multiple strategies agree on the same
stock within a configurable time window (default: 15 minutes). This is a
Phase 3 component that runs after duplicate checking and before ranking.

#### Confirmation Levels

| Level | Condition | Position Multiplier |
|-------|-----------|---------------------|
| `single` | Only 1 strategy signals the stock | 1.0x (no boost) |
| `double` | 2 strategies signal within window | 1.5x |
| `triple` | 3 strategies signal within window | 2.0x |

#### Detection Flow

1. Group current batch of candidates by symbol
2. For each symbol with candidates, query
   `signal_repo.get_recent_signals_by_symbol(symbol, since=now - window)`
3. Collect unique strategy names from both current candidates and recent DB
   signals
4. Determine level: 3+ strategies = triple, 2 = double, 1 = single
5. Return `ConfirmationResult(symbol, level, confirmed_by=[strategy_names], multiplier)`

#### Impact on Downstream Components

- **DuplicateChecker:** Symbols with multi-strategy confirmation bypass
  same-day dedup
- **PositionSizer:** Multiplier applied to position size (capped at 20%/25%
  of capital for double/triple confirmation respectively)
- **SignalRecord:** `confirmation_level`, `confirmed_by`, and
  `position_size_multiplier` fields are persisted to the `signals` table
- **Telegram:** Confirmation badge shown in the signal message (e.g.,
  "DOUBLE CONFIRMED by Gap & Go + ORB")

---

## 11. Step 9 — Signal Ranking & Scoring

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

## 12. Step 9.5 — Composite Hybrid Scoring (Phase 3)

### File: `signalpilot/ranking/composite_scorer.py`

When Phase 3 is active, signals are scored using a 4-factor composite system
instead of legacy single-factor scoring. The composite scorer runs after the
per-strategy scorer and produces a blended score incorporating historical
performance and cross-strategy confirmation data.

#### Four Factors

| Factor | Weight | Source | Range |
|--------|--------|--------|-------|
| Strategy Strength | 0.40 | `candidate.strategy_specific_score` or legacy scorer | 0-100 |
| Win Rate | 0.30 | 30-day trailing win rate from `strategy_performance` table | 0-100 |
| Risk-Reward | 0.20 | Linear mapping: R:R 1.0 -> 0, R:R 3.0+ -> 100 | 0-100 |
| Confirmation Bonus | 0.10 | 0 (single), 50 (double), 100 (triple) | 0-100 |

#### Formula

```
composite = (strategy_strength * 0.40) + (win_rate * 0.30) + (risk_reward * 0.20) + (confirmation * 0.10)
```

#### Win Rate Cache

Per-strategy win rates are cached per day to avoid repeated DB queries. The
cache is keyed by `(strategy_name, date)` and populated on first access via
`strategy_performance_repo`.

#### Star Rating (Composite Mode)

| Score Range | Stars |
|-------------|-------|
| [0, 20) | 1 |
| [20, 40) | 2 |
| [40, 60) | 3 |
| [60, 80) | 4 |
| [80, 100] | 5 |

#### Persistence

`HybridScoreRecord` is persisted to the `hybrid_scores` table for every
scored signal, capturing the composite score and all four factor scores along
with confirmation details.

---

## 13. Step 10 — Risk Management & Position Sizing

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

## 14. Step 10.5 — Circuit Breaker Gate (Phase 3)

### File: `signalpilot/monitor/circuit_breaker.py`

After scoring but before delivery, signals pass through the circuit breaker
gate. The circuit breaker protects against cascading losses by halting all
new signal generation after a configurable number of stop-loss exits in a
single trading day.

#### How It Works

- Tracks daily stop-loss count via the `on_sl_hit()` callback wired from
  ExitMonitor
- When `sl_count >= sl_limit` (default 3): activates, halting all new
  signals for the rest of the day
- Sends a Telegram alert: "Circuit breaker activated after N stop-losses"
- Logs activation to the `circuit_breaker_log` table
- Can be overridden via the `OVERRIDE` Telegram command or the dashboard API
- Resets daily at the start of scanning (9:15 AM)

#### State

```python
_daily_sl_count: int = 0
_is_active: bool = False
_overridden: bool = False
```

#### Key Methods

| Method | Description |
|--------|-------------|
| `on_sl_hit()` | Increment SL count; activate if threshold reached |
| `is_active` | Property: `True` if circuit breaker has tripped |
| `is_overridden` | Property: `True` if user manually overrode |
| `override()` | Set `_overridden = True`, log override to DB |
| `reset()` | Reset all state for new trading day |

---

## 15. Step 10.6 — Adaptive Strategy Management (Phase 3)

### File: `signalpilot/monitor/adaptive_manager.py`

The `AdaptiveManager` adjusts strategy behavior based on recent performance.
It operates at the per-strategy level, tracking consecutive losses and
trailing win rates to automatically throttle or pause underperforming
strategies.

#### Adaptation Levels (Per Strategy)

| Level | Trigger | Effect |
|-------|---------|--------|
| `NORMAL` | Default / win resets | Full signal generation |
| `REDUCED` | 3 consecutive losses | Signals generated but flagged as reduced confidence |
| `PAUSED` | 5 consecutive losses | Strategy temporarily disabled |

#### `on_trade_exit()` Flow

1. If loss: increment `consecutive_losses`, reset `consecutive_wins`
2. If `consecutive_losses >= pause_threshold` (5): transition to `PAUSED`,
   log to `adaptation_log` table, send Telegram alert
3. Elif `consecutive_losses >= throttle_threshold` (3): transition to
   `REDUCED`, log, alert
4. If win: reset `consecutive_losses`, if strategy was `REDUCED` or `PAUSED`
   then transition back to `NORMAL`

#### Trailing Performance Check

`check_trailing_performance()` is called during the weekly rebalance job:

- 5-day win rate < 35%: warning alert sent via Telegram
- 10-day win rate < 30%: auto-pause recommendation sent

#### `should_allow_signal(strategy_name)`

Returns `True` if the strategy is `NORMAL` or `REDUCED`, `False` if `PAUSED`.
This method is called in the scan loop to filter out signals from paused
strategies before delivery.

All state changes are logged to the `adaptation_log` table with event type,
old weight, new weight, and details.

---

## 16. Step 10.7 — News Sentiment Filter (Phase 4 NSF)

### Files: `signalpilot/intelligence/sentiment_engine.py`, `news_fetcher.py`, `news_sentiment.py`, `earnings.py`
### Pipeline Stage: `signalpilot/pipeline/stages/news_sentiment.py`

The News Sentiment Filter (NSF) is an intelligence module that evaluates news
headlines for each ranked signal and takes action based on the sentiment score.
It runs as **pipeline stage 10**, after `RankingStage` and before `RiskSizingStage`,
operating on the `ctx.ranked_signals` list produced by ranking.

### Intelligence Module Architecture

The `signalpilot/intelligence/` package contains four components that work
together:

#### 1. Sentiment Engine (`sentiment_engine.py`)

`VADERSentimentAnalyzer` uses the VADER sentiment analysis library augmented
with a **financial lexicon overlay** loaded from `data/financial_lexicon.json`.
The financial lexicon adds domain-specific terms and adjusts scores for words
that carry different sentiment in financial contexts (e.g., "downgrade",
"upgrade", "miss", "beat").

```python
class VADERSentimentAnalyzer:
    def analyze(self, text: str) -> float:
        """Score text from -1.0 (most negative) to +1.0 (most positive)."""
        ...
```

An optional `FinBERTSentimentEngine` is available for transformer-based
sentiment analysis. The engine to use is selected via the
`news_sentiment_model` config field (`"vader"` or `"finbert"`).

#### 2. News Fetcher (`news_fetcher.py`)

`RSSNewsFetcher` pulls headlines from configurable RSS feeds (default: Google
News RSS, MoneyControl RSS). Each headline is assigned a **recency weight**
using exponential decay:

```
weight = exp(-lambda * age_hours)
lambda = ln(2) / 6
```

This means a headline loses half its weight every 6 hours. A 24-hour-old
headline carries approximately 6.25% of the weight of a fresh headline. The
lookback window is controlled by `news_lookback_hours` (default: 24).

#### 3. News Sentiment Service (`news_sentiment.py`)

`NewsSentimentService` orchestrates the fetcher and engine to produce a
composite sentiment result per stock:

```python
class NewsSentimentService:
    async def get_sentiment(self, stock_code: str) -> SentimentResult: ...
    async def batch_get_sentiment(self, stock_codes: list[str]) -> dict[str, SentimentResult]: ...
```

**Labeling thresholds** (configurable via AppConfig):

| Label | Score Range | Default Thresholds |
|-------|------------|-------------------|
| `STRONG_NEGATIVE` | score < -0.5 | `strong_negative_threshold = -0.5` |
| `MILD_NEGATIVE` | -0.5 <= score < -0.2 | `mild_negative_threshold = -0.2` |
| `NEUTRAL` | -0.2 <= score <= 0.3 | Between mild_negative and positive thresholds |
| `POSITIVE` | score > 0.3 | `positive_threshold = 0.3` |
| `NO_NEWS` | No headlines found | N/A |

Results are cached in the `news_sentiment_cache` database table with a
configurable TTL. The service supports **session-scoped unsuppress overrides**
that allow a user to force a stock through the filter for the remainder of
the trading session via the `UNSUPPRESS` Telegram command.

#### 4. Earnings Calendar (`earnings.py`)

`EarningsCalendar` loads upcoming earnings dates from a CSV file
(`data/earnings_calendar.csv`) and optionally ingests data from a screener API.

```python
class EarningsCalendar:
    async def has_earnings_today(self, stock_code: str) -> bool: ...
    async def get_upcoming_earnings(self, days_ahead: int = 7) -> list[EarningsRecord]: ...
```

Earnings dates are stored in the `earnings_calendar` database table. The
calendar is refreshed during the weekly rebalance job (Sunday 18:00).

### NewsSentimentStage — Pipeline Stage 10

**File:** `signalpilot/pipeline/stages/news_sentiment.py`

The `NewsSentimentStage` processes each ranked signal through the sentiment
filter and applies one of several actions based on the result.

#### Action Matrix

| Condition | Action | Effect on Signal |
|-----------|--------|-----------------|
| Earnings blackout (`has_earnings_today`) | **Suppress** | Signal removed from `ctx.ranked_signals`, added to `ctx.suppressed_signals`, suppression notification sent |
| `STRONG_NEGATIVE` (score < -0.5) | **Suppress** | Signal removed, added to suppressed list, notification sent |
| `MILD_NEGATIVE` (-0.5 to -0.2) | **Downgrade** | Star rating reduced by 1 (minimum 1); original rating preserved in `original_star_rating` |
| `NEUTRAL` (-0.2 to 0.3) | **Pass through** | Signal unchanged |
| `POSITIVE` (score > 0.3) | **Badge** | Signal passed through with positive sentiment badge in Telegram message |
| `NO_NEWS` (no headlines found) | **Pass through** | Signal passed through with "no recent news" note |
| Unsuppress override active | **Pass through** | Signal passed through with `UNSUPPRESSED` action, regardless of sentiment score |

**Priority:** Earnings blackout takes the highest priority and suppresses
regardless of the sentiment score. Unsuppress overrides take the next highest
priority, allowing a stock through even with negative sentiment.

#### Stage Processing Flow

```python
async def process(self, ctx: ScanContext) -> ScanContext:
    if not self._config.news_enabled:
        return ctx    # feature gate: skip if disabled

    # 1. Batch-fetch sentiment for all ranked signal symbols
    symbols = [rs.candidate.symbol for rs in ctx.ranked_signals]
    ctx.sentiment_results = await self._service.batch_get_sentiment(symbols)

    # 2. Apply action matrix to each ranked signal
    surviving_signals = []
    for ranked_signal in ctx.ranked_signals:
        symbol = ranked_signal.candidate.symbol
        result = ctx.sentiment_results.get(symbol)

        # Earnings blackout check (highest priority)
        if self._config.earnings_blackout_enabled:
            if await self._earnings.has_earnings_today(symbol):
                ctx.suppressed_signals.append(SuppressedSignal(..., reason="earnings_blackout"))
                continue

        # Unsuppress override check
        if self._service.is_unsuppressed(symbol):
            result.action = "UNSUPPRESSED"
            surviving_signals.append(ranked_signal)
            continue

        # Sentiment-based action
        if result.label == "STRONG_NEGATIVE":
            ctx.suppressed_signals.append(SuppressedSignal(...))
            continue
        elif result.label == "MILD_NEGATIVE":
            ranked_signal.original_star_rating = ranked_signal.signal_strength
            ranked_signal.signal_strength = max(1, ranked_signal.signal_strength - 1)

        surviving_signals.append(ranked_signal)

    ctx.ranked_signals = surviving_signals
    return ctx
```

#### Impact on Downstream Stages

- **RiskSizingStage (stage 11):** Receives only signals that survived
  sentiment filtering. Suppressed signals never reach position sizing.
- **PersistAndDeliverStage (stage 12):** Persists sentiment metadata
  (`news_sentiment_score`, `news_sentiment_label`, `news_top_headline`,
  `news_action`, `original_star_rating`) on the `SignalRecord` before DB
  insert. Sends suppression notifications via `bot.send_alert()` for each
  entry in `ctx.suppressed_signals`. Passes news kwargs to
  `bot.send_signal()` for enriched message formatting.
- **Telegram message formatting:** `format_signal_message()` is extended
  with `news_sentiment_label`, `news_sentiment_score`, `news_top_headline`,
  and `original_star_rating` parameters. Shows a warning block for
  `MILD_NEGATIVE`, a positive badge for `POSITIVE`, and a "no recent news"
  note for `NO_NEWS`.

#### Suppression Notifications

When a signal is suppressed (either by negative sentiment or earnings
blackout), the `PersistAndDeliverStage` sends a suppression notification to
Telegram via a dedicated `format_suppression_notification()` function:

```
SIGNAL SUPPRESSED -- RELIANCE

Strategy: Gap & Go
Original Rating: ****- (Strong)
Entry Price: 2,850.00

Reason: Strong negative news sentiment
Score: -0.72
Headline: "RELIANCE reports Q3 miss, guidance cut"

This signal was automatically suppressed by the
News Sentiment Filter. Use UNSUPPRESS RELIANCE
to override for today's session.
```

### Scheduled Jobs

Three new cron jobs support the NSF:

| Time | Job | Method | Purpose |
|------|-----|--------|---------|
| 08:30 Mon-Fri | `pre_market_news` | `app.fetch_pre_market_news()` | Batch-fetch sentiment for watchlist + Nifty 500 stocks before market open |
| 11:15 Mon-Fri | `news_cache_refresh_1` | `app.refresh_news_cache()` | Refresh stale cache entries (re-fetch headlines for stocks with expired TTL) |
| 13:15 Mon-Fri | `news_cache_refresh_2` | `app.refresh_news_cache()` | Second mid-day cache refresh |

Additionally, two existing jobs are enhanced:

- **`send_daily_summary()` (15:30):** Now also purges old sentiment cache
  entries and clears all session-scoped unsuppress overrides.
- **`run_weekly_rebalance()` (Sunday 18:00):** Now also refreshes the
  earnings calendar data.

### Dashboard API Routes (Phase 4 NSF)

**File:** `signalpilot/dashboard/routes/news.py`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/news/{stock_code}` | Sentiment result for a single stock (score, label, headlines) |
| `GET` | `/api/v1/news/suppressed/list` | Recently suppressed signals with reasons and sentiment details |
| `GET` | `/api/v1/earnings/upcoming` | Upcoming earnings dates for Nifty 500 stocks |

---

## 17. Step 10.8 — Market Regime Detection (Phase 4 MRD)

### Files: `signalpilot/intelligence/regime_data.py`, `regime_classifier.py`, `morning_brief.py`
### Pipeline Stage: `signalpilot/pipeline/stages/regime_context.py`

Market Regime Detection (MRD) classifies each trading day as **TRENDING**,
**RANGING**, or **VOLATILE** at 9:30 AM IST. It uses composite scoring from
four inputs — India VIX, Nifty gap %, first-15-minute range %, and directional
alignment — to determine the prevailing market condition. Once classified, the
regime adjusts strategy weights, position sizing, signal filtering, and
minimum star thresholds for the remainder of the session.

The system supports **shadow mode** (classify and log without applying
modifiers) for safe rollout, and allows up to **2 re-classifications per day**
at 11:00, 13:00, and 14:30 IST. Re-classifications are severity-only
upgrades: TRENDING can escalate to RANGING, and RANGING can escalate to
VOLATILE, but never the reverse.

### Intelligence Module Architecture

The `signalpilot/intelligence/` package contains three components for regime
detection:

#### 1. RegimeDataCollector (`signalpilot/intelligence/regime_data.py`)

`RegimeDataCollector` gathers market-wide data needed for both regime
classification and the morning brief. It exposes two primary dataclasses and
multiple data-fetching methods.

**Dataclasses:**

```python
@dataclass
class RegimeInputs:
    """Inputs for regime classification at 9:30 AM."""
    india_vix: float | None
    nifty_gap_pct: float | None
    nifty_first_15_range_pct: float | None
    nifty_first_15_direction: str | None      # "up", "down", or "flat"
    directional_alignment: float | None       # -1.0 to 1.0
    sp500_change_pct: float | None
    sgx_nifty_change_pct: float | None

@dataclass
class PreMarketData:
    """Inputs for 8:45 AM morning brief."""
    sp500_close: float | None
    sp500_change_pct: float | None
    nasdaq_change_pct: float | None
    dow_change_pct: float | None
    sgx_nifty: float | None
    sgx_nifty_change_pct: float | None
    asia_markets: dict | None
    india_vix: float | None
    india_vix_change_pct: float | None
    fii_net: float | None
    dii_net: float | None
    crude_oil: float | None
    usd_inr: float | None
```

**Methods:**

```python
class RegimeDataCollector:
    async def collect_regime_inputs(self) -> RegimeInputs:
        """Gather VIX, gap, range, alignment for 9:30 AM classification."""
        ...

    async def collect_pre_market_data(self) -> PreMarketData:
        """Gather global cues, FII/DII for 8:45 AM morning brief."""
        ...

    async def fetch_current_vix(self) -> float | None:
        """Fetch current India VIX value."""
        ...

    async def fetch_global_cues(self) -> dict | None:
        """Fetch S&P 500, NASDAQ, Dow, SGX Nifty, Asia markets."""
        ...

    async def fetch_fii_dii(self) -> dict | None:
        """Fetch FII/DII net flow data."""
        ...

    async def get_current_nifty_data(self) -> dict | None:
        """Fetch current Nifty 50 index data (open, high, low, close)."""
        ...

    def set_prev_day_data(self, data: dict) -> None:
        """Cache previous day close for gap calculation."""
        ...

    def set_global_cues(self, cues: dict) -> None:
        """Cache global cues for session reuse."""
        ...

    def reset_session(self) -> None:
        """Clear all session-scoped caches at start of day."""
        ...
```

Each data source has **independent error handling** with `None` fallback.
If India VIX cannot be fetched, for example, the VIX score defaults to a
neutral value rather than blocking the entire classification.

#### 2. MarketRegimeClassifier (`signalpilot/intelligence/regime_classifier.py`)

`MarketRegimeClassifier` is the core classification engine. It uses a
composite scoring algorithm with four weighted factors to determine the
market regime.

**Scoring Algorithm — Four Static Methods:**

```python
@staticmethod
def _compute_vix_score(vix: float) -> float:
    """0.0 (VIX <= 12) to 1.0 (VIX >= 22), linear interpolation."""
    ...

@staticmethod
def _compute_gap_score(gap_pct: float) -> float:
    """0.0 (gap <= 0.3%) to 1.0 (gap >= 1.5%), linear interpolation."""
    ...

@staticmethod
def _compute_range_score(range_pct: float) -> float:
    """0.0 (range <= 0.5%) to 1.0 (range >= 2.0%), linear interpolation."""
    ...

@staticmethod
def _compute_alignment(direction: str, sp500: float | None,
                        sgx: float | None) -> float:
    """
    -1.0 to 1.0 based on directional agreement between
    Nifty first-15-min direction, S&P 500 change, and SGX Nifty change.
    """
    ...
```

**Composite Scoring Formula:**

Three regime scores are computed from the four input scores:

```
trending_score = gap * 0.35 + alignment * 0.30 + range * 0.20 + (1 - vix) * 0.15
ranging_score  = (1 - gap) * 0.30 + (1 - range) * 0.30 + (1 - vix) * 0.25 + (1 - |alignment|) * 0.15
volatile_score = vix * 0.40 + range * 0.25 + gap * 0.20 + (1 - |alignment|) * 0.15
```

The regime with the highest score wins (**winner-takes-all**). Confidence is
calculated as `winner_score / sum_of_all_scores`, producing a value between
0.33 (equal three-way split) and 1.0 (single dominant regime).

**Classification Methods:**

```python
class MarketRegimeClassifier:
    def classify(self, inputs: RegimeInputs) -> RegimeClassification:
        """
        Initial 9:30 AM classification. Computes all three regime scores,
        selects the winner, looks up per-regime modifiers based on
        confidence level, and returns a complete RegimeClassification.
        """
        ...

    def check_reclassify(self, inputs: RegimeInputs) -> RegimeClassification | None:
        """
        Mid-day re-classification (11:00, 13:00, 14:30). Checks three
        triggers and only reclassifies if severity increases.
        Returns None if no reclassification warranted.
        """
        ...

    def apply_override(self, regime: str) -> RegimeClassification:
        """Manual override via Telegram REGIME OVERRIDE command."""
        ...

    def reset_daily(self) -> None:
        """Clear daily state: cache, reclassification counter, morning VIX."""
        ...

    def get_cached_regime(self) -> RegimeClassification | None:
        """O(1) dict lookup for pipeline reads. Returns None before 9:30 AM."""
        ...
```

**Re-classification Triggers:**

The `check_reclassify()` method checks three conditions, any of which can
trigger a re-classification:

1. **VIX spike** — India VIX has increased by >= 3 points since the morning
   classification (configurable via `regime_vix_spike_threshold`)
2. **Direction reversal** — Nifty first-15-min direction has flipped from
   the morning reading (e.g., "up" at 9:30 became "down" at 11:00)
3. **Round-trip** — Nifty is currently within 0.3% of its open price
   (configurable via `regime_roundtrip_threshold`), indicating failed
   directional conviction

**Severity-Only Upgrades:**

Re-classifications can only increase severity, never decrease it:

```python
_SEVERITY_ORDER = {"TRENDING": 0, "RANGING": 1, "VOLATILE": 2}
```

A TRENDING day can be upgraded to RANGING or VOLATILE. A RANGING day can be
upgraded to VOLATILE. But a VOLATILE day cannot be downgraded back to
RANGING or TRENDING. This prevents the system from oscillating between
regimes and provides a conservative approach to risk management.

**Per-Regime Modifiers:**

The `_get_regime_modifiers()` method returns regime-specific parameters that
control downstream pipeline behavior. Modifiers differ based on confidence
level (high >= `regime_confidence_threshold`, default 0.55):

| Regime | Strategy Weights (GapGo / ORB / VWAP) | Min Stars | Position Modifier | Max Positions |
|--------|----------------------------------------|-----------|-------------------|---------------|
| **TRENDING** (high conf.) | 45% / 35% / 20% | 3 | 1.0 | 8 |
| **RANGING** (high conf.) | 20% / 30% / 50% | 3-4 | 0.85 | 6 |
| **VOLATILE** (high conf.) | 25% / 25% / 25% | 4-5 | 0.65 | 4 |

- **TRENDING**: Favors Gap & Go (momentum strategies thrive in trending
  markets). Full position sizes, standard star threshold.
- **RANGING**: Favors VWAP Reversal (mean-reversion strategies suit
  range-bound markets). Slightly reduced position sizes, moderate filtering.
- **VOLATILE**: Equal strategy weights (no single strategy dominates in
  volatile conditions). Significantly reduced position sizes, strict star
  filtering, fewer positions.

#### 3. MorningBriefGenerator (`signalpilot/intelligence/morning_brief.py`)

`MorningBriefGenerator` produces a pre-market briefing sent to Telegram at
8:45 AM, before market open. It collects global cues, India context, and
generates a regime prediction to help the user prepare for the trading day.

```python
class MorningBriefGenerator:
    async def generate(self) -> str:
        """
        Generate the morning brief. Collects pre-market data,
        predicts the likely regime, checks watchlist alerts,
        and formats the complete brief message.
        """
        ...

    def _predict_regime(self, data: PreMarketData) -> str:
        """
        Simple pre-market heuristic based on VIX level, SGX Nifty
        change, and S&P 500 overnight change. Returns a regime
        prediction string ("Likely TRENDING", "Possibly VOLATILE", etc.)
        This is a heuristic prediction; the actual classification
        occurs at 9:30 AM with real market data.
        """
        ...

    def _format_brief(self, data: PreMarketData, prediction: str,
                       watchlist_alerts: list) -> str:
        """
        Compose the Telegram message with four sections:
        GLOBAL CUES, INDIA CONTEXT, REGIME PREDICTION, WATCHLIST ALERTS.
        """
        ...

    def get_cached_brief(self) -> str | None:
        """Returns last generated brief for the MORNING command."""
        ...
```

**Morning Brief Telegram Format:**

```
MORNING BRIEF -- 28 Feb 2026

GLOBAL CUES
  S&P 500: +0.45%  |  NASDAQ: +0.62%  |  Dow: +0.31%
  SGX Nifty: +0.28%  |  Asia: Mixed
  Crude: $74.20  |  USD/INR: 83.45

INDIA CONTEXT
  India VIX: 14.2 (+0.8)
  FII: -1,245 Cr  |  DII: +2,310 Cr

REGIME PREDICTION
  Likely TRENDING -- Positive global cues, low VIX,
  directional SGX Nifty signal.

WATCHLIST ALERTS
  RELIANCE -- Gap & Go setup, added 2 days ago
  INFY -- VWAP Reversal setup, added 1 day ago
```

### RegimeContextStage — Pipeline Stage 2

**File:** `signalpilot/pipeline/stages/regime_context.py`

`RegimeContextStage` is the lightest pipeline stage, positioned after
`CircuitBreakerGateStage` (stage 1) and before `StrategyEvalStage` (stage 3).
Its purpose is to read the cached regime classification and set the
corresponding modifier fields on the `ScanContext` so that downstream stages
can adapt their behavior.

**Cost:** Less than 1ms per cycle (single dictionary lookup + 6 attribute
assignments). No I/O, no async calls, no external dependencies.

```python
class RegimeContextStage:
    @property
    def name(self) -> str:
        return "RegimeContextStage"

    async def process(self, ctx: ScanContext) -> ScanContext:
        # Pass-through when classifier is None or regime disabled
        if self._classifier is None or not self._config.regime_enabled:
            return ctx

        classification = self._classifier.get_cached_regime()

        # Before 9:30 AM (no cached regime yet): neutral defaults
        if classification is None:
            return ctx

        # Shadow mode: set regime/confidence for logging only
        if self._config.regime_shadow_mode:
            ctx.regime = classification.regime
            ctx.regime_confidence = classification.confidence
            return ctx

        # Active mode: set all 6 ScanContext fields
        ctx.regime = classification.regime
        ctx.regime_confidence = classification.confidence
        ctx.regime_min_stars = classification.min_stars
        ctx.regime_position_modifier = classification.position_modifier
        ctx.regime_max_positions = classification.max_positions
        ctx.regime_strategy_weights = classification.strategy_weights
        return ctx
```

**Behavioral Modes:**

| Condition | Behavior |
|-----------|----------|
| Classifier is `None` or `regime_enabled=False` | Pass-through (no-op) |
| No cached regime (before 9:30 AM) | Return context with neutral defaults |
| Shadow mode (`regime_shadow_mode=True`) | Set `regime` and `regime_confidence` for logging; leave modifier fields at defaults |
| Active mode (`regime_shadow_mode=False`) | Set all 6 ScanContext fields from `RegimeClassification` |

### Impact on Downstream Stages

The regime classification set by `RegimeContextStage` affects three
downstream pipeline stages:

- **RankingStage (stage 9):** After ranking and assigning star ratings, the
  stage applies `ctx.regime_min_stars` as a filter. Signals with star ratings
  below the threshold are dropped from `ctx.ranked_signals`. In a VOLATILE
  regime with high confidence, only 4-5 star signals survive.

- **RiskSizingStage (stage 11):** If `ctx.regime_max_positions` is set, it
  overrides the `max_positions` value from `UserConfig`. The
  `ctx.regime_position_modifier` is applied as a multiplier to the
  calculated quantity (e.g., 0.65 in VOLATILE regime reduces each position
  by 35%), with a minimum of 1 share.

- **PersistAndDeliverStage (stage 12):** Attaches `market_regime`,
  `regime_confidence`, and `regime_weight_modifier` to the `SignalRecord`
  before database insertion. Passes regime information to `send_signal()`
  for display as a regime badge in the Telegram message (e.g.,
  `[TRENDING 78%]` or `[VOLATILE 65%]`).

### Data Models

**`RegimeClassification` dataclass** — Full classification result with 22
fields, used as the return type from `classify()` and `check_reclassify()`:

```python
@dataclass
class RegimeClassification:
    regime: str                           # "TRENDING", "RANGING", "VOLATILE"
    confidence: float                     # 0.0-1.0
    trending_score: float
    ranging_score: float
    volatile_score: float
    vix_score: float
    gap_score: float
    range_score: float
    alignment_score: float
    india_vix: float | None
    nifty_gap_pct: float | None
    nifty_range_pct: float | None
    nifty_direction: str | None
    sp500_change_pct: float | None
    strategy_weights: dict[str, float]    # {"gap_go": 0.45, "orb": 0.35, "vwap": 0.20}
    min_stars: int
    position_modifier: float
    max_positions: int
    classified_at: datetime
    classification_type: str              # "initial", "reclassification", "override"
    reclassification_trigger: str | None  # "vix_spike", "direction_reversal", "round_trip"
    previous_regime: str | None
```

**`RegimePerformanceRecord` dataclass** — Daily per-regime per-strategy
performance tracking:

```python
@dataclass
class RegimePerformanceRecord:
    date: str
    regime: str
    strategy: str
    signals_generated: int
    signals_taken: int
    wins: int
    losses: int
    total_pnl: float
    win_rate: float               # auto-calculated on insert
    avg_pnl: float
    created_at: str
```

**`SignalRecord` — 3 new fields** for regime metadata (nullable, added by
Phase 4 MRD migration):

| Field | Type | Description |
|-------|------|-------------|
| `market_regime` | `TEXT` | Regime at time of signal: "TRENDING", "RANGING", "VOLATILE" |
| `regime_confidence` | `REAL` | Regime confidence at time of signal: 0.0-1.0 |
| `regime_weight_modifier` | `REAL` | Position weight modifier applied: 1.0, 0.85, or 0.65 |

### Database Tables & Migration

Two new tables and three new columns are added by the Phase 4 MRD migration.

#### `market_regimes` table (24 columns)

```sql
CREATE TABLE market_regimes (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    date                    TEXT    NOT NULL,
    regime                  TEXT    NOT NULL,   -- "TRENDING", "RANGING", "VOLATILE"
    confidence              REAL    NOT NULL,
    trending_score          REAL    NOT NULL,
    ranging_score           REAL    NOT NULL,
    volatile_score          REAL    NOT NULL,
    vix_score               REAL    NOT NULL,
    gap_score               REAL    NOT NULL,
    range_score             REAL    NOT NULL,
    alignment_score         REAL    NOT NULL,
    india_vix               REAL,
    nifty_gap_pct           REAL,
    nifty_range_pct         REAL,
    nifty_direction         TEXT,
    sp500_change_pct        REAL,
    strategy_weights        TEXT,              -- JSON: {"gap_go": 0.45, "orb": 0.35, "vwap": 0.20}
    min_stars               INTEGER NOT NULL,
    position_modifier       REAL    NOT NULL,
    max_positions           INTEGER NOT NULL,
    classified_at           TEXT    NOT NULL,
    classification_type     TEXT    NOT NULL,   -- "initial", "reclassification", "override"
    reclassification_trigger TEXT,
    previous_regime         TEXT
);
-- Indexes: idx_market_regimes_date, idx_market_regimes_regime
```

#### `regime_performance` table (11 columns)

```sql
CREATE TABLE regime_performance (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    date                TEXT    NOT NULL,
    regime              TEXT    NOT NULL,
    strategy            TEXT    NOT NULL,
    signals_generated   INTEGER NOT NULL DEFAULT 0,
    signals_taken       INTEGER NOT NULL DEFAULT 0,
    wins                INTEGER NOT NULL DEFAULT 0,
    losses              INTEGER NOT NULL DEFAULT 0,
    total_pnl           REAL    NOT NULL DEFAULT 0.0,
    win_rate            REAL    NOT NULL DEFAULT 0.0,
    avg_pnl             REAL    NOT NULL DEFAULT 0.0
);
-- Index: idx_regime_performance_date
```

#### Columns added to `signals` table

Three nullable columns are added to the existing `signals` table:

```sql
ALTER TABLE signals ADD COLUMN market_regime TEXT;
ALTER TABLE signals ADD COLUMN regime_confidence REAL;
ALTER TABLE signals ADD COLUMN regime_weight_modifier REAL;
```

#### Phase 4 MRD Migration

`DatabaseManager._run_phase4_mrd_migration()` is idempotent, following the
same pattern as earlier migrations. It uses `PRAGMA table_info()` to check
column existence before adding new columns to the `signals` table
(`market_regime`, `regime_confidence`, `regime_weight_modifier`) and creates
the `market_regimes` and `regime_performance` tables with their indexes.

### Repository Layer

Two new repository classes provide database access for regime data:

#### MarketRegimeRepository (`signalpilot/db/regime_repo.py`)

```python
class MarketRegimeRepository:
    def __init__(self, connection: aiosqlite.Connection) -> None: ...

    async def insert_classification(self, classification: RegimeClassification) -> int:
        """
        Persist a regime classification. JSON-serializes strategy_weights
        before INSERT. Returns the row ID.
        """
        ...

    async def get_today_classifications(self) -> list[RegimeClassification]:
        """
        Returns all classifications for today (IST), ordered by
        classified_at ascending. Includes initial, reclassifications,
        and overrides.
        """
        ...

    async def get_regime_history(self, days: int = 7) -> list[RegimeClassification]:
        """
        Returns the latest classification per day for the last N days.
        Uses a subquery to select MAX(classified_at) per date.
        """
        ...
```

#### RegimePerformanceRepository (`signalpilot/db/regime_performance_repo.py`)

```python
class RegimePerformanceRepository:
    def __init__(self, connection: aiosqlite.Connection) -> None: ...

    async def insert_daily_performance(self, record: RegimePerformanceRecord) -> int:
        """
        Persist daily performance record. Auto-calculates win_rate
        as wins / (wins + losses) if denominator > 0.
        """
        ...

    async def get_performance_by_regime(self, regime: str,
                                         days: int = 30) -> list[RegimePerformanceRecord]:
        """
        Returns performance records filtered by regime type
        for the last N days.
        """
        ...

    async def get_performance_summary(self, days: int = 30) -> list[dict]:
        """
        Returns grouped aggregate statistics: total signals, total trades,
        win rate, total P&L, and avg P&L per regime for the last N days.
        """
        ...
```

### Scheduled Jobs

Five new cron jobs support the Market Regime Detection system:

| Time (IST) | Job ID | Method | Purpose |
|------------|--------|--------|---------|
| 08:45 Mon-Fri | `morning_brief` | `app.send_morning_brief()` | Generate and send pre-market morning brief with global cues, India context, regime prediction, and watchlist alerts |
| 09:30 Mon-Fri | `regime_classify` | `app.classify_regime()` | Initial regime classification for the day using VIX, gap, range, and alignment data |
| 11:00 Mon-Fri | `regime_reclass_11` | `app.check_regime_reclassify_11()` | First re-classification check: VIX spike trigger |
| 13:00 Mon-Fri | `regime_reclass_13` | `app.check_regime_reclassify_13()` | Second re-classification check: direction reversal trigger |
| 14:30 Mon-Fri | `regime_reclass_1430` | `app.check_regime_reclassify_1430()` | Third re-classification check: round-trip trigger |

The re-classification jobs call `RegimeDataCollector.collect_regime_inputs()`
to gather fresh data, then `MarketRegimeClassifier.check_reclassify()` to
determine whether conditions warrant a severity upgrade. If the regime
changes, the new classification is persisted via `MarketRegimeRepository`
and a notification is sent to Telegram.

### Telegram Commands

Five new Telegram commands provide regime visibility and control:

| Command | Handler | Description |
|---------|---------|-------------|
| `REGIME` | `handle_regime_command()` | Show current regime classification with scores, confidence, strategy weights, and modifier values |
| `REGIME HISTORY` | `handle_regime_history_command()` | Show last 7 days of regime classifications with daily summaries |
| `REGIME OVERRIDE <type>` | `handle_regime_override_command()` | Manual override to force a specific regime (TRENDING, RANGING, or VOLATILE) for the remainder of the session |
| `VIX` | `handle_vix_command()` | Show current India VIX value with interpretation (low/moderate/high/extreme) |
| `MORNING` | `handle_morning_command()` | Show cached morning brief (the same brief sent at 8:45 AM) |

**REGIME command output example:**

```
MARKET REGIME -- 28 Feb 2026

Classification: TRENDING (78% confidence)
Type: initial (classified at 09:30)

SCORES
  Trending: 0.72  |  Ranging: 0.41  |  Volatile: 0.35

INPUTS
  India VIX: 13.8  |  Nifty Gap: +0.82%
  First-15 Range: 0.95%  |  Direction: UP
  S&P 500: +0.45%  |  Alignment: 0.78

MODIFIERS (Active)
  Strategy Weights: GapGo 45% / ORB 35% / VWAP 20%
  Min Stars: 3  |  Position Modifier: 1.00x
  Max Positions: 8

Reclassifications today: 0/2
```

### Dashboard API Routes (Phase 4 MRD)

**File:** `signalpilot/dashboard/routes/regime.py`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/regime/current` | Current regime classification with full details (scores, inputs, modifiers, confidence) |
| `GET` | `/api/regime/history?days=7` | Classification history for the last N days (one entry per day, latest classification) |
| `GET` | `/api/regime/performance?days=30` | Performance breakdown by regime (signals, trades, win rate, P&L per regime) |
| `GET` | `/api/regime/morning-brief` | Morning brief status (cached brief text, generation timestamp) |

### Configuration

Twenty-six new `AppConfig` fields control regime detection behavior. All are
prefixed with `regime_` and have sensible defaults for safe rollout:

**Feature Flags:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `regime_enabled` | `bool` | `True` | Kill switch — disables all regime detection |
| `regime_shadow_mode` | `bool` | `True` | Classify and log but do not apply modifiers to pipeline |

**Classification Thresholds:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `regime_confidence_threshold` | `float` | `0.55` | Score above this = high confidence modifiers; below = low confidence |
| `regime_max_reclassifications` | `int` | `2` | Maximum re-classifications allowed per trading day |
| `regime_vix_spike_threshold` | `float` | `3.0` | VIX point increase required to trigger re-classification |
| `regime_roundtrip_threshold` | `float` | `0.003` | Nifty distance from open (as decimal) to trigger round-trip re-classification |

**Strategy Weight Matrices (JSON strings):**

| Field | Default | Description |
|-------|---------|-------------|
| `regime_trending_high_weights` | `'{"gap_go":0.45,"orb":0.35,"vwap":0.20}'` | Strategy weights for TRENDING + high confidence |
| `regime_trending_low_weights` | `'{"gap_go":0.40,"orb":0.35,"vwap":0.25}'` | Strategy weights for TRENDING + low confidence |
| `regime_ranging_high_weights` | `'{"gap_go":0.20,"orb":0.30,"vwap":0.50}'` | Strategy weights for RANGING + high confidence |
| `regime_ranging_low_weights` | `'{"gap_go":0.25,"orb":0.30,"vwap":0.45}'` | Strategy weights for RANGING + low confidence |
| `regime_volatile_high_weights` | `'{"gap_go":0.25,"orb":0.25,"vwap":0.25}'` | Strategy weights for VOLATILE + high confidence |
| `regime_volatile_low_weights` | `'{"gap_go":0.30,"orb":0.30,"vwap":0.30}'` | Strategy weights for VOLATILE + low confidence |

**Position Modifiers:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `regime_trending_position_modifier` | `float` | `1.0` | Full position size in trending markets |
| `regime_ranging_position_modifier` | `float` | `0.85` | 15% reduction in ranging markets |
| `regime_volatile_position_modifier` | `float` | `0.65` | 35% reduction in volatile markets |

**Max Positions:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `regime_trending_max_positions` | `int` | `8` | Max simultaneous positions in trending markets |
| `regime_ranging_max_positions` | `int` | `6` | Max simultaneous positions in ranging markets |
| `regime_volatile_max_positions` | `int` | `4` | Max simultaneous positions in volatile markets |

**Minimum Star Ratings:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `regime_trending_min_stars` | `int` | `3` | Min stars required for TRENDING (high confidence) |
| `regime_ranging_high_min_stars` | `int` | `4` | Min stars required for RANGING (high confidence) |
| `regime_ranging_low_min_stars` | `int` | `3` | Min stars required for RANGING (low confidence) |
| `regime_volatile_high_min_stars` | `int` | `5` | Min stars required for VOLATILE (high confidence) |
| `regime_volatile_low_min_stars` | `int` | `4` | Min stars required for VOLATILE (low confidence) |

### Wiring in `create_app()`

The regime detection components are created and injected in `main.py` as part
of the `create_app()` dependency wiring:

```python
# 1. Repositories
regime_repo = MarketRegimeRepository(connection)
regime_perf_repo = RegimePerformanceRepository(connection)

# 2. Data collector
regime_data_collector = RegimeDataCollector(config)

# 3. Classifier
regime_classifier = MarketRegimeClassifier(config)

# 4. Morning brief generator
morning_brief = MorningBriefGenerator(regime_data_collector, watchlist_repo, config)

# 5. Inject into SignalPilotBot
bot = SignalPilotBot(
    ...,
    regime_classifier=regime_classifier,
    regime_repo=regime_repo,
    regime_perf_repo=regime_perf_repo,
    regime_data_collector=regime_data_collector,
    morning_brief=morning_brief,
)

# 6. Inject into SignalPilotApp
app = SignalPilotApp(
    ...,
    regime_classifier=regime_classifier,
    regime_repo=regime_repo,
    regime_perf_repo=regime_perf_repo,
    regime_data_collector=regime_data_collector,
    morning_brief=morning_brief,
)

# 7. Insert RegimeContextStage at position 2 in pipeline
signal_stages = [
    CircuitBreakerGateStage(...),
    RegimeContextStage(regime_classifier, config),   # <-- new, position 2
    StrategyEvalStage(...),
    GapStockMarkingStage(...),
    DeduplicationStage(...),
    ConfidenceStage(...),
    CompositeScoringStage(...),
    AdaptiveFilterStage(...),
    RankingStage(...),
    NewsSentimentStage(...),
    RiskSizingStage(...),
    PersistAndDeliverStage(...),
    DiagnosticStage(...),
]
```

---

## 18. Step 11 — Capital Allocation

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

## 19. Step 12 — Database Persistence

### File: `signalpilot/db/database.py`

SQLite with **WAL mode** and **foreign keys** enabled via pragma. Uses
`aiosqlite` with `Row` factory for named column access.

### Fourteen Tables (5 core + 3 Phase 3 + 2 Phase 4 + 2 Phase 4 NSF + 2 Phase 4 MRD)

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
    strategy_specific_score REAL,              -- Phase 2: composite score
    news_sentiment_score    REAL,              -- Phase 4 NSF: composite sentiment score
    news_sentiment_label    TEXT,              -- Phase 4 NSF: STRONG_NEGATIVE / MILD_NEGATIVE / NEUTRAL / POSITIVE / NO_NEWS
    news_top_headline       TEXT,              -- Phase 4 NSF: most relevant headline
    news_action             TEXT,              -- Phase 4 NSF: suppress / downgrade / pass / badge / unsuppressed
    original_star_rating    INTEGER,           -- Phase 4 NSF: star rating before downgrade (NULL if not downgraded)
    market_regime           TEXT,              -- Phase 4 MRD: "TRENDING" / "RANGING" / "VOLATILE"
    regime_confidence       REAL,              -- Phase 4 MRD: regime confidence 0.0-1.0
    regime_weight_modifier  REAL               -- Phase 4 MRD: position weight modifier applied
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

#### `hybrid_scores` table (Phase 3)

```sql
CREATE TABLE hybrid_scores (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id               INTEGER NOT NULL REFERENCES signals(id),
    composite_score         REAL NOT NULL DEFAULT 0.0,
    strategy_strength_score REAL NOT NULL DEFAULT 0.0,
    win_rate_score          REAL NOT NULL DEFAULT 0.0,
    risk_reward_score       REAL NOT NULL DEFAULT 0.0,
    confirmation_bonus      REAL NOT NULL DEFAULT 0.0,
    confirmed_by            TEXT,
    confirmation_level      TEXT NOT NULL DEFAULT 'single',
    position_size_multiplier REAL NOT NULL DEFAULT 1.0,
    created_at              TEXT
);
```

#### `circuit_breaker_log` table (Phase 3)

```sql
CREATE TABLE circuit_breaker_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT NOT NULL,
    sl_count        INTEGER NOT NULL DEFAULT 0,
    triggered_at    TEXT,
    resumed_at      TEXT,
    manual_override INTEGER NOT NULL DEFAULT 0,
    override_at     TEXT
);
```

#### `adaptation_log` table (Phase 3)

```sql
CREATE TABLE adaptation_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT NOT NULL,
    strategy    TEXT NOT NULL,
    event_type  TEXT NOT NULL,
    details     TEXT NOT NULL DEFAULT '',
    old_weight  REAL,
    new_weight  REAL,
    created_at  TEXT
);
```

#### Phase 3 Columns Added to Existing Tables

The Phase 3 migration adds new columns to existing tables:

- **`signals` table:** `composite_score`, `confirmation_level`, `confirmed_by`,
  `position_size_multiplier`, `adaptation_status`
- **`user_config` table:** `circuit_breaker_limit`, `confidence_boost_enabled`,
  `adaptive_learning_enabled`, `auto_rebalance_enabled`, `adaptation_mode`

#### Phase 3 Migration

`DatabaseManager._run_phase3_migration()` is idempotent, following the same
pattern as the Phase 2 migration. It uses `PRAGMA table_info()` to check
column existence before adding new columns to `signals` and `user_config`,
and creates the `hybrid_scores`, `circuit_breaker_log`, and `adaptation_log`
tables.

#### `signal_actions` table (Phase 4)

```sql
CREATE TABLE signal_actions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id           INTEGER NOT NULL REFERENCES signals(id),
    action              TEXT    NOT NULL,    -- "taken", "skip", "watch"
    reason              TEXT,               -- skip reason: "no_capital", "low_confidence", "sector", "other"
    response_time_ms    INTEGER,            -- ms from signal creation to action
    acted_at            TEXT    NOT NULL,
    message_id          INTEGER             -- Telegram message ID for keyboard update
);
-- Index: idx_signal_actions_signal_id
```

#### `watchlist` table (Phase 4)

```sql
CREATE TABLE watchlist (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol              TEXT    NOT NULL,
    signal_id           INTEGER REFERENCES signals(id),
    strategy            TEXT    NOT NULL,
    entry_price         REAL    NOT NULL,
    added_at            TEXT    NOT NULL,
    expires_at          TEXT    NOT NULL,    -- default: added_at + 5 days
    triggered_count     INTEGER NOT NULL DEFAULT 0,
    last_triggered_at   TEXT
);
-- Index: idx_watchlist_symbol
```

#### `news_sentiment_cache` table (Phase 4 NSF)

```sql
CREATE TABLE news_sentiment_cache (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code              TEXT    NOT NULL,
    composite_score         REAL    NOT NULL,
    label                   TEXT    NOT NULL,    -- "STRONG_NEGATIVE", "MILD_NEGATIVE", "NEUTRAL", "POSITIVE", "NO_NEWS"
    headline_count          INTEGER NOT NULL DEFAULT 0,
    top_headline            TEXT,
    top_negative_headline   TEXT,
    model_used              TEXT    NOT NULL DEFAULT 'vader',
    fetched_at              TEXT    NOT NULL,
    expires_at              TEXT    NOT NULL
);
-- Indexes: idx_news_sentiment_stock_code, idx_news_sentiment_expires
```

#### `earnings_calendar` table (Phase 4 NSF)

```sql
CREATE TABLE earnings_calendar (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code              TEXT    NOT NULL,
    earnings_date           TEXT    NOT NULL,
    quarter                 TEXT,              -- e.g., "Q3FY26"
    is_confirmed            INTEGER NOT NULL DEFAULT 0,
    source                  TEXT,              -- "csv", "screener_api"
    updated_at              TEXT    NOT NULL,
    UNIQUE(stock_code, earnings_date)
);
-- Index: idx_earnings_stock_date
```

#### Phase 4 NSF Migration

`DatabaseManager._run_phase4_nsf_migration()` is idempotent, following the
same pattern as the Phase 2 and Phase 3 migrations. It uses
`PRAGMA table_info()` to check column existence before adding new columns
to the `signals` table (`news_sentiment_score`, `news_sentiment_label`,
`news_top_headline`, `news_action`, `original_star_rating`) and creates
the `news_sentiment_cache` and `earnings_calendar` tables.

#### `market_regimes` table (Phase 4 MRD)

```sql
CREATE TABLE market_regimes (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    date                    TEXT    NOT NULL,
    regime                  TEXT    NOT NULL,
    confidence              REAL    NOT NULL,
    trending_score          REAL    NOT NULL,
    ranging_score           REAL    NOT NULL,
    volatile_score          REAL    NOT NULL,
    vix_score               REAL    NOT NULL,
    gap_score               REAL    NOT NULL,
    range_score             REAL    NOT NULL,
    alignment_score         REAL    NOT NULL,
    india_vix               REAL,
    nifty_gap_pct           REAL,
    nifty_range_pct         REAL,
    nifty_direction         TEXT,
    sp500_change_pct        REAL,
    strategy_weights        TEXT,
    min_stars               INTEGER NOT NULL,
    position_modifier       REAL    NOT NULL,
    max_positions           INTEGER NOT NULL,
    classified_at           TEXT    NOT NULL,
    classification_type     TEXT    NOT NULL,
    reclassification_trigger TEXT,
    previous_regime         TEXT
);
-- Indexes: idx_market_regimes_date, idx_market_regimes_regime
```

#### `regime_performance` table (Phase 4 MRD)

```sql
CREATE TABLE regime_performance (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    date                TEXT    NOT NULL,
    regime              TEXT    NOT NULL,
    strategy            TEXT    NOT NULL,
    signals_generated   INTEGER NOT NULL DEFAULT 0,
    signals_taken       INTEGER NOT NULL DEFAULT 0,
    wins                INTEGER NOT NULL DEFAULT 0,
    losses              INTEGER NOT NULL DEFAULT 0,
    total_pnl           REAL    NOT NULL DEFAULT 0.0,
    win_rate            REAL    NOT NULL DEFAULT 0.0,
    avg_pnl             REAL    NOT NULL DEFAULT 0.0
);
-- Index: idx_regime_performance_date
```

#### Phase 4 MRD Columns Added to Existing Tables

The Phase 4 MRD migration adds three nullable columns to the `signals` table:

- **`signals` table:** `market_regime`, `regime_confidence`, `regime_weight_modifier`

#### Phase 4 MRD Migration

`DatabaseManager._run_phase4_mrd_migration()` is idempotent, following the
same pattern as earlier migrations. It uses `PRAGMA table_info()` to check
column existence before adding new columns to the `signals` table
(`market_regime`, `regime_confidence`, `regime_weight_modifier`) and creates
the `market_regimes` and `regime_performance` tables with their indexes.

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
| `insert_signal(record)` | Insert signal (23 fields incl. NSF metadata), returns row ID |
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

**SignalActionRepository** (`signal_action_repo.py`) — Phase 4:

| Method | Description |
|--------|-------------|
| `insert_action(record)` | Record button press (taken/skip/watch) with response time |
| `get_actions_for_signal(signal_id)` | All actions on a specific signal |
| `get_average_response_time(days=30)` | Average ms from signal creation to user action |
| `get_skip_reason_distribution(days=30)` | `dict[reason_code, count]` for analytics |
| `get_action_summary(date)` | `{"taken": N, "skip": N, "watch": N}` for a date |
| `get_response_time_distribution(days=30)` | Distribution of response times |

**WatchlistRepository** (`watchlist_repo.py`) — Phase 4:

| Method | Description |
|--------|-------------|
| `add_to_watchlist(record)` | Add stock with 5-day expiry |
| `get_active_watchlist(now)` | All non-expired entries |
| `is_on_watchlist(symbol, now)` | Check if stock is being watched |
| `remove_from_watchlist(symbol)` | Manual removal |
| `increment_trigger(symbol, now)` | Bump triggered_count when stock re-signals |
| `cleanup_expired(now)` | Remove expired entries |

**NewsSentimentRepository** (`news_sentiment_repo.py`) — Phase 4 NSF:

| Method | Description |
|--------|-------------|
| `upsert(stock_code, result)` | Insert or update cached sentiment result with TTL |
| `get(stock_code)` | Retrieve cached sentiment (returns `None` if expired) |
| `get_batch(stock_codes)` | Retrieve cached sentiments for multiple stocks |
| `purge_expired(now)` | Remove all entries with `expires_at < now` |
| `purge_all()` | Clear entire cache (used during daily summary cleanup) |

**EarningsCalendarRepository** (`earnings_repo.py`) — Phase 4 NSF:

| Method | Description |
|--------|-------------|
| `upsert(record)` | Insert or update an earnings date entry |
| `has_earnings_today(stock_code, date)` | Check if stock has earnings on the given date |
| `get_upcoming(days_ahead)` | All earnings within N days from today |
| `bulk_upsert(records)` | Batch insert/update earnings records (CSV import or API ingest) |

---

## 20. Step 13 — Telegram Delivery

### Files: `signalpilot/telegram/bot.py`, `formatters.py`, `keyboards.py`

`SignalPilotBot.send_signal()` formats the `FinalSignal` into an HTML Telegram
message with **inline action buttons** (Phase 4) and sends it to the configured
`chat_id`. All handlers are restricted to the configured `chat_id` via
`filters.Chat(chat_id=int(self._chat_id))`.

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
[ TAKEN ]  [ SKIP ]  [ WATCH ]       <-- Phase 4 inline buttons
```

**News sentiment annotations** (Phase 4 NSF): When `news_enabled` is active,
the signal message includes sentiment information:
- **MILD_NEGATIVE:** A warning block is appended:
  `"News Warning: Mild negative sentiment (-0.35) -- headline text"`
  The star rating is shown as downgraded (e.g., "***-- (Moderate, downgraded from Strong)").
- **POSITIVE:** A positive badge is appended:
  `"News: Positive sentiment (+0.52) -- headline text"`
- **NO_NEWS:** A note is appended: `"Note: No recent news found for this stock."`
- **NEUTRAL:** No additional annotation.

**Paper mode:** Adds `PAPER TRADE` prefix so the user knows it is a simulation.

**VWAP Reclaim:** Adds a `Higher Risk` warning for the riskier setup type.

**Strategy display:** Shows setup type when available, e.g.,
"VWAP Reversal (Uptrend Pullback)".

**Latency check:** A warning is logged if delivery takes more than 30 seconds
from signal generation time.

#### Exit Alert Formats

| Exit Type | Header | Body | Keyboard (Phase 4) |
|-----------|--------|------|--------------------|
| `SL_HIT` | "STOP LOSS HIT -- {symbol}" | "Exit immediately." + P&L | — |
| `TRAILING_SL_HIT` | "TRAILING SL HIT -- {symbol}" | "Exit immediately." + P&L | — |
| `T1_HIT` | "TARGET 1 HIT -- {symbol}" | "Consider booking partial profit." | `[ Book 50% at T1 ]` |
| `T2_HIT` | "TARGET 2 HIT -- {symbol}" | "Full exit recommended." + P&L | `[ Exit Remaining at T2 ]` |
| `TIME_EXIT` (advisory) | "TIME EXIT REMINDER" | "Market closing soon. Consider closing." | `[ Exit Now ] [ Hold ]` |
| `TIME_EXIT` (mandatory) | "MANDATORY EXIT" | "Position closed at X (market closing)." | — |
| Trailing SL Update | "TRAILING SL UPDATE" | "New SL: X" + current price + P&L | — |
| SL Approaching | "SL APPROACHING" | "Price nearing stop loss." | `[ Exit Now ] [ Hold ]` |
| Near T2 | "NEAR TARGET 2" | "Price approaching T2." | `[ Take Profit ] [ Let It Run ]` |

#### Star Rating Display

```
1 star:  *---- (Weak)
2 stars: **--- (Fair)
3 stars: ***-- (Moderate)
4 stars: ****- (Strong)
5 stars: ***** (Very Strong)
```

---

## 21. Step 14 — Exit Monitoring

### File: `signalpilot/monitor/exit_monitor.py`

On every scan-loop iteration, the **ExitMonitoringStage** (always-run pipeline
stage) checks all active trades:

```python
# Inside ExitMonitoringStage.process():
active_trades = await self._trade_repo.get_active_trades()
for trade in active_trades:
    alert = await self._exit_monitor.check_trade(trade)
    if alert:
        await self._event_bus.emit(ExitAlertEvent(alert))
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

# Emit events via EventBus for cross-component notification:
await self._event_bus.emit(ExitAlertEvent(alert))           # --> bot delivery
if exit_type in (SL_HIT, TRAILING_SL_HIT):
    await self._event_bus.emit(StopLossHitEvent(...))       # --> circuit breaker
await self._event_bus.emit(TradeExitedEvent(...))           # --> adaptive manager
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

## 22. Step 15 — Telegram Commands (User Interaction)

### File: `signalpilot/telegram/handlers.py`

The bot listens for text messages in the configured chat and dispatches to
handler functions. All commands are case-insensitive.

| Command | Regex Pattern | Action |
|---------|--------------|--------|
| `TAKEN [FORCE] [id]` | `(?i)^/?taken(?:\s+force)?(?:\s+(\d+))?$` | Mark a signal as a trade (optionally by signal ID); FORCE overrides position limit |
| `STATUS` | `(?i)^status$` | Show active signals, open trades with live P&L, and circuit breaker status |
| `JOURNAL` | `(?i)^journal$` | Display performance metrics with per-strategy breakdown (win rate, P&L, risk-reward) |
| `CAPITAL <amt>` | `(?i)^capital\s+\d+(?:\.\d+)?$` | Update total trading capital |
| `PAUSE <strat>` | `(?i)^pause\s+\w+$` | Disable a strategy (GAP/ORB/VWAP) |
| `RESUME <strat>` | `(?i)^resume\s+\w+$` | Re-enable a paused strategy |
| `ALLOCATE` | `(?i)^allocate` | Show/set capital allocation (AUTO or manual) |
| `STRATEGY` | `(?i)^strategy$` | Show 30-day per-strategy performance breakdown |
| `OVERRIDE` | `(?i)^override$` | Override circuit breaker, resume signals (requires confirmation) |
| `SCORE <sym>` | `(?i)^score\s+\w+$` | Show composite score breakdown for a symbol's latest signal |
| `ADAPT` | `(?i)^adapt$` | Show per-strategy adaptation status (normal/throttled/paused) |
| `REBALANCE` | `(?i)^rebalance$` | Trigger immediate capital rebalance across strategies |
| `NEWS [STOCK\|ALL]` | `(?i)^news(?:\s+\w+)?$` | Show news sentiment for a specific stock or all cached results (Phase 4 NSF) |
| `EARNINGS` | `(?i)^earnings$` | Show upcoming earnings dates for Nifty 500 stocks (Phase 4 NSF) |
| `UNSUPPRESS <STOCK>` | `(?i)^unsuppress\s+\w+$` | Override news sentiment suppression for a stock for the current session (Phase 4 NSF) |
| `REGIME` | `(?i)^regime$` | Show current regime classification with scores, confidence, and modifiers (Phase 4 MRD) |
| `REGIME HISTORY` | `(?i)^regime\s+history$` | Show last 7 days of regime classifications (Phase 4 MRD) |
| `REGIME OVERRIDE <type>` | `(?i)^regime\s+override\s+(trending\|ranging\|volatile)$` | Manual regime override for the session (Phase 4 MRD) |
| `VIX` | `(?i)^vix$` | Show current India VIX with interpretation (Phase 4 MRD) |
| `MORNING` | `(?i)^morning$` | Show cached morning brief from 8:45 AM (Phase 4 MRD) |
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

#### Phase 3 Commands

**OVERRIDE** — Circuit Breaker Override

Resets the circuit breaker and resumes signal generation. The bot asks for
confirmation before proceeding. Once confirmed, sets `_overridden = True` on
the circuit breaker instance and logs the override to the
`circuit_breaker_log` table.

**SCORE \<symbol\>** — Composite Score Breakdown

Shows the composite score breakdown for the latest signal of the given
symbol, including all four factor scores (strategy strength, win rate,
risk-reward, confirmation bonus), the final composite score, star rating,
and confirmation level.

**ADAPT** — Adaptation Status

Displays the current adaptation level for each strategy (`NORMAL`,
`REDUCED`, or `PAUSED`), along with the consecutive loss count and trailing
win rate statistics.

**REBALANCE** — Immediate Capital Rebalance

Triggers an immediate capital rebalance across strategies (the same logic
that runs weekly on Sundays at 18:00). Recalculates expectancy-weighted
allocations and sends the updated allocation summary.

#### Phase 4 NSF Commands

**NEWS [STOCK|ALL]** — News Sentiment Lookup

Shows the current news sentiment for a specific stock or all cached results.
When called with a stock code (e.g., `NEWS RELIANCE`), displays the composite
score, label, headline count, top headline, and top negative headline. When
called with `NEWS ALL`, shows a summary of all stocks with cached sentiment
results. When called without arguments, shows sentiment for stocks in the
current watchlist and active signals.

**EARNINGS** — Upcoming Earnings Calendar

Displays upcoming earnings dates for Nifty 500 stocks within the next 7 days.
Shows stock code, earnings date, quarter, and confirmation status. Helps the
user anticipate which stocks may be subject to earnings blackout suppression.

**UNSUPPRESS \<STOCK\>** — Override Sentiment Suppression

Creates a session-scoped override that allows a specific stock to pass
through the news sentiment filter regardless of its sentiment score for the
remainder of the current trading session. The override is cleared automatically
during the daily summary job at 15:30. Example: `UNSUPPRESS RELIANCE` allows
RELIANCE signals through even with strong negative sentiment. The signal
will be tagged with the `UNSUPPRESSED` action in the database.

#### Phase 4 MRD Commands

**REGIME** — Current Regime Classification

Shows the current market regime classification including all three regime
scores, confidence level, input values (VIX, gap, range, direction,
alignment), and the active modifiers (strategy weights, min stars, position
modifier, max positions). Also displays the number of re-classifications
performed today and whether the system is in shadow mode or active mode.

**REGIME HISTORY** — Regime History

Shows the last 7 days of regime classifications. For each day, displays the
final regime (after any re-classifications), confidence, key inputs, and
whether any re-classifications occurred during the session.

**REGIME OVERRIDE \<type\>** — Manual Regime Override

Forces the market regime to a specific type (TRENDING, RANGING, or VOLATILE)
for the remainder of the trading session. The override is applied immediately
and all pipeline modifiers are updated accordingly. The override is recorded
in the `market_regimes` table with `classification_type = "override"`. The
override persists until end of day; the `reset_daily()` method clears it at
the start of the next session.

**VIX** — India VIX Display

Shows the current India VIX value along with an interpretation: low (< 14),
moderate (14-18), high (18-24), or extreme (> 24). Also shows the VIX change
from the previous close and the VIX score used in regime classification.

**MORNING** — Cached Morning Brief

Displays the morning brief that was generated and sent at 8:45 AM. Includes
global cues (S&P 500, NASDAQ, Dow, SGX Nifty, Asia markets, crude, USD/INR),
India context (VIX, FII/DII flows), regime prediction, and watchlist alerts.
Returns "No morning brief available" if accessed before 8:45 AM.

---

## 23. Step 15.5 — Inline Button Callbacks & Quick Actions (Phase 4)

### Files: `signalpilot/telegram/keyboards.py`, `handlers.py`, `db/signal_action_repo.py`, `db/watchlist_repo.py`

Phase 4 adds **inline keyboard buttons** to every signal and exit alert,
replacing the text-based `TAKEN` command flow with one-tap actions. User
actions are tracked for analytics (response time, skip reasons).

### Inline Keyboards

#### Signal Keyboards

**`build_signal_keyboard(signal_id)`** — attached to every delivered signal:

```
[ TAKEN ]  [ SKIP ]  [ WATCH ]
```

Callback data: `taken:{signal_id}`, `skip:{signal_id}`, `watch:{signal_id}`

**`build_skip_reason_keyboard(signal_id)`** — shown after SKIP (2x2 grid):

```
[ No Capital ]        [ Low Confidence ]
[ Already In Sector ] [ Other ]
```

Callback data: `skip_reason:{signal_id}:{reason_code}`

#### Exit Alert Keyboards

**`build_t1_keyboard(trade_id)`** — when Target 1 is reached:

```
[ Book 50% at T1 ]
```

**`build_t2_keyboard(trade_id)`** — when Target 2 is reached:

```
[ Exit Remaining at T2 ]
```

**`build_sl_approaching_keyboard(trade_id)`** — when SL is being approached:

```
[ Exit Now ]  [ Hold ]
```

**`build_near_t2_keyboard(trade_id)`** — when price is near T2 but not hit:

```
[ Take Profit ]  [ Let It Run ]
```

### Callback Handlers

All callback handlers return `CallbackResult(answer_text, success, status_line, new_keyboard)`.

#### Signal Action Callbacks

| Handler | Trigger | Action |
|---------|---------|--------|
| `handle_taken_callback()` | TAKEN button | Create trade, start exit monitoring, record action + response time |
| `handle_skip_callback()` | SKIP button | Show skip reason keyboard |
| `handle_skip_reason_callback()` | Reason button | Mark signal as skipped, record reason + response time |
| `handle_watch_callback()` | WATCH button | Add to watchlist (5-day expiry), record action |

#### Trade Management Callbacks

| Handler | Trigger | Action |
|---------|---------|--------|
| `handle_partial_exit_callback()` | Book 50% at T1 | Partial exit at T1 price |
| `handle_exit_now_callback()` | Exit Now | Close trade at current price, persist P&L |
| `handle_take_profit_callback()` | Take Profit | Close trade at current price (near T2) |
| `handle_hold_callback()` | Hold | Dismiss SL-approaching alert |
| `handle_let_run_callback()` | Let It Run | Dismiss near-T2 alert, continue trailing |

### Signal Action Tracking

**File:** `signalpilot/db/signal_action_repo.py`

Every button press is recorded in the `signal_actions` table:

```python
@dataclass
class SignalActionRecord:
    signal_id: int                    # which signal
    action: str                       # "taken", "skip", "watch"
    reason: str | None                # skip reason code (no_capital, low_confidence, sector, other)
    response_time_ms: int | None      # time from signal creation to action
    acted_at: datetime | None
    message_id: int | None
```

**Analytics queries:**

| Method | Returns |
|--------|---------|
| `get_average_response_time(days=30)` | Average ms from signal to user action |
| `get_skip_reason_distribution(days=30)` | `dict[reason_code, count]` |
| `get_action_summary(date)` | `{"taken": N, "skip": N, "watch": N}` |
| `get_response_time_distribution(days=30)` | Distribution of response times |

### Watchlist

**File:** `signalpilot/db/watchlist_repo.py`

Stocks added via the WATCH button are tracked for re-alerting on future signals.

```python
@dataclass
class WatchlistRecord:
    symbol: str
    signal_id: int | None             # original signal that triggered watchlist add
    strategy: str
    entry_price: float
    added_at: datetime | None
    expires_at: datetime | None       # default: now + 5 days
    triggered_count: int = 0          # times re-alerted for same symbol
    last_triggered_at: datetime | None = None
```

**Key methods:**

| Method | Description |
|--------|-------------|
| `add_to_watchlist(record)` | Add stock with 5-day expiry |
| `get_active_watchlist(now)` | All non-expired entries |
| `is_on_watchlist(symbol, now)` | Check if stock is being watched |
| `remove_from_watchlist(symbol)` | Manual removal |
| `increment_trigger(symbol, now)` | Called when watched stock generates new signal |
| `cleanup_expired(now)` | Remove expired entries |

**Telegram commands:** `/watchlist` shows all active entries, `/unwatch SYMBOL`
removes a stock.

---

## 24. Step 16 — Daily Wind-Down & Summary

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

## 25. Step 17 — Shutdown & Crash Recovery

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

## 26. Step 18 — Dashboard (Phase 3)

### Files: `signalpilot/dashboard/` (backend), `frontend/` (React app)

The web dashboard provides a visual interface for monitoring and managing
SignalPilot. It runs alongside the main application when `dashboard_enabled`
is `True` in configuration.

### Backend — FastAPI

- `create_dashboard_app(db_path, write_connection)` factory creates the
  FastAPI application
- Uses a separate read-only DB connection for queries, shared write
  connection for mutations
- CORS enabled for localhost development

### API Routes

| Prefix | Module | Endpoints |
|--------|--------|-----------|
| `/api/signals` | `signals.py` | GET /live, GET /history |
| `/api/trades` | `trades.py` | GET /, GET /export (CSV download) |
| `/api/performance` | `performance.py` | GET /equity-curve, /daily-pnl, /win-rate, /monthly |
| `/api/strategies` | `strategies.py` | GET /comparison, /confirmed, /pnl-series |
| `/api/allocation` | `allocation.py` | GET /current, GET /history, POST /override, POST /reset |
| `/api/settings` | `settings.py` | GET /, PUT /, PUT /strategies |
| `/api/circuit-breaker` | `circuit_breaker.py` | GET /, POST /override, GET /history |
| `/api/adaptation` | `adaptation.py` | GET /status, GET /log |
| `/api/v1/news` | `news.py` | GET /{stock_code}, GET /suppressed/list (Phase 4 NSF) |
| `/api/v1/earnings` | `news.py` | GET /upcoming (Phase 4 NSF) |
| `/api/regime` | `regime.py` | GET /current, GET /history, GET /performance, GET /morning-brief (Phase 4 MRD) |

### Frontend — React + TypeScript

- **Build tool:** Vite
- **Styling:** Tailwind CSS
- **Data fetching:** React Query with 30-second polling for live data
- **Routing:** React Router with lazy-loaded routes

#### Pages

| Page | Description |
|------|-------------|
| Live Signals | Real-time view of active signals with current prices and P&L |
| Trade Journal | Searchable/filterable trade history with CSV export |
| Performance Charts | Equity curve, daily P&L bar chart, win rate trend, monthly breakdown |
| Strategy Comparison | Side-by-side strategy metrics, confirmed signal analysis |
| Capital Allocation | Current allocation pie chart, allocation history, manual override controls |
| Settings | Configuration editor, strategy enable/disable toggles, circuit breaker controls |

---

## 27. Data Model Chain

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
  [ConfidenceDetector]   <-- (Phase 3) produces ConfirmationResult (level, confirmed_by, multiplier)
    v
  [CompositeScorer]      <-- (Phase 3) produces CompositeScoreResult (composite, factor scores)
    v
RankedSignal             <-- produced by SignalRanker
    | candidate, composite_score, rank (1-N), signal_strength (1-5 stars)
    v
  [RegimeContextStage]   <-- (Phase 4 MRD) sets regime modifiers on ScanContext
    | regime_min_stars filter applied in RankingStage
    | regime_position_modifier applied in RiskSizingStage
    | regime_max_positions override in RiskSizingStage
    v
  [CircuitBreaker]       <-- (Phase 3) gate: blocks signals if SL limit exceeded
    v
  [AdaptiveManager]      <-- (Phase 3) filter: blocks signals from paused strategies
    v
  [NewsSentimentStage]   <-- (Phase 4 NSF) filter/modify: suppress, downgrade, or badge
    | SentimentResult per symbol (score, label, headline, action)
    | STRONG_NEGATIVE --> suppress (remove signal, add to suppressed_signals)
    | MILD_NEGATIVE   --> downgrade (reduce stars by 1, preserve original_star_rating)
    | POSITIVE        --> badge (pass through with positive note)
    | Earnings blackout --> suppress (highest priority)
    v
FinalSignal              <-- produced by RiskManager
    | ranked_signal, quantity, capital_required, expires_at
    v
SignalRecord             <-- persisted to `signals` table
    | id, date, symbol, strategy, entry_price, stop_loss, T1, T2,
    | quantity, capital_required, signal_strength, gap_pct, volume_ratio,
    | reason, created_at, expires_at, status, setup_type, strategy_specific_score
    | + Phase 3: composite_score, confirmation_level, confirmed_by,
    |   position_size_multiplier, adaptation_status
    | + Phase 4 NSF: news_sentiment_score, news_sentiment_label,
    |   news_top_headline, news_action, original_star_rating
    | + Phase 4 MRD: market_regime, regime_confidence, regime_weight_modifier
    v
HybridScoreRecord        <-- (Phase 3) persisted to `hybrid_scores` table
    | signal_id, composite_score, strategy_strength_score, win_rate_score,
    | risk_reward_score, confirmation_bonus, confirmed_by, confirmation_level,
    | position_size_multiplier
    v
TradeRecord              <-- created when user replies TAKEN (15 fields)
    | signal_id, date, symbol, strategy, entry_price, stop_loss, T1, T2,
    | quantity, taken_at, exit_price, pnl_amount, pnl_pct, exit_reason, exited_at

CircuitBreakerRecord     <-- (Phase 3) persisted to `circuit_breaker_log` table
    | date, sl_count, triggered_at, resumed_at, manual_override, override_at

AdaptationLogRecord      <-- (Phase 3) persisted to `adaptation_log` table
    | date, strategy, event_type, details, old_weight, new_weight

SignalActionRecord       <-- (Phase 4) persisted to `signal_actions` table
    | signal_id, action (taken/skip/watch), reason, response_time_ms, acted_at

WatchlistRecord          <-- (Phase 4) persisted to `watchlist` table
    | symbol, signal_id, strategy, entry_price, added_at, expires_at,
    | triggered_count, last_triggered_at

CallbackResult           <-- (Phase 4) return type for inline button callbacks
    | answer_text, success, status_line, new_keyboard

SentimentResult          <-- (Phase 4 NSF) produced by NewsSentimentService
    | score, label, headline, action, headline_count,
    | top_negative_headline, model_used

SuppressedSignal         <-- (Phase 4 NSF) produced by NewsSentimentStage
    | symbol, strategy, original_stars, sentiment_score, sentiment_label,
    | top_headline, reason, entry_price, stop_loss, target_1

EarningsRecord           <-- (Phase 4 NSF) stored in earnings_calendar table
    | stock_code, earnings_date, quarter, is_confirmed, source, updated_at

RegimeClassification     <-- (Phase 4 MRD) produced by MarketRegimeClassifier
    | regime, confidence, trending/ranging/volatile scores, vix/gap/range/alignment scores,
    | india_vix, nifty_gap_pct, nifty_range_pct, nifty_direction, sp500_change_pct,
    | strategy_weights, min_stars, position_modifier, max_positions,
    | classified_at, classification_type, reclassification_trigger, previous_regime

RegimePerformanceRecord  <-- (Phase 4 MRD) persisted to regime_performance table
    | date, regime, strategy, signals_generated, signals_taken,
    | wins, losses, total_pnl, win_rate, avg_pnl

RegimeInputs             <-- (Phase 4 MRD) input to MarketRegimeClassifier
    | india_vix, nifty_gap_pct, nifty_first_15_range_pct, nifty_first_15_direction,
    | directional_alignment, sp500_change_pct, sgx_nifty_change_pct

PreMarketData            <-- (Phase 4 MRD) input to MorningBriefGenerator
    | sp500_close, sp500_change_pct, nasdaq_change_pct, dow_change_pct,
    | sgx_nifty, sgx_nifty_change_pct, asia_markets, india_vix,
    | india_vix_change_pct, fii_net, dii_net, crude_oil, usd_inr
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
| `SignalRecord` | `db/models.py` | 26 fields matching signals table (incl. 5 NSF + 3 MRD fields) |
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
| `ConfirmationResult` | `ranking/confidence.py` | symbol, level (single/double/triple), confirmed_by, multiplier |
| `CompositeScoreResult` | `ranking/composite_scorer.py` | composite_score, strategy_strength, win_rate, risk_reward, confirmation_bonus |
| `HybridScoreRecord` | `db/models.py` | signal_id, composite_score, factor scores, confirmation details |
| `CircuitBreakerRecord` | `db/models.py` | date, sl_count, triggered_at, resumed_at, manual_override |
| `AdaptationLogRecord` | `db/models.py` | date, strategy, event_type, details, old_weight, new_weight |
| `SignalActionRecord` | `db/models.py` | signal_id, action, reason, response_time_ms, acted_at, message_id |
| `WatchlistRecord` | `db/models.py` | symbol, signal_id, strategy, entry_price, added_at, expires_at, triggered_count |
| `CallbackResult` | `db/models.py` | answer_text, success, status_line, new_keyboard |
| `SentimentResult` | `db/models.py` | score, label, headline, action, headline_count, top_negative_headline, model_used |
| `SuppressedSignal` | `db/models.py` | symbol, strategy, original_stars, sentiment_score, sentiment_label, top_headline, reason, entry_price, stop_loss, target_1 |
| `EarningsRecord` | `db/models.py` | stock_code, earnings_date, quarter, is_confirmed, source, updated_at |
| `RegimeClassification` | `db/models.py` | regime, confidence, 4 regime scores, 4 input scores, strategy_weights, min_stars, position_modifier, max_positions, classified_at, classification_type |
| `RegimePerformanceRecord` | `db/models.py` | date, regime, strategy, signals_generated, signals_taken, wins, losses, total_pnl, win_rate, avg_pnl |
| `RegimeInputs` | `intelligence/regime_data.py` | india_vix, nifty_gap_pct, nifty_first_15_range_pct, nifty_first_15_direction, directional_alignment, sp500_change_pct, sgx_nifty_change_pct |
| `PreMarketData` | `intelligence/regime_data.py` | sp500_close, sp500_change_pct, nasdaq_change_pct, dow_change_pct, sgx_nifty, india_vix, fii_net, dii_net, crude_oil, usd_inr |
| `ScanContext` | `pipeline/context.py` | cycle_id, now, phase, accepting_signals, all_candidates, ranked_signals, final_signals, sentiment_results, suppressed_signals, regime, regime_confidence, regime_min_stars, regime_position_modifier, regime_max_positions, regime_strategy_weights |

### Enums

| Enum | Values |
|------|--------|
| `SignalDirection` | `BUY`, `SELL` |
| `ExitType` | `SL_HIT`, `T1_HIT`, `T2_HIT`, `TRAILING_SL_HIT`, `TIME_EXIT` |
| `StrategyPhase` | `PRE_MARKET`, `OPENING`, `ENTRY_WINDOW`, `CONTINUOUS`, `WIND_DOWN`, `POST_MARKET` |
| `ConfirmationLevel` | `SINGLE`, `DOUBLE`, `TRIPLE` |
| `AdaptationLevel` | `NORMAL`, `REDUCED`, `PAUSED` |
| `SentimentLabel` | `STRONG_NEGATIVE`, `MILD_NEGATIVE`, `NEUTRAL`, `POSITIVE`, `NO_NEWS` |
| `SentimentAction` | `SUPPRESS`, `DOWNGRADE`, `PASS`, `BADGE`, `UNSUPPRESSED` |

---

## 28. Logging & Observability

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

## 29. Rate Limiting & Retry

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

## 30. Complete Scan Loop Iteration

### File: `signalpilot/scheduler/lifecycle.py` — `_scan_loop()`

The scan loop delegates all work to the **composable pipeline** (see
[Step 7 — Pipeline Architecture](#8-step-7--strategy-evaluation)):

```
WHILE scanning == True:
  |
  |-- a. Generate 8-char hex cycle_id
  |-- b. set_context(cycle_id, phase)
  |-- c. Build ScanContext(cycle_id, now, phase, accepting_signals)
  |
  |-- d. ctx = await pipeline.run(ctx)
  |   |
  |   |-- SIGNAL STAGES (run if accepting_signals AND phase in OPENING/ENTRY_WINDOW/CONTINUOUS):
  |   |   |
  |   |   1. CircuitBreakerGateStage
  |   |       IF circuit_breaker.is_active: ctx.accepting_signals = False → skip rest
  |   |   2. RegimeContextStage (Phase 4 MRD)
  |   |       Read cached regime classification (O(1) dict lookup)
  |   |       IF no classifier or disabled: pass-through
  |   |       IF shadow mode: set regime/confidence only (for logging)
  |   |       IF active mode: set all 6 ctx fields (regime, confidence,
  |   |       min_stars, position_modifier, max_positions, strategy_weights)
  |   |   3. StrategyEvalStage
  |   |       Fetch user_config, filter enabled strategies, evaluate each
  |   |       --> ctx.all_candidates
  |   |   4. GapStockMarkingStage
  |   |       Mark Gap & Go symbols for ORB/VWAP exclusion
  |   |   5. DeduplicationStage
  |   |       Filter active-trade + same-day signal duplicates
  |   |   6. ConfidenceStage (Phase 3)
  |   |       Detect multi-strategy confirmations --> ctx.confirmation_map
  |   |   7. CompositeScoringStage (Phase 3)
  |   |       4-factor hybrid scoring --> ctx.composite_scores
  |   |   8. AdaptiveFilterStage (Phase 3)
  |   |       Remove signals from paused strategies
  |   |   9. RankingStage
  |   |       Score + rank --> ctx.ranked_signals (1-5 stars)
  |   |       Apply ctx.regime_min_stars filter (Phase 4 MRD)
  |   |   10. NewsSentimentStage (Phase 4 NSF)
  |   |       Fetch/cache sentiment per symbol, apply action matrix:
  |   |       STRONG_NEGATIVE/earnings --> suppress --> ctx.suppressed_signals
  |   |       MILD_NEGATIVE --> downgrade star rating by 1
  |   |       POSITIVE --> badge, NEUTRAL/NO_NEWS --> pass through
  |   |   11. RiskSizingStage
  |   |       Position sizing + capital checks --> ctx.final_signals
  |   |       Apply ctx.regime_position_modifier (Phase 4 MRD)
  |   |       Override max_positions with ctx.regime_max_positions (Phase 4 MRD)
  |   |   12. PersistAndDeliverStage
  |   |       INSERT signals + hybrid_scores + sentiment metadata
  |   |       + regime metadata (market_regime, regime_confidence,
  |   |       regime_weight_modifier) (Phase 4 MRD),
  |   |       send via Telegram with keyboards + regime badge,
  |   |       send suppression notifications for ctx.suppressed_signals
  |   |   13. DiagnosticStage
  |   |       Heartbeat every 60 cycles (~1 min)
  |   |
  |   +-- ALWAYS STAGES (run every cycle):
  |       1. ExitMonitoringStage
  |           active_trades = await trade_repo.get_active_trades()
  |           FOR trade in active_trades:
  |             alert = await exit_monitor.check_trade(trade)
  |             IF alert: event_bus.emit(ExitAlertEvent(alert))
  |
  |-- e. Expire stale signals (30-min window):
  |     count = await signal_repo.expire_stale_signals(now)
  |
  |-- f. On success: consecutive_errors = 0
  |
  |-- EXCEPT any exception:
  |     consecutive_errors += 1
  |     IF consecutive_errors >= 10: --> stop loop, alert via Telegram
  |
  |-- FINALLY: reset_context()
  |
  +-- await asyncio.sleep(1)
```

---

## 31. Summary: A Complete Trading Day

```
08:00  App boots --> AppConfig loaded, logging configured
08:00  create_app() wires 40+ components:
         |-- EventBus + subscriptions (ExitAlert, StopLossHit, TradeExited, AlertMessage)
         |-- ScanPipeline (13 signal stages + 1 always stage)
         |-- Phase 3 intelligence layer (CircuitBreaker, AdaptiveManager, CompositeScorer)
         |-- Phase 4 quick actions (SignalActionRepo, WatchlistRepo, inline keyboards)
         |-- Phase 4 NSF intelligence module (SentimentEngine, NewsFetcher,
         |   NewsSentimentService, EarningsCalendar, NewsSentimentRepo, EarningsRepo)
         +-- Phase 4 MRD intelligence module (RegimeDataCollector,
             MarketRegimeClassifier, MorningBriefGenerator,
             MarketRegimeRepo, RegimePerformanceRepo)
08:00  SmartAPIAuthenticator.authenticate() (TOTP-based 2FA)
08:01  InstrumentManager.load() (Nifty 500 from CSV)
08:01  historical.fetch_previous_day_data()    <-- 499 stocks, batches of 3
08:10  (5s cooldown between API passes)
08:10  historical.fetch_average_daily_volume() <-- 20-day ADV
08:20  ConfigRepository.initialize_default()
08:20  bot.start() --> Telegram polling begins (21 commands + 9 callback handlers)
08:20  MarketScheduler.start() --> 17 cron jobs registered
08:20  (Phase 3) Dashboard starts on configured port if dashboard_enabled

08:30  [CRON] fetch_pre_market_news() (Phase 4 NSF)
         --> Batch-fetch news sentiment for watchlist + Nifty 500 stocks
         --> Cache results in news_sentiment_cache table with TTL

08:45  [CRON] send_morning_brief() (Phase 4 MRD)
         --> MorningBriefGenerator.generate()
         --> Collect global cues (S&P 500, NASDAQ, Dow, SGX Nifty, Asia, crude, USD/INR)
         --> Collect India context (VIX, FII/DII flows)
         --> Predict likely regime (heuristic based on VIX + SGX + S&P 500)
         --> Check watchlist for potential setups
         --> Send formatted brief to Telegram

09:00  [CRON] send_pre_market_alert()
         --> "Signals coming shortly after 9:15 AM"

09:15  [CRON] start_scanning()
         |   _reset_session() --> clear intraday data, reset strategies
         |   (Phase 3) circuit_breaker.reset() --> daily SL counter reset
         |   (Phase 3) adaptive_manager daily state refresh
         |   (Phase 4) watchlist_repo.cleanup_expired()
         |   (Phase 4 MRD) regime_classifier.reset_daily() --> clear cache, reset counter
         |   (Phase 4 MRD) regime_data_collector.reset_session() --> clear caches
         |   websocket.connect() --> subscribe all 500 tokens (Mode 3)
         +-> _scan_loop() starts (every 1 second, via ScanPipeline.run())
               |
               |-- phase = OPENING (9:15-9:30)
               |    +-- GapAndGoStrategy: detect gaps [3%-5%], open > prev_high,
               |        volume >= 50% ADV --> _gap_candidates, _volume_validated
               |    +-- ORB: opening range building (update_opening_range per tick)
               |
               |-- [9:30 CRON] classify_regime() (Phase 4 MRD)
               |    +-- RegimeDataCollector.collect_regime_inputs()
               |        (VIX, gap%, first-15-min range%, directional alignment)
               |    +-- MarketRegimeClassifier.classify(inputs)
               |        --> RegimeClassification (TRENDING/RANGING/VOLATILE + confidence)
               |    +-- Persist to market_regimes table
               |    +-- Send regime notification to Telegram
               |    +-- Pipeline now reads cached regime via RegimeContextStage
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
               +-- SIGNAL STAGES (pipeline, all active phases):
               |    1.  CircuitBreakerGateStage: block if SL limit exceeded
               |    2.  RegimeContextStage (Phase 4 MRD): read cached regime,
               |        set strategy weights, min stars, position modifier
               |    3.  StrategyEvalStage: run enabled strategies
               |    4.  GapStockMarkingStage: mark Gap & Go symbols for exclusion
               |    5.  DeduplicationStage: filter active trades + same-day signals
               |    6.  ConfidenceStage (Phase 3): multi-strategy confirmation
               |    7.  CompositeScoringStage (Phase 3): 4-factor hybrid scoring
               |    8.  AdaptiveFilterStage (Phase 3): block paused strategies
               |    9.  RankingStage: score + rank --> RankedSignal (1-5 stars)
               |        + regime min-stars filter (Phase 4 MRD)
               |    10. NewsSentimentStage (Phase 4 NSF): sentiment filter
               |        STRONG_NEGATIVE/earnings --> suppress signal
               |        MILD_NEGATIVE --> downgrade star rating by 1
               |        POSITIVE --> badge, NEUTRAL/NO_NEWS --> pass through
               |    11. RiskSizingStage: position limits + sizing --> FinalSignal
               |        + regime position modifier + max positions (Phase 4 MRD)
               |    12. PersistAndDeliverStage: INSERT signals + hybrid_scores
               |        + sentiment metadata + regime metadata,
               |        send via Telegram with keyboards + regime badge
               |        [ TAKEN ]  [ SKIP ]  [ WATCH ]
               |        + send suppression notifications for suppressed signals
               |    13. DiagnosticStage: heartbeat every 60 cycles
               |
               +-- ALWAYS STAGE (every tick, all phases 9:15-15:15):
                    ExitMonitoringStage:
                      ExitMonitor.check_trade() for each active trade:
                      |-- SL/trailing SL hit?  --> persist + emit events via EventBus
                      |   +-- StopLossHitEvent --> circuit_breaker.on_sl_hit()
                      |   +-- TradeExitedEvent --> adaptive_manager.on_trade_exit()
                      |   +-- ExitAlertEvent   --> bot.send_exit_alert()
                      |   +-- IF circuit breaker activates: AlertMessageEvent --> bot
                      |-- T2 hit?              --> persist + emit events
                      |   +-- TradeExitedEvent --> adaptive_manager (track wins)
                      |-- T1 hit?              --> advisory alert with
                      |                            [ Book 50% at T1 ] keyboard (Phase 4)
                      +-- Trailing SL update?  --> advisory alert

         (Phase 4) User taps inline buttons on signal/exit messages:
               |-- TAKEN --> handle_taken_callback() --> create trade, record response_time_ms
               |-- SKIP  --> show skip reason keyboard --> record reason + response_time_ms
               |-- WATCH --> handle_watch_callback() --> add to watchlist (5-day expiry)
               +-- Exit buttons (Book T1 / Exit Now / Hold / Let Run) --> manage trade

11:00  [CRON] check_regime_reclassify_11() (Phase 4 MRD)
         --> Collect fresh regime inputs
         --> Check re-classification triggers: VIX spike (>= 3pt increase)
         --> Severity-only upgrade: TRENDING --> RANGING or VOLATILE
         --> Persist + notify if regime changes

11:15  [CRON] refresh_news_cache() (Phase 4 NSF)
         --> Refresh stale sentiment cache entries (re-fetch headlines)

13:00  [CRON] check_regime_reclassify_13() (Phase 4 MRD)
         --> Collect fresh regime inputs
         --> Check re-classification triggers: direction reversal
         --> Severity-only upgrade if warranted
         --> Persist + notify if regime changes

13:15  [CRON] refresh_news_cache() (Phase 4 NSF)
         --> Second mid-day sentiment cache refresh

14:30  [CRON] stop_new_signals() + check_regime_reclassify_1430() (Phase 4 MRD)
         --> _accepting_signals = False (scan loop continues for exits)
         --> Final re-classification check: round-trip trigger
             (Nifty within 0.3% of open price)
         --> Severity-only upgrade if warranted

15:00  [CRON] trigger_exit_reminder()
         --> advisory alerts per open trade (TIME_EXIT, is_alert_only=True)
         --> [ Exit Now ]  [ Hold ] keyboard (Phase 4)

15:15  [CRON] trigger_mandatory_exit()
         --> forced exit for all open trades (persist + alert)

15:30  [CRON] send_daily_summary()
         --> MetricsCalculator.calculate_daily_summary(today)
         --> Per-strategy breakdown (closed trades only)
         --> Cumulative P&L
         --> (Phase 4 NSF) Purge old sentiment cache entries
         --> (Phase 4 NSF) Clear session-scoped unsuppress overrides

15:35  [CRON] shutdown()
         --> WebSocket disconnect, bot stop, DB close, scheduler shutdown

Sunday 18:00  [CRON] weekly_rebalance()
         --> CapitalAllocator.calculate_allocations()
         --> check_auto_pause() (warn if win_rate < 40% after 10+ trades)
         --> (Phase 3) AdaptiveManager.check_trailing_performance()
         |     +-- 5-day win rate < 35%: warning alert
         |     +-- 10-day win rate < 30%: auto-pause recommendation
         --> (Phase 4 NSF) Refresh earnings calendar data
         --> Send allocation summary to Telegram
```
