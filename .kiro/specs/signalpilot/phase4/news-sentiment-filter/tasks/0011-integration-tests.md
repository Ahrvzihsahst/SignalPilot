# Task 11: Integration Tests

## Description
Write end-to-end pipeline integration tests covering all news sentiment action paths: suppress, downgrade, pass-through, earnings blackout, cache miss, and feature disabled. Use `make_app()` helper with mock external dependencies to verify the full flow from ranked signals through news sentiment filtering to signal persistence.

## Prerequisites
Task 1–9 (all component implementations and wiring)

## Requirement Coverage
REQ-NSF-045, REQ-NSF-046

## Files to Create
- `tests/test_integration/test_news_pipeline.py`

## Subtasks

### 11.1 Write pipeline integration tests in `backend/tests/test_integration/test_news_pipeline.py`

- [x] Add test fixtures: `sample_sentiment_result`, `sample_suppressed_signal` to conftest
- [x] Test full suppress flow: ranked signal with STRONG_NEGATIVE cache -> signal removed -> suppression notification sent -> signals table has `news_action="SUPPRESSED"` with sentiment columns populated
- [x] Test full downgrade flow: ranked signal with MILD_NEGATIVE cache -> star rating reduced by 1 -> signal delivered with warning -> signals table has `news_action="DOWNGRADED"`, `original_star_rating` set
- [x] Test full pass-through flow: ranked signal with POSITIVE cache -> signal delivered with positive badge -> signals table has `news_action="PASS"`, `news_sentiment_label="POSITIVE"`
- [x] Test earnings blackout flow: ranked signal with earnings today -> suppressed regardless of sentiment -> `news_action="EARNINGS_BLACKOUT"`
- [x] Test cache miss flow: ranked signal with no cached data -> passes through as NO_NEWS
- [x] Test feature disabled flow: `news_enabled=False` -> no sentiment processing -> all news columns None
- [x] Use `make_app()` helper from `tests/test_integration/conftest.py` with mock external dependencies
- [x] Verify persistence: check signals table contains correct `news_sentiment_score`, `news_sentiment_label`, `news_top_headline`, `news_action`, `original_star_rating`
- Requirement coverage: REQ-NSF-045, REQ-NSF-046
