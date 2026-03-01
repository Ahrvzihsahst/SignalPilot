# Task 8: Scheduler and Lifecycle Integration

## Description
Add three new scheduler jobs (pre-market news fetch at 8:30 AM, cache refresh at 11:15 and 13:15), implement the corresponding lifecycle methods on `SignalPilotApp`, enhance existing lifecycle methods (daily summary, weekly rebalance) with news-related hooks, and wire `NewsSentimentStage` into the pipeline stage list.

## Prerequisites
Task 4 (Intelligence Module), Task 5 (Pipeline Stage)

## Requirement Coverage
REQ-NSF-014, REQ-NSF-017, REQ-NSF-026, REQ-NSF-027, REQ-NSF-029, REQ-NSF-038

## Files to Modify
- `signalpilot/scheduler/scheduler.py`
- `signalpilot/scheduler/lifecycle.py`

## Subtasks

### 8.1 Add scheduler jobs in `backend/signalpilot/scheduler/scheduler.py`

- [x] Add pre-market news fetch job at 8:30 AM IST: `("pre_market_news", 8, 30, app.fetch_pre_market_news)` with `day_of_week='mon-fri'` and `_trading_day_guard`
- [x] Add two cache refresh jobs at 11:15 and 13:15 IST: `("news_cache_refresh_1", 11, 15, app.refresh_news_cache)` and `("news_cache_refresh_2", 13, 15, app.refresh_news_cache)` with same guards
- [x] Write tests verifying the new jobs are registered with correct times
- Requirement coverage: REQ-NSF-026, REQ-NSF-027

### 8.2 Add lifecycle methods in `backend/signalpilot/scheduler/lifecycle.py`

- [x] Add new constructor parameters: `news_sentiment_service=None`, `earnings_repo=None`, `earnings_calendar=None`, `news_sentiment_repo=None` (all default None for backward compat)
- [x] Store as instance attributes: `self._news_sentiment_service`, `self._earnings_repo`, `self._earnings_calendar`, `self._news_sentiment_repo`
- [x] Implement `async def fetch_pre_market_news()`: call `self._news_sentiment_service.fetch_and_analyze_all()`, handle failure gracefully (log error, proceed with NO_NEWS defaults), respect `news_enabled` kill switch
- [x] Implement `async def refresh_news_cache()`: call `self._news_sentiment_service.fetch_and_analyze_stocks()` with active scan list symbols, respect kill switch
- [x] Enhance `send_daily_summary()`: add cache purge call `self._news_sentiment_service.purge_old_entries(48)` and add `self._news_sentiment_service.clear_unsuppress_overrides()` after existing summary logic
- [x] Enhance `run_weekly_rebalance()`: add `self._earnings_calendar.refresh()` after existing rebalance logic
- [x] Update `_build_pipeline()`: insert `NewsSentimentStage(self._news_sentiment_service, self._earnings_repo, self._app_config)` after `RankingStage` and before `RiskSizingStage`
- [x] Import `NewsSentimentStage` at the top of the file
- [x] Write tests verifying: pipeline stage order is correct, fetch_pre_market_news calls service, refresh_news_cache calls service, daily summary purges cache, weekly rebalance refreshes earnings
- Requirement coverage: REQ-NSF-014, REQ-NSF-017, REQ-NSF-026, REQ-NSF-027, REQ-NSF-029, REQ-NSF-038
