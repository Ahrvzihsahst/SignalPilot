# Product Requirements Document (PRD)
# SignalPilot — Phase 4: Intelligence Layer + UX Upgrade

**Version:** 5.0
**Date:** February 25, 2026
**Author:** Biswajit (Product Owner & Developer)
**Status:** Phase 4 — Development starts Week 13 (after Phase 3 Dashboard is live and stable)
**Prerequisites:** Phase 1 (Gap & Go), Phase 2 (ORB + VWAP), Phase 3 (Hybrid Scoring + Dashboard) complete and running live

---

## 1. Phase 4 Overview

Phase 4 upgrades SignalPilot from a rule-based signal system to an **intelligence-augmented, context-aware** trading engine. Instead of blindly scanning technical patterns, SignalPilot will now understand *market context* (regime), *news context* (sentiment), and deliver **automated daily reporting**.

**What Phase 4 delivers:**

| Component | Description | Impact |
|-----------|-------------|--------|
| End-of-Day Auto-Summary | Automated 3:35 PM report — P&L, wins/losses, best/worst, insight | Analytics: Daily accountability without manual effort |
| News Sentiment Filter | FinBERT-powered filter that suppresses/downgrades signals with negative news | Risk: Prevents catastrophic trades on news-driven events |
| Market Regime Detection | VIX + Nifty first-15-min classifier — Trending/Ranging/Volatile | Alpha: Auto-adjusts strategy weights based on market type |

**What Phase 4 does NOT include:**
- No new trading strategies (3 remain sufficient)
- No auto-execution (remains signal-only, SEBI-compliant)
- No multi-user support (Phase 5 — TBD)
- No mobile app (Phase 5 — TBD)

**Why these 3 features together:**
These features form a coherent "intelligence upgrade" that flows sequentially in a trading day:
```
8:45 AM  → Market Regime Detection classifies the day
9:15 AM  → Signal engine adjusts strategy weights based on regime
9:30 AM+ → Signals fire with News Sentiment pre-filtered
3:35 PM  → EOD Auto-Summary arrives with full daily report
```

---

## 2. Feature 1: End-of-Day Auto-Summary

### 2.1 Problem Statement

Currently, users must manually:
- Calculate daily P&L from individual trade messages
- Remember how many signals were generated vs. taken
- Run `JOURNAL` command to see history
- Run `STRATEGY` command to check which strategy worked

Most users end the day without any structured review, missing critical patterns and lessons.

### 2.2 Solution: Automated Daily Report at 3:35 PM

Every trading day at **3:35 PM IST** (5 minutes after market close at 3:30 PM), the bot automatically sends a comprehensive daily summary.

### 2.3 EOD Summary Message Format

**Full Day — Trades Taken:**

```
━━━━━━━━━━━━━━━━━━━━━━
📊 SIGNALPILOT — DAILY SUMMARY
📅 Tuesday, February 25, 2026
━━━━━━━━━━━━━━━━━━━━━━

💰 TODAY'S P&L: +₹1,245 (+2.49%)
📈 Win Rate: 4/5 (80%)
🔄 Signals Generated: 8 | Taken: 5 | Skipped: 3

🏆 BEST TRADE
   TATAMOTORS | Gap & Go | +₹680 (+3.2%)
   Entry: ₹645 → Exit: ₹665.68 (T2 hit)

💔 WORST TRADE
   HDFCBANK | VWAP Reversal | -₹320 (-1.8%)
   Entry: ₹1,785 → Exit: ₹1,752.87 (SL hit)

━━━ STRATEGY SCORECARD ━━━

📋 Gap & Go:     2/2 wins  | +₹890  | 🟢🟢
📋 ORB:          1/2 wins  | +₹175  | 🟢🔴
📋 VWAP Reversal: 1/1 wins | +₹180  | 🟢

━━━ MARKET CONTEXT ━━━

🌡️ Market Regime: TRENDING (Nifty +1.2%)
📊 India VIX: 14.8 (Low volatility)
🔥 Confirmed Signals: 2 of 8 (25%)

━━━ INSIGHT OF THE DAY ━━━

💡 "Gap & Go crushed it today — trending market with
   low VIX is its sweet spot. 3 of your skipped signals
   would have been winners. Consider increasing signal
   threshold from 3★ to include 3★+ on trending days."

━━━ RUNNING TOTALS ━━━

📅 This Week:  +₹3,450 (Mon-Tue) | 9/12 (75%)
📅 This Month: +₹8,920 (Feb) | 38/52 (73%)
📅 Capital:    ₹50,000 → ₹58,920 (+17.8%)

━━━━━━━━━━━━━━━━━━━━━━
🔗 Full details: http://localhost:3000/journal
```

**Zero Trades Day:**

```
━━━━━━━━━━━━━━━━━━━━━━
📊 SIGNALPILOT — DAILY SUMMARY
📅 Tuesday, February 25, 2026
━━━━━━━━━━━━━━━━━━━━━━

📭 NO TRADES TAKEN TODAY

🔄 Signals Generated: 3 | Taken: 0 | Skipped: 3
📊 Skip Reasons: No Capital (1), Not Confident (2)

📋 If you had taken all signals:
   Hypothetical P&L: +₹445 (2/3 would have won)

🌡️ Market Regime: RANGING (Nifty -0.1%)
📊 India VIX: 18.2 (Moderate)

💡 "Ranging markets tend to work well for VWAP Reversal.
   2 of 3 skipped signals were VWAP setups. Consider
   lowering confidence threshold for VWAP on ranging days."

━━━━━━━━━━━━━━━━━━━━━━
```

**Circuit Breaker Triggered Day:**

