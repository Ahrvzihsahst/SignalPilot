# Product Requirements Document (PRD)
# SignalPilot — Phase 3: Hybrid Scoring Engine + Dashboard

**Version:** 3.0  
**Date:** February 15, 2026  
**Author:** Biswajit (Product Owner & Developer)  
**Status:** Phase 3 — Development starts Week 11 (after Phase 2 validated and live)  
**Prerequisites:** Phase 1 (Gap & Go) and Phase 2 (ORB + VWAP Reversal) complete and running live

---

## 1. Phase 3 Overview

Phase 3 transforms SignalPilot from a multi-strategy signal tool into an **intelligent, self-adapting trading system** with a professional dashboard. No new strategies are added — instead, the existing 3 strategies are unified under a Hybrid Scoring Engine that ranks, confirms, and adapts in real-time.

**What Phase 3 delivers:**

| Component | Description |
|-----------|-------------|
| Confidence Score | Multi-strategy confirmation boosts signal strength and position size |
| Smart Ranking | Unified scoreboard ranks all signals by composite score with win-rate tiebreaker |
| Adaptive Strategy Selection | Real-time intraday auto-learning — reduces signals after 3 consecutive losses in a day (extends existing weekly rebalance and auto-pause from Phase 2) |
| Daily Circuit Breaker | Auto-pauses ALL signals after 3 stop losses in a single day |
| Dashboard (React + FastAPI) | Live signals, trade journal, performance charts, strategy comparison, settings |

**What Phase 3 does NOT include:**
- No new strategies (3 is sufficient for personal MVP)
- No multi-user support (Phase 4)
- No mobile app (Phase 4)
- No monetization features (Phase 4)

---

## 2. Hybrid Scoring Engine

### 2.1 Component A: Confidence Score — Multi-Strategy Confirmation

When a stock triggers 2 or more strategies simultaneously (within the same 15-minute window), the signal is treated as a **multi-strategy confirmed signal** with enhanced properties.

**Detection Logic:**

```
For each new signal generated:
  1. Check if any other strategy has generated a signal for the SAME stock
     within the last 15 minutes
  2. If YES → Mark as "Multi-Strategy Confirmed"
  3. Count confirming strategies (2/3 or 3/3)
```

**What happens when confirmed:**

| Enhancement | 2/3 Strategies Agree | 3/3 Strategies Agree |
|-------------|---------------------|---------------------|
| Star rating boost | +1 star (e.g., 3★ → 4★) | +2 stars (auto 5★) |
| Signal label | "🔥 CONFIRMED (2/3)" | "🔥🔥 TRIPLE CONFIRMED (3/3)" |
| Position size | 1.5x normal allocation | 2x normal allocation |
| Priority in queue | Jumps to #1 in ranking | Jumps to #1 + displaces weakest open position if slots are full |

**Position Size Override Rules:**

```
Normal allocation = Total Capital ÷ max_positions
  (currently: Total Capital ÷ 8, via PositionSizer.calculate() in signalpilot/risk/position_sizer.py)

Confirmed (2/3):
  Allocation = Normal × 1.5
  Max = Total Capital ÷ 5 (capped — never exceed 20% of capital on one trade)

Triple Confirmed (3/3):
  Allocation = Normal × 2.0
  Max = Total Capital ÷ 4 (capped — never exceed 25% of capital on one trade)
```

**Example:** Capital = ₹50,000 → Normal = ₹6,250

| Confirmation | Allocation | Cap |
|---|---|---|
| Single strategy | ₹6,250 | ₹6,250 |
| 2/3 confirmed | ₹9,375 | ₹10,000 (20% cap) |
| 3/3 confirmed | ₹12,500 | ₹12,500 (25% cap) |

**Telegram Alert for Confirmed Signals:**

```
🔥 MULTI-STRATEGY CONFIRMED — TATA MOTORS

📋 Confirmed by: Gap & Go + ORB (2/3 strategies)
📍 Entry Price: ₹645.00
🛑 Stop Loss: ₹631.10 (2.15% risk)
🎯 Target 1: ₹654.68 (1.5%)
🎯 Target 2: ₹661.13 (2.5%)
📊 Quantity: 23 shares (1.5x allocation)
💰 Capital Required: ₹14,835
⚡ Signal Strength: ★★★★★ (Boosted from ★★★★)
📝 Reason: Stock gapped up 3.8% AND broke 30-min opening
   range high with 2.1x volume. Double confirmation.

⏰ Valid for: 30 mins | Positions open: 3/8
━━━━━━━━━━━━━━━━━━━━━━
Reply TAKEN to log this trade
```

**Important Constraints:**
- Confirmed signals still respect the max 8 position limit (`default_max_positions = 8`)
- If taking a 1.5x or 2x position would exceed remaining available capital, scale down to what's available
- A confirmed signal does NOT bypass the auto-skip rule for expensive stocks (quantity == 0 when stock price exceeds per-trade allocation)

