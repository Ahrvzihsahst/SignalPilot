"""Tests for the backtest runner and result dataclass."""

from datetime import date, datetime

from signalpilot.backtest.data_loader import BacktestCandle
from signalpilot.backtest.runner import BacktestResult, BacktestRunner, SimulatedTrade
from signalpilot.db.models import CandidateSignal, SignalDirection
from signalpilot.utils.constants import IST

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_candle(
    symbol: str,
    day: date,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: float = 100_000,
    hour: int = 9,
    minute: int = 30,
) -> BacktestCandle:
    return BacktestCandle(
        symbol=symbol,
        date=day,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        timestamp=datetime(day.year, day.month, day.day, hour, minute, tzinfo=IST),
    )


def _make_closed_trade(pnl: float, exit_price: float = 110.0) -> SimulatedTrade:
    """Helper to create a closed trade with the given P&L."""
    return SimulatedTrade(
        symbol="TEST",
        strategy="test",
        entry_price=100.0,
        stop_loss=95.0,
        target_1=110.0,
        target_2=120.0,
        entry_date=date(2025, 1, 15),
        exit_price=exit_price,
        exit_date=date(2025, 1, 15),
        exit_reason="t1_hit" if pnl > 0 else "sl_hit",
        pnl_amount=pnl,
        pnl_pct=(pnl / 100.0),
    )


# ---------------------------------------------------------------------------
# BacktestResult property tests
# ---------------------------------------------------------------------------


class TestBacktestResultProperties:
    """Tests for the computed properties on BacktestResult."""

    def test_wins_count(self):
        result = BacktestResult(
            strategy_name="test",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
            trades=[
                _make_closed_trade(pnl=500),
                _make_closed_trade(pnl=-100),
                _make_closed_trade(pnl=300),
            ],
        )
        assert result.wins == 2

    def test_losses_count(self):
        result = BacktestResult(
            strategy_name="test",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
            trades=[
                _make_closed_trade(pnl=500),
                _make_closed_trade(pnl=-100),
                _make_closed_trade(pnl=-200),
            ],
        )
        assert result.losses == 2

    def test_losses_excludes_open_trades(self):
        """Trades without exit_price are not counted as losses."""
        open_trade = SimulatedTrade(
            symbol="TEST",
            strategy="test",
            entry_price=100.0,
            stop_loss=95.0,
            target_1=110.0,
            target_2=120.0,
            entry_date=date(2025, 1, 15),
        )
        result = BacktestResult(
            strategy_name="test",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
            trades=[open_trade, _make_closed_trade(pnl=-100)],
        )
        assert result.losses == 1

    def test_win_rate(self):
        result = BacktestResult(
            strategy_name="test",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
            trades=[
                _make_closed_trade(pnl=500),
                _make_closed_trade(pnl=-100),
                _make_closed_trade(pnl=300),
                _make_closed_trade(pnl=-200),
            ],
        )
        assert result.win_rate == 50.0

    def test_win_rate_no_trades(self):
        result = BacktestResult(
            strategy_name="test",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        )
        assert result.win_rate == 0.0

    def test_total_pnl(self):
        result = BacktestResult(
            strategy_name="test",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
            trades=[
                _make_closed_trade(pnl=500),
                _make_closed_trade(pnl=-100),
                _make_closed_trade(pnl=300),
            ],
        )
        assert result.total_pnl == 700.0

    def test_avg_win(self):
        result = BacktestResult(
            strategy_name="test",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
            trades=[
                _make_closed_trade(pnl=600),
                _make_closed_trade(pnl=-100),
                _make_closed_trade(pnl=400),
            ],
        )
        assert result.avg_win == 500.0

    def test_avg_win_no_wins(self):
        result = BacktestResult(
            strategy_name="test",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
            trades=[_make_closed_trade(pnl=-100)],
        )
        assert result.avg_win == 0.0

    def test_avg_loss(self):
        result = BacktestResult(
            strategy_name="test",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
            trades=[
                _make_closed_trade(pnl=500),
                _make_closed_trade(pnl=-200),
                _make_closed_trade(pnl=-400),
            ],
        )
        assert result.avg_loss == -300.0

    def test_avg_loss_no_losses(self):
        result = BacktestResult(
            strategy_name="test",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
            trades=[_make_closed_trade(pnl=500)],
        )
        assert result.avg_loss == 0.0


