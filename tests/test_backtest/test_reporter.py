"""Tests for the backtest reporter and validation logic."""

from datetime import date

from signalpilot.backtest.reporter import THRESHOLDS, BacktestReporter
from signalpilot.backtest.runner import BacktestResult, SimulatedTrade

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _winning_trade(pnl: float = 500.0) -> SimulatedTrade:
    """Create a closed winning trade."""
    return SimulatedTrade(
        symbol="WIN",
        strategy="test",
        entry_price=100.0,
        stop_loss=95.0,
        target_1=110.0,
        target_2=120.0,
        entry_date=date(2025, 1, 15),
        exit_price=105.0,
        exit_date=date(2025, 1, 15),
        exit_reason="t1_hit",
        pnl_amount=pnl,
        pnl_pct=5.0,
    )


def _losing_trade(pnl: float = -200.0) -> SimulatedTrade:
    """Create a closed losing trade."""
    return SimulatedTrade(
        symbol="LOSE",
        strategy="test",
        entry_price=100.0,
        stop_loss=95.0,
        target_1=110.0,
        target_2=120.0,
        entry_date=date(2025, 1, 15),
        exit_price=98.0,
        exit_date=date(2025, 1, 15),
        exit_reason="sl_hit",
        pnl_amount=pnl,
        pnl_pct=-2.0,
    )


def _make_result(
    strategy_name: str = "test",
    wins: int = 70,
    losses: int = 30,
    win_pnl: float = 500.0,
    loss_pnl: float = -200.0,
    signals: int | None = None,
    interleave: bool = True,
) -> BacktestResult:
    """Build a BacktestResult with the specified win/loss distribution.

    When *interleave* is True (default), wins and losses are distributed
    evenly so that consecutive-loss and drawdown metrics stay low.
    """
    win_trades = [_winning_trade(win_pnl) for _ in range(wins)]
    loss_trades = [_losing_trade(loss_pnl) for _ in range(losses)]

    if interleave and wins > 0 and losses > 0:
        # Distribute losses evenly among wins to keep max consecutive low
        trades: list[SimulatedTrade] = []
        ratio = max(1, wins // max(losses, 1))
        wi, li = 0, 0
        while wi < wins or li < losses:
            for _ in range(ratio):
                if wi < wins:
                    trades.append(win_trades[wi])
                    wi += 1
            if li < losses:
                trades.append(loss_trades[li])
                li += 1
    else:
        trades = win_trades + loss_trades

    total_trades = wins + losses
    return BacktestResult(
        strategy_name=strategy_name,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 3, 31),
        signals_generated=signals if signals is not None else total_trades + 20,
        trades_taken=total_trades,
        trades=trades,
    )


# ---------------------------------------------------------------------------
# Pass scenario
# ---------------------------------------------------------------------------


class TestBacktestReporterPass:
    """Test that a result meeting all thresholds passes validation."""

    def test_all_thresholds_met(self):
        # Use smaller losses to keep drawdown under 15%
        result = _make_result(wins=70, losses=30, signals=150, win_pnl=500.0, loss_pnl=-50.0)
        reporter = BacktestReporter()
        report = reporter.validate(result)

        assert report.passed is True, f"Failures: {report.failures}"
        assert report.failures == []
        assert report.win_rate == 70.0
        assert report.total_signals == 150
        assert report.trades_taken == 100

    def test_summary_contains_pass(self):
        result = _make_result(wins=70, losses=30, signals=150, win_pnl=500.0, loss_pnl=-50.0)
        reporter = BacktestReporter()
        report = reporter.validate(result)

        summary = report.summary()
        assert "[PASS]" in summary
        assert "Failures:" not in summary


# ---------------------------------------------------------------------------
# Fail: win rate below threshold
# ---------------------------------------------------------------------------


