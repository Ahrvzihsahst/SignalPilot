# Requirements Document -- Phase 4: News Sentiment Filter

## Introduction

SignalPilot's existing strategies (Gap & Go, ORB, VWAP Reversal) are purely technical -- they analyze price, volume, and VWAP patterns but are blind to fundamental and news-driven events. This creates dangerous scenarios where the system generates buy signals on stocks undergoing SEBI investigations, fraud allegations, earnings misses, or other material negative events.

The News Sentiment Filter adds a pre-delivery intelligence layer that checks recent news sentiment for each ranked signal before it reaches the user. Signals associated with strongly negative news or same-day earnings are suppressed entirely; signals with mildly negative sentiment are downgraded by one star with a visible warning. The filter integrates as a single new pipeline stage (`NewsSentimentStage`) between `RankingStage` (stage 8) and `RiskSizingStage` (stage 9), ensuring that capital is never allocated to signals that will be blocked, and that sentiment metadata is available for persistence and formatting.

The feature introduces six new components under `backend/signalpilot/intelligence/` (keeping the feature isolated), two new SQLite tables (`news_sentiment`, `earnings_calendar`), five new nullable columns on the `signals` table, three new Telegram commands (NEWS, EARNINGS, UNSUPPRESS), three new FastAPI dashboard endpoints, and two new scheduler jobs (pre-market news fetch at 8:30 AM, 2-hour cache refresh during market hours).

All news fetching and sentiment inference happen outside the 1-second scan loop -- in scheduler jobs or background tasks -- so the pipeline stage only performs fast SQLite cache lookups (<10ms per signal cycle). The system supports FinBERT (higher accuracy, ~420MB) and VADER with a financial lexicon (lighter, <1MB) as interchangeable sentiment backends, with VADER recommended as the production default.

**Prerequisites:** Phase 1 (Gap & Go), Phase 2 (ORB + VWAP Reversal), Phase 3 (Hybrid Scoring + Dashboard), Phase 4 Quick Action Buttons complete and running live.

**Parent PRD:** `PRD_Phase4_News_Sentiment_Filter.md`

---

## 1. News Data Ingestion

### REQ-NSF-001: RSS Feed Ingestion

**User Story:** As a trader, I want the system to ingest financial news from multiple Indian market RSS feeds, so that it has broad coverage of market-moving headlines.

**Priority:** P0
**Dependencies:** None (new component)
**Components affected:** New `backend/signalpilot/intelligence/news_fetcher.py`

#### Acceptance Criteria

- [ ] WHEN the `NewsFetcher` is invoked THEN it SHALL fetch and parse RSS feeds from at least five Tier 1 sources: MoneyControl (`moneycontrol.com/rss/latestnews.xml`), Economic Times Markets, LiveMint Markets, Business Standard Markets, and NDTV Profit Stock Market.
- [ ] WHEN an RSS feed is fetched THEN the system SHALL extract the headline text, source name, publication timestamp, and link for each entry.
- [ ] WHEN an RSS feed is fetched THEN the system SHALL parse the publication timestamp into an IST-aware datetime using `ZoneInfo("Asia/Kolkata")`.
- [ ] IF an individual RSS feed fails to respond or returns invalid XML THEN the system SHALL log a warning and continue fetching from the remaining feeds without raising an exception.
- [ ] WHEN headlines are fetched THEN the system SHALL filter them to include only items published within a configurable lookback window (default: 24 hours).
- [ ] WHEN all feeds have been fetched THEN the system SHALL deduplicate headlines with identical or near-identical text from different sources.

---

### REQ-NSF-002: Stock-Specific News via Google News

**User Story:** As a trader, I want the system to query Google News for stock-specific headlines when no Tier 1 RSS results match a given stock, so that per-stock sentiment coverage is maximized.

**Priority:** P1
**Dependencies:** REQ-NSF-001
**Components affected:** `backend/signalpilot/intelligence/news_fetcher.py`

#### Acceptance Criteria

- [ ] WHEN stock-specific news is requested THEN the `NewsFetcher` SHALL query Google News RSS via `feedparser` using the query format `"{STOCK_NAME}" NSE` for the given stock.
- [ ] WHEN Google News results are returned THEN the system SHALL parse headlines, source, and publication timestamps using the same extraction logic as Tier 1 RSS feeds.
- [ ] IF the Google News query returns no results or fails THEN the system SHALL treat the stock as having no news (label `NO_NEWS`) and log the outcome.
- [ ] WHEN Google News is queried THEN the system SHALL respect rate limiting to avoid being blocked, using `TokenBucketRateLimiter` with configurable per-second and per-minute caps.

---

### REQ-NSF-003: NSE/BSE Corporate Announcements

**User Story:** As a trader, I want the system to check NSE and BSE corporate announcements for official filings (earnings results, board meetings, SEBI orders), so that material disclosures are included in sentiment evaluation.

**Priority:** P2
**Dependencies:** REQ-NSF-001
**Components affected:** `backend/signalpilot/intelligence/news_fetcher.py`

#### Acceptance Criteria

- [ ] WHEN stock-specific news is requested THEN the `NewsFetcher` SHALL query the NSE corporate announcements API for the given stock code.
- [ ] WHEN corporate announcements are available THEN the system SHALL extract the announcement subject, date, and category (e.g., "Board Meeting", "Financial Results", "SEBI Order").
- [ ] WHEN BSE corporate filings are accessible THEN the system SHALL also query the BSE API as a supplementary source.
- [ ] IF the NSE or BSE API is unreachable or returns an error THEN the system SHALL log a warning and proceed without that source, treating the data as unavailable rather than blocking the pipeline.

---

## 2. Sentiment Analysis

### REQ-NSF-004: FinBERT Sentiment Inference

**User Story:** As a trader, I want the system to analyze news headlines using a financial-domain sentiment model, so that sentiment classification is accurate for market-related language.

**Priority:** P0
**Dependencies:** REQ-NSF-001
**Components affected:** New `backend/signalpilot/intelligence/news_sentiment.py`

#### Acceptance Criteria

- [ ] WHEN the `NewsSentimentService` is configured with `sentiment_model="finbert"` THEN it SHALL load the FinBERT model from HuggingFace and keep it in memory for the application lifetime.
- [ ] WHEN a headline is passed to the FinBERT model THEN it SHALL return three probability scores: `positive`, `negative`, and `neutral`, each in the range [0.0, 1.0] summing to approximately 1.0.
- [ ] WHEN the input headline exceeds 512 tokens THEN the system SHALL truncate it to 512 tokens before inference.
- [ ] WHEN FinBERT inference runs THEN it SHALL complete within 100ms per headline on CPU (approximate target: ~50ms typical).
- [ ] WHEN the application starts with `sentiment_model="finbert"` THEN model loading SHALL complete and the service SHALL be ready before the first scheduler job runs.

---

### REQ-NSF-005: VADER Fallback Sentiment Engine

**User Story:** As a developer, I want a lightweight VADER-based sentiment fallback with a financial lexicon, so that the system can run on resource-constrained environments without FinBERT.

