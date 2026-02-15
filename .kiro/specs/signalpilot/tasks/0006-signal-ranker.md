# Task 6: Signal Ranker

## References
- Requirements: `/.kiro/specs/signalpilot/requirements.md` (Req 10-11)
- Design: `/.kiro/specs/signalpilot/design.md` (Section 4.3)

---

## Subtasks

### 6.1 Implement `signalpilot/ranking/scorer.py` with SignalScorer

- [ ] Implement `ScoringWeights` dataclass (if not already in models) with: gap_weight, volume_weight, price_distance_weight
- [ ] Implement `SignalScorer` class as specified in design (Section 4.3.1)
- [ ] Normalization functions (all clamp to 0.0-1.0 range):
  - `_normalize_gap(gap_pct: float) -> float`: 3% -> 0.0, 5% -> 1.0, linear interpolation
  - `_normalize_volume_ratio(volume_ratio: float) -> float`: 0.5 -> 0.0, 3.0 -> 1.0, linear interpolation
  - `_normalize_price_distance(distance_pct: float) -> float`: 0% -> 0.0, 3%+ -> 1.0, linear interpolation
- [ ] `score(candidate: CandidateSignal) -> float`:
  - composite = (normalized_gap * gap_weight) + (normalized_volume * volume_weight) + (normalized_price_distance * price_distance_weight)
  - Return composite score (0.0 to 1.0)
- [ ] Write tests in `tests/test_ranking/test_scorer.py`:
  - Verify `_normalize_gap(3.0)` = 0.0, `_normalize_gap(5.0)` = 1.0, `_normalize_gap(4.0)` = 0.5
  - Verify `_normalize_volume_ratio(0.5)` = 0.0, `_normalize_volume_ratio(3.0)` = 1.0
  - Verify `_normalize_price_distance(0.0)` = 0.0, `_normalize_price_distance(3.0)` = 1.0
  - Verify clamping: values below min return 0.0, values above max return 1.0
  - Verify composite scoring with known weights (e.g., equal weights 0.33/0.33/0.33)

**Requirement coverage:** Req 10.1 (multi-factor scoring with configurable weights)

---

### 6.2 Implement `signalpilot/ranking/ranker.py` with SignalRanker

- [ ] Implement `SignalRanker` class as specified in design (Section 4.3.2)
- [ ] `rank(candidates: list[CandidateSignal], max_signals: int = 5) -> list[RankedSignal]`:
  - Score all candidates using SignalScorer
  - Sort in descending order by composite score
  - Assign star ratings via `_score_to_stars()`
  - Return top N (default 5)
- [ ] `_score_to_stars(score: float) -> int`:
  - 0.0-0.2 -> 1 star
  - 0.2-0.4 -> 2 stars
  - 0.4-0.6 -> 3 stars
  - 0.6-0.8 -> 4 stars
  - 0.8-1.0 -> 5 stars
- [ ] Write tests in `tests/test_ranking/test_ranker.py`:
  - Verify ranking order (highest score first)
  - Verify top-5 cutoff (6 candidates -> only 5 returned)
  - Verify star rating assignment for each range
  - Verify fewer than 5 candidates returns all of them (Req 11.2)
  - Verify empty candidate list returns empty result

**Requirement coverage:** Req 10.2 (rank descending), Req 10.3 (star rating), Req 11.1 (top 5 selection), Req 11.2 (fewer than 5)
