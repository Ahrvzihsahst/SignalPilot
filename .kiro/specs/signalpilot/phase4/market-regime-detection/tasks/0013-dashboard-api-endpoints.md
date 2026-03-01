# Task 13: Dashboard API Endpoints

## Description
Implement five new FastAPI endpoints for the dashboard: `GET /api/v1/regime/current`, `GET /api/v1/regime/history`, `GET /api/v1/regime/performance`, `POST /api/v1/regime/override`, and `GET /api/v1/morning-brief`. Register both routers in the dashboard app.

## Prerequisites
Task 2 (Repository Layer), Task 5 (Classifier), Task 8 (Morning Brief Generator)

## Requirement Coverage
REQ-MRD-039, REQ-MRD-040, REQ-MRD-041, REQ-MRD-042, REQ-MRD-043

## Files to Create
- `signalpilot/dashboard/routes/regime.py`

## Files to Modify
- `signalpilot/dashboard/app.py`

## Subtasks

### 13.1 Implement `backend/signalpilot/dashboard/routes/regime.py`

- [ ] Create `router = APIRouter()` for `/api/v1/regime` routes
- [ ] Define `RegimeOverrideRequest(BaseModel)` with `regime: str` field
- [ ] Implement `GET /current`: read cached regime from classifier. If no classification, return 200 with `regime: null` and DEFAULT modifiers. If available, return full classification as JSON (regime, confidence, scores, inputs, modifiers)
- [ ] Implement `GET /history`: query `regime_repo.get_regime_history(days)` with configurable `days` query parameter (default 30). Return list of daily regime records
- [ ] Implement `GET /performance`: query `regime_perf_repo.get_performance_summary(days)` with configurable `days` parameter (default 30). Return aggregated win rate, signals, P&L by regime and strategy
- [ ] Implement `POST /override`: validate regime is TRENDING/RANGING/VOLATILE (return 400 if invalid), call `classifier.apply_override(regime)`, return updated classification
- [ ] Create `morning_router = APIRouter()` for `/api/v1/morning-brief`
- [ ] Implement `GET /`: return morning brief data as JSON. If not generated yet, return 200 with `generated: false`
- Requirement coverage: REQ-MRD-039, REQ-MRD-040, REQ-MRD-041, REQ-MRD-042, REQ-MRD-043

### 13.2 Register routers in `backend/signalpilot/dashboard/app.py`

- [ ] Import `regime` routes module
- [ ] Register `regime.router` with prefix `/api/v1/regime` and tags `["regime"]`
- [ ] Register `regime.morning_router` with prefix `/api/v1/morning-brief` and tags `["morning-brief"]`
- Requirement coverage: REQ-MRD-039

### 13.3 Write tests

- [ ] Write tests in `backend/tests/test_dashboard/test_regime_api.py` covering:
  - `GET /current` with classification returns full data
  - `GET /current` with no classification returns null regime and defaults
  - `GET /history` returns list of daily records
  - `GET /history?days=7` limits to 7 days
  - `GET /history` with no data returns empty list
  - `GET /performance` returns grouped summary
  - `GET /performance` with no data returns empty aggregations
  - `POST /override` with valid regime returns updated classification
  - `POST /override` with invalid regime returns 400
  - `GET /morning-brief` with generated brief returns data
  - `GET /morning-brief` before generation returns `generated: false`
- Requirement coverage: REQ-MRD-039 through REQ-MRD-043, REQ-MRD-051
