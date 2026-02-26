# SignalPilot System Flow

Complete architecture and data flow for the SignalPilot intraday signal generation system.
All 27 components across Phase 1, 2, and 3 are represented in a single integrated view.

---

## Comprehensive System Diagram

```
 BOOT SEQUENCE
 ═════════════════════════════════════════════════════════════════════════════════════
    .env file
       │
       ▼
 ┌─────────────┐    ┌────────────────────────────────────────────────────────────┐
 │  AppConfig   │───▶│                    create_app()                           │
 │ (pydantic-   │    │                                                            │
 │  settings)   │    │  Wiring order:                                             │
 └─────────────┘    │  1. DatabaseManager (SQLite WAL, 8 tables)                 │
                     │  2. Repositories (signal, trade, config, metrics,          │
                     │     hybrid_score, circuit_breaker, adaptation_log,         │
                     │     strategy_performance)                                  │
                     │  3. SmartAPIAuthenticator (Angel One TOTP 2FA)             │
                     │  4. InstrumentManager (Nifty 500 CSV)                     │
                     │  5. MarketDataStore (in-memory cache)                     │
                     │  6. HistoricalDataFetcher (Angel One + yfinance)          │
                     │  7. Strategies (GapAndGo, ORB, VWAPReversal)              │
                     │  8. DuplicateChecker                                      │
                     │  9. Scorers (SignalScorer, ORBScorer, VWAPScorer)         │
                     │ 10. SignalRanker                                           │
                     │ 11. ConfidenceDetector + CompositeScorer                  │
                     │ 12. CapitalAllocator + PositionSizer + RiskManager        │
                     │ 13. ExitMonitor (with trailing configs + callbacks)        │
                     │ 14. CircuitBreaker + AdaptiveManager                      │
                     │ 15. SignalPilotBot (Telegram, 13 commands)                │
                     │ 16. WebSocketClient (Angel One feed)                      │
                     │ 17. MarketScheduler (APScheduler, 9 cron jobs)            │
                     │ 18. FastAPI Dashboard (optional, 8 route modules)         │
                     └───────────────────────┬────────────────────────────────────┘
                                             │
                                             ▼
                                    ┌─────────────────┐
                                    │ SignalPilotApp   │
                                    │ (orchestrator)   │
                                    └────────┬────────┘
                                             │
                          ┌──────────────────┼──────────────────┐
                          │                  │                  │
                          ▼                  ▼                  ▼
                   startup()          recover()          shutdown()
                   (normal)        (crash mid-day)       (graceful)


 MARKET SCHEDULE TIMELINE (IST, Mon-Fri, skip NSE holidays)
 ═════════════════════════════════════════════════════════════════════════════════════

  9:00     9:15        9:30         9:45        10:00       11:00
    │        │           │            │            │           │
    ▼        ▼           ▼            ▼            ▼           ▼
 ┌──────┐┌───────┐┌──────────┐┌───────────┐┌──────────┐┌──────────┐
 │PRE-  ││START  ││          ││LOCK       ││          ││          │
 │MARKET││SCAN   ││ Gap&Go   ││OPENING    ││VWAP      ││ORB       │
 │ALERT ││       ││ entry    ││RANGES     ││SCAN      ││WINDOW    │
 │      ││WS conn││ valid.   ││           ││START     ││END       │
 │      ││CB/AM  ││          ││ORB begins ││          ││          │
 │      ││reset  ││          ││           ││          ││          │
 └──────┘└───────┘└──────────┘└───────────┘└──────────┘└──────────┘

    │◄──OPENING──▶│◄ENTRY_WINDOW▶│◄────────── CONTINUOUS ──────────────────────▶│
                                                                                 │
 14:30       15:00       15:15        15:30       15:35        Sun 18:00
    │           │           │            │           │              │
    ▼           ▼           ▼            ▼           ▼              ▼
 ┌──────────┐┌──────────┐┌──────────┐┌──────────┐┌──────────┐┌──────────┐
 │STOP NEW  ││EXIT      ││MANDATORY ││DAILY     ││SHUTDOWN  ││WEEKLY    │
 │SIGNALS   ││REMINDER  ││EXIT      ││SUMMARY   ││          ││REBALANCE │
 │          ││          ││          ││          ││          ││          │
 │_accepting││advisory  ││force     ││metrics + ││WS disc.  ││capital   │
 │=False    ││alerts    ││all close ││strategy  ││bot stop  ││allocator │
 │          ││          ││& persist ││breakdown ││DB close  ││recalc    │
 └──────────┘└──────────┘└──────────┘└──────────┘└──────────┘└──────────┘

    │◄──────────────── WIND_DOWN ──────────────────▶│


 CORE SIGNAL PIPELINE (runs every ~1s during OPENING / ENTRY_WINDOW / CONTINUOUS)
 ═════════════════════════════════════════════════════════════════════════════════════

 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │ Angel One WebSocket (real-time tick feed, reconnect with exponential backoff)   │
 └──────────────────────────────────┬───────────────────────────────────────────────┘
                                    │ TickData per symbol
                                    ▼
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │                        MarketDataStore (in-memory)                               │
 │  ┌────────────┐  ┌──────────────┐  ┌────────────┐  ┌──────────────────────────┐ │
 │  │ Tick Cache  │  │Opening Ranges│  │ VWAP State │  │ 15-min Candles + Hist.  │ │
 │  │ (per symbol)│  │(9:15-9:45)   │  │(cumul.)    │  │ Refs (prev close, ADV)  │ │
 │  └────────────┘  └──────────────┘  └────────────┘  └──────────────────────────┘ │
 └──────────────────────────────────┬───────────────────────────────────────────────┘
                                    │
                                    ▼
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │                     Strategy Evaluation (phase-gated)                            │
 │                                                                                  │
 │  ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────────────┐ │
 │  │    Gap & Go         │  │       ORB           │  │     VWAP Reversal         │ │
 │  │                     │  │                     │  │                           │ │
 │  │ Phases: OPENING,    │  │ Phase: CONTINUOUS   │  │ Phase: CONTINUOUS         │ │
 │  │   ENTRY_WINDOW      │  │ Window: 9:45-11:00  │  │ Window: 10:00-14:30      │ │
 │  │                     │  │                     │  │                           │ │
 │  │ Gap detection,      │  │ 30-min range break, │  │ 2 setups:                │ │
 │  │ volume confirmation,│  │ volume surge,       │  │  uptrend_pullback,       │ │
 │  │ entry validation    │  │ price > range high  │  │  vwap_reclaim            │ │
 │  └─────────┬──────────┘  └─────────┬──────────┘  └────────────┬─────────────┘ │
 │            │                        │                           │               │
 └────────────┼────────────────────────┼───────────────────────────┼───────────────┘
              │                        │                           │
              └────────────────────────┼───────────────────────────┘
                                       │ list[CandidateSignal]
                                       ▼
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │                Phase 3: Confidence Detection                                     │
 │                                                                                  │
 │  Group candidates by symbol, check for multi-strategy agreement:                │
 │  - In-batch: multiple strategies in current scan cycle                          │
 │  - Cross-cycle: recent signals from DB within 15-min window                     │
 │                                                                                  │
 │  Result: single (1x, +0 stars) / double (1.5x, +1 star) / triple (2x, +2)     │
 └──────────────────────────────────┬───────────────────────────────────────────────┘
                                    │ list[CandidateSignal] + confirmation_map
                                    ▼
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │                  Duplicate Checker                                                │
 │                                                                                  │
 │  - Active trade check (skip if symbol already has open position)                │
 │  - Same-day signal check (skip if signal already sent today for symbol+strategy)│
 │  - Multi-confirmation bypass (double/triple confirmations can override dedup)    │
 └──────────────────────────────────┬───────────────────────────────────────────────┘
                                    │ filtered list[CandidateSignal]
                                    ▼
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │                Phase 3: Composite Scoring (4-factor hybrid)                      │
 │                                                                                  │
 │  For each candidate:                                                            │
 │  ┌───────────────────────────────────────────────────────────────────────────┐   │
 │  │ composite = strategy_strength * 0.40  (per-strategy scorer, 0-100)       │   │
 │  │           + win_rate          * 0.30  (trailing 30-day, cached per day)  │   │
 │  │           + risk_reward       * 0.20  (R:R linear map: 1->0, 3->100)    │   │
 │  │           + confirmation      * 0.10  (single=0, double=50, triple=100) │   │
 │  └───────────────────────────────────────────────────────────────────────────┘   │
 │                                                                                  │
 │  Composite score clamped to 0-100, used for ranking and strength estimation     │
 └──────────────────────────────────┬───────────────────────────────────────────────┘
                                    │ composite_scores map
                                    ▼
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │                Signal Ranking                                                    │
 │                                                                                  │
 │  SignalRanker uses composite_scores + confirmations:                             │
 │  - Per-strategy scorers: SignalScorer (Gap&Go), ORBScorer, VWAPScorer           │
 │  - Top-N selection (N = max_positions from config, default 8)                   │
 │  - Star rating: 1-5 stars based on composite score thresholds                   │
 │  - Confirmation star boost applied (+1 for double, +2 for triple, max 5)       │
 └──────────────────────────────────┬───────────────────────────────────────────────┘
                                    │ list[RankedSignal]
                                    ▼
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │                Phase 3: Circuit Breaker Gate                                     │
 │                                                                                  │
 │  If circuit_breaker.is_active == True:                                          │
 │    _accepting_signals = False  (skip signal generation, continue exit monitor)  │
 │                                                                                  │
 │  Triggers at N stop-loss hits/day (default 3), warns at N-1                     │
 │  Manual override via OVERRIDE CIRCUIT command                                   │
 │  Resets daily at 9:15 AM                                                        │
 └──────────────────────────────────┬───────────────────────────────────────────────┘
                                    │ (pass if not active)
                                    ▼
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │                Phase 3: Adaptive Filter                                          │
 │                                                                                  │
 │  Per-strategy state: NORMAL -> REDUCED -> PAUSED                                │
 │                                                                                  │
 │  - NORMAL:  all signals pass                                                    │
 │  - REDUCED: only 5-star signals pass (after 3 consecutive losses)               │
 │  - PAUSED:  no signals pass (after 5 consecutive losses)                        │
 │                                                                                  │
 │  Resets daily at 9:15 AM. Winning trades reset consecutive loss counter.        │
 └──────────────────────────────────┬───────────────────────────────────────────────┘
                                    │ filtered list[CandidateSignal]
                                    ▼
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │                Risk Management                                                   │
 │                                                                                  │
 │  RiskManager.filter_and_size():                                                 │
 │  - Check available position slots (max 8 - active trades)                       │
 │  - Price affordability check (entry_price vs per-trade capital)                 │
 │                                                                                  │
 │  PositionSizer:                                                                 │
 │  - Equal allocation: total_capital / max_positions                              │
 │  - Confirmation multipliers: 1.0x (single), 1.5x (double), 2.0x (triple)       │
 │                                                                                  │
 │  CapitalAllocator:                                                              │
 │  - Expectancy-weighted allocation across strategies                             │
 │  - 20% reserve for exceptional signals                                          │
 │  - Auto-pause for strategies with < 40% win rate                                │
 └──────────────────────────────────┬───────────────────────────────────────────────┘
                                    │ list[FinalSignal]
                                    ▼
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │                Database Persistence                                              │
 │                                                                                  │
 │  SQLite (WAL mode) via aiosqlite                                                │
 │                                                                                  │
 │  ┌────────────┐  ┌─────────────────┐  ┌──────────────────────────────────────┐  │
 │  │ signals    │  │ hybrid_scores   │  │ Paper mode check:                    │  │
 │  │ table      │  │ table           │  │  ORB: orb_paper_mode flag            │  │
 │  │            │  │                 │  │  VWAP: vwap_paper_mode flag          │  │
 │  │ status:    │  │ 4-factor score  │  │  Gap & Go: always live               │  │
 │  │  sent /    │  │ breakdown +     │  │                                      │  │
 │  │  paper     │  │ confirmation    │  │ Paper signals: status = "paper"      │  │
 │  └────────────┘  └─────────────────┘  └──────────────────────────────────────┘  │
 └──────────────────────────────────┬───────────────────────────────────────────────┘
                                    │ signal_id assigned
                                    ▼
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │                Telegram Delivery                                                 │
 │                                                                                  │
 │  bot.send_signal() with:                                                        │
 │  - Entry, SL, T1, T2, quantity                                                  │
 │  - Star rating (with confirmation boost)                                        │
 │  - Confirmation badge (double/triple)                                           │
 │  - Paper mode indicator if applicable                                           │
 │  - Signal ID for TAKEN command reference                                        │
 └──────────────────────────────────────────────────────────────────────────────────┘


 EXIT MONITORING LOOP (runs in parallel within the same scan loop, every ~1s)
 ═════════════════════════════════════════════════════════════════════════════════════

 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │  TradeRepository.get_active_trades()                                            │
 └──────────────────────────────────┬───────────────────────────────────────────────┘
                                    │ list[TradeRecord]
                                    ▼
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │                ExitMonitor.check_trade() (per trade)                             │
 │                                                                                  │
 │  get_tick(symbol) from MarketDataStore                                          │
 │       │                                                                          │
 │       ▼                                                                          │
 │  ┌─────────────────────────────────────────────────────────────────────────────┐ │
 │  │  Per-strategy trailing stop config lookup:                                  │ │
 │  │  Gap & Go:  breakeven 2%, trail 4%/2%                                      │ │
 │  │  ORB:       breakeven 1.5%, trail 2%/1%                                    │ │
 │  │  VWAP:      breakeven 1-1.5%, no trail (breakeven only)                    │ │
 │  └─────────────────────────────────────────────────────────────────────────────┘ │
 │       │                                                                          │
 │       ▼                                                                          │
 │  ┌────────────────────────────────────────────────────────┐                     │
 │  │  Priority-ordered exit checks:                         │                     │
 │  │                                                        │                     │
 │  │  1. SL / Trailing SL hit  ──▶ full exit + persist      │                     │
 │  │  2. Target 2 hit          ──▶ full exit + persist      │                     │
 │  │  3. Target 1 hit          ──▶ advisory only (once)     │                     │
 │  │  4. Trailing SL update    ──▶ advisory (new SL level)  │                     │
 │  └───────────────────┬────────────────────────────────────┘                     │
 └──────────────────────┼──────────────────────────────────────────────────────────┘
                        │ on exit event
                        ▼
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │                _persist_exit()                                                   │
 │                                                                                  │
 │  1. trade_repo.close_trade()  ──▶  trades table (exit_price, pnl, exit_reason)  │
 │  2. Telegram alert            ──▶  bot.send_exit_alert()                        │
 │  3. Circuit breaker callback  ──▶  circuit_breaker.on_sl_hit() [SL exits only]  │
 │  4. Adaptive manager callback ──▶  adaptive_manager.on_trade_exit() [all exits] │
 └──────────────────────────────────────────────────────────────────────────────────┘


 FEEDBACK LOOPS (Phase 3 closed-loop control)
 ═════════════════════════════════════════════════════════════════════════════════════

                            ┌──────────────────────────────────┐
                            │        ExitMonitor               │
                            │     (trade exit events)          │
                            └───┬──────────────────────────┬───┘
                                │                          │
              SL hit callback   │                          │  all exit callback
                                ▼                          ▼
              ┌────────────────────────┐   ┌────────────────────────────────┐
              │    CircuitBreaker      │   │      AdaptiveManager           │
              │                        │   │                                │
              │  N SL hits/day         │   │  consecutive losses tracking   │
              │      │                 │   │      │                         │
              │      ▼                 │   │      ▼                         │
              │  is_active = True      │   │  NORMAL ─▶ REDUCED ─▶ PAUSED  │
              │      │                 │   │  (3 losses)  (5 losses)        │
              │      ▼                 │   │      │                         │
              │  HALT signal gen.      │   │      ▼                         │
              │  (exit monitor         │   │  Filter signals by strength    │
              │   continues)           │   │  or block strategy entirely    │
              └─────────┬──────────────┘   └──────────┬─────────────────────┘
                        │                              │
                        │ blocks _accepting_signals    │ blocks in scan loop
                        ▼                              ▼
              ┌─────────────────────────────────────────────────────────────┐
              │            Scan Loop (next iteration)                       │
              │   Circuit breaker checked at top of each cycle             │
              │   Adaptive filter applied after composite scoring          │
              └─────────────────────────────────────────────────────────────┘


              ┌────────────────────────────────┐
              │  StrategyPerformanceRepository  │
              │  (wins, losses, pnl, win_rate) │
              └──────┬─────────────────┬───────┘
                     │                 │
        ┌────────────┘                 └────────────┐
        ▼                                           ▼
 ┌──────────────────────────┐    ┌──────────────────────────────────┐
 │    CapitalAllocator      │    │       CompositeScorer            │
 │                          │    │                                  │
 │  Weekly rebalance:       │    │  win_rate factor (30% weight):   │
 │  expectancy-weighted     │    │  trailing 30-day win rate        │
 │  capital distribution    │    │  cached per day per strategy     │
 │  across strategies       │    │                                  │
 │                          │    │  Feeds into composite_score      │
 │  Auto-pause if           │    │  which drives ranking + star     │
 │  win rate < 40%          │    │  rating                          │
 └──────────────────────────┘    └──────────────────────────────────┘


 USER INTERACTION (Telegram Bot, 13 commands)
 ═════════════════════════════════════════════════════════════════════════════════════

                    ┌─────────────────────────────────────────────────┐
                    │                  Telegram User                   │
                    └────────────────────┬────────────────────────────┘
                                         │ command text
                                         ▼
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │                      SignalPilotBot                                               │
 │                                                                                  │
 │  Trade Management:              Configuration:         Phase 3:                  │
 │  ┌──────────────────────┐       ┌────────────────────┐ ┌────────────────────────┐│
 │  │ TAKEN [id]           │       │ CAPITAL <amount>   │ │ SCORE <SYMBOL>         ││
 │  │ STATUS               │       │ PAUSE <strategy>   │ │ ADAPT                  ││
 │  │ JOURNAL              │       │ RESUME <strategy>  │ │ REBALANCE              ││
 │  │                      │       │ ALLOCATE [...]     │ │ OVERRIDE CIRCUIT       ││
 │  │                      │       │ STRATEGY           │ │                        ││
 │  │                      │       │ HELP               │ │                        ││
 │  └──────────┬───────────┘       └─────────┬──────────┘ └───────────┬────────────┘│
 └─────────────┼─────────────────────────────┼────────────────────────┼─────────────┘
               │                             │                        │
               ▼                             ▼                        ▼
 ┌────────────────────┐  ┌────────────────────────┐  ┌────────────────────────────┐
 │ signal_repo        │  │ config_repo             │  │ hybrid_score_repo          │
 │ trade_repo         │  │ strategy_perf_repo      │  │ circuit_breaker            │
 │ exit_monitor       │  │ capital_allocator        │  │ adaptive_manager           │
 │ metrics_calculator │  │                          │  │ adaptation_log_repo        │
 └────────────────────┘  └────────────────────────┘  └────────────────────────────┘


 DASHBOARD (optional, enabled via config.dashboard_enabled)
 ═════════════════════════════════════════════════════════════════════════════════════

 ┌──────────────────────┐          ┌──────────────────────────────────────────────┐
 │   React Frontend     │   HTTP   │           FastAPI Backend                    │
 │   (6 pages)          │◀────────▶│           8 route modules:                   │
 │                      │          │                                              │
 │   - Signals          │          │  /api/signals         (list, filter)         │
 │   - Trades           │          │  /api/trades          (list, P&L)            │
 │   - Performance      │          │  /api/performance     (metrics, charts)      │
 │   - Strategies       │          │  /api/strategies      (per-strategy stats)   │
 │   - Allocation       │          │  /api/allocation      (capital weights)      │
 │   - Settings         │          │  /api/settings        (user config CRUD)     │
 │                      │          │  /api/circuit-breaker  (status, log)         │
 │                      │          │  /api/adaptation       (log, states)         │
 └──────────────────────┘          └────────────────┬─────────────────────────────┘
                                                    │
                                          ┌─────────┴─────────┐
                                          │                   │
                                          ▼                   ▼
                                   ┌────────────┐     ┌────────────┐
                                   │  Read-only  │     │  Write     │
                                   │  SQLite     │     │  SQLite    │
                                   │  connection │     │  connection│
                                   │  (queries)  │     │  (settings)│
                                   └────────────┘     └────────────┘


 DATABASE SCHEMA (8 tables, SQLite WAL mode)
 ═════════════════════════════════════════════════════════════════════════════════════

 ┌───────────────┐  ┌───────────────┐  ┌───────────────┐  ┌────────────────────────┐
 │   signals     │  │   trades      │  │  user_config  │  │ strategy_performance   │
 │               │  │               │  │               │  │                        │
 │ Phase 1+2+3   │  │ Phase 1+2     │  │ Phase 1+2+3   │  │ Phase 2+3              │
 │               │  │               │  │               │  │                        │
 │ +composite_   │  │ entry/exit    │  │ +circuit_     │  │ wins, losses,          │
 │  score        │  │ price, pnl,   │  │  breaker_    │  │ expectancy,            │
 │ +confirmation │  │ exit_reason   │  │  limit       │  │ capital_weight         │
 │  _level       │  │               │  │ +adaptation  │  │                        │
 │ +adaptation   │  │               │  │  _mode       │  │                        │
 │  _status      │  │               │  │               │  │                        │
 └───────────────┘  └───────────────┘  └───────────────┘  └────────────────────────┘

 ┌───────────────┐  ┌───────────────┐  ┌───────────────┐  ┌────────────────────────┐
 │ hybrid_scores │  │circuit_breaker│  │adaptation_log │  │   vwap_cooldown        │
 │               │  │    _log       │  │               │  │                        │
 │ Phase 3       │  │ Phase 3       │  │ Phase 3       │  │ Phase 2                │
 │               │  │               │  │               │  │                        │
 │ 4-factor      │  │ activation/   │  │ throttle/     │  │ per-stock signal       │
 │ breakdown,    │  │ override      │  │ pause/resume  │  │ cooldown tracking      │
 │ confirmation  │  │ events        │  │ events        │  │                        │
 └───────────────┘  └───────────────┘  └───────────────┘  └────────────────────────┘
```

