# Task 1: Configuration and Constants Updates

## Description
Add all Phase 2 configuration parameters (ORB, VWAP, scoring weights, paper mode) to `AppConfig` and new time constants. This is the foundational task with no dependencies.

## Prerequisites
None (foundational task)

## Requirement Coverage
REQ-P2-006, REQ-P2-011C, REQ-P2-015, REQ-P2-036, REQ-P2-041

## Files to Modify
- `signalpilot/config.py`
- `signalpilot/utils/constants.py`
- `.env.example`

## Subtasks

- [ ] 1.1 Add ORB strategy parameters to `AppConfig` in `signalpilot/config.py`
  - Add fields: `orb_range_min_pct` (default 0.5), `orb_range_max_pct` (default 3.0), `orb_volume_multiplier` (default 1.5), `orb_signal_window_end` (default "11:00"), `orb_target_1_pct` (default 1.5), `orb_target_2_pct` (default 2.5), `orb_breakeven_trigger_pct` (default 1.5), `orb_trail_trigger_pct` (default 2.0), `orb_trail_distance_pct` (default 1.0), `orb_gap_exclusion_pct` (default 3.0)
  - Requirement coverage: REQ-P2-006

- [ ] 1.2 Add ORB scoring weight fields to `AppConfig`
  - Add fields: `orb_scoring_volume_weight` (default 0.40), `orb_scoring_range_weight` (default 0.30), `orb_scoring_distance_weight` (default 0.30)
  - Requirement coverage: REQ-P2-006

- [ ] 1.3 Add VWAP strategy parameters to `AppConfig`
  - Add fields: `vwap_scan_start` (default "10:00"), `vwap_scan_end` (default "14:30"), `vwap_touch_threshold_pct` (default 0.3), `vwap_reclaim_volume_multiplier` (default 1.5), `vwap_pullback_volume_multiplier` (default 1.0), `vwap_max_signals_per_stock` (default 2), `vwap_cooldown_minutes` (default 60), `vwap_setup1_sl_below_vwap_pct` (default 0.5), `vwap_setup1_target1_pct` (default 1.0), `vwap_setup1_target2_pct` (default 1.5), `vwap_setup2_target1_pct` (default 1.5), `vwap_setup2_target2_pct` (default 2.0), `vwap_setup1_breakeven_trigger_pct` (default 1.0), `vwap_setup2_breakeven_trigger_pct` (default 1.5)
  - Requirement coverage: REQ-P2-011C

- [ ] 1.4 Add VWAP scoring weight fields to `AppConfig`
  - Add fields: `vwap_scoring_volume_weight` (default 0.35), `vwap_scoring_touch_weight` (default 0.35), `vwap_scoring_trend_weight` (default 0.30)
  - Requirement coverage: REQ-P2-011C

- [ ] 1.5 Add paper trading mode flags to `AppConfig`
  - Add fields: `orb_paper_mode` (default True), `vwap_paper_mode` (default True)
  - Requirement coverage: REQ-P2-036

- [ ] 1.6 Update `default_max_positions` from 5 to 8 in `AppConfig`
  - Requirement coverage: REQ-P2-015

- [ ] 1.7 Add `model_validator` for scoring weight sum validation
  - ORB weights must sum to 1.0 (tolerance 0.01), VWAP weights must sum to 1.0, Gap & Go weights must sum to 1.0
  - Application SHALL refuse to start if validation fails with clear error message
  - Requirement coverage: REQ-P2-041

- [ ] 1.8 Add Phase 2 time constants to `signalpilot/utils/constants.py`
  - Add: `ORB_WINDOW_END = time(11, 0)`, `VWAP_SCAN_START = time(10, 0)`, `OPENING_RANGE_LOCK = time(9, 45)`, `MAX_SIGNALS_PER_BATCH = 8`
  - Requirement coverage: REQ-P2-006, REQ-P2-011C

- [ ] 1.9 Update `.env.example` with all new Phase 2 fields
  - Requirement coverage: REQ-P2-006, REQ-P2-011C

- [ ] 1.10 Write tests for new config fields, defaults, and weight validation
  - Test all defaults load correctly, test invalid weight sums raise ValidationError, test env override works
  - Requirement coverage: REQ-P2-041
