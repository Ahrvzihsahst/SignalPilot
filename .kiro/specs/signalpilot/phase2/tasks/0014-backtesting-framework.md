# Task 14: Backtesting Framework

## Description
Create a backtesting module that replays historical data through ORB and VWAP strategies, simulates trades with the same rules as the live system, and validates results against minimum performance thresholds.

## Prerequisites
Task 0006 (ORB Strategy), Task 0007 (VWAP Strategy)

## Requirement Coverage
REQ-P2-034, REQ-P2-035

## Files to Create
- `signalpilot/backtest/__init__.py`
- `signalpilot/backtest/data_loader.py`
- `signalpilot/backtest/runner.py`
- `signalpilot/backtest/reporter.py`

## Subtasks

- [ ] 14.1 Create `signalpilot/backtest/__init__.py`
  - Requirement coverage: foundational

- [ ] 14.2 Create `signalpilot/backtest/data_loader.py` with `BacktestDataLoader`
  - `load_historical_data(symbols, period="1y") -> dict[str, DataFrame]` -- fetch 1 year OHLCV via yfinance with local caching
  - Convert to `Candle15Min` and tick-equivalent data structures for strategy replay
  - Requirement coverage: REQ-P2-034

- [ ] 14.3 Create `signalpilot/backtest/runner.py` with `BacktestRunner`
  - `run(strategy_class, data, config) -> BacktestResult`
  - Replay historical data day by day: simulate opening range calculation (ORB), VWAP calculation (VWAP), candle evaluation
  - Apply same position sizing, SL, target, and trailing SL rules as live system
  - Collect all simulated signals and trades
  - Requirement coverage: REQ-P2-034

- [ ] 14.4 Create `signalpilot/backtest/reporter.py` with `BacktestReporter`
  - `validate(result: BacktestResult) -> BacktestReport`
  - Calculate: total signals, win rate, total P&L, avg win, avg loss, expectancy, max consecutive losses, max drawdown
  - Validate against thresholds: win rate > 55%, positive expectancy, max consecutive losses <= 8, max drawdown <= 15%, min 100 signals
  - ORB-specific target: win rate >= 60%
  - VWAP-specific target: win rate >= 65%
  - Output PASS/FAIL with details
  - Requirement coverage: REQ-P2-035

- [ ] 14.5 Write backtest runner tests in `tests/test_backtest/test_runner.py`
  - Test with mock historical data produces expected signal count, test position sizing applied, test SL/target logic simulated
  - Requirement coverage: REQ-P2-034

- [ ] 14.6 Write reporter validation tests in `tests/test_backtest/test_reporter.py`
  - Test PASS scenario (all thresholds met), test FAIL scenario (win rate below 55%), test individual threshold failures
  - Requirement coverage: REQ-P2-035
