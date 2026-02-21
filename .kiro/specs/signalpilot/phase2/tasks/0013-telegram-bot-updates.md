# Task 13: Telegram Bot Updates

## Description
Implement new Phase 2 Telegram commands (PAUSE, RESUME, ALLOCATE, STRATEGY), update signal format and daily summary with strategy information, and register new handlers.

## Prerequisites
Task 0004 (Repository Updates), Task 0012 (Capital Allocator)

## Requirement Coverage
REQ-P2-024, REQ-P2-025, REQ-P2-026, REQ-P2-027, REQ-P2-028, REQ-P2-029, REQ-P2-030

## Files to Modify
- `signalpilot/telegram/handlers.py`
- `signalpilot/telegram/formatters.py`
- `signalpilot/telegram/bot.py`

## Subtasks

- [ ] 13.1 Implement `handle_pause()` in `signalpilot/telegram/handlers.py`
  - Parse "PAUSE GAP" / "PAUSE ORB" / "PAUSE VWAP"
  - Map to `config_repo.set_strategy_enabled(field, False)`
  - Respond: "[Strategy Name] paused. No signals will be generated from this strategy."
  - Handle: no strategy name -> usage instructions, already paused -> "already paused"
  - Requirement coverage: REQ-P2-024

- [ ] 13.2 Implement `handle_resume()` in `signalpilot/telegram/handlers.py`
  - Parse "RESUME GAP" / "RESUME ORB" / "RESUME VWAP"
  - Map to `config_repo.set_strategy_enabled(field, True)`
  - Respond: "[Strategy Name] resumed. Signals will be generated when conditions are met."
  - Handle: no strategy name -> usage instructions, already active -> "already active"
  - Requirement coverage: REQ-P2-025

- [ ] 13.3 Implement `handle_allocate()` in `signalpilot/telegram/handlers.py`
  - "ALLOCATE" alone -> show current allocation per strategy (weight %, capital, positions, reserve)
  - "ALLOCATE GAP 40 ORB 20 VWAP 20" -> set manual allocation (reject if sum > 80%)
  - "ALLOCATE AUTO" -> re-enable automatic rebalancing
  - Requirement coverage: REQ-P2-026

- [ ] 13.4 Implement `handle_strategy()` in `signalpilot/telegram/handlers.py`
  - Query `StrategyPerformanceRepository` for trailing 30-day data per strategy
  - Format response per PRD template (Section 5.5): strategy name, win rate, trades, avg win/loss, net P&L, allocation %
  - Include next rebalancing date (next Sunday)
  - Handle: no trades for a strategy -> show "No trades" with allocation
  - Requirement coverage: REQ-P2-027

- [ ] 13.5 Update `handle_help()` with Phase 2 commands
  - Add ALLOCATE, STRATEGY, PAUSE, RESUME with brief descriptions
  - Requirement coverage: REQ-P2-030

- [ ] 13.6 Update `format_signal_message()` in `signalpilot/telegram/formatters.py`
  - Include strategy name with setup type (e.g., "VWAP Reversal (Uptrend Pullback)")
  - Show "Positions open: X/8" (updated from X/5)
  - Add "Higher Risk" warning for VWAP Reclaim (setup_type="vwap_reclaim") signals
  - Show "Position full -- signal for reference only" when status is "position_full"
  - Requirement coverage: REQ-P2-028

- [ ] 13.7 Update `format_daily_summary()` in `signalpilot/telegram/formatters.py`
  - Add "BY STRATEGY" section with per-strategy rows: strategy icon, name, signal count, taken count, P&L
  - Follow PRD template (Section 5.4)
  - Requirement coverage: REQ-P2-029

- [ ] 13.8 Add `format_strategy_report()` for STRATEGY command output
  - Follow PRD template (Section 5.5)
  - Requirement coverage: REQ-P2-027

- [ ] 13.9 Add `format_allocation_summary()` for weekly rebalance notification
  - Requirement coverage: REQ-P2-017

- [ ] 13.10 Register new command handlers in `signalpilot/telegram/bot.py`
  - Register PAUSE, RESUME, ALLOCATE, STRATEGY with regex filters
  - Requirement coverage: REQ-P2-024, REQ-P2-025, REQ-P2-026, REQ-P2-027

- [ ] 13.11 Write handler tests in `tests/test_telegram/test_phase2_handlers.py`
  - PAUSE: happy path, already paused, no strategy name
  - RESUME: happy path, already active, no strategy name
  - ALLOCATE: show, set manual, AUTO, over 80% rejection
  - STRATEGY: with data, no trades, next rebalance date
  - Requirement coverage: REQ-P2-024, REQ-P2-025, REQ-P2-026, REQ-P2-027

- [ ] 13.12 Write formatter tests in `tests/test_telegram/test_formatters.py`
  - Updated signal format with strategy name/setup type, X/8, Higher Risk label, position_full display, daily summary with per-strategy breakdown
  - Requirement coverage: REQ-P2-028, REQ-P2-029