```
━━━━━━━━━━━━━━━━━━━━━━
📊 SIGNALPILOT — DAILY SUMMARY
📅 Tuesday, February 25, 2026
━━━━━━━━━━━━━━━━━━━━━━

🛑 CIRCUIT BREAKER ACTIVATED at 11:15 AM

💰 TODAY'S P&L: -₹1,850 (-3.70%)
📈 Win Rate: 0/3 (0%)

⚡ Circuit breaker saved you from 4 additional signals
   that fired after pause. Result: 2 would have lost,
   2 would have won. Net avoided loss: -₹380.

🌡️ Market Regime: VOLATILE (Nifty -2.8% swing)
📊 India VIX: 22.5 (High)

💡 "All 3 losses were Gap & Go on a volatile day.
   Phase 4's Market Regime Detection would have
   reduced Gap & Go weight today. This confirms
   the value of regime-aware trading."

━━━━━━━━━━━━━━━━━━━━━━
```

### 2.4 Insight Engine — Automated Pattern Recognition

The "Insight of the Day" is generated by a rule-based engine that checks for patterns:

**Insight Rules (Priority Order — first match wins):**

| Priority | Condition | Insight Template |
|----------|-----------|------------------|
| 1 | Circuit breaker triggered | "Circuit breaker saved you from {N} additional signals..." |
| 2 | Win rate = 100% | "Perfect day! {strategy} was {N}/{N}. {regime} market with VIX {level} is its sweet spot." |
| 3 | Win rate = 0% | "Tough day. {regime} markets are historically weak for {worst_strategy}. Consider pausing {worst_strategy} on {regime} days." |
| 4 | One strategy >> others | "{best_strategy} carried today ({N}/{M} wins, +₹{amount}). Consider higher allocation." |
| 5 | Skipped signals > Taken | "You skipped {N} of {M} signals. {X} skipped signals would have been winners. Review skip reasons." |
| 6 | Confirmed signals outperformed | "Confirmed signals went {N}/{M} vs single signals {A}/{B}. Multi-strategy confirmation is working." |
| 7 | Average response time > 60s | "Average button tap time was {T} seconds. Faster response = better entry prices." |
| 8 | Partial exits outperformed | "Partial exits earned {X}% more than full exits today. Keep using the T1 partial strategy." |
| 9 | Consecutive win streak | "{N}-trade winning streak! Stay disciplined — don't increase position size on confidence alone." |
| 10 | Default | "Solid trading day. {strategy} performed best in today's {regime} market." |

**Implementation:**

```python
def generate_daily_insight(trades: list, regime: str, vix: float) -> str:
    rules = [
        circuit_breaker_insight,
        perfect_day_insight,
        zero_win_insight,
        strategy_dominance_insight,
        skip_analysis_insight,
        confirmation_insight,
        response_time_insight,
        partial_exit_insight,
        streak_insight,
        default_insight,
    ]
    for rule in rules:
        insight = rule(trades, regime, vix)
        if insight:
            return insight
    return default_insight(trades, regime, vix)
```

### 2.5 Weekly Auto-Summary (Bonus — Saturday 9:00 AM)

Every Saturday at 9:00 AM, a weekly rollup is sent:

```
━━━━━━━━━━━━━━━━━━━━━━
📊 SIGNALPILOT — WEEKLY REPORT
📅 Week of Feb 17-21, 2026
━━━━━━━━━━━━━━━━━━━━━━

💰 WEEKLY P&L: +₹3,450 (+6.9%)
📈 Win Rate: 16/22 (72.7%)
📅 Trading Days: 5 | Best Day: Tuesday (+₹1,845)

━━━ STRATEGY LEADERBOARD ━━━

🥇 Gap & Go:       8/10 (80%) | +₹2,100
🥈 VWAP Reversal:  5/7 (71%)  | +₹980
🥉 ORB:            3/5 (60%)  | +₹370

━━━ PERFORMANCE TRENDS ━━━

📈 Equity Curve: ₹50,000 → ₹53,450
📊 Best Time Slot: 9:30-10:00 AM (5/6 wins)
📊 Worst Time Slot: 1:00-2:00 PM (1/4 wins)
🔥 Confirmed Signal Win Rate: 6/7 (86%)
📋 Most Traded Sector: Banking (8 trades)
📋 Best Sector: Auto (4/4 wins)

━━━ REGIME ANALYSIS ━━━

📊 Trending Days (3): Win rate 12/15 (80%)
📊 Ranging Days (1):  Win rate 3/5 (60%)
📊 Volatile Days (1): Win rate 1/2 (50%)

💡 WEEKLY INSIGHT:
"Your system thrives on trending days (80% WR). This
week had 3 trending days which boosted results. Check
if next week's VIX forecast suggests more volatility —
if so, shift capital toward VWAP Reversal."

━━━ NEXT WEEK PREP ━━━

📅 Earnings this week: RELIANCE (Wed), HDFCBANK (Thu)
⚠️ These stocks will be NEWS-FILTERED (auto-suppressed)
📊 Expiry week: Yes (Feb monthly) — expect higher VIX
━━━━━━━━━━━━━━━━━━━━━━
```

### 2.6 Technical Implementation

**Scheduler:** APScheduler (already in Python ecosystem)

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")

# Daily summary at 3:35 PM IST on weekdays
scheduler.add_job(
    send_daily_summary,
    trigger="cron",
    day_of_week="mon-fri",
    hour=15, minute=35,
    id="daily_summary"
)

# Weekly summary at 9:00 AM IST on Saturdays
scheduler.add_job(
    send_weekly_summary,
    trigger="cron",
    day_of_week="sat",
    hour=9, minute=0,
    id="weekly_summary"
)

scheduler.start()
```

**Data Aggregation Queries:**

```sql
-- Daily P&L
SELECT
    SUM(CASE WHEN outcome = 'WIN' THEN profit_amount ELSE -loss_amount END) as daily_pnl,
    COUNT(*) as total_trades,
    SUM(CASE WHEN outcome = 'WIN' THEN 1 ELSE 0 END) as wins,
    SUM(CASE WHEN outcome = 'LOSS' THEN 1 ELSE 0 END) as losses,
    strategy,
    MAX(profit_amount) as best_trade_pnl,
    MIN(-loss_amount) as worst_trade_pnl
FROM signals
WHERE DATE(created_at) = DATE('now')
  AND user_action = 'TAKEN'
GROUP BY strategy;