---

## Legend

```
Symbol          Meaning
──────────────  ──────────────────────────────────────────────
  ═══           Section separator (major system boundary)
  ───           Box border (component or group boundary)
  │ ▼ ▲         Vertical data flow (downward is primary)
  ─ ▶ ◀         Horizontal data flow or reference
  ┌ ┐ └ ┘       Box corners
  ├ ┤ ┬ ┴ ┼     Box junction points
  [ ... ]       Alternative or parallel options
  ( ... )       Annotation or description
```

---

## Data Model Transformation Chain

Each stage of the pipeline transforms data through a specific model type. The
chain below shows how raw market data becomes a persisted trade record.

```
 ┌──────────┐     ┌─────────────────┐     ┌────────────────────┐
 │ TickData  │────▶│ CandidateSignal │────▶│ ConfirmationResult │
 │           │     │                 │     │                    │
 │ symbol    │     │ symbol          │     │ confirmation_level │
 │ ltp       │     │ direction       │     │ confirmed_by[]     │
 │ open      │     │ strategy_name   │     │ star_boost         │
 │ high/low  │     │ entry/sl/t1/t2  │     │ position_size_     │
 │ volume    │     │ gap_pct         │     │   multiplier       │
 │ timestamp │     │ volume_ratio    │     │                    │
 └──────────┘     │ setup_type      │     └────────┬───────────┘
                   │ strategy_       │              │
                   │  specific_score │              │
                   └────────┬───────┘              │
                            │                      │
                            ▼                      │
                   ┌────────────────────┐          │
                   │CompositeScoreResult│◀─────────┘
                   │                    │
                   │ composite_score    │   strategy_strength * 0.4
                   │ strategy_strength  │ + win_rate          * 0.3
                   │ win_rate_score     │ + risk_reward       * 0.2
                   │ risk_reward_score  │ + confirmation      * 0.1
                   │ confirmation_bonus │
                   └────────┬───────────┘
                            │
                            ▼
                   ┌──────────────┐     ┌─────────────┐     ┌──────────────┐
                   │ RankedSignal │────▶│ FinalSignal  │────▶│ SignalRecord  │
                   │              │     │              │     │              │
                   │ candidate    │     │ ranked_signal│     │ Persisted in │
                   │ composite_   │     │ quantity     │     │ signals table│
                   │  score       │     │ capital_     │     │              │
                   │ rank         │     │  required    │     │ +composite_  │
                   │ signal_      │     │ expires_at   │     │  score       │
                   │  strength    │     │              │     │ +confirmation│
                   │  (1-5 stars) │     └──────────────┘     │  _level      │
                   └──────────────┘                          └──────┬───────┘
                                                                    │
                                                    TAKEN command   │
                                                                    ▼
                                                            ┌──────────────┐
                                                            │ TradeRecord   │
                                                            │               │
                                                            │ entry/exit    │
                                                            │ pnl_amount    │
                                                            │ pnl_pct       │
                                                            │ exit_reason   │
                                                            │ taken_at      │
                                                            │ exited_at     │
                                                            └──────────────┘
```

