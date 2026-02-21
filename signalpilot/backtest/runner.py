"""Backtest runner -- replays historical data through strategies."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Callable

from signalpilot.backtest.data_loader import BacktestCandle
from signalpilot.db.models import CandidateSignal

logger = logging.getLogger(__name__)


@dataclass
class SimulatedTrade:
    """A trade simulated during backtesting."""

    symbol: str
    strategy: str
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float
    entry_date: date
    exit_price: float | None = None
    exit_date: date | None = None
    exit_reason: str | None = None
    pnl_amount: float = 0.0
    pnl_pct: float = 0.0


@dataclass
class BacktestResult:
    """Results from a backtest run."""

    strategy_name: str
    start_date: date
    end_date: date
    signals_generated: int = 0
    trades_taken: int = 0
    trades: list[SimulatedTrade] = field(default_factory=list)

    @property
    def wins(self) -> int:
        """Count of trades that closed with positive P&L."""
        return sum(1 for t in self.trades if t.pnl_amount > 0)

    @property
    def losses(self) -> int:
        """Count of trades that closed with non-positive P&L."""
        return sum(
            1 for t in self.trades if t.pnl_amount <= 0 and t.exit_price is not None
        )

    @property
    def win_rate(self) -> float:
        """Win percentage among closed trades."""
        closed = [t for t in self.trades if t.exit_price is not None]
        if not closed:
            return 0.0
        return (self.wins / len(closed)) * 100

    @property
    def total_pnl(self) -> float:
        """Sum of P&L across all trades."""
        return sum(t.pnl_amount for t in self.trades)

    @property
    def avg_win(self) -> float:
        """Average P&L of winning trades."""
        wins = [t.pnl_amount for t in self.trades if t.pnl_amount > 0]
        return sum(wins) / len(wins) if wins else 0.0

    @property
    def avg_loss(self) -> float:
        """Average P&L of losing trades."""
        losses = [
            t.pnl_amount
            for t in self.trades
            if t.pnl_amount <= 0 and t.exit_price is not None
        ]
        return sum(losses) / len(losses) if losses else 0.0


# Type alias for the strategy evaluation callback.
EvaluateFn = Callable[
    [str, list[BacktestCandle], BacktestCandle],
    CandidateSignal | None,
]

# Fixed quantity used in backtest P&L calculation.
_BACKTEST_QTY = 100


class BacktestRunner:
    """Replays historical data through strategy logic to simulate trading.

    For each trading day in the data window the runner:
    1. Checks open trades for SL / target exits.
    2. Evaluates symbols for new entry signals (up to ``max_positions``).
    3. Force-closes any remaining open trades at end of day (intraday only).
    """

    def __init__(self, max_positions: int = 8):
        self._max_positions = max_positions

    def run(
        self,
        strategy_name: str,
        data: dict[str, list[BacktestCandle]],
        evaluate_fn: EvaluateFn,
        start_date: date,
        end_date: date,
    ) -> BacktestResult:
        """Run backtest by replaying candle data through *evaluate_fn*.

        Parameters
        ----------
        strategy_name:
            Label for the strategy being tested.
        data:
            Mapping of symbol to list of ``BacktestCandle`` (may span many days).
        evaluate_fn:
            ``(symbol, candles_so_far, current_candle) -> CandidateSignal | None``
        start_date, end_date:
            Inclusive date range to simulate.

        Returns
        -------
        BacktestResult with all simulated trades and aggregate stats.
        """
        logger.info(
            "Entering run",
            extra={
                "strategy": strategy_name,
                "symbols": len(data),
                "start": str(start_date),
                "end": str(end_date),
            },
        )

        result = BacktestResult(
            strategy_name=strategy_name,
            start_date=start_date,
            end_date=end_date,
        )

        open_trades: list[SimulatedTrade] = []

        # Discover all unique trading days within the window.
        all_dates = sorted(
            {
                c.date
                for candles in data.values()
                for c in candles
                if start_date <= c.date <= end_date
            }
        )

        for day in all_dates:
            # Partition candles by symbol for this day.
            day_candles: dict[str, list[BacktestCandle]] = {}
            for symbol, candles in data.items():
                day_candles[symbol] = [c for c in candles if c.date == day]

            # --- 1. Check exits on open trades ---
            for trade in list(open_trades):
                exit_result = self._check_exit(
                    trade, day_candles.get(trade.symbol, [])
                )
                if exit_result is not None:
                    exit_price, exit_reason = exit_result
                    trade.exit_price = exit_price
                    trade.exit_date = day
                    trade.exit_reason = exit_reason
                    trade.pnl_amount = (exit_price - trade.entry_price) * _BACKTEST_QTY
                    trade.pnl_pct = (
                        (exit_price - trade.entry_price) / trade.entry_price
                    ) * 100
                    open_trades.remove(trade)

            # --- 2. Generate new signals ---
            if len(open_trades) < self._max_positions:
                for symbol, candles in day_candles.items():
                    if not candles:
                        continue
                    signal = evaluate_fn(symbol, candles, candles[-1])
                    if signal is not None:
                        result.signals_generated += 1
                        if len(open_trades) < self._max_positions:
                            trade = SimulatedTrade(
                                symbol=symbol,
                                strategy=strategy_name,
                                entry_price=signal.entry_price,
                                stop_loss=signal.stop_loss,
                                target_1=signal.target_1,
                                target_2=signal.target_2,
                                entry_date=day,
                            )
                            open_trades.append(trade)
                            result.trades.append(trade)
                            result.trades_taken += 1

            # --- 3. Intra-day SL/target check for newly opened trades ---
            for trade in list(open_trades):
                if trade.exit_price is not None:
                    continue
                exit_result = self._check_exit(
                    trade, day_candles.get(trade.symbol, [])
                )
                if exit_result is not None:
                    exit_price, exit_reason = exit_result
                    trade.exit_price = exit_price
                    trade.exit_date = day
                    trade.exit_reason = exit_reason
                    trade.pnl_amount = (exit_price - trade.entry_price) * _BACKTEST_QTY
                    trade.pnl_pct = (
                        (exit_price - trade.entry_price) / trade.entry_price
                    ) * 100
                    open_trades.remove(trade)

            # --- 4. EOD close (intraday strategy) ---
            for trade in list(open_trades):
                day_data = day_candles.get(trade.symbol, [])
                if day_data:
                    last_candle = day_data[-1]
                    trade.exit_price = last_candle.close
                    trade.exit_date = day
                    trade.exit_reason = "eod_close"
                    trade.pnl_amount = (
                        last_candle.close - trade.entry_price
                    ) * _BACKTEST_QTY
                    trade.pnl_pct = (
                        (last_candle.close - trade.entry_price) / trade.entry_price
                    ) * 100
                    open_trades.remove(trade)

        logger.info(
            "Exiting run",
            extra={
                "signals": result.signals_generated,
                "trades": result.trades_taken,
                "total_pnl": result.total_pnl,
            },
        )
        return result

    def _check_exit(
        self, trade: SimulatedTrade, candles: list[BacktestCandle]
    ) -> tuple[float, str] | None:
        """Check if *trade* should exit based on intraday candle data.

        Returns ``(exit_price, reason)`` or ``None`` if no exit triggered.
        Priority: stop-loss first, then target-2.
        """
        for candle in candles:
            # SL hit
            if candle.low <= trade.stop_loss:
                return (trade.stop_loss, "sl_hit")
            # T2 hit
            if candle.high >= trade.target_2:
                return (trade.target_2, "t2_hit")
        return None
