# Product Requirements Document (PRD)
# Intraday Trading Signal Generator — "SignalPilot"

**Version:** 1.0  
**Date:** February 15, 2026  
**Author:** Biswajit (Product Owner & Developer)  
**Status:** MVP — Personal Use → Future SaaS

---

## 1. Executive Summary

SignalPilot is a pure intraday signal generation tool for Indian equity markets (NSE). It scans Nifty 500 stocks during market hours, identifies high-probability trade setups using predefined technical strategies, and delivers actionable buy/sell signals via Telegram — complete with entry price, stop loss, target, and quantity.

The tool is designed for complete beginners who trade on Zerodha/Groww with ₹10K–₹1L capital. It removes emotional decision-making and replaces it with disciplined, rule-based signals. The user executes trades manually — SignalPilot never places orders.

---

## 2. Problem Statement

Indian retail traders (especially beginners) suffer from:

- Trading based on emotions, gut feel, or unverified tips from Telegram/WhatsApp groups
- Missing opportunities because they can't watch the market all day
- Inconsistent decision-making — rules change based on mood
- Inability to test if their trading ideas work before risking real money
- Losing money to psychological biases (holding losers too long, selling winners too early)

**Current solutions:** Most beginners rely on tips groups, social media influencers, or random chart screenshots — none of which are systematic, backtested, or risk-managed.

---

## 3. Target User

| Attribute | Detail |
|-----------|--------|
| Experience Level | Complete beginner (0–1 year of trading) |
| Market | Indian equities — NSE only |
| Capital Range | ₹10,000 – ₹1,00,000 |
| Current Broker | Zerodha / Groww (manual execution) |
| Trading Style | Intraday (buy and sell same day) |
| Current Behavior | Tips-based, emotional, inconsistent |
| Goal | Follow a disciplined system without needing to understand the technicals |

**User Persona — "Rahul":**  
Rahul is a 28-year-old software developer in Pune. He opened a Zerodha account 6 months ago with ₹30,000. He's lost ₹5,000 so far following random Telegram tips. He doesn't know what RSI or MACD means, but he wants a system that tells him exactly what to buy, when to buy, where to set stop loss, and when to exit. He wants to check his phone at 9:30 AM, see a clear signal, place the trade on Zerodha, and go to work.

---

## 4. Product Vision

**"Signals you can trust, discipline you can follow."**

SignalPilot sends clear, actionable, risk-managed intraday signals so beginners can trade like disciplined professionals — without needing to understand technical analysis.

---

## 5. Core Feature: Signal Generation

### 5.1 What the User Sees (Signal Format)

```
🟢 BUY SIGNAL — TATA MOTORS

📍 Entry Price: ₹645.00
🛑 Stop Loss: ₹631.10 (2.15% risk)
🎯 Target 1: ₹677.25 (5%)
🎯 Target 2: ₹690.15 (7%)
📊 Quantity: 15 shares
💰 Capital Required: ₹9,675
⚡ Signal Strength: ★★★★☆ (Strong)
📋 Strategy: Gap & Go
📝 Reason: Stock gapped up 4.2% at open on strong Q3 results.
   Volume in first 15 mins is 2.3x average daily volume.
   Holding above opening price.

⏰ Valid Until: 30 mins from signal | Auto-expires after that
━━━━━━━━━━━━━━━━━━━━━━
Reply TAKEN to log this trade
Reply STATUS to check open signals
Reply JOURNAL to view your performance
```

### 5.2 Signal Logic (Phase 1 — Gap & Go Strategy)

**Entry Conditions (ALL must be true):**

1. Stock gaps up 3–5% at market open (9:15 AM)
2. Opens above previous day's high
3. Volume in first 15 minutes > 50% of average daily volume
4. Stock is in Nifty 500 (liquid stocks only)

**Entry Timing:** 9:30–9:45 AM, only if stock holds above opening price

**Note:** Gap & Go is inherently a market-open strategy — gaps only exist at 9:15 AM. However, the scanning engine runs continuously (9:15 AM–3:30 PM) so that Phase 2 and Phase 3 strategies can generate signals throughout the day without any architectural changes.

**Stop Loss:** Below opening price (2–3% from entry)

**Targets:**
- Target 1: 5% from entry
- Target 2: 7% from entry

**Expected Performance:**
- Win Rate: 52–58%
- Average Win: 6.5%
- Average Loss: 2.8%
- Expectancy: +2.2% per trade
- Signals: 20–25 per month (before filtering)

### 5.3 Strategy Roadmap (Phased Implementation)

| Phase | Timeline | Strategy | Type |
|-------|----------|----------|------|
| Phase 1 | Week 1–4 | Gap & Go | Intraday |
| Phase 2 | Week 5–8 | VWAP Bounce + Opening Range Breakout | Intraday |
| Phase 3 | Week 9–12 | Intraday Momentum + Hybrid Scoring | Intraday |