Summary of the full chain:

```
TickData --> CandidateSignal --> ConfirmationResult --> CompositeScoreResult
         --> RankedSignal --> FinalSignal --> SignalRecord --> TradeRecord
```

---

## Market Phase Timeline

Each phase activates a specific set of strategies and system behaviors.

### OPENING Phase (9:15 - 9:30)

| Component          | Activity                                                 |
|--------------------|----------------------------------------------------------|
| WebSocket          | Connected, receiving ticks for all Nifty 500 symbols     |
| MarketDataStore    | Building opening ranges, accumulating ticks               |
| Gap & Go           | **Active** -- gap detection, volume accumulation          |
| ORB                | Inactive (opening range still building)                   |
| VWAP Reversal      | Inactive (VWAP scan starts at 10:00)                     |
| ExitMonitor        | Monitoring any trades from crash recovery                 |
| CircuitBreaker     | Reset at 9:15, monitoring SL events                      |
| AdaptiveManager    | Reset at 9:15, all strategies at NORMAL                  |

### ENTRY_WINDOW Phase (9:30 - 9:45)

| Component          | Activity                                                 |
|--------------------|----------------------------------------------------------|
| Gap & Go           | **Active** -- entry validation, signal generation         |
| ORB                | Inactive (opening range still building)                   |
| VWAP Reversal      | Inactive                                                 |
| ConfidenceDetector | Checking for multi-strategy agreement                    |
| CompositeScorer    | Scoring Gap & Go candidates                              |
| DuplicateChecker   | Filtering same-day and active-trade duplicates           |
| SignalRanker       | Ranking and star-rating candidates                       |
| RiskManager        | Position sizing with confirmation multipliers            |

