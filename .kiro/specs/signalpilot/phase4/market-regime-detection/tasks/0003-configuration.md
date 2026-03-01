# Task 3: Configuration

## Description
Add all regime detection configuration parameters to `AppConfig` in `config.py` and update `.env.example` with the new environment variables. This includes the kill switch, shadow mode, confidence threshold, re-classification limits, weight matrices (as JSON strings), position modifiers, max positions, and min star ratings per regime.

## Prerequisites
None (can run in parallel with Task 1)

## Requirement Coverage
REQ-MRD-044, REQ-MRD-045, REQ-MRD-046

## Files to Modify
- `signalpilot/config.py`
- `.env.example`

## Subtasks

### 3.1 Add regime detection config fields to `backend/signalpilot/config.py`

- [ ] Add `regime_enabled: bool = Field(default=True)` -- feature kill switch
- [ ] Add `regime_shadow_mode: bool = Field(default=True)` -- classify and log but do not apply weights (default True per Design Section 9.4)
- [ ] Add `regime_confidence_threshold: float = Field(default=0.55)` -- high vs low confidence boundary
- [ ] Add `regime_max_reclassifications: int = Field(default=2)` -- max re-classifications per day
- [ ] Add `regime_vix_spike_threshold: float = Field(default=0.15)` -- 15% VIX spike triggers re-classification
- [ ] Add `regime_roundtrip_threshold: float = Field(default=0.003)` -- 0.3% of open for round-trip RANGING detection
- [ ] Add six strategy weight fields as JSON strings with defaults from Design Section 6.1: `regime_trending_weights_high`, `regime_trending_weights_low`, `regime_ranging_weights_high`, `regime_ranging_weights_low`, `regime_volatile_weights_high`, `regime_volatile_weights_low`
- [ ] Add three position modifier fields: `regime_trending_position_modifier` (1.0), `regime_ranging_position_modifier` (0.85), `regime_volatile_position_modifier` (0.65)
- [ ] Add three max positions fields: `regime_trending_max_positions` (8), `regime_ranging_max_positions` (6), `regime_volatile_max_positions` (4)
- [ ] Add five min star rating fields: `regime_trending_min_stars` (3), `regime_ranging_high_min_stars` (3), `regime_ranging_low_min_stars` (4), `regime_volatile_high_min_stars` (5), `regime_volatile_low_min_stars` (4)
- [ ] Write tests verifying: all defaults load correctly, JSON weight strings parse correctly, `regime_enabled` and `regime_shadow_mode` default to True
- Requirement coverage: REQ-MRD-044, REQ-MRD-045, REQ-MRD-046

### 3.2 Update `backend/.env.example` with new environment variables

- [ ] Add all regime detection environment variables with documented defaults following the mapping from Design Section 6.2
- [ ] Include comments explaining shadow mode activation workflow
- Requirement coverage: REQ-MRD-044
