# Product Requirements Document (PRD)
# SignalPilot — Phase 4: Market Regime Detection

**Version:** 2.0
**Date:** February 28, 2026
**Author:** Biswajit (Product Owner & Developer)
**Status:** Phase 4 — Development
**Prerequisites:** Phase 1 (Gap & Go), Phase 2 (ORB + VWAP), Phase 3 (Hybrid Scoring + Dashboard), Phase 4 Quick Action Buttons complete and running live
**Parent PRD:** PRD_Phase4_Intelligence_Layer.md

---

## 1. Problem Statement

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

---

## 2. Solution: Morning Classification + Dynamic Strategy Weighting

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

---

## 3. Codebase Integration: Pipeline & Scheduler Placement

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

### 3.2 New Stage: `RegimeContextStage` — Between Stages 1 and 2

Market Regime Detection inserts as a **single new pipeline stage** between `CircuitBreakerGateStage` and `StrategyEvalStage`:

```
 1. CircuitBreakerGateStage     ← halt if SL limit exceeded
                                   ↓
 NEW: RegimeContextStage        ← read cached regime classification
                                   - Set regime modifiers on ScanContext
                                   - regime_min_stars, regime_position_modifier, regime_max_positions
                                   ↓
 2. StrategyEvalStage           ← run strategies (unchanged)
```

**Why this position:**

- **After CircuitBreakerGateStage (1):** Circuit breaker takes priority — if the breaker is tripped, regime doesn't matter. No point loading regime data if signals are already blocked.
- **Before StrategyEvalStage (2):** Regime context is available to all downstream stages from the very start of the pipeline. Every stage that needs regime data can read it from `ctx`.
- **The stage itself is near-zero cost:** Regime classification happens once at 9:30 AM via a scheduler job and is cached in memory. This stage simply reads the cached result and sets 6 fields on the context. Cost: **<1ms per cycle**.

**The stage follows the existing `PipelineStage` protocol:**

```python
class RegimeContextStage:
    @property
    def name(self) -> str:
        return "RegimeContext"

    async def process(self, ctx: ScanContext) -> ScanContext:
        # Read today's cached regime from MarketRegimeClassifier (in-memory cache)
        # If no classification yet (before 9:30 AM), use DEFAULT regime
        # Set ctx.regime, ctx.regime_confidence, ctx.regime_min_stars, etc.
        return ctx
```

### 3.3 ScanContext Changes

Add these **optional fields** to `ScanContext` (`backend/signalpilot/pipeline/context.py`). All default to neutral values — if the stage is absent, every other stage behaves identically to today:

```python
# Set by RegimeContextStage
regime: str | None = None                        # "TRENDING", "RANGING", "VOLATILE", or None (default)
regime_confidence: float = 0.0                   # 0.0-1.0
regime_min_stars: int = 3                        # Minimum star threshold (default 3 = no filter)
regime_position_modifier: float = 1.0            # 0.65x-1.0x multiplier (default 1.0 = no change)
regime_max_positions: int | None = None          # 4/6/8 override (None = use config default)
regime_strategy_weights: dict | None = None      # {"gap_go": 0.45, "orb": 0.35, "vwap": 0.20}
```

### 3.4 Existing Stages That Need Minor Modification

Three existing stages need **small, additive reads** of the new context fields. No logic rewrites — just reading optional fields that default to neutral values:

**`RankingStage`** (`backend/signalpilot/pipeline/stages/ranking.py`):
```python
# After existing ranking logic produces ranked_signals:
if ctx.regime_min_stars and ctx.regime_min_stars > 3:
    ctx.ranked_signals = [
        s for s in ctx.ranked_signals
        if s.signal_strength >= ctx.regime_min_stars
    ]
```
*Impact: 2-3 lines added. Default `regime_min_stars=3` means this filter is a no-op unless regime is active.*

**`RiskSizingStage`** (`backend/signalpilot/pipeline/stages/risk_sizing.py`):
```python
# Apply regime position modifier to quantity:
if ctx.regime_position_modifier and ctx.regime_position_modifier < 1.0:
    quantity = int(quantity * ctx.regime_position_modifier)

# Override max_positions if regime specifies it:
max_positions = ctx.regime_max_positions or user_config.max_positions
```
*Impact: 3-4 lines added. Default `regime_position_modifier=1.0` and `regime_max_positions=None` mean no change unless regime is active.*