### CONTINUOUS Phase (9:45 - 14:30)

| Component          | Activity                                                 |
|--------------------|----------------------------------------------------------|
| Gap & Go           | Inactive (entry window closed)                           |
| ORB                | **Active 9:45-11:00** -- breakout detection               |
| VWAP Reversal      | **Active 10:00-14:30** -- mean-reversion setups           |
| Opening Ranges     | Locked at 9:45 (30-min range finalized)                  |
| ConfidenceDetector | Cross-strategy confirmation (ORB + VWAP overlap)         |
| CompositeScorer    | Full 4-factor scoring with live win rates                |
| CircuitBreaker     | May activate if SL limit reached                         |
| AdaptiveManager    | May throttle/pause losing strategies                     |
| ExitMonitor        | Full monitoring: SL, T1, T2, trailing SL, breakeven     |

### WIND_DOWN Phase (14:30 - 15:30)

| Component          | Activity                                                 |
|--------------------|----------------------------------------------------------|
| All Strategies     | Inactive (_accepting_signals = False at 14:30)           |
| ExitMonitor        | **Active** -- monitoring all open positions               |
| Exit Reminder      | 15:00 -- advisory alerts with current P&L                |
| Mandatory Exit     | 15:15 -- force-close all open trades                     |
| Daily Summary      | 15:30 -- performance metrics + strategy breakdown        |
| Shutdown           | 15:35 -- WebSocket disconnect, bot stop, DB close        |

### Off-Hours

| Component          | Activity                                                 |
|--------------------|----------------------------------------------------------|
| Weekly Rebalance   | Sunday 18:00 -- CapitalAllocator recalculates weights    |
| MarketScheduler    | Running, all weekday jobs guarded by trading day check   |
| Dashboard          | Available if enabled (reads from SQLite)                 |
