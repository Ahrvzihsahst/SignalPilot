"""Telegram message formatters for signals, alerts, and summaries."""

from signalpilot.db.models import (
    DailySummary,
    ExitAlert,
    ExitType,
    FinalSignal,
    PerformanceMetrics,
    SignalRecord,
    TradeRecord,
)

_STAR_LABELS = {1: "Weak", 2: "Fair", 3: "Moderate", 4: "Strong", 5: "Very Strong"}


def star_rating(strength: int) -> str:
    """Convert 1-5 strength to star display with label.

    Example: 4 -> "****. (Strong)"
    """
    strength = max(1, min(5, strength))
    filled = "\u2b50" * strength
    empty = "\u2606" * (5 - strength)
    label = _STAR_LABELS.get(strength, "")
    return f"{filled}{empty} ({label})"


def format_signal_message(signal: FinalSignal) -> str:
    """Format a FinalSignal into the user-facing Telegram message (HTML)."""
    c = signal.ranked_signal.candidate
    risk_pct = abs((c.stop_loss - c.entry_price) / c.entry_price * 100)
    t1_pct = abs((c.target_1 - c.entry_price) / c.entry_price * 100)
    t2_pct = abs((c.target_2 - c.entry_price) / c.entry_price * 100)
    stars = star_rating(signal.ranked_signal.signal_strength)

    direction = c.direction.value
    return (
        f"<b>{direction} SIGNAL -- {c.symbol}</b>\n"
        f"\n"
        f"Entry Price: {c.entry_price:,.2f}\n"
        f"Stop Loss: {c.stop_loss:,.2f} ({risk_pct:.1f}% risk)\n"
        f"Target 1: {c.target_1:,.2f} ({t1_pct:.1f}%)\n"
        f"Target 2: {c.target_2:,.2f} ({t2_pct:.1f}%)\n"
        f"Quantity: {signal.quantity} shares\n"
        f"Capital Required: {signal.capital_required:,.0f}\n"
        f"Signal Strength: {stars}\n"
        f"Strategy: {c.strategy_name}\n"
        f"Reason: {c.reason}\n"
        f"\n"
        f"Valid Until: {signal.expires_at.strftime('%I:%M %p')} (auto-expires)\n"
        f"{'=' * 30}\n"
        f"Reply TAKEN to log this trade"
    )


def format_exit_alert(alert: ExitAlert) -> str:
    """Format an ExitAlert into a Telegram message (HTML)."""
    trade = alert.trade
    pnl_sign = "+" if alert.pnl_pct >= 0 else ""

    if alert.trailing_sl_update is not None and alert.exit_type is None:
        return (
            f"<b>TRAILING SL UPDATE -- {trade.symbol}</b>\n"
            f"Trailing SL updated to {alert.trailing_sl_update:,.2f}\n"
            f"Current Price: {alert.current_price:,.2f} ({pnl_sign}{alert.pnl_pct:.1f}%)"
        )

    if alert.exit_type == ExitType.SL_HIT:
        return (
            f"<b>STOP LOSS HIT -- {trade.symbol}</b>\n"
            f"Stop Loss hit at {alert.current_price:,.2f}. Exit immediately.\n"
            f"P&L: {pnl_sign}{alert.pnl_pct:.1f}%"
        )

    if alert.exit_type == ExitType.TRAILING_SL_HIT:
        return (
            f"<b>TRAILING SL HIT -- {trade.symbol}</b>\n"
            f"Trailing Stop Loss hit at {alert.current_price:,.2f}. Exit immediately.\n"
            f"P&L: {pnl_sign}{alert.pnl_pct:.1f}%"
        )

    if alert.exit_type == ExitType.T1_HIT:
        return (
            f"<b>TARGET 1 HIT -- {trade.symbol}</b>\n"
            f"Target 1 hit at {alert.current_price:,.2f}! "
            f"Consider booking partial profit.\n"
            f"P&L: {pnl_sign}{alert.pnl_pct:.1f}%"
        )

    if alert.exit_type == ExitType.T2_HIT:
        return (
            f"<b>TARGET 2 HIT -- {trade.symbol}</b>\n"
            f"Target 2 hit at {alert.current_price:,.2f}! "
            f"Full exit recommended.\n"
            f"P&L: {pnl_sign}{alert.pnl_pct:.1f}%"
        )

    if alert.exit_type == ExitType.TIME_EXIT:
        if alert.is_alert_only:
            return (
                f"<b>TIME EXIT REMINDER -- {trade.symbol}</b>\n"
                f"Market closing soon. Current Price: {alert.current_price:,.2f}\n"
                f"Unrealized P&L: {pnl_sign}{alert.pnl_pct:.1f}%\n"
                f"Consider closing this position."
            )
        return (
            f"<b>MANDATORY EXIT -- {trade.symbol}</b>\n"
            f"Position closed at {alert.current_price:,.2f} (market closing).\n"
            f"P&L: {pnl_sign}{alert.pnl_pct:.1f}%"
        )

    return f"Alert for {trade.symbol}: price {alert.current_price:,.2f}"


