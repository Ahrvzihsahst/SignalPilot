# Product Requirements Document (PRD)
# SignalPilot — Phase 2: Opening Range Breakout (ORB) + VWAP Reversal

**Version:** 2.0  
**Date:** February 15, 2026  
**Author:** Biswajit (Product Owner & Developer)  
**Status:** Phase 2 — Development starts Week 5 (parallel with Phase 1 live)  
**Prerequisites:** Phase 1 (Gap & Go) complete and running live

---

## 1. Phase 2 Overview

Phase 2 adds two new intraday strategies to SignalPilot that fill the trading day beyond the morning Gap & Go window. These strategies generate signals from 9:45 AM through 2:30 PM, transforming SignalPilot from a morning-only tool into a full-day scanning engine.

| Time Coverage | Strategy | Phase |
|---|---|---|
| 9:30–9:45 AM | Gap & Go (already live) | Phase 1 ✅ |
| 9:45 AM–11:00 AM | **Opening Range Breakout (ORB)** | **Phase 2 (NEW)** |
| 10:00 AM–2:30 PM | **VWAP Reversal** | **Phase 2 (NEW)** |

**What Phase 2 delivers:**
- 2 new strategies scanning throughout the day
- Multi-strategy signal ranking and duplicate prevention
- Performance-based capital allocation across all 3 strategies
- Max positions increased from 5 to 8
- Backtesting validation + 2-week paper trading before going live
- New Telegram commands: ALLOCATE, STRATEGY, PAUSE, RESUME

---

## 2. Strategy A: Opening Range Breakout (ORB)

### 2.1 Overview

The Opening Range Breakout strategy waits for the first 30 minutes of trading to establish a price range, then enters when price breaks above that range with volume confirmation. This captures directional moves that develop after the initial market volatility settles.

**Signal Window:** 9:45 AM – 11:00 AM (after range is formed)  
**Direction:** Long only (short selling to be added later as "Advanced Mode")

### 2.2 Entry Conditions (ALL must be true)

1. Opening range defined as the HIGH and LOW between 9:15–9:45 AM (30-minute range)
2. Price breaks ABOVE the opening range high
3. Volume on breakout candle > 1.5x average candle volume
4. Opening range size is between 0.5%–3% of stock price (too narrow = false breakouts, too wide = poor risk-reward)
5. Stock is in Nifty 500 (liquid stocks only)
6. Stock has NOT already gapped 3%+ at open (those are Gap & Go territory — no overlap)

### 2.3 Entry Timing

9:45 AM onwards, only when breakout candle closes above the opening range high

### 2.4 Risk-Reward (Conservative)

| Parameter | Value |
|-----------|-------|
| Stop Loss | Below opening range low (2–3% from entry) |
| Target 1 | 1.5% from entry |
| Target 2 | 2.5–3% from entry |
| Expected Win Rate | 60–65% |
| Risk-Reward Ratio | 1:1.2 |
| Expected Signals | 8–12 per month (after filtering) |

### 2.5 Exit Logic

| Condition | Action |
|-----------|--------|
| Target 1 hit (1.5%) | Alert: "🎯 Target 1 hit! Consider booking partial profit" |
| Target 2 hit (2.5-3%) | Alert: "🎯🎯 Target 2 hit! Full exit recommended" |
| Stop Loss hit | Alert: "🛑 Stop Loss hit. Exit immediately." |
| Trailing SL | After +1.5% move → SL tightens to breakeven. After +2% → SL trails at 1% below current price |
| Time exit (3:00 PM) | Alert: "⏰ Close all intraday positions in next 15 mins" |

### 2.6 Duplicate Prevention

- If a stock already triggered a Gap & Go signal (gapped 3%+), ORB will NOT generate a signal for the same stock on the same day
- If a user already has an active position in a stock, ORB will skip that stock

### 2.7 Signal Strength Calculation

| Factor | Weight |
|--------|--------|
| Breakout candle volume vs average | 40% |
| Opening range size (tighter = more explosive breakout) | 30% |
| Distance from range (closer to breakout level = tighter SL) | 30% |

### 2.8 Future Addition: Short Selling (Advanced Mode)

Short selling via ORB breakdown (price breaks below opening range low) will be added after the founder has personally validated short signals for 30 consecutive trading days. When added:

