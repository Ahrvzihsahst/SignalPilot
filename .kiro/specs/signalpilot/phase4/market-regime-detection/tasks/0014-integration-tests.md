# Task 14: Integration Tests

## Description
Write integration tests that verify the end-to-end flow from regime classification through pipeline modifier application, signal persistence with regime metadata, re-classification mid-day, shadow mode, and regime override. These tests exercise the full pipeline with mock external dependencies.

## Prerequisites
Task 1-12 (all component implementations)

## Requirement Coverage
REQ-MRD-052

## Files to Create
- `tests/test_integration/test_regime_pipeline.py`

## Subtasks

### 14.1 Write pipeline integration tests

- [ ] Write tests in `backend/tests/test_integration/test_regime_pipeline.py` using `make_app()` helper with mock external dependencies:
  - Full pipeline cycle with TRENDING regime: strategy weights set to Gap&Go 45%, ORB 35%, VWAP 20%, min_stars=3, normal sizing (modifier=1.0), max_positions=8
  - Full pipeline cycle with VOLATILE regime: min_stars=5 filters low-star signals, position sizes reduced by 35% (modifier=0.65), max_positions=4
  - Full pipeline cycle with RANGING regime: weights adjusted to Gap&Go 20%, ORB 30%, VWAP 50%, modifier=0.85, max_positions=6
  - Pipeline before 9:30 AM (no classification): all stages behave identically to pre-feature baseline, no regime modifiers applied
  - Shadow mode: classification runs and populates ctx.regime/ctx.regime_confidence, but all modifiers remain neutral (min_stars=3, modifier=1.0, max_positions=None)
  - Re-classification mid-day: regime upgrades from TRENDING to VOLATILE, next pipeline cycle picks up VOLATILE modifiers
  - Regime override via `apply_override()`: overridden regime reflected in next pipeline cycle
  - Signal record persistence: verify `signals` table contains correct `market_regime`, `regime_confidence`, `regime_weight_modifier` values
  - Classification persistence: verify `market_regimes` table contains the classification record with all inputs and scores
  - Kill switch (`regime_enabled=False`): no regime processing, all regime columns NULL on signals
- Requirement coverage: REQ-MRD-052
