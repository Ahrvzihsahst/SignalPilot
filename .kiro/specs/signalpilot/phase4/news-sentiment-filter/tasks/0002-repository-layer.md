# Task 2: Repository Layer

## Description
Implement `NewsSentimentRepository` and `EarningsCalendarRepository` for the two new tables, and update `SignalRepository._row_to_record()` to handle the five new nullable news columns with backward compatibility.

## Prerequisites
Task 1 (Data Models and Database Foundation)

## Requirement Coverage
REQ-NSF-018, REQ-NSF-019, REQ-NSF-020, REQ-NSF-021, REQ-NSF-022, REQ-NSF-029

## Files to Create
- `signalpilot/db/news_sentiment_repo.py`
- `signalpilot/db/earnings_repo.py`

## Files to Modify
- `signalpilot/db/signal_repo.py`

## Subtasks

### 2.1 Implement `backend/signalpilot/db/news_sentiment_repo.py`

- [x] Create `NewsSentimentRepository` class accepting `aiosqlite.Connection` in constructor
- [x] Implement `upsert_headlines(stock_code, headlines: list[NewsSentimentRecord]) -> int` using `INSERT OR REPLACE` with `(stock_code, headline, source)` conflict key
- [x] Implement `get_stock_sentiment(stock_code, lookback_hours=24) -> list[NewsSentimentRecord]` using indexed `stock_code` + `published_at` lookup, ordered by `published_at DESC`
- [x] Implement `get_composite_score(stock_code, lookback_hours=24) -> tuple[float, str, int] | None` returning recency-weighted composite score, label, and headline count
- [x] Implement `get_top_negative_headline(stock_code, lookback_hours=24) -> str | None`
- [x] Implement `purge_old_entries(older_than_hours=48) -> int` deleting rows where `fetched_at` exceeds threshold
- [x] Implement `get_all_stock_sentiments(lookback_hours=24) -> dict[str, tuple[float, str, int]]` for NEWS ALL command
- [x] Implement `_row_to_record()` static method
- [x] Write tests in `backend/tests/test_db/test_news_sentiment_repo.py` covering upsert, query within lookback, exclusion outside lookback, composite score computation, purge count, conflict handling, and empty stock case
- Requirement coverage: REQ-NSF-020, REQ-NSF-018, REQ-NSF-029

### 2.2 Implement `backend/signalpilot/db/earnings_repo.py`

- [x] Create `EarningsCalendarRepository` class accepting `aiosqlite.Connection` in constructor
- [x] Implement `has_earnings_today(stock_code) -> bool` comparing against `datetime.now(IST).date()`
- [x] Implement `get_upcoming_earnings(days_ahead=7) -> list[EarningsCalendarRecord]` ordered by `earnings_date ASC`
- [x] Implement `upsert_earnings(stock_code, earnings_date, quarter, source, is_confirmed) -> None` using `(stock_code, earnings_date)` conflict key, setting `updated_at = datetime.now(IST)`
- [x] Implement `get_today_earnings_stocks() -> list[str]` for batch checking
- [x] Implement `_row_to_record()` static method
- [x] Write tests in `backend/tests/test_db/test_earnings_repo.py` covering `has_earnings_today` True/False cases, upcoming earnings range queries, upsert conflict resolution, and IST date handling
- Requirement coverage: REQ-NSF-022, REQ-NSF-019

### 2.3 Update `SignalRepository._row_to_record()` for new columns

- [x] Handle backward compatibility for the five new nullable columns using the existing Phase 3 optional-column pattern (index-based access with fallback to None)
- [x] Ensure `insert_signal()` persists the new fields when present
- [x] Write tests verifying old rows without news columns are read correctly, and new rows with news metadata round-trip correctly
- Requirement coverage: REQ-NSF-021
