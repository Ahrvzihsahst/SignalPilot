# Task 6: Signal Ranker

## Status: COMPLETED

## References
- Requirements: `/.kiro/specs/signalpilot/requirements.md` (Req 10-11)
- Design: `/.kiro/specs/signalpilot/design.md` (Section 4.3)

---

## Subtasks

### 6.1 Implement `signalpilot/ranking/scorer.py` with SignalScorer

- [x] Reuse `ScoringWeights` dataclass from `signalpilot/db/models.py` (already defined in task 0002)
- [x] Implement `SignalScorer` class as specified in design (Section 4.3.1)
- [x] Normalization functions (all clamp to 0.0-1.0 range):
  - `_normalize_gap(gap_pct)`: 3% → 0.0, 5% → 1.0, linear interpolation
  - `_normalize_volume_ratio(volume_ratio)`: 0.5 → 0.0, 3.0 → 1.0, linear interpolation
  - `_normalize_price_distance(distance_pct)`: 0% → 0.0, 3%+ → 1.0, linear interpolation
- [x] `score(candidate)`: composite = (norm_gap * w1) + (norm_vol * w2) + (norm_dist * w3)
- [x] Write tests in `tests/test_ranking/test_scorer.py` (20 tests):
  - Normalization boundary tests (min, max, midpoint for each factor)
  - Clamping tests (below min → 0.0, above max → 1.0)
  - Negative distance clamped to 0.0
  - Composite scoring: all-min=0.0, all-max=1.0, midpoint=0.5
  - Custom equal weights verification
  - Gap-dominant scoring verification

**Requirement coverage:** Req 10.1 (multi-factor scoring with configurable weights)

---

### 6.2 Implement `signalpilot/ranking/ranker.py` with SignalRanker

- [x] Implement `SignalRanker` class as specified in design (Section 4.3.2)
- [x] `rank(candidates, max_signals=5)`:
  - Score all candidates using SignalScorer
  - Sort in descending order by composite score
  - Assign star ratings via `_score_to_stars()`
  - Return top N (default 5)
- [x] `_score_to_stars(score)`:
  - [0.0, 0.2) → 1 star, [0.2, 0.4) → 2 stars, [0.4, 0.6) → 3 stars,
    [0.6, 0.8) → 4 stars, [0.8, 1.0] → 5 stars
- [x] Write tests in `tests/test_ranking/test_ranker.py` (24 tests):
  - Ranking order (highest score first)
  - Scores descending verification
  - Top-5 cutoff (6 candidates → 5 returned)
  - Custom max_signals
  - Fewer than 5 candidates returns all (Req 11.2)
  - Empty candidate list returns empty
  - Parametrized star rating tests (15 boundary values)
  - Stars assigned correctly in ranked output
  - Single candidate handling
  - Tied scores maintain stable input order

**Requirement coverage:** Req 10.2 (rank descending), Req 10.3 (star rating), Req 11.1 (top 5 selection), Req 11.2 (fewer than 5)

---

## Code Review Result
- **No Critical or High issues found** — approved for production
- Medium: Input validation for weights/max_signals (deferred — not needed for internal-only usage)
- Low: Tied score test added, NaN handling deferred