**Implementation Note — DuplicateChecker Modification Required:**

The current `DuplicateChecker` (`signalpilot/monitor/duplicate_checker.py`) suppresses same-stock signals from different strategies on the same day via `signal_repo.has_signal_for_stock_today()`. For Confidence Score to detect multi-strategy confirmation, this behavior must be relaxed during the 15-minute confirmation window:
- **Within a 15-minute window:** allow the same stock to generate signals from multiple strategies (needed for confirmation detection)
- **After confirmation is resolved:** resume normal dedup behavior for subsequent scan cycles
- **Active trade blocking:** if a stock already has an active TRADE (not just a signal), continue blocking as before via `trade_repo.get_active_trades()`

---

### 2.2 Component B: Smart Ranking — Unified Scoreboard

All signals from all strategies are ranked on a single unified scoreboard using a composite score.

**Composite Score Calculation:**

```
Composite Score = (Strategy Signal Strength × 0.4)
               + (Strategy Win Rate × 0.3)
               + (Risk-Reward Ratio × 0.2)
               + (Confirmation Bonus × 0.1)

Where:
  Strategy Signal Strength = Per-strategy score (normalized 0-100)
  Strategy Win Rate = Trailing 30-day win rate from strategy_performance table (0-100)
  Risk-Reward Ratio = Target / Stop Loss distance (normalized 0-100)
  Confirmation Bonus = 0 (single), 50 (2/3 confirmed), 100 (3/3 confirmed)
```

**Relationship to Existing Scoring System:**

The `Strategy Signal Strength` component maps directly to the existing per-strategy scoring output from `SignalScorer` (`signalpilot/ranking/scorer.py`), which produces a 0.0-1.0 score scaled to 0-100. Current per-strategy scoring weights (configurable via `AppConfig`):
- **Gap & Go:** `gap_pct` (0.40) + `volume_ratio` (0.35) + `price_distance` (0.25) — via `SignalScorer`
- **ORB:** `volume` (0.40) + `range_size` (0.30) + `breakout_distance` (0.30) — via `ORBScorer`
- **VWAP Reversal:** `volume` (0.35) + `vwap_touch` (0.35) + `trend_confirmation` (0.30) — via `VWAPScorer`

The new Composite Score wraps these existing strategy-specific scores with cross-strategy factors (win rate from `StrategyPerformanceRepository`, risk-reward ratio, confirmation bonus) to create a unified ranking across all three strategies. The existing `SignalRanker` and star-rating system (1-5 stars based on score thresholds) will be replaced by this unified scoreboard.

**Tiebreaker Rule:**
When two signals have the same composite score:
→ **Higher trailing win rate strategy wins**
→ If still tied → Better risk-reward ratio wins
→ If still tied → Most recent signal wins

**Ranking in Practice:**

When user sends `STATUS`, signals are shown ranked by composite score:

```
📊 ACTIVE SIGNALS (Ranked)
━━━━━━━━━━━━━━━━━━━━━━

#1 🔥 TATA MOTORS ★★★★★ | Score: 87
   📋 Confirmed: Gap & Go + ORB
   Status: +1.2% | TAKEN ✅

#2 INFOSYS ★★★★☆ | Score: 72
   📋 Strategy: VWAP Reversal
   Status: +0.4% | TAKEN ✅

#3 HDFC BANK ★★★☆☆ | Score: 61
   📋 Strategy: ORB
   Status: -0.3% | TAKEN ✅

#4 🔒 RELIANCE ★★★★☆ | Score: 68
   📋 Strategy: VWAP Reversal
   Status: Position full — reference only

━━━━━━━━━━━━━━━━━━━━━━
Positions: 3/8 | Capital used: ₹24,250/₹50,000
```

---

### 2.3 Component C: Adaptive Strategy Selection — Real-Time Auto-Learning

The system continuously monitors each strategy's performance and adapts in real-time within the trading day.

**Intraday Adaptation Rules:**

| Trigger | Action | Recovery |
|---------|--------|----------|
| Strategy hits 3 consecutive losses TODAY | Reduce that strategy's signals — only send 5★ signals for rest of day | Resumes normally next trading day |
| Strategy hits 5 consecutive losses TODAY | Fully pause that strategy for rest of day | Resumes normally next trading day |
| Strategy hit rate drops below 35% over trailing 5 days | Send warning to user: "⚠️ [Strategy] underperforming. Consider pausing." | User decides via existing PAUSE/RESUME commands |
| Strategy hit rate drops below 30% over trailing 10 days | Auto-pause strategy via `config_repo.set_strategy_enabled()`. Notify user. | User must manually RESUME after reviewing |

**Foundation Already Built (Phase 2):**

