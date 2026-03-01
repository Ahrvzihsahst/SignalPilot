# Task 3: Configuration

## Description
Add 12 new news sentiment configuration fields to `AppConfig`, add validation for `sentiment_model`, and update `.env.example` with the new environment variables and their defaults.

## Prerequisites
None (can be done in parallel with Task 1)

## Requirement Coverage
REQ-NSF-006, REQ-NSF-039, REQ-NSF-040, REQ-NSF-041, REQ-NSF-042

## Files to Modify
- `signalpilot/config.py`
- `.env.example`

## Subtasks

### 3.1 Add news sentiment config fields to `backend/signalpilot/config.py`

- [x] Add `news_enabled: bool = True` — kill switch for the entire news sentiment feature
- [x] Add `sentiment_model: str = "vader"` — sentiment engine selection ("vader" or "finbert")
- [x] Add `news_lookback_hours: int = 24` — how far back to look for news headlines
- [x] Add `news_cache_ttl_hours: int = 2` — cache refresh interval
- [x] Add `strong_negative_threshold: float = -0.5` — compound score below which signals are suppressed
- [x] Add `mild_negative_threshold: float = -0.2` — compound score below which signals are downgraded
- [x] Add `positive_threshold: float = 0.3` — compound score above which positive badge is shown
- [x] Add `earnings_blackout_enabled: bool = True` — enable/disable earnings day suppression
- [x] Add `news_pre_market_fetch_time: str = "08:30"` — pre-market news fetch time
- [x] Add `news_max_headlines_per_stock: int = 10` — cap on cached headlines per stock
- [x] Add `news_rss_feeds: str = "..."` — comma-separated list of RSS feed URLs
- [x] Add `news_financial_lexicon_path: str = "signalpilot/intelligence/financial_lexicon.json"` — path to financial term lexicon
- [x] Add `news_earnings_csv_path: str = "data/earnings_calendar.csv"` — path to earnings CSV
- [x] Add validation that `sentiment_model` is one of `"vader"` or `"finbert"` (fail fast on unrecognized value)
- [x] Update `backend/.env.example` with the new environment variables and their defaults
- [x] Write tests verifying defaults load correctly and invalid `sentiment_model` raises a validation error
- Requirement coverage: REQ-NSF-039, REQ-NSF-040, REQ-NSF-041, REQ-NSF-006, REQ-NSF-042
