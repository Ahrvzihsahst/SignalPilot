# Task 12: Application Wiring

## Description
Wire all new regime detection components into `create_app()` in `main.py` following the existing dependency-injection pattern. Instantiate repositories, data collector, classifier, morning brief generator, and pass them to `SignalPilotApp` and `SignalPilotBot` constructors.

## Prerequisites
Task 1-11 (all component implementations)

## Requirement Coverage
REQ-MRD-022

## Files to Modify
- `signalpilot/main.py`

## Subtasks

### 12.1 Wire all new components in `backend/signalpilot/main.py` `create_app()`

- [ ] Import new modules: `MarketRegimeRepository`, `RegimePerformanceRepository`, `RegimeDataCollector`, `MarketRegimeClassifier`, `MorningBriefGenerator`
- [ ] After existing repository setup: instantiate `MarketRegimeRepository(connection)` and `RegimePerformanceRepository(connection)`
- [ ] After existing data layer setup: instantiate `RegimeDataCollector(market_data, config)` and `MarketRegimeClassifier(regime_data_collector, regime_repo, config)`
- [ ] Instantiate `MorningBriefGenerator(regime_data_collector, watchlist_repo, config)`
- [ ] Pass new components to `SignalPilotApp` constructor: `regime_classifier`, `regime_repo`, `regime_performance_repo`, `morning_brief_generator`, `regime_data_collector`
- [ ] Pass `regime_classifier`, `morning_brief_generator`, `regime_data_collector`, `regime_repo`, `regime_performance_repo` to `SignalPilotBot` constructor for REGIME/VIX/MORNING commands
- [ ] Verify no existing stage constructors or argument lists are modified
- [ ] Write a test verifying `create_app()` successfully creates an app with all regime detection components wired
- Requirement coverage: REQ-MRD-022
