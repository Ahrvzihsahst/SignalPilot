# SignalPilot System Flow

Complete architecture and data flow for the SignalPilot intraday signal generation system.
All 40+ components across Phase 1, 2, 3, and 4 (including News Sentiment Filter) are represented in a single integrated view.

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
 │  settings)   │    │  Wiring order (23 stages):                                │
 └─────────────┘    │                                                            │
                     │  1. DatabaseManager (SQLite WAL, 12 tables)               │
                     │  2. Repositories (signal, trade, config, metrics,          │
                     │     strategy_performance, signal_action, watchlist,        │
                     │     hybrid_score, circuit_breaker, adaptation_log,        │
                     │     news_sentiment, earnings_calendar)                    │
                     │  3. EventBus (in-process async event dispatch)             │
                     │  4. SmartAPIAuthenticator (Angel One TOTP 2FA)             │
                     │  5. InstrumentManager (Nifty 500 CSV)                     │
                     │  6. MarketDataStore (in-memory cache)                     │
                     │  7. HistoricalDataFetcher (Angel One + yfinance)          │
                     │  8. Strategies (GapAndGo, ORB, VWAPReversal)              │
                     │  9. DuplicateChecker                                      │
                     │ 10. Scorers (SignalScorer, ORBScorer, VWAPScorer)         │
                     │ 11. SignalRanker                                           │
                     │ 12. ConfidenceDetector + CompositeScorer                  │
                     │ 13. CapitalAllocator + PositionSizer + RiskManager        │
                     │ 14. ExitMonitor (trailing configs + EventBus)              │
                     │ 15. CircuitBreaker + AdaptiveManager                      │
                     │ 16. Intelligence (VADERSentimentEngine, NewsFetcher,      │
                     │     NewsSentimentService, EarningsCalendar)               │
                     │ 17. SignalPilotBot (Telegram, 16 commands + 9 callbacks)  │
                     │ 18. WebSocketClient (Angel One feed)                      │
                     │ 19. MarketScheduler (APScheduler, 12 cron jobs)           │
                     │ 20. EventBus subscriptions (4 event→handler bindings)     │
                     │ 21. ScanPipeline (12 signal stages + 1 always stage)      │
                     │ 22. FastAPI Dashboard (optional, 10 route modules)        │
                     │ 23. SignalPilotApp (orchestrator)                          │
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


 EVENT BUS (decoupled cross-component communication)
 ═════════════════════════════════════════════════════════════════════════════════════

 Components emit events; subscribers handle them. No direct references needed.

 ┌──────────────────┐    emit()     ┌──────────────┐    dispatch    ┌──────────────┐
 │   ExitMonitor    │──────────────▶│   EventBus   │──────────────▶│  Subscribers  │
 │   CircuitBreaker │               │              │               │              │
 │   AdaptiveManager│               │  Sequential  │               │  Isolated    │
 └──────────────────┘               │  dispatch,   │               │  (one fail   │
                                    │  error-      │               │  ≠ all fail) │
                                    │  isolated    │               │              │
                                    └──────────────┘               └──────────────┘

 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │  Event Type             │  Emitted by        │  Handled by                      │
 │─────────────────────────┼────────────────────┼──────────────────────────────────│
 │  ExitAlertEvent         │  ExitMonitor       │  bot.send_exit_alert()           │
 │  StopLossHitEvent       │  ExitMonitor       │  circuit_breaker.on_sl_hit()     │
 │  TradeExitedEvent       │  ExitMonitor       │  adaptive_manager.on_trade_exit()│
 │  AlertMessageEvent      │  CB / Adaptive Mgr │  bot.send_alert()                │
 └──────────────────────────────────────────────────────────────────────────────────┘


 MARKET SCHEDULE TIMELINE (IST, Mon-Fri, skip NSE holidays)
 ═════════════════════════════════════════════════════════════════════════════════════

  8:30     9:00     9:15        9:30         9:45        10:00       11:00
    │        │        │           │            │            │           │
    ▼        ▼        ▼           ▼            ▼            ▼           ▼
 ┌──────┐┌──────┐┌───────┐┌──────────┐┌───────────┐┌──────────┐┌──────────┐
 │PRE-  ││PRE-  ││START  ││          ││LOCK       ││          ││          │
 │MARKET││MARKET││SCAN   ││ Gap&Go   ││OPENING    ││VWAP      ││ORB       │
 │NEWS  ││ALERT ││       ││ entry    ││RANGES     ││SCAN      ││WINDOW    │
 │      ││      ││WS conn││ valid.   ││           ││START     ││END       │
 │fetch ││      ││CB/AM  ││          ││ORB begins ││          ││          │
 │RSS + ││      ││reset  ││          ││           ││          ││          │
 │VADER ││      ││       ││          ││           ││          ││          │
 └──────┘└──────┘└───────┘└──────────┘└───────────┘└──────────┘└──────────┘

    │◄──OPENING──▶│◄ENTRY_WINDOW▶│◄────────── CONTINUOUS ──────────────────────▶│
                                                                                 │
 11:15       13:15       14:30       15:00       15:15        15:30       15:35
    │           │           │           │           │            │           │
    ▼           ▼           ▼           ▼           ▼            ▼           ▼
 ┌──────────┐┌──────────┐┌──────────┐┌──────────┐┌──────────┐┌──────────┐┌──────────┐
 │NEWS      ││NEWS      ││STOP NEW  ││EXIT      ││MANDATORY ││DAILY     ││SHUTDOWN  │
 │CACHE     ││CACHE     ││SIGNALS   ││REMINDER  ││EXIT      ││SUMMARY   ││          │
 │REFRESH 1 ││REFRESH 2 ││          ││          ││          ││          ││          │
 │          ││          ││_accepting││advisory  ││force     ││metrics + ││WS disc.  │
 │mid-morn  ││mid-aftn  ││=False    ││alerts    ││all close ││strategy  ││bot stop  │
 │sentiment ││sentiment ││          ││+ buttons ││& persist ││breakdown ││DB close  │
 │re-fetch  ││re-fetch  ││          ││          ││          ││          ││          │
 └──────────┘└──────────┘└──────────┘└──────────┘└──────────┘└──────────┘└──────────┘

    │◄──────────────── WIND_DOWN ──────────────────▶│

                                                                Sun 18:00
                                                                    │
                                                                    ▼
                                                               ┌──────────┐
                                                               │WEEKLY    │
                                                               │REBALANCE │
                                                               │          │
                                                               │capital   │
                                                               │allocator │
                                                               │recalc    │
                                                               └──────────┘


 COMPOSABLE PIPELINE (12 signal stages + 1 always stage, runs every ~1s)
 ═════════════════════════════════════════════════════════════════════════════════════

 The scan loop delegates ALL work to a ScanPipeline. Each stage implements the
 PipelineStage protocol (name + async process(ctx)) and transforms a ScanContext.

 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │  ScanContext (mutable state bag passed through all stages)                      │
 │                                                                                 │
 │  cycle_id, now, phase, accepting_signals                                       │
 │  user_config, enabled_strategies, all_candidates                               │
 │  confirmation_map, composite_scores                                            │
 │  ranked_signals, sentiment_results, suppressed_signals                         │
 │  final_signals, active_trade_count                                             │
 └──────────────────────────────────────────────────────────────────────────────────┘

 SIGNAL STAGES (run only when accepting_signals=True AND phase in
 OPENING / ENTRY_WINDOW / CONTINUOUS):

 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │  Stage 1: CircuitBreakerGateStage                                               │
 │  If circuit_breaker.is_active: set ctx.accepting_signals = False → skip rest   │
 └──────────────────────────────────┬───────────────────────────────────────────────┘
                                    │ (pass if not active)
                                    ▼
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │  Stage 2: StrategyEvalStage                                                     │
 │                                                                                 │
 │  Load user_config, filter enabled strategies (gap_go/orb/vwap_enabled flags)   │
 │  Run strategy.evaluate(market_data, phase) for each enabled strategy           │
 │                                                                                 │
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
 │            └────────────────────────┼───────────────────────────┘               │
 └─────────────────────────────────────┼──────────────────────────────────────────┘
                                       │ ctx.all_candidates = list[CandidateSignal]
                                       ▼
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │  Stage 3: GapStockMarkingStage                                                  │
 │                                                                                 │
 │  Extract Gap & Go symbols from candidates                                      │
 │  Call mark_gap_stock(symbol) on ORB/VWAP strategies (exclude gapping stocks)   │
 └──────────────────────────────────┬───────────────────────────────────────────────┘
                                    │
                                    ▼
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │  Stage 4: DeduplicationStage                                                    │
 │                                                                                 │
 │  - Active trade check (skip if symbol already has open position)               │
 │  - Same-day signal check (skip if signal already sent today for symbol)        │
 │  - Multi-confirmation bypass (double/triple can override dedup)                │
 └──────────────────────────────────┬───────────────────────────────────────────────┘
                                    │ filtered list[CandidateSignal]
                                    ▼
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │  Stage 5: ConfidenceStage (Phase 3)                                             │
 │                                                                                 │
 │  Group candidates by symbol, check for multi-strategy agreement:               │
 │  - In-batch: multiple strategies in current scan cycle                         │
 │  - Cross-cycle: recent signals from DB within 15-min window                    │
 │                                                                                 │
 │  Result: single (1x, +0 stars) / double (1.5x, +1 star) / triple (2x, +2)    │
 └──────────────────────────────────┬───────────────────────────────────────────────┘
                                    │ ctx.confirmation_map
                                    ▼
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │  Stage 6: CompositeScoringStage (Phase 3)                                       │
 │                                                                                 │
 │  For each candidate:                                                           │
 │  ┌───────────────────────────────────────────────────────────────────────────┐  │
 │  │ composite = strategy_strength * 0.40  (per-strategy scorer, 0-100)      │  │
 │  │           + win_rate          * 0.30  (trailing 30-day, cached per day) │  │
 │  │           + risk_reward       * 0.20  (R:R linear map: 1->0, 3->100)   │  │
 │  │           + confirmation      * 0.10  (single=0, double=50, triple=100)│  │
 │  └───────────────────────────────────────────────────────────────────────────┘  │
 └──────────────────────────────────┬───────────────────────────────────────────────┘
                                    │ ctx.composite_scores
                                    ▼
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │  Stage 7: AdaptiveFilterStage (Phase 3)                                         │
 │                                                                                 │
 │  Per-strategy state: NORMAL -> REDUCED -> PAUSED                               │
 │  - NORMAL:  all signals pass                                                   │
 │  - REDUCED: only 5-star signals pass (after 3 consecutive losses)              │
 │  - PAUSED:  no signals pass (after 5 consecutive losses)                       │
 └──────────────────────────────────┬───────────────────────────────────────────────┘
                                    │ filtered candidates
                                    ▼
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │  Stage 8: RankingStage                                                          │
 │                                                                                 │
 │  Per-strategy scorers: SignalScorer (Gap&Go), ORBScorer, VWAPScorer            │
 │  Top-N selection (N = max_positions from config, default 8)                    │
 │  Star rating: 1-5 stars based on composite score thresholds                    │
 │  Confirmation star boost applied (+1 for double, +2 for triple, max 5)        │
 └──────────────────────────────────┬───────────────────────────────────────────────┘
                                    │ ctx.ranked_signals = list[RankedSignal]
                                    ▼
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │  Stage 9: NewsSentimentStage (Phase 4 — News Sentiment Filter)                  │
 │                                                                                 │
 │  For each ranked signal, fetch sentiment from NewsSentimentService cache:      │
 │                                                                                 │
 │  ┌──────────────────────────────────────────────────────────────────────────┐   │
 │  │  Action Matrix:                                                         │   │
 │  │                                                                          │   │
 │  │  1. Earnings blackout (highest priority):                               │   │
 │  │     - has_earnings_today(symbol) → suppress, unless unsuppress override │   │
 │  │                                                                          │   │
 │  │  2. STRONG_NEGATIVE (composite < strong_negative_threshold):            │   │
 │  │     → suppress signal, add to ctx.suppressed_signals,                   │   │
 │  │       send suppression notification via Telegram                        │   │
 │  │                                                                          │   │
 │  │  3. MILD_NEGATIVE (composite < mild_negative_threshold):                │   │
 │  │     → downgrade star rating by 1 (minimum 1 star)                       │   │
 │  │                                                                          │   │
 │  │  4. NEUTRAL / POSITIVE / NO_NEWS:                                       │   │
 │  │     → pass through unchanged                                            │   │
 │  │                                                                          │   │
 │  │  5. Unsuppress override (via UNSUPPRESS <STOCK> command):               │   │
 │  │     → pass through with UNSUPPRESSED action, bypass any suppression     │   │
 │  └──────────────────────────────────────────────────────────────────────────┘   │
 │                                                                                 │
 │  Composite score uses recency-weighted decay: w = exp(-lambda * age_hours)     │
 │  Half-life = 6 hours (recent headlines weigh more)                             │
 │                                                                                 │
 │  ctx.sentiment_results = dict[str, SentimentResult]                            │
 │  ctx.suppressed_signals = list[SuppressedSignal]                               │
 └──────────────────────────────────┬───────────────────────────────────────────────┘
                                    │ filtered ctx.ranked_signals (suppressed removed)
                                    ▼
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │  Stage 10: RiskSizingStage                                                      │
 │                                                                                 │
 │  RiskManager.filter_and_size():                                                │
 │  - Check available position slots (max 8 - active trades)                      │
 │  - Price affordability check (entry_price vs per-trade capital)                │
 │                                                                                 │
 │  PositionSizer:                                                                │
 │  - Equal allocation: total_capital / max_positions                             │
 │  - Confirmation multipliers: 1.0x (single), 1.5x (double), 2.0x (triple)      │
 │                                                                                 │
 │  CapitalAllocator:                                                             │
 │  - Expectancy-weighted allocation across strategies                            │
 │  - 20% reserve for exceptional signals                                         │
 │  - Auto-pause for strategies with < 40% win rate                               │
 └──────────────────────────────────┬───────────────────────────────────────────────┘
                                    │ ctx.final_signals = list[FinalSignal]
                                    ▼
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │  Stage 11: PersistAndDeliverStage                                               │
 │                                                                                 │
 │  For each FinalSignal:                                                         │
 │  ┌──────────────────────────────────────────────────────────────────────────┐   │
 │  │  1. Convert to SignalRecord                                              │   │
 │  │  2. Paper mode check (ORB: orb_paper_mode, VWAP: vwap_paper_mode)      │   │
 │  │  3. INSERT INTO signals table (signal_repo.insert_signal)               │   │
 │  │  4. INSERT INTO hybrid_scores table (Phase 3 composite breakdown)       │   │
 │  │  5. bot.send_signal() with inline keyboard:                             │   │
 │  │                                                                          │   │
 │  │     ┌─────────────────────────────────────────┐                          │   │
 │  │     │  BUY SIGNAL -- RELIANCE  ****- (Strong) │                          │   │
 │  │     │  Entry: 2,850  SL: 2,764  T1: 2,992    │                          │   │
 │  │     │  NEWS WARNING (if MILD_NEGATIVE)        │  ◀── sentiment badge    │   │
 │  │     │  ...                                    │                          │   │
 │  │     │  [ TAKEN ]   [ SKIP ]   [ WATCH ]       │  ◀── Phase 4 buttons    │   │
 │  │     └─────────────────────────────────────────┘                          │   │
 │  └──────────────────────────────────────────────────────────────────────────┘   │
 └──────────────────────────────────┬───────────────────────────────────────────────┘
                                    │
                                    ▼
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │  Stage 12: DiagnosticStage                                                      │
 │                                                                                 │
 │  Heartbeat every 60 cycles (~1 min): phase, strategy count, WS status          │
 └──────────────────────────────────────────────────────────────────────────────────┘


 ALWAYS STAGE (runs every cycle regardless of signal acceptance)
 ═════════════════════════════════════════════════════════════════════════════════════

 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │  ExitMonitoringStage                                                            │
 │                                                                                 │
 │  trade_repo.get_active_trades()                                                │
 │       │                                                                         │
 │       ▼ for each active trade                                                  │
 │  ┌─────────────────────────────────────────────────────────────────────────────┐│
 │  │  Per-strategy trailing stop config:                                        ││
 │  │  Gap & Go:  breakeven 2%, trail 4%/2%                                     ││
 │  │  ORB:       breakeven 1.5%, trail 2%/1%                                   ││
 │  │  VWAP:      breakeven 1-1.5%, no trail (breakeven only)                   ││
 │  └─────────────────────────────────────────────────────────────────────────────┘│
 │       │                                                                         │
 │       ▼                                                                         │
 │  ┌─────────────────────────────────────────────────────────────────────────────┐│
 │  │  Priority-ordered exit checks:                                             ││
 │  │                                                                            ││
 │  │  1. SL / Trailing SL hit  ──▶ full exit + persist + events                ││
 │  │  2. Target 2 hit          ──▶ full exit + persist + events                ││
 │  │  3. Target 1 hit          ──▶ advisory + [ Book 50% at T1 ] button        ││
 │  │  4. Trailing SL update    ──▶ advisory (new SL level)                     ││
 │  │  5. SL Approaching        ──▶ advisory + [ Exit Now ] [ Hold ] buttons    ││
 │  │  6. Near T2               ──▶ advisory + [ Take Profit ] [ Let Run ]      ││
 │  └──────────────────────────────┬──────────────────────────────────────────────┘│
 └─────────────────────────────────┼──────────────────────────────────────────────┘
                                   │ on exit event
                                   ▼
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │                _persist_exit() + EventBus emission                              │
 │                                                                                 │
 │  1. trade_repo.close_trade()    ──▶  trades table (exit_price, pnl)            │
 │  2. event_bus.emit(ExitAlertEvent)      ──▶  bot.send_exit_alert()             │
 │  3. event_bus.emit(StopLossHitEvent)    ──▶  circuit_breaker.on_sl_hit()       │
 │     (SL exits only)                                                            │
 │  4. event_bus.emit(TradeExitedEvent)    ──▶  adaptive_manager.on_trade_exit()  │
 │     (all exits)                                                                │
 └──────────────────────────────────────────────────────────────────────────────────┘


 PHASE 4: INLINE BUTTON CALLBACKS & QUICK ACTIONS
 ═════════════════════════════════════════════════════════════════════════════════════

 User taps inline buttons on Telegram messages instead of typing text commands.
 Actions are tracked (response_time_ms, skip reasons) for analytics.

 SIGNAL BUTTONS (attached to every signal message):

                    ┌─────────────────────────────────────────────┐
                    │        Signal Message Delivered              │
                    │                                             │
                    │  [ TAKEN ]     [ SKIP ]     [ WATCH ]       │
                    └──────┬────────────┬────────────┬────────────┘
                           │            │            │
                           ▼            ▼            ▼
               ┌──────────────┐  ┌──────────┐  ┌──────────────────┐
               │handle_taken  │  │show skip │  │handle_watch      │
               │_callback()   │  │reason    │  │_callback()       │
               │              │  │keyboard: │  │                  │
               │Create trade, │  │┌────────┐│  │Add to watchlist  │
               │start exit    │  ││No Cap. ││  │(5-day expiry),   │
               │monitor,      │  ││Low Conf││  │re-alert on       │
               │record action │  ││Sector  ││  │future signals    │
               │+ response_ms │  ││Other   ││  │                  │
               └──────┬───────┘  │└───┬────┘│  └──────────────────┘
                      │          └────┼─────┘
                      ▼               ▼
               ┌────────────┐  ┌────────────────────┐
               │trade_repo  │  │signal_action_repo  │
               │exit_monitor│  │record: signal_id,  │
               │signal_     │  │  action, reason,   │
               │action_repo │  │  response_time_ms  │
               └────────────┘  └────────────────────┘

 EXIT BUTTONS (attached to exit alert messages):

  T1 Hit:              T2 Hit:              SL Approaching:       Near T2:
  ┌──────────────┐     ┌────────────────┐   ┌───────┬───────┐   ┌───────────┬──────┐
  │Book 50% at T1│     │Exit at T2      │   │Exit   │Hold   │   │Take Profit│Let   │
  └──────┬───────┘     └───────┬────────┘   │Now    │       │   │           │Run   │
         │                     │            └───┬───┴───┬───┘   └─────┬─────┴──┬───┘
         ▼                     ▼                │       │             │        │
  partial_exit()       full_exit()        exit_now() hold()    take_profit() let_run()
  (50% at T1)          (100% at T2)       (market    (dismiss)  (close at    (continue
                                           price)               current)     trailing)

 ANALYTICS TABLES:

 ┌──────────────────────┐  ┌──────────────────────────────────────────────┐
 │  signal_actions      │  │  watchlist                                   │
 │                      │  │                                              │
 │  signal_id           │  │  symbol, signal_id, strategy                │
 │  action (taken/      │  │  entry_price                                │
 │    skip/watch)       │  │  added_at, expires_at (5 days)              │
 │  reason (skip only)  │  │  triggered_count (re-alert counter)         │
 │  response_time_ms    │  │                                              │
 │  acted_at            │  │  Queries: avg response time, skip reason    │
 └──────────────────────┘  │  distribution, action summaries per day     │
                           └──────────────────────────────────────────────┘


 FEEDBACK LOOPS (Phase 3 closed-loop control via EventBus)
 ═════════════════════════════════════════════════════════════════════════════════════

                            ┌──────────────────────────────────┐
                            │        ExitMonitor               │
                            │     (emits events via EventBus)  │
                            └───┬──────────────────────────┬───┘
                                │                          │
          StopLossHitEvent      │                          │  TradeExitedEvent
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
              │  emit(AlertMessage)    │   │  Filter signals by strength    │
              │                        │   │  emit(AlertMessage) on change  │
              └─────────┬──────────────┘   └──────────┬─────────────────────┘
                        │                              │
                        │ Stage 1: CB gate             │ Stage 7: Adaptive filter
                        ▼                              ▼
              ┌─────────────────────────────────────────────────────────────┐
              │            ScanPipeline (next iteration)                    │
              │   Circuit breaker gate = Stage 1 of every cycle           │
              │   Adaptive filter      = Stage 7 of every cycle           │
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


 INTELLIGENCE MODULE (Phase 4 — News Sentiment Filter)
 ═════════════════════════════════════════════════════════════════════════════════════

 Pre-market and intraday news sentiment analysis pipeline. RSS headlines are
 fetched, scored by VADER (or FinBERT), cached in SQLite, and consumed by the
 NewsSentimentStage in the scan pipeline.

 ┌─────────────────────────────────────────────────────────────────────────────────┐
 │ Data Flow: RSS Feeds → Sentiment Engine → Cache → Pipeline Stage              │
 └─────────────────────────────────────────────────────────────────────────────────┘

  8:30 IST (pre_market_news job)          11:15 / 13:15 IST (news_cache_refresh)
        │                                        │
        ▼                                        ▼
 ┌──────────────┐                         ┌──────────────┐
 │ NewsFetcher   │                         │ NewsFetcher   │
 │ (RSS feeds)  │                         │ (RSS feeds)  │
 │              │                         │              │
 │ aiohttp +    │                         │ incremental  │
 │ feedparser   │                         │ refresh      │
 └──────┬───────┘                         └──────┬───────┘
        │ list[RawHeadline]                      │
        ▼                                        ▼
 ┌──────────────────┐                     ┌──────────────────┐
 │ SentimentEngine   │                     │ SentimentEngine   │
 │                   │                     │                   │
 │ VADERSentiment    │                     │ VADER (default)   │
 │  Engine (default) │                     │ or FinBERT        │
 │ or FinBERT        │                     │                   │
 │                   │                     │ compound_score,   │
 │ compound_score,   │                     │ pos/neg/neu       │
 │ pos/neg/neu       │                     │                   │
 └──────┬────────────┘                     └──────┬────────────┘
        │ list[NewsSentimentRecord]               │
        ▼                                        ▼
 ┌───────────────────────────────────────────────────────────────┐
 │                  NewsSentimentService                         │
 │                                                               │
 │  Orchestrates fetch → analyze → cache                        │
 │                                                               │
 │  Recency-weighted composite: w = exp(-ln(2)/6h * age_hours)  │
 │  Classification thresholds (configurable):                    │
 │    STRONG_NEGATIVE < -0.5                                     │
 │    MILD_NEGATIVE   < -0.15                                    │
 │    NEUTRAL         <= +0.15                                   │
 │    POSITIVE        > +0.15                                    │
 │                                                               │
 │  Session-scoped unsuppress overrides (via UNSUPPRESS cmd)    │
 └──────────────────────────┬────────────────────────────────────┘
                            │ upsert to cache
                            ▼
 ┌───────────────────────────────────────────────────────────────┐
 │  news_sentiment_cache (SQLite)        earnings_calendar      │
 │                                                               │
 │  Read by NewsSentimentStage           Read by NewsSentiment  │
 │  (pipeline stage 9) during            Stage to check         │
 │  each scan cycle                      earnings blackout      │
 └───────────────────────────────────────────────────────────────┘

 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │  EarningsCalendar                                                               │
 │                                                                                 │
 │  Ingestion sources:                                                            │
 │  - CSV file (data/earnings.csv): manual upload of known earnings dates         │
 │  - Screener.in API: automated scraping of upcoming earnings                    │
 │                                                                                 │
 │  earnings_repo.has_earnings_today(symbol) → boolean blackout check             │
 │  earnings_repo.get_upcoming_earnings(days) → list for EARNINGS command         │
 └──────────────────────────────────────────────────────────────────────────────────┘


 USER INTERACTION (Telegram Bot: 16 text commands + 9 callback handlers)
 ═════════════════════════════════════════════════════════════════════════════════════

                    ┌─────────────────────────────────────────────────┐
                    │                  Telegram User                   │
                    └────────┬───────────────────────────┬────────────┘
                             │ text commands              │ button taps
                             ▼                            ▼
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │                      SignalPilotBot                                              │
 │                                                                                 │
 │  Text Commands:                                                                │
 │  ┌──────────────────────┐  ┌────────────────────┐  ┌────────────────────────┐  │
 │  │ Trade Management     │  │ Configuration      │  │ Phase 3 Intelligence   │  │
 │  │                      │  │                    │  │                        │  │
 │  │ TAKEN [FORCE] [id]   │  │ CAPITAL <amount>   │  │ SCORE <SYMBOL>         │  │
 │  │ STATUS               │  │ PAUSE <strategy>   │  │ ADAPT                  │  │
 │  │ JOURNAL              │  │ RESUME <strategy>  │  │ REBALANCE              │  │
 │  │ WATCHLIST             │  │ ALLOCATE [...]     │  │ OVERRIDE CIRCUIT       │  │
 │  │                      │  │ STRATEGY           │  │                        │  │
 │  │                      │  │ HELP               │  │                        │  │
 │  └──────────────────────┘  └────────────────────┘  └────────────────────────┘  │
 │                                                                                 │
 │  ┌──────────────────────────────────────────────────────────────────────────┐   │
 │  │ Phase 4: News Sentiment Commands                                        │   │
 │  │                                                                          │   │
 │  │ NEWS [<STOCK>|ALL]    — show sentiment for a stock or all cached stocks │   │
 │  │ EARNINGS              — show upcoming earnings calendar                 │   │
 │  │ UNSUPPRESS <STOCK>    — override sentiment suppression for a stock      │   │
 │  │                         (session-scoped, cleared at end of day)          │   │
 │  └──────────────────────────────────────────────────────────────────────────┘   │
 │                                                                                 │
 │  Inline Button Callbacks (Phase 4):                                            │
 │  ┌──────────────────────┐  ┌────────────────────┐  ┌────────────────────────┐  │
 │  │ Signal Actions       │  │ Trade Exits        │  │ Alert Dismissals       │  │
 │  │                      │  │                    │  │                        │  │
 │  │ handle_taken_cb()    │  │ partial_exit()     │  │ hold()                 │  │
 │  │ handle_skip_cb()     │  │ exit_now()         │  │ let_run()              │  │
 │  │ handle_skip_reason() │  │ take_profit()      │  │                        │  │
 │  │ handle_watch_cb()    │  │                    │  │                        │  │
 │  └──────────┬───────────┘  └─────────┬──────────┘  └───────────┬────────────┘  │
 └─────────────┼─────────────────────────┼────────────────────────┼────────────────┘
               │                         │                        │
               ▼                         ▼                        ▼
 ┌────────────────────┐  ┌────────────────────────┐  ┌────────────────────────────┐
 │ signal_repo        │  │ trade_repo              │  │ signal_action_repo         │
 │ trade_repo         │  │ exit_monitor            │  │ watchlist_repo             │
 │ exit_monitor       │  │ get_current_prices      │  │                            │
 │ metrics_calculator │  │                          │  │ Response time analytics,   │
 │ config_repo        │  │                          │  │ skip reason distribution   │
 └────────────────────┘  └────────────────────────┘  └────────────────────────────┘


 DASHBOARD (optional, enabled via config.dashboard_enabled)
 ═════════════════════════════════════════════════════════════════════════════════════

 ┌──────────────────────┐          ┌──────────────────────────────────────────────┐
 │   React Frontend     │   HTTP   │           FastAPI Backend                    │
 │   frontend/          │◀────────▶│           10 route modules:                  │
 │   (Vite+TS+Tailwind) │          │                                              │
 │                      │          │  /api/signals         (list, filter)         │
 │   - Live Signals     │          │  /api/trades          (list, P&L)            │
 │   - Trade Journal    │          │  /api/performance     (metrics, charts)      │
 │   - Performance      │          │  /api/strategies      (per-strategy stats)   │
 │   - Strategies       │          │  /api/allocation      (capital weights)      │
 │   - Allocation       │          │  /api/settings        (user config CRUD)     │
 │   - Settings         │          │  /api/circuit-breaker  (status, log)         │
 │   - News Sentiment   │          │  /api/adaptation       (log, states)         │
 │   - Earnings         │          │  /api/news            (sentiment, suppressed)│
 │                      │          │  /api/earnings        (upcoming calendar)    │
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


 DATABASE SCHEMA (12 tables, SQLite WAL mode)
 ═════════════════════════════════════════════════════════════════════════════════════

 Core Tables:
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

 Phase 3 Tables:
 ┌───────────────┐  ┌───────────────┐  ┌───────────────┐  ┌────────────────────────┐
 │ hybrid_scores │  │circuit_breaker│  │adaptation_log │  │   vwap_cooldown        │
 │               │  │    _log       │  │               │  │                        │
 │ Phase 3       │  │ Phase 3       │  │ Phase 3       │  │ Phase 2                │
 │               │  │               │  │               │  │                        │
 │ 4-factor      │  │ activation/   │  │ throttle/     │  │ per-stock signal       │
 │ breakdown,    │  │ override      │  │ pause/resume  │  │ cooldown tracking      │
 │ confirmation  │  │ events        │  │ events        │  │                        │
 └───────────────┘  └───────────────┘  └───────────────┘  └────────────────────────┘

 Phase 4 Tables (Quick Actions):
 ┌────────────────────────┐  ┌────────────────────────────────────────────────────┐
 │   signal_actions       │  │   watchlist                                        │
 │                        │  │                                                    │
 │ Phase 4                │  │ Phase 4                                            │
 │                        │  │                                                    │
 │ action (taken/skip/    │  │ symbol, strategy, entry_price                     │
 │   watch), reason,      │  │ expires_at (5 days), triggered_count              │
 │ response_time_ms       │  │ last_triggered_at                                 │
 └────────────────────────┘  └────────────────────────────────────────────────────┘

 Phase 4 Tables (News Sentiment Filter):
 ┌────────────────────────────────────────┐  ┌───────────────────────────────────┐
 │   news_sentiment_cache                │  │   earnings_calendar               │
 │                                        │  │                                   │
 │ Phase 4 — NSF                          │  │ Phase 4 — NSF                     │
 │                                        │  │                                   │
 │ stock_code, composite_score,          │  │ stock_code, earnings_date,        │
 │ label (STRONG_NEGATIVE/MILD_NEGATIVE/ │  │ quarter, is_confirmed,            │
 │   NEUTRAL/POSITIVE/NO_NEWS),          │  │ source (csv/screener.in),         │
 │ headline_count, top_headline,         │  │ updated_at                        │
 │ top_negative_headline,                │  │                                   │
 │ model_used (vader/finbert),           │  │ Queries: has_earnings_today,      │
 │ fetched_at, expires_at                │  │ get_upcoming_earnings(days)       │
 │                                        │  │                                   │
 │ Queries: get_stock_sentiment,         │  │                                   │
 │ get_top_negative_headline,            │  │                                   │
 │ upsert_headlines, purge_old_entries   │  │                                   │
 └────────────────────────────────────────┘  └───────────────────────────────────┘
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
  [ ... ]       Inline keyboard button
  ( ... )       Annotation or description
