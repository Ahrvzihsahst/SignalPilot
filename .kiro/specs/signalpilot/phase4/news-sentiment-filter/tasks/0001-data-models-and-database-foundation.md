# Task 1: Data Models and Database Foundation

## Description
Add all new dataclasses (`SentimentResult`, `SuppressedSignal`, `NewsSentimentRecord`, `EarningsCalendarRecord`), extend `SignalRecord` with news metadata columns, extend `ScanContext` with sentiment fields, and create the database migration for two new tables plus five new columns on `signals`.

## Prerequisites
None (foundational task)

## Requirement Coverage
REQ-NSF-015, REQ-NSF-018, REQ-NSF-019, REQ-NSF-021, REQ-NSF-043, REQ-NSF-044

## Files to Modify
- `signalpilot/db/models.py`
- `signalpilot/pipeline/context.py`
- `signalpilot/db/database.py`

## Subtasks

### 1.1 Add new dataclasses to `backend/signalpilot/db/models.py`

- [x] Add `SentimentResult` dataclass with fields: `score` (float), `label` (str), `headline` (str | None), `action` (str), `headline_count` (int), `top_negative_headline` (str | None), `model_used` (str)
- [x] Add `SuppressedSignal` dataclass with fields: `symbol` (str), `strategy` (str), `original_stars` (int), `sentiment_score` (float), `sentiment_label` (str), `top_headline` (str | None), `reason` (str), `entry_price` (float), `stop_loss` (float), `target_1` (float)
- [x] Add `NewsSentimentRecord` dataclass with all fields from Design Section 4.1 (id, stock_code, headline, source, published_at, positive_score, negative_score, neutral_score, composite_score, sentiment_label, fetched_at, model_used) with appropriate defaults
- [x] Add `EarningsCalendarRecord` dataclass with fields: id, stock_code, earnings_date, quarter, source, is_confirmed, updated_at with appropriate defaults
- [x] Extend `SignalRecord` with five new nullable fields: `news_sentiment_score: float | None = None`, `news_sentiment_label: str | None = None`, `news_top_headline: str | None = None`, `news_action: str | None = None`, `original_star_rating: int | None = None`
- [x] Update `__all__` to include `SentimentResult`, `SuppressedSignal`, `NewsSentimentRecord`, `EarningsCalendarRecord`
- [x] Write tests in `backend/tests/test_db/test_models.py` verifying dataclass instantiation, defaults, and field types for all four new dataclasses
- Requirement coverage: REQ-NSF-043, REQ-NSF-044, REQ-NSF-021

### 1.2 Extend `ScanContext` in `backend/signalpilot/pipeline/context.py`

- [x] Add import for `SentimentResult` and `SuppressedSignal` from `signalpilot.db.models`
- [x] Add `sentiment_results: dict[str, SentimentResult] = field(default_factory=dict)` field
- [x] Add `suppressed_signals: list[SuppressedSignal] = field(default_factory=list)` field
- [x] Write tests verifying default empty dict/list values ensure zero behavioral change when NewsSentimentStage is absent
- Requirement coverage: REQ-NSF-015

### 1.3 Add database migration in `backend/signalpilot/db/database.py`

- [x] Implement `async def _run_news_sentiment_migration(self) -> None` method on `DatabaseManager`
- [x] Create `news_sentiment` table with `UNIQUE(stock_code, headline, source)` constraint
- [x] Create `idx_news_stock_date` index on `news_sentiment(stock_code, published_at)`
- [x] Create `idx_news_fetched_at` index on `news_sentiment(fetched_at)`
- [x] Create `earnings_calendar` table with `UNIQUE(stock_code, earnings_date)` constraint
- [x] Create `idx_earnings_date` index on `earnings_calendar(earnings_date)`
- [x] Create `idx_earnings_stock_date` index on `earnings_calendar(stock_code, earnings_date)`
- [x] Add five nullable columns to `signals` table using idempotent `PRAGMA table_info()` check: `news_sentiment_score REAL`, `news_sentiment_label TEXT`, `news_top_headline TEXT`, `news_action TEXT`, `original_star_rating INTEGER`
- [x] Call `_run_news_sentiment_migration()` from `_create_tables()` after existing Phase 4 migration
- [x] Write tests verifying: tables created with correct columns, indexes exist, ALTER TABLE is idempotent (safe to re-run), backward compatibility with existing data
- Requirement coverage: REQ-NSF-018, REQ-NSF-019, REQ-NSF-021