class TestFailWinRate:
    """Test that low win rate triggers failure."""

    def test_win_rate_below_default_threshold(self):
        # Default threshold is 55%. 40 wins / 100 = 40%.
        result = _make_result(wins=40, losses=60, signals=150)
        reporter = BacktestReporter()
        report = reporter.validate(result)

        assert report.passed is False
        assert any("Win rate" in f for f in report.failures)

    def test_win_rate_exactly_at_threshold_passes(self):
        # 55 wins / 100 = 55.0% -- exactly at default threshold
        result = _make_result(wins=55, losses=45, signals=150)
        reporter = BacktestReporter()
        report = reporter.validate(result)

        # Should pass the win rate check (>= not >)
        assert not any("Win rate" in f for f in report.failures)


# ---------------------------------------------------------------------------
# Fail: negative expectancy
# ---------------------------------------------------------------------------


class TestFailExpectancy:
    """Test that negative expectancy triggers failure."""

    def test_negative_expectancy(self):
        # Many small wins overwhelmed by large losses
        result = _make_result(wins=60, losses=40, win_pnl=10.0, loss_pnl=-500.0, interleave=True)
        reporter = BacktestReporter()
        report = reporter.validate(result)

        assert report.passed is False
        assert any("expectancy" in f.lower() for f in report.failures)


# ---------------------------------------------------------------------------
# Fail: insufficient signals
# ---------------------------------------------------------------------------


class TestFailInsufficientSignals:
    """Test that too few signals triggers failure."""

    def test_below_min_signals(self):
        result = _make_result(wins=7, losses=3, signals=50)
        reporter = BacktestReporter()
        report = reporter.validate(result)

        assert report.passed is False
        assert any("signals" in f.lower() for f in report.failures)

    def test_exactly_min_signals_passes(self):
        result = _make_result(wins=70, losses=30, signals=100)
        reporter = BacktestReporter()
        report = reporter.validate(result)

        assert not any(
            "signals" in f.lower() and "minimum" in f.lower() for f in report.failures
        )


# ---------------------------------------------------------------------------
# Fail: max consecutive losses exceeded
# ---------------------------------------------------------------------------


class TestFailConsecutiveLosses:
    """Test that excessive consecutive losses triggers failure."""

    def test_too_many_consecutive_losses(self):
        # Build trades: 5 wins then 10 losses in a row (exceeds limit of 8)
        trades = [_winning_trade() for _ in range(5)] + [
            _losing_trade() for _ in range(10)
        ]
        result = BacktestResult(
            strategy_name="test",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 3, 31),
            signals_generated=150,
            trades_taken=15,
            trades=trades,
        )
        reporter = BacktestReporter()
        report = reporter.validate(result)

        assert report.passed is False
        assert any("consecutive" in f.lower() for f in report.failures)
        assert report.max_consecutive_losses == 10

    def test_consecutive_losses_within_limit_passes(self):
        # 5 wins, 7 losses (within limit of 8)
        trades = [_winning_trade() for _ in range(60)] + [
            _losing_trade() for _ in range(7)
        ]
        # Interleave enough wins at end to keep the test realistic
        trades.append(_winning_trade())
        result = BacktestResult(
            strategy_name="test",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 3, 31),
            signals_generated=150,
            trades_taken=68,
            trades=trades,
        )
        reporter = BacktestReporter()
        report = reporter.validate(result)

        assert not any("consecutive" in f.lower() for f in report.failures)


# ---------------------------------------------------------------------------
# Fail: max drawdown exceeded
# ---------------------------------------------------------------------------


class TestFailMaxDrawdown:
    """Test that excessive drawdown triggers failure."""

    def test_drawdown_exceeds_limit(self):
        # Create a sequence where equity peaks then drops significantly.
        # 10 big wins (+5000 each) then 20 losses (-1000 each).
        # Peak = 50,000. Drawdown = 20,000. DD% = 40%.
        trades = [_winning_trade(pnl=5000.0) for _ in range(10)] + [
            _losing_trade(pnl=-1000.0) for _ in range(20)
        ]
        result = BacktestResult(
            strategy_name="test",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 3, 31),
            signals_generated=150,
            trades_taken=30,
            trades=trades,
        )
        reporter = BacktestReporter()
        report = reporter.validate(result)

        assert report.passed is False
        assert any("drawdown" in f.lower() for f in report.failures)
        assert report.max_drawdown_pct > 15.0