The weekly rebalance mechanism already exists and Phase 3 builds on top of it:
- `CapitalAllocator` (`signalpilot/risk/capital_allocator.py`) calculates expectancy-weighted allocation using 30-day rolling `strategy_performance` data
- Auto-pause recommendation triggers at `win_rate < 40%` with `>= 10 trades` in 30 days (via `check_auto_pause()`)
- Sunday 18:00 IST cron job (`weekly_rebalance` in `MarketScheduler`) runs allocation calculation + auto-pause check + Telegram summary
- Fixed 20% reserve (`RESERVE_PCT = 0.20`) is held back; 80% distributed across strategies using normalized expectancy weights
- Manual override via `ALLOCATE GAP 40 ORB 20 VWAP 20` command (total must be <= 80%)

**Weekly Adaptation (Enhanced from Phase 2):**

```
Every Sunday at 6:00 PM:

1. Calculate trailing 30-day performance per strategy (extends existing CapitalAllocator.calculate_allocations())
2. Recalculate capital weights using performance-based formula (extends existing expectancy-weighted logic)
3. If any strategy has < 40% win rate for 30 days (existing auto-pause threshold, now with paper-trading recovery):
   → Auto-pause
   → Enter 1-week paper trading mode for that strategy
   → If paper trading recovers to > 50% → suggest re-enabling
4. If any strategy has > 70% win rate for 30 days:
   → Increase its weight by 10% (bonus allocation)
   → Cap at 50% of total capital (no single strategy dominance)
5. Send weekly rebalancing report to Telegram
```

**Telegram Adaptation Alerts:**

```
⚠️ INTRADAY ADAPTATION

📋 Strategy: ORB
🔴 Status: 3 consecutive losses today
📉 Action: Reduced to 5★ signals only for rest of day
🔄 Recovery: Normal operation resumes tomorrow

Today's ORB results: 0W / 3L | -₹540
━━━━━━━━━━━━━━━━━━━━━━
```

```
📊 WEEKLY REBALANCING REPORT — Feb 22, 2026
━━━━━━━━━━━━━━━━━━━━━━

⚡ Gap & Go: 58% WR → Weight: 35% (+2%)
📐 ORB: 61% WR → Weight: 20% (unchanged)
📈 VWAP: 69% WR → Weight: 25% (+3%) 🔥 Top performer
🏦 Reserve: 20% (fixed)

Changes applied. New allocations active from Monday.
━━━━━━━━━━━━━━━━━━━━━━
```

---

## 3. Daily Circuit Breaker

**Rule:** If 3 stop losses are hit across ANY combination of strategies in a single day, ALL signal generation pauses for the rest of the day.

**Note:** This is distinct from the existing scan-loop circuit breaker (10 consecutive errors → stops the scan loop for system stability, in `SignalPilotApp._scan_loop()`). The Phase 3 circuit breaker is a **trading-level** safety mechanism that monitors SL hits across active trades via `ExitMonitor` callbacks.

**Logic:**

```
daily_sl_count = 0

On each stop loss hit (triggered by ExitMonitor._persist_exit() with exit_reason="sl_hit"):
  daily_sl_count += 1

  if daily_sl_count == 2:
    Send alert: "⚠️ 2 stop losses hit today. 1 more triggers circuit breaker."

  if daily_sl_count >= 3:
    Set _accepting_signals = False (same flag used by stop_new_signals() at 14:30)
    Continue monitoring existing positions (SL/Target/Trailing SL alerts still active via ExitMonitor)
    Send alert: "🛑 CIRCUIT BREAKER ACTIVATED..."

Reset daily_sl_count to 0 at start of each trading day (in start_scanning() at 9:15 AM)
```

**Circuit Breaker Telegram Alert:**

```
🛑 CIRCUIT BREAKER ACTIVATED

3 stop losses hit today. All new signals paused.
Existing positions are still being monitored.

Today's results:
  ⚡ Gap & Go: HDFC BANK → SL hit (-₹180)
  📐 ORB: WIPRO → SL hit (-₹210)
  📈 VWAP: ICICI BANK → SL hit (-₹150)

💰 Total loss today: -₹540 (1.08% of capital)
📋 Action: No new signals until tomorrow 9:15 AM
━━━━━━━━━━━━━━━━━━━━━━
"Bad days happen. Protecting capital is more
important than catching opportunities."
```

**Important:**
- Circuit breaker only stops NEW signals — existing open positions continue to be monitored for SL/Target/Trailing SL/Time exit
- Circuit breaker resets automatically at 9:00 AM next trading day
- User can manually override via new command: `OVERRIDE CIRCUIT` (with confirmation prompt)

---

## 4. Dashboard — React + FastAPI

### 4.1 Architecture

