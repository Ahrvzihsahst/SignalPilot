# Task 5: Market Regime Classifier

## Description
Implement `MarketRegimeClassifier` in `backend/signalpilot/intelligence/regime_classifier.py` -- the core classification engine. This includes the four component score functions (VIX, gap, range, alignment), the composite score formula, winner-takes-all selection, confidence calculation, modifier derivation, in-memory cache management, re-classification logic with severity-upgrade-only rule, and manual override support.

## Prerequisites
Task 1 (Data Models -- needs `RegimeClassification`), Task 2 (Repository -- needs `MarketRegimeRepository`), Task 3 (Configuration -- needs AppConfig fields), Task 4 (Data Collector -- needs `RegimeDataCollector`)

## Requirement Coverage
REQ-MRD-008, REQ-MRD-009, REQ-MRD-010, REQ-MRD-011, REQ-MRD-012, REQ-MRD-013, REQ-MRD-014, REQ-MRD-015, REQ-MRD-016, REQ-MRD-017, REQ-MRD-018, REQ-MRD-023, REQ-MRD-024, REQ-MRD-034

## Files to Create
- `signalpilot/intelligence/regime_classifier.py`

## Subtasks

### 5.1 Implement component score static methods

- [ ] `_compute_vix_score(vix: float | None) -> float` mapping VIX to [-0.5, 1.0]: <12 -> -0.5, 12-14 -> 0.0, 14-18 -> 0.3, 18-22 -> 0.6, >=22 -> 1.0, None -> 0.0
- [ ] `_compute_gap_score(nifty_gap_pct: float | None) -> float` mapping abs(gap) to [-0.5, 1.0]: >1.5% -> 1.0, 0.8-1.5% -> 0.6, 0.3-0.8% -> 0.2, <=0.3% -> -0.5, None -> 0.0
- [ ] `_compute_range_score(first_15_range_pct: float | None) -> float` mapping range to [-0.5, 1.0]: >1.0% -> 1.0, 0.5-1.0% -> 0.5, 0.2-0.5% -> 0.0, <=0.2% -> -0.5, None -> 0.0
- [ ] `_compute_alignment(nifty_gap_pct, first_15_direction, sgx_direction, sp500_change_pct) -> float` computing `abs(sum(directions)) / 4` with each direction as +1/-1/0, missing inputs default to 0
- Requirement coverage: REQ-MRD-009, REQ-MRD-010, REQ-MRD-011, REQ-MRD-012

### 5.2 Implement classification core logic

- [ ] `_classify_from_scores(vix_score, gap_score, range_score, alignment, inputs, ...) -> RegimeClassification` computing:
  - `trending_score = (gap * 0.35) + (alignment * 0.30) + (range * 0.20) + ((1 - vix) * 0.15)`
  - `ranging_score = ((-gap) * 0.35) + ((-range) * 0.30) + ((1 - vix) * 0.35)`
  - `volatile_score = (vix * 0.40) + (range * 0.30) + ((1 - alignment) * 0.30)`
  - Winner-takes-all selection
  - Confidence = selected_score / sum(abs(all_scores)), clamped [0.0, 1.0], fallback 0.33
- [ ] `_get_regime_modifiers(regime, confidence) -> dict` deriving strategy_weights, min_star_rating, position_size_modifier, max_positions from AppConfig based on regime and confidence level (high vs low relative to `regime_confidence_threshold`)
- Requirement coverage: REQ-MRD-008, REQ-MRD-013, REQ-MRD-015, REQ-MRD-016, REQ-MRD-017, REQ-MRD-018

### 5.3 Implement classify(), cache, and re-classification

- [ ] Constructor accepts `data_collector` (RegimeDataCollector), `regime_repo` (MarketRegimeRepository), `config` (AppConfig). Initialize `_cache: dict[date, RegimeClassification]`, `_reclass_count: dict[date, int]`, `_morning_vix: dict[date, float]`
- [ ] `async def classify() -> RegimeClassification`: collect inputs -> compute scores -> classify -> cache result keyed by IST date -> persist to DB -> store morning VIX for spike detection -> return classification
- [ ] `def get_cached_regime(for_date=None) -> RegimeClassification | None`: return cached classification for the given (or today's) date. Must be <1ms
- [ ] `async def check_reclassify(checkpoint: str) -> RegimeClassification | None`: evaluate trigger conditions per checkpoint (11:00=VIX spike >15%, 13:00=direction reversal, 14:30=round-trip within 0.3%). Enforce severity-only upgrades (`_SEVERITY_ORDER`), max 2 per day. Update cache immediately if triggered, persist with `is_reclassification=True`. Return new classification or None
- [ ] `def apply_override(regime: str) -> RegimeClassification`: set cached regime to specified value with confidence=1.0, recalculate modifiers
- [ ] `def reset_daily() -> None`: clear re-classification count for the new day
- Requirement coverage: REQ-MRD-008, REQ-MRD-014, REQ-MRD-023, REQ-MRD-024, REQ-MRD-034

### 5.4 Write unit tests

- [ ] Write tests in `backend/tests/test_intelligence/test_regime_classifier.py` covering:
  - VIX score: all five brackets (<12, 12-14, 14-18, 18-22, >=22) and None input
  - Gap score: all four brackets (>1.5%, 0.8-1.5%, 0.3-0.8%, <=0.3%) and None input
  - Range score: all four brackets (>1.0%, 0.5-1.0%, 0.2-0.5%, <=0.2%) and None input
  - Alignment: full agreement (1.0), partial (intermediate), no agreement (0.0), missing inputs (default 0, denominator stays 4)
  - Classification: TRENDING with high conf, RANGING with high conf, VOLATILE with high conf
  - Default when all inputs None (low confidence)
  - Confidence calculation: normal case + zero scores fallback to 0.33
  - In-memory cache: write and read, keyed by date, stale entries not returned
  - Modifiers: TRENDING high/low conf, RANGING high/low conf, VOLATILE high/low conf
  - Re-classification: severity upgrade allowed (TRENDING->VOLATILE), severity downgrade blocked (VOLATILE->TRENDING), max 2 per day enforced
  - Re-classification triggers: VIX spike >15%, direction reversal, round-trip within 0.3%
  - Manual override: sets cache with confidence 1.0
- Requirement coverage: REQ-MRD-008 through REQ-MRD-018, REQ-MRD-023, REQ-MRD-024, REQ-MRD-034, REQ-MRD-051
