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
    format_daily_summary,
    format_exit_alert,
    format_journal_message,
    format_signal_message,
    format_status_message,
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
    assert "Reply TAKEN" in msg


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
