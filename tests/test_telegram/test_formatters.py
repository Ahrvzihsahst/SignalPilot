"""Tests for Telegram message formatters."""

from datetime import date, datetime

import pytest

from signalpilot.db.models import (
    CandidateSignal,
    DailySummary,
    ExitAlert,
    ExitType,
    FinalSignal,
    PerformanceMetrics,
    RankedSignal,
    SignalDirection,
    SignalRecord,
    TradeRecord,
)
from signalpilot.telegram.formatters import (
    format_allocation_summary,
    format_daily_summary,
    format_exit_alert,
    format_journal_message,
    format_signal_message,
    format_status_message,
    format_strategy_report,
    star_rating,
)
from signalpilot.utils.constants import IST


def _make_final_signal(
    symbol: str = "SBIN",
    entry_price: float = 645.0,
    stop_loss: float = 625.65,
    target_1: float = 677.25,
    target_2: float = 690.15,
    quantity: int = 15,
    capital_required: float = 9675.0,
    signal_strength: int = 4,
    strategy_name: str = "Gap & Go",
    reason: str = "Gap up 4.2%, volume 2.1x ADV",
) -> FinalSignal:
    candidate = CandidateSignal(
        symbol=symbol,
        direction=SignalDirection.BUY,
        strategy_name=strategy_name,
        entry_price=entry_price,
        stop_loss=stop_loss,
        target_1=target_1,
        target_2=target_2,
        gap_pct=4.2,
        volume_ratio=2.1,
        price_distance_from_open_pct=1.5,
        reason=reason,
        generated_at=datetime(2025, 1, 6, 9, 35, 0, tzinfo=IST),
    )
    ranked = RankedSignal(
        candidate=candidate,
        composite_score=0.75,
        rank=1,
        signal_strength=signal_strength,
    )
    return FinalSignal(
        ranked_signal=ranked,
        quantity=quantity,
        capital_required=capital_required,
        expires_at=datetime(2025, 1, 6, 10, 5, 0, tzinfo=IST),
    )


def _make_trade(
    trade_id: int = 1,
    symbol: str = "SBIN",
    entry_price: float = 645.0,
    stop_loss: float = 625.65,
    quantity: int = 15,
) -> TradeRecord:
    return TradeRecord(
        id=trade_id,
        signal_id=1,
        symbol=symbol,
        entry_price=entry_price,
        stop_loss=stop_loss,
        target_1=677.25,
        target_2=690.15,
        quantity=quantity,
        taken_at=datetime(2025, 1, 6, 9, 36, 0, tzinfo=IST),
    )


# ── star_rating ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "strength, label",
    [
        (1, "Weak"),
        (2, "Fair"),
        (3, "Moderate"),
        (4, "Strong"),
        (5, "Very Strong"),
    ],
)
def test_star_rating_labels(strength: int, label: str) -> None:
    result = star_rating(strength)
    assert label in result


@pytest.mark.parametrize("strength", [1, 2, 3, 4, 5])
def test_star_rating_length(strength: int) -> None:
    """Star display has exactly 5 star/empty characters before the label."""
    result = star_rating(strength)
    # Stars are emojis, so check the count in the parenthesized label section
    assert f"({['Weak', 'Fair', 'Moderate', 'Strong', 'Very Strong'][strength - 1]})" in result


# ── format_signal_message ──────────────────────────────────────


def test_signal_message_contains_all_fields() -> None:
    signal = _make_final_signal()
    msg = format_signal_message(signal)

    assert "BUY SIGNAL" in msg  # direction.value from CandidateSignal
    assert "SBIN" in msg
    assert "645" in msg
    assert "625.65" in msg
    assert "677.25" in msg
    assert "690.15" in msg
    assert "15 shares" in msg
    assert "9,675" in msg
    assert "Strong" in msg  # 4-star label
    assert "Gap & Go" in msg
    assert "Gap up 4.2%" in msg
    assert "10:05 AM" in msg  # expires_at
    assert "Tap a button below" in msg


def test_signal_message_with_signal_id() -> None:
    """format_signal_message with signal_id shows ID line and TAKEN <id> footer."""
    signal = _make_final_signal()
    msg = format_signal_message(signal, signal_id=42)
    assert "Signal ID: #42" in msg
    assert "Tap a button below or reply TAKEN 42" in msg