**Priority:** P0
**Dependencies:** REQ-NSF-001
**Components affected:** `backend/signalpilot/intelligence/news_sentiment.py`

#### Acceptance Criteria

- [ ] WHEN the `NewsSentimentService` is configured with `sentiment_model="vader"` THEN it SHALL use the VADER sentiment analyzer with a custom financial lexicon overlay.
- [ ] WHEN the financial lexicon is applied THEN it SHALL include domain-specific terms with sentiment scores: e.g., "SEBI probe" = -0.9, "record revenue" = +0.8, "fraud" = -1.0, "upgrade" = +0.7, "downgrade" = -0.7, and at least 20 additional financial terms.
- [ ] WHEN VADER processes a headline THEN it SHALL return `positive`, `negative`, and `neutral` scores normalized to [0.0, 1.0] to match the FinBERT output interface.
- [ ] WHEN VADER is used THEN inference SHALL complete in under 5ms per headline.
- [ ] WHEN VADER is configured THEN total memory usage of the model SHALL be under 1MB.
- [ ] WHEN either model backend is selected THEN the `NewsSentimentService` SHALL expose the same public API, so that downstream consumers (scoring, pipeline stage) are model-agnostic.

---

### REQ-NSF-006: Sentiment Model Selection Configuration

**User Story:** As a developer, I want to switch between FinBERT and VADER via configuration, so that the deployment can be tuned for available hardware.

**Priority:** P1
**Dependencies:** REQ-NSF-004, REQ-NSF-005
**Components affected:** `backend/signalpilot/config.py` (`AppConfig`)

#### Acceptance Criteria

- [ ] WHEN Phase 4 News Sentiment Filter is deployed THEN `AppConfig` SHALL include a `sentiment_model` field with allowed values `"finbert"` and `"vader"`, defaulting to `"vader"`.
- [ ] WHEN the `sentiment_model` config value is changed via `.env` THEN the system SHALL use the selected model on the next application restart.
- [ ] IF `sentiment_model` is set to an unrecognized value THEN the system SHALL fail fast at startup with a clear error message.

---

## 3. Sentiment Scoring Logic

### REQ-NSF-007: Per-Stock Composite Sentiment Score

**User Story:** As a trader, I want the system to compute a single composite sentiment score for each stock based on all recent headlines, so that signal modification decisions are based on aggregated sentiment rather than individual articles.

**Priority:** P0
**Dependencies:** REQ-NSF-004 or REQ-NSF-005, REQ-NSF-001
**Components affected:** `backend/signalpilot/intelligence/news_sentiment.py`

#### Acceptance Criteria

- [ ] WHEN sentiment scores are available for a stock's headlines THEN the system SHALL compute a composite score as `avg_positive - avg_negative`, where `avg_positive` and `avg_negative` are recency-weighted averages across all headlines.
- [ ] WHEN the composite score is calculated THEN it SHALL be in the range [-1.0, +1.0], where -1.0 is maximally negative and +1.0 is maximally positive.
- [ ] WHEN no headlines are found for a stock THEN the composite score SHALL be 0.0 and the label SHALL be `"NO_NEWS"`.
- [ ] WHEN the composite score is calculated THEN the system SHALL also record the headline count, the most negative headline, and the most positive headline for display purposes.

---

### REQ-NSF-008: Recency Weighting

**User Story:** As a trader, I want more recent news to have a greater influence on sentiment score, so that stale headlines from 20 hours ago do not overshadow breaking news.

**Priority:** P0
**Dependencies:** REQ-NSF-007
**Components affected:** `backend/signalpilot/intelligence/news_sentiment.py`

#### Acceptance Criteria

- [ ] WHEN calculating the weighted average sentiment THEN the system SHALL assign recency weights based on hours since publication: 0-2 hours = 1.0, 2-6 hours = 0.7, 6-12 hours = 0.4, 12-24 hours = 0.2.
- [ ] WHEN a headline's publication time is older than the configured lookback window (default 24 hours) THEN it SHALL be excluded from scoring entirely.
- [ ] WHEN all headlines for a stock have been weighted THEN the composite score SHALL be the weighted average, not the simple average, of the individual sentiment scores.

---

### REQ-NSF-009: Sentiment Label Classification

**User Story:** As a trader, I want each stock's sentiment to be classified into a discrete label, so that the pipeline stage can apply deterministic modification rules.

**Priority:** P0
**Dependencies:** REQ-NSF-007
**Components affected:** `backend/signalpilot/intelligence/news_sentiment.py`

#### Acceptance Criteria

- [ ] WHEN the composite score is less than -0.6 THEN the sentiment label SHALL be `"STRONG_NEGATIVE"`.
- [ ] WHEN the composite score is between -0.6 (inclusive) and -0.3 (exclusive) THEN the sentiment label SHALL be `"MILD_NEGATIVE"`.
- [ ] WHEN the composite score is between -0.3 (inclusive) and +0.3 (inclusive) THEN the sentiment label SHALL be `"NEUTRAL"`.
- [ ] WHEN the composite score is greater than +0.3 THEN the sentiment label SHALL be `"POSITIVE"`.
- [ ] WHEN no headlines exist for a stock THEN the sentiment label SHALL be `"NO_NEWS"`.
- [ ] WHEN the sentiment label thresholds are evaluated THEN they SHALL use the configurable thresholds from `AppConfig` (defaults: strong_negative < -0.6, mild_negative < -0.3, positive > +0.3).

---

## 4. Signal Modification Rules

### REQ-NSF-010: Signal Suppression on Strong Negative Sentiment

**User Story:** As a trader, I want signals on stocks with strongly negative news to be completely suppressed, so that I am never prompted to buy into a stock under investigation, fraud allegation, or similar material negative event.

**Priority:** P0
**Dependencies:** REQ-NSF-009, REQ-NSF-014 (pipeline stage)
**Components affected:** `backend/signalpilot/pipeline/stages/news_sentiment.py`

#### Acceptance Criteria

- [ ] WHEN a ranked signal's stock has sentiment label `"STRONG_NEGATIVE"` THEN the `NewsSentimentStage` SHALL remove that signal from `ctx.ranked_signals`.
- [ ] WHEN a signal is suppressed THEN the system SHALL add a `SuppressedSignal` entry to `ctx.suppressed_signals` containing the symbol, strategy, original star rating, sentiment score, sentiment label, top headline, and reason `"NEWS_SUPPRESSED"`.
- [ ] WHEN a signal is suppressed THEN the system SHALL log the suppression at INFO level with the symbol, sentiment score, and triggering headline.
- [ ] WHEN a signal is suppressed THEN the signal SHALL still be persisted to the `signals` table with `news_action="SUPPRESSED"` so that suppression outcomes can be tracked historically.

---

### REQ-NSF-011: Signal Suppression on Earnings Day

**User Story:** As a trader, I want signals on stocks with same-day earnings announcements to be suppressed, so that I avoid the unpredictable volatility surrounding earnings releases.

