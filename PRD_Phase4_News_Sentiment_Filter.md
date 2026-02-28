# Product Requirements Document (PRD)
# SignalPilot — Phase 4: News Sentiment Filter

**Version:** 2.0
**Date:** February 28, 2026
**Author:** Biswajit (Product Owner & Developer)
**Status:** Phase 4 — Development
**Prerequisites:** Phase 1 (Gap & Go), Phase 2 (ORB + VWAP), Phase 3 (Hybrid Scoring + Dashboard), Phase 4 Quick Action Buttons complete and running live
**Parent PRD:** PRD_Phase4_Intelligence_Layer.md

---

## 1. Problem Statement

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

---

## 2. Solution: Pre-Signal News Sentiment Check

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

---

## 3. Codebase Integration: Pipeline Placement

### 3.1 Current Pipeline (12 stages)

The scan loop in `SignalPilotApp._scan_loop()` (`backend/signalpilot/scheduler/lifecycle.py`) creates a fresh `ScanContext` every second and runs it through a `ScanPipeline` (`backend/signalpilot/pipeline/stage.py`). Signal stages run only when `accepting_signals=True` and the phase is OPENING, ENTRY_WINDOW, or CONTINUOUS.

```
 1. CircuitBreakerGateStage     ← halt if SL limit exceeded
 2. StrategyEvalStage           ← run Gap & Go / ORB / VWAP → all_candidates
 3. GapStockMarkingStage        ← exclude gap stocks from ORB/VWAP
 4. DeduplicationStage          ← cross-strategy same-day dedup
 5. ConfidenceStage             ← multi-strategy confirmation → confirmation_map
 6. CompositeScoringStage       ← 4-factor hybrid scoring → composite_scores
 7. AdaptiveFilterStage         ← block paused/underperforming strategies
 8. RankingStage                ← top-N selection, 1-5 stars → ranked_signals
 9. RiskSizingStage             ← position sizing, capital allocation → final_signals
10. PersistAndDeliverStage      ← DB insert + Telegram delivery
11. DiagnosticStage             ← heartbeat logging
    ---
12. ExitMonitoringStage         ← (ALWAYS) SL/target/trailing-SL/time exits
```

### 3.2 New Stage: `NewsSentimentStage` — Between Stages 8 and 9

The News Sentiment Filter inserts as a **single new pipeline stage** between `RankingStage` and `RiskSizingStage`:

```
 8. RankingStage                ← assigns stars (1-5) → ranked_signals
                                   ↓
 NEW: NewsSentimentStage        ← check cached news for each ranked signal
                                   - STRONG_NEGATIVE / EARNINGS_DAY → remove from ranked_signals
                                   - MILD_NEGATIVE → signal_strength -= 1, tag warning
                                   - NO_NEWS / POSITIVE / NEUTRAL → pass through
                                   ↓
 9. RiskSizingStage             ← sizes only surviving signals
```

**Why this position:**

- **After RankingStage (8):** Stars are already assigned, so we can downgrade `signal_strength` for MILD_NEGATIVE. Without stars assigned first, there's nothing to downgrade.
- **Before RiskSizingStage (9):** Suppressed signals are removed from `ranked_signals` before position sizing, so capital isn't wasted on signals that will never be sent.
- **Before PersistAndDeliverStage (10):** Sentiment metadata (`news_sentiment_score`, `news_action`, etc.) is available on the signals for persistence and formatting.

**No existing stages are modified.** The new stage follows the existing `PipelineStage` protocol:

```python
class NewsSentimentStage:
    @property
    def name(self) -> str:
        return "NewsSentiment"

    async def process(self, ctx: ScanContext) -> ScanContext:
        # Only process if there are ranked signals to check
        # Read cached sentiment from news_sentiment_repo (SQLite lookup, <2ms per stock)
        # Suppress / downgrade / pass through based on sentiment label
        # Store results on ctx.sentiment_results and ctx.suppressed_signals
        return ctx
```

### 3.3 ScanContext Changes