**Note:** The originally discussed swing strategies (52-Week Breakout, Golden Cross, Mean Reversion, Pullback to Support) are NOT suitable for intraday timeframes. They may be added in a future "Swing Trading" module if demand exists.

---

## 6. Risk Management Rules

### 6.1 Position Sizing (Auto-Calculated)

The tool automatically calculates quantity based on:

```
Per-Trade Capital = Total Capital ÷ Max Open Positions (5)
Quantity = Per-Trade Capital ÷ Entry Price
```

**Example:** Capital = ₹50,000 → Per-Trade = ₹10,000

| Stock | Entry Price | Max Quantity | Capital Used |
|-------|------------|-------------|-------------|
| Tata Motors | ₹645 | 15 shares | ₹9,675 |
| Reliance | ₹2,450 | 4 shares | ₹9,800 |
| MRF | ₹1,20,000 | ❌ SKIPPED | Exceeds allocation |

### 6.2 Hard Rules

| Rule | Value |
|------|-------|
| Max open positions | 5 at any time |
| Stop loss per trade | 2–3% (strategy-defined) |
| Max daily positions | Signals ranked by strength, top 5 shown |
| Auto-skip expensive stocks | If stock price > per-trade allocation, signal is suppressed |
| Signal expiry | 30 minutes from generation — auto-expires if not acted upon |
| No new signals after | 2:30 PM (insufficient time for trade to play out before 3:15 PM) |
| Mandatory exit | All positions must be closed by 3:15 PM (intraday) |

### 6.3 Signal Ranking

When multiple stocks trigger simultaneously, signals are ranked by:

1. **Gap percentage** (higher = stronger momentum)
2. **Volume ratio** (higher = stronger conviction)
3. **Distance from opening price** (closer = tighter stop loss = better risk-reward)

Only the top 5 signals are sent to the user.

---

## 7. Exit Logic

### 7.1 Target Hit
- If Target 1 (5%) is hit → Alert user: "🎯 Target 1 hit! Consider booking partial profit"
- If Target 2 (7%) is hit → Alert user: "🎯🎯 Target 2 hit! Full exit recommended"

### 7.2 Stop Loss Hit
- If price drops to SL → Alert user: "🛑 Stop Loss hit on TATA MOTORS at ₹631.10. Exit immediately."

### 7.3 Time-Based Exit
- At 3:00 PM → Alert: "⏰ Market closing in 15 mins. Exit all open intraday positions."
- If position is in profit but hasn't hit target → Recommend exit
- If position is in minor loss (less than SL) → Recommend exit to avoid overnight risk

### 7.4 Trailing Stop Loss
- Once price moves 2%+ in favor, stop loss automatically tightens to breakeven (entry price)
- Once price moves 4%+ in favor, stop loss trails at 2% below current price
- Trailing SL updates are sent via Telegram

---

## 8. Telegram Bot Specification

### 8.1 Bot Type
Two-way interactive Telegram bot

### 8.2 Commands

| User Input | Bot Response |
|------------|-------------|
| (automatic) | Sends signal at 9:30–9:45 AM |
| `TAKEN` | Logs trade as taken. Confirms: "✅ Trade logged. Tracking TATA MOTORS." |
| `STATUS` | Shows all active signals and their current P&L |
| `JOURNAL` | Shows performance summary: win rate, total P&L, avg win/loss |
| `CAPITAL 50000` | Updates user's capital for position sizing |
| `HELP` | Shows available commands |

### 8.3 Automated Alerts

| Time | Alert Type |
|------|-----------|
| 9:00 AM | "🔍 Pre-market scan running. Signals coming shortly." |
| 9:30–9:45 AM | Gap & Go signals (Phase 1) |
| 9:45 AM–2:30 PM | Signals from other strategies as conditions are met (Phase 2/3) |
| During market hours | SL hit / Target hit / Trailing SL updates |
| 2:30 PM | "🚫 No new signals. Monitoring existing positions only." |
| 3:00 PM | "⏰ Close all intraday positions in next 15 minutes" |
| 3:30 PM | Daily summary: signals sent, trades taken, P&L |

---

## 9. Trade Journal

### 9.1 Logging Method
Manual — user replies `TAKEN` to a signal on Telegram

### 9.2 Data Tracked Per Trade

- Date and time
- Stock name and symbol
- Entry price (signal price)
- Stop loss and targets
- Quantity and capital deployed
- Whether user took the trade (TAKEN or not)
- Outcome: SL hit / T1 hit / T2 hit / Time exit
- P&L (₹ and %)
- Strategy used

### 9.3 Journal Summary (via `JOURNAL` command)

