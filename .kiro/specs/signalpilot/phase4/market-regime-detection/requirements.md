# Requirements Document -- Phase 4: Market Regime Detection

## Introduction

SignalPilot currently treats every trading day identically -- all three strategies (Gap & Go, ORB, VWAP Reversal) run at equal weight regardless of market conditions. This is a significant blind spot because market conditions dramatically affect which strategies perform well and which generate false signals. On trending days, breakout strategies (Gap & Go, ORB) thrive while VWAP Reversal generates fake reversals. On ranging days, VWAP Reversal excels while Gap & Go finds no momentum. On volatile days (high VIX, wide swings), all strategies suffer from whipsaws and need defensive sizing. Without regime awareness, approximately 30% of trading days produce signals in the wrong strategy, leading to avoidable losses.

Market Regime Detection solves this by classifying each trading day into one of three regimes -- TRENDING, RANGING, or VOLATILE -- at 9:30 AM IST (15 minutes after market open), using a weighted composite of eight market inputs: India VIX, Nifty 50 opening gap percentage, first-15-minute range and direction, previous day's range, FII/DII net flows, SGX Nifty direction, and S&P 500 change. Based on the classified regime, the system dynamically adjusts strategy capital allocation weights, minimum star rating thresholds, position size modifiers, and maximum position counts. Intraday re-classification checkpoints at 11:00 AM, 1:00 PM, and 2:30 PM allow the system to adapt if conditions deteriorate (only severity upgrades, never downgrades, max 2 re-classifications per day).

The feature integrates as a single new pipeline stage (`RegimeContextStage`) inserted between `CircuitBreakerGateStage` (stage 1) and `StrategyEvalStage` (stage 2), which reads the cached regime classification and sets six modifier fields on `ScanContext`. The stage itself is near-zero cost (<1ms per cycle) because all expensive work (data collection, classification) happens in scheduler jobs outside the scan loop. Three existing stages (`RankingStage`, `RiskSizingStage`, `PersistAndDeliverStage`) receive small additive reads of the new context fields, with neutral defaults ensuring zero behavioral change when the feature is disabled.

The feature introduces six new components under `backend/signalpilot/intelligence/` (keeping the feature isolated from existing code), two new SQLite tables (`market_regimes`, `regime_performance`), three new nullable columns on the `signals` table, five new Telegram commands (REGIME, REGIME HISTORY, REGIME OVERRIDE, VIX, MORNING), five new FastAPI dashboard endpoints, and five new scheduler jobs (8:45 AM morning brief, 9:30 AM classification, 11:00 AM / 1:00 PM / 2:30 PM re-classification checkpoints). A shadow mode (`regime_shadow_mode` flag in `AppConfig`) allows the feature to classify and log without adjusting weights for the first 2 weeks, enabling accuracy validation before live activation.

**Prerequisites:** Phase 1 (Gap & Go), Phase 2 (ORB + VWAP Reversal), Phase 3 (Hybrid Scoring + Dashboard), Phase 4 Quick Action Buttons and News Sentiment Filter complete and running live.

**Parent PRD:** `PRD_Phase4_Market_Regime_Detection.md`

---

## 1. Regime Data Collection

### REQ-MRD-001: India VIX Fetch

**User Story:** As a trader, I want the system to fetch the current India VIX value, so that volatility levels are factored into the day's regime classification.

**Priority:** P0
**Dependencies:** None (new component)
**Components affected:** New `backend/signalpilot/intelligence/regime_data.py`

#### Acceptance Criteria

- [ ] WHEN the `RegimeDataCollector` is invoked to collect regime inputs THEN it SHALL fetch the current India VIX value from SmartAPI or nsetools as the primary source.
- [ ] WHEN the India VIX value is fetched THEN it SHALL be returned as a float representing the VIX index level (e.g., 14.2, 18.8).
- [ ] IF the primary VIX data source (SmartAPI) is unavailable THEN the system SHALL fall back to the nsetools library or NSE India VIX page scraping.
- [ ] IF all VIX data sources fail THEN the system SHALL log a warning and default the VIX score component to 0.0 (neutral), allowing classification to proceed from available data.
- [ ] WHEN VIX data is fetched THEN it SHALL be cached in memory for the current trading session to avoid repeated API calls.

---

### REQ-MRD-002: Nifty 50 Opening Gap Calculation

**User Story:** As a trader, I want the system to calculate the Nifty 50 opening gap percentage, so that gap-up or gap-down days are identified for regime classification.

**Priority:** P0
**Dependencies:** Existing `MarketDataStore` (`backend/signalpilot/data/market_data.py`)
**Components affected:** `backend/signalpilot/intelligence/regime_data.py`

#### Acceptance Criteria

- [ ] WHEN the `RegimeDataCollector` calculates the Nifty 50 opening gap THEN it SHALL compute `(today_open - yesterday_close) / yesterday_close * 100` as a percentage.
- [ ] WHEN the opening gap is calculated THEN the `yesterday_close` value SHALL be sourced from `HistoricalDataFetcher` or `MarketDataStore.historical_references`.
- [ ] WHEN the opening gap is calculated THEN the `today_open` value SHALL be sourced from the Nifty 50 tick data received at 9:15 AM via `MarketDataStore`.
- [ ] IF yesterday's close or today's open is unavailable THEN the system SHALL log a warning and default the gap score component to 0.0 (neutral).

---

### REQ-MRD-003: Nifty 50 First-15-Minute Range and Direction

**User Story:** As a trader, I want the system to measure the Nifty 50 first-15-minute range and direction, so that the opening session volatility and trend are captured for classification.

**Priority:** P0
**Dependencies:** Existing `MarketDataStore`
**Components affected:** `backend/signalpilot/intelligence/regime_data.py`

#### Acceptance Criteria

- [ ] WHEN the `RegimeDataCollector` calculates the first-15-minute range THEN it SHALL compute `(high - low) / open * 100` using the Nifty 50 high, low, and open from the 9:15-9:30 AM candle.
- [ ] WHEN the first-15-minute direction is determined THEN it SHALL be classified as `'UP'` if close > open, `'DOWN'` if close < open, or `'FLAT'` if close equals open (within 0.01% tolerance).
- [ ] WHEN the data is collected THEN the 9:15-9:30 AM candle data SHALL be sourced from `MarketDataStore` tick aggregation for the Nifty 50 index.
- [ ] IF the first-15-minute candle data is incomplete (e.g., market data gap) THEN the system SHALL log a warning and default the range score component to 0.0 (neutral) and direction to `'FLAT'`.

---

### REQ-MRD-004: Previous Day Market Data

**User Story:** As a trader, I want the system to include the previous day's Nifty 50 range in classification inputs, so that recent historical volatility context informs the current day's regime.

**Priority:** P1
**Dependencies:** Existing `HistoricalDataFetcher`
**Components affected:** `backend/signalpilot/intelligence/regime_data.py`

#### Acceptance Criteria

- [ ] WHEN the `RegimeDataCollector` collects previous day data THEN it SHALL compute the previous day's range percentage as `(yesterday_high - yesterday_low) / yesterday_close * 100`.
- [ ] WHEN previous day data is collected THEN it SHALL be sourced from `HistoricalDataFetcher` or pre-fetched historical references at startup.
- [ ] IF previous day data is unavailable THEN the system SHALL log a warning and exclude this component from the classification score without blocking classification.

---

### REQ-MRD-005: FII/DII Net Flow Data

**User Story:** As a trader, I want the system to include previous day's FII/DII net flow data, so that institutional money flow context is available for regime classification and the morning brief.

**Priority:** P1
**Dependencies:** None (new data source)
**Components affected:** `backend/signalpilot/intelligence/regime_data.py`

#### Acceptance Criteria

- [ ] WHEN the `RegimeDataCollector` fetches FII/DII data THEN it SHALL retrieve the previous trading day's net FII and net DII values in crores from NSE or a public data source.
- [ ] WHEN FII/DII data is fetched THEN it SHALL be cached for the current trading session since the values do not change intraday.
- [ ] IF FII/DII data is unavailable THEN the system SHALL log a warning and proceed with classification from available inputs, treating FII/DII as neutral.

---

### REQ-MRD-006: Global Cues (SGX Nifty, S&P 500)

