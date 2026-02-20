"""Backtest report generation and validation."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from signalpilot.backtest.runner import BacktestResult

logger = logging.getLogger(__name__)


@dataclass
class BacktestReport:
    """Validated backtest report with pass/fail status."""

    strategy_name: str
    total_signals: int
    trades_taken: int
    win_rate: float
    total_pnl: float
    avg_win: float
    avg_loss: float
    expectancy: float
    max_consecutive_losses: int
    max_drawdown_pct: float
    passed: bool
    failures: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """Produce a human-readable multi-line summary of the report."""
        status = "PASS" if self.passed else "FAIL"
        lines = [
            f"Backtest Report: {self.strategy_name} [{status}]",
            f"  Signals: {self.total_signals}, Trades: {self.trades_taken}",
            f"  Win Rate: {self.win_rate:.1f}%",
            f"  Total P&L: {self.total_pnl:+,.0f}",
            f"  Avg Win: {self.avg_win:+,.0f}, Avg Loss: {self.avg_loss:+,.0f}",
            f"  Expectancy: {self.expectancy:+,.0f}",
            f"  Max Consecutive Losses: {self.max_consecutive_losses}",
            f"  Max Drawdown: {self.max_drawdown_pct:.1f}%",
        ]
        if self.failures:
            lines.append("  Failures:")
            for f in self.failures:
                lines.append(f"    - {f}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Strategy-specific validation thresholds
# ---------------------------------------------------------------------------

THRESHOLDS: dict[str, dict[str, float | int]] = {
    "default": {
        "min_win_rate": 55.0,
        "min_signals": 100,
        "max_consecutive_losses": 8,
        "max_drawdown_pct": 15.0,
    },
    "ORB": {
        "min_win_rate": 60.0,
        "min_signals": 100,
        "max_consecutive_losses": 8,
        "max_drawdown_pct": 15.0,
    },
    "VWAP Reversal": {
        "min_win_rate": 65.0,
        "min_signals": 100,
        "max_consecutive_losses": 8,
        "max_drawdown_pct": 15.0,
    },
}


class BacktestReporter:
    """Validates backtest results against strategy-specific thresholds."""

    def validate(self, result: BacktestResult) -> BacktestReport:
        """Validate *result* and produce a pass/fail report.

        Checks: win rate, expectancy, signal count, consecutive losses,
        and maximum drawdown against the thresholds for the strategy.
        """
        logger.info(
            "Entering validate",
            extra={"strategy": result.strategy_name, "trades": result.trades_taken},
        )

        thresholds = THRESHOLDS.get(result.strategy_name, THRESHOLDS["default"])

        max_consec = self._max_consecutive_losses(result)
        max_dd = self._max_drawdown(result)
        expectancy = self._calculate_expectancy(result)

        failures: list[str] = []

        if result.win_rate < thresholds["min_win_rate"]:
            failures.append(
                f"Win rate {result.win_rate:.1f}% below minimum "
                f"{thresholds['min_win_rate']:.1f}%"
            )

        if expectancy <= 0:
            failures.append(f"Negative expectancy: {expectancy:+,.0f}")

        if result.signals_generated < thresholds["min_signals"]:
            failures.append(
                f"Only {result.signals_generated} signals "
                f"(minimum {int(thresholds['min_signals'])})"
            )

        if max_consec > thresholds["max_consecutive_losses"]:
            failures.append(
                f"Max consecutive losses {max_consec} exceeds limit "
                f"{int(thresholds['max_consecutive_losses'])}"
            )

        if max_dd > thresholds["max_drawdown_pct"]:
            failures.append(
                f"Max drawdown {max_dd:.1f}% exceeds limit "
                f"{thresholds['max_drawdown_pct']:.1f}%"
            )

        report = BacktestReport(
            strategy_name=result.strategy_name,
            total_signals=result.signals_generated,
            trades_taken=result.trades_taken,
            win_rate=result.win_rate,
            total_pnl=result.total_pnl,
            avg_win=result.avg_win,
            avg_loss=result.avg_loss,
            expectancy=expectancy,
            max_consecutive_losses=max_consec,
            max_drawdown_pct=max_dd,
            passed=len(failures) == 0,
            failures=failures,
        )

        logger.info(
            "Exiting validate",
            extra={"passed": report.passed, "failure_count": len(failures)},
        )
        return report

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _max_consecutive_losses(self, result: BacktestResult) -> int:
        """Longest streak of consecutive losing trades."""
        max_consec = 0
        current = 0
        for trade in result.trades:
            if trade.exit_price is not None and trade.pnl_amount <= 0:
                current += 1
                max_consec = max(max_consec, current)
            else:
                current = 0
        return max_consec

    def _max_drawdown(self, result: BacktestResult) -> float:
        """Peak-to-trough drawdown as a percentage of the peak equity."""
        if not result.trades:
            return 0.0
        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0
        for trade in result.trades:
            cumulative += trade.pnl_amount
            peak = max(peak, cumulative)
            drawdown = peak - cumulative
            if peak > 0:
                dd_pct = (drawdown / peak) * 100
                max_dd = max(max_dd, dd_pct)
        return max_dd

    def _calculate_expectancy(self, result: BacktestResult) -> float:
        """Expected value per trade based on win/loss distribution."""
        closed = [t for t in result.trades if t.exit_price is not None]
        if not closed:
            return 0.0
        wins = [t for t in closed if t.pnl_amount > 0]
        losses = [t for t in closed if t.pnl_amount <= 0]
        win_rate = len(wins) / len(closed) if closed else 0
        avg_win = sum(t.pnl_amount for t in wins) / len(wins) if wins else 0
        avg_loss = (
            abs(sum(t.pnl_amount for t in losses) / len(losses)) if losses else 0
        )
        return (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
