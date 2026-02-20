# Task 2: Data Model Updates

## Description
Extend existing dataclasses (`CandidateSignal`, `SignalRecord`, `TradeRecord`, `UserConfig`, `DailySummary`) with Phase 2 fields and create new dataclasses (`StrategyDaySummary`, `StrategyPerformanceRecord`).

## Prerequisites
Task 0001 (Configuration and Constants)

## Requirement Coverage
REQ-P2-020, REQ-P2-023, REQ-P2-029, REQ-P2-032, REQ-P2-033, REQ-P2-039

## Files to Modify
- `signalpilot/db/models.py`

## Subtasks

- [ ] 2.1 Extend `CandidateSignal` in `signalpilot/db/models.py`
  - Add `setup_type: str | None = None` (for VWAP: "uptrend_pullback" or "vwap_reclaim")
  - Add `strategy_specific_score: float | None = None`
  - Ensure `gap_pct` defaults to 0.0 for non-Gap & Go signals
  - Requirement coverage: REQ-P2-032

- [ ] 2.2 Extend `SignalRecord` in `signalpilot/db/models.py`
  - Add `setup_type: str | None = None`
  - Add `strategy_specific_score: float | None = None`
  - Requirement coverage: REQ-P2-032

- [ ] 2.3 Extend `TradeRecord` in `signalpilot/db/models.py`
  - Add `strategy: str = "gap_go"`
  - Requirement coverage: REQ-P2-033

- [ ] 2.4 Extend `UserConfig` in `signalpilot/db/models.py`
  - Add `gap_go_enabled: bool = True`, `orb_enabled: bool = True`, `vwap_enabled: bool = True`
  - Update `max_positions` default from 5 to 8
  - Requirement coverage: REQ-P2-023

- [ ] 2.5 Create `StrategyDaySummary` dataclass in `signalpilot/db/models.py`
  - Fields: `strategy_name: str`, `signals_generated: int`, `signals_taken: int`, `pnl: float`
  - Requirement coverage: REQ-P2-029

- [ ] 2.6 Extend `DailySummary` in `signalpilot/db/models.py`
  - Add `strategy_breakdown: dict[str, StrategyDaySummary] = field(default_factory=dict)`
  - Requirement coverage: REQ-P2-029

- [ ] 2.7 Create `StrategyPerformanceRecord` dataclass in `signalpilot/db/models.py`
  - Fields: `id: int | None`, `strategy: str`, `date: str`, `signals_generated: int`, `signals_taken: int`, `wins: int`, `losses: int`, `total_pnl: float`, `win_rate: float`, `avg_win: float`, `avg_loss: float`, `expectancy: float`, `capital_weight_pct: float`
  - Requirement coverage: REQ-P2-020

- [ ] 2.8 Update `__all__` exports in `signalpilot/db/models.py`
  - Requirement coverage: foundational

- [ ] 2.9 Verify backward compatibility -- existing Phase 1 code works with new defaults
  - Requirement coverage: REQ-P2-039

- [ ] 2.10 Write tests for all new dataclass fields and defaults in `tests/test_db/test_models.py`
  - Test instantiation with defaults, test optional fields, test backward compat
  - Requirement coverage: REQ-P2-032, REQ-P2-033
