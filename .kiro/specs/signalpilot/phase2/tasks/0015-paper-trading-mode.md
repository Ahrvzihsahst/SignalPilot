# Task 15: Paper Trading Mode

## Description
Implement paper trading mode where Phase 2 strategies generate signals tagged as "PAPER TRADE" that are tracked through the exit monitor but not treated as live trades. Includes a comparison report after the 2-week paper period.

## Prerequisites
Task 0010 (Multi-Strategy Integration), Task 0014 (Backtesting Framework)

## Requirement Coverage
REQ-P2-036, REQ-P2-037

## Files to Modify
- `signalpilot/scheduler/lifecycle.py`
- `signalpilot/telegram/formatters.py`

## Subtasks

- [ ] 15.1 Add paper mode check in scan loop in `signalpilot/scheduler/lifecycle.py`
  - Check `config.orb_paper_mode` / `config.vwap_paper_mode` flags
  - For paper-mode strategies, set `status="paper"` on generated signals
  - Requirement coverage: REQ-P2-036

- [ ] 15.2 Track paper trades through exit monitor
  - Paper signals with status="paper" should still be tracked by exit monitor identically to live trades (SL/target/trailing SL evaluation)
  - Requirement coverage: REQ-P2-036

- [ ] 15.3 Add "PAPER TRADE" prefix in `signalpilot/telegram/formatters.py`
  - Paper signals sent via Telegram prefixed with "PAPER TRADE" and note: "This is not a live signal"
  - Requirement coverage: REQ-P2-036

- [ ] 15.4 Implement paper trading report generation
  - After 2-week paper period, generate comparison report: paper win rate vs backtest win rate, paper P&L vs expected, variance %, PASS/FAIL recommendation
  - "WITHIN TOLERANCE -- Ready for live deployment" if variance <= 10%
  - "OUTSIDE TOLERANCE -- Review and re-calibrate before going live" if variance > 10%
  - Send report via Telegram
  - Requirement coverage: REQ-P2-037

- [ ] 15.5 Write paper trading tests
  - Paper signal gets `status="paper"`, paper signal formatted with prefix, paper trade tracked through exit monitor, report within tolerance shows PASS, report outside tolerance shows FAIL
  - Requirement coverage: REQ-P2-036, REQ-P2-037