Add these **optional fields** to `ScanContext` (`backend/signalpilot/pipeline/context.py`). All default to neutral values — if the stage is absent, every other stage behaves identically to today:

```python
# Set by NewsSentimentStage
sentiment_results: dict[str, SentimentResult] = field(default_factory=dict)
    # Per-symbol sentiment lookup: {symbol: SentimentResult(score, label, headline)}
suppressed_signals: list[SuppressedSignal] = field(default_factory=list)
    # Signals removed due to STRONG_NEGATIVE or EARNINGS_DAY (for notification)
```

### 3.4 PersistAndDeliverStage Enhancement

The existing `PersistAndDeliverStage` (`backend/signalpilot/pipeline/stages/persist_and_deliver.py`) needs **3 additive lines** to persist sentiment metadata on each `SignalRecord` before DB insert:

```python
# Inside the loop over final_signals, after existing Phase 3 field assignments:
if ctx.sentiment_results and signal.symbol in ctx.sentiment_results:
    sentiment = ctx.sentiment_results[signal.symbol]
    record.news_sentiment_score = sentiment.score
    record.news_sentiment_label = sentiment.label
    record.news_top_headline = sentiment.headline
    record.news_action = sentiment.action       # 'PASS', 'DOWNGRADED'
    record.original_star_rating = original_stars # stored before downgrade
```

After signal delivery, send suppression notifications for removed signals:

```python
for suppressed in ctx.suppressed_signals:
    await self._bot.send_alert(format_suppression_notification(suppressed))
```

### 3.5 Formatter Enhancement

The existing `format_signal_message()` in `backend/signalpilot/telegram/formatters.py` needs **2 optional parameters** added to its signature:

```python
def format_signal_message(
    signal, ...,
    news_sentiment_label: str | None = None,     # NEW
    news_top_headline: str | None = None,         # NEW
) -> str:
```

When `news_sentiment_label == "MILD_NEGATIVE"`, prepend the warning block to the existing message format. When `news_sentiment_label == "POSITIVE"`, append the positive badge. No changes to existing formatting logic.

### 3.6 New Components

| Component | File Path | Responsibility |
|-----------|-----------|----------------|
| `NewsSentimentService` | `backend/signalpilot/intelligence/news_sentiment.py` | FinBERT/VADER inference, scoring logic, caching orchestration |
| `NewsFetcher` | `backend/signalpilot/intelligence/news_fetcher.py` | RSS feed ingestion (feedparser), Google News queries, response parsing |
| `EarningsCalendar` | `backend/signalpilot/intelligence/earnings.py` | Earnings date lookup, blackout detection |
| `NewsSentimentStage` | `backend/signalpilot/pipeline/stages/news_sentiment.py` | Pipeline stage — reads cached sentiment, filters/tags ranked_signals |
| `NewsSentimentRepository` | `backend/signalpilot/db/news_sentiment_repo.py` | Cache headlines + scores in SQLite (`news_sentiment` table) |
| `EarningsCalendarRepository` | `backend/signalpilot/db/earnings_repo.py` | Store/query earnings dates (`earnings_calendar` table) |

All new components are placed under a new `backend/signalpilot/intelligence/` package — keeping the feature isolated from existing code.

### 3.7 Wiring in `create_app()` (`backend/signalpilot/main.py`)

New components are instantiated **after** existing repository and bot setup, **before** pipeline construction:

```python
# After existing repo setup:
news_sentiment_repo = NewsSentimentRepository(connection)
earnings_repo = EarningsCalendarRepository(connection)

# After existing component setup:
news_fetcher = NewsFetcher(config)
news_sentiment_service = NewsSentimentService(
    news_fetcher, news_sentiment_repo, earnings_repo, config
)
```

In `_build_pipeline()`, insert after `RankingStage`:

```python
signal_stages = [
    CircuitBreakerGateStage(self._circuit_breaker),
    StrategyEvalStage(...),
    GapStockMarkingStage(),
    DeduplicationStage(...),
    ConfidenceStage(...),
    CompositeScoringStage(...),
    AdaptiveFilterStage(...),
    RankingStage(...),
    NewsSentimentStage(news_sentiment_service, earnings_repo, bot),  # ← NEW
    RiskSizingStage(...),
    PersistAndDeliverStage(...),
    DiagnosticStage(...),
]
```