```
┌──────────────────────────────────────────────┐
│               SIGNALPILOT DASHBOARD          │
│                                              │
│  ┌─────────────┐      ┌──────────────────┐  │
│  │   React      │◄────►│    FastAPI        │  │
│  │   Frontend   │      │    Backend        │  │
│  │   (Vite)     │      │                  │  │
│  │   Port 3000  │      │   Port 8000      │  │
│  └─────────────┘      └────────┬─────────┘  │
│                                 │            │
│                         ┌───────▼────────┐   │
│                         │    SQLite DB   │   │
│                         │  (shared with  │   │
│                         │   signal       │   │
│                         │   engine)      │   │
│                         └────────────────┘   │
│                                              │
│  Access: http://localhost:3000               │
│  Host: Same machine as signal engine         │
└──────────────────────────────────────────────┘
```

**Tech Stack:**

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + Vite + Tailwind CSS |
| Charts | Recharts (React-native charting, lightweight) |
| State Management | React Query (server state) + useState (UI state) |
| Backend API | FastAPI (Python) — shares SQLite DB with signal engine |
| Database | SQLite (same DB used by signal engine — no duplication, WAL mode) |
| Data Source | Existing repos: `SignalRepository`, `TradeRepository`, `MetricsCalculator`, `StrategyPerformanceRepository`, `ConfigRepository` |
| Access | localhost:3000 (local only) |

### 4.2 Pages & Features

**Page 1: Live Signals Panel (Home)**

```
┌─────────────────────────────────────────────────┐
│  SignalPilot Dashboard        📊 Feb 15, 2026   │
├─────────────────────────────────────────────────┤
│                                                  │
│  ┌── Market Status: 🟢 OPEN (11:42 AM) ───────┐│
│  │ Capital: ₹50,410  |  Positions: 4/8         ││
│  │ Today's P&L: +₹320 (+0.63%)                 ││
│  │ Circuit Breaker: 1/3 SL (inactive)           ││
│  └──────────────────────────────────────────────┘│
│                                                  │
│  ACTIVE SIGNALS (Ranked by Composite Score)      │
│  ┌──────────────────────────────────────────────┐│
│  │ #1 🔥 TATA MOTORS  ★★★★★  Score: 87        ││
│  │    Confirmed: Gap & Go + ORB                 ││
│  │    Entry: ₹645 | SL: ₹631 | T1: ₹654       ││
│  │    P&L: +₹180 (+1.2%) | Qty: 23             ││
│  │    Status: ✅ TAKEN | Trailing SL active      ││
│  ├──────────────────────────────────────────────┤│
│  │ #2 INFOSYS  ★★★★☆  Score: 72               ││
│  │    Strategy: VWAP Reversal (Uptrend Pullback)││
│  │    Entry: ₹1,485 | SL: ₹1,467 | T1: ₹1,500 ││
│  │    P&L: +₹60 (+0.4%) | Qty: 4               ││
│  │    Status: ✅ TAKEN                           ││
│  ├──────────────────────────────────────────────┤│
│  │ #3 HDFC BANK  ★★★☆☆  Score: 61             ││
│  │    Strategy: ORB                             ││
│  │    Entry: ₹1,720 | SL: ₹1,685 | T1: ₹1,746 ││
│  │    P&L: -₹52 (-0.3%) | Qty: 3               ││
│  │    Status: ✅ TAKEN                           ││
│  └──────────────────────────────────────────────┘│
│                                                  │
│  EXPIRED/REFERENCE SIGNALS                       │
│  ┌──────────────────────────────────────────────┐│
│  │ 🔒 RELIANCE  ★★★★☆ — Position full          ││
│  │ ⏰ BAJAJ AUTO  ★★★☆☆ — Expired (30 min)     ││
│  └──────────────────────────────────────────────┘│
└─────────────────────────────────────────────────┘
```

**Features:**
- Auto-refreshes every 30 seconds (polls FastAPI)
- Color-coded P&L (green = profit, red = loss)
- Click on any signal to expand full details (reason, strategy scores, timestamps)
- Circuit breaker status bar at top

---

**Page 2: Trade Journal**

```
┌─────────────────────────────────────────────────┐
│  Trade Journal                                   │
├─────────────────────────────────────────────────┤
│                                                  │
│  Filters: [Date Range ▼] [Strategy ▼] [Result ▼]│
│  Search: [____________] [🔍]                     │
│                                                  │
│  ┌────┬──────────┬─────────┬────────┬──────────┐│
│  │Date│  Stock   │Strategy │ P&L    │  Result   ││
│  ├────┼──────────┼─────────┼────────┼──────────┤│
│  │2/15│TATA MOTOR│Gap+ORB🔥│ +₹890  │ T2 Hit   ││
│  │2/15│INFOSYS   │VWAP     │ +₹150  │ T1 Hit   ││
│  │2/14│HDFC BANK │ORB      │ -₹410  │ SL Hit   ││
│  │2/14│RELIANCE  │Gap & Go │ +₹320  │ T1 Hit   ││
│  │2/13│WIPRO     │VWAP     │ +₹85   │ Time Exit││
│  │2/13│ICICI BANK│ORB      │ -₹220  │ SL Hit   ││
│  └────┴──────────┴─────────┴────────┴──────────┘│
│                                                  │
│  Page: [< 1 2 3 ... 12 >]  |  Export: [CSV] [PDF]│
│                                                  │
│  Summary: 48 trades | 29W 19L | WR: 60.4%       │
│  Total P&L: +₹4,280 | Avg Win: ₹298 | Avg Loss:││
│  ₹189 | Best: +₹890 | Worst: -₹410             │
└─────────────────────────────────────────────────┘
```

