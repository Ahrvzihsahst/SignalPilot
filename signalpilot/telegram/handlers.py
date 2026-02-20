"""Telegram command handler logic.

Each handler is a standalone async function that takes repositories/services
as arguments and returns a response string. This keeps the handlers testable
without depending on python-telegram-bot's Update/Context objects.
"""

import logging
import re
from datetime import datetime

from signalpilot.db.models import SignalRecord, TradeRecord
from signalpilot.telegram.formatters import (
    format_journal_message,
    format_status_message,
)
from signalpilot.utils.constants import IST

logger = logging.getLogger(__name__)

_CAPITAL_PATTERN = re.compile(r"(?i)^capital\s+(\d+(?:\.\d+)?)$")


async def handle_taken(
    signal_repo,
    trade_repo,
    exit_monitor,
    now: datetime | None = None,
) -> str:
    """Process the TAKEN command.

    Finds the latest active signal, creates a trade record, starts exit
    monitoring, and returns a confirmation message.
    """
    now = now or datetime.now(IST)
    signal: SignalRecord | None = await signal_repo.get_latest_active_signal(now)

    if signal is None:
        return "No active signal to log."

    if signal.expires_at is not None and signal.expires_at <= now:
        return "Signal has expired and is no longer valid."

    trade = TradeRecord(
        signal_id=signal.id,
        date=signal.date,
        symbol=signal.symbol,
        entry_price=signal.entry_price,
        stop_loss=signal.stop_loss,
        target_1=signal.target_1,
        target_2=signal.target_2,
        quantity=signal.quantity,
        taken_at=now,
    )
    trade_id = await trade_repo.insert_trade(trade)
    trade.id = trade_id

    await signal_repo.update_status(signal.id, "taken")

    exit_monitor.start_monitoring(trade)

    logger.info("Trade logged for %s (signal_id=%d, trade_id=%d)", signal.symbol, signal.id, trade_id)
    return f"Trade logged. Tracking {signal.symbol}."


async def handle_status(
    signal_repo,
    trade_repo,
    get_current_prices,
    now: datetime | None = None,
) -> str:
    """Process the STATUS command.

    Returns formatted status of active signals and open trades with live P&L.
    ``get_current_prices`` is an async callable: list[str] -> dict[str, float].
    """
    now = now or datetime.now(IST)
    today = now.date()

    signals = await signal_repo.get_active_signals(today, now)
    trades = await trade_repo.get_active_trades()

    symbols = [t.symbol for t in trades]
    current_prices = await get_current_prices(symbols) if symbols else {}

    return format_status_message(signals, trades, current_prices)


async def handle_journal(metrics_calculator) -> str:
    """Process the JOURNAL command.

    Returns formatted performance metrics or an empty-state message.
    """
    metrics = await metrics_calculator.calculate()
    return format_journal_message(metrics)


async def handle_capital(config_repo, text: str, max_positions: int = 5) -> str:
    """Process the CAPITAL command.

    Parses the amount from the message text, updates the config, and returns
    a confirmation with the new per-trade allocation.
    """
    match = _CAPITAL_PATTERN.match(text.strip())
    if not match:
        return (
            "Usage: CAPITAL <amount>\n"
            "Example: CAPITAL 50000\n"
            "Sets your total trading capital."
        )

    amount = float(match.group(1))
    if amount <= 0:
        return "Capital must be a positive number."

    await config_repo.update_capital(amount)
    per_trade = amount / max_positions
    logger.info("Capital updated to %.0f (per-trade: %.0f)", amount, per_trade)
    return f"Capital updated to {amount:,.0f}. Per-trade allocation is now {per_trade:,.0f}."


_STRATEGY_MAP = {
    "GAP": ("gap_go_enabled", "Gap & Go"),
    "ORB": ("orb_enabled", "ORB"),
    "VWAP": ("vwap_enabled", "VWAP Reversal"),
}

_PAUSE_PATTERN = re.compile(r"(?i)^pause\s+(\w+)$")
_RESUME_PATTERN = re.compile(r"(?i)^resume\s+(\w+)$")
_ALLOCATE_PATTERN = re.compile(r"(?i)^allocate\s+(.*)")


async def handle_pause(config_repo, text: str) -> str:
    """Process the PAUSE command."""
    match = _PAUSE_PATTERN.match(text.strip())
    if not match:
        return "Usage: PAUSE GAP | PAUSE ORB | PAUSE VWAP"

    key = match.group(1).upper()
    if key not in _STRATEGY_MAP:
        return f"Unknown strategy: {key}. Use GAP, ORB, or VWAP."

    field, name = _STRATEGY_MAP[key]
    current = await config_repo.get_strategy_enabled(field)
    if not current:
        return f"{name} is already paused."

    await config_repo.set_strategy_enabled(field, False)
    logger.info("Strategy paused: %s", name)
    return f"{name} paused. No signals will be generated from this strategy."