**User Story:** As a trader, I want the system to include SGX Nifty direction and S&P 500 percentage change as global cues, so that international market sentiment is factored into regime classification.

**Priority:** P1
**Dependencies:** None (new data source)
**Components affected:** `backend/signalpilot/intelligence/regime_data.py`

#### Acceptance Criteria

- [ ] WHEN the `RegimeDataCollector` fetches global cues THEN it SHALL retrieve the SGX Nifty pre-market direction (`'UP'`, `'DOWN'`, or `'FLAT'`) and the S&P 500 previous session percentage change.
- [ ] WHEN global cues are fetched THEN the SGX Nifty direction SHALL be determined from the pre-market SGX Nifty futures trend relative to the previous Nifty close.
- [ ] WHEN global cues are fetched THEN the S&P 500 percentage change SHALL represent the previous US trading session's close-to-close change.
- [ ] IF SGX Nifty or S&P 500 data is unavailable THEN the system SHALL log a warning and default the corresponding directional alignment component to 0 (neutral), allowing classification to proceed from available data.
- [ ] WHEN global cues are fetched THEN they SHALL be cached in memory for the current trading session.

---

### REQ-MRD-007: Graceful Data Degradation

**User Story:** As a developer, I want the classification algorithm to gracefully handle missing data inputs, so that the system always produces a classification even when individual data sources fail.

**Priority:** P0
**Dependencies:** REQ-MRD-001 through REQ-MRD-006
**Components affected:** `backend/signalpilot/intelligence/regime_data.py`, `backend/signalpilot/intelligence/regime_classifier.py`

#### Acceptance Criteria

- [ ] WHEN one or more data inputs are unavailable THEN the `MarketRegimeClassifier` SHALL still produce a classification using the available inputs, with missing components defaulting to their neutral score (0.0).
- [ ] WHEN data degradation occurs THEN the classification confidence SHALL be reduced proportionally to the number of missing inputs.
- [ ] WHEN data degradation occurs THEN the system SHALL log at WARNING level which inputs were unavailable and which defaults were applied.
- [ ] WHEN only VIX and the Nifty 50 gap/range are available (minimum viable inputs) THEN the system SHALL still produce a valid classification.

---

## 2. Regime Classification Algorithm

### REQ-MRD-008: Composite Regime Score Calculation

**User Story:** As a trader, I want the system to classify the market regime using a weighted composite of multiple indicators, so that the classification is robust and not dependent on any single input.

**Priority:** P0
**Dependencies:** REQ-MRD-001 through REQ-MRD-006
**Components affected:** New `backend/signalpilot/intelligence/regime_classifier.py`

#### Acceptance Criteria

- [ ] WHEN the `MarketRegimeClassifier.classify_regime()` method is called THEN it SHALL compute component scores from the eight inputs: VIX score, gap score (based on `abs(nifty_gap_pct)`), first-15-minute range score, directional alignment score, and incorporate previous day range, FII/DII, SGX direction, and S&P 500 change.
- [ ] WHEN component scores are calculated THEN each individual component score SHALL be normalized to the range [-1.0, +1.0].
- [ ] WHEN the composite scores are calculated THEN the system SHALL compute three regime scores using weighted formulas: `trending_score = (gap_score * 0.35) + (alignment * 0.30) + (range_score * 0.20) + ((1 - vix_score) * 0.15)`, `ranging_score = ((-gap_score) * 0.35) + ((-range_score) * 0.30) + ((1 - vix_score) * 0.35)`, `volatile_score = (vix_score * 0.40) + (range_score * 0.30) + ((1 - alignment) * 0.30)`.
- [ ] WHEN the three regime scores are computed THEN the system SHALL select the regime with the highest score (winner-takes-all).
- [ ] WHEN the regime is selected THEN the confidence SHALL be calculated as the selected regime's score divided by the sum of absolute values of all three regime scores, clamped to [0.0, 1.0], with a fallback of 0.33 if all scores are zero.

---

### REQ-MRD-009: VIX Score Mapping

**User Story:** As a developer, I want VIX levels mapped to a standardized score, so that the classification algorithm has a consistent volatility signal.

**Priority:** P0
**Dependencies:** REQ-MRD-001
**Components affected:** `backend/signalpilot/intelligence/regime_classifier.py`

#### Acceptance Criteria

- [ ] WHEN VIX is below 12 THEN the VIX score SHALL be -0.5 (very calm, ranging likely).
- [ ] WHEN VIX is between 12 and 14 (exclusive) THEN the VIX score SHALL be 0.0 (normal).
- [ ] WHEN VIX is between 14 and 18 (exclusive) THEN the VIX score SHALL be 0.3 (slightly elevated).
- [ ] WHEN VIX is between 18 and 22 (exclusive) THEN the VIX score SHALL be 0.6 (high, volatile likely).
- [ ] WHEN VIX is 22 or above THEN the VIX score SHALL be 1.0 (very high, defensive mode).

---

### REQ-MRD-010: Gap Score Mapping

**User Story:** As a developer, I want Nifty gap percentages mapped to a standardized score, so that the classification algorithm captures gap magnitude.

**Priority:** P0
**Dependencies:** REQ-MRD-002
**Components affected:** `backend/signalpilot/intelligence/regime_classifier.py`

#### Acceptance Criteria

- [ ] WHEN the absolute Nifty gap percentage is greater than 1.5% THEN the gap score SHALL be 1.0 (big gap, trending day).
- [ ] WHEN the absolute Nifty gap percentage is between 0.8% and 1.5% (inclusive) THEN the gap score SHALL be 0.6 (moderate gap).
- [ ] WHEN the absolute Nifty gap percentage is between 0.3% and 0.8% (exclusive) THEN the gap score SHALL be 0.2 (small gap).
- [ ] WHEN the absolute Nifty gap percentage is 0.3% or less THEN the gap score SHALL be -0.5 (no gap, ranging likely).

---

### REQ-MRD-011: Range Score Mapping

**User Story:** As a developer, I want the first-15-minute range percentage mapped to a standardized score, so that opening session volatility is captured.

**Priority:** P0
**Dependencies:** REQ-MRD-003
**Components affected:** `backend/signalpilot/intelligence/regime_classifier.py`

#### Acceptance Criteria

- [ ] WHEN the first-15-minute range percentage is greater than 1.0% THEN the range score SHALL be 1.0 (wide range, volatile).
- [ ] WHEN the first-15-minute range percentage is between 0.5% and 1.0% (inclusive) THEN the range score SHALL be 0.5 (moderate range, trending).
- [ ] WHEN the first-15-minute range percentage is between 0.2% and 0.5% (exclusive) THEN the range score SHALL be 0.0 (normal).
- [ ] WHEN the first-15-minute range percentage is 0.2% or less THEN the range score SHALL be -0.5 (tight range, ranging).

---

### REQ-MRD-012: Directional Alignment Score

**User Story:** As a developer, I want a directional alignment score that measures whether multiple market signals agree on direction, so that the classification algorithm can distinguish strong trends from mixed signals.

**Priority:** P0
**Dependencies:** REQ-MRD-002, REQ-MRD-003, REQ-MRD-006
**Components affected:** `backend/signalpilot/intelligence/regime_classifier.py`

#### Acceptance Criteria

- [ ] WHEN the directional alignment score is calculated THEN it SHALL evaluate four directional signals: Nifty gap direction (positive if gap > 0.3%, negative if gap < -0.3%, else neutral), first-15-minute candle direction (UP=+1, DOWN=-1, FLAT=0), SGX Nifty direction (UP=+1, DOWN=-1, FLAT=0), and S&P 500 direction (positive if change > 0.3%, negative if change < -0.3%, else neutral).
- [ ] WHEN the four directional signals are evaluated THEN the alignment score SHALL be computed as `abs(sum(directions)) / len(directions)`, producing a value between 0.0 (mixed signals) and 1.0 (full agreement).
- [ ] WHEN one or more directional signals are unavailable THEN the missing signals SHALL default to 0 (neutral) and the denominator SHALL still use the total count of 4, reducing the alignment score proportionally.

---

### REQ-MRD-013: Classification Result Structure

**User Story:** As a developer, I want the classification result to include the regime, confidence, component scores, and raw inputs, so that the result is fully auditable and can be persisted, displayed, and debugged.

