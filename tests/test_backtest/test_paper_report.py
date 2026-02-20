"""Tests for paper trading comparison report."""

from dataclasses import dataclass
from datetime import date

from signalpilot.backtest.paper_report import PaperTradingReport, PaperTradingReporter


@dataclass
class _FakeTrade:
    """Minimal trade-like object for testing."""

    exit_price: float | None = None
    pnl_amount: float = 0.0


# ---------------------------------------------------------------------------
# PaperTradingReporter.generate_report
# ---------------------------------------------------------------------------


class TestGenerateReport:
    """Test suite for PaperTradingReporter.generate_report."""

    def setup_method(self):
        self.reporter = PaperTradingReporter()
        self.period_start = date(2025, 2, 1)
        self.period_end = date(2025, 2, 28)

    def test_within_tolerance_passes(self):
        """Report within tolerance (variance <= 10%) should pass."""
        # Backtest: 60% win rate, +5000 P&L
        # Paper: 3 wins out of 5 = 60% win rate, ~+5000 P&L
        trades = [
            _FakeTrade(exit_price=105.0, pnl_amount=500.0),
            _FakeTrade(exit_price=110.0, pnl_amount=1500.0),
            _FakeTrade(exit_price=108.0, pnl_amount=1200.0),
            _FakeTrade(exit_price=95.0, pnl_amount=-300.0),
            _FakeTrade(exit_price=97.0, pnl_amount=-100.0),
        ]
        # paper_pnl = 500 + 1500 + 1200 - 300 - 100 = 2800
        # paper_win_rate = 3/5 * 100 = 60.0
        # backtest_win_rate = 60.0 -> win_rate_variance = 0
        # backtest_expected_pnl = 2800 -> pnl_variance = 0
        report = self.reporter.generate_report(
            strategy_name="ORB",
            paper_trades=trades,
            backtest_win_rate=60.0,
            backtest_expected_pnl=2800.0,
            period_start=self.period_start,
            period_end=self.period_end,
        )

        assert report.passed is True
        assert report.variance_pct <= self.reporter.TOLERANCE_PCT
        assert "WITHIN TOLERANCE" in report.recommendation
        assert report.strategy_name == "ORB"
        assert report.paper_win_rate == 60.0
        assert report.paper_pnl == 2800.0

    def test_outside_tolerance_fails(self):
        """Report outside tolerance (variance > 10%) should fail."""
        # Paper: 1 win out of 5 = 20% win rate
        # Backtest: 60% win rate -> win_rate_variance = 40
        trades = [
            _FakeTrade(exit_price=110.0, pnl_amount=500.0),
            _FakeTrade(exit_price=90.0, pnl_amount=-600.0),
            _FakeTrade(exit_price=92.0, pnl_amount=-400.0),
            _FakeTrade(exit_price=88.0, pnl_amount=-800.0),
            _FakeTrade(exit_price=91.0, pnl_amount=-500.0),
        ]

        report = self.reporter.generate_report(
            strategy_name="VWAP Reversal",
            paper_trades=trades,
            backtest_win_rate=60.0,
            backtest_expected_pnl=5000.0,
            period_start=self.period_start,
            period_end=self.period_end,
        )

        assert report.passed is False
        assert report.variance_pct > self.reporter.TOLERANCE_PCT
        assert "OUTSIDE TOLERANCE" in report.recommendation
        assert report.strategy_name == "VWAP Reversal"

    def test_no_paper_trades_fails(self):
        """No paper trades should result in failure with insufficient trades message."""
        report = self.reporter.generate_report(
            strategy_name="ORB",
            paper_trades=[],
            backtest_win_rate=55.0,
            backtest_expected_pnl=3000.0,
            period_start=self.period_start,
            period_end=self.period_end,
        )

        assert report.passed is False
        assert report.variance_pct == 100.0
        assert "Insufficient paper trades" in report.recommendation
        assert report.paper_win_rate == 0.0
        assert report.paper_pnl == 0.0

    def test_zero_backtest_pnl_uses_full_variance(self):
        """When backtest expected P&L is zero, pnl_variance defaults to 100%."""
        trades = [
            _FakeTrade(exit_price=105.0, pnl_amount=500.0),
        ]

        report = self.reporter.generate_report(
            strategy_name="ORB",
            paper_trades=trades,
            backtest_win_rate=100.0,
            backtest_expected_pnl=0.0,
            period_start=self.period_start,
            period_end=self.period_end,
        )

        # pnl_variance = 100.0 because backtest_expected_pnl is 0
        assert report.passed is False
        assert report.variance_pct == 100.0

    def test_trades_without_exit_price_excluded_from_win_rate(self):
        """Trades with exit_price=None should be excluded from win rate calc."""
        trades = [
            _FakeTrade(exit_price=110.0, pnl_amount=1000.0),
            _FakeTrade(exit_price=None, pnl_amount=0.0),  # still open
            _FakeTrade(exit_price=95.0, pnl_amount=-200.0),
        ]
        # Only 2 closed trades: 1 win / 2 = 50% win rate
        # paper_pnl = 1000 + 0 - 200 = 800

        report = self.reporter.generate_report(
            strategy_name="ORB",
            paper_trades=trades,
            backtest_win_rate=50.0,
            backtest_expected_pnl=800.0,
            period_start=self.period_start,
            period_end=self.period_end,
        )

        assert report.paper_win_rate == 50.0
        assert report.paper_pnl == 800.0
        assert report.passed is True

    def test_report_date_range_preserved(self):
        """Report should preserve the provided period start and end dates."""
        start = date(2025, 3, 1)
        end = date(2025, 3, 15)

        report = self.reporter.generate_report(
            strategy_name="ORB",
            paper_trades=[],
            backtest_win_rate=50.0,
            backtest_expected_pnl=1000.0,
            period_start=start,
            period_end=end,
        )

        assert report.period_start == start
        assert report.period_end == end


