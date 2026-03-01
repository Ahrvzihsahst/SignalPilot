# Task 9: Telegram Formatters

## Description
Add regime-related formatter functions to `backend/signalpilot/telegram/formatters.py`: `format_regime_display()` for the REGIME command, `format_regime_modifiers()` for modifier sections, `format_classification_notification()` for the 9:30 AM alert, `format_reclass_notification()` for re-classification alerts, `format_regime_history()` for REGIME HISTORY, and enhance `format_signal_message()` to include a regime badge.

## Prerequisites
Task 1 (Data Models -- needs `RegimeClassification`)

## Requirement Coverage
REQ-MRD-037, REQ-MRD-038, REQ-MRD-047

## Files to Modify
- `signalpilot/telegram/formatters.py`

## Subtasks

### 9.1 Add regime formatter functions

- [ ] Implement `format_regime_display(classification: RegimeClassification) -> str` showing full classification details: regime name, confidence, all inputs (VIX, gap%, range%, direction, alignment, SGX, S&P, FII/DII), three scores (trending, ranging, volatile), and active adjustments (weights, min stars, position modifier, max positions)
- [ ] Implement `format_regime_modifiers(classification: RegimeClassification) -> str` showing the active adjustments section (strategy weights per strategy, min rating, position modifier, max positions)
- [ ] Implement `format_classification_notification(classification: RegimeClassification) -> str` for the 9:30 AM Telegram notification including regime, inputs, adjustments. Add "SHADOW MODE -- weights not applied" note when shadow mode is active
- [ ] Implement `format_reclass_notification(classification, previous_regime, trigger_reason) -> str` for re-classification alerts including previous/new regime, trigger reason, updated adjustments, and "existing positions not affected" note
- [ ] Implement `format_regime_history(history: list[dict], performance: list[dict]) -> str` formatting the REGIME HISTORY command response with per-day regime and aggregated stats
- [ ] Add helper functions: `_fmt_pct(value)` for percentage formatting, `_fmt_crores(value)` for crore formatting, `_fmt_float(value)` for float formatting, `_vix_interpretation(vix)` for VIX level interpretation text
- Requirement coverage: REQ-MRD-037, REQ-MRD-038

### 9.2 Enhance `format_signal_message()` with regime badge

- [ ] Add optional parameters: `market_regime: str | None = None`, `regime_confidence: float | None = None`
- [ ] When `market_regime` is not None: include a regime badge line (e.g., "Market: TRENDING (72% confidence)")
- [ ] When regime is VOLATILE: include a cautionary note (e.g., "Defensive sizing applied")
- [ ] When `market_regime` is None: no change to existing format (backward compatible)
- Requirement coverage: REQ-MRD-047

### 9.3 Write unit tests

- [ ] Write tests in `backend/tests/test_telegram/test_formatters_regime.py` covering:
  - `format_regime_display` includes all sections (inputs, scores, adjustments)
  - `format_classification_notification` contains regime name and adjustments
  - `format_classification_notification` includes shadow mode note when applicable
  - `format_reclass_notification` shows previous and new regime, trigger reason, "existing positions not affected"
  - `format_regime_history` shows per-day entries and aggregate stats
  - Signal message with TRENDING regime includes badge
  - Signal message with VOLATILE regime includes cautionary note
  - Signal message with None regime has no badge (backward compatible)
  - Helper functions format correctly (pct, crores, VIX interpretation)
- Requirement coverage: REQ-MRD-037, REQ-MRD-038, REQ-MRD-047, REQ-MRD-051