# ---------------------------------------------------------------------------
# Strategy-specific thresholds
# ---------------------------------------------------------------------------


class TestStrategySpecificThresholds:
    """Test that ORB and VWAP strategies use their own higher thresholds."""

    def test_orb_uses_60_pct_min_win_rate(self):
        assert THRESHOLDS["ORB"]["min_win_rate"] == 60.0

        # 58% win rate -- passes default (55%) but fails ORB (60%).
        result = _make_result(strategy_name="ORB", wins=58, losses=42, signals=150)
        reporter = BacktestReporter()
        report = reporter.validate(result)

        assert report.passed is False
        assert any("Win rate" in f for f in report.failures)

    def test_orb_passes_at_60_pct(self):
        result = _make_result(strategy_name="ORB", wins=60, losses=40, signals=150)
        reporter = BacktestReporter()
        report = reporter.validate(result)

        assert not any("Win rate" in f for f in report.failures)

    def test_vwap_uses_65_pct_min_win_rate(self):
        assert THRESHOLDS["VWAP Reversal"]["min_win_rate"] == 65.0

        # 62% win rate -- passes default and ORB but fails VWAP (65%).
        result = _make_result(
            strategy_name="VWAP Reversal", wins=62, losses=38, signals=150
        )
        reporter = BacktestReporter()
        report = reporter.validate(result)

        assert report.passed is False
        assert any("Win rate" in f for f in report.failures)

    def test_vwap_passes_at_65_pct(self):
        result = _make_result(
            strategy_name="VWAP Reversal", wins=65, losses=35, signals=150
        )
        reporter = BacktestReporter()
        report = reporter.validate(result)

        assert not any("Win rate" in f for f in report.failures)

    def test_unknown_strategy_uses_default(self):
        result = _make_result(
            strategy_name="Unknown Strategy", wins=56, losses=44, signals=150
        )
        reporter = BacktestReporter()
        report = reporter.validate(result)

        # 56% > 55% default -- should pass win rate check
        assert not any("Win rate" in f for f in report.failures)


# ---------------------------------------------------------------------------
# Report summary
# ---------------------------------------------------------------------------


class TestReportSummary:
    """Test the human-readable report summary output."""

    def test_summary_shows_fail_reasons(self):
        result = _make_result(wins=30, losses=70, signals=50)
        reporter = BacktestReporter()
        report = reporter.validate(result)

        summary = report.summary()
        assert "[FAIL]" in summary
        assert "Failures:" in summary

    def test_report_fields_populated(self):
        result = _make_result(wins=70, losses=30, signals=150)
        reporter = BacktestReporter()
        report = reporter.validate(result)

        assert report.strategy_name == "test"
        assert report.total_signals == 150
        assert report.trades_taken == 100
        assert report.win_rate == 70.0
        assert report.avg_win > 0
        assert report.avg_loss < 0
        assert report.expectancy > 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases for the reporter."""

    def test_empty_trades(self):
        result = BacktestResult(
            strategy_name="test",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 3, 31),
            signals_generated=0,
            trades_taken=0,
        )
        reporter = BacktestReporter()
        report = reporter.validate(result)

        assert report.passed is False
        assert report.max_drawdown_pct == 0.0
        assert report.expectancy == 0.0

    def test_all_wins(self):
        result = _make_result(wins=100, losses=0, signals=150)
        reporter = BacktestReporter()
        report = reporter.validate(result)

        assert report.win_rate == 100.0
        assert report.max_consecutive_losses == 0
        assert report.max_drawdown_pct == 0.0
        assert report.passed is True
