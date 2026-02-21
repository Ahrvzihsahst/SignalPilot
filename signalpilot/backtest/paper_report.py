"""Paper trading comparison report.

Compares paper trading results against backtest expectations to determine
whether a strategy is ready for live deployment.
"""

import logging
from dataclasses import dataclass
from datetime import date

logger = logging.getLogger(__name__)


@dataclass
class PaperTradingReport:
    """Comparison of paper trading results vs backtest expectations."""

    strategy_name: str
    period_start: date
    period_end: date
    paper_win_rate: float
    backtest_win_rate: float
    paper_pnl: float
    backtest_expected_pnl: float
    variance_pct: float
    passed: bool
    recommendation: str


class PaperTradingReporter:
    """Generates paper trading comparison reports.

    Compares actual paper trade metrics (win rate, P&L) against the
    corresponding backtest results.  A strategy passes validation when
    the maximum variance across win-rate and P&L stays within the
    configured tolerance (default 10 %).
    """

    TOLERANCE_PCT = 10.0

    def generate_report(
        self,
        strategy_name: str,
        paper_trades: list,
        backtest_win_rate: float,
        backtest_expected_pnl: float,
        period_start: date,
        period_end: date,
    ) -> PaperTradingReport:
        """Generate comparison report between paper trading and backtest results.

        Parameters
        ----------
        strategy_name:
            Human-readable strategy name (e.g. "ORB", "VWAP Reversal").
        paper_trades:
            List of trade-record-like objects with ``exit_price`` and
            ``pnl_amount`` attributes.
        backtest_win_rate:
            Expected win rate from backtesting (0-100).
        backtest_expected_pnl:
            Expected cumulative P&L from backtesting.
        period_start / period_end:
            Date range covered by the paper trades.
        """
        logger.info(
            "Entering generate_report",
            extra={
                "strategy_name": strategy_name,
                "paper_trade_count": len(paper_trades),
            },
        )

        if not paper_trades:
            report = PaperTradingReport(
                strategy_name=strategy_name,
                period_start=period_start,
                period_end=period_end,
                paper_win_rate=0.0,
                backtest_win_rate=backtest_win_rate,
                paper_pnl=0.0,
                backtest_expected_pnl=backtest_expected_pnl,
                variance_pct=100.0,
                passed=False,
                recommendation="OUTSIDE TOLERANCE -- Insufficient paper trades for comparison",
            )
            logger.info(
                "Exiting generate_report",
                extra={"passed": False, "reason": "no_paper_trades"},
            )
            return report

        # Calculate paper metrics
        closed = [t for t in paper_trades if getattr(t, "exit_price", None) is not None]
        wins = sum(1 for t in closed if getattr(t, "pnl_amount", 0) > 0)
        paper_win_rate = (wins / len(closed) * 100) if closed else 0.0
        paper_pnl = sum(getattr(t, "pnl_amount", 0) for t in closed)

        # Calculate variance
        win_rate_variance = abs(paper_win_rate - backtest_win_rate)
        if backtest_expected_pnl != 0:
            pnl_variance = abs(paper_pnl - backtest_expected_pnl) / abs(backtest_expected_pnl) * 100
        else:
            pnl_variance = 100.0
        variance = max(win_rate_variance, pnl_variance)

        passed = variance <= self.TOLERANCE_PCT
        if passed:
            recommendation = "WITHIN TOLERANCE -- Ready for live deployment"
        else:
            recommendation = "OUTSIDE TOLERANCE -- Review and re-calibrate before going live"

        report = PaperTradingReport(
            strategy_name=strategy_name,
            period_start=period_start,
            period_end=period_end,
            paper_win_rate=paper_win_rate,
            backtest_win_rate=backtest_win_rate,
            paper_pnl=paper_pnl,
            backtest_expected_pnl=backtest_expected_pnl,
            variance_pct=variance,
            passed=passed,
            recommendation=recommendation,
        )

        logger.info(
            "Exiting generate_report",
            extra={
                "passed": passed,
                "variance_pct": round(variance, 2),
            },
        )
        return report

    def format_report(self, report: PaperTradingReport) -> str:
        """Format report for Telegram delivery."""
        status = "PASS" if report.passed else "FAIL"
        return (
            f"<b>Paper Trading Report: {report.strategy_name} [{status}]</b>\n"
            f"Period: {report.period_start} to {report.period_end}\n"
            f"\n"
            f"Paper Win Rate: {report.paper_win_rate:.1f}%\n"
            f"Backtest Win Rate: {report.backtest_win_rate:.1f}%\n"
            f"Paper P&L: {report.paper_pnl:+,.0f}\n"
            f"Expected P&L: {report.backtest_expected_pnl:+,.0f}\n"
            f"Variance: {report.variance_pct:.1f}%\n"
            f"\n"
            f"<b>{report.recommendation}</b>"
        )