- SHORT signal: Price breaks below opening range low with volume
- Stop Loss: Above opening range high
- Targets: Same 1.5% / 2.5–3% (to the downside)
- Users must explicitly enable "Advanced Mode" to receive short signals

---

## 3. Strategy B: VWAP Reversal

### 3.1 Overview

The VWAP Reversal strategy identifies stocks that pull back to the Volume Weighted Average Price (VWAP) and bounce, indicating institutional buying interest at fair value. This strategy fires throughout the trading day, filling the gap between morning strategies and market close.

**Signal Window:** 10:00 AM – 2:30 PM (continuous scanning)  
**Candle Timeframe:** 15-minute candles  
**Direction:** Long only

### 3.2 Entry Conditions — Setup 1: Uptrend Pullback (ALL must be true)

1. Stock was trading above VWAP earlier in the day (established uptrend)
2. Price pulls back to touch or dip slightly below VWAP (within 0.3%)
3. 15-minute candle closes back above VWAP (bullish bounce confirmed)
4. Volume on bounce candle > average 15-min candle volume
5. Stock is in Nifty 500

### 3.3 Entry Conditions — Setup 2: VWAP Reclaim from Below (ALL must be true)

1. Stock was trading below VWAP (bearish morning)
2. Price crosses above VWAP with a strong 15-minute bullish candle
3. Volume on reclaim candle > 1.5x average 15-min candle volume (higher threshold — riskier setup)
4. Stock is in Nifty 500

**Note:** VWAP Reclaim from below is flagged as "⚠️ Higher Risk" in the signal to the user.

### 3.4 Risk-Reward (Conservative)

**Setup 1 — Uptrend Pullback to VWAP:**

| Parameter | Value |
|-----------|-------|
| Stop Loss | Below VWAP by 0.5% (1–1.5% total risk) |
| Target 1 | 1% from entry |
| Target 2 | 1.5–2% from entry |
| Expected Win Rate | 65–70% |
| Risk-Reward Ratio | 1:1 |

**Setup 2 — VWAP Reclaim from Below (riskier):**

| Parameter | Value |
|-----------|-------|
| Stop Loss | Below the recent swing low (2–3% risk) |
| Target 1 | 1.5% from entry |
| Target 2 | 2–2.5% from entry |
| Expected Win Rate | 55–60% |
| Risk-Reward Ratio | 1:1 |

**Combined Expected Signals:** 15–25 per month (before filtering)

### 3.5 Exit Logic

| Condition | Action |
|-----------|--------|
| Target 1 hit | Alert: "🎯 Target 1 hit! Consider booking partial profit" |
| Target 2 hit | Alert: "🎯🎯 Target 2 hit! Full exit recommended" |
| Stop Loss hit | Alert: "🛑 Stop Loss hit. Exit immediately." |
| Trailing SL (Uptrend Pullback) | After +1% move → SL tightens to breakeven |
| Trailing SL (VWAP Reclaim) | After +1.5% move → SL tightens to breakeven |
| Time exit (3:00 PM) | Alert: "⏰ Close all intraday positions in next 15 mins" |

### 3.6 Signal Strength Calculation

| Factor | Weight |
|--------|--------|
| Bounce candle volume vs average | 35% |
| Precision of VWAP touch (closer = cleaner setup) | 35% |
| Overall day trend alignment | 30% |

### 3.7 VWAP Signal Guardrails

| Guardrail | Rule |
|-----------|------|
| Max VWAP signals per stock per day | 2 (first two touches are cleanest) |
| No duplicate on active positions | If user has an active position in a stock, skip it |
| Cooldown period | After a VWAP signal on a stock, no new signal for that stock for at least 60 minutes |
| No signals after 2:30 PM | Insufficient time for trade to play out before 3:15 PM exit |

---

## 4. Multi-Strategy Rules

### 4.1 Max Open Positions (Updated)

| Rule | Phase 1 (Gap & Go only) | Phase 2 (3 strategies) |
|------|------------------------|----------------------|
| Max simultaneous positions | 5 | **8** |
| Per-trade capital | Total Capital ÷ 5 | **Total Capital ÷ 8** |

**Example:** ₹50,000 capital → Per-trade allocation = ₹6,250 in Phase 2

### 4.2 Capital Allocation — Performance-Based

Capital is allocated based on each strategy's historical win rate and expectancy. The system recalculates allocation weekly based on trailing 30-day backtested performance.

**Allocation Formula:**