**`PersistAndDeliverStage`** (`backend/signalpilot/pipeline/stages/persist_and_deliver.py`):
```python
# Before DB insert, attach regime metadata to SignalRecord:
if ctx.regime:
    record.market_regime = ctx.regime
    record.regime_confidence = ctx.regime_confidence
    record.regime_weight_modifier = ctx.regime_position_modifier
```
*Impact: 3 lines added. Fields are nullable — no impact when regime is not active.*

### 3.5 New Components

| Component | File Path | Responsibility |
|-----------|-----------|----------------|
| `MarketRegimeClassifier` | `backend/signalpilot/intelligence/regime_classifier.py` | Classification algorithm (VIX + gap + alignment → TRENDING/RANGING/VOLATILE), caching, re-classification |
| `RegimeDataCollector` | `backend/signalpilot/intelligence/regime_data.py` | Fetch VIX (SmartAPI/nsetools), Nifty gap/range (MarketDataStore), SGX/S&P500, FII/DII |
| `MorningBriefGenerator` | `backend/signalpilot/intelligence/morning_brief.py` | Compose the 8:45 AM morning brief message from collected data |
| `RegimeContextStage` | `backend/signalpilot/pipeline/stages/regime_context.py` | Pipeline stage — reads cached regime, sets modifiers on ScanContext |
| `MarketRegimeRepository` | `backend/signalpilot/db/regime_repo.py` | Store/query regime classifications (`market_regimes` table) |
| `RegimePerformanceRepository` | `backend/signalpilot/db/regime_performance_repo.py` | Track strategy performance by regime (`regime_performance` table) |

All new components are placed under `backend/signalpilot/intelligence/` — keeping the feature isolated from existing code.

### 3.6 Wiring in `create_app()` (`backend/signalpilot/main.py`)

New components are instantiated **after** existing repository and data layer setup, **before** pipeline construction:

```python
# After existing repo setup:
regime_repo = MarketRegimeRepository(connection)
regime_performance_repo = RegimePerformanceRepository(connection)

# After existing data layer setup (market_data, historical, etc.):
regime_data_collector = RegimeDataCollector(market_data, config)
regime_classifier = MarketRegimeClassifier(
    regime_data_collector, regime_repo, config
)
morning_brief = MorningBriefGenerator(regime_data_collector, watchlist_repo, config)
```

In `_build_pipeline()`, insert after `CircuitBreakerGateStage`:

```python
signal_stages = [
    CircuitBreakerGateStage(self._circuit_breaker),
    RegimeContextStage(regime_classifier),              # ← NEW
    StrategyEvalStage(...),
    GapStockMarkingStage(),
    DeduplicationStage(...),
    ConfidenceStage(...),
    CompositeScoringStage(...),
    AdaptiveFilterStage(...),
    RankingStage(...),
    RiskSizingStage(...),
    PersistAndDeliverStage(...),
    DiagnosticStage(...),
]
```

### 3.7 Scheduler Jobs

Five new cron jobs added to `MarketScheduler` (`backend/signalpilot/scheduler/scheduler.py`), following the existing pattern of `day_of_week='mon-fri'` + `_trading_day_guard` decorator:

| Time | Job | Action |
|------|-----|--------|
| **8:45 AM** | `send_morning_brief()` | Fetch global cues (S&P500, SGX, VIX, FII/DII), generate pre-market prediction, send Telegram brief |
| **9:30 AM** | `classify_regime()` | Collect 15-min data (Nifty gap, range, direction), run classification algorithm, persist to `market_regimes` table, cache in memory, send Telegram notification |
| **11:00 AM** | `check_regime_reclassify()` | If VIX spiked >15% from morning value, re-classify. Only upgrades severity (TRENDING→VOLATILE). |
| **1:00 PM** | `check_regime_reclassify()` | If Nifty reversed direction from morning, re-classify. Max 2 re-classifications per day. |
| **2:30 PM** | `check_regime_reclassify()` | If Nifty within 0.3% of open (round-trip), switch to RANGING. |

These run alongside the existing 9 scheduler jobs without conflict:
- 8:45 AM morning brief runs **before** the 9:00 AM pre-market alert
- 9:30 AM classification runs **after** 9:15 AM start scanning but **before** 9:45 AM lock opening ranges
- Re-classification checkpoints run during CONTINUOUS phase (9:45-14:30) alongside normal scanning

### 3.8 Integration with Existing Capital Allocation

The existing `CapitalAllocator` (`backend/signalpilot/scoring/capital_allocator.py`) already uses expectancy-based dynamic weighting from `StrategyPerformanceRepository`. Regime weights **layer on top** of this:

```
Final weight = CapitalAllocator weight × regime_strategy_weight adjustment
```