### 3.8 Scheduler Jobs

Two new cron jobs added to `MarketScheduler` (`backend/signalpilot/scheduler/scheduler.py`), following the existing pattern of `day_of_week='mon-fri'` + `_trading_day_guard` decorator:

| Time | Job | Action |
|------|-----|--------|
| **8:30 AM** | `fetch_pre_market_news()` | Bulk fetch headlines for all Nifty 500 stocks, run sentiment analysis, cache in `news_sentiment` table |
| **Every 2 hours** (market hours) | `refresh_news_cache()` | Background refresh of cached sentiment for stocks on the active scan list |

These run alongside the existing 9 scheduler jobs without conflict. Pre-market news fetch completes before 9:15 AM market open, so the cache is warm when signals start flowing.

### 3.9 Performance Impact

| Scenario | Per-Cycle Cost | Notes |
|----------|---------------|-------|
| No signals this cycle | **0ms** | Stage checks `ranked_signals` is empty, returns immediately |
| Signals present, cache hit | **~5-10ms** | SQLite indexed lookup per symbol (<2ms each), in-memory filter/tag |
| Signals present, cache miss | **0ms (async)** | Treat as NO_NEWS, queue background re-fetch for next cycle |

**Memory impact:** VADER <1MB, FinBERT ~420MB. VADER recommended for production.

**Startup impact:** VADER <1s, FinBERT +5-10s model load.

**The 1-second scan loop is never blocked.** All network I/O (RSS fetch, FinBERT inference) happens in scheduler jobs or background tasks, never in the pipeline cycle.

### 3.10 What Stays Untouched

- **All 12 existing pipeline stages** — zero logic changes to their core code
- **Existing Telegram commands** (TAKEN, SKIP, WATCH, STATUS, JOURNAL, CAPITAL, etc.) — unchanged
- **Existing DB tables** — only additive column migrations with nullable defaults
- **EventBus** — no new event types needed
- **Exit monitoring** — completely unaffected
- **WebSocket, data engine, strategies** — completely unaffected

---

## 4. News Data Sources

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

---

## 5. Sentiment Analysis Architecture

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

---

## 6. Sentiment Scoring Logic

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
    hours_ago = (datetime.now(IST) - published_time).total_seconds() / 3600
    if hours_ago < 2:
        return 1.0      # Last 2 hours: full weight
    elif hours_ago < 6:
        return 0.7       # 2-6 hours: 70% weight
    elif hours_ago < 12:
        return 0.4       # 6-12 hours: 40% weight
    else:
        return 0.2       # 12-24 hours: 20% weight