**Priority:** P0
**Dependencies:** REQ-NSF-025 (earnings calendar), REQ-NSF-014 (pipeline stage)
**Components affected:** `backend/signalpilot/pipeline/stages/news_sentiment.py`

#### Acceptance Criteria

- [ ] WHEN a ranked signal's stock has an earnings announcement scheduled for today (per the `earnings_calendar` table) THEN the `NewsSentimentStage` SHALL remove that signal from `ctx.ranked_signals`.
- [ ] WHEN a signal is suppressed due to earnings THEN the system SHALL add a `SuppressedSignal` entry with reason `"EARNINGS_BLACKOUT"` to `ctx.suppressed_signals`.
- [ ] WHEN a signal is suppressed due to earnings THEN the signal SHALL be persisted with `news_action="EARNINGS_BLACKOUT"`.
- [ ] WHEN earnings blackout is evaluated THEN the system SHALL check the `earnings_calendar` table using the current IST date and the signal's stock code.

---

### REQ-NSF-012: Signal Downgrade on Mild Negative Sentiment

**User Story:** As a trader, I want signals on stocks with mildly negative news to be delivered with a reduced star rating and a visible warning, so that I can make an informed decision with awareness of the negative sentiment.

**Priority:** P0
**Dependencies:** REQ-NSF-009, REQ-NSF-014 (pipeline stage)
**Components affected:** `backend/signalpilot/pipeline/stages/news_sentiment.py`

#### Acceptance Criteria

- [ ] WHEN a ranked signal's stock has sentiment label `"MILD_NEGATIVE"` THEN the `NewsSentimentStage` SHALL reduce the signal's `signal_strength` (star rating) by 1.
- [ ] WHEN a signal is downgraded THEN the system SHALL store the original star rating in the signal's `original_star_rating` field before modification.
- [ ] IF the signal's star rating is already 1 (minimum) THEN the downgrade SHALL keep the rating at 1 and still tag the warning.
- [ ] WHEN a signal is downgraded THEN the system SHALL attach the sentiment label, score, and top negative headline to the signal's metadata for formatting.
- [ ] WHEN a signal is downgraded THEN `news_action` SHALL be set to `"DOWNGRADED"`.

---

### REQ-NSF-013: Signal Pass-Through on Positive, Neutral, or No News

**User Story:** As a trader, I want signals on stocks with positive, neutral, or no news to pass through without modification, so that the filter does not interfere with technically valid signals in the absence of negative sentiment.

**Priority:** P0
**Dependencies:** REQ-NSF-009, REQ-NSF-014 (pipeline stage)
**Components affected:** `backend/signalpilot/pipeline/stages/news_sentiment.py`

#### Acceptance Criteria

- [ ] WHEN a ranked signal's stock has sentiment label `"NO_NEWS"` THEN the signal SHALL pass through unchanged with `news_action="PASS"`.
- [ ] WHEN a ranked signal's stock has sentiment label `"POSITIVE"` THEN the signal SHALL pass through unchanged with `news_action="PASS"`.
- [ ] WHEN a ranked signal's stock has sentiment label `"NEUTRAL"` THEN the signal SHALL pass through unchanged with `news_action="PASS"`.
- [ ] WHEN a signal passes through THEN the system SHALL attach the sentiment score and label to the signal's metadata so it can be displayed in the Telegram message format.

---

## 5. Pipeline Integration

### REQ-NSF-014: NewsSentimentStage Pipeline Stage

**User Story:** As a developer, I want the news sentiment filter implemented as a `PipelineStage` that slots between `RankingStage` and `RiskSizingStage`, so that it integrates cleanly with the existing composable pipeline architecture.

**Priority:** P0
**Dependencies:** REQ-NSF-007, REQ-NSF-009, REQ-NSF-010, REQ-NSF-011, REQ-NSF-012, REQ-NSF-013
**Components affected:** New `backend/signalpilot/pipeline/stages/news_sentiment.py`, `backend/signalpilot/scheduler/lifecycle.py` (pipeline build order)

#### Acceptance Criteria

- [ ] WHEN the pipeline is constructed THEN the `NewsSentimentStage` SHALL be inserted after `RankingStage` (stage 8) and before `RiskSizingStage` (stage 9).
- [ ] WHEN the `NewsSentimentStage` implements the `PipelineStage` protocol THEN it SHALL expose a `name` property returning `"NewsSentiment"` and an `async def process(self, ctx: ScanContext) -> ScanContext` method.
- [ ] WHEN `ctx.ranked_signals` is empty THEN the stage SHALL return the context immediately without performing any lookups (zero overhead when no signals are present).
- [ ] WHEN `ctx.ranked_signals` contains signals THEN the stage SHALL look up cached sentiment for each signal's symbol from `NewsSentimentRepository` (SQLite indexed lookup).
- [ ] WHEN a cache miss occurs for a symbol THEN the stage SHALL treat it as `NO_NEWS` (pass through) and queue a background re-fetch for the next cycle, without blocking the scan loop.
- [ ] WHEN the stage completes THEN `ctx.sentiment_results` SHALL contain a `dict[str, SentimentResult]` mapping each processed symbol to its sentiment result.
- [ ] WHEN the stage completes THEN `ctx.suppressed_signals` SHALL contain a `list[SuppressedSignal]` for all signals that were removed.
- [ ] WHEN the `NewsSentimentStage` is absent from the pipeline (e.g., feature disabled) THEN all other stages SHALL behave identically to the pre-feature baseline due to the optional default values on `ScanContext`.

---

### REQ-NSF-015: ScanContext Extension

**User Story:** As a developer, I want `ScanContext` extended with optional sentiment fields, so that sentiment data flows through the pipeline without breaking existing stages.

**Priority:** P0
**Dependencies:** REQ-NSF-014
**Components affected:** `backend/signalpilot/pipeline/context.py`

#### Acceptance Criteria

- [ ] WHEN Phase 4 News Sentiment Filter is deployed THEN `ScanContext` SHALL include a new field `sentiment_results: dict[str, SentimentResult]` defaulting to an empty dict.
- [ ] WHEN Phase 4 News Sentiment Filter is deployed THEN `ScanContext` SHALL include a new field `suppressed_signals: list[SuppressedSignal]` defaulting to an empty list.
- [ ] WHEN the `NewsSentimentStage` is not present in the pipeline THEN the default values of these fields SHALL ensure no behavioral change in any existing stage.
- [ ] WHEN `SentimentResult` is defined THEN it SHALL be a dataclass with fields: `score: float`, `label: str`, `headline: str | None`, `action: str`, and `headline_count: int`.
- [ ] WHEN `SuppressedSignal` is defined THEN it SHALL be a dataclass with fields: `symbol: str`, `strategy: str`, `original_stars: int`, `sentiment_score: float`, `sentiment_label: str`, `top_headline: str | None`, `reason: str`, and `entry_price: float`.

---

### REQ-NSF-016: PersistAndDeliverStage Enhancement

**User Story:** As a developer, I want `PersistAndDeliverStage` to persist sentiment metadata on each signal record and send suppression notifications, so that all sentiment decisions are traceable in the database and visible to the user.