```
Strategy Weight = (Win Rate × Avg Win) - ((1 - Win Rate) × Avg Loss)
                  ─────────────────────────────────────────────────────
                  Sum of all strategy weights

Capital per strategy = Total Capital × Strategy Weight
Max positions per strategy = Max Total Positions × Strategy Weight (rounded)
```

**Example with initial backtest data:**

| Strategy | Win Rate | Avg Win | Avg Loss | Expectancy | Weight | Positions (of 8) |
|----------|---------|---------|----------|-----------|--------|-----------------|
| Gap & Go | 55% | 6.5% | 2.8% | +2.31% | 38% | 3 |
| ORB | 62% | 2.0% | 2.5% | +0.29% | 17% | 2 |
| VWAP Reversal | 67% | 1.25% | 1.25% | +0.43% | 25% | 2 |
| Reserve (unallocated) | — | — | — | — | 20% | 1 |

**Reserve capital (20%):** Always keep 1 position worth of capital unallocated as buffer for exceptional signals (★★★★★ strength).

**Weekly Rebalancing:**
- Every Sunday, recalculate weights from the trailing 30-day performance
- If a strategy's win rate drops below 40% for 30 days, auto-pause it and notify user
- User can manually override allocations via Telegram command: `ALLOCATE`

### 4.3 Signal Priority & Duplicate Prevention

When multiple strategies fire on the same stock:

1. **Same stock, same day** → Only the FIRST signal is sent. Subsequent signals for that stock are suppressed.
2. **Active position exists** → No new signals for stocks with active positions.
3. **All position slots full** → New signals are queued and shown as "🔒 Position full — signal for reference only"
4. **Cross-strategy ranking:** When signals from different strategies arrive simultaneously, rank by Signal Strength (★ rating) regardless of strategy.

### 4.4 Auto-Skip Rules (Carried from Phase 1)

| Rule | Description |
|------|-------------|
| Stock price exceeds per-trade allocation | Signal is suppressed (e.g., MRF at ₹1,20,000 with ₹6,250 allocation) |
| Signal expiry | 30 minutes from generation — auto-expires if not acted upon |
| No new signals after 2:30 PM | Insufficient time for trade to play out before 3:15 PM exit |
| ORB excludes Gap & Go stocks | Stocks that gapped 3%+ are excluded from ORB scanning |

---

## 5. Updated Telegram Bot

### 5.1 New Commands (Phase 2)

| Command | Response |
|---------|----------|
| `ALLOCATE` | Shows current capital allocation per strategy and allows override |
| `STRATEGY` | Shows performance breakdown per strategy (win rate, P&L, signals) |
| `PAUSE GAP` / `PAUSE ORB` / `PAUSE VWAP` | Temporarily pauses a specific strategy |
| `RESUME GAP` / `RESUME ORB` / `RESUME VWAP` | Resumes a paused strategy |

**Existing commands remain unchanged:** TAKEN, STATUS, JOURNAL, CAPITAL, HELP

### 5.2 Updated Signal Format (Phase 2)

```
🟢 BUY SIGNAL — INFOSYS

📍 Entry Price: ₹1,485.00
🛑 Stop Loss: ₹1,467.00 (1.2% risk)
🎯 Target 1: ₹1,499.85 (1%)
🎯 Target 2: ₹1,507.25 (1.5%)
📊 Quantity: 4 shares
💰 Capital Required: ₹5,940
⚡ Signal Strength: ★★★★☆ (Strong)
📋 Strategy: VWAP Reversal (Uptrend Pullback)
📝 Reason: Stock pulled back to VWAP at ₹1,483 after
   morning uptrend. 15-min bounce candle closed at ₹1,485
   with 1.8x average volume. Clean reversal setup.

⏰ Valid for: 30 mins | Positions open: 4/8
━━━━━━━━━━━━━━━━━━━━━━
Reply TAKEN to log this trade
```

**Changes from Phase 1 format:**
- "Positions open: X/8" replaces "X/5"
- Strategy name now shows specific setup type (e.g., "VWAP Reversal (Uptrend Pullback)" or "VWAP Reversal ⚠️ Higher Risk")
- Capital required reflects Phase 2 allocation (Total ÷ 8)

### 5.3 Updated Automated Alerts

