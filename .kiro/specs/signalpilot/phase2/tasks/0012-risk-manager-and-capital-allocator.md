# Task 12: Risk Manager and Capital Allocator

## Description
Create `CapitalAllocator` for performance-based capital allocation with weekly rebalancing and auto-pause. Update `RiskManager` for strategy-aware position sizing and max positions 5 -> 8. Add weekly rebalancing cron job to `MarketScheduler`.

## Prerequisites
Task 0003 (Database Schema Migration), Task 0004 (Repository Updates)

## Requirement Coverage
REQ-P2-015, REQ-P2-016, REQ-P2-017, REQ-P2-018, REQ-P2-026

## Files to Create
- `signalpilot/risk/capital_allocator.py`

## Files to Modify
- `signalpilot/risk/risk_manager.py`
- `signalpilot/scheduler/scheduler.py`

## Subtasks

- [ ] 12.1 Create `signalpilot/risk/capital_allocator.py` with `CapitalAllocator`
  - Constructor accepts `StrategyPerformanceRepository` and `ConfigRepository`
  - Define `StrategyAllocation` dataclass: `strategy_name`, `weight_pct`, `allocated_capital`, `max_positions`
  - Define `STRATEGY_NAMES = ["gap_go", "ORB", "VWAP Reversal"]` and `RESERVE_PCT = 0.20`
  - Requirement coverage: REQ-P2-016

- [ ] 12.2 Implement `calculate_allocations(total_capital: float, max_positions: int, today: date) -> dict[str, StrategyAllocation]`
  - Formula: `weight = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)` per strategy
  - Normalize weights to sum to (1 - RESERVE_PCT) = 0.80
  - Allocate positions per strategy: `max_positions * strategy_weight` (rounded, min 1)
  - Reserve 20% (1 position slot) as buffer for 5-star exceptional signals
  - Fallback: equal allocation when no historical data (first week)
  - Requirement coverage: REQ-P2-016

- [ ] 12.3 Implement `check_auto_pause(today: date) -> list[str]`
  - Query trailing 30-day performance for each strategy
  - If win rate < 40% AND sample size >= 10 trades -> return strategy name for auto-pause
  - Requirement coverage: REQ-P2-018

- [ ] 12.4 Implement `set_manual_allocation(allocations: dict[str, float])` and `enable_auto_allocation()`
  - Manual override sets static weights, disables auto-rebalancing
  - `enable_auto_allocation()` re-enables auto mode
  - Requirement coverage: REQ-P2-026

- [ ] 12.5 Update `RiskManager` in `signalpilot/risk/risk_manager.py`
  - Accept optional `CapitalAllocator` in constructor
  - Support strategy-aware position sizing: per-trade capital from allocator if available
  - Update per-trade capital from `total_capital / 8` (new max positions)
  - Requirement coverage: REQ-P2-015

- [ ] 12.6 Add weekly rebalancing cron job to `MarketScheduler` in `signalpilot/scheduler/scheduler.py`
  - Schedule on Sunday (or first trading day after) to recalculate strategy weights
  - Send Telegram summary of new allocation
  - Log warning if any strategy's allocation changes > 10%
  - Requirement coverage: REQ-P2-017

- [ ] 12.7 Write tests in `tests/test_risk/test_capital_allocator.py`
  - Equal allocation with no historical data, weighted allocation with known performance data, auto-pause trigger (win rate < 40%, >= 10 trades), manual override and auto re-enable, reserve buffer enforcement (20% always reserved)
  - Requirement coverage: REQ-P2-016, REQ-P2-017, REQ-P2-018