**Priority:** P0
**Dependencies:** REQ-NSF-014, REQ-NSF-015, REQ-NSF-021 (DB columns)
**Components affected:** `backend/signalpilot/pipeline/stages/persist_and_deliver.py`

#### Acceptance Criteria

- [ ] WHEN a signal is persisted and `ctx.sentiment_results` contains an entry for the signal's symbol THEN `PersistAndDeliverStage` SHALL set `news_sentiment_score`, `news_sentiment_label`, `news_top_headline`, `news_action`, and `original_star_rating` on the `SignalRecord` before DB insert.
- [ ] WHEN `ctx.suppressed_signals` is not empty THEN `PersistAndDeliverStage` SHALL send a suppression notification message via the Telegram bot for each suppressed signal after signal delivery completes.
- [ ] WHEN sentiment metadata is not available (feature disabled or empty `sentiment_results`) THEN the existing persistence logic SHALL behave identically to the pre-feature baseline with all news fields as `None`.

---

### REQ-NSF-017: Pipeline Wiring in create_app

**User Story:** As a developer, I want all new news sentiment components instantiated and wired in `create_app()` following the existing dependency-injection pattern, so that the feature is cleanly integrated into the application lifecycle.

**Priority:** P0
**Dependencies:** REQ-NSF-014, REQ-NSF-019, REQ-NSF-020
**Components affected:** `backend/signalpilot/main.py`

#### Acceptance Criteria

- [ ] WHEN the application starts THEN `create_app()` SHALL instantiate `NewsSentimentRepository(connection)` and `EarningsCalendarRepository(connection)` after existing repository setup.
- [ ] WHEN the application starts THEN `create_app()` SHALL instantiate `NewsFetcher(config)` and `NewsSentimentService(news_fetcher, news_sentiment_repo, earnings_repo, config)` after existing component setup.
- [ ] WHEN the pipeline is built THEN `NewsSentimentStage(news_sentiment_service, earnings_repo, bot)` SHALL be inserted into the `signal_stages` list immediately after `RankingStage` and before `RiskSizingStage`.
- [ ] WHEN the stage is wired THEN no existing stage constructors or argument lists SHALL be modified.

---

## 6. Database Schema

### REQ-NSF-018: News Sentiment Table

**User Story:** As a developer, I want a `news_sentiment` table to cache headline-level sentiment data, so that the pipeline stage can perform fast indexed lookups instead of real-time API calls.

**Priority:** P0
**Dependencies:** None (new table)
**Components affected:** New `backend/signalpilot/db/news_sentiment_repo.py`, `backend/signalpilot/db/database.py` (migration)

#### Acceptance Criteria

- [ ] WHEN the database is initialized THEN a `news_sentiment` table SHALL be created with columns: `id` (INTEGER PRIMARY KEY AUTOINCREMENT), `stock_code` (TEXT NOT NULL), `headline` (TEXT NOT NULL), `source` (TEXT NOT NULL), `published_at` (DATETIME NOT NULL), `positive_score` (REAL), `negative_score` (REAL), `neutral_score` (REAL), `composite_score` (REAL), `sentiment_label` (TEXT), `fetched_at` (DATETIME DEFAULT CURRENT_TIMESTAMP), `model_used` (TEXT DEFAULT 'vader').
- [ ] WHEN the `news_sentiment` table is created THEN an index `idx_news_stock_date` SHALL be created on `(stock_code, published_at)` for fast lookups.
- [ ] WHEN the `NewsSentimentRepository` queries cached sentiment THEN it SHALL use the indexed `stock_code` and `published_at` columns to retrieve headlines within the lookback window.

---

### REQ-NSF-019: Earnings Calendar Table

**User Story:** As a developer, I want an `earnings_calendar` table to store upcoming earnings dates for Nifty 500 stocks, so that earnings blackout detection can be performed via a fast local lookup.

**Priority:** P0
**Dependencies:** None (new table)
**Components affected:** New `backend/signalpilot/db/earnings_repo.py`, `backend/signalpilot/db/database.py` (migration)

#### Acceptance Criteria

- [ ] WHEN the database is initialized THEN an `earnings_calendar` table SHALL be created with columns: `id` (INTEGER PRIMARY KEY AUTOINCREMENT), `stock_code` (TEXT NOT NULL), `earnings_date` (DATE NOT NULL), `quarter` (TEXT), `source` (TEXT), `is_confirmed` (BOOLEAN DEFAULT 0), `updated_at` (DATETIME DEFAULT CURRENT_TIMESTAMP).
- [ ] WHEN the `earnings_calendar` table is created THEN an index `idx_earnings_date` SHALL be created on `(earnings_date)`.
- [ ] WHEN the `EarningsCalendarRepository` is queried for today's earnings THEN it SHALL return all stock codes with `earnings_date` equal to the current IST date.
- [ ] WHEN earnings data is inserted or updated THEN the `updated_at` timestamp SHALL use `datetime.now(IST)`.

---

### REQ-NSF-020: News Sentiment Repository

**User Story:** As a developer, I want a `NewsSentimentRepository` following the existing repository pattern, so that sentiment data access is consistent with the rest of the codebase.

**Priority:** P0
**Dependencies:** REQ-NSF-018
**Components affected:** New `backend/signalpilot/db/news_sentiment_repo.py`

#### Acceptance Criteria

- [ ] WHEN the `NewsSentimentRepository` is instantiated THEN it SHALL accept an `aiosqlite.Connection` as its constructor parameter, following the same pattern as `SignalRepository`, `TradeRepository`, and `ConfigRepository`.
- [ ] WHEN `upsert_headlines(stock_code, headlines)` is called THEN it SHALL insert or replace headline sentiment records for the given stock, using `(stock_code, headline, source)` as the conflict key.
- [ ] WHEN `get_stock_sentiment(stock_code, lookback_hours)` is called THEN it SHALL return all cached headlines for that stock within the lookback window, ordered by `published_at` descending.
- [ ] WHEN `get_composite_score(stock_code, lookback_hours)` is called THEN it SHALL return the pre-computed composite score and label for the stock based on cached data.
- [ ] WHEN `purge_old_entries(older_than_hours)` is called THEN it SHALL delete all rows where `fetched_at` is older than the specified threshold.
- [ ] WHEN any repository method executes THEN it SHALL use async operations via `aiosqlite`.

---

### REQ-NSF-021: Signals Table Column Additions

**User Story:** As a developer, I want five new nullable columns on the `signals` table to persist sentiment metadata per signal, so that sentiment decisions are queryable for performance analysis and dashboard display.

**Priority:** P0
**Dependencies:** REQ-NSF-018
**Components affected:** `backend/signalpilot/db/database.py` (migration), `backend/signalpilot/db/models.py`

#### Acceptance Criteria

