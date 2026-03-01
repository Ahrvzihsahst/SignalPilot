# Task 12: Test Fixtures and Shared Setup

## Description
Add shared test fixtures for the news sentiment feature to the root `conftest.py` and integration `conftest.py`. This ensures the in-memory SQLite database runs the news sentiment migration and provides reusable sample data fixtures for all test files.

## Prerequisites
Task 1 (Data Models), Task 2 (Repository Layer)

## Requirement Coverage
REQ-NSF-045

## Files to Modify
- `tests/conftest.py`
- `tests/test_integration/conftest.py`

## Files to Create
- `tests/test_intelligence/__init__.py`

## Subtasks

### 12.1 Add shared test fixtures to `backend/tests/conftest.py`

- [x] Add `sample_sentiment_result` fixture returning a `SentimentResult` with MILD_NEGATIVE values
- [x] Add `sample_suppressed_signal` fixture returning a `SuppressedSignal` with STRONG_NEGATIVE values
- [x] Add `news_sentiment_repo` fixture using in-memory SQLite with news_sentiment table created
- [x] Add `earnings_repo` fixture using in-memory SQLite with earnings_calendar table created
- [x] Ensure the in-memory `db` fixture runs the news sentiment migration
- [x] Create `backend/tests/test_intelligence/__init__.py`
- Requirement coverage: REQ-NSF-045