**Features:**
- Filter by date range, strategy, result (win/loss/SL/target/time exit)
- Search by stock name
- Click on any row to expand full signal details
- Export to CSV for external analysis
- Running summary stats at the bottom (updates with filters)

---

**Page 3: Performance Charts**

```
┌─────────────────────────────────────────────────┐
│  Performance                [1W] [1M] [3M] [ALL]│
├─────────────────────────────────────────────────┤
│                                                  │
│  EQUITY CURVE                                    │
│  ₹54k ┤                              ╭──────    │
│  ₹52k ┤                    ╭────────╯           │
│  ₹50k ┤──────╮   ╭────────╯                     │
│  ₹48k ┤       ╰──╯                               │
│       └──────────────────────────────────────    │
│        Jan 15    Jan 25    Feb 5     Feb 15      │
│                                                  │
│  DAILY P&L                                       │
│  +₹800 ┤   █                     █               │
│  +₹400 ┤   █  █     █  █     █  █  █            │
│       0 ┤───────────────────────────────          │
│  -₹400 ┤      █  █        █        █             │
│       └──────────────────────────────────        │
│                                                  │
│  WIN RATE OVER TIME (Rolling 20-trade)           │
│    70% ┤         ╭──╮         ╭────              │
│    60% ┤───╮  ╭──╯  ╰──╮  ╭──╯                  │
│    50% ┤    ╰──╯         ╰──╯                     │
│       └──────────────────────────────────        │
│                                                  │
│  MONTHLY SUMMARY                                 │
│  ┌──────────┬─────────┬────────┬────────────────┐│
│  │  Month   │ Trades  │ Win %  │ Net P&L        ││
│  ├──────────┼─────────┼────────┼────────────────┤│
│  │  Feb '26 │   22    │ 63.6%  │ +₹2,340        ││
│  │  Jan '26 │   26    │ 57.7%  │ +₹1,940        ││
│  └──────────┴─────────┴────────┴────────────────┘│
└─────────────────────────────────────────────────┘
```

**Charts included:**
- Equity curve (cumulative P&L over time)
- Daily P&L bar chart (green/red bars)
- Win rate trend line (rolling 20-trade average)
- Monthly summary table
- Time period selectors: 1 week, 1 month, 3 months, All

---

**Page 4: Strategy Comparison**

```
┌─────────────────────────────────────────────────┐
│  Strategy Comparison          Period: [Last 30D ▼]│
├─────────────────────────────────────────────────┤
│                                                  │
│  ┌─────────────┬──────────┬─────────┬──────────┐│
│  │  Metric     │ Gap & Go │   ORB   │  VWAP    ││
│  ├─────────────┼──────────┼─────────┼──────────┤│
│  │ Win Rate    │  57%     │  63%    │  68% 🏆  ││
│  │ Total Trades│  14      │  10     │  18      ││
│  │ Net P&L     │ +₹3,280  │ +₹520  │ +₹960   ││
│  │ Avg Win     │  ₹580    │  ₹210  │  ₹150   ││
│  │ Avg Loss    │  ₹260    │  ₹180  │  ₹120   ││
│  │ Expectancy  │ +2.31%   │ +0.29% │ +0.43%  ││
│  │ Profit Factor│  2.23   │  1.17  │  1.25   ││
│  │ Max Consec L│  3       │  2     │  2       ││
│  │ Capital Wt  │  40%     │  20%   │  25%     ││
│  │ Status      │  🟢 Live │ 🟢 Live│ 🟢 Live ││
│  └─────────────┴──────────┴─────────┴──────────┘│
│                                                  │
│  P&L BY STRATEGY (Stacked Area Chart)            │
│  ₹5k ┤    ████████████████████████████           │
│  ₹3k ┤    ████████████████░░░░░░░░░░░░          │
│      ┤    ████████░░░░░░░░▒▒▒▒▒▒▒▒▒▒▒          │
│    0 └───────────────────────────────────        │
│       █ Gap & Go  ░ ORB  ▒ VWAP                  │
│                                                  │
│  CONFIRMED SIGNALS PERFORMANCE                   │
│  Multi-strategy confirmed: 6 trades              │
│  Win Rate: 83% | Avg P&L: +₹420                 │
│  vs Single strategy: 60% WR | Avg P&L: +₹180    │
└─────────────────────────────────────────────────┘
```

