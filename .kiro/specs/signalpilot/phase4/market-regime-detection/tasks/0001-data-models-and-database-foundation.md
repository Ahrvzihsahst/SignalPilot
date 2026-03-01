# Task 1: Data Models and Database Foundation

## Description
Add `RegimeClassification` and `RegimePerformanceRecord` dataclasses to `models.py`, extend `SignalRecord` with three regime metadata columns, extend `ScanContext` with six regime fields, and create the database migration for two new tables (`market_regimes`, `regime_performance`) plus three new columns on `signals`.

## Prerequisites
None (foundational task)

## Requirement Coverage
REQ-MRD-013, REQ-MRD-020, REQ-MRD-027, REQ-MRD-028, REQ-MRD-029, REQ-MRD-049, REQ-MRD-050

## Files to Modify
- `signalpilot/db/models.py`
- `signalpilot/pipeline/context.py`
- `signalpilot/db/database.py`

## Subtasks

### 1.1 Add new dataclasses to `backend/signalpilot/db/models.py`

- [ ] Add `RegimeClassification` dataclass with fields as specified in Design Section 4.1: `regime` (str), `confidence` (float), `trending_score` (float, default 0.0), `ranging_score` (float, default 0.0), `volatile_score` (float, default 0.0), all raw input fields (india_vix, nifty_gap_pct, nifty_first_15_range_pct, nifty_first_15_direction, directional_alignment, sp500_change_pct, sgx_direction, fii_net_crores, dii_net_crores, prev_day_range_pct -- all `float | None` or `str | None`), derived modifiers (`strategy_weights: dict[str, float]`, `min_star_rating: int = 3`, `max_positions: int | None = None`, `position_size_modifier: float = 1.0`), and metadata (`is_reclassification: bool = False`, `previous_regime: str | None = None`, `classified_at: datetime`)
- [ ] Add `RegimePerformanceRecord` dataclass with fields: `id` (int | None), `regime_date` (date), `regime` (str), `strategy` (str), `signals_generated` (int, default 0), `signals_taken` (int, default 0), `wins` (int, default 0), `losses` (int, default 0), `pnl` (float, default 0.0), `win_rate` (float | None), `created_at` (datetime | None)
- [ ] Extend `SignalRecord` with three new nullable fields: `market_regime: str | None = None`, `regime_confidence: float | None = None`, `regime_weight_modifier: float | None = None`
- [ ] Update `__all__` to include `RegimeClassification` and `RegimePerformanceRecord`
- [ ] Write tests in `backend/tests/test_db/test_models.py` verifying dataclass instantiation, defaults, and field types for both new dataclasses
- Requirement coverage: REQ-MRD-013, REQ-MRD-049, REQ-MRD-050, REQ-MRD-029

### 1.2 Extend `ScanContext` in `backend/signalpilot/pipeline/context.py`

- [ ] Add six new fields with neutral defaults: `regime: str | None = None`, `regime_confidence: float = 0.0`, `regime_min_stars: int = 3`, `regime_position_modifier: float = 1.0`, `regime_max_positions: int | None = None`, `regime_strategy_weights: dict | None = None`
- [ ] Write tests verifying that default values ensure zero behavioral change when `RegimeContextStage` is absent (regime=None, min_stars=3, modifier=1.0, max_positions=None, strategy_weights=None)
- Requirement coverage: REQ-MRD-020

### 1.3 Add database migration in `backend/signalpilot/db/database.py`

- [ ] Implement `async def _run_regime_detection_migration(self) -> None` method on `DatabaseManager`
- [ ] Create `market_regimes` table with all columns from Design Section 5.1 (id, regime_date, classification_time, regime, confidence, trending_score, ranging_score, volatile_score, india_vix, nifty_gap_pct, nifty_first_15_range_pct, nifty_first_15_direction, directional_alignment, sp500_change_pct, sgx_direction, fii_net_crores, dii_net_crores, is_reclassification, previous_regime, strategy_weights_json, min_star_rating, max_positions, position_size_modifier, created_at)
- [ ] Create `idx_regime_date` index on `market_regimes(regime_date)`
- [ ] Create `regime_performance` table with all columns from Design Section 5.2 (id, regime_date, regime, strategy, signals_generated, signals_taken, wins, losses, pnl, win_rate, created_at)
- [ ] Create `idx_regime_perf` index on `regime_performance(regime, strategy)` and `idx_regime_perf_date` on `regime_performance(regime_date)`
- [ ] Add three nullable columns to `signals` table using idempotent `PRAGMA table_info()` check: `market_regime TEXT`, `regime_confidence REAL`, `regime_weight_modifier REAL`
- [ ] Call `_run_regime_detection_migration()` from `_create_tables()` after existing `_run_news_sentiment_migration()`
- [ ] Write tests in `backend/tests/test_db/test_database.py` verifying: tables created with correct columns, indexes exist, ALTER TABLE is idempotent (safe to re-run), backward compatibility with existing data
- Requirement coverage: REQ-MRD-027, REQ-MRD-028, REQ-MRD-029
