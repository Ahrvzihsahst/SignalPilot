# Task 5: Pipeline Stage

## Description
Implement `NewsSentimentStage` as a new pipeline stage (stage 9) that reads cached sentiment data and applies the suppress/downgrade/pass-through action matrix to ranked signals. This is the core integration point between the news sentiment engine and the existing composable pipeline.

## Prerequisites
Task 1 (Data Models), Task 2 (Repository Layer), Task 3 (Configuration), Task 4 (Intelligence Module)

## Requirement Coverage
REQ-NSF-010, REQ-NSF-011, REQ-NSF-012, REQ-NSF-013, REQ-NSF-014, REQ-NSF-028, REQ-NSF-037, REQ-NSF-041

## Files to Create
- `signalpilot/pipeline/stages/news_sentiment.py`

## Subtasks

### 5.1 Implement `backend/signalpilot/pipeline/stages/news_sentiment.py`

- [x] Create `NewsSentimentStage` class implementing the `PipelineStage` protocol as specified in Design Section 3.4
- [x] Constructor accepts: `news_sentiment_service`, `earnings_repo`, `config`
- [x] `name` property returns `"NewsSentiment"`
- [x] `process(ctx)` logic:
  1. Return ctx unchanged if `config.news_enabled` is False (kill switch)
  2. Return ctx immediately if `ctx.ranked_signals` is empty
  3. Batch fetch sentiment for all symbols via `get_sentiment_batch()`
  4. For each ranked signal: check earnings blackout first (highest priority), then check unsuppress override, then apply label-based action (suppress STRONG_NEGATIVE, downgrade MILD_NEGATIVE, pass-through NEUTRAL/POSITIVE/NO_NEWS)
  5. Populate `ctx.ranked_signals` (filtered), `ctx.suppressed_signals`, `ctx.sentiment_results`
- [x] Log summary: passed count, suppressed count
- [x] Write tests in `backend/tests/test_pipeline/test_news_sentiment_stage.py`:
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
- Requirement coverage: REQ-NSF-010, REQ-NSF-011, REQ-NSF-012, REQ-NSF-013, REQ-NSF-014, REQ-NSF-028, REQ-NSF-037, REQ-NSF-041