**Features:**
- Side-by-side comparison table for all strategies
- Stacked area chart showing cumulative P&L contribution per strategy
- Confirmed signals performance section (proves hybrid scoring value)
- Filter by time period (1 week, 1 month, 3 months, all)
- Highlights best-performing strategy with 🏆

---

**Page 5: Capital Allocation**

```
┌─────────────────────────────────────────────────┐
│  Capital Allocation                              │
├─────────────────────────────────────────────────┤
│                                                  │
│  CURRENT ALLOCATION (Donut Chart)                │
│                                                  │
│           ┌──────────┐                           │
│        ╭──│ Gap & Go ├──╮                        │
│       │   │   40%    │   │                       │
│       │   └──────────┘   │                       │
│    ╭──┤                  ├──╮                    │
│    │VWAP│               │ORB│                    │
│    │25% │               │20%│                    │
│    ╰──┤    Reserve     ├──╯                     │
│       │     20%        │                         │
│       ╰────────────────╯                         │
│                                                  │
│  ALLOCATION HISTORY (Line Chart)                 │
│  50% ┤ ─── Gap & Go                             │
│  40% ┤────────────────────────────               │
│  30% ┤ ─── VWAP                                  │
│  20% ┤─────── ORB ────────────────               │
│  10% ┤                                            │
│      └────────────────────────────               │
│       Week 1  Week 2  Week 3  Week 4             │
│                                                  │
│  REBALANCING LOG                                 │
│  ┌──────────┬──────────────────────────────────┐│
│  │  Date    │  Change                          ││
│  ├──────────┼──────────────────────────────────┤│
│  │  Feb 16  │ VWAP: 22% → 25% (+3%)           ││
│  │  Feb 16  │ Reserve: 20% (fixed)              ││
│  │  Feb 9   │ Gap & Go: 38% → 40% (+2%)       ││
│  │  Feb 9   │ ORB: 22% → 20% (-2%)            ││
│  └──────────┴──────────────────────────────────┘│
│                                                  │
│  Next rebalance: Sunday, Feb 22                  │
│                                                  │
│  [Manual Override]                                │
│  Gap & Go: [35%▼] ORB: [20%▼] VWAP: [25%▼]     │
│  Reserve: 20% (fixed)  [Apply] [Reset to Auto]   │
└─────────────────────────────────────────────────┘
```

**Features:**
- Donut chart showing current allocation
- Line chart showing allocation changes over time (weekly rebalance history)
- Rebalancing log with every change recorded
- Manual override controls with Apply/Reset buttons (total must be <= 80%; 20% reserve is always held back per existing `RESERVE_PCT = 0.20`)

---

**Page 6: Settings**

```
┌─────────────────────────────────────────────────┐
│  Settings                                        │
├─────────────────────────────────────────────────┤
│                                                  │
│  CAPITAL & RISK                                  │
│  ┌──────────────────────────────────────────────┐│
│  │ Total Capital:     [₹ 50,000    ] [Update]  ││
│  │ Max Positions:     [8           ] [Update]  ││
│  │ Circuit Breaker:   [3 SL/day    ] [Update]  ││
│  └──────────────────────────────────────────────┘│
│                                                  │
│  STRATEGIES                                      │
│  ┌──────────────────────────────────────────────┐│
│  │ ⚡ Gap & Go         [🟢 Enabled ] [Pause]   ││
│  │ 📐 ORB              [🟢 Enabled ] [Pause]   ││
│  │ 📈 VWAP Reversal    [🟢 Enabled ] [Pause]   ││
│  └──────────────────────────────────────────────┘│
│                                                  │
│  HYBRID SCORING                                  │
│  ┌──────────────────────────────────────────────┐│
│  │ Confidence Boost:   [🟢 On ] [Off]          ││
│  │ Adaptive Learning:  [🟢 On ] [Off]          ││
│  │ Auto-Rebalance:     [🟢 On ] [Off]          ││
│  │ Intraday Adaptation:[🟢 Aggressive ▼]       ││
│  │   Options: Conservative / Moderate / Aggressive│
│  └──────────────────────────────────────────────┘│
│                                                  │
│  NOTIFICATIONS                                   │
│  ┌──────────────────────────────────────────────┐│
│  │ Telegram Chat ID:  [123456789  ] [Verify]   ││
│  │ Signal alerts:      [🟢 On ]               ││
│  │ SL/Target alerts:   [🟢 On ]               ││
│  │ Daily summary:      [🟢 On ]               ││
│  │ Weekly report:      [🟢 On ]               ││
│  │ Adaptation alerts:  [🟢 On ]               ││
│  └──────────────────────────────────────────────┘│
│                                                  │
│  DATA                                            │
│  ┌──────────────────────────────────────────────┐│
│  │ [Export All Trades CSV]                      ││
│  │ [Export Performance Report PDF]              ││
│  │ [Reset Paper Trading Data]                   ││
│  │ [⚠️ Reset All Data]                          ││
│  └──────────────────────────────────────────────┘│
└─────────────────────────────────────────────────┘
```

