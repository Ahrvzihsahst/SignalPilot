# Implementation Tasks -- Phase 4: News Sentiment Filter

## References
- Requirements: `.kiro/specs/signalpilot/phase4/news-sentiment-filter/requirements.md`
- Design: `.kiro/specs/signalpilot/phase4/news-sentiment-filter/design.md`

---

## 1. Data Models and Database Foundation ✅

- [x] 1.1 Add new dataclasses to `backend/signalpilot/db/models.py`
  - Add `SentimentResult`, `SuppressedSignal`, `NewsSentimentRecord`, `EarningsCalendarRecord` dataclasses as specified in Design Section 4.1
  - Extend `SignalRecord` with five new nullable fields: `news_sentiment_score`, `news_sentiment_label`, `news_top_headline`, `news_action`, `original_star_rating`
  - Update `__all__` exports to include the four new dataclasses
  - Write tests in `backend/tests/test_db/test_models.py` verifying dataclass instantiation, defaults, and field types
  - Requirements: REQ-NSF-043, REQ-NSF-044, REQ-NSF-021

- [x] 1.2 Extend `ScanContext` in `backend/signalpilot/pipeline/context.py`
  - Add `sentiment_results: dict[str, SentimentResult]` field with `field(default_factory=dict)`
  - Add `suppressed_signals: list[SuppressedSignal]` field with `field(default_factory=list)`
  - Add the necessary import for `SentimentResult` and `SuppressedSignal` from models
  - Write tests verifying default values ensure zero behavioral change when NewsSentimentStage is absent
  - Requirements: REQ-NSF-015

- [x] 1.3 Add database migration in `backend/signalpilot/db/database.py`
  - Implement `_run_news_sentiment_migration()` method on `DatabaseManager` following the idempotent `PRAGMA table_info()` check-before-alter pattern from Phase 2/3/4
  - Create `news_sentiment` table with schema from Design Section 5.1 including `UNIQUE(stock_code, headline, source)` constraint and `idx_news_stock_date`, `idx_news_fetched_at` indexes
  - Create `earnings_calendar` table with schema from Design Section 5.2 including `UNIQUE(stock_code, earnings_date)` constraint and `idx_earnings_date`, `idx_earnings_stock_date` indexes
  - Add five nullable columns to `signals` table: `news_sentiment_score REAL`, `news_sentiment_label TEXT`, `news_top_headline TEXT`, `news_action TEXT`, `original_star_rating INTEGER`
  - Call `_run_news_sentiment_migration()` from `_create_tables()` after existing migrations
  - Write tests in `backend/tests/test_db/test_database.py` verifying tables are created, indexes exist, columns are added idempotently, and re-running migration is safe
  - Requirements: REQ-NSF-018, REQ-NSF-019, REQ-NSF-021

## 2. Repository Layer

- [ ] 2.1 Implement `backend/signalpilot/db/news_sentiment_repo.py`
  - Create `NewsSentimentRepository` class accepting `aiosqlite.Connection` in constructor
  - Implement `upsert_headlines(stock_code, headlines: list[NewsSentimentRecord]) -> int` using `INSERT OR REPLACE` with `(stock_code, headline, source)` conflict key
  - Implement `get_stock_sentiment(stock_code, lookback_hours=24) -> list[NewsSentimentRecord]` using indexed `stock_code` + `published_at` lookup, ordered by `published_at DESC`
  - Implement `get_composite_score(stock_code, lookback_hours=24) -> tuple[float, str, int] | None` returning recency-weighted composite score, label, and headline count
  - Implement `get_top_negative_headline(stock_code, lookback_hours=24) -> str | None`
  - Implement `purge_old_entries(older_than_hours=48) -> int` deleting rows where `fetched_at` exceeds threshold
  - Implement `get_all_stock_sentiments(lookback_hours=24) -> dict[str, tuple[float, str, int]]` for NEWS ALL command
  - Implement `_row_to_record()` static method
  - Write tests in `backend/tests/test_db/test_news_sentiment_repo.py` covering upsert, query within lookback, exclusion outside lookback, composite score computation, purge count, conflict handling, and empty stock case
  - Requirements: REQ-NSF-020, REQ-NSF-018, REQ-NSF-029

