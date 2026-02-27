"""Backtesting framework for SignalPilot strategies.

Provides historical data replay, trade simulation, and validation reporting
for Gap & Go, ORB, and VWAP Reversal strategies.
"""

from signalpilot.backtest.data_loader import BacktestCandle, BacktestDataLoader
from signalpilot.backtest.reporter import BacktestReport, BacktestReporter
from signalpilot.backtest.runner import BacktestResult, BacktestRunner, SimulatedTrade

__all__ = [
    "BacktestCandle",
    "BacktestDataLoader",
    "BacktestReport",
    "BacktestReporter",
    "BacktestResult",
    "BacktestRunner",
    "SimulatedTrade",
]