**Priority:** P0
**Dependencies:** REQ-MRD-008
**Components affected:** `backend/signalpilot/intelligence/regime_classifier.py`

#### Acceptance Criteria

- [ ] WHEN `classify_regime()` returns a result THEN it SHALL include: `regime` (str: `"TRENDING"`, `"RANGING"`, or `"VOLATILE"`), `confidence` (float: 0.0-1.0, rounded to 2 decimal places), `scores` (dict mapping each regime name to its computed score, rounded to 3 decimal places), and `inputs` (dict containing all raw input values used: VIX, gap_pct, first_15_range_pct, alignment, prev_day_range_pct, fii_net_crores, dii_net_crores, sgx_direction, sp500_change_pct).
- [ ] WHEN the classification result is produced THEN it SHALL be representable as a Python dataclass or dict for easy serialization to JSON and database persistence.

---

### REQ-MRD-014: In-Memory Regime Cache

**User Story:** As a developer, I want the classified regime cached in memory, so that the pipeline stage can read it in <1ms per cycle without repeated classification.

**Priority:** P0
**Dependencies:** REQ-MRD-008
**Components affected:** `backend/signalpilot/intelligence/regime_classifier.py`

#### Acceptance Criteria

- [ ] WHEN `classify_regime()` completes THEN the result SHALL be stored in an in-memory cache (dict or attribute) on the `MarketRegimeClassifier` instance, keyed by the current IST date.
- [ ] WHEN the `RegimeContextStage` reads the cached regime THEN it SHALL retrieve the result in constant time (<1ms) without triggering a re-classification.
- [ ] WHEN no classification has been performed yet for the current day (before 9:30 AM) THEN the cache SHALL return a DEFAULT regime with neutral modifiers (all weights equal, `regime_min_stars=3`, `regime_position_modifier=1.0`, `regime_max_positions=None`).
- [ ] WHEN a re-classification occurs THEN it SHALL overwrite the cached result immediately, and the next pipeline cycle SHALL pick up the updated regime.

---

## 3. Dynamic Strategy Weight Adjustment

### REQ-MRD-015: Regime-Based Strategy Weights

**User Story:** As a trader, I want strategy capital allocation weights dynamically adjusted based on the classified regime, so that capital favors the strategies most likely to succeed in current market conditions.

**Priority:** P0
**Dependencies:** REQ-MRD-008
**Components affected:** `backend/signalpilot/intelligence/regime_classifier.py`, `backend/signalpilot/pipeline/stages/regime_context.py`

#### Acceptance Criteria

- [ ] WHEN the regime is TRENDING with high confidence (> 0.55) THEN the strategy weights SHALL be: Gap & Go 45%, ORB 35%, VWAP Reversal 20%.
- [ ] WHEN the regime is TRENDING with low confidence (<= 0.55) THEN the strategy weights SHALL be: Gap & Go 38%, ORB 35%, VWAP Reversal 27%.
- [ ] WHEN the regime is RANGING with high confidence (> 0.55) THEN the strategy weights SHALL be: Gap & Go 20%, ORB 30%, VWAP Reversal 50%.
- [ ] WHEN the regime is RANGING with low confidence (<= 0.55) THEN the strategy weights SHALL be: Gap & Go 28%, ORB 33%, VWAP Reversal 39%.
- [ ] WHEN the regime is VOLATILE with high confidence (> 0.55) THEN the strategy weights SHALL be: Gap & Go 25%, ORB 25%, VWAP Reversal 25% (remaining 25% unallocated as reserve).
- [ ] WHEN the regime is VOLATILE with low confidence (<= 0.55) THEN the strategy weights SHALL be: Gap & Go 30%, ORB 30%, VWAP Reversal 30% (remaining 10% unallocated as reserve).
- [ ] WHEN no regime classification is available (DEFAULT) THEN the strategy weights SHALL be: Gap & Go 33%, ORB 33%, VWAP Reversal 34%.
- [ ] WHEN regime weights are applied THEN they SHALL layer on top of the existing `CapitalAllocator` weights as: `final_weight = CapitalAllocator_weight * regime_strategy_weight_adjustment`, not replace them.

---

### REQ-MRD-016: Regime-Based Minimum Star Rating

**User Story:** As a trader, I want the minimum star rating threshold adjusted by regime, so that only higher-quality signals are delivered during uncertain or volatile conditions.

**Priority:** P0
**Dependencies:** REQ-MRD-008
**Components affected:** `backend/signalpilot/pipeline/stages/ranking.py` (minor modification)

#### Acceptance Criteria

- [ ] WHEN the regime is TRENDING (any confidence) THEN `regime_min_stars` SHALL be 3 (aggressive, standard threshold).
- [ ] WHEN the regime is RANGING with low confidence THEN `regime_min_stars` SHALL be 4 (selective).
- [ ] WHEN the regime is RANGING with high confidence THEN `regime_min_stars` SHALL be 3.
- [ ] WHEN the regime is VOLATILE with high confidence THEN `regime_min_stars` SHALL be 5 (defensive, only top signals).
- [ ] WHEN the regime is VOLATILE with low confidence THEN `regime_min_stars` SHALL be 4.
- [ ] WHEN the regime is DEFAULT (no classification) THEN `regime_min_stars` SHALL be 3 (no additional filtering).
- [ ] WHEN `RankingStage` processes ranked signals AND `ctx.regime_min_stars` is greater than 3 THEN it SHALL filter out signals with `signal_strength` below `ctx.regime_min_stars`.
- [ ] WHEN `regime_min_stars` is 3 (default) THEN the filter SHALL be a no-op, preserving backward compatibility.

---

### REQ-MRD-017: Regime-Based Position Size Modifier

**User Story:** As a trader, I want per-trade position sizes reduced during volatile or ranging regimes, so that risk exposure is automatically lowered when conditions are unfavorable.

**Priority:** P0
**Dependencies:** REQ-MRD-008
**Components affected:** `backend/signalpilot/pipeline/stages/risk_sizing.py` (minor modification)

#### Acceptance Criteria

- [ ] WHEN the regime is TRENDING THEN `regime_position_modifier` SHALL be 1.0 (normal position sizing).
- [ ] WHEN the regime is RANGING THEN `regime_position_modifier` SHALL be 0.85 (15% size reduction).
- [ ] WHEN the regime is VOLATILE THEN `regime_position_modifier` SHALL be 0.65 (35% size reduction).
- [ ] WHEN the regime is DEFAULT THEN `regime_position_modifier` SHALL be 1.0 (no change).
- [ ] WHEN `RiskSizingStage` calculates quantity AND `ctx.regime_position_modifier` is less than 1.0 THEN it SHALL multiply the calculated quantity by the modifier and round down to the nearest integer via `int()`.
- [ ] WHEN `regime_position_modifier` is 1.0 (default) THEN the multiplication SHALL be a no-op, preserving backward compatibility.

---

### REQ-MRD-018: Regime-Based Maximum Positions Override

**User Story:** As a trader, I want the maximum concurrent positions limit adjusted by regime, so that capital concentration is reduced during volatile conditions.

**Priority:** P0
**Dependencies:** REQ-MRD-008
**Components affected:** `backend/signalpilot/pipeline/stages/risk_sizing.py` (minor modification)

#### Acceptance Criteria

- [ ] WHEN the regime is TRENDING THEN `regime_max_positions` SHALL be 8 (standard).
- [ ] WHEN the regime is RANGING THEN `regime_max_positions` SHALL be 6 (moderately reduced).
- [ ] WHEN the regime is VOLATILE THEN `regime_max_positions` SHALL be 4 (significantly reduced).
- [ ] WHEN the regime is DEFAULT THEN `regime_max_positions` SHALL be `None` (use `user_config.max_positions`).
- [ ] WHEN `RiskSizingStage` determines the maximum positions AND `ctx.regime_max_positions` is not `None` THEN it SHALL use `ctx.regime_max_positions` instead of `user_config.max_positions` for the current cycle.
- [ ] WHEN `regime_max_positions` is `None` (default) THEN the behavior SHALL be identical to the pre-feature baseline, using `user_config.max_positions`.

---

## 4. Pipeline Integration

### REQ-MRD-019: RegimeContextStage Pipeline Stage

