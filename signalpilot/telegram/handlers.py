"""Telegram command handler logic.

Each handler is a standalone async function that takes repositories/services
as arguments and returns a response string. This keeps the handlers testable
without depending on python-telegram-bot's Update/Context objects.
"""

import logging
import re
from datetime import date, datetime

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
        "<b>HELP</b> - Show this help message"
    )