- [ ] 2.2 Implement `backend/signalpilot/db/earnings_repo.py`
  - Create `EarningsCalendarRepository` class accepting `aiosqlite.Connection` in constructor
  - Implement `has_earnings_today(stock_code) -> bool` comparing against `datetime.now(IST).date()`
  - Implement `get_upcoming_earnings(days_ahead=7) -> list[EarningsCalendarRecord]` ordered by `earnings_date ASC`
  - Implement `upsert_earnings(stock_code, earnings_date, quarter, source, is_confirmed) -> None` using `(stock_code, earnings_date)` conflict key, setting `updated_at = datetime.now(IST)`
  - Implement `get_today_earnings_stocks() -> list[str]` for batch checking
  - Implement `_row_to_record()` static method
  - Write tests in `backend/tests/test_db/test_earnings_repo.py` covering `has_earnings_today` True/False cases, upcoming earnings range queries, upsert conflict resolution, and IST date handling
  - Requirements: REQ-NSF-022, REQ-NSF-019

- [ ] 2.3 Update `SignalRepository._row_to_record()` for new columns
  - Handle backward compatibility for the five new nullable columns using the existing Phase 3 optional-column pattern (index-based access with fallback to None)
  - Ensure `insert_signal()` persists the new fields when present
  - Write tests verifying old rows without news columns are read correctly, and new rows with news metadata round-trip correctly
  - Requirements: REQ-NSF-021

## 3. Configuration

- [ ] 3.1 Add news sentiment config fields to `backend/signalpilot/config.py`
  - Add 12 new fields to `AppConfig` as specified in Design Section 6.1: `news_enabled`, `sentiment_model`, `news_lookback_hours`, `news_cache_ttl_hours`, `strong_negative_threshold`, `mild_negative_threshold`, `positive_threshold`, `earnings_blackout_enabled`, `news_pre_market_fetch_time`, `news_max_headlines_per_stock`, `news_rss_feeds`, `news_financial_lexicon_path`, `news_earnings_csv_path`
  - Add validation that `sentiment_model` is one of `"vader"` or `"finbert"` (fail fast on unrecognized value)
  - Update `backend/.env.example` with the new environment variables and their defaults
  - Write tests verifying defaults load correctly and invalid `sentiment_model` raises a validation error
  - Requirements: REQ-NSF-039, REQ-NSF-040, REQ-NSF-041, REQ-NSF-006, REQ-NSF-042

## 4. Intelligence Module -- Core Services

- [ ] 4.1 Create `backend/signalpilot/intelligence/__init__.py` and financial lexicon
  - Create the `backend/signalpilot/intelligence/` package with `__init__.py`
  - Create `backend/signalpilot/intelligence/financial_lexicon.json` with the 40+ term-score mappings from Design Section 6.3
  - Requirements: REQ-NSF-042

- [ ] 4.2 Implement `backend/signalpilot/intelligence/sentiment_engine.py`
  - Define `ScoredHeadline` dataclass with fields: `title`, `source`, `published_at`, `positive_score`, `negative_score`, `neutral_score`, `compound_score`, `model_used`
  - Define `SentimentEngine` protocol with `model_name` property, `analyze(text) -> ScoredHeadline`, and `analyze_batch(texts) -> list[ScoredHeadline]`
  - Implement `VADERSentimentEngine` class: load `vaderSentiment.SentimentIntensityAnalyzer`, optionally merge financial lexicon JSON via `analyzer.lexicon.update()`, implement `analyze()` mapping VADER's `polarity_scores()` to `ScoredHeadline`, implement `analyze_batch()` as sequential calls
  - Implement `FinBERTSentimentEngine` class: load `ProsusAI/finbert` via `transformers.pipeline`, implement `analyze()` and `analyze_batch()` mapping FinBERT outputs to `ScoredHeadline`
  - Handle missing lexicon file gracefully (log warning, use default VADER), handle malformed JSON gracefully
  - Write tests in `backend/tests/test_intelligence/test_sentiment_engine.py`: VADER positive/negative/neutral headlines, financial lexicon overlay strengthens scores, missing lexicon fallback, malformed lexicon fallback, protocol satisfaction by both implementations, batch analysis count
  - Requirements: REQ-NSF-004, REQ-NSF-005, REQ-NSF-006, REQ-NSF-042