async def handle_resume(config_repo, text: str) -> str:
    """Process the RESUME command."""
    match = _RESUME_PATTERN.match(text.strip())
    if not match:
        return "Usage: RESUME GAP | RESUME ORB | RESUME VWAP"

    key = match.group(1).upper()
    if key not in _STRATEGY_MAP:
        return f"Unknown strategy: {key}. Use GAP, ORB, or VWAP."

    field, name = _STRATEGY_MAP[key]
    current = await config_repo.get_strategy_enabled(field)
    if current:
        return f"{name} is already active."

    await config_repo.set_strategy_enabled(field, True)
    logger.info("Strategy resumed: %s", name)
    return f"{name} resumed. Signals will be generated when conditions are met."


async def handle_allocate(capital_allocator, config_repo, text: str) -> str:
    """Process the ALLOCATE command."""
    stripped = text.strip()

    if re.match(r"(?i)^allocate$", stripped):
        # Show current allocation
        if capital_allocator is None:
            return "Capital allocator not configured."
        config = await config_repo.get_user_config()
        if config is None:
            return "No user config found."
        today = datetime.now(IST).date()
        allocs = await capital_allocator.calculate_allocations(
            config.total_capital, config.max_positions, today
        )
        lines = ["<b>Current Allocation</b>"]
        for name, alloc in allocs.items():
            lines.append(
                f"  {alloc.strategy_name}: {alloc.weight_pct:.0f}% | "
                f"{alloc.allocated_capital:,.0f} | {alloc.max_positions} positions"
            )
        lines.append("  Reserve: 20% buffer for exceptional signals")
        return "\n".join(lines)

    if re.match(r"(?i)^allocate\s+auto$", stripped):
        if capital_allocator is None:
            return "Capital allocator not configured."
        capital_allocator.enable_auto_allocation()
        return "Auto allocation re-enabled. Weights will recalculate weekly."

    # Manual allocation: ALLOCATE GAP 40 ORB 20 VWAP 20
    match = _ALLOCATE_PATTERN.match(stripped)
    if match and capital_allocator is not None:
        parts = match.group(1).upper().split()
        weights: dict[str, float] = {}
        i = 0
        while i < len(parts) - 1:
            key = parts[i]
            try:
                pct = float(parts[i + 1])
            except (ValueError, IndexError):
                return "Usage: ALLOCATE GAP 40 ORB 20 VWAP 20"
            if key in _STRATEGY_MAP:
                _, name = _STRATEGY_MAP[key]
                weights[name] = pct / 100
            i += 2

        total_pct = sum(weights.values()) * 100
        if total_pct > 80:
            return f"Total allocation ({total_pct:.0f}%) exceeds 80% limit. 20% must be reserved."

        capital_allocator.set_manual_allocation(weights)
        return f"Manual allocation set. Total: {total_pct:.0f}% (20% reserve)."

    return "Usage: ALLOCATE | ALLOCATE AUTO | ALLOCATE GAP 40 ORB 20 VWAP 20"


async def handle_strategy(strategy_performance_repo) -> str:
    """Process the STRATEGY command — show per-strategy performance."""
    if strategy_performance_repo is None:
        return "Strategy performance tracking not configured."

    today = datetime.now(IST).date()
    from datetime import timedelta
    start = today - timedelta(days=30)

    from signalpilot.telegram.formatters import format_strategy_report
    records = await strategy_performance_repo.get_by_date_range(start, today)
    return format_strategy_report(records)


async def handle_help() -> str:
    """Process the HELP command.

    Returns a formatted list of available commands.
    """
    return (
        "<b>SignalPilot Commands</b>\n"
        "\n"
        "<b>TAKEN</b> - Log the latest signal as a trade\n"
        "<b>STATUS</b> - View active signals and open trades\n"
        "<b>JOURNAL</b> - View trading performance summary\n"
        "<b>CAPITAL &lt;amount&gt;</b> - Update trading capital\n"
        "<b>PAUSE &lt;strategy&gt;</b> - Pause a strategy (GAP/ORB/VWAP)\n"
        "<b>RESUME &lt;strategy&gt;</b> - Resume a strategy\n"
        "<b>ALLOCATE</b> - View/set capital allocation\n"
        "<b>STRATEGY</b> - View per-strategy performance\n"
        "<b>HELP</b> - Show this help message"
    )