**User Story:** As a developer, I want the regime detection implemented as a `PipelineStage` that slots between `CircuitBreakerGateStage` and `StrategyEvalStage`, so that regime context is available to all downstream stages from the very start of the pipeline.

**Priority:** P0
**Dependencies:** REQ-MRD-008, REQ-MRD-014
**Components affected:** New `backend/signalpilot/pipeline/stages/regime_context.py`

#### Acceptance Criteria

- [ ] WHEN the pipeline is constructed THEN the `RegimeContextStage` SHALL be inserted after `CircuitBreakerGateStage` (stage 1) and before `StrategyEvalStage` (stage 2).
- [ ] WHEN the `RegimeContextStage` implements the `PipelineStage` protocol THEN it SHALL expose a `name` property returning `"RegimeContext"` and an `async def process(self, ctx: ScanContext) -> ScanContext` method.
- [ ] WHEN the `RegimeContextStage` processes a context THEN it SHALL read the cached regime from `MarketRegimeClassifier` and set six fields on the context: `ctx.regime`, `ctx.regime_confidence`, `ctx.regime_min_stars`, `ctx.regime_position_modifier`, `ctx.regime_max_positions`, and `ctx.regime_strategy_weights`.
- [ ] WHEN no classification exists for the current day (before 9:30 AM) THEN the stage SHALL set DEFAULT regime values (all neutral) on the context.
- [ ] WHEN the `RegimeContextStage` processes a context THEN total execution time SHALL be under 1ms per cycle (pure in-memory cache read).
- [ ] WHEN the `RegimeContextStage` is absent from the pipeline (e.g., feature disabled) THEN all other stages SHALL behave identically to the pre-feature baseline due to the optional default values on `ScanContext`.

---

### REQ-MRD-020: ScanContext Extension

**User Story:** As a developer, I want `ScanContext` extended with optional regime fields, so that regime data flows through the pipeline without breaking existing stages.

**Priority:** P0
**Dependencies:** REQ-MRD-019
**Components affected:** `backend/signalpilot/pipeline/context.py`

#### Acceptance Criteria

- [ ] WHEN Phase 4 Market Regime Detection is deployed THEN `ScanContext` SHALL include the following new fields with specified defaults: `regime: str | None = None`, `regime_confidence: float = 0.0`, `regime_min_stars: int = 3`, `regime_position_modifier: float = 1.0`, `regime_max_positions: int | None = None`, `regime_strategy_weights: dict | None = None`.
- [ ] WHEN the `RegimeContextStage` is not present in the pipeline THEN the default values of these fields SHALL ensure no behavioral change in any existing stage.
- [ ] WHEN `regime` is `None` THEN all downstream stages SHALL treat this as "no regime active" and apply no regime-based modifications.

---

### REQ-MRD-021: PersistAndDeliverStage Enhancement

**User Story:** As a developer, I want `PersistAndDeliverStage` to persist regime metadata on each signal record, so that every signal is tagged with the market regime under which it was generated for historical analysis.

**Priority:** P0
**Dependencies:** REQ-MRD-019, REQ-MRD-020, REQ-MRD-029 (DB columns)
**Components affected:** `backend/signalpilot/pipeline/stages/persist_and_deliver.py`

#### Acceptance Criteria

- [ ] WHEN a signal is persisted AND `ctx.regime` is not `None` THEN `PersistAndDeliverStage` SHALL set `market_regime`, `regime_confidence`, and `regime_weight_modifier` on the `SignalRecord` before DB insert.
- [ ] WHEN regime metadata is not available (feature disabled or `ctx.regime` is `None`) THEN the existing persistence logic SHALL behave identically to the pre-feature baseline with all regime fields as `None`.
- [ ] WHEN regime metadata is persisted THEN the `market_regime` field SHALL contain one of `"TRENDING"`, `"RANGING"`, or `"VOLATILE"`.

---

### REQ-MRD-022: Pipeline Wiring in create_app

**User Story:** As a developer, I want all new regime detection components instantiated and wired in `create_app()` following the existing dependency-injection pattern, so that the feature is cleanly integrated into the application lifecycle.

**Priority:** P0
**Dependencies:** REQ-MRD-019, REQ-MRD-025, REQ-MRD-026
**Components affected:** `backend/signalpilot/main.py`

#### Acceptance Criteria

- [ ] WHEN the application starts THEN `create_app()` SHALL instantiate `MarketRegimeRepository(connection)` and `RegimePerformanceRepository(connection)` after existing repository setup.
- [ ] WHEN the application starts THEN `create_app()` SHALL instantiate `RegimeDataCollector(market_data, config)` and `MarketRegimeClassifier(regime_data_collector, regime_repo, config)` after existing data layer setup.
- [ ] WHEN the application starts THEN `create_app()` SHALL instantiate `MorningBriefGenerator(regime_data_collector, watchlist_repo, config)` for the pre-market brief.
- [ ] WHEN the pipeline is built THEN `RegimeContextStage(regime_classifier)` SHALL be inserted into the `signal_stages` list immediately after `CircuitBreakerGateStage` and before `StrategyEvalStage`.
- [ ] WHEN the stage is wired THEN no existing stage constructors or argument lists SHALL be modified.

---

## 5. Intraday Regime Re-Classification

### REQ-MRD-023: Scheduled Re-Classification Checkpoints

**User Story:** As a trader, I want the system to re-evaluate the regime at key intraday checkpoints, so that if conditions deteriorate significantly from the morning classification, the strategy adjustments are updated.

**Priority:** P0
**Dependencies:** REQ-MRD-008, REQ-MRD-014
**Components affected:** `backend/signalpilot/intelligence/regime_classifier.py`, `backend/signalpilot/scheduler/scheduler.py`

#### Acceptance Criteria

- [ ] WHEN 11:00 AM IST arrives on a trading day THEN the `MarketScheduler` SHALL trigger a `check_regime_reclassify()` job that checks if VIX has spiked more than 15% from the morning value, and if so, re-classifies.
- [ ] WHEN 1:00 PM IST arrives on a trading day THEN the `MarketScheduler` SHALL trigger a `check_regime_reclassify()` job that checks if Nifty 50 has reversed direction from the morning classification, and if so, re-classifies.
- [ ] WHEN 2:30 PM IST arrives on a trading day THEN the `MarketScheduler` SHALL trigger a `check_regime_reclassify()` job that checks if Nifty 50 is within 0.3% of its open (round-trip), and if so, switches to RANGING.
- [ ] WHEN re-classification checkpoints are scheduled THEN they SHALL use `day_of_week='mon-fri'` and the `_trading_day_guard` decorator to skip NSE holidays, following the existing scheduler pattern.

---

### REQ-MRD-024: Re-Classification Rules

**User Story:** As a developer, I want re-classification constrained by safety rules, so that the system does not flip-flop between regimes intraday.

**Priority:** P0
**Dependencies:** REQ-MRD-023
**Components affected:** `backend/signalpilot/intelligence/regime_classifier.py`

#### Acceptance Criteria

- [ ] WHEN re-classification is evaluated THEN the system SHALL only upgrade severity (e.g., TRENDING to VOLATILE, RANGING to VOLATILE), never downgrade (e.g., VOLATILE to TRENDING).
- [ ] WHEN the maximum of 2 re-classifications per day has been reached THEN subsequent checkpoint evaluations SHALL log a skip message and not re-classify, regardless of the trigger condition.
- [ ] WHEN a re-classification occurs THEN the system SHALL log the event at INFO level with the previous regime, new regime, trigger condition, and checkpoint time.
- [ ] WHEN a re-classification occurs THEN the in-memory cache SHALL be updated immediately, and the next pipeline cycle SHALL pick up the new regime.
- [ ] WHEN a re-classification occurs THEN it SHALL be persisted to the `market_regimes` table with `is_reclassification=True` and `previous_regime` set to the previous classification.
- [ ] WHEN a re-classification occurs THEN existing open positions SHALL NOT be affected -- only new signals are filtered by the updated rules.

---

## 6. Pre-Market Morning Brief

### REQ-MRD-025: Morning Brief Generation

**User Story:** As a trader, I want to receive a pre-market morning brief at 8:45 AM IST with global cues, India context, regime prediction, and watchlist alerts, so that I have situational awareness before market open.