def test_signal_message_without_signal_id() -> None:
    """format_signal_message without signal_id keeps generic TAKEN footer."""
    signal = _make_final_signal()
    msg = format_signal_message(signal)
    assert "Signal ID:" not in msg
    assert "Tap a button below or reply TAKEN" in msg


def test_signal_message_risk_pct() -> None:
    """Risk percentage should be computed from entry and stop loss."""
    signal = _make_final_signal(entry_price=100.0, stop_loss=97.0)
    msg = format_signal_message(signal)
    assert "3.0% risk" in msg


# ── format_exit_alert ──────────────────────────────────────────


def test_exit_alert_sl_hit() -> None:
    alert = ExitAlert(
        trade=_make_trade(), exit_type=ExitType.SL_HIT,
        current_price=625.65, pnl_pct=-3.0, is_alert_only=False,
    )
    msg = format_exit_alert(alert)
    assert "STOP LOSS HIT" in msg
    assert "SBIN" in msg
    assert "625.65" in msg
    assert "Exit immediately" in msg
    assert "-3.0%" in msg


def test_exit_alert_t1_hit() -> None:
    alert = ExitAlert(
        trade=_make_trade(), exit_type=ExitType.T1_HIT,
        current_price=677.25, pnl_pct=5.0, is_alert_only=True,
    )
    msg = format_exit_alert(alert)
    assert "TARGET 1 HIT" in msg
    assert "partial profit" in msg
    assert "+5.0%" in msg


def test_exit_alert_t2_hit() -> None:
    alert = ExitAlert(
        trade=_make_trade(), exit_type=ExitType.T2_HIT,
        current_price=690.15, pnl_pct=7.0, is_alert_only=False,
    )
    msg = format_exit_alert(alert)
    assert "TARGET 2 HIT" in msg
    assert "Full exit" in msg
    assert "+7.0%" in msg


def test_exit_alert_trailing_sl_hit() -> None:
    alert = ExitAlert(
        trade=_make_trade(), exit_type=ExitType.TRAILING_SL_HIT,
        current_price=660.0, pnl_pct=2.3, is_alert_only=False,
    )
    msg = format_exit_alert(alert)
    assert "TRAILING SL HIT" in msg
    assert "Exit immediately" in msg


def test_exit_alert_trailing_sl_update() -> None:
    alert = ExitAlert(
        trade=_make_trade(), exit_type=None,
        current_price=670.0, pnl_pct=3.9, is_alert_only=True,
        trailing_sl_update=656.60,
    )
    msg = format_exit_alert(alert)
    assert "TRAILING SL UPDATE" in msg
    assert "656.60" in msg


def test_exit_alert_time_exit_advisory() -> None:
    alert = ExitAlert(
        trade=_make_trade(), exit_type=ExitType.TIME_EXIT,
        current_price=650.0, pnl_pct=0.8, is_alert_only=True,
    )
    msg = format_exit_alert(alert)
    assert "TIME EXIT REMINDER" in msg
    assert "Consider closing" in msg


def test_exit_alert_time_exit_mandatory() -> None:
    alert = ExitAlert(
        trade=_make_trade(), exit_type=ExitType.TIME_EXIT,
        current_price=650.0, pnl_pct=0.8, is_alert_only=False,
    )
    msg = format_exit_alert(alert)
    assert "MANDATORY EXIT" in msg
    assert "market closing" in msg


# ── format_status_message ──────────────────────────────────────


def test_status_message_empty() -> None:
    msg = format_status_message([], [], {})
    assert msg == "No active signals or open trades."


def test_status_message_with_signals() -> None:
    signal = SignalRecord(
        symbol="SBIN", entry_price=645.0, stop_loss=625.65,
        target_1=677.25, target_2=690.15,
    )
    msg = format_status_message([signal], [], {})
    assert "Active Signals" in msg
    assert "SBIN" in msg
    assert "645" in msg


def test_status_message_with_trades_and_prices() -> None:
    trade = _make_trade(entry_price=100.0, quantity=10)
    msg = format_status_message([], [trade], {"SBIN": 105.0})
    assert "Open Trades" in msg
    assert "SBIN" in msg
    assert "+5.0%" in msg
    assert "+50" in msg  # pnl_amount = (105-100)*10 = 50


