# Task 9: Signal Scoring Updates

## Description
Create `ORBScorer` and `VWAPScorer` with strategy-specific normalization and weighting. Update `SignalScorer` to dispatch to the correct scorer based on strategy name. Update `SignalRanker` max from 5 to 8.

## Prerequisites
Task 0001 (Configuration and Constants), Task 0002 (Data Models)

## Requirement Coverage
REQ-P2-005, REQ-P2-011B, REQ-P2-013

## Files to Create
- `signalpilot/ranking/orb_scorer.py`
- `signalpilot/ranking/vwap_scorer.py`

## Files to Modify
- `signalpilot/ranking/scorer.py`
- `signalpilot/ranking/ranker.py`

## Subtasks

- [ ] 9.1 Create `signalpilot/ranking/orb_scorer.py` with `ORBScorer`
  - `score(signal, avg_candle_volume, range_size_pct) -> float`
  - Volume normalization: 1.5x -> 0.0, 4.0x -> 1.0 (linear interpolation)
  - Range tightness normalization: 3% -> 0.0, 0.5% -> 1.0 (inverse -- tighter = better)
  - Distance from breakout normalization: further -> lower score
  - Weighted composite: volume (40%) + range (30%) + distance (30%)
  - Output normalized to [0.0, 1.0]
  - Requirement coverage: REQ-P2-005

- [ ] 9.2 Create `signalpilot/ranking/vwap_scorer.py` with `VWAPScorer`
  - `score(signal, avg_candle_volume, vwap_touch_pct, candles_above_vwap_ratio) -> float`
  - Volume normalization: 1.0x -> 0.0, 3.0x -> 1.0
  - VWAP touch precision normalization: 0.3% -> 0.0, 0% (exact touch) -> 1.0
  - Trend alignment normalization: ratio of candles above VWAP
  - Weighted composite: volume (35%) + touch precision (35%) + trend alignment (30%)
  - Output normalized to [0.0, 1.0]
  - Requirement coverage: REQ-P2-011B

- [ ] 9.3 Update `SignalScorer` in `signalpilot/ranking/scorer.py`
  - Update `__init__()` to accept `orb_scorer: ORBScorer | None` and `vwap_scorer: VWAPScorer | None`
  - Update `score()` to dispatch based on `signal.strategy_name`: "ORB" -> ORBScorer, "VWAP Reversal" -> VWAPScorer, default -> existing Gap & Go scoring
  - Preserve `_score_gap_and_go()` as the default path (no change to Phase 1 behavior)
  - Requirement coverage: REQ-P2-013

- [ ] 9.4 Update `SignalRanker` in `signalpilot/ranking/ranker.py`
  - Update `max_signals` default from 5 to 8 for cross-strategy ranking
  - Requirement coverage: REQ-P2-013

- [ ] 9.5 Write ORB scorer tests in `tests/test_ranking/test_orb_scorer.py`
  - Test normalization at boundaries (min/max), mid-range values, weighted output in [0,1]
  - Requirement coverage: REQ-P2-005

- [ ] 9.6 Write VWAP scorer tests in `tests/test_ranking/test_vwap_scorer.py`
  - Test normalization at boundaries, mid-range values, trend alignment, weighted output in [0,1]
  - Requirement coverage: REQ-P2-011B

- [ ] 9.7 Extend `tests/test_ranking/test_scorer.py` with strategy dispatch tests
  - Correct scorer called for each strategy name, unknown strategy falls back to Gap & Go
  - Requirement coverage: REQ-P2-013