- [ ] 4.3 Implement `backend/signalpilot/intelligence/news_fetcher.py`
  - Define `RawHeadline` dataclass with fields: `title`, `source`, `published_at`, `link`, `stock_codes`
  - Implement `NewsFetcher` class: accept `AppConfig`, parse feed URLs from `news_rss_feeds`, build symbol matching index from Nifty 500 list via `initialize(symbols)`
  - Implement `_fetch_feed(url) -> list[RawHeadline]` using `aiohttp` for async HTTP + `feedparser` for parsing, with 10s timeout per feed
  - Implement `_match_headline_to_stocks(headline) -> list[str]` using case-insensitive substring matching against company names and stock codes
  - Implement `fetch_all_stocks() -> dict[str, list[RawHeadline]]` fetching all configured feeds, matching headlines to stocks, filtering by lookback window, capping at `max_headlines_per_stock`, deduplicating near-identical headlines
  - Implement `fetch_stocks(symbols) -> dict[str, list[RawHeadline]]` for targeted refresh
  - Implement `close()` to close the `aiohttp.ClientSession`
  - Handle individual feed failures gracefully (log warning, continue with remaining feeds)
  - Write tests in `backend/tests/test_intelligence/test_news_fetcher.py`: valid RSS parsing, malformed XML handling, headline-to-stock matching, lookback filtering, headline cap enforcement, feed timeout handling, empty feed response, URL validation
  - Requirements: REQ-NSF-001, REQ-NSF-002, REQ-NSF-003, REQ-NSF-040

- [ ] 4.4 Implement `backend/signalpilot/intelligence/news_sentiment.py`
  - Implement `NewsSentimentService` class as specified in Design Section 3.3
  - Constructor accepts: `news_fetcher`, `sentiment_engine` (protocol), `news_sentiment_repo`, `earnings_repo`, `config`
  - Implement `fetch_and_analyze_all() -> int`: fetch all stocks, run sentiment engine, upsert to repo, return headline count
  - Implement `fetch_and_analyze_stocks(symbols) -> int`: same for subset
  - Implement `get_sentiment_for_stock(stock_code, lookback_hours) -> SentimentResult`: query repo, compute composite score with recency weighting (exponential decay, 6-hour half-life), classify label, build `SentimentResult`
  - Implement `get_sentiment_batch(symbols) -> dict[str, SentimentResult]`: batch version
  - Implement `_compute_composite_score(headlines) -> tuple[float, str]` with recency-weighted average: `weight_i = exp(-lambda * age_hours_i)` where `lambda = ln(2) / 6`
  - Implement `_classify_label(score) -> str` using configurable thresholds
  - Implement `add_unsuppress_override()`, `is_unsuppressed()`, `clear_unsuppress_overrides()` for session-scoped unsuppress
  - Implement `purge_old_entries(older_than_hours=48) -> int`
  - Write tests in `backend/tests/test_intelligence/test_news_sentiment.py`: fetch_and_analyze_all caches results, get_sentiment_for_stock returns correct SentimentResult, NO_NEWS for unknown stock, composite score with recency weighting, label classification at all five threshold boundaries, unsuppress override management, purge delegation, batch query
  - Requirements: REQ-NSF-007, REQ-NSF-008, REQ-NSF-009, REQ-NSF-025

- [ ] 4.5 Implement `backend/signalpilot/intelligence/earnings.py`
  - Implement `EarningsCalendar` class accepting `EarningsCalendarRepository` and `AppConfig`
  - Implement `ingest_from_csv(csv_path) -> int`: parse CSV format `stock_code,earnings_date,quarter,is_confirmed`, upsert via repo
  - Implement `ingest_from_screener() -> int`: async scrape of Screener.in earnings page using `aiohttp`, with error handling
  - Implement `refresh() -> int`: run all configured ingestion sources, return total upserted
  - Handle missing CSV file (log warning, return 0), handle scrape failure (log warning, return 0)
  - Create placeholder CSV at `backend/data/earnings_calendar.csv` with header and a few sample rows
  - Write tests in `backend/tests/test_intelligence/test_earnings.py`: CSV ingestion with valid data, missing CSV handling, refresh calls all sources
  - Requirements: REQ-NSF-036, REQ-NSF-038

## 5. Pipeline Stage