-- Skip analysis
SELECT
    skip_reason,
    COUNT(*) as count,
    SUM(CASE WHEN outcome = 'WIN' THEN 1 ELSE 0 END) as would_have_won
FROM signals s
JOIN signal_actions sa ON s.id = sa.signal_id
WHERE DATE(s.created_at) = DATE('now')
  AND sa.user_action = 'SKIP'
GROUP BY skip_reason;
```

### 2.7 Database Schema Changes

**New table: `daily_summaries`**

```sql
CREATE TABLE daily_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    summary_date DATE NOT NULL UNIQUE,
    total_signals INTEGER DEFAULT 0,
    signals_taken INTEGER DEFAULT 0,
    signals_skipped INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    daily_pnl REAL DEFAULT 0.0,
    daily_pnl_percent REAL DEFAULT 0.0,
    best_trade_stock TEXT,
    best_trade_pnl REAL,
    best_trade_strategy TEXT,
    worst_trade_stock TEXT,
    worst_trade_pnl REAL,
    worst_trade_strategy TEXT,
    market_regime TEXT,                  -- 'TRENDING', 'RANGING', 'VOLATILE'
    india_vix REAL,
    nifty_change_percent REAL,
    circuit_breaker_triggered BOOLEAN DEFAULT 0,
    insight_text TEXT,
    confirmed_signals_count INTEGER DEFAULT 0,
    confirmed_win_rate REAL,
    gap_go_wins INTEGER DEFAULT 0,
    gap_go_total INTEGER DEFAULT 0,
    orb_wins INTEGER DEFAULT 0,
    orb_total INTEGER DEFAULT 0,
    vwap_wins INTEGER DEFAULT 0,
    vwap_total INTEGER DEFAULT 0,
    running_week_pnl REAL DEFAULT 0.0,
    running_month_pnl REAL DEFAULT 0.0,
    running_capital REAL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**New table: `weekly_summaries`**

```sql
CREATE TABLE weekly_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start_date DATE NOT NULL,
    week_end_date DATE NOT NULL,
    trading_days INTEGER,
    total_trades INTEGER,
    wins INTEGER,
    losses INTEGER,
    weekly_pnl REAL,
    weekly_pnl_percent REAL,
    best_day_date DATE,
    best_day_pnl REAL,
    worst_day_date DATE,
    worst_day_pnl REAL,
    best_strategy TEXT,
    best_strategy_win_rate REAL,
    best_time_slot TEXT,
    worst_time_slot TEXT,
    best_sector TEXT,
    trending_days INTEGER,
    ranging_days INTEGER,
    volatile_days INTEGER,
    trending_win_rate REAL,
    ranging_win_rate REAL,
    volatile_win_rate REAL,
    insight_text TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 2.8 Dashboard Integration

Add two new pages to the React dashboard:

**Page 7: Daily Reports**
- Calendar view with green/red/grey dots for each trading day
- Click any day to see the full daily summary
- P&L heatmap by day of week and time slot
- Streak tracker (current win/loss streak)

**Page 8: Weekly Reports**
- Weekly performance cards (scrollable timeline)
- Strategy leaderboard chart (stacked bar: wins/losses by strategy per week)
- Regime correlation chart (scatter: regime type vs. win rate)

**API Endpoints (add to FastAPI):**

```
GET /api/v1/summary/daily/{date}     → Daily summary for a specific date
GET /api/v1/summary/daily/latest     → Most recent daily summary
GET /api/v1/summary/weekly/{date}    → Weekly summary containing that date
GET /api/v1/summary/weekly/latest    → Most recent weekly summary
GET /api/v1/summary/monthly/{month}  → Aggregated monthly summary
GET /api/v1/summary/calendar         → Calendar data (date, pnl, regime) for heatmap
```

### 2.9 Success Metrics

| Metric | Target |
|--------|--------|
| Daily summary delivery rate | 100% of trading days (0 missed) |
| User opens/reads summary | > 90% (track Telegram message read receipts) |
| Weekly summary engagement | User sends at least 1 command after reading weekly report > 60% of weeks |
| Insight accuracy | Manual review: insights make sense for > 80% of days |
| Dashboard daily report views | > 3 views per week per user |

---

## 3. Feature 2: News Sentiment Filter

### 3.1 Problem Statement

SignalPilot's strategies are purely technical — they analyze price, volume, and VWAP patterns. They are **blind to fundamental/news events**. This creates dangerous scenarios:

| Scenario | What Happens | Result |
|----------|-------------|--------|
| Stock gaps up 5% on fraud allegation (short covering) | Gap & Go triggers BUY signal | User buys, stock crashes -15% |
| Company announces terrible earnings after hours | ORB breakout triggers next morning | User buys the dead cat bounce, loses |
| SEBI investigation announced | VWAP shows "reversal" pattern | User buys, stock gets circuit locked down |
| Positive news but overreaction | Gap too large (8%+) | User buys at top, stock mean-reverts |

**Real examples from NSE:**
- ADANI stocks in Jan 2023 — massive gaps with extreme news. Technical signals were useless.
- YES BANK — multiple "reversal" signals before it went to ₹5.
- PAYTM — post-listing, multiple "ORB breakouts" that were traps.

### 3.2 Solution: Pre-Signal News Sentiment Check

Before any signal is sent to the user, the system checks recent news for that stock. If negative sentiment is detected, the signal is either **suppressed** or **downgraded**.

**Flow:**

```
Technical signal generated for STOCK_X
       ↓
Check news for STOCK_X (last 24 hours)
       ↓
  ┌────────────────────────────────┐
  │   No news found                │ → Send signal normally
  │   Positive/Neutral sentiment   │ → Send signal normally (+ add "📰 No negative news")
  │   Mild negative sentiment      │ → Downgrade by 1 star + add warning flag
  │   Strong negative sentiment    │ → SUPPRESS signal (do not send) + log reason
  │   Earnings day detected        │ → SUPPRESS signal + log "EARNINGS_BLACKOUT"
  └────────────────────────────────┘
