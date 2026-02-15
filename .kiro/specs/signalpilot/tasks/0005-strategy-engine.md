# Task 5: Strategy Engine

## References
- Requirements: `/.kiro/specs/signalpilot/requirements.md` (Req 6-9, 33)
- Design: `/.kiro/specs/signalpilot/design.md` (Section 4.2)

---

## Subtasks

### 5.1 Implement `signalpilot/strategy/base.py` with abstract base class

- [ ] Implement `BaseStrategy` ABC as specified in design (Section 4.2.1)
- [ ] Define abstract properties:
  - `name -> str` — strategy name (e.g., "Gap & Go")
  - `active_phases -> list[StrategyPhase]` — phases during which this strategy evaluates
- [ ] Define abstract method:
  - `evaluate(phase: StrategyPhase, market_data: MarketDataStore) -> list[CandidateSignal]`
- [ ] Write a trivial test to verify ABC cannot be instantiated directly

**Requirement coverage:** Req 33 (extensible scanning architecture for future strategies)

---

### 5.2 Implement `signalpilot/strategy/gap_and_go.py` with GapAndGoStrategy

- [ ] Implement `GapAndGoStrategy(BaseStrategy)` as specified in design (Section 4.2.2)
- [ ] Set `name = "Gap & Go"` and `active_phases = [OPENING, ENTRY_WINDOW]`
- [ ] Phase-dependent evaluation:
  - **OPENING phase (9:15-9:30 AM):** gap detection + volume accumulation
  - **ENTRY_WINDOW phase (9:30-9:45 AM):** price hold validation + signal generation
- [ ] `_detect_gaps_and_accumulate_volume()`:
  - Scan all symbols in MarketDataStore
  - Calculate gap % = `((open_price - prev_close) / prev_close) * 100`
  - Flag candidates with 3-5% gap (inclusive) AND open > prev high (Req 6.1-6.4)
  - Exclude stocks with gap < 3% or > 5% (Req 6.3)
  - At 9:30 AM: check cumulative volume > 50% of 20-day ADV (Req 7.1-7.3)
- [ ] `_validate_and_generate_signals()`:
  - Check current price > opening price (Req 8.2)
  - Disqualify if price drops below open at any point (Req 8.3)
  - No signals after 9:45 AM for Gap & Go (Req 8.4)
- [ ] `_calculate_stop_loss(entry_price, opening_price)`:
  - SL = opening price (Req 9.1)
  - Cap risk at 3% from entry (Req 9.4): if `(entry - opening_price) / entry > 0.03`, adjust SL to `entry * 0.97`
- [ ] `_calculate_targets(entry_price)`:
  - Target 1 = entry * 1.05 (Req 9.2)
  - Target 2 = entry * 1.07 (Req 9.3)
- [ ] Track state per candidate using sets:
  - `_gap_candidates` — symbols with valid gap
  - `_volume_validated` — symbols passing volume check
  - `_disqualified` — symbols where price fell below open
  - `_signals_generated` — symbols for which signals were already created (prevent duplicates)
- [ ] Write tests in `tests/test_strategy/test_gap_and_go.py`:
  - Test gap detection at exact 3% boundary (included)
  - Test gap detection at exact 5% boundary (included)
  - Test exclusion when gap = 2.9% (below threshold)
  - Test exclusion when gap = 5.1% (above threshold)
  - Test exclusion when open <= prev high
  - Test volume validation pass (volume > 50% ADV)
  - Test volume validation fail (volume < 50% ADV)
  - Test price hold validation — price above open generates signal
  - Test disqualification — price drops below open
  - Test SL calculation with opening price
  - Test SL cap at 3% when gap is large
  - Test T1 = entry + 5%, T2 = entry + 7%
  - Test no signal generated after 9:45 AM

**Requirement coverage:** Req 6 (gap detection), Req 7 (volume validation), Req 8 (entry timing), Req 9 (SL/target calculation)