**Priority:** P1
**Dependencies:** REQ-MRD-001, REQ-MRD-005, REQ-MRD-006
**Components affected:** New `backend/signalpilot/intelligence/morning_brief.py`, `backend/signalpilot/scheduler/scheduler.py`

#### Acceptance Criteria

- [ ] WHEN 8:45 AM IST arrives on a trading day THEN the `MarketScheduler` SHALL trigger a `send_morning_brief()` job that collects global cues, India context data, and generates a pre-market regime prediction.
- [ ] WHEN the morning brief is generated THEN it SHALL include: global cues section (S&P 500 change, Nasdaq change, Asian market direction, SGX Nifty direction), India context section (India VIX value and interpretation, previous day's FII and DII net flows in crores), regime prediction (likely regime based on available pre-market data with reasoning), and watchlist alerts from `WatchlistRepository` for stocks watched within the past 5 days.
- [ ] WHEN the morning brief is generated THEN it SHALL be sent via `bot.send_alert()` following the existing Telegram messaging pattern.
- [ ] WHEN the morning brief scheduler job is set up THEN it SHALL use `day_of_week='mon-fri'` and the `_trading_day_guard` decorator.
- [ ] IF any data source for the morning brief fails THEN the brief SHALL still be generated with available data and a note indicating which sections are missing.

---

### REQ-MRD-026: Morning Brief Watchlist Integration

**User Story:** As a trader, I want the morning brief to include status updates on my watched stocks, so that I am reminded of stocks I previously flagged for monitoring.

**Priority:** P2
**Dependencies:** REQ-MRD-025, existing `WatchlistRepository`
**Components affected:** `backend/signalpilot/intelligence/morning_brief.py`

#### Acceptance Criteria

- [ ] WHEN the morning brief is generated THEN the `MorningBriefGenerator` SHALL query `WatchlistRepository` for active watchlist entries (within 5-day expiry window).
- [ ] WHEN watchlist entries exist THEN the brief SHALL include each watched stock's symbol and the date it was added.
- [ ] IF no watchlist entries are active THEN the watchlist section SHALL be omitted from the morning brief.

---

## 7. Database Schema

### REQ-MRD-027: Market Regimes Table

**User Story:** As a developer, I want a `market_regimes` table to store each day's regime classification with all inputs and derived values, so that classification history is queryable for analysis, the REGIME HISTORY command, and the dashboard.

**Priority:** P0
**Dependencies:** None (new table)
**Components affected:** New `backend/signalpilot/db/regime_repo.py`, `backend/signalpilot/db/database.py` (migration)

#### Acceptance Criteria

- [ ] WHEN the database is initialized THEN a `market_regimes` table SHALL be created with columns: `id` (INTEGER PRIMARY KEY AUTOINCREMENT), `regime_date` (DATE NOT NULL), `classification_time` (TIME NOT NULL), `regime` (TEXT NOT NULL), `confidence` (REAL NOT NULL), `trending_score` (REAL), `ranging_score` (REAL), `volatile_score` (REAL), `india_vix` (REAL), `nifty_gap_pct` (REAL), `nifty_first_15_range_pct` (REAL), `nifty_first_15_direction` (TEXT), `directional_alignment` (REAL), `sp500_change_pct` (REAL), `sgx_direction` (TEXT), `fii_net_crores` (REAL), `dii_net_crores` (REAL), `is_reclassification` (BOOLEAN DEFAULT 0), `previous_regime` (TEXT), `strategy_weights_json` (TEXT), `min_star_rating` (INTEGER), `max_positions` (INTEGER), `position_size_modifier` (REAL), `created_at` (DATETIME DEFAULT CURRENT_TIMESTAMP).
- [ ] WHEN the `market_regimes` table is created THEN an index `idx_regime_date` SHALL be created on `(regime_date)` for fast date-based lookups.
- [ ] WHEN the migration runs THEN it SHALL use the idempotent pattern established by Phase 2/3/4 migrations in `DatabaseManager`.

---

### REQ-MRD-028: Regime Performance Table

**User Story:** As a developer, I want a `regime_performance` table to track strategy performance broken down by regime, so that the system can validate whether regime-based weight adjustments are improving outcomes.

**Priority:** P1
**Dependencies:** None (new table)
**Components affected:** New `backend/signalpilot/db/regime_performance_repo.py`, `backend/signalpilot/db/database.py` (migration)

#### Acceptance Criteria

- [ ] WHEN the database is initialized THEN a `regime_performance` table SHALL be created with columns: `id` (INTEGER PRIMARY KEY AUTOINCREMENT), `regime_date` (DATE NOT NULL), `regime` (TEXT NOT NULL), `strategy` (TEXT NOT NULL), `signals_generated` (INTEGER DEFAULT 0), `signals_taken` (INTEGER DEFAULT 0), `wins` (INTEGER DEFAULT 0), `losses` (INTEGER DEFAULT 0), `pnl` (REAL DEFAULT 0.0), `win_rate` (REAL), `created_at` (DATETIME DEFAULT CURRENT_TIMESTAMP).
- [ ] WHEN the `regime_performance` table is created THEN an index `idx_regime_perf` SHALL be created on `(regime, strategy)`.
- [ ] WHEN the daily summary job runs (15:30 IST) THEN the system SHALL populate the `regime_performance` table with that day's strategy performance metrics grouped by the day's regime.

---

### REQ-MRD-029: Signals Table Column Additions

**User Story:** As a developer, I want three new nullable columns on the `signals` table to persist regime metadata per signal, so that every signal can be traced to the market regime under which it was generated.

**Priority:** P0
**Dependencies:** None
**Components affected:** `backend/signalpilot/db/database.py` (migration), `backend/signalpilot/db/models.py`

#### Acceptance Criteria

- [ ] WHEN the regime detection migration runs THEN it SHALL add three columns to the `signals` table: `market_regime` (TEXT), `regime_confidence` (REAL), and `regime_weight_modifier` (REAL), all nullable.
- [ ] WHEN the migration runs THEN it SHALL use the idempotent `PRAGMA table_info()` check-before-alter pattern established by Phase 2/3/4 migrations in `DatabaseManager._run_regime_detection_migration()`.
- [ ] WHEN `SignalRecord` is updated THEN it SHALL include three new optional fields: `market_regime: str | None = None`, `regime_confidence: float | None = None`, `regime_weight_modifier: float | None = None`.
- [ ] WHEN `_row_to_record()` in `SignalRepository` processes a row THEN it SHALL handle backward compatibility for the new columns using the existing Phase 3 optional-column pattern.

---

### REQ-MRD-030: Market Regime Repository

**User Story:** As a developer, I want a `MarketRegimeRepository` following the existing repository pattern, so that regime classification data access is consistent with the rest of the codebase.

**Priority:** P0
**Dependencies:** REQ-MRD-027
**Components affected:** New `backend/signalpilot/db/regime_repo.py`

#### Acceptance Criteria

- [ ] WHEN the `MarketRegimeRepository` is instantiated THEN it SHALL accept an `aiosqlite.Connection` as its constructor parameter, following the same pattern as `SignalRepository`, `TradeRepository`, and other existing repositories.
- [ ] WHEN `insert_classification(classification_data)` is called THEN it SHALL insert a row into the `market_regimes` table with all classification inputs, scores, and derived values.
- [ ] WHEN `get_today_classifications()` is called THEN it SHALL return all regime classification rows for the current IST date, ordered by `classification_time` ascending.
- [ ] WHEN `get_regime_history(days)` is called THEN it SHALL return the most recent classifications for the specified number of trading days, one per day (latest classification per day), ordered by `regime_date` descending.
- [ ] WHEN any repository method executes THEN it SHALL use async operations via `aiosqlite`.

---

### REQ-MRD-031: Regime Performance Repository

**User Story:** As a developer, I want a `RegimePerformanceRepository` for tracking strategy outcomes per regime, so that regime effectiveness can be measured over time.

**Priority:** P1
**Dependencies:** REQ-MRD-028
**Components affected:** New `backend/signalpilot/db/regime_performance_repo.py`

#### Acceptance Criteria

- [ ] WHEN the `RegimePerformanceRepository` is instantiated THEN it SHALL accept an `aiosqlite.Connection` as its constructor parameter.
- [ ] WHEN `insert_daily_performance(regime_date, regime, strategy, stats)` is called THEN it SHALL insert a row into the `regime_performance` table with the day's metrics for that strategy under that regime.
- [ ] WHEN `get_performance_by_regime(regime, days)` is called THEN it SHALL return aggregated performance metrics (total signals, wins, losses, P&L, win rate) for the specified regime over the given number of days.
- [ ] WHEN `get_performance_summary(days)` is called THEN it SHALL return a summary table of performance by regime and strategy for the dashboard and REGIME HISTORY command.
- [ ] WHEN any repository method executes THEN it SHALL use async operations via `aiosqlite`.

---

## 8. Telegram Commands

### REQ-MRD-032: REGIME Command

**User Story:** As a trader, I want to send `REGIME` to see the current market regime classification with all inputs and derived adjustments, so that I understand how the system is currently interpreting market conditions.

**Priority:** P0
**Dependencies:** REQ-MRD-008, REQ-MRD-014
**Components affected:** `backend/signalpilot/telegram/bot.py`

#### Acceptance Criteria

- [ ] WHEN a user sends `REGIME` THEN the bot SHALL reply with the current regime classification including: the regime name and confidence level, all raw input values (VIX, gap%, range%, alignment, SGX direction, S&P 500 change, FII/DII flows), the three regime scores (trending, ranging, volatile), and the active adjustments (strategy weights, min star rating, position modifier, max positions).
- [ ] IF no classification has been performed yet today (before 9:30 AM) THEN the bot SHALL reply indicating that classification will occur at 9:30 AM and show DEFAULT regime values.
- [ ] WHEN the REGIME command is handled THEN it SHALL be registered as a `MessageHandler` in `SignalPilotBot.start()` following the same pattern as existing commands (STATUS, JOURNAL, CAPITAL).

---

### REQ-MRD-033: REGIME HISTORY Command

**User Story:** As a trader, I want to send `REGIME HISTORY` to see the last 20 trading days' regimes with strategy performance per regime, so that I can evaluate how well the regime system is working.

**Priority:** P1
**Dependencies:** REQ-MRD-030, REQ-MRD-031
**Components affected:** `backend/signalpilot/telegram/bot.py`

#### Acceptance Criteria

- [ ] WHEN a user sends `REGIME HISTORY` THEN the bot SHALL query `MarketRegimeRepository.get_regime_history(20)` and `RegimePerformanceRepository.get_performance_summary(20)` and reply with a formatted summary showing each day's date, regime, confidence, and per-strategy win rate and P&L.
- [ ] WHEN regime history is displayed THEN it SHALL include aggregate statistics: distribution of regimes (e.g., "8 TRENDING, 7 RANGING, 5 VOLATILE"), average win rate per regime, and total P&L per regime.
- [ ] IF fewer than 20 trading days of data are available THEN the bot SHALL display all available data with a note indicating the data range.

---

### REQ-MRD-034: REGIME OVERRIDE Command

**User Story:** As an experienced trader, I want to manually override the regime classification using `REGIME OVERRIDE TRENDING`, so that I can apply my own market judgment when I disagree with the system's classification.

**Priority:** P2
**Dependencies:** REQ-MRD-014
**Components affected:** `backend/signalpilot/telegram/bot.py`, `backend/signalpilot/intelligence/regime_classifier.py`

#### Acceptance Criteria

- [ ] WHEN a user sends `REGIME OVERRIDE {REGIME}` (where REGIME is TRENDING, RANGING, or VOLATILE) THEN the system SHALL update the in-memory cached regime to the specified value with confidence 1.0.
- [ ] WHEN a regime override is applied THEN the system SHALL recalculate all derived modifiers (strategy weights, min stars, position modifier, max positions) based on the overridden regime.
- [ ] WHEN a regime override is applied THEN the next pipeline cycle SHALL pick up the overridden regime via `RegimeContextStage`.
- [ ] WHEN a regime override is applied THEN it SHALL reset at the next re-classification checkpoint, reverting to the algorithm's classification.
- [ ] WHEN the override is applied THEN the bot SHALL reply confirming the override, showing the new adjustments, and warning that the override resets at the next checkpoint.
- [ ] IF an invalid regime name is provided THEN the bot SHALL reply with an error message listing the valid options (TRENDING, RANGING, VOLATILE).

---

### REQ-MRD-035: VIX Command

**User Story:** As a trader, I want to send `VIX` to see the current India VIX value and its interpretation, so that I can quickly gauge market volatility without leaving the Telegram interface.

**Priority:** P1
**Dependencies:** REQ-MRD-001
**Components affected:** `backend/signalpilot/telegram/bot.py`

#### Acceptance Criteria

- [ ] WHEN a user sends `VIX` THEN the bot SHALL reply with the current India VIX value, the VIX score used in classification (e.g., 0.3), and a plain-language interpretation (e.g., "Low VIX (14.2) -- calm market expected, breakout strategies favored").
- [ ] WHEN the VIX interpretation is displayed THEN it SHALL use the same thresholds as the classification algorithm: <12 "Very calm", 12-14 "Normal", 14-18 "Slightly elevated", 18-22 "High", >=22 "Very high".
- [ ] IF VIX data is unavailable THEN the bot SHALL reply indicating that VIX data could not be fetched and to try again later.

---

### REQ-MRD-036: MORNING Command

**User Story:** As a trader, I want to send `MORNING` to re-send today's morning brief, so that I can review the pre-market analysis at any time during the day.

**Priority:** P2
**Dependencies:** REQ-MRD-025
**Components affected:** `backend/signalpilot/telegram/bot.py`

#### Acceptance Criteria

- [ ] WHEN a user sends `MORNING` THEN the bot SHALL re-generate and send the morning brief with the same format as the 8:45 AM automated brief, using current cached data.
- [ ] IF the morning brief data has not been collected yet today (before 8:45 AM) THEN the bot SHALL reply indicating that the morning brief will be available after 8:45 AM.
- [ ] WHEN the MORNING command is handled THEN it SHALL be registered as a `MessageHandler` following the existing command pattern.

---

## 9. Telegram Notifications

### REQ-MRD-037: Classification Notification

**User Story:** As a trader, I want to receive a Telegram notification when the regime is classified at 9:30 AM, so that I know which regime is active and how strategy weights have been adjusted.

**Priority:** P0
**Dependencies:** REQ-MRD-008
**Components affected:** `backend/signalpilot/intelligence/regime_classifier.py`, `backend/signalpilot/telegram/bot.py`

#### Acceptance Criteria

- [ ] WHEN the initial regime classification completes at 9:30 AM THEN the system SHALL send a Telegram notification via `bot.send_alert()` containing: the classified regime and confidence level, key inputs (VIX, gap%, first-15-min range/direction, alignment), strategy weight adjustments showing old and new percentages, and the active min star rating, position modifier, and max positions.
- [ ] WHEN the classification notification is formatted THEN it SHALL follow the existing structured message style used by other SignalPilot notifications.

---

### REQ-MRD-038: Re-Classification Notification

**User Story:** As a trader, I want to receive a Telegram notification when the regime is re-classified intraday, so that I am aware of the mid-day adjustment and its impact on strategy weights.

**Priority:** P0
**Dependencies:** REQ-MRD-024
**Components affected:** `backend/signalpilot/intelligence/regime_classifier.py`, `backend/signalpilot/telegram/bot.py`

#### Acceptance Criteria

- [ ] WHEN a regime re-classification occurs THEN the system SHALL send a Telegram notification via `bot.send_alert()` containing: the previous regime and its confidence, the updated regime and its confidence, the specific trigger that caused re-classification (e.g., "VIX jumped from 14.2 to 18.8 (+32%)"), the updated strategy weight adjustments showing before and after, and a note that existing positions are not affected.
- [ ] WHEN the re-classification notification is formatted THEN it SHALL clearly distinguish itself from the initial classification notification (e.g., header: "REGIME UPDATE").

---

## 10. API Endpoints (FastAPI Dashboard)

### REQ-MRD-039: Current Regime API

**User Story:** As a dashboard user, I want an API endpoint to retrieve the current regime classification with all inputs and scores, so that the dashboard can display the live regime status.

**Priority:** P1
**Dependencies:** REQ-MRD-014, REQ-MRD-030
**Components affected:** New `backend/signalpilot/dashboard/routes/regime.py`, `backend/signalpilot/dashboard/app.py`

#### Acceptance Criteria

- [ ] WHEN a GET request is made to `/api/v1/regime/current` THEN the API SHALL return JSON containing the current regime, confidence, all three regime scores, all raw inputs, and the active modifiers (strategy weights, min stars, position modifier, max positions).
- [ ] IF no classification has been performed today THEN the API SHALL return a 200 response with `regime: null` and DEFAULT modifier values.
- [ ] WHEN the route module is created THEN it SHALL be registered in `backend/signalpilot/dashboard/app.py` following the same pattern as existing route modules.

---

### REQ-MRD-040: Regime History API

**User Story:** As a dashboard user, I want an API endpoint to retrieve the regime classification history, so that the dashboard can display a historical regime calendar.

**Priority:** P1
**Dependencies:** REQ-MRD-030
**Components affected:** `backend/signalpilot/dashboard/routes/regime.py`

#### Acceptance Criteria

- [ ] WHEN a GET request is made to `/api/v1/regime/history` THEN the API SHALL return JSON containing the regime classifications for the last 30 days (configurable via `days` query parameter), including date, regime, confidence, and key inputs.
- [ ] WHEN regime history is returned THEN each entry SHALL represent the final classification for that day (accounting for re-classifications).
- [ ] IF no history is available THEN the API SHALL return a 200 response with an empty list.

---

### REQ-MRD-041: Regime Performance API

**User Story:** As a dashboard user, I want an API endpoint to retrieve strategy performance broken down by regime, so that the dashboard can show a regime vs. performance correlation chart.

**Priority:** P1
**Dependencies:** REQ-MRD-031
**Components affected:** `backend/signalpilot/dashboard/routes/regime.py`

#### Acceptance Criteria

- [ ] WHEN a GET request is made to `/api/v1/regime/performance` THEN the API SHALL return JSON containing win rate, total signals, wins, losses, and P&L for each strategy grouped by regime.
- [ ] WHEN performance data is returned THEN it SHALL support an optional `days` query parameter (default 30) to control the lookback window.
- [ ] IF no performance data is available THEN the API SHALL return a 200 response with empty aggregations.

---

### REQ-MRD-042: Regime Override API

**User Story:** As a dashboard user, I want an API endpoint to manually override the regime classification, so that the dashboard can offer the same override capability as the Telegram REGIME OVERRIDE command.

**Priority:** P2
**Dependencies:** REQ-MRD-034
**Components affected:** `backend/signalpilot/dashboard/routes/regime.py`

#### Acceptance Criteria

- [ ] WHEN a POST request is made to `/api/v1/regime/override` with a JSON body `{"regime": "TRENDING"}` THEN the API SHALL update the in-memory cached regime and return the updated classification with recalculated modifiers.
- [ ] IF the provided regime value is not one of `"TRENDING"`, `"RANGING"`, or `"VOLATILE"` THEN the API SHALL return a 400 response with an error message.
- [ ] WHEN the override is applied THEN it SHALL behave identically to the Telegram REGIME OVERRIDE command (resets at next checkpoint).

---

### REQ-MRD-043: Morning Brief API

**User Story:** As a dashboard user, I want an API endpoint to retrieve today's morning brief data, so that the dashboard can display the pre-market analysis.

**Priority:** P2
**Dependencies:** REQ-MRD-025
**Components affected:** `backend/signalpilot/dashboard/routes/regime.py`

#### Acceptance Criteria

- [ ] WHEN a GET request is made to `/api/v1/morning-brief` THEN the API SHALL return JSON containing the morning brief data: global cues (S&P 500, Nasdaq, Asian markets, SGX Nifty), India context (VIX, FII/DII), regime prediction, and watchlist alerts.
- [ ] IF the morning brief has not been generated yet today THEN the API SHALL return a 200 response with `generated: false` and empty sections.

---

## 11. Configuration

### REQ-MRD-044: AppConfig Regime Detection Parameters

**User Story:** As a developer, I want all regime detection thresholds, weight matrices, and parameters configurable via `AppConfig` and `.env`, so that tuning can be done without code changes.

**Priority:** P0
**Dependencies:** Phase 1 `AppConfig` (`backend/signalpilot/config.py`)
**Components affected:** `backend/signalpilot/config.py`

#### Acceptance Criteria

- [ ] WHEN Phase 4 Market Regime Detection is deployed THEN `AppConfig` SHALL include the following new fields with specified defaults:
  - `regime_enabled` (bool, default `True`) -- feature kill switch
  - `regime_shadow_mode` (bool, default `True`) -- classify and log but do not adjust weights
  - `regime_confidence_threshold` (float, default `0.55`) -- high vs low confidence boundary
  - `regime_max_reclassifications` (int, default `2`) -- max re-classifications per day
  - `regime_vix_spike_threshold` (float, default `0.15`) -- 15% VIX increase triggers re-classification
  - `regime_roundtrip_threshold` (float, default `0.003`) -- 0.3% of open for ranging detection
  - `regime_trending_weights` (dict or JSON str) -- strategy weights for TRENDING regime
  - `regime_ranging_weights` (dict or JSON str) -- strategy weights for RANGING regime
  - `regime_volatile_weights` (dict or JSON str) -- strategy weights for VOLATILE regime
  - `regime_trending_position_modifier` (float, default `1.0`)
  - `regime_ranging_position_modifier` (float, default `0.85`)
  - `regime_volatile_position_modifier` (float, default `0.65`)
  - `regime_trending_max_positions` (int, default `8`)
  - `regime_ranging_max_positions` (int, default `6`)
  - `regime_volatile_max_positions` (int, default `4`)
- [ ] WHEN any regime detection config parameter is changed via `.env` THEN the system SHALL use the updated value on the next application restart.

---

### REQ-MRD-045: Shadow Mode

**User Story:** As a developer, I want a shadow mode where the system classifies and logs regimes but does not apply weight adjustments, so that accuracy can be validated for the first 2 weeks before going live.

**Priority:** P0
**Dependencies:** REQ-MRD-044
**Components affected:** `backend/signalpilot/pipeline/stages/regime_context.py`, `backend/signalpilot/intelligence/regime_classifier.py`

#### Acceptance Criteria

- [ ] WHEN `regime_shadow_mode` is `True` in `AppConfig` THEN the `RegimeContextStage` SHALL still read the cached regime and set `ctx.regime` and `ctx.regime_confidence` for logging and persistence, but SHALL set all modifier fields to their neutral defaults (`regime_min_stars=3`, `regime_position_modifier=1.0`, `regime_max_positions=None`, `regime_strategy_weights=None`).
- [ ] WHEN shadow mode is active THEN classifications SHALL still be persisted to the `market_regimes` table and notifications SHALL still be sent via Telegram, so that the user can observe the system's recommendations without them being applied.
- [ ] WHEN shadow mode is active THEN the classification notification SHALL include a note indicating "SHADOW MODE -- weights not applied".
- [ ] WHEN `regime_shadow_mode` is toggled from `True` to `False` THEN the system SHALL apply regime modifiers on the next application restart.

---

### REQ-MRD-046: Feature Kill Switch

**User Story:** As a developer, I want a single configuration flag to completely disable the regime detection feature, so that the feature can be turned off instantly in production if it causes issues.

**Priority:** P0
**Dependencies:** REQ-MRD-044
**Components affected:** `backend/signalpilot/pipeline/stages/regime_context.py`, `backend/signalpilot/config.py`

#### Acceptance Criteria

- [ ] WHEN `regime_enabled` is `False` in `AppConfig` THEN the `RegimeContextStage.process()` method SHALL return the `ScanContext` unchanged without reading the cached regime or setting any modifier fields.
- [ ] WHEN `regime_enabled` is `False` THEN the classification scheduler job, re-classification checkpoint jobs, and morning brief job SHALL skip execution and log an info message.
- [ ] WHEN `regime_enabled` is toggled from `False` to `True` THEN the system SHALL resume normal operation on the next application restart, with the 9:30 AM classification job kicking off regime detection.

---

## 12. Regime-Aware Signal Formatting

### REQ-MRD-047: Signal Message Regime Badge

**User Story:** As a trader, I want delivered signals to include a regime badge showing the current market regime, so that I have context about the market conditions under which the signal was generated.

**Priority:** P1
**Dependencies:** REQ-MRD-021
**Components affected:** `backend/signalpilot/telegram/formatters.py`

#### Acceptance Criteria

- [ ] WHEN `format_signal_message()` is called AND `ctx.regime` is not `None` THEN the formatted message SHALL include a regime badge (e.g., "Market: TRENDING (72% confidence)") in the signal details section.
- [ ] WHEN the regime is VOLATILE THEN the badge SHALL include a cautionary note (e.g., "Defensive sizing applied").
- [ ] WHEN `ctx.regime` is `None` THEN the formatter SHALL not include any regime badge, preserving backward compatibility.

---

## 13. Integration with Existing Capital Allocation

### REQ-MRD-048: Regime Weight Layering on CapitalAllocator

**User Story:** As a developer, I want regime weights to layer on top of the existing `CapitalAllocator` long-term performance weights, so that both short-term market context and long-term strategy performance are considered.

**Priority:** P0
**Dependencies:** REQ-MRD-015, existing `CapitalAllocator`
**Components affected:** `backend/signalpilot/scoring/capital_allocator.py` or `backend/signalpilot/pipeline/stages/risk_sizing.py`

#### Acceptance Criteria

- [ ] WHEN both CapitalAllocator weights and regime strategy weights are available THEN the final weight for each strategy SHALL be computed as `CapitalAllocator_weight * regime_strategy_weight_adjustment`.
- [ ] WHEN the regime is DEFAULT (no classification) or regime strategy weights are `None` THEN the CapitalAllocator weights SHALL be used without modification.
- [ ] WHEN regime weights are applied THEN they SHALL NOT replace or override the CapitalAllocator -- they modify its output for the current session only.

---

## 14. Data Models

### REQ-MRD-049: RegimeClassification Dataclass

**User Story:** As a developer, I want a `RegimeClassification` dataclass to represent the classification result, so that the classifier, pipeline stage, repository, and formatters share a common typed contract.

**Priority:** P0
**Dependencies:** None
**Components affected:** `backend/signalpilot/db/models.py` or `backend/signalpilot/intelligence/regime_classifier.py`

#### Acceptance Criteria

- [ ] WHEN `RegimeClassification` is defined THEN it SHALL be a Python dataclass with fields: `regime` (str), `confidence` (float), `trending_score` (float), `ranging_score` (float), `volatile_score` (float), `india_vix` (float | None), `nifty_gap_pct` (float | None), `nifty_first_15_range_pct` (float | None), `nifty_first_15_direction` (str | None), `directional_alignment` (float | None), `sp500_change_pct` (float | None), `sgx_direction` (str | None), `fii_net_crores` (float | None), `dii_net_crores` (float | None), `strategy_weights` (dict[str, float]), `min_star_rating` (int), `max_positions` (int), `position_size_modifier` (float), `is_reclassification` (bool), `previous_regime` (str | None), and `classified_at` (datetime).
- [ ] WHEN `RegimeClassification` is used in the in-memory cache THEN the cache key SHALL be the current IST date (date object) and the value SHALL be a `RegimeClassification` instance (latest classification for the day).

---

### REQ-MRD-050: RegimePerformanceRecord Dataclass

**User Story:** As a developer, I want a `RegimePerformanceRecord` dataclass to represent daily strategy performance under a specific regime, for database persistence and API responses.

**Priority:** P1
**Dependencies:** None
**Components affected:** `backend/signalpilot/db/models.py`

#### Acceptance Criteria

- [ ] WHEN `RegimePerformanceRecord` is defined THEN it SHALL be a Python dataclass with fields: `regime_date` (date), `regime` (str), `strategy` (str), `signals_generated` (int), `signals_taken` (int), `wins` (int), `losses` (int), `pnl` (float), and `win_rate` (float | None).

---

## 15. Testing

### REQ-MRD-051: Unit Test Coverage

**User Story:** As a developer, I want comprehensive unit tests for all new components, so that classification logic, data collection, pipeline integration, and re-classification rules are verified in isolation.

**Priority:** P0
**Dependencies:** All REQ-MRD requirements
**Components affected:** `tests/test_intelligence/`, `tests/test_db/`, `tests/test_pipeline/`

#### Acceptance Criteria

- [ ] WHEN unit tests are run THEN there SHALL be tests covering: `RegimeDataCollector` (VIX fetch, gap calculation, range/direction, global cues, graceful degradation for each data source failure), `MarketRegimeClassifier` (TRENDING classification with high/low confidence, RANGING classification with high/low confidence, VOLATILE classification with high/low confidence, DEFAULT regime when no data, VIX score mapping for all five brackets, gap score mapping for all four brackets, range score mapping for all four brackets, directional alignment with full agreement/partial agreement/no agreement, confidence calculation, in-memory cache read/write), `RegimeContextStage` (setting all six context fields from cache, DEFAULT values when no classification, shadow mode neutral defaults, feature disabled pass-through), `RankingStage` min-stars filter (filtering at threshold 4 and 5, no-op at threshold 3), `RiskSizingStage` position modifier (1.0x no-op, 0.85x and 0.65x applied correctly, max_positions override), `MarketRegimeRepository` (insert, get_today, get_history), `RegimePerformanceRepository` (insert, get_by_regime, get_summary), and re-classification rules (severity upgrade only, max 2 per day, VIX spike trigger, direction reversal trigger, round-trip RANGING trigger).
- [ ] WHEN async tests are written THEN they SHALL use `async def` with the project's `asyncio_mode="auto"` configuration.
- [ ] WHEN tests mock external dependencies THEN they SHALL use the existing `conftest.py` fixture pattern (in-memory SQLite `db` fixture, `app_config` fixture).

---

### REQ-MRD-052: Integration Test Coverage

**User Story:** As a developer, I want integration tests that verify the end-to-end flow from data collection through classification to pipeline modifier application, so that the full feature integration is validated.

**Priority:** P1
**Dependencies:** REQ-MRD-019, REQ-MRD-021, REQ-MRD-051
**Components affected:** `tests/test_integration/`

#### Acceptance Criteria

- [ ] WHEN integration tests are run THEN there SHALL be tests covering: a full pipeline cycle with TRENDING regime where strategy weights, min stars, and position sizing reflect TRENDING modifiers; a full pipeline cycle with VOLATILE regime where min stars is set to 5 and position sizes are reduced by 35%; a pipeline cycle with no classification (before 9:30 AM) where all stages behave identically to the pre-feature baseline; shadow mode where classification is logged but modifiers are neutral; a re-classification scenario where the regime upgrades from TRENDING to VOLATILE mid-day and subsequent signals reflect the updated modifiers; and a regime override via the Telegram command that is picked up by the next pipeline cycle.
- [ ] WHEN integration tests exercise the pipeline THEN they SHALL use the `make_app()` helper from `tests/test_integration/conftest.py` to construct a fully wired application with mock external dependencies.
- [ ] WHEN integration tests verify persistence THEN they SHALL check that the `signals` table contains the correct `market_regime`, `regime_confidence`, and `regime_weight_modifier` values, and that the `market_regimes` table contains the classification record.

---

## 16. Performance

### REQ-MRD-053: Pipeline Cycle Overhead

**User Story:** As a developer, I want the regime context stage to add negligible overhead to the 1-second scan loop, so that signal detection latency is unaffected.

**Priority:** P0
**Dependencies:** REQ-MRD-019
**Components affected:** `backend/signalpilot/pipeline/stages/regime_context.py`

#### Acceptance Criteria

- [ ] WHEN the `RegimeContextStage` processes a context THEN total execution time SHALL be under 1ms per cycle (pure in-memory cache read, no network I/O, no database queries).
- [ ] WHEN the classification algorithm runs (at 9:30 AM or re-classification checkpoints) THEN total execution time SHALL be under 200ms (pure math on float inputs).
- [ ] WHEN the morning brief data fetch runs (at 8:45 AM) THEN total execution time SHALL be under 5 seconds (network I/O for VIX, SGX, S&P 500, FII/DII).
- [ ] WHEN the `RegimeContextStage` runs THEN it SHALL NOT create any new async tasks that perform network I/O or database queries within the scan loop context.
