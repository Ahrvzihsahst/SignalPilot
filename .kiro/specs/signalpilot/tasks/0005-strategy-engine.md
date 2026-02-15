# Task 5: Strategy Engine

## Status: COMPLETED

## References
- Requirements: `/.kiro/specs/signalpilot/requirements.md` (Req 6-9, 33)
- Design: `/.kiro/specs/signalpilot/design.md` (Section 4.2)

---

## Subtasks

### 5.1 Implement `signalpilot/strategy/base.py` with abstract base class

- [x] Implement `BaseStrategy` ABC as specified in design (Section 4.2.1)
- [x] Define abstract properties:
  - `name -> str` — strategy name (e.g., "Gap & Go")
  - `active_phases -> list[StrategyPhase]` — phases during which this strategy evaluates
- [x] Define abstract method:
  - `evaluate(phase: StrategyPhase, market_data: MarketDataStore) -> list[CandidateSignal]`
- [x] Write tests in `tests/test_strategy/test_base.py` (2 tests):
  - ABC cannot be instantiated directly
  - Concrete subclass can be instantiated

**Requirement coverage:** Req 33 (extensible scanning architecture for future strategies)

---

### 5.2 Implement `signalpilot/strategy/gap_and_go.py` with GapAndGoStrategy

- [x] Implement `GapAndGoStrategy(BaseStrategy)` as specified in design (Section 4.2.2)
- [x] Set `name = "Gap & Go"` and `active_phases = [OPENING, ENTRY_WINDOW]`
- [x] Phase-dependent evaluation:
  - **OPENING phase (9:15-9:30 AM):** gap detection + volume accumulation
  - **ENTRY_WINDOW phase (9:30-9:45 AM):** price hold validation + signal generation
- [x] `_detect_gaps_and_accumulate_volume()`:
  - Scan all symbols in MarketDataStore
  - Calculate gap % = `((open_price - prev_close) / prev_close) * 100`
  - Flag candidates with 3-5% gap (inclusive) AND open > prev high (Req 6.1-6.4)
  - Exclude stocks with gap < 3% or > 5% (Req 6.3)
  - Check cumulative volume > 50% of 20-day ADV (Req 7.1-7.3)
- [x] `_validate_and_generate_signals()`:
  - Check current price > opening price strictly (Req 8.2) — fixed per code review H3
  - Disqualify if price at or below open (Req 8.3)
  - Guard against missing historical data (C2 fix)
- [x] `_calculate_stop_loss(entry_price, opening_price)`:
  - SL = opening price (Req 9.1)
  - Cap risk at 3% from entry (Req 9.4)
- [x] `_calculate_targets(entry_price)`:
  - Target 1 = entry * 1.05 (Req 9.2)
  - Target 2 = entry * 1.07 (Req 9.3)
- [x] Track state per candidate using sets/dicts
- [x] IST-aware `datetime.now(IST)` for generated_at (C1 fix)
- [x] Clean disqualified symbols from `_volume_validated` (H1 fix)
- [x] Write tests in `tests/test_strategy/test_gap_and_go.py` (27 tests):
  - Test gap detection at exact 3% boundary (included)
  - Test gap detection at exact 5% boundary (included)
  - Test exclusion when gap = 2.9% (below threshold)
  - Test exclusion when gap = 5.1% (above threshold)
  - Test exclusion when open <= prev high
  - Test volume validation pass (volume > 50% ADV)
  - Test volume validation fail (volume < 50% ADV)
  - Test volume validation on second evaluation
  - Test price hold validation — price above open generates signal
  - Test disqualification — price drops below open
  - Test disqualification — price exactly at open (H3 fix)
  - Test no duplicate signals
  - Test SL calculation with opening price
  - Test SL cap at 3% when gap is large
  - Test SL at boundary
  - Test T1 = entry + 5%, T2 = entry + 7%
  - Test no signals in all inactive phases (parametrized: PRE_MARKET, CONTINUOUS, WIND_DOWN, POST_MARKET)
  - Test reset clears state
  - Test signal contains correct fields
  - Test multiple candidates
  - Test symbol without historical data skipped

**Requirement coverage:** Req 6 (gap detection), Req 7 (volume validation), Req 8 (entry timing), Req 9 (SL/target calculation)

---

## Code Review Fixes Applied
- **C1 (Critical):** Use `datetime.now(IST)` instead of naive `datetime.now()` for signal timestamps
- **C2 (Critical):** Guard against missing/zero-ADV historical data at signal generation with `continue` instead of misleading `adv=1.0` fallback
- **H1 (High):** Clean disqualified symbols from `_volume_validated` set for robust state machine
- **H3 (High):** Strict "above" check (`ltp > open_price`, not `>=`) per spec requirement
- **H4 (High):** Parametrized inactive phase tests covering PRE_MARKET, CONTINUOUS, WIND_DOWN, POST_MARKET
- **M6 (Medium):** Added concrete subclass test for BaseStrategy
