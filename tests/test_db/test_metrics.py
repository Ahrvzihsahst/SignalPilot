"""Tests for MetricsCalculator."""

from datetime import date, datetime

import pytest

from signalpilot.db.models import SignalRecord, TradeRecord


async def _insert_signal(signal_repo, d=None):
    d = d or date(2026, 2, 16)
    signal = SignalRecord(
        date=d,
        symbol="SBIN",
        strategy="gap_and_go",
        entry_price=770.0,
        stop_loss=745.0,
        target_1=808.5,
        target_2=823.9,
        quantity=13,
        capital_required=10010.0,
        signal_strength=4,
        gap_pct=4.05,
        volume_ratio=1.8,
        reason="Gap up",
        created_at=datetime(d.year, d.month, d.day, 9, 35, 0),
        expires_at=datetime(d.year, d.month, d.day, 10, 5, 0),
    )
    return await signal_repo.insert_signal(signal)


async def _insert_closed_trade(
    trade_repo, signal_id, symbol="SBIN", pnl_amount=500.0,
    d=None, taken_at=None,
):
    d = d or date(2026, 2, 16)
    taken_at = taken_at or datetime(d.year, d.month, d.day, 9, 36, 0)
    trade = TradeRecord(
        signal_id=signal_id,
        date=d,
        symbol=symbol,
        entry_price=770.0,
        stop_loss=745.0,
        target_1=808.5,
        target_2=823.9,
        quantity=13,
        taken_at=taken_at,
    )
    trade_id = await trade_repo.insert_trade(trade)
    pnl_pct = pnl_amount / 770.0 * 100
    exit_reason = "t1_hit" if pnl_amount > 0 else "sl_hit"
    await trade_repo.close_trade(trade_id, 770.0 + pnl_amount / 13, pnl_amount, pnl_pct, exit_reason)
    return trade_id