**Features:**
- Update capital and risk parameters without Telegram commands
- Enable/disable individual strategies with one click
- Toggle hybrid scoring components independently
- Configure notification preferences
- Export data (CSV for trades, PDF for performance report)
- Reset options with confirmation dialogs

---

## 5. Updated Database Schema (Phase 3 Additions)

**Existing Schema (Phase 1 + Phase 2):**

Before Phase 3, the database has 5 tables:
- `signals` — 18 columns including Phase 2 additions: `setup_type` (TEXT), `strategy_specific_score` (REAL)
- `trades` — 15 columns including Phase 2 addition: `strategy` (TEXT, default `'gap_go'`)
- `user_config` — 9 columns including Phase 2 additions: `gap_go_enabled`, `orb_enabled`, `vwap_enabled` (all INTEGER 0/1)
- `strategy_performance` — 13 columns: daily per-strategy metrics (signals, wins, losses, pnl, win_rate, expectancy, capital_weight_pct) used by `CapitalAllocator` for weekly rebalancing
- `vwap_cooldown` — 3 columns: per-symbol signal cooldown tracking

All tables use SQLite WAL mode with `aiosqlite` and `Row` factory.

### 5.1 New Tables

**hybrid_scores table:**
```
id, signal_id, composite_score, strategy_strength_score,
win_rate_score, risk_reward_score, confirmation_bonus,
confirmed_by (comma-separated strategy names or null),
confirmation_level (single/double/triple),
position_size_multiplier (1.0/1.5/2.0),
created_at
```

**circuit_breaker_log table:**
```
id, date, sl_count, triggered_at, resumed_at,
manual_override (0/1), override_at
```

**adaptation_log table:**
```
id, date, strategy, event_type (consecutive_loss/pause/resume/rebalance),
details, old_weight, new_weight, created_at
```

### 5.2 Modified Tables

**signals table (add columns):**

Note: `setup_type` (TEXT) and `strategy_specific_score` (REAL) already exist from Phase 2. The new `composite_score` is the unified cross-strategy Hybrid Score (Section 2.2), distinct from the per-strategy `strategy_specific_score`.

```
+ composite_score (FLOAT) — unified Hybrid Score, distinct from existing strategy_specific_score
+ confirmation_level (TEXT: single/double/triple)
+ confirmed_by (TEXT: comma-separated strategy names)
+ position_size_multiplier (FLOAT: 1.0/1.5/2.0)
+ adaptation_status (TEXT: normal/reduced/paused)
```

**user_config table (add columns):**

Note: `gap_go_enabled`, `orb_enabled`, `vwap_enabled` (all INTEGER 0/1) already exist from Phase 2. The columns below are new Phase 3 additions.

```
+ circuit_breaker_limit (INT, default 3)
+ confidence_boost_enabled (INT 0/1, default 1)
+ adaptive_learning_enabled (INT 0/1, default 1)
+ auto_rebalance_enabled (INT 0/1, default 1)
+ adaptation_mode (TEXT: conservative/moderate/aggressive)
```

**strategy_performance table (no schema changes):**

The existing `strategy_performance` table (Phase 2) is used as-is for Composite Score win-rate lookups and adaptive strategy selection. No new columns needed — the table already stores `win_rate`, `expectancy`, `avg_win`, `avg_loss`, and `capital_weight_pct` per strategy per day.

---

## 6. New Telegram Commands (Phase 3)

| Command | Response |
|---------|----------|
| `OVERRIDE CIRCUIT` | Disables circuit breaker for rest of day (with confirmation: "Are you sure? Reply YES to confirm") |
| `SCORE [STOCK]` | Shows composite score breakdown for a specific stock if signal exists |
| `ADAPT` | Shows current adaptation status for each strategy |
| `REBALANCE` | Triggers manual rebalance immediately (calls existing `CapitalAllocator.calculate_allocations()`) |

**Existing commands enhanced (9 commands already implemented in Phase 1 + Phase 2):**

Current commands: `TAKEN [id]`, `STATUS`, `JOURNAL`, `CAPITAL <amount>`, `PAUSE <strategy>`, `RESUME <strategy>`, `ALLOCATE [AUTO | GAP x ORB y VWAP z]`, `STRATEGY`, `HELP`

