# Task 10: Dashboard API Endpoints

## Description
Implement three new FastAPI routes for the dashboard: stock-specific news sentiment, suppressed signals list, and upcoming earnings calendar. Register the routers in the dashboard app.

## Prerequisites
Task 2 (Repository Layer), Task 4 (Intelligence Module)

## Requirement Coverage
REQ-NSF-030, REQ-NSF-031, REQ-NSF-032

## Files to Create
- `signalpilot/dashboard/routes/news.py`

## Files to Modify
- `signalpilot/dashboard/app.py`

## Subtasks

### 10.1 Implement `backend/signalpilot/dashboard/routes/news.py`

- [x] Create `router = APIRouter()` for `/api/v1/news` routes
- [x] Implement `GET /{stock_code}` endpoint: query `NewsSentimentRepository`, return composite score, label, headline count, model used, and recent headlines list
- [x] Implement `GET /suppressed` endpoint: query signals table where `news_action IN ('SUPPRESSED', 'EARNINGS_BLACKOUT')`, support `date` and `limit` query parameters
- [x] Create `earnings_router = APIRouter()` for `/api/v1/earnings` routes
- [x] Implement `GET /upcoming` endpoint: query `EarningsCalendarRepository.get_upcoming_earnings()`, support configurable `days` parameter (default 14)
- [x] Register both routers in `backend/signalpilot/dashboard/app.py`
- [x] Write tests for all three endpoints: valid stock returns sentiment, unknown stock returns NO_NEWS, suppressed signals filtered by date, upcoming earnings returns correct range
- Requirement coverage: REQ-NSF-030, REQ-NSF-031, REQ-NSF-032