```

### 3.3 News Data Sources

**Tier 1 — RSS Feeds (free, real-time):**

| Source | RSS URL | Coverage |
|--------|---------|----------|
| MoneyControl | `https://www.moneycontrol.com/rss/latestnews.xml` | Broad market news |
| Economic Times Markets | `https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms` | Market-specific |
| LiveMint | `https://www.livemint.com/rss/markets` | Financial markets |
| Business Standard | `https://www.business-standard.com/rss/markets-106.rss` | Markets section |
| NDTV Profit | `https://www.ndtvprofit.com/rss/stock-market` | Stock-specific news |

**Tier 2 — Stock-Specific (API-based):**

| Source | Method | Coverage |
|--------|--------|----------|
| Google News | `feedparser` + query `"{STOCK_NAME}" NSE` | Stock-specific headlines |
| NSE Announcements | NSE corporate announcements API | Official filings (results, board meetings) |
| BSE Corporate Filings | BSE API | Official filings |

**Tier 3 — Earnings Calendar:**

| Source | Method |
|--------|--------|
| Screener.in | Scrape upcoming results calendar |
| TradingView | Earnings calendar API |
| Hard-coded | Maintain a local CSV of Nifty 500 earnings dates, updated monthly |

### 3.4 Sentiment Analysis Architecture

**Model:** FinBERT (pre-trained financial sentiment model)

```
Input: News headline + snippet (max 512 tokens)
Output: {positive: 0.XX, negative: 0.XX, neutral: 0.XX}
```

**Why FinBERT:**
- Pre-trained on financial text (not generic BERT)
- Understands financial context ("stock fell 5%" = negative, "profit fell 5%" = negative)
- Available on HuggingFace, runs locally, no API costs
- Fast inference (~50ms per headline on CPU)

**Alternative (lighter):** VADER Sentiment with financial lexicon boost
- Add domain terms: "SEBI probe" = -0.9, "record revenue" = +0.8, "fraud" = -1.0
- Much faster but less accurate
- Good fallback if FinBERT is too heavy for the system

### 3.5 Sentiment Scoring Logic

**Per-stock sentiment score calculation:**

```python
def calculate_stock_sentiment(stock_code: str, stock_name: str) -> dict:
    # 1. Fetch news from last 24 hours
    headlines = fetch_news_headlines(stock_code, stock_name, hours=24)

    if not headlines:
        return {"score": 0.0, "label": "NO_NEWS", "headlines": []}

    # 2. Run FinBERT on each headline
    sentiments = []
    for headline in headlines:
        result = finbert_predict(headline.text)
        sentiments.append({
            "headline": headline.text,
            "source": headline.source,
            "positive": result["positive"],
            "negative": result["negative"],
            "neutral": result["neutral"],
            "timestamp": headline.published
        })

    # 3. Calculate weighted average (newer = higher weight)
    weights = [recency_weight(s["timestamp"]) for s in sentiments]
    avg_positive = weighted_avg([s["positive"] for s in sentiments], weights)
    avg_negative = weighted_avg([s["negative"] for s in sentiments], weights)

    # 4. Final composite score: -1.0 (very negative) to +1.0 (very positive)
    composite = avg_positive - avg_negative

    # 5. Classify
    if composite < -0.6:
        label = "STRONG_NEGATIVE"
    elif composite < -0.3:
        label = "MILD_NEGATIVE"
    elif composite > 0.3:
        label = "POSITIVE"
    else:
        label = "NEUTRAL"

    return {
        "score": composite,
        "label": label,
        "headline_count": len(sentiments),
        "top_negative": get_most_negative(sentiments),
        "top_positive": get_most_positive(sentiments),
        "headlines": sentiments
    }
```

**Recency weighting:**

```python
def recency_weight(published_time: datetime) -> float:
    hours_ago = (datetime.now() - published_time).total_seconds() / 3600
    if hours_ago < 2:
        return 1.0      # Last 2 hours: full weight
    elif hours_ago < 6:
        return 0.7       # 2-6 hours: 70% weight
    elif hours_ago < 12:
        return 0.4       # 6-12 hours: 40% weight
    else:
        return 0.2       # 12-24 hours: 20% weight
```

### 3.6 Signal Modification Rules

| Sentiment Label | Score Range | Action | Signal Modification |
|----------------|-------------|--------|-------------------|
| NO_NEWS | N/A | Pass through | Add "📰 No recent news" |
| POSITIVE | > +0.3 | Pass through | Add "📰 Positive news sentiment" |
| NEUTRAL | -0.3 to +0.3 | Pass through | No modification |
| MILD_NEGATIVE | -0.6 to -0.3 | Downgrade | Star rating -1, add "⚠️ Negative news detected: {headline}" |
| STRONG_NEGATIVE | < -0.6 | Suppress | Signal NOT sent. Logged as "NEWS_SUPPRESSED" |
| EARNINGS_DAY | N/A | Suppress | Signal NOT sent. Logged as "EARNINGS_BLACKOUT" |

**Suppressed Signal Notification (sent as info, not as signal):**

```
🚫 SIGNAL SUPPRESSED — TATAMOTORS

A Gap & Go signal was detected but SUPPRESSED due to:
⚠️ Strong negative news sentiment (-0.72)

📰 Headlines:
• "Tata Motors faces SEBI probe over financial disclosures"
  — MoneyControl, 2 hours ago
• "Tata Motors Q3 results miss estimates by wide margin"
  — Economic Times, 6 hours ago

📋 Signal details (for reference only):
   Entry: ₹645 | SL: ₹631 | Target: ₹661

💡 This stock will be excluded from scanning for 24 hours.
   Use NEWS TATAMOTORS to check latest sentiment.
━━━━━━━━━━━━━━━━━━━━━━
```

**Downgraded Signal Example:**

```
📊 SIGNAL — GAP & GO — HDFCBANK

⚠️ NEWS WARNING: Mild negative sentiment (-0.35)
📰 "HDFC Bank faces RBI scrutiny on credit card practices"
   — LiveMint, 4 hours ago

📍 Entry: ₹1,785.00
🛑 SL: ₹1,752.87 (1.80%)
🎯 T1: ₹1,803.38 (1.0%)
🎯 T2: ₹1,812.75 (1.55%)
📊 Qty: 8 shares
💰 Capital: ₹14,280
⭐ Strength: ★★★☆☆ (Downgraded from ★★★★ due to news)

⏰ Valid for: 30 mins | Positions: 2/8
━━━━━━━━━━━━━━━━━━━━━━
```