- [ ] WHEN the news sentiment migration runs THEN it SHALL add five columns to the `signals` table: `news_sentiment_score` (REAL), `news_sentiment_label` (TEXT), `news_top_headline` (TEXT), `news_action` (TEXT), and `original_star_rating` (INTEGER), all nullable.
- [ ] WHEN the migration runs THEN it SHALL use the idempotent `PRAGMA table_info()` check-before-alter pattern established by Phase 2/3/4 migrations in `DatabaseManager._run_news_sentiment_migration()`.
- [ ] WHEN `SignalRecord` is updated THEN it SHALL include five new optional fields: `news_sentiment_score: float | None = None`, `news_sentiment_label: str | None = None`, `news_top_headline: str | None = None`, `news_action: str | None = None`, `original_star_rating: int | None = None`.
- [ ] WHEN `_row_to_record()` in `SignalRepository` processes a row THEN it SHALL handle backward compatibility for the new columns using the existing Phase 3 optional-column pattern.
- [ ] WHEN the `news_action` column is populated THEN it SHALL contain one of: `"PASS"`, `"DOWNGRADED"`, `"SUPPRESSED"`, or `"EARNINGS_BLACKOUT"`.

---

### REQ-NSF-022: Earnings Calendar Repository

**User Story:** As a developer, I want an `EarningsCalendarRepository` for managing earnings date lookups, so that blackout detection queries are encapsulated in a repository.

**Priority:** P0
**Dependencies:** REQ-NSF-019
**Components affected:** New `backend/signalpilot/db/earnings_repo.py`

#### Acceptance Criteria

- [ ] WHEN the `EarningsCalendarRepository` is instantiated THEN it SHALL accept an `aiosqlite.Connection` as its constructor parameter.
- [ ] WHEN `has_earnings_today(stock_code)` is called THEN it SHALL return `True` if the stock has an entry in `earnings_calendar` with `earnings_date` equal to today's IST date, `False` otherwise.
- [ ] WHEN `get_upcoming_earnings(days_ahead)` is called THEN it SHALL return all earnings entries within the specified number of days, ordered by `earnings_date` ascending.
- [ ] WHEN `upsert_earnings(stock_code, earnings_date, quarter, source, is_confirmed)` is called THEN it SHALL insert or update the earnings entry using `(stock_code, earnings_date)` as the conflict key.
- [ ] WHEN any repository method executes THEN it SHALL use async operations via `aiosqlite`.

---

## 7. Telegram Commands

### REQ-NSF-023: NEWS Command

**User Story:** As a trader, I want to send `NEWS TATAMOTORS` to see the latest sentiment analysis for a stock, so that I can check news before manually deciding to take a signal.

**Priority:** P1
**Dependencies:** REQ-NSF-007, REQ-NSF-020
**Components affected:** `backend/signalpilot/telegram/bot.py`, new handler in existing command registration pattern

#### Acceptance Criteria

- [ ] WHEN a user sends `NEWS {STOCK_CODE}` THEN the bot SHALL query the `NewsSentimentRepository` for the stock's cached sentiment and reply with the composite score, sentiment label, headline count, and the top 3 most recent headlines with source and age.
- [ ] WHEN a user sends `NEWS ALL` THEN the bot SHALL display a summary table of sentiment labels for all stocks currently on the active scan list, sorted by composite score ascending (most negative first).
- [ ] IF the stock code is not recognized or has no cached data THEN the bot SHALL reply with a message indicating no news data is available and suggest checking the stock code.
- [ ] WHEN the NEWS command is handled THEN it SHALL be registered as a `MessageHandler` in `SignalPilotBot.start()` following the same pattern as TAKEN, STATUS, JOURNAL, and CAPITAL commands.

---

### REQ-NSF-024: EARNINGS Command

**User Story:** As a trader, I want to send `EARNINGS` to see upcoming earnings dates for Nifty 500 stocks, so that I can plan around earnings blackout periods.

**Priority:** P1
**Dependencies:** REQ-NSF-022
**Components affected:** `backend/signalpilot/telegram/bot.py`

#### Acceptance Criteria

- [ ] WHEN a user sends `EARNINGS` THEN the bot SHALL query `EarningsCalendarRepository.get_upcoming_earnings(days_ahead=7)` and reply with a formatted list of stocks with earnings in the next 7 days, grouped by date.
- [ ] WHEN the earnings list is displayed THEN each entry SHALL show the stock code, earnings date, quarter (e.g., "Q3FY26"), and whether the date is confirmed or tentative.
- [ ] IF no upcoming earnings are found THEN the bot SHALL reply indicating no Nifty 500 earnings are scheduled in the next 7 days.
- [ ] WHEN the EARNINGS command is handled THEN it SHALL be registered as a `MessageHandler` following the existing command pattern.

---

### REQ-NSF-025: UNSUPPRESS Command

**User Story:** As an experienced trader, I want to override news suppression for a specific stock using `UNSUPPRESS TATAMOTORS`, so that I can take a signal on a stock I believe is being incorrectly filtered.

**Priority:** P2
**Dependencies:** REQ-NSF-010, REQ-NSF-020
**Components affected:** `backend/signalpilot/telegram/bot.py`, `backend/signalpilot/intelligence/news_sentiment.py`

#### Acceptance Criteria

- [ ] WHEN a user sends `UNSUPPRESS {STOCK_CODE}` THEN the system SHALL add the stock to an in-memory unsuppress override list for the current trading session.
- [ ] WHEN a stock is on the unsuppress override list THEN the `NewsSentimentStage` SHALL treat that stock as `NO_NEWS` (pass through) regardless of its actual sentiment score.
- [ ] WHEN a signal passes through due to an unsuppress override THEN the `news_action` SHALL be set to `"UNSUPPRESSED"` and a warning SHALL be included in the Telegram message.
- [ ] WHEN the trading day ends (15:30 IST) THEN the unsuppress override list SHALL be cleared automatically.
- [ ] WHEN the UNSUPPRESS command is handled THEN the bot SHALL reply confirming the override and warn the user about the negative sentiment details.

---

## 8. Caching and Performance

### REQ-NSF-026: Pre-Market News Fetch Scheduler Job

**User Story:** As a trader, I want the system to bulk-fetch and cache news for all Nifty 500 stocks before market open, so that sentiment data is warm and available when the first signals start flowing at 9:15 AM.

**Priority:** P0
**Dependencies:** REQ-NSF-001, REQ-NSF-020
**Components affected:** `backend/signalpilot/scheduler/scheduler.py`, `backend/signalpilot/intelligence/news_sentiment.py`

#### Acceptance Criteria

- [ ] WHEN 8:30 AM IST arrives on a trading day THEN the `MarketScheduler` SHALL trigger a `fetch_pre_market_news()` job that fetches headlines for all Nifty 500 stocks, runs sentiment analysis, and caches results in the `news_sentiment` table.
- [ ] WHEN the pre-market job is scheduled THEN it SHALL use `day_of_week='mon-fri'` and the `_trading_day_guard` decorator to skip NSE holidays, following the existing scheduler pattern.
- [ ] WHEN the pre-market fetch completes THEN all Nifty 500 stocks SHALL have cached sentiment data available before the 9:15 AM market open.
- [ ] IF the pre-market fetch job fails or times out THEN the system SHALL log an error and proceed with NO_NEWS defaults for all stocks (never block market open).

---

