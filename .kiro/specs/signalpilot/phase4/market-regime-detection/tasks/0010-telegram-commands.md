# Task 10: Telegram Commands

## Description
Implement five new Telegram commands: `REGIME` (show current classification), `REGIME HISTORY` (last 20 days with performance), `REGIME OVERRIDE <REGIME>` (manual override), `VIX` (current India VIX), and `MORNING` (re-send morning brief). Register all command handlers in `SignalPilotBot.start()` following the existing pattern.

## Prerequisites
Task 5 (Classifier -- needs `get_cached_regime()`, `apply_override()`), Task 8 (Morning Brief -- needs `get_cached_brief()`), Task 9 (Formatters -- needs regime display/notification formatters)

## Requirement Coverage
REQ-MRD-032, REQ-MRD-033, REQ-MRD-034, REQ-MRD-035, REQ-MRD-036

## Files to Modify
- `signalpilot/telegram/handlers.py`
- `signalpilot/telegram/bot.py`

## Subtasks

### 10.1 Implement command handler functions in `backend/signalpilot/telegram/handlers.py`

- [ ] Implement `async def handle_regime_command(regime_classifier) -> str`: read cached regime, if None return "No classification yet today" message with DEFAULT values, otherwise return `format_regime_display(classification)`
- [ ] Implement `async def handle_regime_history_command(regime_repo, regime_perf_repo) -> str`: query `regime_repo.get_regime_history(20)` and `regime_perf_repo.get_performance_summary(20)`, if no history return "No regime history available yet", otherwise return `format_regime_history(history, performance)`
- [ ] Implement `async def handle_regime_override_command(regime_classifier, regime_text: str) -> str`: parse regime from text, validate it's one of TRENDING/RANGING/VOLATILE (return error if invalid), call `regime_classifier.apply_override(regime)`, return confirmation with updated modifiers and reset warning
- [ ] Implement `async def handle_vix_command(data_collector) -> str`: get cached pre-market data, if None or VIX unavailable return "VIX data not available" message, otherwise format VIX value, score, and interpretation
- [ ] Implement `async def handle_morning_command(morning_brief_generator) -> str`: get cached brief, if None return "Morning brief not generated yet" message, otherwise return the cached brief
- Requirement coverage: REQ-MRD-032, REQ-MRD-033, REQ-MRD-034, REQ-MRD-035, REQ-MRD-036

### 10.2 Register commands in `backend/signalpilot/telegram/bot.py`

- [ ] Add `regime_classifier`, `morning_brief_generator`, `regime_data_collector`, `regime_repo`, `regime_performance_repo` as optional constructor parameters (default None for backward compat)
- [ ] Register `REGIME` command with regex `(?i)^regime$` -> dispatches to `handle_regime_command()`
- [ ] Register `REGIME HISTORY` command with regex `(?i)^regime\s+history$` -> dispatches to `handle_regime_history_command()`
- [ ] Register `REGIME OVERRIDE` command with regex `(?i)^regime\s+override\s+(trending|ranging|volatile)$` -> dispatches to `handle_regime_override_command()`
- [ ] Register `VIX` command with regex `(?i)^vix$` -> dispatches to `handle_vix_command()`
- [ ] Register `MORNING` command with regex `(?i)^morning$` -> dispatches to `handle_morning_command()`
- [ ] Follow existing `MessageHandler` registration pattern (same as STATUS, JOURNAL, CAPITAL)
- Requirement coverage: REQ-MRD-032, REQ-MRD-033, REQ-MRD-034, REQ-MRD-035, REQ-MRD-036

### 10.3 Write unit tests

- [ ] Write tests in `backend/tests/test_telegram/test_regime_commands.py` covering:
  - REGIME with cached classification returns formatted display
  - REGIME before 9:30 AM (no classification) returns default message
  - REGIME HISTORY with data returns formatted history
  - REGIME HISTORY with no data returns info message
  - REGIME OVERRIDE TRENDING applies override and confirms
  - REGIME OVERRIDE with invalid regime returns error with valid options
  - VIX with available data returns value, score, and interpretation
  - VIX with unavailable data returns error message
  - MORNING with cached brief returns the brief
  - MORNING before 8:45 AM returns "not generated yet" message
- Requirement coverage: REQ-MRD-032 through REQ-MRD-036, REQ-MRD-051
