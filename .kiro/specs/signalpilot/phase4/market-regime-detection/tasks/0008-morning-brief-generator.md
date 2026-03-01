# Task 8: Morning Brief Generator

## Description
Implement `MorningBriefGenerator` in `backend/signalpilot/intelligence/morning_brief.py`. This component composes the 8:45 AM pre-market morning brief message that includes global cues (S&P 500, Nasdaq, Asian markets, SGX Nifty), India context (VIX, FII/DII), a pre-market regime prediction with reasoning, and watchlist alerts.

## Prerequisites
Task 4 (Data Collector -- needs `RegimeDataCollector` and `PreMarketData`)

## Requirement Coverage
REQ-MRD-025, REQ-MRD-026

## Files to Create
- `signalpilot/intelligence/morning_brief.py`

## Subtasks

### 8.1 Implement `backend/signalpilot/intelligence/morning_brief.py`

- [ ] Create `MorningBriefGenerator` class with constructor accepting `data_collector` (RegimeDataCollector), `watchlist_repo` (WatchlistRepository), `config` (AppConfig)
- [ ] Store `_last_brief: str | None = None` for caching the brief for the MORNING re-send command
- [ ] Implement `async def generate() -> str`:
  1. Call `data_collector.collect_pre_market_data()` to fetch VIX, global cues, FII/DII
  2. Build global cues section (S&P 500, Nasdaq, Nikkei, Hang Seng, SGX Nifty)
  3. Build India context section (VIX value + interpretation, FII/DII net flows)
  4. Compute pre-market regime prediction via `_predict_regime(data)`
  5. Query `watchlist_repo` for active entries (within 5-day window)
  6. Format all sections into HTML string via `_format_brief()`
  7. Cache result in `_last_brief`
  8. Handle any section's data failure gracefully -- include "Data unavailable" note
- [ ] Implement `def get_cached_brief() -> str | None` returning the cached morning brief
- [ ] Implement `def _predict_regime(data: PreMarketData) -> tuple[str, str]` using available pre-market inputs (VIX + SGX direction + S&P change) to make a preliminary regime prediction with reasoning text
- [ ] Implement `def _format_brief(data, regime_prediction, reasoning, watchlist_entries) -> str` producing the formatted Telegram message as specified in Design Section 3.4 (header, global cues, India context, regime prediction, watchlist alerts if any, footer)
- [ ] If no watchlist entries are active, omit the watchlist section
- Requirement coverage: REQ-MRD-025, REQ-MRD-026

### 8.2 Write unit tests

- [ ] Write tests in `backend/tests/test_intelligence/test_morning_brief.py` covering:
  - Generate with all data available produces complete brief with all sections
  - Generate with partial data failure still produces brief with "unavailable" notes
  - Pre-market regime prediction logic: high VIX -> VOLATILE prediction, strong SGX UP -> TRENDING, etc.
  - Watchlist entries included when present
  - Watchlist section omitted when no entries
  - Cached brief returned by `get_cached_brief()`
  - `get_cached_brief()` returns None before first generate()
- Requirement coverage: REQ-MRD-025, REQ-MRD-026