def test_status_message_trade_no_price() -> None:
    trade = _make_trade()
    msg = format_status_message([], [trade], {})
    assert "no live price" in msg


# ── format_journal_message ─────────────────────────────────────


def test_journal_message_empty() -> None:
    msg = format_journal_message(None)
    assert "No trades logged yet" in msg
    assert "TAKEN" in msg


def test_journal_message_with_metrics() -> None:
    metrics = PerformanceMetrics(
        date_range_start=date(2025, 1, 1),
        date_range_end=date(2025, 1, 6),
        total_signals=20,
        trades_taken=15,
        wins=10,
        losses=5,
        win_rate=66.7,
        total_pnl=5000.0,
        avg_win=800.0,
        avg_loss=-300.0,
        risk_reward_ratio=2.67,
        best_trade_symbol="RELIANCE",
        best_trade_pnl=2000.0,
        worst_trade_symbol="TCS",
        worst_trade_pnl=-500.0,
    )
    msg = format_journal_message(metrics)
    assert "Trade Journal" in msg
    assert "66.7%" in msg
    assert "+5,000" in msg
    assert "RELIANCE" in msg
    assert "TCS" in msg
    assert "2.67" in msg


# ── format_daily_summary ──────────────────────────────────────


def test_daily_summary_no_signals() -> None:
    summary = DailySummary(
        date=date(2025, 1, 6),
        signals_sent=0,
        trades_taken=0,
        wins=0,
        losses=0,
        total_pnl=0.0,
        cumulative_pnl=0.0,
    )
    msg = format_daily_summary(summary)
    assert "No signals generated today" in msg


def test_daily_summary_with_trades() -> None:
    trade = _make_trade()
    trade.exit_reason = "t1_hit"
    trade.pnl_amount = 500.0
    summary = DailySummary(
        date=date(2025, 1, 6),
        signals_sent=5,
        trades_taken=3,
        wins=2,
        losses=1,
        total_pnl=1200.0,
        cumulative_pnl=5000.0,
        trades=[trade],
    )
    msg = format_daily_summary(summary)
    assert "Daily Summary" in msg
    assert "Signals Generated: 5" in msg
    assert "Trades Taken: 3" in msg
    assert "+1,200" in msg
    assert "+5,000" in msg
    assert "SBIN" in msg
    assert "t1_hit" in msg


# =========================================================================
# Phase 2: format_signal_message — strategy variants
# =========================================================================


def test_signal_message_orb_strategy() -> None:
    """format_signal_message with ORB strategy shows 'ORB' in Strategy field."""
    signal = _make_final_signal(strategy_name="ORB")
    msg = format_signal_message(signal)
    assert "Strategy: ORB" in msg


def test_signal_message_vwap_reversal_with_setup_type() -> None:
    """VWAP Reversal + setup_type shows 'VWAP Reversal (Uptrend Pullback)'."""
    signal = _make_final_signal(strategy_name="VWAP Reversal")
    signal.ranked_signal.candidate.setup_type = "uptrend_pullback"
    msg = format_signal_message(signal)
    assert "Strategy: VWAP Reversal (Uptrend Pullback)" in msg


def test_signal_message_vwap_reclaim_shows_higher_risk() -> None:
    """VWAP Reversal with setup_type='vwap_reclaim' shows 'Higher Risk' warning."""
    signal = _make_final_signal(strategy_name="VWAP Reversal")
    signal.ranked_signal.candidate.setup_type = "vwap_reclaim"
    msg = format_signal_message(signal)
    assert "Higher Risk" in msg


def test_signal_message_paper_trade_prefix() -> None:
    """format_signal_message with is_paper=True shows 'PAPER TRADE' prefix."""
    signal = _make_final_signal()
    msg = format_signal_message(signal, is_paper=True)
    assert "PAPER TRADE" in msg
    # Prefix should appear before the signal header
    paper_idx = msg.index("PAPER TRADE")
    signal_idx = msg.index("SIGNAL")
    assert paper_idx < signal_idx


def test_signal_message_positions_format() -> None:
    """format_signal_message shows 'Positions open: 3/8' format."""
    signal = _make_final_signal()
    msg = format_signal_message(signal, active_count=3, max_positions=8)
    assert "Positions open: 3/8" in msg