| Time | Alert |
|------|-------|
| 9:00 AM | "🔍 Pre-market scan running. Signals coming shortly." |
| 9:30–9:45 AM | Gap & Go signals |
| 9:45 AM–11:00 AM | Opening Range Breakout signals |
| 10:00 AM–2:30 PM | VWAP Reversal signals as conditions are met |
| During market hours | SL hit / Target hit / Trailing SL updates |
| 2:30 PM | "🚫 No new signals. Monitoring existing positions only." |
| 3:00 PM | "⏰ Close all intraday positions in next 15 minutes" |
| 3:30 PM | Daily summary with per-strategy performance breakdown |

### 5.4 Updated Daily Summary (Phase 2)

```
📊 DAILY SUMMARY — Feb 15, 2026
━━━━━━━━━━━━━━━━━━━━━━

📋 BY STRATEGY:
  ⚡ Gap & Go: 2 signals | 1 taken | +₹320
  📐 ORB: 3 signals | 2 taken | +₹180
  📈 VWAP Reversal: 4 signals | 2 taken | -₹90

📈 TOTALS:
  Signals: 9 | Taken: 5 | Skipped: 4
  🏆 Wins: 3 | Losses: 2
  💰 Net P&L: +₹410

💪 Capital: ₹50,410 (+0.82%)
━━━━━━━━━━━━━━━━━━━━━━
```

### 5.5 STRATEGY Command Output

```
📊 STRATEGY PERFORMANCE (Last 30 Days)
━━━━━━━━━━━━━━━━━━━━━━

⚡ GAP & GO
  Win Rate: 57% | Trades: 14
  Avg Win: +₹580 | Avg Loss: -₹260
  Net P&L: +₹3,280 | Capital: 38%

📐 OPENING RANGE BREAKOUT
  Win Rate: 63% | Trades: 10
  Avg Win: +₹210 | Avg Loss: -₹180
  Net P&L: +₹520 | Capital: 17%

📈 VWAP REVERSAL
  Win Rate: 68% | Trades: 18
  Avg Win: +₹150 | Avg Loss: -₹120
  Net P&L: +₹960 | Capital: 25%

🏦 Reserve: 20% (1 position buffer)
━━━━━━━━━━━━━━━━━━━━━━
Next rebalance: Sunday, Feb 22
```

---

## 6. Updated Database Schema (Phase 2 Additions)

### 6.1 Modified Tables

**signals table (updated):**
```
id, date, symbol, strategy (gap_go/orb/vwap_reversal),
setup_type (for VWAP: uptrend_pullback/vwap_reclaim),
entry_price, stop_loss, target_1, target_2, quantity,
capital_required, signal_strength, strategy_specific_score,
reason, created_at, expires_at,
status (sent/expired/paper/position_full)
```

**trades table (updated):**
```
id, signal_id, date, symbol, strategy, entry_price,
exit_price, stop_loss, quantity, pnl_amount, pnl_pct,
exit_reason (sl_hit/t1_hit/t2_hit/time_exit/trailing_sl),
taken_at, exited_at
```

**user_config table (updated):**
```
id, telegram_chat_id, total_capital, max_positions,
gap_go_enabled (1/0), orb_enabled (1/0), vwap_enabled (1/0),
created_at, updated_at
```

### 6.2 New Tables

**strategy_performance table:**
```
id, strategy, date, signals_generated, signals_taken,
wins, losses, total_pnl, win_rate, avg_win, avg_loss,
expectancy, capital_weight_pct
```

**vwap_cooldown table:**
```
id, symbol, last_signal_at, signal_count_today
```

---

## 7. Backtesting Requirement

Before any Phase 2 strategy goes live, it MUST pass the following validation.

### 7.1 Backtest Criteria

| Criteria | Minimum Threshold |
|----------|------------------|
| Historical data period | Minimum 1 year of Nifty 500 daily data |
| Win rate | Must exceed 55% on historical data |
| Expectancy | Must be positive (net profitable) |
| Max consecutive losses | Must not exceed 8 in a row |
| Max drawdown | Must not exceed 15% of capital |
| Sample size | Minimum 100 signal occurrences in backtest period |

### 7.2 Backtest-to-Live Validation

After backtest passes, strategy enters a **2-week paper trading phase:**

1. Strategy generates signals in real-time but marked as "📝 PAPER TRADE" in Telegram
2. User does NOT trade these signals with real money
3. Tool tracks what would have happened if signals were followed
4. After 2 weeks, compare paper results to backtest expectations
5. If within 10% variance → strategy goes live
6. If outside 10% variance → investigate and re-calibrate