- [ ] 5.1 Implement `backend/signalpilot/pipeline/stages/news_sentiment.py`
  - Create `NewsSentimentStage` class implementing the `PipelineStage` protocol as specified in Design Section 3.4
  - Constructor accepts: `news_sentiment_service`, `earnings_repo`, `config`
  - `name` property returns `"NewsSentiment"`
  - `process(ctx)` logic:
    1. Return ctx unchanged if `config.news_enabled` is False (kill switch)
    2. Return ctx immediately if `ctx.ranked_signals` is empty
    3. Batch fetch sentiment for all symbols via `get_sentiment_batch()`
    4. For each ranked signal: check earnings blackout first (highest priority), then check unsuppress override, then apply label-based action (suppress STRONG_NEGATIVE, downgrade MILD_NEGATIVE, pass-through NEUTRAL/POSITIVE/NO_NEWS)
    5. Populate `ctx.ranked_signals` (filtered), `ctx.suppressed_signals`, `ctx.sentiment_results`
  - Log summary: passed count, suppressed count
  - Write tests in `backend/tests/test_pipeline/test_news_sentiment_stage.py`:
    - Kill switch: `news_enabled=False` returns ctx unchanged
    - Empty signals: empty `ranked_signals` returns immediately
    - Suppression: STRONG_NEGATIVE removes signal, adds to `suppressed_signals`
    - Earnings blackout: earnings today suppresses regardless of sentiment
    - Earnings priority: earnings overrides positive sentiment
    - Downgrade: MILD_NEGATIVE reduces star rating by 1
    - Downgrade minimum: 1-star signal stays at 1
    - Pass-through: NEUTRAL, POSITIVE, NO_NEWS pass unchanged
    - Cache miss: unknown stock treated as NO_NEWS
    - Unsuppress override: overridden stock passes through with UNSUPPRESSED action
    - Multiple signals: mix of suppress/downgrade/pass in single batch
    - `sentiment_results` populated for every processed symbol
    - `suppressed_signals` list contains correct entries
  - Requirements: REQ-NSF-010, REQ-NSF-011, REQ-NSF-012, REQ-NSF-013, REQ-NSF-014, REQ-NSF-028, REQ-NSF-037, REQ-NSF-041

## 6. Telegram Enhancements

- [ ] 6.1 Add formatter functions in `backend/signalpilot/telegram/formatters.py`
  - Add `format_suppression_notification(suppressed: SuppressedSignal) -> str` function: include symbol, strategy, reason, sentiment score, top headlines, original signal details (entry, SL, target), and hint to use `NEWS {STOCK_CODE}`
  - Extend `format_signal_message()` signature with optional `news_sentiment_label: str | None = None` and `news_top_headline: str | None = None` parameters
  - When `news_sentiment_label == "MILD_NEGATIVE"`: prepend warning block with sentiment score and headline, show star rating note like "Strength: 3/5 (Downgraded from 4/5 due to news)"
  - When `news_sentiment_label == "POSITIVE"`: append positive news badge
  - When `news_sentiment_label == "NO_NEWS"`: append "No recent news" note
  - When `news_sentiment_label` is None or "NEUTRAL": no change to existing format
  - Write tests in `backend/tests/test_telegram/test_formatters_news.py`: suppression notification includes all required fields, downgraded signal has warning block, positive badge present, NO_NEWS note present, None/NEUTRAL format unchanged
  - Requirements: REQ-NSF-033, REQ-NSF-034, REQ-NSF-035

- [ ] 6.2 Implement NEWS, EARNINGS, and UNSUPPRESS Telegram commands
  - Add `handle_news_command` in `backend/signalpilot/telegram/bot.py` (or a new handlers file): query `NewsSentimentService` for stock-specific or ALL sentiment, format response with composite score, label, headline count, top 3 headlines with source and age
  - Add `handle_earnings_command`: query `EarningsCalendarRepository.get_upcoming_earnings(7)`, format grouped by date with stock code, quarter, confirmed/tentative status
  - Add `handle_unsuppress_command`: add stock to `NewsSentimentService` unsuppress override list, reply with confirmation including current sentiment details and expiry warning
  - Register all three commands as `MessageHandler` entries in `SignalPilotBot.start()` following the existing pattern (TAKEN, STATUS, JOURNAL, CAPITAL)
  - Write tests in `backend/tests/test_telegram/test_news_commands.py`: NEWS with valid stock returns sentiment, NEWS ALL returns summary table, NEWS with unknown stock returns error, EARNINGS returns formatted list, EARNINGS with no data returns info message, UNSUPPRESS adds override and confirms
  - Requirements: REQ-NSF-023, REQ-NSF-024, REQ-NSF-025