# ---------------------------------------------------------------------------
# PaperTradingReporter.format_report
# ---------------------------------------------------------------------------


class TestFormatReport:
    """Test suite for PaperTradingReporter.format_report."""

    def setup_method(self):
        self.reporter = PaperTradingReporter()

    def test_format_passing_report(self):
        """Formatted report for a passing result includes PASS and key metrics."""
        report = PaperTradingReport(
            strategy_name="ORB",
            period_start=date(2025, 2, 1),
            period_end=date(2025, 2, 28),
            paper_win_rate=58.0,
            backtest_win_rate=60.0,
            paper_pnl=4800.0,
            backtest_expected_pnl=5000.0,
            variance_pct=4.0,
            passed=True,
            recommendation="WITHIN TOLERANCE -- Ready for live deployment",
        )

        text = self.reporter.format_report(report)

        assert "ORB" in text
        assert "[PASS]" in text
        assert "58.0%" in text
        assert "60.0%" in text
        assert "+4,800" in text
        assert "+5,000" in text
        assert "4.0%" in text
        assert "WITHIN TOLERANCE" in text

    def test_format_failing_report(self):
        """Formatted report for a failing result includes FAIL."""
        report = PaperTradingReport(
            strategy_name="VWAP Reversal",
            period_start=date(2025, 2, 1),
            period_end=date(2025, 2, 28),
            paper_win_rate=30.0,
            backtest_win_rate=60.0,
            paper_pnl=-2000.0,
            backtest_expected_pnl=5000.0,
            variance_pct=30.0,
            passed=False,
            recommendation="OUTSIDE TOLERANCE -- Review and re-calibrate before going live",
        )

        text = self.reporter.format_report(report)

        assert "VWAP Reversal" in text
        assert "[FAIL]" in text
        assert "OUTSIDE TOLERANCE" in text
        assert "-2,000" in text

    def test_format_includes_period(self):
        """Formatted report includes the period date range."""
        report = PaperTradingReport(
            strategy_name="ORB",
            period_start=date(2025, 3, 1),
            period_end=date(2025, 3, 31),
            paper_win_rate=0.0,
            backtest_win_rate=0.0,
            paper_pnl=0.0,
            backtest_expected_pnl=0.0,
            variance_pct=0.0,
            passed=True,
            recommendation="WITHIN TOLERANCE -- Ready for live deployment",
        )

        text = self.reporter.format_report(report)

        assert "2025-03-01" in text
        assert "2025-03-31" in text