### REQ-NSF-027: Background Cache Refresh

**User Story:** As a trader, I want the sentiment cache to be refreshed every 2 hours during market hours, so that news developments during the trading session are reflected in sentiment scores.

**Priority:** P1
**Dependencies:** REQ-NSF-026
**Components affected:** `backend/signalpilot/scheduler/scheduler.py`

#### Acceptance Criteria

- [ ] WHEN market hours are active THEN the `MarketScheduler` SHALL trigger a `refresh_news_cache()` job every 2 hours (e.g., at 11:15, 13:15) to refresh cached sentiment for stocks on the active scan list.
- [ ] WHEN the refresh job runs THEN it SHALL update the `news_sentiment` table with newly fetched headlines and recomputed sentiment scores.
- [ ] WHEN the refresh job is scheduled THEN it SHALL use `day_of_week='mon-fri'` and the `_trading_day_guard` decorator.
- [ ] IF the refresh job fails THEN the system SHALL continue using the existing cached data and log a warning.

---

### REQ-NSF-028: Scan Loop Safety

**User Story:** As a developer, I want the `NewsSentimentStage` to never block the 1-second scan loop with network I/O, so that signal detection latency is unaffected by the news feature.

**Priority:** P0
**Dependencies:** REQ-NSF-014
**Components affected:** `backend/signalpilot/pipeline/stages/news_sentiment.py`

#### Acceptance Criteria

- [ ] WHEN the `NewsSentimentStage` processes signals THEN it SHALL only perform SQLite cache lookups (indexed reads), never network calls to RSS feeds or inference APIs.
- [ ] WHEN a cache miss occurs for a symbol THEN the stage SHALL treat it as `NO_NEWS` and return immediately, scheduling a background re-fetch for the next scan cycle.
- [ ] WHEN the stage processes signals with cache hits THEN total execution time SHALL be under 10ms per signal cycle (benchmark target: <2ms per symbol lookup).
- [ ] WHEN the `NewsSentimentStage` runs THEN it SHALL NOT create any new async tasks that perform network I/O within the scan loop context.

---

### REQ-NSF-029: Cache Expiry and Cleanup

**User Story:** As a developer, I want old sentiment cache entries to be purged periodically, so that the SQLite database does not grow unbounded.

**Priority:** P1
**Dependencies:** REQ-NSF-020
**Components affected:** `backend/signalpilot/db/news_sentiment_repo.py`, `backend/signalpilot/scheduler/scheduler.py`

#### Acceptance Criteria

- [ ] WHEN the daily summary job runs (15:30 IST) THEN the system SHALL purge `news_sentiment` entries where `fetched_at` is older than 48 hours.
- [ ] WHEN purging old entries THEN the system SHALL log the number of rows deleted.
- [ ] WHEN the cache is queried THEN entries older than the configured lookback window (default 24 hours) SHALL be excluded from scoring regardless of whether they have been purged.

---

## 9. API Endpoints (FastAPI Dashboard)

### REQ-NSF-030: Stock Sentiment API

**User Story:** As a dashboard user, I want an API endpoint to retrieve sentiment analysis for a specific stock, so that the dashboard can display news sentiment alongside technical signal data.

**Priority:** P2
**Dependencies:** REQ-NSF-020
**Components affected:** New `backend/signalpilot/dashboard/routes/news.py`, `backend/signalpilot/dashboard/app.py`

#### Acceptance Criteria

- [ ] WHEN a GET request is made to `/api/v1/news/{stock_code}` THEN the API SHALL return JSON containing the composite score, sentiment label, headline count, model used, and a list of recent headlines with individual scores and timestamps.
- [ ] IF the stock code has no cached sentiment data THEN the API SHALL return a 200 response with `label: "NO_NEWS"` and an empty headlines list.
- [ ] WHEN the route module is created THEN it SHALL be registered in `backend/signalpilot/dashboard/app.py` following the same pattern as existing route modules (performance, signals, strategies).

---

### REQ-NSF-031: Suppressed Signals API

**User Story:** As a dashboard user, I want an API endpoint to list all suppressed signals with their suppression reasons, so that I can review what the filter blocked.

**Priority:** P2
**Dependencies:** REQ-NSF-021
**Components affected:** `backend/signalpilot/dashboard/routes/news.py`

#### Acceptance Criteria

- [ ] WHEN a GET request is made to `/api/v1/news/suppressed` THEN the API SHALL return JSON containing all signals from the `signals` table where `news_action` is `"SUPPRESSED"` or `"EARNINGS_BLACKOUT"`, ordered by creation date descending.
- [ ] WHEN suppressed signals are returned THEN each entry SHALL include the symbol, strategy, original star rating, sentiment score, top headline, news action, and signal timestamp.
- [ ] WHEN the endpoint supports query parameters THEN it SHALL accept optional `date` (ISO format) and `limit` (default 50) filters.

---

### REQ-NSF-032: Upcoming Earnings API

**User Story:** As a dashboard user, I want an API endpoint to retrieve the upcoming earnings calendar, so that the dashboard can display which stocks are in blackout periods.

**Priority:** P2
**Dependencies:** REQ-NSF-022
**Components affected:** `backend/signalpilot/dashboard/routes/news.py`

#### Acceptance Criteria

- [ ] WHEN a GET request is made to `/api/v1/earnings/upcoming` THEN the API SHALL return JSON containing all earnings entries within the next 14 days (configurable via `days` query parameter), ordered by `earnings_date` ascending.
- [ ] WHEN earnings entries are returned THEN each entry SHALL include `stock_code`, `earnings_date`, `quarter`, `source`, and `is_confirmed`.
- [ ] IF no upcoming earnings are found THEN the API SHALL return a 200 response with an empty list.

---

## 10. Formatter Enhancements

### REQ-NSF-033: Downgraded Signal Formatting

**User Story:** As a trader, I want downgraded signals to include a visible news warning block with the triggering headline, so that I can see exactly why the signal was downgraded.

**Priority:** P0
**Dependencies:** REQ-NSF-012, REQ-NSF-016
**Components affected:** `backend/signalpilot/telegram/formatters.py`

#### Acceptance Criteria

- [ ] WHEN `format_signal_message()` is called with `news_sentiment_label="MILD_NEGATIVE"` THEN the formatted message SHALL include a warning block prepended before the signal details, containing the sentiment score and the top negative headline with source and age.
- [ ] WHEN a signal is downgraded THEN the star rating line SHALL show the reduced rating with a note indicating the original rating (e.g., "Strength: 3/5 (Downgraded from 4/5 due to news)").
- [ ] WHEN `format_signal_message()` receives `news_sentiment_label=None` or `news_sentiment_label="NEUTRAL"` THEN the existing format SHALL be unchanged.
- [ ] WHEN the formatter signature is extended THEN it SHALL add two optional parameters: `news_sentiment_label: str | None = None` and `news_top_headline: str | None = None`, with no changes to the existing parameter list.

---

### REQ-NSF-034: Positive News Badge

**User Story:** As a trader, I want signals on stocks with positive news to include a brief positive sentiment badge, so that I have additional confidence in technically valid setups with favorable news.

