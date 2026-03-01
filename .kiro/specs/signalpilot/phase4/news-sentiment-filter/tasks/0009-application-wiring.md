# Task 9: Application Wiring

## Description
Wire all new components into `create_app()` in `main.py` following the existing dependency-injection pattern, and add new Python dependencies (`vaderSentiment`, `feedparser`, `aiohttp`) to `pyproject.toml` with optional FinBERT extras.

## Prerequisites
Task 1–8 (all component implementations)

## Requirement Coverage
REQ-NSF-004, REQ-NSF-005, REQ-NSF-017

## Files to Modify
- `signalpilot/main.py`
- `pyproject.toml`

## Subtasks

### 9.1 Wire all new components in `backend/signalpilot/main.py` `create_app()`

- [x] Import new modules: `NewsSentimentRepository`, `EarningsCalendarRepository`, `NewsFetcher`, `VADERSentimentEngine`, `FinBERTSentimentEngine`, `NewsSentimentService`, `EarningsCalendar`, `NewsSentimentStage`
- [x] After existing repository setup: instantiate `NewsSentimentRepository(connection)` and `EarningsCalendarRepository(connection)`
- [x] Select sentiment engine based on `config.sentiment_model`: VADER (with `lexicon_path`) or FinBERT
- [x] Instantiate `NewsFetcher(config)`, `NewsSentimentService(news_fetcher, sentiment_engine, news_sentiment_repo, earnings_repo, config)`, `EarningsCalendar(earnings_repo, config)`
- [x] Pass new components to `SignalPilotApp` constructor: `news_sentiment_service`, `earnings_repo`, `earnings_calendar`, `news_sentiment_repo`
- [x] Pass `news_sentiment_service` and `earnings_repo` to `SignalPilotBot` constructor for NEWS/EARNINGS/UNSUPPRESS commands
- [x] Verify no existing stage constructors or argument lists are modified
- [x] Write a test verifying `create_app()` successfully creates an app with all news sentiment components wired
- Requirement coverage: REQ-NSF-017

### 9.2 Add new Python dependencies to `backend/pyproject.toml`

- [x] Add `vaderSentiment>=3.3.2`, `feedparser>=6.0.10`, `aiohttp>=3.9.0` to `[project.dependencies]`
- [x] Add optional `[project.optional-dependencies] finbert = ["transformers>=4.35.0", "torch>=2.0.0", "sentencepiece>=0.1.99"]`
- [x] Run `pip install -e ".[dev]"` to verify dependencies install correctly
- Requirement coverage: REQ-NSF-004, REQ-NSF-005