---

## 8. Development Timeline

Phase 2 development runs **parallel with Phase 1 live trading.**

| Week | Deliverable |
|------|------------|
| Week 5 | ORB strategy coding + backtesting on 1-year Nifty 500 data |
| Week 6 | VWAP Reversal strategy coding + backtesting on 1-year Nifty 500 data |
| Week 7 | Multi-strategy integration: performance-based capital allocation, duplicate prevention, signal ranking, new Telegram commands (ALLOCATE, STRATEGY, PAUSE, RESUME) |
| Week 8 | Phase 2 paper trading begins — ORB and VWAP signals marked as "📝 PAPER TRADE" alongside live Gap & Go signals |
| Week 9–10 | Paper trading validation period (2 weeks). Compare results to backtest expectations. |
| Week 10 | If within 10% variance → Phase 2 goes live. If not → re-calibrate and re-test. |

---

## 9. Technical Changes from Phase 1

### 9.1 New Dependencies

| Component | Purpose |
|-----------|---------|
| VWAP calculation library | Real-time VWAP computation from tick data |
| 15-minute candle aggregator | Build 15-min candles from WebSocket tick data for VWAP strategy |
| Opening range tracker | Store and compute 30-min high/low for ORB |

### 9.2 WebSocket Changes

Phase 1 already maintains a full-day WebSocket connection (9:15 AM–3:30 PM). Phase 2 requires:

- **Additional computed fields per tick:** Running VWAP, 15-min candle OHLCV, opening range high/low
- **State management for 500 stocks:** Each stock needs its own VWAP, candle history, opening range, and cooldown tracker
- **Performance consideration:** Processing 500 stocks on 15-min candles = ~500 × 25 candles/day = 12,500 candle evaluations. Well within laptop capability.

### 9.3 Data Flow Update

```
9:15 AM       → Market opens. WebSocket connected. Start recording opening range.
9:15–9:30 AM  → Phase 1: Monitor gap + volume for Gap & Go
9:30–9:45 AM  → Phase 1: Send Gap & Go signals
9:45 AM       → Opening range (30-min) locked. ORB scanning begins.
9:45–11:00 AM → Phase 2: ORB breakout monitoring
10:00 AM      → VWAP Reversal scanning begins (first 15-min candle completes at 9:30, need trend context by 10:00)
10:00 AM–2:30 PM → Phase 2: Continuous VWAP monitoring with guardrails
2:30 PM       → Stop all new signal generation
2:30–3:15 PM  → Monitor existing positions only (SL/Target/Trailing SL)
3:00 PM       → Exit reminder
3:30 PM       → Daily summary with per-strategy breakdown. Disconnect.
```

---

## 10. Risks Specific to Phase 2

| Risk | Impact | Mitigation |
|------|--------|-----------|
| ORB false breakouts | Consecutive losses, erodes confidence | Opening range 0.5-3% filter eliminates most noise |
| VWAP signals too frequent | Alert fatigue | Max 2 per stock/day + 60-min cooldown |
| Performance-based allocation over-fits | Capital shifts too aggressively | Weekly rebalancing (not daily), 20% reserve buffer |
| Paper trading doesn't match live execution | Slippage, fill delays in real trading | Conservative targets already account for slippage |
| Strategy underperforms after going live | Capital loss | Auto-pause if win rate drops below 40% for 30 days |
| Laptop handling 3 strategies + 500 stocks | Performance/memory issues | 15-min candles (not 1-min), efficient state management |

---

## 11. Success Metrics for Phase 2

| Metric | Target |
|--------|--------|
| ORB backtest win rate | ≥ 60% on 1-year Nifty 500 data |
| VWAP backtest win rate | ≥ 65% on 1-year Nifty 500 data |
| Paper trading variance | Within 10% of backtest results |
| Combined system win rate (all 3 strategies) | ≥ 58% |
| Daily signal count (after filtering) | 3–8 signals per day |
| No duplicate signals | 0 duplicate stock signals per day |
| Alert fatigue check | User receives max 15 messages/day (signals + updates) |
| Capital allocation accuracy | Rebalancing runs correctly every Sunday |

---

*Document End — Phase 2 PRD v2.0*
*Prerequisites: Phase 1 (Gap & Go) complete and running live*
*Development begins: Week 5 (parallel with Phase 1 live)*