# =========================================================================
# Phase 2: format_daily_summary — strategy breakdown
# =========================================================================


def test_daily_summary_with_strategy_breakdown() -> None:
    """format_daily_summary with strategy_breakdown shows BY STRATEGY section."""
    from signalpilot.db.models import StrategyDaySummary

    summary = DailySummary(
        date=date(2025, 1, 6),
        signals_sent=10,
        trades_taken=6,
        wins=4,
        losses=2,
        total_pnl=2500.0,
        cumulative_pnl=8000.0,
        strategy_breakdown={
            "Gap & Go": StrategyDaySummary(
                strategy_name="Gap & Go",
                signals_generated=4,
                signals_taken=3,
                pnl=1500.0,
            ),
            "ORB": StrategyDaySummary(
                strategy_name="ORB",
                signals_generated=3,
                signals_taken=2,
                pnl=800.0,
            ),
            "VWAP Reversal": StrategyDaySummary(
                strategy_name="VWAP Reversal",
                signals_generated=3,
                signals_taken=1,
                pnl=200.0,
            ),
        },
    )
    msg = format_daily_summary(summary)
    assert "BY STRATEGY" in msg
    assert "Gap & Go" in msg
    assert "ORB" in msg
    assert "VWAP Reversal" in msg
    assert "4 signals" in msg
    assert "+1,500" in msg
    assert "+800" in msg


# =========================================================================
# Phase 2: format_strategy_report
# =========================================================================


def test_format_strategy_report_with_records() -> None:
    """format_strategy_report with records returns formatted report."""
    from signalpilot.db.models import StrategyPerformanceRecord

    records = [
        StrategyPerformanceRecord(
            strategy="Gap & Go",
            date="2025-01-06",
            signals_generated=5,
            signals_taken=3,
            wins=2,
            losses=1,
            total_pnl=1500.0,
            win_rate=66.7,
            avg_win=900.0,
            avg_loss=-300.0,
            capital_weight_pct=40.0,
        ),
        StrategyPerformanceRecord(
            strategy="ORB",
            date="2025-01-06",
            signals_generated=3,
            signals_taken=2,
            wins=1,
            losses=1,
            total_pnl=200.0,
            win_rate=50.0,
            avg_win=500.0,
            avg_loss=-300.0,
            capital_weight_pct=20.0,
        ),
    ]
    msg = format_strategy_report(records)
    assert "Strategy Performance (30-day)" in msg
    assert "Gap & Go" in msg
    assert "ORB" in msg
    assert "Win Rate" in msg
    assert "Net P&L" in msg
    assert "Allocation: 40%" in msg
    assert "Allocation: 20%" in msg


def test_format_strategy_report_empty_records() -> None:
    """format_strategy_report with empty records returns 'No data' message."""
    msg = format_strategy_report([])
    assert "No strategy performance data available" in msg


def test_format_strategy_report_none_records() -> None:
    """format_strategy_report with None returns 'No data' message."""
    msg = format_strategy_report(None)
    assert "No strategy performance data available" in msg


# =========================================================================
# Phase 2: format_allocation_summary
# =========================================================================


def test_format_allocation_summary() -> None:
    """format_allocation_summary formats correctly with all strategies."""
    from dataclasses import dataclass as _dc

    @_dc
    class AllocResult:
        strategy_name: str
        weight_pct: float
        allocated_capital: float
        max_positions: int

    allocations = {
        "Gap & Go": AllocResult(
            strategy_name="Gap & Go",
            weight_pct=40.0,
            allocated_capital=40_000.0,
            max_positions=3,
        ),
        "ORB": AllocResult(
            strategy_name="ORB",
            weight_pct=20.0,
            allocated_capital=20_000.0,
            max_positions=2,
        ),
        "VWAP Reversal": AllocResult(
            strategy_name="VWAP Reversal",
            weight_pct=20.0,
            allocated_capital=20_000.0,
            max_positions=2,
        ),
    }
    msg = format_allocation_summary(allocations)
    assert "Weekly Capital Rebalancing" in msg
    assert "Gap & Go: 40%" in msg
    assert "ORB: 20%" in msg
    assert "VWAP Reversal: 20%" in msg
    assert "40,000" in msg
    assert "Reserve: 20%" in msg