### 3.7 New Telegram Commands

| Command | Action |
|---------|--------|
| `NEWS TATAMOTORS` | Show latest sentiment analysis for a stock |
| `NEWS ALL` | Show sentiment summary for all stocks currently on scan list |
| `EARNINGS` | Show upcoming earnings calendar for Nifty 500 (next 7 days) |
| `UNSUPPRESS TATAMOTORS` | Override news suppression for a stock (expert mode) |

### 3.8 Caching & Performance

**News fetch frequency:**
- Pre-market scan (8:30 AM): Fetch news for ALL Nifty 500 stocks
- Cache results in SQLite for 2 hours
- Re-fetch only for stocks that generate a technical signal (on-demand)
- Background refresh every 2 hours during market hours

**FinBERT model loading:**
- Load once at startup, keep in memory
- Model size: ~420MB (FinBERT-base)
- Inference: ~50ms per headline on CPU
- Batch processing: 10 headlines for a stock = ~500ms total

**Fallback if FinBERT is too heavy:**
- Use VADER + custom financial lexicon
- Model size: <1MB
- Inference: <5ms per headline
- Lower accuracy but adequate for headline-level sentiment

### 3.9 Database Schema Changes

**New table: `news_sentiment`**

```sql
CREATE TABLE news_sentiment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code TEXT NOT NULL,
    headline TEXT NOT NULL,
    source TEXT NOT NULL,
    published_at DATETIME NOT NULL,
    positive_score REAL,
    negative_score REAL,
    neutral_score REAL,
    composite_score REAL,
    sentiment_label TEXT,            -- 'POSITIVE', 'NEUTRAL', 'MILD_NEGATIVE', 'STRONG_NEGATIVE'
    fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    model_used TEXT DEFAULT 'finbert' -- 'finbert' or 'vader'
);

CREATE INDEX idx_news_stock_date ON news_sentiment(stock_code, published_at);
```

**New table: `earnings_calendar`**

```sql
CREATE TABLE earnings_calendar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code TEXT NOT NULL,
    earnings_date DATE NOT NULL,
    quarter TEXT,                    -- 'Q3FY26'
    source TEXT,                     -- 'screener.in', 'manual'
    is_confirmed BOOLEAN DEFAULT 0,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_earnings_date ON earnings_calendar(earnings_date);
```

**Modified table: `signals` — add columns:**

```sql
ALTER TABLE signals ADD COLUMN news_sentiment_score REAL;
ALTER TABLE signals ADD COLUMN news_sentiment_label TEXT;
ALTER TABLE signals ADD COLUMN news_top_headline TEXT;
ALTER TABLE signals ADD COLUMN news_action TEXT;           -- 'PASS', 'DOWNGRADED', 'SUPPRESSED', 'EARNINGS_BLACKOUT'
ALTER TABLE signals ADD COLUMN original_star_rating INTEGER; -- star rating before news downgrade
```

### 3.10 Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Catastrophic trade prevention | 0 trades taken on stocks with SEBI probes, fraud news, or earnings misses | Manual review of suppressed signals |
| Suppressed signal accuracy | > 70% of suppressed signals would have been losers | Track suppressed signal outcomes |
| False suppression rate | < 15% of suppressed signals would have been winners | Same as above — want this low |
| News fetch latency | < 3 seconds for single-stock sentiment check | Monitor fetch + inference time |
| Downgraded signal performance | Downgraded signals have lower win rate than normal signals | Compare win rates |
| Earnings blackout compliance | 100% of stocks with same-day earnings are blocked | Cross-check calendar vs. signals |

---

## 4. Feature 3: Market Regime Detection

### 4.1 Problem Statement

SignalPilot treats every trading day the same — all 3 strategies run at equal weight regardless of market conditions. But market conditions dramatically affect strategy performance:

| Market Regime | Best Strategy | Worst Strategy | Why |
|--------------|---------------|----------------|-----|
| **Trending** (Nifty +1% to +3%) | Gap & Go, ORB | VWAP Reversal | Strong momentum favors breakouts; reversals are fake |
| **Ranging** (Nifty -0.3% to +0.3%) | VWAP Reversal | Gap & Go | No directional momentum; mean-reversion works |
| **Volatile** (Nifty swings >2% intraday) | None (defensive) | All strategies | Wide whipsaws trigger false breakouts AND false reversals |
| **Gap Day** (Nifty gaps >1%) | Gap & Go | ORB (delayed entry misses) | Gaps create immediate opportunities; waiting for ORB wastes time |
| **Low VIX** (<14) | ORB | Gap & Go | Tight ranges; breakouts are clean with less noise |
| **High VIX** (>20) | Reduce all | Gap & Go especially | Wide stops needed; position sizes shrink; false signals increase |

Without regime detection, ~30% of trading days produce signals in the wrong strategy, leading to avoidable losses.

### 4.2 Solution: Morning Classification + Dynamic Strategy Weighting

At **9:30 AM IST** (15 minutes after market open), classify the day's market regime and adjust strategy weights.

**Classification Inputs (collected 9:15-9:30 AM):**

| Input | Source | Update Frequency |
|-------|--------|-----------------|
| India VIX | NSE VIX index (via SmartAPI/nsetools) | Real-time |
| Nifty 50 opening gap % | (Today's open - Yesterday's close) / Yesterday's close | Once at 9:15 AM |
| Nifty 50 first-15-min range | High - Low of 9:15-9:30 candle | Once at 9:30 AM |
| Nifty 50 first-15-min direction | Close vs Open of first candle | Once at 9:30 AM |
| Previous day's Nifty range | Yesterday's (High - Low) / Close × 100 | Once at startup |
| FII/DII net flow (previous day) | NSE FII/DII data | Once at 8:30 AM |
| SGX Nifty direction | SGX Nifty pre-market trend | Once at 8:45 AM |
| Global cues | US market (S&P 500 % change), Asian market direction | Once at 8:45 AM |