**Priority:** P1
**Dependencies:** REQ-NSF-013
**Components affected:** `backend/signalpilot/telegram/formatters.py`

#### Acceptance Criteria

- [ ] WHEN `format_signal_message()` is called with `news_sentiment_label="POSITIVE"` THEN the formatted message SHALL include a positive news badge appended after the signal details (e.g., "Positive news sentiment").
- [ ] WHEN `format_signal_message()` is called with `news_sentiment_label="NO_NEWS"` THEN the formatted message SHALL include a neutral informational note (e.g., "No recent news").

---

### REQ-NSF-035: Suppression Notification Formatting

**User Story:** As a trader, I want to receive an informational notification when a signal is suppressed, so that I know the system detected a setup but chose not to deliver it due to negative news.

**Priority:** P0
**Dependencies:** REQ-NSF-010, REQ-NSF-011, REQ-NSF-016
**Components affected:** `backend/signalpilot/telegram/formatters.py`

#### Acceptance Criteria

- [ ] WHEN a suppressed signal notification is formatted THEN it SHALL include: the stock symbol, the strategy that generated the signal, the suppression reason (`NEWS_SUPPRESSED` or `EARNINGS_BLACKOUT`), the sentiment score (for news-based suppression), the top negative headlines with source and age, the original signal details (entry, SL, target) for reference only, and a hint to use the `NEWS {STOCK_CODE}` command.
- [ ] WHEN the notification is formatted THEN it SHALL be clearly marked as informational and not actionable (e.g., "SIGNAL SUPPRESSED" header).
- [ ] WHEN a `format_suppression_notification(suppressed: SuppressedSignal)` function is created THEN it SHALL accept a `SuppressedSignal` dataclass and return a formatted string.

---

## 11. Earnings Calendar and Blackout Logic

### REQ-NSF-036: Earnings Date Ingestion

**User Story:** As a developer, I want the system to ingest earnings dates from multiple sources (Screener.in, manual CSV, TradingView), so that the earnings calendar is populated for blackout detection.

**Priority:** P1
**Dependencies:** REQ-NSF-019, REQ-NSF-022
**Components affected:** New `backend/signalpilot/intelligence/earnings.py`

#### Acceptance Criteria

- [ ] WHEN the `EarningsCalendar` service is initialized THEN it SHALL support ingesting earnings dates from at least two sources: a local CSV file (manually maintained) and an automated web source (e.g., Screener.in scrape).
- [ ] WHEN earnings dates are ingested THEN they SHALL be upserted into the `earnings_calendar` table via `EarningsCalendarRepository`.
- [ ] WHEN an earnings date is ingested THEN the `source` field SHALL indicate the origin (e.g., `"screener.in"`, `"manual_csv"`, `"tradingview"`).
- [ ] WHEN both confirmed and tentative dates are available THEN the `is_confirmed` field SHALL distinguish between them.

---

### REQ-NSF-037: Earnings Blackout Window

**User Story:** As a trader, I want stocks with same-day earnings to be automatically blocked from signal generation, so that I avoid unpredictable post-earnings volatility.

**Priority:** P0
**Dependencies:** REQ-NSF-011, REQ-NSF-022, REQ-NSF-036
**Components affected:** `backend/signalpilot/pipeline/stages/news_sentiment.py`

#### Acceptance Criteria

- [ ] WHEN the `NewsSentimentStage` evaluates a ranked signal THEN it SHALL check `EarningsCalendarRepository.has_earnings_today(stock_code)` using the current IST date.
- [ ] IF a stock has earnings today THEN the signal SHALL be suppressed with reason `"EARNINGS_BLACKOUT"` regardless of the stock's news sentiment score.
- [ ] WHEN an earnings blackout suppression occurs THEN it SHALL take priority over any sentiment-based action (i.e., even if sentiment is POSITIVE, earnings day still triggers suppression).
- [ ] WHEN evaluating earnings blackout THEN the check SHALL use `datetime.now(IST).date()` for the date comparison, never naive `datetime.now()`.

---

### REQ-NSF-038: Weekly Earnings Calendar Update

**User Story:** As a developer, I want the earnings calendar refreshed weekly, so that newly announced earnings dates are captured.

**Priority:** P2
**Dependencies:** REQ-NSF-036
**Components affected:** `backend/signalpilot/scheduler/scheduler.py`, `backend/signalpilot/intelligence/earnings.py`

#### Acceptance Criteria

- [ ] WHEN the weekly rebalance job runs (Sundays 18:00 IST) THEN the system SHALL also trigger an earnings calendar refresh that fetches updated earnings dates and upserts them into the `earnings_calendar` table.
- [ ] IF the earnings calendar refresh fails THEN the system SHALL log a warning and retain the existing calendar data.
- [ ] WHEN the refresh completes THEN it SHALL log the count of new and updated earnings entries.

---

## 12. Configuration

### REQ-NSF-039: AppConfig News Sentiment Parameters

**User Story:** As a developer, I want all news sentiment thresholds and parameters configurable via `AppConfig` and `.env`, so that tuning can be done without code changes.

**Priority:** P0
**Dependencies:** Phase 1 `AppConfig` (`backend/signalpilot/config.py`)
**Components affected:** `backend/signalpilot/config.py`

#### Acceptance Criteria

- [ ] WHEN Phase 4 News Sentiment Filter is deployed THEN `AppConfig` SHALL include the following new fields with specified defaults:
  - `sentiment_model` (str, default `"vader"`) -- `"finbert"` or `"vader"`
  - `news_lookback_hours` (int, default `24`) -- how far back to fetch headlines
  - `news_cache_ttl_hours` (int, default `2`) -- cache refresh interval
  - `strong_negative_threshold` (float, default `-0.6`) -- composite score below which signals are suppressed
  - `mild_negative_threshold` (float, default `-0.3`) -- composite score below which signals are downgraded
  - `positive_threshold` (float, default `0.3`) -- composite score above which positive badge is shown
  - `news_enabled` (bool, default `True`) -- feature kill switch
  - `earnings_blackout_enabled` (bool, default `True`) -- earnings blackout kill switch
  - `news_pre_market_fetch_time` (str, default `"08:30"`) -- cron time for pre-market fetch
  - `news_max_headlines_per_stock` (int, default `10`) -- cap headlines per stock to limit inference cost
- [ ] WHEN any news sentiment config parameter is changed via `.env` THEN the system SHALL use the updated value on the next application restart.
- [ ] WHEN `news_enabled` is set to `False` THEN the `NewsSentimentStage` SHALL skip all processing and pass `ctx` through unchanged, making the feature fully deactivatable.

---

### REQ-NSF-040: RSS Feed URL Configuration

**User Story:** As a developer, I want RSS feed URLs configurable via environment variables, so that feeds can be added, removed, or replaced without code changes.

**Priority:** P1
**Dependencies:** REQ-NSF-001
**Components affected:** `backend/signalpilot/config.py`

#### Acceptance Criteria

