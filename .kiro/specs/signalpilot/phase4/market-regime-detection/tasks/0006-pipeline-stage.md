# Task 6: RegimeContextStage Pipeline Stage

## Description
Implement `RegimeContextStage` as a new pipeline stage (stage 2, between CircuitBreakerGateStage and StrategyEvalStage). The stage reads the cached regime classification from `MarketRegimeClassifier` and sets six modifier fields on `ScanContext`. In shadow mode, it sets regime and confidence for logging but leaves modifiers at neutral defaults. When the feature is disabled, it returns the context unchanged.

## Prerequisites
Task 1 (Data Models -- ScanContext fields), Task 5 (Classifier -- needs `get_cached_regime()`)

## Requirement Coverage
REQ-MRD-019, REQ-MRD-045, REQ-MRD-046, REQ-MRD-053

## Files to Create
- `signalpilot/pipeline/stages/regime_context.py`

## Subtasks

### 6.1 Implement `backend/signalpilot/pipeline/stages/regime_context.py`

- [ ] Create `RegimeContextStage` class implementing the `PipelineStage` protocol as specified in Design Section 3.3
- [ ] Constructor accepts: `regime_classifier` (MarketRegimeClassifier), `config` (AppConfig)
- [ ] `name` property returns `"RegimeContext"`
- [ ] `process(ctx)` logic:
  1. Return ctx unchanged if `config.regime_enabled` is False (kill switch)
  2. Read cached regime via `self._classifier.get_cached_regime()` -- in-memory dict read, <1ms
  3. If no classification (None), return ctx unchanged (all fields already have neutral defaults)
  4. Always set `ctx.regime` and `ctx.regime_confidence` (for logging/persistence even in shadow mode)
  5. If `config.regime_shadow_mode` is True: log debug message, return ctx without setting modifiers
  6. Set `ctx.regime_min_stars`, `ctx.regime_position_modifier`, `ctx.regime_max_positions`, `ctx.regime_strategy_weights` from classification
- [ ] Log regime at debug level for each cycle
- Requirement coverage: REQ-MRD-019, REQ-MRD-045, REQ-MRD-046, REQ-MRD-053

### 6.2 Write unit tests

- [ ] Write tests in `backend/tests/test_pipeline/test_regime_context_stage.py` covering:
  - Sets all six context fields from cached classification
  - Default values when no classification exists (before 9:30 AM) -- ctx fields unchanged
  - Shadow mode: regime and confidence set, but modifiers remain neutral (min_stars=3, modifier=1.0, max_positions=None, strategy_weights=None)
  - Feature disabled (`regime_enabled=False`): ctx returned completely unchanged
  - Execution time benchmark: stage completes in under 1ms (pure dict lookup + attribute set)
  - Classifier returns different regimes on different dates -- correct date used
- Requirement coverage: REQ-MRD-019, REQ-MRD-045, REQ-MRD-046, REQ-MRD-053, REQ-MRD-051