Phase 3 enhancements:
- `STATUS` → Now shows composite scores and confirmation badges alongside existing live P&L
- `JOURNAL` → Now includes confirmed signal stats alongside existing performance metrics
- `STRATEGY` → Now shows adaptation history and intraday status alongside existing 30-day per-strategy breakdown
- `TAKEN [id]` → Already supports optional signal ID for specific signal selection (no change needed)

---

## 7. FastAPI Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/signals/live` | GET | Active signals with real-time P&L |
| `/api/signals/history` | GET | Historical signals with filters |
| `/api/trades` | GET | Trade journal with filters, pagination |
| `/api/trades/export` | GET | CSV/PDF export |
| `/api/performance/equity-curve` | GET | Equity curve data points |
| `/api/performance/daily-pnl` | GET | Daily P&L bars |
| `/api/performance/win-rate` | GET | Rolling win rate data |
| `/api/performance/monthly` | GET | Monthly summary |
| `/api/strategies/comparison` | GET | Side-by-side strategy stats |
| `/api/strategies/confirmed` | GET | Confirmed signals performance |
| `/api/allocation/current` | GET | Current capital weights |
| `/api/allocation/history` | GET | Allocation changes over time |
| `/api/allocation/override` | POST | Manual allocation update |
| `/api/allocation/reset` | POST | Reset to auto-allocation |
| `/api/settings` | GET/PUT | User settings CRUD |
| `/api/settings/strategies` | PUT | Enable/disable strategies |
| `/api/circuit-breaker` | GET | Current circuit breaker status |
| `/api/circuit-breaker/override` | POST | Manual override |
| `/api/adaptation/status` | GET | Adaptation status per strategy |
| `/api/adaptation/log` | GET | Adaptation event history |

---

## 8. Development Timeline

Phase 3 starts at **Week 11** after Phase 2 is validated and live.

| Week | Deliverable |
|------|------------|
| Week 11 | Hybrid Scoring Engine: Confidence Score (multi-strategy confirmation), Composite Score calculation, Smart Ranking with tiebreaker logic |
| Week 12 | Adaptive Strategy Selection: Intraday adaptation (3 consecutive loss detection), weekly rebalancing enhancement, circuit breaker implementation |
| Week 13 | FastAPI backend: All API endpoints, SQLite integration, new database tables |
| Week 14 | React Dashboard: Live Signals Panel + Trade Journal pages |
| Week 15 | React Dashboard: Performance Charts + Strategy Comparison pages |
| Week 16 | React Dashboard: Capital Allocation + Settings pages. Integration testing. Phase 3 go-live. |

---

## 9. Risks Specific to Phase 3

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Confidence Score over-allocates to confirmed signals | One bad confirmed trade = bigger loss | Hard caps: 20% max for 2/3, 25% max for 3/3 confirmed |
| Adaptive learning too aggressive | Good strategy paused after temporary bad streak | 3 consecutive losses only reduces (not pauses). 5 needed for full pause. Auto-resumes next day. |
| Dashboard adds latency to signal engine | Signals delayed due to API serving | FastAPI runs as separate process. Signal engine has priority. Dashboard polls every 30 seconds (not real-time). |
| SQLite concurrent access issues | Dashboard reads while engine writes | WAL mode already enabled in `DatabaseManager.initialize()`. Use separate read-only connection for FastAPI. |
| Circuit breaker triggers too often in volatile markets | Miss recovery opportunities | User can override with `OVERRIDE CIRCUIT`. Limit is configurable in Settings. |
| Dashboard scope creep | Development extends beyond timeline | 6 pages defined — no additions until Phase 4 |

---

## 10. Success Metrics for Phase 3

| Metric | Target |
|--------|--------|
| Confirmed signals win rate | > 75% (vs ~60% for single strategy signals) |
| Composite score top-3 signals win rate | > 65% |
| Adaptive learning prevents > 5 consecutive losses | 100% of trading days |
| Circuit breaker triggers | < 2 times per month (indicates strategies are healthy) |
| Dashboard page load time | < 2 seconds on localhost |
| Dashboard data freshness | < 30 seconds lag from signal engine |
| Weekly rebalancing accuracy | Runs correctly every Sunday without manual intervention |
| System stability (engine + dashboard) | > 98% uptime during market hours |

---

## 11. What's Next — Phase 4 Preview

Phase 3 completes the personal MVP. Phase 4 will focus on scaling to multi-user and monetization:

- Multi-user Telegram bot (individual capital tracking per user)
- User authentication and account management
- Cloud deployment (move from laptop to AWS/DigitalOcean)
- Mobile-responsive dashboard (or dedicated mobile app)
- Subscription/payment system
- SEBI RA registration (if operating as signal service)
- WhatsApp integration
- Paper trading mode for new users

---

*Document End — Phase 3 PRD v3.0*
*Prerequisites: Phase 1 + Phase 2 complete and running live*
*Development begins: Week 11*
*Estimated completion: Week 16*