### 4.3 Regime Classification Algorithm

**Step 1: Calculate Regime Score**

```python
def classify_regime(
    vix: float,
    nifty_gap_pct: float,
    first_15_range_pct: float,
    first_15_direction: str,     # 'UP', 'DOWN', 'FLAT'
    prev_day_range_pct: float,
    fii_dii_net: float,          # crores
    sgx_direction: str,          # 'UP', 'DOWN', 'FLAT'
    sp500_change_pct: float
) -> dict:

    # Component scores (-1.0 to +1.0)

    # VIX Score: Low VIX = calm, High VIX = volatile
    if vix < 12:
        vix_score = -0.5     # Very calm (ranging likely)
    elif vix < 14:
        vix_score = 0.0       # Normal
    elif vix < 18:
        vix_score = 0.3       # Slightly elevated
    elif vix < 22:
        vix_score = 0.6       # High (volatile likely)
    else:
        vix_score = 1.0       # Very high (defensive mode)

    # Gap Score: Large gap = trending, no gap = ranging
    gap_abs = abs(nifty_gap_pct)
    if gap_abs > 1.5:
        gap_score = 1.0       # Big gap — trending day
    elif gap_abs > 0.8:
        gap_score = 0.6       # Moderate gap
    elif gap_abs > 0.3:
        gap_score = 0.2       # Small gap
    else:
        gap_score = -0.5      # No gap — ranging likely

    # First-15-min range score
    if first_15_range_pct > 1.0:
        range_score = 1.0     # Wide range — volatile
    elif first_15_range_pct > 0.5:
        range_score = 0.5     # Moderate range — trending
    elif first_15_range_pct > 0.2:
        range_score = 0.0     # Normal
    else:
        range_score = -0.5    # Tight range — ranging

    # Directional alignment score
    # If gap, first-15-min, SGX, S&P500 all same direction → strong trend
    directions = [
        1 if nifty_gap_pct > 0.3 else (-1 if nifty_gap_pct < -0.3 else 0),
        1 if first_15_direction == 'UP' else (-1 if first_15_direction == 'DOWN' else 0),
        1 if sgx_direction == 'UP' else (-1 if sgx_direction == 'DOWN' else 0),
        1 if sp500_change_pct > 0.3 else (-1 if sp500_change_pct < -0.3 else 0),
    ]
    alignment = abs(sum(directions)) / len(directions)
    # alignment = 1.0 means all agree, 0.0 means mixed

    # Composite regime score
    # Trending = high gap + high alignment + moderate VIX
    # Ranging = low gap + low range + low VIX
    # Volatile = high VIX + wide range + low alignment

    trending_score = (gap_score * 0.35) + (alignment * 0.30) + (range_score * 0.20) + ((1 - vix_score) * 0.15)
    ranging_score = ((-gap_score) * 0.35) + ((-range_score) * 0.30) + ((1 - vix_score) * 0.35)
    volatile_score = (vix_score * 0.40) + (range_score * 0.30) + ((1 - alignment) * 0.30)

    # Winner takes all
    scores = {
        "TRENDING": trending_score,
        "RANGING": ranging_score,
        "VOLATILE": volatile_score
    }
    regime = max(scores, key=scores.get)
    confidence = scores[regime] / sum(abs(v) for v in scores.values()) if sum(abs(v) for v in scores.values()) > 0 else 0.33

    return {
        "regime": regime,
        "confidence": round(confidence, 2),
        "scores": {k: round(v, 3) for k, v in scores.items()},
        "inputs": {
            "vix": vix,
            "gap_pct": nifty_gap_pct,
            "first_15_range_pct": first_15_range_pct,
            "alignment": alignment
        }
    }
```

### 4.4 Dynamic Strategy Weight Adjustment

Based on regime, modify the capital allocation and signal thresholds:

**Weight Adjustment Matrix:**

| | Gap & Go | ORB | VWAP Reversal | Min Star Rating |
|---|----------|-----|---------------|-----------------|
| **TRENDING (high confidence)** | 45% (+12%) | 35% (+2%) | 20% (-14%) | 3★ (aggressive) |
| **TRENDING (low confidence)** | 38% (+5%) | 35% (+2%) | 27% (-7%) | 3★ |
| **RANGING (high confidence)** | 20% (-13%) | 30% (-3%) | 50% (+16%) | 3★ |
| **RANGING (low confidence)** | 28% (-5%) | 33% (±0%) | 39% (+5%) | 4★ (selective) |
| **VOLATILE (high confidence)** | 25% (-8%) | 25% (-8%) | 25% (-9%) | 5★ only (defensive) |
| **VOLATILE (low confidence)** | 30% (-3%) | 30% (-3%) | 30% (-4%) | 4★ |
| **DEFAULT (equal)** | 33% | 33% | 34% | 3★ |

*Percentages show baseline ± adjustment. Default baseline from Phase 2: Gap & Go 33%, ORB 33%, VWAP 34%*

**Confidence Threshold:** > 0.55 = high confidence, ≤ 0.55 = low confidence

### 4.5 Position Size Adjustment by Regime

Beyond capital allocation, adjust per-trade position sizing:

| Regime | Position Size Modifier | Max Positions | Rationale |
|--------|----------------------|---------------|-----------|
| TRENDING | 1.0× (normal) | 8 | Standard — momentum supports trades |
| RANGING | 0.85× (slightly reduced) | 6 | Tighter ranges = less room for profit |
| VOLATILE | 0.65× (significantly reduced) | 4 | Wide swings = bigger SL = less capital per trade |

### 4.6 Intraday Regime Re-Classification

The initial 9:30 AM classification may change as the day develops. Re-classify at key checkpoints:

| Time | Trigger | What Changes |
|------|---------|-------------|
| 9:30 AM | Initial classification | Set strategy weights for the day |
| 11:00 AM | Mid-morning check | If VIX has spiked >15% from morning, re-classify |
| 1:00 PM | Afternoon check | If Nifty has reversed direction from morning, re-classify |
| 2:30 PM | Late session | If Nifty is within 0.3% of open (round-trip), switch to RANGING |

