# Task 7: PersistAndDeliverStage Enhancement

## Description
Enhance the existing `PersistAndDeliverStage` to persist news sentiment metadata (five new columns) on signal records before DB insert, and send suppression notification messages via Telegram for each signal suppressed by the news filter.

## Prerequisites
Task 1 (Data Models), Task 5 (Pipeline Stage), Task 6 (Telegram Enhancements — formatters)

## Requirement Coverage
REQ-NSF-016

## Files to Modify
- `signalpilot/pipeline/stages/persist_and_deliver.py`

## Subtasks

### 7.1 Enhance `backend/signalpilot/pipeline/stages/persist_and_deliver.py`

- [x] In `_signal_to_record` (or equivalent): when `ctx.sentiment_results` contains an entry for the signal's symbol, set `news_sentiment_score`, `news_sentiment_label`, `news_top_headline`, `news_action`, and `original_star_rating` on the `SignalRecord` before DB insert
- [x] After signal delivery: iterate `ctx.suppressed_signals` and send each as a suppression notification via `self._bot.send_alert(format_suppression_notification(suppressed))`
- [x] When sentiment metadata is not available: all news fields remain None (backward compatible)
- [x] Write tests verifying: sentiment metadata persisted correctly on signal records, suppression notifications sent for each suppressed signal, no behavior change when sentiment_results is empty
- Requirement coverage: REQ-NSF-016