- [ ] WHEN Phase 4 is deployed THEN `AppConfig` SHALL include a `news_rss_feeds` field accepting a comma-separated list of RSS feed URLs, with defaults pointing to the five Tier 1 sources (MoneyControl, Economic Times, LiveMint, Business Standard, NDTV Profit).
- [ ] WHEN the `NewsFetcher` initializes THEN it SHALL read the feed URL list from `AppConfig` and iterate over all configured feeds during fetch operations.
- [ ] IF an RSS feed URL is malformed THEN the system SHALL log a warning at startup and exclude that feed from the fetch cycle.

---

### REQ-NSF-041: Feature Kill Switch

**User Story:** As a developer, I want a single configuration flag to completely disable the news sentiment filter, so that the feature can be turned off instantly in production if it causes issues.

**Priority:** P0
**Dependencies:** REQ-NSF-039
**Components affected:** `backend/signalpilot/pipeline/stages/news_sentiment.py`, `backend/signalpilot/config.py`

#### Acceptance Criteria

- [ ] WHEN `news_enabled` is `False` in `AppConfig` THEN the `NewsSentimentStage.process()` method SHALL return the `ScanContext` unchanged without performing any lookups, scoring, or modifications.
- [ ] WHEN `news_enabled` is `False` THEN the pre-market fetch and cache refresh scheduler jobs SHALL skip execution and log an info message.
- [ ] WHEN `news_enabled` is toggled from `False` to `True` THEN the system SHALL resume normal operation on the next application restart, with the pre-market fetch job populating the cache.

---

### REQ-NSF-042: Financial Lexicon Configuration (VADER)

**User Story:** As a developer, I want the VADER financial lexicon to be configurable via an external file, so that domain-specific sentiment terms can be updated without code changes.

**Priority:** P2
**Dependencies:** REQ-NSF-005
**Components affected:** `backend/signalpilot/intelligence/news_sentiment.py`, `backend/signalpilot/config.py`

#### Acceptance Criteria

- [ ] WHEN the VADER sentiment engine initializes THEN it SHALL load a financial lexicon from a configurable JSON or CSV file path (default: `backend/signalpilot/intelligence/financial_lexicon.json`).
- [ ] WHEN the lexicon file is loaded THEN it SHALL contain term-score mappings (e.g., `{"SEBI probe": -0.9, "record revenue": 0.8, "fraud": -1.0}`) that override or extend VADER's default lexicon.
- [ ] IF the lexicon file is missing or malformed THEN the system SHALL log a warning and fall back to VADER's default lexicon without the financial overlay.
- [ ] WHEN the lexicon file path is changed via `AppConfig` THEN the system SHALL use the updated file on the next application restart.

---

## 13. Data Models

### REQ-NSF-043: SentimentResult Dataclass

**User Story:** As a developer, I want a `SentimentResult` dataclass to represent per-stock sentiment analysis output, so that the pipeline, repository, and formatters share a common typed contract.

**Priority:** P0
**Dependencies:** None
**Components affected:** `backend/signalpilot/db/models.py` or `backend/signalpilot/intelligence/news_sentiment.py`

#### Acceptance Criteria

- [ ] WHEN `SentimentResult` is defined THEN it SHALL be a Python dataclass with fields: `score` (float), `label` (str), `headline` (str | None), `action` (str), `headline_count` (int), `top_negative_headline` (str | None), and `model_used` (str).
- [ ] WHEN `SentimentResult` is used in `ScanContext.sentiment_results` THEN the dict key SHALL be the stock symbol (str) and the value SHALL be a `SentimentResult` instance.

---

### REQ-NSF-044: SuppressedSignal Dataclass

**User Story:** As a developer, I want a `SuppressedSignal` dataclass to represent signals removed by the news filter, so that suppression notifications have structured data available for formatting.

**Priority:** P0
**Dependencies:** None
**Components affected:** `backend/signalpilot/db/models.py` or `backend/signalpilot/intelligence/news_sentiment.py`

#### Acceptance Criteria

- [ ] WHEN `SuppressedSignal` is defined THEN it SHALL be a Python dataclass with fields: `symbol` (str), `strategy` (str), `original_stars` (int), `sentiment_score` (float), `sentiment_label` (str), `top_headline` (str | None), `reason` (str), `entry_price` (float), `stop_loss` (float), and `target_1` (float).
- [ ] WHEN `SuppressedSignal` is used in `ScanContext.suppressed_signals` THEN it SHALL be a list of `SuppressedSignal` instances populated by the `NewsSentimentStage`.

---

## 14. Testing

### REQ-NSF-045: Unit Test Coverage

**User Story:** As a developer, I want comprehensive unit tests for all new components, so that sentiment analysis logic, scoring, and signal modification rules are verified in isolation.

**Priority:** P0
**Dependencies:** All REQ-NSF requirements
**Components affected:** `tests/test_intelligence/`, `tests/test_db/`, `tests/test_pipeline/`

#### Acceptance Criteria

- [ ] WHEN unit tests are run THEN there SHALL be tests covering: `NewsFetcher` (RSS parsing, error handling, deduplication), `NewsSentimentService` (FinBERT mock, VADER mock, composite scoring, recency weighting, label classification for all five labels), `NewsSentimentStage` (suppression, downgrade, pass-through, cache miss, empty ranked signals, feature disabled via kill switch, earnings blackout priority), `NewsSentimentRepository` (upsert, query, purge, composite score calculation), and `EarningsCalendarRepository` (has_earnings_today, get_upcoming, upsert).
- [ ] WHEN async tests are written THEN they SHALL use `async def` with the project's `asyncio_mode="auto"` configuration.
- [ ] WHEN tests mock external dependencies THEN they SHALL use the existing `conftest.py` fixture pattern (in-memory SQLite `db` fixture, `app_config` fixture).

---

### REQ-NSF-046: Integration Test Coverage

**User Story:** As a developer, I want integration tests that verify the end-to-end flow from ranked signals through sentiment filtering to delivery or suppression, so that the pipeline integration is validated.

**Priority:** P1
**Dependencies:** REQ-NSF-014, REQ-NSF-016, REQ-NSF-045
**Components affected:** `tests/test_integration/`

#### Acceptance Criteria

- [ ] WHEN integration tests are run THEN there SHALL be tests covering: a full pipeline cycle where a signal is suppressed due to STRONG_NEGATIVE sentiment and a suppression notification is sent, a full pipeline cycle where a signal is downgraded due to MILD_NEGATIVE sentiment and the star rating is reduced by 1, a full pipeline cycle where a signal passes through with POSITIVE sentiment and the positive badge is included, an earnings blackout scenario where a signal is suppressed regardless of sentiment, and a cache miss scenario where the signal passes through as NO_NEWS.
- [ ] WHEN integration tests exercise the pipeline THEN they SHALL use the `make_app()` helper from `tests/test_integration/conftest.py` to construct a fully wired application with mock external dependencies.
- [ ] WHEN integration tests verify persistence THEN they SHALL check that the `signals` table contains the correct `news_sentiment_score`, `news_sentiment_label`, `news_top_headline`, `news_action`, and `original_star_rating` values.