```
📊 YOUR TRADING JOURNAL
━━━━━━━━━━━━━━━━━━━━━━
📅 Period: Feb 1 – Feb 15, 2026
📈 Signals Sent: 18
✅ Trades Taken: 12
🏆 Win Rate: 58.3% (7W / 5L)
💰 Total P&L: +₹2,340
📊 Avg Win: ₹580 | Avg Loss: ₹266
⚖️ Risk-Reward: 2.18:1
🔥 Best Trade: TATA MOTORS +₹890
💔 Worst Trade: HDFC BANK -₹410
━━━━━━━━━━━━━━━━━━━━━━
```

---

## 10. Technical Architecture

### 10.1 System Overview

```
┌─────────────────────────────────────────────────┐
│                  SIGNAL PILOT                    │
├─────────────────────────────────────────────────┤
│                                                  │
│  ┌──────────┐    ┌──────────┐    ┌───────────┐  │
│  │  Data     │───▶│ Strategy │───▶│  Signal   │  │
│  │  Engine   │    │  Engine  │    │  Ranker   │  │
│  └──────────┘    └──────────┘    └─────┬─────┘  │
│       │                                 │        │
│       │  Angel One                      │        │
│       │  SmartAPI                        ▼        │
│       │  (WebSocket)           ┌───────────────┐ │
│       │                        │  Telegram Bot │ │
│       │                        │  (2-way)      │ │
│       │                        └───────┬───────┘ │
│       │                                │         │
│       │                        ┌───────▼───────┐ │
│       │                        │ Trade Journal │ │
│       │                        │ (SQLite)      │ │
│       │                        └───────────────┘ │
│                                                  │
│  Infrastructure: Windows Laptop + JioFiber       │
│  Runtime: Python 3.11+                           │
└─────────────────────────────────────────────────┘
```

### 10.2 Tech Stack

| Component | Technology | Reason |
|-----------|-----------|--------|
| Language | Python 3.11+ | Angel One SDK, rich ecosystem for finance |
| Live Market Data | Angel One SmartAPI (WebSocket) | Free, real-time, reliable |
| Historical Data | Angel One SmartAPI + yfinance (fallback) | Free backtesting data |
| Stock Universe | Nifty 500 | Liquid, well-traded stocks |
| Strategy Engine | Custom Python (pandas, numpy, ta-lib) | Full control over logic |
| Signal Delivery | python-telegram-bot | Free, instant, two-way |
| Trade Journal | SQLite | Lightweight, zero setup, local |
| Scheduling | APScheduler / Windows Task Scheduler | Auto-start before market |
| OS | Windows | Developer's primary OS |
| Internet | JioFiber | Reliable broadband |

### 10.3 Data Flow (Market Day)

```
8:50 AM  → Script auto-starts
9:00 AM  → Authenticate with Angel One SmartAPI
9:00 AM  → Send "Pre-market scan running" to Telegram
9:15 AM  → Market opens. Subscribe to Nifty 500 WebSocket feed
9:15 AM  → Detect gaps (compare open price vs previous close)
9:15-9:30 AM → Monitor volume accumulation for first 15 minutes
9:30 AM  → Run Gap & Go conditions
9:30-9:45 AM → Rank qualifying Gap & Go signals, send top signals to Telegram
9:45 AM - 2:30 PM → CONTINUOUS SCANNING for all active strategies
           → Any strategy conditions met → Generate signal → Rank → Send to Telegram
           → Monitor open positions for SL/Target/Trailing SL updates
2:30 PM  → Stop generating new signals (not enough time for trades to play out)
2:30-3:00 PM → Monitor existing positions only
3:00 PM  → Send "Close all positions" reminder
3:30 PM  → Send daily summary
3:35 PM  → Disconnect WebSocket, save journal data
```

**Signal Generation Windows by Strategy:**

| Strategy | Signal Window | Reason |
|----------|-------------|--------|
| Gap & Go (Phase 1) | 9:30–9:45 AM | Gap is an opening event only |
| VWAP Bounce (Phase 2) | 9:30 AM–2:30 PM | Bounces happen throughout the day |
| Opening Range Breakout (Phase 2) | 10:00 AM–12:00 PM | After opening range is established |
| Intraday Momentum (Phase 3) | 9:30 AM–2:30 PM | Continuous momentum scanning |

**Architecture Note:** The WebSocket connection and scanning engine run continuously from 9:15 AM to 3:30 PM from day one. Even in Phase 1 (Gap & Go only), the infrastructure supports full-day scanning so that Phase 2 and Phase 3 strategies plug in without any redesign.

### 10.4 Database Schema (SQLite)

**signals table:**
```
id, date, symbol, strategy, entry_price, stop_loss, target_1,
target_2, quantity, capital_required, signal_strength, gap_pct,
volume_ratio, reason, created_at, expires_at, status (sent/expired)
```

