# Task 7: Existing Stage Modifications (Ranking, RiskSizing, PersistAndDeliver)

## Description
Add small regime-aware enhancements to three existing pipeline stages: `RankingStage` (min-stars filter), `RiskSizingStage` (position modifier + max positions override), and `PersistAndDeliverStage` (regime metadata persistence + signal badge data). Each modification is additive and designed as a no-op when regime is not active.

## Prerequisites
Task 1 (Data Models -- ScanContext fields, SignalRecord extensions), Task 6 (Pipeline Stage -- fields available on ctx)

## Requirement Coverage
REQ-MRD-016, REQ-MRD-017, REQ-MRD-018, REQ-MRD-021, REQ-MRD-048

## Files to Modify
- `signalpilot/pipeline/stages/ranking.py`
- `signalpilot/pipeline/stages/risk_sizing.py`
- `signalpilot/pipeline/stages/persist_and_deliver.py`

## Subtasks

### 7.1 Enhance `RankingStage` with min-stars filter

- [ ] After existing ranking logic, add 2-3 lines: if `ctx.regime_min_stars > 3`, filter `ctx.ranked_signals` to only include signals with `signal_strength >= ctx.regime_min_stars`
- [ ] Log when filtering occurs: count before vs after, threshold value
- [ ] When `regime_min_stars` is 3 (default), the condition `> 3` is False -- complete no-op
- [ ] Write tests in `backend/tests/test_pipeline/test_ranking_regime.py`:
  - min_stars=3: no filtering applied (all signals pass)
  - min_stars=4: signals with < 4 stars removed
  - min_stars=5: only 5-star signals pass
  - All signals below threshold: returns empty list
- Requirement coverage: REQ-MRD-016

### 7.2 Enhance `RiskSizingStage` with position modifier and max positions override

- [ ] Before calling `filter_and_size()`: if `ctx.regime_max_positions is not None`, create a shallow copy of `UserConfig` with `max_positions` overridden to `ctx.regime_max_positions`, use this copy for the `filter_and_size()` call
- [ ] After `filter_and_size()`: if `ctx.regime_position_modifier < 1.0`, multiply each signal's quantity by the modifier, rounding down via `int()`, ensuring at least 1 share
- [ ] Log when modifier is applied: modifier value, signal count
- [ ] When `regime_max_positions=None` and `regime_position_modifier=1.0` (defaults): neither modification activates
- [ ] Write tests in `backend/tests/test_pipeline/test_risk_sizing_regime.py`:
  - position_modifier=1.0: no change to quantities
  - position_modifier=0.85: 15% reduction applied correctly
  - position_modifier=0.65: 35% reduction, minimum 1 share enforced
  - max_positions override: regime value used instead of config
  - max_positions=None: config value used (no override)
- Requirement coverage: REQ-MRD-017, REQ-MRD-018, REQ-MRD-048

### 7.3 Enhance `PersistAndDeliverStage` with regime metadata

- [ ] In the signal persistence loop: when `ctx.regime is not None`, set `record.market_regime = ctx.regime`, `record.regime_confidence = ctx.regime_confidence`, `record.regime_weight_modifier = ctx.regime_position_modifier`
- [ ] Update the `send_signal()` call to pass `market_regime=ctx.regime` and `regime_confidence=ctx.regime_confidence` for signal badge formatting
- [ ] When `ctx.regime` is None: no metadata attached, all regime columns remain NULL
- [ ] Write tests verifying:
  - Regime metadata persisted correctly on signal records
  - No behavior change when ctx.regime is None
  - Signal delivery includes regime data for formatting
- Requirement coverage: REQ-MRD-021