class TestMetricsCalculator:
    async def test_no_trades_returns_zero_metrics(self, metrics):
        result = await metrics.calculate_performance_metrics()
        assert result.total_signals == 0
        assert result.trades_taken == 0
        assert result.wins == 0
        assert result.losses == 0
        assert result.win_rate == 0.0
        assert result.total_pnl == 0.0
        assert result.avg_win == 0.0
        assert result.avg_loss == 0.0
        assert result.risk_reward_ratio == 0.0
        assert result.best_trade_symbol == ""
        assert result.worst_trade_symbol == ""

    async def test_mixed_wins_and_losses(self, metrics, signal_repo, trade_repo):
        signal_id = await _insert_signal(signal_repo)

        await _insert_closed_trade(trade_repo, signal_id, "SBIN", pnl_amount=1000.0)
        await _insert_closed_trade(trade_repo, signal_id, "INFY", pnl_amount=500.0)
        await _insert_closed_trade(trade_repo, signal_id, "TCS", pnl_amount=200.0)
        await _insert_closed_trade(trade_repo, signal_id, "HDFC", pnl_amount=-300.0)
        await _insert_closed_trade(trade_repo, signal_id, "ICICI", pnl_amount=-600.0)

        result = await metrics.calculate_performance_metrics()

        assert result.trades_taken == 5
        assert result.wins == 3
        assert result.losses == 2
        assert result.win_rate == pytest.approx(60.0)
        assert result.total_pnl == pytest.approx(800.0)
        assert result.avg_win == pytest.approx(1700.0 / 3)
        assert result.avg_loss == pytest.approx(-900.0 / 2)
        assert result.risk_reward_ratio == pytest.approx(abs((1700.0 / 3) / (-900.0 / 2)))
        assert result.best_trade_symbol == "SBIN"
        assert result.best_trade_pnl == pytest.approx(1000.0)
        assert result.worst_trade_symbol == "ICICI"
        assert result.worst_trade_pnl == pytest.approx(-600.0)

    async def test_all_wins(self, metrics, signal_repo, trade_repo):
        signal_id = await _insert_signal(signal_repo)

        await _insert_closed_trade(trade_repo, signal_id, "SBIN", pnl_amount=1000.0)
        await _insert_closed_trade(trade_repo, signal_id, "INFY", pnl_amount=500.0)

        result = await metrics.calculate_performance_metrics()
        assert result.wins == 2
        assert result.losses == 0
        assert result.win_rate == pytest.approx(100.0)
        assert result.avg_loss == 0.0
        assert result.risk_reward_ratio == 0.0

    async def test_all_losses(self, metrics, signal_repo, trade_repo):
        signal_id = await _insert_signal(signal_repo)

        await _insert_closed_trade(trade_repo, signal_id, "SBIN", pnl_amount=-500.0)
        await _insert_closed_trade(trade_repo, signal_id, "INFY", pnl_amount=-300.0)

        result = await metrics.calculate_performance_metrics()
        assert result.wins == 0
        assert result.losses == 2
        assert result.win_rate == pytest.approx(0.0)
        assert result.avg_win == 0.0

    async def test_zero_pnl_counted_as_loss(self, metrics, signal_repo, trade_repo):
        signal_id = await _insert_signal(signal_repo)
        await _insert_closed_trade(trade_repo, signal_id, "SBIN", pnl_amount=0.0)

        result = await metrics.calculate_performance_metrics()
        assert result.wins == 0
        assert result.losses == 1

    async def test_daily_summary_basic(self, metrics, signal_repo, trade_repo):
        d = date(2026, 2, 16)
        signal_id = await _insert_signal(signal_repo, d=d)

        await _insert_closed_trade(trade_repo, signal_id, "SBIN", pnl_amount=500.0, d=d)
        await _insert_closed_trade(trade_repo, signal_id, "INFY", pnl_amount=-200.0, d=d)

        summary = await metrics.calculate_daily_summary(d)
        assert summary.date == d
        assert summary.signals_sent == 1
        assert summary.trades_taken == 2
        assert summary.wins == 1
        assert summary.losses == 1
        assert summary.total_pnl == pytest.approx(300.0)
        assert len(summary.trades) == 2

    async def test_daily_summary_no_trades(self, metrics):
        summary = await metrics.calculate_daily_summary(date(2026, 2, 16))
        assert summary.trades_taken == 0
        assert summary.wins == 0
        assert summary.losses == 0
        assert summary.total_pnl == 0.0
        assert summary.trades == []

    async def test_daily_summary_cumulative_pnl(self, metrics, signal_repo, trade_repo):
        d1 = date(2026, 2, 15)
        sid1 = await _insert_signal(signal_repo, d=d1)
        await _insert_closed_trade(trade_repo, sid1, "SBIN", pnl_amount=1000.0, d=d1)

        d2 = date(2026, 2, 16)
        sid2 = await _insert_signal(signal_repo, d=d2)
        await _insert_closed_trade(trade_repo, sid2, "INFY", pnl_amount=500.0, d=d2)

        summary = await metrics.calculate_daily_summary(d2)
        assert summary.total_pnl == pytest.approx(500.0)
        assert summary.cumulative_pnl == pytest.approx(1500.0)

    async def test_performance_metrics_with_date_range(self, metrics, signal_repo, trade_repo):
        d1 = date(2026, 2, 15)
        sid1 = await _insert_signal(signal_repo, d=d1)
        await _insert_closed_trade(trade_repo, sid1, "SBIN", pnl_amount=1000.0, d=d1)

        d2 = date(2026, 2, 16)
        sid2 = await _insert_signal(signal_repo, d=d2)
        await _insert_closed_trade(trade_repo, sid2, "INFY", pnl_amount=-500.0, d=d2)

        result = await metrics.calculate_performance_metrics(date_start=d2, date_end=d2)
        assert result.trades_taken == 1
        assert result.total_pnl == pytest.approx(-500.0)
        assert result.date_range_start == d2
        assert result.date_range_end == d2

    async def test_date_range_filters_best_worst_trade_symbols(self, metrics, signal_repo, trade_repo):
        """Best/worst trade symbols should respect the date range filter."""
        d1 = date(2026, 2, 15)
        sid1 = await _insert_signal(signal_repo, d=d1)
        await _insert_closed_trade(trade_repo, sid1, "SBIN", pnl_amount=5000.0, d=d1)

        d2 = date(2026, 2, 16)
        sid2 = await _insert_signal(signal_repo, d=d2)
        await _insert_closed_trade(trade_repo, sid2, "INFY", pnl_amount=200.0, d=d2)
        await _insert_closed_trade(trade_repo, sid2, "TCS", pnl_amount=-100.0, d=d2)

        # Filter to d2 only — should NOT include SBIN from d1
        result = await metrics.calculate_performance_metrics(date_start=d2, date_end=d2)
        assert result.best_trade_symbol == "INFY"
        assert result.best_trade_pnl == pytest.approx(200.0)
        assert result.worst_trade_symbol == "TCS"
        assert result.worst_trade_pnl == pytest.approx(-100.0)