**Re-classification rules:**
- Only upgrade severity (TRENDING → VOLATILE), never downgrade (VOLATILE → TRENDING)
- Maximum 2 re-classifications per day to avoid flip-flopping
- Each re-classification is logged and sent as a Telegram notification

**Re-classification Notification:**

```
🌡️ REGIME UPDATE — 11:15 AM

Previous: TRENDING (confidence: 0.72)
Updated:  VOLATILE (confidence: 0.65)

📊 India VIX jumped from 14.2 → 18.8 (+32%) in last hour
📉 Nifty reversed from +0.8% to -0.3%

⚡ Strategy adjustments applied:
   Gap & Go: 45% → 25% (paused for new signals)
   ORB: 35% → 25%
   VWAP Reversal: 20% → 25%
   Min rating: 3★ → 5★ only
   Max positions: 8 → 4

⚠️ Existing positions are NOT affected.
   Only new signals are filtered by updated rules.
━━━━━━━━━━━━━━━━━━━━━━
```

### 4.7 Pre-Market Intelligence Brief (Bonus)

Every day at **8:45 AM IST**, send a brief context message:

```
━━━━━━━━━━━━━━━━━━━━━━
🌅 SIGNALPILOT — MORNING BRIEF
📅 Tuesday, February 25, 2026
━━━━━━━━━━━━━━━━━━━━━━

🌍 GLOBAL CUES
   🇺🇸 S&P 500: +0.85% | Nasdaq: +1.2%
   🇯🇵 Nikkei: +0.4% | 🇭🇰 Hang Seng: -0.2%
   📊 SGX Nifty: +0.6% (indicating gap-up open)

🇮🇳 INDIA CONTEXT
   📊 India VIX: 14.2 (Low — calm market expected)
   💰 FII (yesterday): -₹1,200 Cr (net sell)
   💰 DII (yesterday): +₹1,800 Cr (net buy)
   📅 No major earnings today

🔮 REGIME PREDICTION: Likely TRENDING DAY
   Reasoning: Positive global cues + SGX gap-up + low VIX
   → Gap & Go and ORB likely to perform well
   → Watch for confirmation at 9:30 AM

⚠️ WATCHLIST ALERTS
   📌 TATAMOTORS (watched since Feb 22) — No signal yet
   📌 RELIANCE (watched since Feb 23) — Approaching ORB zone

━━━━━━━━━━━━━━━━━━━━━━
Classification at 9:30 AM. First signals expected 9:30-9:45 AM.
```

### 4.8 New Telegram Commands

| Command | Action |
|---------|--------|
| `REGIME` | Show current market regime classification with all inputs |
| `REGIME HISTORY` | Show last 20 trading days' regimes with strategy performance per regime |
| `REGIME OVERRIDE TRENDING` | Manually override regime (expert mode) — resets at next checkpoint |
| `VIX` | Show current India VIX and interpretation |
| `MORNING` | Re-send today's morning brief |

### 4.9 Database Schema Changes

**New table: `market_regimes`**

```sql
CREATE TABLE market_regimes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    regime_date DATE NOT NULL,
    classification_time TIME NOT NULL,      -- '09:30:00', '11:00:00', etc.
    regime TEXT NOT NULL,                    -- 'TRENDING', 'RANGING', 'VOLATILE'
    confidence REAL NOT NULL,
    trending_score REAL,
    ranging_score REAL,
    volatile_score REAL,
    india_vix REAL,
    nifty_gap_pct REAL,
    nifty_first_15_range_pct REAL,
    nifty_first_15_direction TEXT,
    directional_alignment REAL,
    sp500_change_pct REAL,
    sgx_direction TEXT,
    fii_net_crores REAL,
    dii_net_crores REAL,
    is_reclassification BOOLEAN DEFAULT 0,
    previous_regime TEXT,                   -- if reclassified, what was it before
    strategy_weights_json TEXT,             -- {"gap_go": 0.45, "orb": 0.35, "vwap": 0.20}
    min_star_rating INTEGER,
    max_positions INTEGER,
    position_size_modifier REAL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_regime_date ON market_regimes(regime_date);
```

**New table: `regime_performance`** (populated daily by EOD summary)

```sql
CREATE TABLE regime_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    regime_date DATE NOT NULL,
    regime TEXT NOT NULL,
    strategy TEXT NOT NULL,                -- 'GAP_GO', 'ORB', 'VWAP_REVERSAL'
    signals_generated INTEGER DEFAULT 0,
    signals_taken INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    pnl REAL DEFAULT 0.0,
    win_rate REAL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_regime_perf ON regime_performance(regime, strategy);
```

### 4.10 Dashboard Integration

**Page 9: Market Regime**
- Current regime display (large badge: TRENDING / RANGING / VOLATILE)
- Live inputs dashboard (VIX, gap, alignment, scores)
- Strategy weight visualization (pie chart adjusting in real-time)
- Historical regime calendar (color-coded: green=trending, yellow=ranging, red=volatile)
- Regime vs. performance correlation chart (bar chart: win rate by regime by strategy)

**API Endpoints:**

```
GET /api/v1/regime/current              → Current regime + all inputs
GET /api/v1/regime/history?days=30      → Last 30 days of regimes
GET /api/v1/regime/performance          → Win rate by regime by strategy
POST /api/v1/regime/override            → Manual override (expert mode)
GET /api/v1/morning-brief               → Today's morning brief data
```

### 4.11 Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Regime classification accuracy | > 70% alignment with end-of-day actual behavior | Compare morning prediction vs actual Nifty behavior |
| Win rate improvement in trending regime | Gap & Go win rate > 70% on trending days (vs ~60% baseline) | regime_performance table |
| Loss prevention in volatile regime | < 2 signals sent on volatile days (vs ~6 on normal days) | Signal count by regime |
| Capital saved on volatile days | 30%+ less capital deployed on volatile days | Position sizes × count |
| Re-classification accuracy | > 60% of re-classifications correctly identify deterioration | Compare re-class trigger vs. afternoon outcome |
| Strategy weight correlation | Higher-weighted strategies outperform lower-weighted on 70%+ of days | Compare performance by weight |

