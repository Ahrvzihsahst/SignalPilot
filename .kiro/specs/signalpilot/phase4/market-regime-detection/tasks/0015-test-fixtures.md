# Task 15: Test Fixtures and Shared Setup

## Description
Add shared test fixtures to `conftest.py` for regime detection tests: `sample_regime_inputs`, `sample_regime_classification`, `regime_repo`, `regime_perf_repo` fixtures. Ensure the in-memory `db` fixture runs the regime detection migration.

## Prerequisites
Task 1 (Data Models), Task 2 (Repository Layer)

## Requirement Coverage
REQ-MRD-051

## Files to Modify
- `tests/conftest.py`

## Subtasks

### 15.1 Add shared test fixtures to `backend/tests/conftest.py`

- [ ] Add `sample_regime_inputs` fixture returning a `RegimeInputs` with trending-day values (india_vix=14.2, nifty_gap_pct=1.2, nifty_first_15_range_pct=0.6, nifty_first_15_direction="UP", prev_day_range_pct=1.5, fii_net_crores=-1200.0, dii_net_crores=1800.0, sgx_direction="UP", sp500_change_pct=0.85) as specified in Design Section 8.3
- [ ] Add `sample_regime_classification` fixture returning a TRENDING `RegimeClassification` with values from Design Section 8.3 (regime="TRENDING", confidence=0.72, trending_score=0.55, strategy_weights={"gap_go": 45, "orb": 35, "vwap": 20}, etc.)
- [ ] Add `regime_repo` fixture using the in-memory SQLite `db` fixture with market_regimes table created
- [ ] Add `regime_perf_repo` fixture using the in-memory SQLite `db` fixture with regime_performance table created
- [ ] Ensure the in-memory `db` fixture runs `_run_regime_detection_migration()` to create the new tables
- [ ] Add imports for `RegimeInputs`, `RegimeClassification`, `MarketRegimeRepository`, `RegimePerformanceRepository`
- Requirement coverage: REQ-MRD-051