```

---

## Data Model Transformation Chain

Each pipeline stage transforms data through a specific model type. The
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
                   ┌──────────────┐
                   │ RankedSignal │
                   │              │
                   │ candidate    │
                   │ composite_   │
                   │  score       │
                   │ rank         │
                   │ signal_      │
                   │  strength    │
                   │  (1-5 stars) │
                   └──────┬───────┘
                          │
                          ▼
          ┌────────────────────────────────────────────────┐
          │        NewsSentimentStage Filter               │
          │                                                │
          │  ┌──────────────┐        ┌──────────────────┐  │
          │  │SentimentResult│       │SuppressedSignal   │  │
          │  │              │        │                   │  │
          │  │ score        │        │ symbol, strategy  │  │
          │  │ label        │        │ original_stars    │  │
          │  │ headline     │        │ sentiment_score   │  │
          │  │ action       │        │ sentiment_label   │  │
          │  │ headline_    │        │ top_headline      │  │
          │  │  count       │        │ reason            │  │
          │  │ top_negative │        │ entry/sl/t1       │  │
          │  │  _headline   │        │                   │  │
          │  │ model_used   │        │ (logged,          │  │
          │  └──────────────┘        │  notified via TG) │  │
          │                          └──────────────────┘  │
          └───────────────────────┬────────────────────────┘
                                  │ passed signals
                                  ▼
                   ┌─────────────┐     ┌──────────────┐
                   │ FinalSignal  │────▶│ SignalRecord  │
                   │              │     │              │
                   │ ranked_signal│     │ Persisted in │
                   │ quantity     │     │ signals table│
                   │ capital_     │     │              │
                   │  required    │     │ +composite_  │
                   │ expires_at   │     │  score       │
                   │              │     │ +confirmation│
                   └──────────────┘     │  _level      │
                                        └──────┬───────┘
                                                                    │
                                                     ┌──────────────┤
                                                     │              │
                                           Phase 4   │    TAKEN     │
                                           buttons   │    command   │
                                                     ▼              ▼
                                           ┌───────────────┐ ┌──────────────┐
                                           │SignalAction   │ │ TradeRecord   │
                                           │Record         │ │               │
                                           │               │ │ entry/exit    │
                                           │ action        │ │ pnl_amount    │
                                           │ reason        │ │ pnl_pct       │
                                           │ response_ms   │ │ exit_reason   │
                                           └───────────────┘ │ taken_at      │
                                                             │ exited_at     │
                                                             └──────────────┘
```

