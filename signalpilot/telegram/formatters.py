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


def _confirmation_badge(confirmation_level: str | None, confirmed_by: str | None = None) -> str:
    """Build a confirmation badge string for confirmed signals.

    Returns an empty string for single/None confirmation.
    """
    if not confirmation_level or confirmation_level == "single":
        return ""

    if confirmation_level == "triple":
        badge = "TRIPLE CONFIRMED"
        multiplier = "2.0x"
    elif confirmation_level == "double":
        badge = "DOUBLE CONFIRMED"
        multiplier = "1.5x"
    else:
        return ""

    lines = [f"<b>[{badge}]</b>"]
    if confirmed_by:
        lines.append(f"Confirmed by: {confirmed_by}")
    lines.append(f"Position size: {multiplier}")
    return "\n".join(lines)


def format_signal_message(
    signal: FinalSignal,
    active_count: int = 0,
    max_positions: int = 8,
    is_paper: bool = False,
    signal_id: int | None = None,
    confirmation_level: str | None = None,
    confirmed_by: str | None = None,
    boosted_stars: int | None = None,
) -> str:
    """Format a FinalSignal into the user-facing Telegram message (HTML).

    When ``confirmation_level`` is "double" or "triple", a badge is prepended
    showing the confirmation details, strategy list, and position multiplier.
    ``boosted_stars`` overrides the default star rating when provided.
    """
    c = signal.ranked_signal.candidate
    risk_pct = abs((c.stop_loss - c.entry_price) / c.entry_price * 100)
    t1_pct = abs((c.target_1 - c.entry_price) / c.entry_price * 100)
    t2_pct = abs((c.target_2 - c.entry_price) / c.entry_price * 100)

    # Use boosted stars if provided, else default
    effective_strength = boosted_stars if boosted_stars is not None else signal.ranked_signal.signal_strength
    stars = star_rating(effective_strength)

    direction = c.direction.value

    # Strategy display with setup type
    strategy_display = c.strategy_name
    if c.setup_type:
        setup_label = c.setup_type.replace("_", " ").title()
        strategy_display = f"{c.strategy_name} ({setup_label})"

    # Build prefix/warnings
    prefix = ""
    if is_paper:
        prefix = "<b>PAPER TRADE</b>\n"

    # Confirmation badge
    badge = _confirmation_badge(confirmation_level, confirmed_by)
    if badge:
        prefix = prefix + badge + "\n"

    warnings = ""
    if c.setup_type == "vwap_reclaim":
        warnings = "\n\u26a0\ufe0f Higher Risk setup"

    # Signal ID line (only when DB id is available)
    id_line = f"Signal ID: #{signal_id}\n" if signal_id is not None else ""

    # Footer: include signal ID in TAKEN hint when available
    if signal_id is not None:
        taken_hint = f"Reply TAKEN {signal_id} to log this trade"
    else:
        taken_hint = "Reply TAKEN to log this trade"

    return (
        f"{prefix}"
        f"<b>{direction} SIGNAL -- {c.symbol}</b>\n"
        f"\n"
        f"Entry Price: {c.entry_price:,.2f}\n"
        f"Stop Loss: {c.stop_loss:,.2f} ({risk_pct:.1f}% risk)\n"
        f"Target 1: {c.target_1:,.2f} ({t1_pct:.1f}%)\n"
        f"Target 2: {c.target_2:,.2f} ({t2_pct:.1f}%)\n"
        f"Quantity: {signal.quantity} shares\n"
        f"Capital Required: {signal.capital_required:,.0f}\n"
        f"Signal Strength: {stars}\n"
        f"Strategy: {strategy_display}\n"
        f"Positions open: {active_count}/{max_positions}\n"
        f"{id_line}"
        f"Reason: {c.reason}{warnings}\n"
        f"\n"
        f"Valid Until: {signal.expires_at.strftime('%I:%M %p')} (auto-expires)\n"
        f"{'=' * 30}\n"
        f"{taken_hint}"
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
    score_map: dict[str, float] | None = None,
    confirmation_map: dict[str, str] | None = None,
) -> str:
    """Format the STATUS command response.

    When ``score_map`` is provided, signals are sorted by composite score
    descending and rank numbers are shown. Confirmation badges are added
    for symbols in ``confirmation_map``.
    """
    if not signals and not trades:
        return "No active signals or open trades."

    parts: list[str] = []

    if signals:
        parts.append("<b>Active Signals</b>")

        # Sort by composite score if available
        if score_map:
            signals = sorted(
                signals,
                key=lambda s: score_map.get(s.symbol, 0.0),
                reverse=True,
            )

        for i, s in enumerate(signals):
            rank_prefix = f"#{i + 1} " if score_map else ""
            score_suffix = ""
            if score_map and s.symbol in score_map:
                score_suffix = f" [Score: {score_map[s.symbol]:.0f}]"

            badge = ""
            if confirmation_map and s.symbol in confirmation_map:
                level = confirmation_map[s.symbol]
                badge = f" [{level.upper()} CONFIRMED]"

            parts.append(
                f"  {rank_prefix}{s.symbol}{badge}: Entry {s.entry_price:,.2f}, "
                f"SL {s.stop_loss:,.2f}, "
                f"T1 {s.target_1:,.2f}, T2 {s.target_2:,.2f}{score_suffix}"
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


def format_journal_message(
    metrics: PerformanceMetrics | None,
    confirmed_count: int = 0,
) -> str:
    """Format the JOURNAL command response.

    When ``confirmed_count`` > 0, appends a confirmed signals section.
    """
    if metrics is None:
        return "No trades logged yet. Reply TAKEN to a signal to start tracking."

    parts = [
        "<b>Trade Journal</b>",
        f"Period: {metrics.date_range_start} to {metrics.date_range_end}",
        "",
        f"Signals Sent: {metrics.total_signals}",
        f"Trades Taken: {metrics.trades_taken}",
        f"Win Rate: {metrics.win_rate:.1f}%",
        f"Total P&L: {metrics.total_pnl:+,.0f}",
        f"Avg Win: {metrics.avg_win:+,.0f}",
        f"Avg Loss: {metrics.avg_loss:+,.0f}",
        f"Risk-Reward: {metrics.risk_reward_ratio:.2f}",
        "",
        f"Best Trade: {metrics.best_trade_symbol} ({metrics.best_trade_pnl:+,.0f})",
        f"Worst Trade: {metrics.worst_trade_symbol} ({metrics.worst_trade_pnl:+,.0f})",
    ]

    if confirmed_count > 0:
        parts.append("")
        parts.append(f"<b>Confirmed Signals Today: {confirmed_count}</b>")

    return "\n".join(parts)


def format_daily_summary(summary: DailySummary) -> str:
    """Format the 3:30 PM daily summary."""
    if summary.signals_sent == 0:
        return f"<b>Daily Summary -- {summary.date}</b>\nNo signals generated today."

    parts = [
        f"<b>Daily Summary -- {summary.date}</b>",
        "",
        f"Signals Generated: {summary.signals_sent}",
        f"Trades Taken: {summary.trades_taken}",
        f"Wins: {summary.wins} | Losses: {summary.losses}",
        f"Today's P&L: {summary.total_pnl:+,.0f}",
        f"Cumulative P&L: {summary.cumulative_pnl:+,.0f}",
    ]

    # Per-strategy breakdown
    if summary.strategy_breakdown:
        parts.append("")
        parts.append("<b>BY STRATEGY</b>")
        strategy_icons = {"Gap & Go": "\U0001f4c8", "ORB": "\U0001f4ca", "VWAP Reversal": "\U0001f4c9"}
        for name, breakdown in summary.strategy_breakdown.items():
            icon = strategy_icons.get(name, "\U0001f4cb")
            parts.append(
                f"  {icon} {name}: "
                f"{breakdown.signals_generated} signals, "
                f"{breakdown.signals_taken} taken, "
                f"P&L {breakdown.pnl:+,.0f}"
            )

    if summary.trades:
        parts.append("")
        parts.append("<b>Trade Details</b>")
        for t in summary.trades:
            outcome = t.exit_reason or "open"
            pnl_str = f"{t.pnl_amount:+,.0f}" if t.pnl_amount is not None else "n/a"
            parts.append(f"  {t.symbol}: {outcome} | P&L: {pnl_str}")

    return "\n".join(parts)


def format_strategy_report(records) -> str:
    """Format STRATEGY command output showing per-strategy performance."""
    if not records:
        return "No strategy performance data available yet."

    # Group by strategy
    by_strategy: dict[str, list] = {}
    for r in records:
        by_strategy.setdefault(r.strategy, []).append(r)

    parts = ["<b>Strategy Performance (30-day)</b>"]
    for strategy, recs in by_strategy.items():
        total_taken = sum(r.signals_taken for r in recs)
        total_wins = sum(r.wins for r in recs)
        total_losses = sum(r.losses for r in recs)
        total_pnl = sum(r.total_pnl for r in recs)

        win_rate = (total_wins / total_taken * 100) if total_taken > 0 else 0
        avg_win = (
            sum(r.avg_win * r.wins for r in recs if r.wins > 0) / total_wins
            if total_wins > 0
            else 0
        )
        avg_loss = (
            sum(abs(r.avg_loss) * r.losses for r in recs if r.losses > 0) / total_losses
            if total_losses > 0
            else 0
        )
        alloc = recs[-1].capital_weight_pct if recs else 0

        parts.append(f"\n<b>{strategy}</b>")
        if total_taken == 0:
            parts.append(f"  No trades | Allocation: {alloc:.0f}%")
        else:
            parts.append(f"  Win Rate: {win_rate:.0f}% ({total_taken} trades)")
            parts.append(f"  Avg Win: +{avg_win:,.0f} | Avg Loss: -{avg_loss:,.0f}")
            parts.append(f"  Net P&L: {total_pnl:+,.0f}")
            parts.append(f"  Allocation: {alloc:.0f}%")

    return "\n".join(parts)


def format_allocation_summary(allocations: dict) -> str:
    """Format weekly rebalance allocation summary."""
    parts = ["<b>Weekly Capital Rebalancing</b>"]
    for name, alloc in allocations.items():
        parts.append(
            f"  {alloc.strategy_name}: {alloc.weight_pct:.0f}% | "
            f"{alloc.allocated_capital:,.0f} | {alloc.max_positions} positions"
        )
    parts.append("  Reserve: 20%")
    return "\n".join(parts)
