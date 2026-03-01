# Task 11: Scheduler and Lifecycle Integration

## Description
Add five new scheduler jobs (8:45 AM morning brief, 9:30 AM classification, 11:00/13:00/14:30 re-classification checkpoints), implement the corresponding lifecycle methods on `SignalPilotApp`, enhance existing lifecycle methods (daily summary for regime performance tracking, start_scanning for daily reset), and wire `RegimeContextStage` into the pipeline stage list.

## Prerequisites
Task 5 (Classifier), Task 6 (Pipeline Stage), Task 8 (Morning Brief Generator)

## Requirement Coverage
REQ-MRD-022, REQ-MRD-023, REQ-MRD-024, REQ-MRD-025, REQ-MRD-028, REQ-MRD-037, REQ-MRD-038, REQ-MRD-046

## Files to Modify
- `signalpilot/scheduler/scheduler.py`
- `signalpilot/scheduler/lifecycle.py`

## Subtasks

### 11.1 Add scheduler jobs in `backend/signalpilot/scheduler/scheduler.py`

- [ ] Add five new regime detection jobs following the pattern from Design Section 3.6:
  - `("morning_brief", 8, 45, app.send_morning_brief)` -- pre-market brief
  - `("regime_classify", 9, 30, app.classify_regime)` -- initial classification
  - `("regime_reclass_11", 11, 0, app.check_regime_reclassify_11)` -- VIX spike check
  - `("regime_reclass_13", 13, 0, app.check_regime_reclassify_13)` -- direction reversal check
  - `("regime_reclass_1430", 14, 30, app.check_regime_reclassify_1430)` -- round-trip check
- [ ] All jobs use `day_of_week='mon-fri'` and `_trading_day_guard` decorator
- [ ] Use `hasattr(app, method_name)` guard for backward compatibility
- [ ] Write tests verifying the five new jobs are registered with correct times and guards
- Requirement coverage: REQ-MRD-023, REQ-MRD-025

### 11.2 Add lifecycle methods in `backend/signalpilot/scheduler/lifecycle.py`

- [ ] Add new constructor parameters (all default None for backward compat): `regime_classifier`, `regime_repo`, `regime_performance_repo`, `morning_brief_generator`, `regime_data_collector`
- [ ] Store as instance attributes: `self._regime_classifier`, `self._regime_repo`, `self._regime_performance_repo`, `self._morning_brief_generator`, `self._regime_data_collector`
- [ ] Implement `async def send_morning_brief()`: check `regime_enabled`, call `morning_brief_generator.generate()`, send via `bot.send_alert()`. Handle failure gracefully (log exception, skip)
- [ ] Implement `async def classify_regime()`: check `regime_enabled`, call `regime_classifier.classify()`, format and send classification notification, log regime and confidence
- [ ] Implement `async def check_regime_reclassify_11()`, `check_regime_reclassify_13()`, `check_regime_reclassify_1430()`: delegate to `_check_regime_reclassify(checkpoint)` with appropriate checkpoint string
- [ ] Implement `async def _check_regime_reclassify(checkpoint: str)`: check `regime_enabled`, call `regime_classifier.check_reclassify(checkpoint)`, send re-classification notification if triggered
- [ ] All lifecycle methods use `set_context(job_name=...)` / `reset_context()` for structured logging
- Requirement coverage: REQ-MRD-022, REQ-MRD-023, REQ-MRD-024, REQ-MRD-025, REQ-MRD-037, REQ-MRD-038, REQ-MRD-046

### 11.3 Enhance existing lifecycle methods

- [ ] Enhance `send_daily_summary()`: after existing summary logic, compute regime performance for the day by querying signals and trades, insert via `regime_performance_repo.insert_daily_performance()` for each strategy
- [ ] Enhance `start_scanning()` or equivalent: call `regime_classifier.reset_daily()` to clear re-classification count
- [ ] Update `_build_pipeline()`: insert `RegimeContextStage(self._regime_classifier, self._app_config)` after `CircuitBreakerGateStage` and before `StrategyEvalStage` -- matching the stage order from Design Section 2.4
- [ ] Import `RegimeContextStage` at the top of the file
- Requirement coverage: REQ-MRD-022, REQ-MRD-028

### 11.4 Write tests

- [ ] Write tests verifying:
  - Pipeline stage order: RegimeContextStage is at position 2 (after CircuitBreakerGate, before StrategyEval)
  - `send_morning_brief` calls generator and bot.send_alert
  - `classify_regime` calls classifier and sends notification
  - `_check_regime_reclassify` calls classifier, sends notification only when triggered
  - All lifecycle methods respect `regime_enabled=False` kill switch
  - Daily summary populates regime_performance table
  - `start_scanning` resets daily classifier state
- Requirement coverage: REQ-MRD-022, REQ-MRD-023, REQ-MRD-025, REQ-MRD-028, REQ-MRD-046, REQ-MRD-051