Summary of the full chain:

```
 TickData --> CandidateSignal --> ConfirmationResult --> CompositeScoreResult
          --> RankedSignal --> [NewsSentimentStage: SentimentResult filter]
              ├── suppressed --> SuppressedSignal (notified, not delivered)
              └── passed --> FinalSignal --> SignalRecord
                                              ├──▶ SignalActionRecord (Phase 4)
                                              └──▶ TradeRecord (via TAKEN)
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
| NewsSentimentStage | **Active** -- using pre-market cache (fetched at 8:30)   |
| CircuitBreaker     | Reset at 9:15, monitoring SL events via EventBus         |
| AdaptiveManager    | Reset at 9:15, all strategies at NORMAL                  |

### ENTRY_WINDOW Phase (9:30 - 9:45)

| Component          | Activity                                                 |
|--------------------|----------------------------------------------------------|
| Gap & Go           | **Active** -- entry validation, signal generation         |
| ORB                | Inactive (opening range still building)                   |
| VWAP Reversal      | Inactive                                                 |
| Pipeline Stages    | Full 12-stage pipeline running                           |
| PersistAndDeliver  | Signals delivered with [ TAKEN ] [ SKIP ] [ WATCH ]      |

### CONTINUOUS Phase (9:45 - 14:30)

| Component          | Activity                                                 |
|--------------------|----------------------------------------------------------|
| Gap & Go           | Inactive (entry window closed)                           |
| ORB                | **Active 9:45-11:00** -- breakout detection               |
| VWAP Reversal      | **Active 10:00-14:30** -- mean-reversion setups           |
| Opening Ranges     | Locked at 9:45 (30-min range finalized)                  |
| ConfidenceStage    | Cross-strategy confirmation (ORB + VWAP overlap)         |
| CompositeScoring   | Full 4-factor scoring with live win rates                |
| NewsSentimentStage | Filters/downgrades signals based on cached sentiment     |
| CircuitBreaker     | May activate if SL limit reached (Stage 1 gate)          |
| AdaptiveManager    | May throttle/pause losing strategies (Stage 7 filter)    |
| ExitMonitor        | Full monitoring: SL, T1, T2, trailing SL, breakeven     |
| Phase 4 Buttons    | Active on all delivered signals and exit alerts           |

### WIND_DOWN Phase (14:30 - 15:30)

| Component          | Activity                                                 |
|--------------------|----------------------------------------------------------|
| All Strategies     | Inactive (_accepting_signals = False at 14:30)           |
| ExitMonitor        | **Active** -- monitoring all open positions               |
| Exit Reminder      | 15:00 -- advisory alerts with [ Exit Now ] [ Hold ]      |
| Mandatory Exit     | 15:15 -- force-close all open trades                     |
| Daily Summary      | 15:30 -- performance metrics + strategy breakdown        |
| Shutdown           | 15:35 -- WebSocket disconnect, bot stop, DB close        |

### Pre-Market (8:30 - 9:15)

| Component          | Activity                                                 |
|--------------------|----------------------------------------------------------|
| Pre-Market News    | 8:30 -- RSS fetch + VADER analysis, cache in SQLite      |
| Pre-Market Alert   | 9:00 -- advisory Telegram message                        |

### Off-Hours

| Component          | Activity                                                 |
|--------------------|----------------------------------------------------------|
| Weekly Rebalance   | Sunday 18:00 -- CapitalAllocator recalculates weights    |
| MarketScheduler    | Running, all weekday jobs guarded by trading day check   |
| Dashboard          | Available if enabled (reads from SQLite)                 |