---

## 5. Development Timeline

### Phase 4: 4-Week Sprint (Weeks 13-16)

| Week | Focus | Deliverables |
|------|-------|-------------|
| **Week 13** | News Sentiment Filter | RSS feed ingestion pipeline, FinBERT model integration (or VADER fallback), stock-specific sentiment scoring, earnings calendar, news_sentiment table |
| **Week 14** | News Sentiment Filter (Integration) | Signal suppression/downgrade logic, suppressed signal notification, NEWS command, EARNINGS command, UNSUPPRESS override, testing with live data |
| **Week 15** | Market Regime Detection | VIX + gap + alignment data collection, regime classification algorithm, dynamic strategy weight adjustment, position size modifier, morning brief, REGIME command |
| **Week 16** | EOD Summary + Integration Testing | Daily summary engine, weekly summary engine, insight generation rules, daily/weekly_summaries tables, dashboard pages (7-9), full integration testing, go-live |

### Dependencies & Parallel Work

```
Week 13-14: News Sentiment (standalone — needs FinBERT download + RSS setup)
    ↓
Week 15: Market Regime (standalone — needs VIX data source)
    ↓
Week 16: EOD Summary (depends on ALL above — aggregates data from all features)
```

### Risk Mitigation

| Risk | Mitigation |
|------|------------|
| FinBERT too heavy for laptop | Fallback: VADER + financial lexicon (pre-built, Week 13 Day 1) |
| RSS feeds are unreliable/blocked | Fallback: Google News scraping via feedparser |
| VIX data not available via SmartAPI | Fallback: Scrape NSE India VIX page / use nsetools library |
| Regime classification is inaccurate initially | Start in "shadow mode" — classify but don't adjust weights for first 2 weeks. Compare predictions to actual outcomes. |

---

## 6. Combined Database Schema Summary (All Phase 4 Tables)

### New Tables (6)

| Table | Purpose | Feature |
|-------|---------|---------|
| `daily_summaries` | Pre-computed daily report data | EOD Summary |
| `weekly_summaries` | Pre-computed weekly report data | EOD Summary |
| `news_sentiment` | Cached news headlines with sentiment scores | News Filter |
| `earnings_calendar` | Upcoming earnings dates for Nifty 500 | News Filter |
| `market_regimes` | Daily regime classifications with inputs | Regime Detection |
| `regime_performance` | Strategy performance broken down by regime | Regime Detection |

### Modified Tables

| Table | New Columns | Feature |
|-------|------------|---------|
| `signals` | `news_sentiment_score`, `news_sentiment_label`, `news_top_headline`, `news_action`, `original_star_rating` | News Filter |
| `signals` | `market_regime`, `regime_confidence`, `regime_weight_modifier` | Regime Detection |

---

## 7. New API Endpoints (FastAPI)

| Endpoint | Method | Feature |
|----------|--------|---------|
| `/api/v1/summary/daily/{date}` | GET | EOD Summary |
| `/api/v1/summary/daily/latest` | GET | EOD Summary |
| `/api/v1/summary/weekly/{date}` | GET | EOD Summary |
| `/api/v1/summary/weekly/latest` | GET | EOD Summary |
| `/api/v1/summary/monthly/{month}` | GET | EOD Summary |
| `/api/v1/summary/calendar` | GET | EOD Summary |
| `/api/v1/news/{stock_code}` | GET | News Filter |
| `/api/v1/news/suppressed` | GET | News Filter |
| `/api/v1/earnings/upcoming` | GET | News Filter |
| `/api/v1/regime/current` | GET | Regime Detection |
| `/api/v1/regime/history` | GET | Regime Detection |
| `/api/v1/regime/performance` | GET | Regime Detection |
| `/api/v1/regime/override` | POST | Regime Detection |
| `/api/v1/morning-brief` | GET | Regime Detection |

---

## 8. New Telegram Commands Summary

| Command | Feature | Description |
|---------|---------|-------------|
| `NEWS {STOCK}` | News Filter | Show sentiment analysis for a stock |
| `NEWS ALL` | News Filter | Sentiment for all scan-list stocks |
| `EARNINGS` | News Filter | Upcoming earnings calendar (7 days) |
| `UNSUPPRESS {STOCK}` | News Filter | Override news suppression |
| `REGIME` | Regime Detection | Current market regime + inputs |
| `REGIME HISTORY` | Regime Detection | Last 20 days' regimes + performance |
| `REGIME OVERRIDE {TYPE}` | Regime Detection | Manual regime override |
| `VIX` | Regime Detection | Current India VIX + interpretation |
| `MORNING` | Regime Detection | Re-send today's morning brief |

---

## 9. Overall Phase 4 Success Metrics

| Category | Metric | Target |
|----------|--------|--------|
| **Risk** | Catastrophic trades prevented (news-related) | 0 per month |
| **Risk** | Signals suppressed that would have lost | > 70% accuracy |
| **Alpha** | Win rate on trending days | > 70% (vs ~60% baseline) |
| **Alpha** | Losses on volatile days | < 50% of normal-day losses |
| **Analytics** | Daily summary delivery | 100% of trading days |
| **Analytics** | Weekly insight actionability | > 80% insights rated useful |
| **Overall** | System win rate improvement | +5% absolute (e.g., 60% → 65%) |
| **Overall** | Monthly drawdown reduction | -30% compared to Phase 3 baseline |

---

## 10. What's Next — Phase 5 Preview

*Phase 5 scope is not yet defined. It will be planned after Phase 4 is live, validated, and producing measurable results.*

*Potential directions to evaluate based on Phase 4 outcomes:*
- TBD

---

*Document Version: 4.0 — February 25, 2026*
*Total estimated development: 4 weeks (Weeks 13-16)*
*Prerequisites: Phase 3 (Hybrid Scoring + Dashboard) live and stable*
