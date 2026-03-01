# Implementation Tasks -- Phase 4: Market Regime Detection

## References
- Requirements: `.kiro/specs/signalpilot/phase4/market-regime-detection/requirements.md`
- Design: `.kiro/specs/signalpilot/phase4/market-regime-detection/design.md`

---

## 1. Data Models and Database Foundation

- [ ] 1.1 Add new dataclasses to `backend/signalpilot/db/models.py`
  - Add `RegimeClassification` dataclass with all fields from Design Section 4.1 (regime, confidence, scores, raw inputs, derived modifiers, metadata)
  - Add `RegimePerformanceRecord` dataclass with fields for daily strategy performance under a regime
  - Extend `SignalRecord` with three new nullable fields: `market_regime`, `regime_confidence`, `regime_weight_modifier`
  - Update `__all__` exports and write model instantiation tests
  - Requirements: REQ-MRD-013, REQ-MRD-049, REQ-MRD-050, REQ-MRD-029

- [ ] 1.2 Extend `ScanContext` in `backend/signalpilot/pipeline/context.py`
  - Add six regime fields with neutral defaults: `regime`, `regime_confidence`, `regime_min_stars`, `regime_position_modifier`, `regime_max_positions`, `regime_strategy_weights`
  - Write tests verifying default values ensure zero behavioral change when RegimeContextStage is absent
  - Requirements: REQ-MRD-020

- [ ] 1.3 Add database migration in `backend/signalpilot/db/database.py`
  - Implement `_run_regime_detection_migration()` creating `market_regimes` table, `regime_performance` table, indexes, and three nullable columns on `signals`
  - Call from `_create_tables()` after existing migrations. Use idempotent `PRAGMA table_info()` pattern
  - Write tests for table creation, indexes, idempotent re-run, backward compatibility
  - Requirements: REQ-MRD-027, REQ-MRD-028, REQ-MRD-029

## 2. Repository Layer

- [ ] 2.1 Implement `backend/signalpilot/db/regime_repo.py`
  - Create `MarketRegimeRepository` with `insert_classification()`, `get_today_classifications()`, `get_regime_history(days)`
  - Write tests for insert, today's records, history (latest per day), empty table
  - Requirements: REQ-MRD-030

- [ ] 2.2 Implement `backend/signalpilot/db/regime_performance_repo.py`
  - Create `RegimePerformanceRepository` with `insert_daily_performance()`, `get_performance_by_regime()`, `get_performance_summary()`
  - Write tests for insert with win rate, aggregation by regime, grouped summary
  - Requirements: REQ-MRD-031

- [ ] 2.3 Update `SignalRepository._row_to_record()` for new regime columns
  - Handle backward compatibility for three new nullable columns using existing optional-column pattern
  - Ensure `insert_signal()` persists new fields. Write round-trip tests
  - Requirements: REQ-MRD-029

## 3. Configuration

- [ ] 3.1 Add regime detection config fields to `backend/signalpilot/config.py`
  - Add 20+ fields: `regime_enabled`, `regime_shadow_mode`, confidence threshold, re-classification limits, six weight matrices (JSON strings), three position modifiers, three max positions, five min star ratings
  - Update `backend/.env.example` with new environment variables and defaults
  - Write tests verifying defaults and JSON weight parsing
  - Requirements: REQ-MRD-044, REQ-MRD-045, REQ-MRD-046

## 4. Regime Data Collector

- [ ] 4.1 Create `RegimeInputs` and `PreMarketData` dataclasses in `backend/signalpilot/intelligence/regime_data.py`
  - Define all-nullable dataclasses for classification inputs and pre-market data
  - Requirements: REQ-MRD-001 through REQ-MRD-006

- [ ] 4.2 Implement `RegimeDataCollector` class
  - Fetch VIX (with fallback chain), Nifty gap/range/direction, SGX, S&P 500, FII/DII, previous day range
  - `collect_pre_market_data()` for 8:45 AM brief, `collect_regime_inputs()` for 9:30 AM classification
  - Each data source has independent error handling, defaults to None on failure
  - Write comprehensive tests for each data source, fallbacks, partial failures, caching
  - Requirements: REQ-MRD-001 through REQ-MRD-007

## 5. Market Regime Classifier

- [ ] 5.1 Implement component score static methods in `backend/signalpilot/intelligence/regime_classifier.py`
  - `_compute_vix_score()`, `_compute_gap_score()`, `_compute_range_score()`, `_compute_alignment()`
  - Write tests for all score brackets and None inputs
  - Requirements: REQ-MRD-009, REQ-MRD-010, REQ-MRD-011, REQ-MRD-012

- [ ] 5.2 Implement classification core logic
  - Composite score formula (trending/ranging/volatile), winner-takes-all, confidence calculation, modifier derivation
  - Write tests for each regime classification scenario and modifier tables
  - Requirements: REQ-MRD-008, REQ-MRD-013, REQ-MRD-015 through REQ-MRD-018

- [ ] 5.3 Implement `classify()`, cache management, and re-classification
  - In-memory cache keyed by IST date, `get_cached_regime()` for pipeline, `check_reclassify()` with severity-upgrade-only rule and max 2/day
  - `apply_override()` for manual override, `reset_daily()` for session start
  - Write tests for cache read/write, re-classification triggers, severity rules, override
  - Requirements: REQ-MRD-008, REQ-MRD-014, REQ-MRD-023, REQ-MRD-024, REQ-MRD-034

## 6. RegimeContextStage Pipeline Stage