**trades table:**
```
id, signal_id, date, symbol, entry_price, exit_price, stop_loss,
quantity, pnl_amount, pnl_pct, exit_reason (sl_hit/t1_hit/t2_hit/time_exit),
taken_at, exited_at
```

**user_config table:**
```
id, telegram_chat_id, total_capital, max_positions,
created_at, updated_at
```

---

## 11. Regulatory Compliance

| Aspect | Status |
|--------|--------|
| Auto-execution of trades | ❌ NOT implemented — signals only |
| SEBI Algo Trading Registration | NOT required (manual execution by user) |
| SEBI Research Analyst (RA) | NOT required for personal use MVP |
| SEBI Investment Advisor (IA) | NOT required for personal use MVP |
| Data Source | Angel One SmartAPI (authorized broker API) |
| Static IP Requirement | NOT needed (no order placement via API) |

**⚠️ Future Consideration:** If this tool is commercialized (sold to others as a signal service), SEBI RA registration may be required. Consult a compliance advisor before monetizing.

---

## 12. MVP Scope — What's IN vs OUT

### ✅ IN (Phase 1 — Week 1 to 4)

- Gap & Go strategy implementation
- Nifty 500 stock scanning
- Real-time data via Angel One SmartAPI WebSocket
- Signal generation with entry, SL, target, quantity
- Signal ranking (top 5 by strength)
- Auto-skip stocks exceeding per-trade allocation
- Signal expiry 30 minutes after generation
- No new signals after 2:30 PM
- Continuous scanning architecture (WebSocket 9:15 AM–3:30 PM) built for future strategy additions
- Telegram bot — signal delivery + TAKEN/STATUS/JOURNAL commands
- Trailing stop loss alerts
- Time-based exit reminder (3:00 PM)
- Daily summary at 3:30 PM
- SQLite trade journal
- Position sizing auto-calculation

### ❌ OUT (Future Phases)

- Additional intraday strategies (VWAP Bounce, ORB, Momentum)
- Hybrid scoring across multiple strategies
- Backtesting dashboard / UI
- Web or mobile app
- Auto-execution via broker API
- WhatsApp delivery
- Multi-user support
- Pricing / subscription system
- News sentiment filtering
- Swing trading module
- Paper trading / simulation mode

---

## 13. Success Metrics (90-Day Goal)

**Primary Goal:** Follow the signal system with 100% discipline for 30 consecutive trading days, and verify that real results match backtested expectations within reasonable range.

| Metric | Target |
|--------|--------|
| Strategy win rate (actual vs backtest) | Within 5% of expected 52–58% |
| Average win vs average loss ratio | > 2:1 |
| Signals generated per month | 15–25 (after filtering) |
| Signal delivery latency | < 30 seconds from condition trigger to Telegram |
| System uptime during market hours | > 95% (no crashes during 9:15–3:30) |
| Personal discipline | 100% — every signal either taken or consciously skipped |

---

## 14. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Angel One API downtime | No signals | yfinance fallback for gap detection (delayed) |
| Laptop crash during market hours | Missed signals / no exit alerts | Windows auto-restart script + phone alarm at 3:00 PM as manual backup |
| JioFiber outage | No connectivity | Mobile hotspot as backup |
| Gap & Go underperforms in choppy markets | Consecutive losses | Max daily loss limit (e.g., 3 SL hits = stop trading for the day) |
| False signals in low-liquidity stocks | Slippage, inability to exit | Nifty 500 filter ensures adequate liquidity |
| SEBI regulatory changes | Tool may need registration | Signal-only, no auto-execution, personal use — lowest regulatory risk |

---

## 15. Development Timeline

| Week | Deliverable |
|------|------------|
| Week 1 | Setup: Angel One SmartAPI auth, WebSocket connection, Nifty 500 instrument list, historical data download |
| Week 2 | Gap & Go strategy logic: gap detection, volume analysis, signal generation, position sizing, ranking |
| Week 3 | Telegram bot: signal delivery, TAKEN/STATUS/JOURNAL commands, exit alerts, trailing SL logic |
| Week 4 | Integration testing with live market data, backtesting validation, bug fixes, go-live |
| Week 5–8 | Phase 2: Add VWAP Bounce + Opening Range Breakout strategies |
| Week 9–12 | Phase 3: Intraday Momentum + Hybrid signal scoring across all strategies |

---

## 16. Open Questions for Future

1. Should there be a "paper trading" mode where the tool tracks signals as if you took them, without real money?
2. Should the tool eventually auto-execute via Kite Connect / Angel One API (requires SEBI compliance)?
3. What's the maximum drawdown threshold before the tool pauses all signals for the day?
4. Should there be a web dashboard for visualizing journal data and strategy performance?
5. When commercializing, what's the target pricing? (Competitors: Streak ₹499/mo, Tradetron ₹750/mo)

---

*Document End — Version 1.0*
*Next Step: Begin Phase 1 development*