The regime does NOT replace the adaptive allocator — it modifies the output. On a VOLATILE day, even a well-performing strategy gets its weight reduced. On a TRENDING day, Gap & Go gets a boost regardless of its trailing win rate. The two systems complement each other:

- **CapitalAllocator** = long-term performance adjustment (30-day trailing window)
- **Regime weights** = short-term context adjustment (today's market conditions)

### 3.9 Performance Impact

| Scenario | Per-Cycle Cost | Notes |
|----------|---------------|-------|
| `RegimeContextStage` | **<1ms** | Reads cached regime from in-memory dict, sets 6 fields on ctx |
| `RankingStage` min-stars filter | **<0.1ms** | Single list comprehension on max 5 items |
| `RiskSizingStage` modifier | **<0.1ms** | One multiplication per signal |
| Classification (9:30 AM) | **~50-200ms** | Pure math on 8 float inputs. Runs once per day. |
| Re-classification checkpoints | **~50-200ms** | Same algorithm. Max 3× per day. |
| Morning brief data fetch | **~2-5s** | Network I/O for VIX, SGX, S&P. Runs once at 8:45 AM. |

**The 1-second scan loop is never blocked.** All expensive operations (data fetch, classification) happen in scheduler jobs, not in the pipeline cycle. The pipeline stage is a pure cache read.

### 3.10 What Stays Untouched

- **StrategyEvalStage, GapStockMarkingStage, DeduplicationStage, ConfidenceStage, CompositeScoringStage, AdaptiveFilterStage, DiagnosticStage** — zero changes
- **ExitMonitoringStage** — completely unaffected (regime does not affect open positions)
- **Existing Telegram commands** (TAKEN, SKIP, WATCH, STATUS, JOURNAL, CAPITAL, etc.) — unchanged
- **WebSocket, data engine, strategies** — completely unaffected
- **EventBus** — no new event types needed
- **Circuit breaker, adaptive manager** — operate independently from regime

---

## 4. Regime Classification Algorithm

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

---

## 5. Dynamic Strategy Weight Adjustment

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

These weights are stored in `AppConfig` (`backend/signalpilot/config.py`) as configurable parameters, following the existing pattern for strategy thresholds and scoring weights.

---

## 6. Position Size Adjustment by Regime

Beyond capital allocation, adjust per-trade position sizing:

| Regime | Position Size Modifier | Max Positions | Rationale |
|--------|----------------------|---------------|-----------|
| TRENDING | 1.0× (normal) | 8 | Standard — momentum supports trades |
| RANGING | 0.85× (slightly reduced) | 6 | Tighter ranges = less room for profit |
| VOLATILE | 0.65× (significantly reduced) | 4 | Wide swings = bigger SL = less capital per trade |

The modifier is applied inside `RiskSizingStage` (`backend/signalpilot/pipeline/stages/risk_sizing.py`) after the existing `PositionSizer.calculate()` call. The `regime_max_positions` overrides `user_config.max_positions` for the current cycle only — the user's configured value is not modified.

---

## 7. Intraday Regime Re-Classification

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
- Re-classification updates the in-memory cache immediately — the next pipeline cycle picks up the new regime via `RegimeContextStage`

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

---

## 8. Pre-Market Intelligence Brief (Bonus)

Every day at **8:45 AM IST**, send a brief context message via `bot.send_alert()`:

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

The watchlist section reads from the existing `WatchlistRepository` (`backend/signalpilot/db/watchlist_repo.py`) — reusing the Phase 4 Quick Action Buttons watchlist data.

---

## 9. New Telegram Commands

| Command | Action |
|---------|--------|
| `REGIME` | Show current market regime classification with all inputs |
| `REGIME HISTORY` | Show last 20 trading days' regimes with strategy performance per regime |
| `REGIME OVERRIDE TRENDING` | Manually override regime (expert mode) — resets at next checkpoint |
| `VIX` | Show current India VIX and interpretation |
| `MORNING` | Re-send today's morning brief |

These commands are registered as `MessageHandler` entries in `SignalPilotBot.start()` (`backend/signalpilot/telegram/bot.py`), following the same pattern as existing commands (TAKEN, STATUS, JOURNAL, CAPITAL, etc.). The `REGIME OVERRIDE` command updates the in-memory cache directly — the next pipeline cycle picks it up.

---

## 10. Database Schema Changes

### 10.1 New table: `market_regimes`

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

### 10.2 New table: `regime_performance` (populated daily by EOD summary)

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

### 10.3 Modified table: `signals` — add columns

Added via idempotent migration in `DatabaseManager._run_regime_detection_migration()` (`backend/signalpilot/db/database.py`), following the existing Phase 2/3/4 migration pattern using `PRAGMA table_info()` to check before `ALTER TABLE ADD COLUMN`:

```sql
ALTER TABLE signals ADD COLUMN market_regime TEXT;
ALTER TABLE signals ADD COLUMN regime_confidence REAL;
ALTER TABLE signals ADD COLUMN regime_weight_modifier REAL;
```

### 10.4 SignalRecord Model Extension

Add 3 optional fields to `SignalRecord` (`backend/signalpilot/db/models.py`), all defaulting to `None`:

```python
# Market Regime fields (Phase 4c)
market_regime: str | None = None              # 'TRENDING', 'RANGING', 'VOLATILE'
regime_confidence: float | None = None
regime_weight_modifier: float | None = None
```

The existing `_row_to_record()` pattern in `SignalRepository` already handles backward compatibility for optional columns (Phase 3 established this pattern) — the same approach applies here.

---

## 11. Dashboard Integration

**Page 9: Market Regime**
- Current regime display (large badge: TRENDING / RANGING / VOLATILE)
- Live inputs dashboard (VIX, gap, alignment, scores)
- Strategy weight visualization (pie chart adjusting in real-time)
- Historical regime calendar (color-coded: green=trending, yellow=ranging, red=volatile)
- Regime vs. performance correlation chart (bar chart: win rate by regime by strategy)

Added as a new route module `backend/signalpilot/dashboard/routes/regime.py`, registered in `backend/signalpilot/dashboard/app.py` following the same pattern as existing route modules (performance, signals, strategies, circuit_breaker, adaptation, etc.):

**API Endpoints:**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/regime/current` | GET | Current regime + all inputs |
| `/api/v1/regime/history` | GET | Last 30 days of regimes |
| `/api/v1/regime/performance` | GET | Win rate by regime by strategy |
| `/api/v1/regime/override` | POST | Manual override (expert mode) |
| `/api/v1/morning-brief` | GET | Today's morning brief data |

---

## 12. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Regime classification accuracy | > 70% alignment with end-of-day actual behavior | Compare morning prediction vs actual Nifty behavior |
| Win rate improvement in trending regime | Gap & Go win rate > 70% on trending days (vs ~60% baseline) | regime_performance table |
| Loss prevention in volatile regime | < 2 signals sent on volatile days (vs ~6 on normal days) | Signal count by regime |
| Capital saved on volatile days | 30%+ less capital deployed on volatile days | Position sizes × count |
| Re-classification accuracy | > 60% of re-classifications correctly identify deterioration | Compare re-class trigger vs. afternoon outcome |
| Strategy weight correlation | Higher-weighted strategies outperform lower-weighted on 70%+ of days | Compare performance by weight |
| Pipeline cycle overhead | < 1ms per cycle for RegimeContextStage | Measure stage duration |

---

## 13. Development Timeline

| Week | Focus | Deliverables |
|------|-------|-------------|
| **Week 15** | Market Regime Detection | `RegimeDataCollector` (VIX/SGX/S&P/FII-DII fetch), `MarketRegimeClassifier` (classification algorithm + in-memory cache), `RegimeContextStage` pipeline integration, `RankingStage`/`RiskSizingStage` minor modifications, `PersistAndDeliverStage` regime metadata persistence, `MarketRegimeRepository`, `RegimePerformanceRepository`, DB migrations, 8:45 AM morning brief, 9:30 AM classification job, re-classification checkpoints, REGIME/VIX/MORNING Telegram commands, dashboard API routes, unit + integration tests |

### Risk Mitigation

| Risk | Mitigation |
|------|------------|
| VIX data not available via SmartAPI | Fallback: Scrape NSE India VIX page / use nsetools library. `RegimeDataCollector` abstracts the data source. |
| Regime classification is inaccurate initially | Start in **shadow mode** — classify and log but don't adjust weights for first 2 weeks. Compare predictions to actual outcomes. Shadow mode is controlled by a `regime_shadow_mode` flag in `AppConfig`. |
| SGX Nifty or S&P data unavailable | Classification algorithm gracefully handles missing inputs — scores default to 0.0 for unavailable components. The algorithm still classifies from available data (VIX + gap + range). |
| Re-classification causes flip-flopping | Max 2 re-classifications per day. Only upgrade severity (TRENDING→VOLATILE), never downgrade. |

---

*Document Version: 2.0 — February 28, 2026*
*Extracted from: PRD_Phase4_Intelligence_Layer.md v4.0*
*Updated with codebase integration analysis*
