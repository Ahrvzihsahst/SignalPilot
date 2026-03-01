# Task 4: Regime Data Collector

## Description
Implement `RegimeDataCollector` in `backend/signalpilot/intelligence/regime_data.py` with the `RegimeInputs` and `PreMarketData` dataclasses. This component fetches all external data needed for regime classification: India VIX (with fallback chain), Nifty 50 gap/range/direction, SGX Nifty, S&P 500, FII/DII flows, and previous day range. Each data source has independent error handling and defaults to neutral on failure.

## Prerequisites
Task 3 (Configuration -- needs AppConfig fields)

## Requirement Coverage
REQ-MRD-001, REQ-MRD-002, REQ-MRD-003, REQ-MRD-004, REQ-MRD-005, REQ-MRD-006, REQ-MRD-007

## Files to Create
- `signalpilot/intelligence/regime_data.py`

## Files to Modify
- `signalpilot/intelligence/__init__.py` (ensure package exists -- may already exist from NSF)

## Subtasks

### 4.1 Create `RegimeInputs` and `PreMarketData` dataclasses

- [ ] Define `RegimeInputs` dataclass with all fields from Design Section 3.1: `india_vix`, `nifty_gap_pct`, `nifty_first_15_range_pct`, `nifty_first_15_direction`, `prev_day_range_pct`, `fii_net_crores`, `dii_net_crores`, `sgx_direction`, `sp500_change_pct`, `collected_at` -- all nullable with `None` defaults
- [ ] Define `PreMarketData` dataclass with fields for pre-market data: `india_vix`, `sp500_change_pct`, `nasdaq_change_pct`, `sgx_direction`, `sgx_change_pct`, `nikkei_change_pct`, `hang_seng_change_pct`, `fii_net_crores`, `dii_net_crores`, `collected_at` -- all nullable
- Requirement coverage: REQ-MRD-001 through REQ-MRD-006

### 4.2 Implement `RegimeDataCollector` class

- [ ] Constructor accepts `market_data` (MarketDataStore) and `config` (AppConfig), initializes `_session_cache` dict and `_pre_market_data: PreMarketData | None`
- [ ] Implement `async def fetch_current_vix() -> float | None` with fallback chain: SmartAPI VIX token -> nsetools -> NSE VIX page scraping. Return `None` and log WARNING if all fail
- [ ] Implement `async def fetch_global_cues() -> dict` fetching SGX Nifty direction and S&P 500 change via aiohttp/yfinance. Return neutral dict on failure
- [ ] Implement `async def fetch_fii_dii() -> tuple[float | None, float | None]` fetching previous day's net FII and DII in crores. Return `(None, None)` on failure
- [ ] Implement `async def collect_pre_market_data() -> PreMarketData` combining VIX + global cues + FII/DII. Cache result in `_pre_market_data`. Each source failure is independent
- [ ] Implement `async def collect_regime_inputs() -> RegimeInputs` combining cached pre-market data with fresh Nifty 50 data: opening gap `(today_open - yesterday_close) / yesterday_close * 100`, first-15-min range `(high - low) / open * 100`, first-15-min direction (UP/DOWN/FLAT based on close vs open), plus previous day range from HistoricalDataFetcher
- [ ] Implement `def get_cached_pre_market_data() -> PreMarketData | None` returning cached pre-market data
- [ ] Implement `async def get_current_nifty_data() -> dict` for re-classification checkpoint use (ltp, open, high, low, change_pct)
- [ ] Each individual data source failure MUST be caught, logged at WARNING level, and the corresponding input set to None
- Requirement coverage: REQ-MRD-001, REQ-MRD-002, REQ-MRD-003, REQ-MRD-004, REQ-MRD-005, REQ-MRD-006, REQ-MRD-007

### 4.3 Write unit tests

- [ ] Write tests in `backend/tests/test_intelligence/test_regime_data.py` covering:
  - VIX fetch from primary source returns float
  - VIX fallback to nsetools when SmartAPI fails
  - VIX all sources fail returns None and logs WARNING
  - Nifty gap calculation: `(open - prev_close) / prev_close * 100`
  - Nifty gap with missing data returns None
  - First-15-min range calculation: `(high - low) / open * 100`
  - First-15-min direction UP (close > open), DOWN (close < open), FLAT (within 0.01%)
  - Previous day range calculation
  - FII/DII fetch success and failure
  - Global cues fetch success and failure
  - `collect_regime_inputs()` with all data available
  - `collect_regime_inputs()` with partial failures -- remaining inputs still collected
  - `collect_pre_market_data()` caches result
  - `get_cached_pre_market_data()` returns cached data
- Requirement coverage: REQ-MRD-001 through REQ-MRD-007
