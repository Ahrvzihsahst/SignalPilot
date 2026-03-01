# Task 4: Intelligence Module -- Core Services

## Description
Create the `backend/signalpilot/intelligence/` package with all core services: `SentimentEngine` protocol with VADER and FinBERT implementations, `NewsFetcher` for async RSS feed fetching, `NewsSentimentService` as the orchestrator, and `EarningsCalendar` for earnings date management. This is the largest task and forms the core business logic of the feature.

## Prerequisites
Task 1 (Data Models), Task 2 (Repository Layer), Task 3 (Configuration)

## Requirement Coverage
REQ-NSF-001, REQ-NSF-002, REQ-NSF-003, REQ-NSF-004, REQ-NSF-005, REQ-NSF-006, REQ-NSF-007, REQ-NSF-008, REQ-NSF-009, REQ-NSF-025, REQ-NSF-036, REQ-NSF-038, REQ-NSF-040, REQ-NSF-042

## Files to Create
- `signalpilot/intelligence/__init__.py`
- `signalpilot/intelligence/financial_lexicon.json`
- `signalpilot/intelligence/sentiment_engine.py`
- `signalpilot/intelligence/news_fetcher.py`
- `signalpilot/intelligence/news_sentiment.py`
- `signalpilot/intelligence/earnings.py`
- `data/earnings_calendar.csv`

## Subtasks

### 4.1 Create `backend/signalpilot/intelligence/__init__.py` and financial lexicon

- [x] Create the `backend/signalpilot/intelligence/` package with `__init__.py`
- [x] Create `backend/signalpilot/intelligence/financial_lexicon.json` with the 40+ term-score mappings from Design Section 6.3
- Requirement coverage: REQ-NSF-042

### 4.2 Implement `backend/signalpilot/intelligence/sentiment_engine.py`

- [x] Define `ScoredHeadline` dataclass with fields: `title`, `source`, `published_at`, `positive_score`, `negative_score`, `neutral_score`, `compound_score`, `model_used`
- [x] Define `SentimentEngine` protocol with `model_name` property, `analyze(text) -> ScoredHeadline`, and `analyze_batch(texts) -> list[ScoredHeadline]`
- [x] Implement `VADERSentimentEngine` class: load `vaderSentiment.SentimentIntensityAnalyzer`, optionally merge financial lexicon JSON via `analyzer.lexicon.update()`, implement `analyze()` mapping VADER's `polarity_scores()` to `ScoredHeadline`, implement `analyze_batch()` as sequential calls
- [x] Implement `FinBERTSentimentEngine` class: load `ProsusAI/finbert` via `transformers.pipeline`, implement `analyze()` and `analyze_batch()` mapping FinBERT outputs to `ScoredHeadline`
- [x] Handle missing lexicon file gracefully (log warning, use default VADER), handle malformed JSON gracefully
- [x] Write tests in `backend/tests/test_intelligence/test_sentiment_engine.py`: VADER positive/negative/neutral headlines, financial lexicon overlay strengthens scores, missing lexicon fallback, malformed lexicon fallback, protocol satisfaction by both implementations, batch analysis count
- Requirement coverage: REQ-NSF-004, REQ-NSF-005, REQ-NSF-006, REQ-NSF-042

### 4.3 Implement `backend/signalpilot/intelligence/news_fetcher.py`

- [x] Define `RawHeadline` dataclass with fields: `title`, `source`, `published_at`, `link`, `stock_codes`
- [x] Implement `NewsFetcher` class: accept `AppConfig`, parse feed URLs from `news_rss_feeds`, build symbol matching index from Nifty 500 list via `initialize(symbols)`
- [x] Implement `_fetch_feed(url) -> list[RawHeadline]` using `aiohttp` for async HTTP + `feedparser` for parsing, with 10s timeout per feed
- [x] Implement `_match_headline_to_stocks(headline) -> list[str]` using case-insensitive substring matching against company names and stock codes
- [x] Implement `fetch_all_stocks() -> dict[str, list[RawHeadline]]` fetching all configured feeds, matching headlines to stocks, filtering by lookback window, capping at `max_headlines_per_stock`, deduplicating near-identical headlines
- [x] Implement `fetch_stocks(symbols) -> dict[str, list[RawHeadline]]` for targeted refresh
- [x] Implement `close()` to close the `aiohttp.ClientSession`
- [x] Handle individual feed failures gracefully (log warning, continue with remaining feeds)
- [x] Write tests in `backend/tests/test_intelligence/test_news_fetcher.py`: valid RSS parsing, malformed XML handling, headline-to-stock matching, lookback filtering, headline cap enforcement, feed timeout handling, empty feed response, URL validation
- Requirement coverage: REQ-NSF-001, REQ-NSF-002, REQ-NSF-003, REQ-NSF-040

### 4.4 Implement `backend/signalpilot/intelligence/news_sentiment.py`

- [x] Implement `NewsSentimentService` class as specified in Design Section 3.3
- [x] Constructor accepts: `news_fetcher`, `sentiment_engine` (protocol), `news_sentiment_repo`, `earnings_repo`, `config`
- [x] Implement `fetch_and_analyze_all() -> int`: fetch all stocks, run sentiment engine, upsert to repo, return headline count
- [x] Implement `fetch_and_analyze_stocks(symbols) -> int`: same for subset
- [x] Implement `get_sentiment_for_stock(stock_code, lookback_hours) -> SentimentResult`: query repo, compute composite score with recency weighting (exponential decay, 6-hour half-life), classify label, build `SentimentResult`
- [x] Implement `get_sentiment_batch(symbols) -> dict[str, SentimentResult]`: batch version
- [x] Implement `_compute_composite_score(headlines) -> tuple[float, str]` with recency-weighted average: `weight_i = exp(-lambda * age_hours_i)` where `lambda = ln(2) / 6`
- [x] Implement `_classify_label(score) -> str` using configurable thresholds
- [x] Implement `add_unsuppress_override()`, `is_unsuppressed()`, `clear_unsuppress_overrides()` for session-scoped unsuppress
- [x] Implement `purge_old_entries(older_than_hours=48) -> int`
- [x] Write tests in `backend/tests/test_intelligence/test_news_sentiment.py`: fetch_and_analyze_all caches results, get_sentiment_for_stock returns correct SentimentResult, NO_NEWS for unknown stock, composite score with recency weighting, label classification at all five threshold boundaries, unsuppress override management, purge delegation, batch query
- Requirement coverage: REQ-NSF-007, REQ-NSF-008, REQ-NSF-009, REQ-NSF-025

### 4.5 Implement `backend/signalpilot/intelligence/earnings.py`

- [x] Implement `EarningsCalendar` class accepting `EarningsCalendarRepository` and `AppConfig`
- [x] Implement `ingest_from_csv(csv_path) -> int`: parse CSV format `stock_code,earnings_date,quarter,is_confirmed`, upsert via repo
- [x] Implement `ingest_from_screener() -> int`: async scrape of Screener.in earnings page using `aiohttp`, with error handling
- [x] Implement `refresh() -> int`: run all configured ingestion sources, return total upserted
- [x] Handle missing CSV file (log warning, return 0), handle scrape failure (log warning, return 0)
- [x] Create placeholder CSV at `backend/data/earnings_calendar.csv` with header and a few sample rows
- [x] Write tests in `backend/tests/test_intelligence/test_earnings.py`: CSV ingestion with valid data, missing CSV handling, refresh calls all sources
- Requirement coverage: REQ-NSF-036, REQ-NSF-038