# ---------------------------------------------------------------------------
# BacktestRunner tests
# ---------------------------------------------------------------------------


class TestBacktestRunner:
    """Tests for BacktestRunner.run with mock candle data."""

    def _always_signal(self, symbol, candles, current_candle):
        """Evaluate function that always produces a signal."""
        return CandidateSignal(
            symbol=symbol,
            direction=SignalDirection.BUY,
            strategy_name="test",
            entry_price=current_candle.open,
            stop_loss=current_candle.open * 0.97,
            target_1=current_candle.open * 1.03,
            target_2=current_candle.open * 1.05,
            gap_pct=3.0,
            volume_ratio=1.5,
        )

    def _never_signal(self, symbol, candles, current_candle):
        """Evaluate function that never produces a signal."""
        return None

    def test_produces_expected_signal_count(self):
        """Runner generates signals for each symbol with data."""
        day = date(2025, 1, 15)
        data = {
            "SBIN": [_make_candle("SBIN", day, 100, 105, 99, 103)],
            "TCS": [_make_candle("TCS", day, 200, 210, 198, 205)],
        }
        runner = BacktestRunner(max_positions=8)
        result = runner.run("test", data, self._always_signal, day, day)

        assert result.signals_generated == 2
        assert result.trades_taken == 2
        assert len(result.trades) == 2

    def test_no_signals_when_evaluate_returns_none(self):
        day = date(2025, 1, 15)
        data = {"SBIN": [_make_candle("SBIN", day, 100, 105, 99, 103)]}
        runner = BacktestRunner()
        result = runner.run("test", data, self._never_signal, day, day)

        assert result.signals_generated == 0
        assert result.trades_taken == 0

    def test_sl_exit_detected(self):
        """When candle low touches stop-loss, trade exits at SL same day."""
        day = date(2025, 1, 15)

        def signal_at_100(symbol, candles, current):
            return CandidateSignal(
                symbol=symbol,
                direction=SignalDirection.BUY,
                strategy_name="test",
                entry_price=100.0,
                stop_loss=95.0,
                target_1=110.0,
                target_2=120.0,
            )

        # Candle with low=94 triggers SL at 95 during intra-day exit check.
        data = {
            "SBIN": [_make_candle("SBIN", day, 100, 105, 94, 96)],
        }

        runner = BacktestRunner(max_positions=8)
        result = runner.run("test", data, signal_at_100, day, day)

        assert result.trades_taken == 1
        trade = result.trades[0]
        assert trade.exit_reason == "sl_hit"
        assert trade.exit_price == 95.0

    def test_t2_exit_detected(self):
        """When candle high reaches target_2, trade exits at T2 same day."""
        day = date(2025, 1, 15)

        def signal_at_100(symbol, candles, current):
            return CandidateSignal(
                symbol=symbol,
                direction=SignalDirection.BUY,
                strategy_name="test",
                entry_price=100.0,
                stop_loss=95.0,
                target_1=110.0,
                target_2=120.0,
            )

        # Candle with high=121 triggers T2 at 120 during intra-day exit check.
        data = {
            "SBIN": [_make_candle("SBIN", day, 100, 121, 99, 119)],
        }

        runner = BacktestRunner(max_positions=8)
        result = runner.run("test", data, signal_at_100, day, day)

        assert result.trades_taken == 1
        trade = result.trades[0]
        assert trade.exit_reason == "t2_hit"
        assert trade.exit_price == 120.0

    def test_eod_close(self):
        """Trades that do not hit SL or targets close at end of day."""
        day = date(2025, 1, 15)
        # high=104 stays below T2 (open*1.05=105), low=98 stays above SL (open*0.97=97)
        data = {
            "SBIN": [_make_candle("SBIN", day, 100, 104, 98, 103)],
        }
        runner = BacktestRunner(max_positions=8)
        result = runner.run("test", data, self._always_signal, day, day)

        trade = result.trades[0]
        assert trade.exit_reason == "eod_close"
        assert trade.exit_price == 103.0

    def test_position_limit_enforced(self):
        """Runner should not open more trades than max_positions."""
        day = date(2025, 1, 15)
        symbols = [f"SYM{i}" for i in range(10)]
        data = {
            sym: [_make_candle(sym, day, 100 + i, 110 + i, 99 + i, 105 + i)]
            for i, sym in enumerate(symbols)
        }

        runner = BacktestRunner(max_positions=3)
        result = runner.run("test", data, self._always_signal, day, day)

        # All 10 symbols produce signals, but only 3 should be taken.
        # Actually signals_generated will be 3 too because the loop
        # stops entering the symbol evaluation once max_positions is reached?
        # No -- the runner loop evaluates all symbols but only opens up to max.
        # Let's check signals_generated >= 3 (at least 3 symbols evaluated
        # before hitting the limit) and trades_taken == 3.
        assert result.trades_taken == 3
        assert result.signals_generated >= 3

    def test_multi_day_trading(self):
        """Runner processes multiple days independently."""
        day1 = date(2025, 1, 15)
        day2 = date(2025, 1, 16)
        # Keep high below T2 (open*1.05) and low above SL (open*0.97) for both days
        data = {
            "SBIN": [
                _make_candle("SBIN", day1, 100, 104, 98, 103),
                _make_candle("SBIN", day2, 104, 108, 102, 106),
            ],
        }
        runner = BacktestRunner(max_positions=8)
        result = runner.run("test", data, self._always_signal, day1, day2)

        # Day 1: signal -> eod close. Day 2: signal -> eod close.
        assert result.trades_taken == 2
        assert result.signals_generated == 2
        assert all(t.exit_reason == "eod_close" for t in result.trades)

    def test_pnl_calculation(self):
        """P&L is calculated as (exit - entry) * 100 (fixed qty)."""
        day = date(2025, 1, 15)
        # high=104 < T2 (100*1.05=105), low=98 > SL (100*0.97=97) -> EOD close
        data = {
            "SBIN": [_make_candle("SBIN", day, 100, 104, 98, 103)],
        }
        runner = BacktestRunner(max_positions=8)
        result = runner.run("test", data, self._always_signal, day, day)

        trade = result.trades[0]
        # entry = open = 100, exit = close = 103, qty = 100
        assert trade.pnl_amount == (103.0 - 100.0) * 100
        assert trade.pnl_pct == ((103.0 - 100.0) / 100.0) * 100

    def test_date_range_filtering(self):
        """Only candles within start_date..end_date are processed."""
        day1 = date(2025, 1, 14)  # Before range
        day2 = date(2025, 1, 15)  # In range
        day3 = date(2025, 1, 16)  # After range
        data = {
            "SBIN": [
                _make_candle("SBIN", day1, 100, 105, 99, 103),
                _make_candle("SBIN", day2, 104, 108, 102, 106),
                _make_candle("SBIN", day3, 107, 112, 105, 110),
            ],
        }
        runner = BacktestRunner(max_positions=8)
        result = runner.run("test", data, self._always_signal, day2, day2)

        assert result.trades_taken == 1
        assert result.trades[0].entry_date == day2

    def test_empty_data(self):
        """Runner handles empty data gracefully."""
        runner = BacktestRunner()
        result = runner.run(
            "test", {}, self._always_signal, date(2025, 1, 1), date(2025, 1, 31)
        )
        assert result.signals_generated == 0
        assert result.trades_taken == 0
        assert result.total_pnl == 0.0