## 7. PersistAndDeliverStage Enhancement

- [ ] 7.1 Enhance `backend/signalpilot/pipeline/stages/persist_and_deliver.py`
  - In `_signal_to_record` (or equivalent): when `ctx.sentiment_results` contains an entry for the signal's symbol, set `news_sentiment_score`, `news_sentiment_label`, `news_top_headline`, `news_action`, and `original_star_rating` on the `SignalRecord` before DB insert
  - After signal delivery: iterate `ctx.suppressed_signals` and send each as a suppression notification via `self._bot.send_alert(format_suppression_notification(suppressed))`
  - When sentiment metadata is not available: all news fields remain None (backward compatible)
  - Write tests verifying: sentiment metadata persisted correctly on signal records, suppression notifications sent for each suppressed signal, no behavior change when sentiment_results is empty
  - Requirements: REQ-NSF-016

## 8. Scheduler and Lifecycle Integration

- [ ] 8.1 Add scheduler jobs in `backend/signalpilot/scheduler/scheduler.py`
  - Add pre-market news fetch job at 8:30 AM IST: `("pre_market_news", 8, 30, app.fetch_pre_market_news)` with `day_of_week='mon-fri'` and `_trading_day_guard`
  - Add two cache refresh jobs at 11:15 and 13:15 IST: `("news_cache_refresh_1", 11, 15, app.refresh_news_cache)` and `("news_cache_refresh_2", 13, 15, app.refresh_news_cache)` with same guards
  - Write tests verifying the new jobs are registered with correct times
  - Requirements: REQ-NSF-026, REQ-NSF-027

- [ ] 8.2 Add lifecycle methods in `backend/signalpilot/scheduler/lifecycle.py`
  - Add new constructor parameters: `news_sentiment_service=None`, `earnings_repo=None`, `earnings_calendar=None`, `news_sentiment_repo=None` (all default None for backward compat)
  - Store as instance attributes: `self._news_sentiment_service`, `self._earnings_repo`, `self._earnings_calendar`, `self._news_sentiment_repo`
  - Implement `async def fetch_pre_market_news()`: call `self._news_sentiment_service.fetch_and_analyze_all()`, handle failure gracefully (log error, proceed with NO_NEWS defaults), respect `news_enabled` kill switch
  - Implement `async def refresh_news_cache()`: call `self._news_sentiment_service.fetch_and_analyze_stocks()` with active scan list symbols, respect kill switch
  - Enhance `send_daily_summary()`: add cache purge call `self._news_sentiment_service.purge_old_entries(48)` and add `self._news_sentiment_service.clear_unsuppress_overrides()` after existing summary logic
  - Enhance `run_weekly_rebalance()`: add `self._earnings_calendar.refresh()` after existing rebalance logic
  - Update `_build_pipeline()`: insert `NewsSentimentStage(self._news_sentiment_service, self._earnings_repo, self._app_config)` after `RankingStage` and before `RiskSizingStage`
  - Import `NewsSentimentStage` at the top of the file
  - Write tests verifying: pipeline stage order is correct, fetch_pre_market_news calls service, refresh_news_cache calls service, daily summary purges cache, weekly rebalance refreshes earnings
  - Requirements: REQ-NSF-014, REQ-NSF-017, REQ-NSF-026, REQ-NSF-027, REQ-NSF-029, REQ-NSF-038

## 9. Application Wiring

- [ ] 9.1 Wire all new components in `backend/signalpilot/main.py` `create_app()`
  - Import new modules: `NewsSentimentRepository`, `EarningsCalendarRepository`, `NewsFetcher`, `VADERSentimentEngine`, `FinBERTSentimentEngine`, `NewsSentimentService`, `EarningsCalendar`, `NewsSentimentStage`
  - After existing repository setup: instantiate `NewsSentimentRepository(connection)` and `EarningsCalendarRepository(connection)`
  - Select sentiment engine based on `config.sentiment_model`: VADER (with `lexicon_path`) or FinBERT
  - Instantiate `NewsFetcher(config)`, `NewsSentimentService(news_fetcher, sentiment_engine, news_sentiment_repo, earnings_repo, config)`, `EarningsCalendar(earnings_repo, config)`
  - Pass new components to `SignalPilotApp` constructor: `news_sentiment_service`, `earnings_repo`, `earnings_calendar`, `news_sentiment_repo`
  - Pass `news_sentiment_service` and `earnings_repo` to `SignalPilotBot` constructor for NEWS/EARNINGS/UNSUPPRESS commands
  - Verify no existing stage constructors or argument lists are modified
  - Write a test verifying `create_app()` successfully creates an app with all news sentiment components wired
  - Requirements: REQ-NSF-017

