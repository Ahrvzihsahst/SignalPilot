# Task 16: Phase 2 Integration Tests

## Description
Create Phase 2 test fixtures and write integration tests covering multi-strategy scanning, cross-strategy deduplication, position limits at 8, per-strategy daily summary, and pause/resume flow.

## Prerequisites
All previous tasks (0001-0015)

## Requirement Coverage
REQ-P2-040, REQ-P2-042

## Files to Modify
- `tests/conftest.py`
- `tests/test_integration/conftest.py`

## Files to Create
- `tests/test_integration/test_multi_strategy_scan.py`
- `tests/test_integration/test_dedup_cross_strategy.py`
- `tests/test_integration/test_position_limit_8.py`
- `tests/test_integration/test_daily_summary_phase2.py`
- `tests/test_integration/test_pause_resume_flow.py`

## Subtasks

- [ ] 16.1 Add Phase 2 sample fixtures to `tests/conftest.py`
  - `sample_orb_candidate` -- ORB CandidateSignal with valid breakout data
  - `sample_vwap_candidate` -- VWAP Uptrend Pullback CandidateSignal
  - `sample_vwap_reclaim_candidate` -- VWAP Reclaim CandidateSignal with Higher Risk
  - Requirement coverage: REQ-P2-040

- [ ] 16.2 Update `tests/test_integration/conftest.py`
  - Update `make_app()` to accept `strategies` list parameter
  - Add `make_signal_record()` overloads for ORB/VWAP signal types
  - Add Phase 2 helpers: `make_orb_signal()`, `make_vwap_signal()`
  - Requirement coverage: REQ-P2-040

- [ ] 16.3 Write multi-strategy scan loop integration test in `tests/test_integration/test_multi_strategy_scan.py`
  - 3 strategies active, feed mock data, verify correct phase-based evaluation, verify candidates merged and ranked across strategies
  - Requirement coverage: REQ-P2-014, REQ-P2-031

- [ ] 16.4 Write cross-strategy deduplication test in `tests/test_integration/test_dedup_cross_strategy.py`
  - Gap & Go signal for stock A, then ORB should NOT signal stock A same day, VWAP should NOT signal stock A same day
  - Requirement coverage: REQ-P2-012

- [ ] 16.5 Write position limit at 8 test in `tests/test_integration/test_position_limit_8.py`
  - With 8 active trades, no new signals sent. With 7, one allowed. Position-full signals tagged correctly
  - Requirement coverage: REQ-P2-015

- [ ] 16.6 Write daily summary with per-strategy breakdown test in `tests/test_integration/test_daily_summary_phase2.py`
  - Daily summary includes BY STRATEGY section, totals are correct across all strategies
  - Requirement coverage: REQ-P2-029

- [ ] 16.7 Write strategy pause/resume flow test in `tests/test_integration/test_pause_resume_flow.py`
  - PAUSE ORB -> scan loop skips ORB -> RESUME ORB -> ORB evaluates again
  - Requirement coverage: REQ-P2-024, REQ-P2-025

- [ ] 16.8 Add structured logging context assertions for Phase 2 components
  - Verify `strategy` and `setup_type` context fields set via `set_context()` during Phase 2 strategy evaluation
  - Requirement coverage: REQ-P2-042

- [ ] 16.9 Verify all tests pass with 0 failures
  - Run full test suite: `pytest tests/` -- all Phase 1 + Phase 2 tests pass
  - Requirement coverage: REQ-P2-040