def format_status_message(
    signals: list[SignalRecord],
    trades: list[TradeRecord],
    current_prices: dict[str, float],
) -> str:
    """Format the STATUS command response."""
    if not signals and not trades:
        return "No active signals or open trades."

    parts: list[str] = []

    if signals:
        parts.append("<b>Active Signals</b>")
        for s in signals:
            parts.append(
                f"  {s.symbol}: Entry {s.entry_price:,.2f}, "
                f"SL {s.stop_loss:,.2f}, "
                f"T1 {s.target_1:,.2f}, T2 {s.target_2:,.2f}"
            )

    if trades:
        parts.append("")
        parts.append("<b>Open Trades</b>")
        for t in trades:
            price = current_prices.get(t.symbol)
            if price is not None:
                pnl_pct = ((price - t.entry_price) / t.entry_price) * 100
                pnl_amount = (price - t.entry_price) * t.quantity
                sign = "+" if pnl_pct >= 0 else ""
                parts.append(
                    f"  {t.symbol}: Entry {t.entry_price:,.2f}, "
                    f"LTP {price:,.2f}, "
                    f"P&L {sign}{pnl_amount:,.0f} ({sign}{pnl_pct:.1f}%), "
                    f"SL {t.stop_loss:,.2f}"
                )
            else:
                parts.append(
                    f"  {t.symbol}: Entry {t.entry_price:,.2f}, "
                    f"SL {t.stop_loss:,.2f} (no live price)"
                )

    return "\n".join(parts)


def format_journal_message(metrics: PerformanceMetrics | None) -> str:
    """Format the JOURNAL command response."""
    if metrics is None:
        return "No trades logged yet. Reply TAKEN to a signal to start tracking."

    return (
        f"<b>Trade Journal</b>\n"
        f"Period: {metrics.date_range_start} to {metrics.date_range_end}\n"
        f"\n"
        f"Signals Sent: {metrics.total_signals}\n"
        f"Trades Taken: {metrics.trades_taken}\n"
        f"Win Rate: {metrics.win_rate:.1f}%\n"
        f"Total P&L: {metrics.total_pnl:+,.0f}\n"
        f"Avg Win: {metrics.avg_win:+,.0f}\n"
        f"Avg Loss: {metrics.avg_loss:+,.0f}\n"
        f"Risk-Reward: {metrics.risk_reward_ratio:.2f}\n"
        f"\n"
        f"Best Trade: {metrics.best_trade_symbol} ({metrics.best_trade_pnl:+,.0f})\n"
        f"Worst Trade: {metrics.worst_trade_symbol} ({metrics.worst_trade_pnl:+,.0f})"
    )


def format_daily_summary(summary: DailySummary) -> str:
    """Format the 3:30 PM daily summary."""
    if summary.signals_sent == 0:
        return f"<b>Daily Summary -- {summary.date}</b>\nNo signals generated today."

    parts = [
        f"<b>Daily Summary -- {summary.date}</b>",
        f"",
        f"Signals Generated: {summary.signals_sent}",
        f"Trades Taken: {summary.trades_taken}",
        f"Wins: {summary.wins} | Losses: {summary.losses}",
        f"Today's P&L: {summary.total_pnl:+,.0f}",
        f"Cumulative P&L: {summary.cumulative_pnl:+,.0f}",
    ]

    if summary.trades:
        parts.append("")
        parts.append("<b>Trade Details</b>")
        for t in summary.trades:
            outcome = t.exit_reason or "open"
            pnl_str = f"{t.pnl_amount:+,.0f}" if t.pnl_amount is not None else "n/a"
            parts.append(f"  {t.symbol}: {outcome} | P&L: {pnl_str}")

    return "\n".join(parts)