- [ ] 6.1 Implement `backend/signalpilot/pipeline/stages/regime_context.py`
  - Read cached regime and set six fields on ScanContext
  - Kill switch bypass, shadow mode (set regime/confidence only, leave modifiers neutral), DEFAULT when no classification
  - Write tests for all branches: full mode, shadow mode, disabled, no classification, execution time <1ms
  - Requirements: REQ-MRD-019, REQ-MRD-045, REQ-MRD-046, REQ-MRD-053

## 7. Existing Stage Modifications

- [ ] 7.1 Enhance `RankingStage` with min-stars filter
  - Filter signals below `ctx.regime_min_stars` when threshold > 3. No-op at default
  - Write tests for threshold 3 (no filter), 4, and 5
  - Requirements: REQ-MRD-016

- [ ] 7.2 Enhance `RiskSizingStage` with position modifier and max positions override
  - Shallow copy UserConfig with regime max_positions, multiply quantities by position modifier
  - Write tests for 1.0x (no-op), 0.85x, 0.65x modifiers and max positions override
  - Requirements: REQ-MRD-017, REQ-MRD-018, REQ-MRD-048

- [ ] 7.3 Enhance `PersistAndDeliverStage` with regime metadata
  - Attach `market_regime`, `regime_confidence`, `regime_weight_modifier` to SignalRecord when ctx.regime is set
  - Pass regime data to signal formatting. No-op when ctx.regime is None
  - Requirements: REQ-MRD-021

## 8. Morning Brief Generator

- [ ] 8.1 Implement `backend/signalpilot/intelligence/morning_brief.py`
  - `MorningBriefGenerator` composing 8:45 AM pre-market brief with global cues, India context, regime prediction, watchlist alerts
  - Graceful handling of missing data sections. Cache brief for MORNING re-send command
  - Write tests for complete brief, partial data, prediction logic, watchlist inclusion, caching
  - Requirements: REQ-MRD-025, REQ-MRD-026

## 9. Telegram Formatters

- [ ] 9.1 Add regime formatter functions to `backend/signalpilot/telegram/formatters.py`
  - `format_regime_display()`, `format_regime_modifiers()`, `format_classification_notification()`, `format_reclass_notification()`, `format_regime_history()`, helper functions
  - Requirements: REQ-MRD-037, REQ-MRD-038

- [ ] 9.2 Enhance `format_signal_message()` with regime badge
  - Add optional `market_regime` and `regime_confidence` parameters. VOLATILE includes cautionary note
  - Write tests for all formatter functions and signal badge scenarios
  - Requirements: REQ-MRD-047

## 10. Telegram Commands

- [ ] 10.1 Implement command handlers in `backend/signalpilot/telegram/handlers.py`
  - `handle_regime_command()`, `handle_regime_history_command()`, `handle_regime_override_command()`, `handle_vix_command()`, `handle_morning_command()`
  - Requirements: REQ-MRD-032 through REQ-MRD-036

- [ ] 10.2 Register commands in `backend/signalpilot/telegram/bot.py`
  - Add constructor parameters, register five MessageHandlers with regex patterns
  - Write tests for all command happy paths and error cases
  - Requirements: REQ-MRD-032 through REQ-MRD-036

## 11. Scheduler and Lifecycle Integration

- [ ] 11.1 Add five scheduler jobs in `backend/signalpilot/scheduler/scheduler.py`
  - Morning brief (8:45), classification (9:30), re-classification checkpoints (11:00, 13:00, 14:30)
  - Requirements: REQ-MRD-023, REQ-MRD-025

- [ ] 11.2 Add lifecycle methods in `backend/signalpilot/scheduler/lifecycle.py`
  - `send_morning_brief()`, `classify_regime()`, three re-classification checkpoint methods
  - All respect `regime_enabled` kill switch, use structured logging context
  - Requirements: REQ-MRD-022, REQ-MRD-023, REQ-MRD-025, REQ-MRD-037, REQ-MRD-038, REQ-MRD-046

- [ ] 11.3 Enhance existing lifecycle methods
  - Daily summary populates regime_performance table, start_scanning resets daily state
  - Update `_build_pipeline()` to insert RegimeContextStage at position 2
  - Write tests for pipeline order, lifecycle calls, kill switch, daily summary, state reset
  - Requirements: REQ-MRD-022, REQ-MRD-028

## 12. Application Wiring

- [ ] 12.1 Wire all new components in `backend/signalpilot/main.py` `create_app()`
  - Instantiate repos, data collector, classifier, morning brief generator
  - Pass to SignalPilotApp and SignalPilotBot constructors
  - Verify no existing constructors modified. Write wiring test
  - Requirements: REQ-MRD-022

## 13. Dashboard API Endpoints

- [ ] 13.1 Implement `backend/signalpilot/dashboard/routes/regime.py`
  - `GET /current`, `GET /history`, `GET /performance`, `POST /override` on regime router
  - `GET /` on morning brief router
  - Register both routers in `backend/signalpilot/dashboard/app.py`
  - Write tests for all five endpoints (success, empty data, invalid input)
  - Requirements: REQ-MRD-039 through REQ-MRD-043

## 14. Integration Tests

- [ ] 14.1 Write pipeline integration tests in `backend/tests/test_integration/test_regime_pipeline.py`
  - Full pipeline cycles with TRENDING, VOLATILE, RANGING regimes
  - No classification baseline, shadow mode, re-classification mid-day, override
  - Signal persistence with regime metadata, classification persistence
  - Kill switch disabled scenario
  - Requirements: REQ-MRD-052

## 15. Test Fixtures and Shared Setup

- [ ] 15.1 Add shared test fixtures to `backend/tests/conftest.py`
  - `sample_regime_inputs`, `sample_regime_classification`, `regime_repo`, `regime_perf_repo` fixtures
  - Ensure in-memory db fixture runs regime detection migration
  - Requirements: REQ-MRD-051
