# Task 11: Exit Monitor Updates (Per-Strategy Trailing SL)

## Description
Add per-strategy trailing stop loss configuration to `ExitMonitor`. Each strategy (Gap & Go, ORB, VWAP Setup 1, VWAP Setup 2) has different breakeven trigger and trailing distance thresholds.

## Prerequisites
Task 0002 (Data Models)

## Requirement Coverage
REQ-P2-004, REQ-P2-011A

## Files to Modify
- `signalpilot/monitor/exit_monitor.py`

## Subtasks

- [ ] 11.1 Add `TrailingStopConfig` dataclass to `signalpilot/monitor/exit_monitor.py`
  - Fields: `breakeven_trigger_pct: float`, `trail_trigger_pct: float | None`, `trail_distance_pct: float | None`
  - Requirement coverage: REQ-P2-004, REQ-P2-011A

- [ ] 11.2 Define `DEFAULT_TRAILING_CONFIGS` mapping strategy name to `TrailingStopConfig`
  - Gap & Go: breakeven at 2.0%, trail at 4.0% with 2.0% distance
  - ORB: breakeven at 1.5%, trail at 2.0% with 1.0% distance
  - VWAP Reversal (Setup 1): breakeven at 1.0%, no trailing (None/None)
  - VWAP Reversal (Setup 2): breakeven at 1.5%, no trailing (None/None)
  - Requirement coverage: REQ-P2-004, REQ-P2-011A

- [ ] 11.3 Update `ExitMonitor.__init__()` to accept `trailing_configs: dict[str, TrailingStopConfig] | None`
  - Requirement coverage: REQ-P2-004

- [ ] 11.4 Implement `_get_config_for_trade(trade: TradeRecord) -> TrailingStopConfig`
  - Look up config by `trade.strategy`, fall back to Gap & Go defaults for unknown strategies
  - For VWAP trades, further distinguish by `setup_type` if available
  - Requirement coverage: REQ-P2-004, REQ-P2-011A

- [ ] 11.5 Update `_update_trailing_stop()` to use per-trade config
  - Replace class-level scalar thresholds with config from `_get_config_for_trade()`
  - Maintain backward compatibility (Phase 1 trades still work correctly)
  - Requirement coverage: REQ-P2-004, REQ-P2-011A

- [ ] 11.6 Write tests in `tests/test_monitor/test_exit_monitor.py`
  - ORB: breakeven at +1.5%, trail at +2% with 1% distance
  - VWAP Setup 1: breakeven at +1.0%, no trailing beyond breakeven
  - VWAP Setup 2: breakeven at +1.5%, no trailing beyond breakeven
  - Gap & Go: unchanged behavior (2.0%/4.0%/2.0%)
  - Unknown strategy: falls back to Gap & Go config
  - Requirement coverage: REQ-P2-004, REQ-P2-011A
