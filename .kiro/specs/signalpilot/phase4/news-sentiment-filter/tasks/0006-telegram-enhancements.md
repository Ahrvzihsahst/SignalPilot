# Task 6: Telegram Enhancements

## Description
Extend signal formatters to display news sentiment metadata (warning blocks, positive badges, suppression notifications) and implement three new Telegram commands: NEWS, EARNINGS, and UNSUPPRESS.

## Prerequisites
Task 1 (Data Models), Task 2 (Repository Layer), Task 4 (Intelligence Module)

## Requirement Coverage
REQ-NSF-023, REQ-NSF-024, REQ-NSF-025, REQ-NSF-033, REQ-NSF-034, REQ-NSF-035

## Files to Modify
- `signalpilot/telegram/formatters.py`
- `signalpilot/telegram/bot.py`

## Subtasks

### 6.1 Add formatter functions in `backend/signalpilot/telegram/formatters.py`

- [x] Add `format_suppression_notification(suppressed: SuppressedSignal) -> str` function: include symbol, strategy, reason, sentiment score, top headlines, original signal details (entry, SL, target), and hint to use `NEWS {STOCK_CODE}`
- [x] Extend `format_signal_message()` signature with optional `news_sentiment_label: str | None = None` and `news_top_headline: str | None = None` parameters
- [x] When `news_sentiment_label == "MILD_NEGATIVE"`: prepend warning block with sentiment score and headline, show star rating note like "Strength: 3/5 (Downgraded from 4/5 due to news)"
- [x] When `news_sentiment_label == "POSITIVE"`: append positive news badge
- [x] When `news_sentiment_label == "NO_NEWS"`: append "No recent news" note
- [x] When `news_sentiment_label` is None or "NEUTRAL": no change to existing format
- [x] Write tests in `backend/tests/test_telegram/test_formatters_news.py`: suppression notification includes all required fields, downgraded signal has warning block, positive badge present, NO_NEWS note present, None/NEUTRAL format unchanged
- Requirement coverage: REQ-NSF-033, REQ-NSF-034, REQ-NSF-035

### 6.2 Implement NEWS, EARNINGS, and UNSUPPRESS Telegram commands

- [x] Add `handle_news_command` in `backend/signalpilot/telegram/bot.py` (or a new handlers file): query `NewsSentimentService` for stock-specific or ALL sentiment, format response with composite score, label, headline count, top 3 headlines with source and age
- [x] Add `handle_earnings_command`: query `EarningsCalendarRepository.get_upcoming_earnings(7)`, format grouped by date with stock code, quarter, confirmed/tentative status
- [x] Add `handle_unsuppress_command`: add stock to `NewsSentimentService` unsuppress override list, reply with confirmation including current sentiment details and expiry warning
- [x] Register all three commands as `MessageHandler` entries in `SignalPilotBot.start()` following the existing pattern (TAKEN, STATUS, JOURNAL, CAPITAL)
- [x] Write tests in `backend/tests/test_telegram/test_news_commands.py`: NEWS with valid stock returns sentiment, NEWS ALL returns summary table, NEWS with unknown stock returns error, EARNINGS returns formatted list, EARNINGS with no data returns info message, UNSUPPRESS adds override and confirms
- Requirement coverage: REQ-NSF-023, REQ-NSF-024, REQ-NSF-025