```

---

## 7. Signal Modification Rules

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

---

## 8. New Telegram Commands

| Command | Action |
|---------|--------|
| `NEWS TATAMOTORS` | Show latest sentiment analysis for a stock |
| `NEWS ALL` | Show sentiment summary for all stocks currently on scan list |
| `EARNINGS` | Show upcoming earnings calendar for Nifty 500 (next 7 days) |
| `UNSUPPRESS TATAMOTORS` | Override news suppression for a stock (expert mode) |

These commands are registered as `MessageHandler` entries in `SignalPilotBot.start()` (`backend/signalpilot/telegram/bot.py`), following the same pattern as existing commands (TAKEN, STATUS, JOURNAL, CAPITAL, etc.).

---

## 9. Caching & Performance

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

---

## 10. Database Schema Changes

### 10.1 New table: `news_sentiment`

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

### 10.2 New table: `earnings_calendar`

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

### 10.3 Modified table: `signals` — add columns

Added via idempotent migration in `DatabaseManager._run_news_sentiment_migration()` (`backend/signalpilot/db/database.py`), following the existing Phase 2/3/4 migration pattern using `PRAGMA table_info()` to check before `ALTER TABLE ADD COLUMN`:

```sql
ALTER TABLE signals ADD COLUMN news_sentiment_score REAL;
ALTER TABLE signals ADD COLUMN news_sentiment_label TEXT;
ALTER TABLE signals ADD COLUMN news_top_headline TEXT;
ALTER TABLE signals ADD COLUMN news_action TEXT;           -- 'PASS', 'DOWNGRADED', 'SUPPRESSED', 'EARNINGS_BLACKOUT'
ALTER TABLE signals ADD COLUMN original_star_rating INTEGER; -- star rating before news downgrade
```

### 10.4 SignalRecord Model Extension

Add 5 optional fields to `SignalRecord` (`backend/signalpilot/db/models.py`), all defaulting to `None`:

```python
# News Sentiment fields (Phase 4b)
news_sentiment_score: float | None = None
news_sentiment_label: str | None = None
news_top_headline: str | None = None
news_action: str | None = None               # 'PASS', 'DOWNGRADED', 'SUPPRESSED', 'EARNINGS_BLACKOUT'
original_star_rating: int | None = None
```

The existing `_row_to_record()` pattern in `SignalRepository` already handles backward compatibility for optional columns (Phase 3 established this pattern) — the same approach applies here.

---

## 11. API Endpoints (FastAPI)

Added as a new route module `backend/signalpilot/dashboard/routes/news.py`, registered in `backend/signalpilot/dashboard/app.py` following the same pattern as existing route modules (performance, signals, strategies, etc.):

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/news/{stock_code}` | GET | Get sentiment analysis for a stock |
| `/api/v1/news/suppressed` | GET | List suppressed signals with reasons |
| `/api/v1/earnings/upcoming` | GET | Upcoming earnings calendar |

---

## 12. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Catastrophic trade prevention | 0 trades taken on stocks with SEBI probes, fraud news, or earnings misses | Manual review of suppressed signals |
| Suppressed signal accuracy | > 70% of suppressed signals would have been losers | Track suppressed signal outcomes |
| False suppression rate | < 15% of suppressed signals would have been winners | Same as above — want this low |
| News fetch latency | < 3 seconds for single-stock sentiment check | Monitor fetch + inference time |
| Downgraded signal performance | Downgraded signals have lower win rate than normal signals | Compare win rates |
| Earnings blackout compliance | 100% of stocks with same-day earnings are blocked | Cross-check calendar vs. signals |
| Pipeline cycle overhead (cache hit) | < 10ms per signal cycle | Measure NewsSentimentStage duration |

---

## 13. Development Timeline

| Week | Focus | Deliverables |
|------|-------|-------------|
| **Week 13** | News Sentiment Filter (Core) | `NewsFetcher` (RSS + feedparser), `NewsSentimentService` (FinBERT/VADER), `NewsSentimentRepository`, `EarningsCalendarRepository`, DB migrations, 8:30 AM pre-market fetch job, unit tests |
| **Week 14** | News Sentiment Filter (Integration) | `NewsSentimentStage` pipeline integration, `PersistAndDeliverStage` enhancement, suppression notifications, formatter news badge, NEWS/EARNINGS/UNSUPPRESS Telegram commands, dashboard API routes, integration tests with live data |

### Risk Mitigation

| Risk | Mitigation |
|------|------------|
| FinBERT too heavy for laptop/EC2 | Fallback: VADER + financial lexicon (pre-built, Week 13 Day 1). VADER is the recommended default for production. |
| RSS feeds are unreliable/blocked | Fallback: Google News scraping via feedparser. Multiple Tier 1 sources provide redundancy. |
| Cache miss during signal cycle | Treat as NO_NEWS (pass through). Never block the scan loop on network I/O. Background re-fetch for next cycle. |
| Sentiment model gives false positives | UNSUPPRESS command allows expert override. Start with conservative thresholds (suppress only at < -0.6). |

---

*Document Version: 2.0 — February 28, 2026*
*Extracted from: PRD_Phase4_Intelligence_Layer.md v4.0*
*Updated with codebase integration analysis*