- [ ] 9.2 Add new Python dependencies to `backend/pyproject.toml`
  - Add `vaderSentiment>=3.3.2`, `feedparser>=6.0.10`, `aiohttp>=3.9.0` to `[project.dependencies]`
  - Add optional `[project.optional-dependencies] finbert = ["transformers>=4.35.0", "torch>=2.0.0", "sentencepiece>=0.1.99"]`
  - Run `pip install -e ".[dev]"` to verify dependencies install correctly
  - Requirements: REQ-NSF-004, REQ-NSF-005 (dependencies)

## 10. Dashboard API Endpoints

- [ ] 10.1 Implement `backend/signalpilot/dashboard/routes/news.py`
  - Create `router = APIRouter()` for `/api/v1/news` routes
  - Implement `GET /{stock_code}` endpoint: query `NewsSentimentRepository`, return composite score, label, headline count, model used, and recent headlines list
  - Implement `GET /suppressed` endpoint: query signals table where `news_action IN ('SUPPRESSED', 'EARNINGS_BLACKOUT')`, support `date` and `limit` query parameters
  - Create `earnings_router = APIRouter()` for `/api/v1/earnings` routes
  - Implement `GET /upcoming` endpoint: query `EarningsCalendarRepository.get_upcoming_earnings()`, support configurable `days` parameter (default 14)
  - Register both routers in `backend/signalpilot/dashboard/app.py`
  - Write tests for all three endpoints: valid stock returns sentiment, unknown stock returns NO_NEWS, suppressed signals filtered by date, upcoming earnings returns correct range
  - Requirements: REQ-NSF-030, REQ-NSF-031, REQ-NSF-032

## 11. Integration Tests

- [ ] 11.1 Write pipeline integration tests in `backend/tests/test_integration/test_news_pipeline.py`
  - Add test fixtures: `sample_sentiment_result`, `sample_suppressed_signal` to conftest
  - Test full suppress flow: ranked signal with STRONG_NEGATIVE cache -> signal removed -> suppression notification sent -> signals table has `news_action="SUPPRESSED"` with sentiment columns populated
  - Test full downgrade flow: ranked signal with MILD_NEGATIVE cache -> star rating reduced by 1 -> signal delivered with warning -> signals table has `news_action="DOWNGRADED"`, `original_star_rating` set
  - Test full pass-through flow: ranked signal with POSITIVE cache -> signal delivered with positive badge -> signals table has `news_action="PASS"`, `news_sentiment_label="POSITIVE"`
  - Test earnings blackout flow: ranked signal with earnings today -> suppressed regardless of sentiment -> `news_action="EARNINGS_BLACKOUT"`
  - Test cache miss flow: ranked signal with no cached data -> passes through as NO_NEWS
  - Test feature disabled flow: `news_enabled=False` -> no sentiment processing -> all news columns None
  - Use `make_app()` helper from `tests/test_integration/conftest.py` with mock external dependencies
  - Verify persistence: check signals table contains correct `news_sentiment_score`, `news_sentiment_label`, `news_top_headline`, `news_action`, `original_star_rating`
  - Requirements: REQ-NSF-045, REQ-NSF-046

## 12. Test Fixtures and Shared Setup

- [ ] 12.1 Add shared test fixtures to `backend/tests/conftest.py`
  - Add `sample_sentiment_result` fixture returning a `SentimentResult` with MILD_NEGATIVE values
  - Add `sample_suppressed_signal` fixture returning a `SuppressedSignal` with STRONG_NEGATIVE values
  - Add `news_sentiment_repo` fixture using in-memory SQLite with news_sentiment table created
  - Add `earnings_repo` fixture using in-memory SQLite with earnings_calendar table created
  - Ensure the in-memory `db` fixture runs the news sentiment migration
  - Create `backend/tests/test_intelligence/__init__.py`
  - Requirements: REQ-NSF-045 (test infrastructure)
