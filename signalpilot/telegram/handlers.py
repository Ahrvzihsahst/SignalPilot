"""Telegram command handler logic.

Each handler is a standalone async function that takes repositories/services
as arguments and returns a response string. This keeps the handlers testable
without depending on python-telegram-bot's Update/Context objects.
"""

import logging
import re
from datetime import datetime, timedelta

from signalpilot.db.models import (
    CallbackResult,
    SignalActionRecord,
    SignalRecord,
    TradeRecord,
    WatchlistRecord,
)
from signalpilot.telegram.formatters import (
    format_journal_message,
    format_status_message,
)
from signalpilot.utils.constants import IST

logger = logging.getLogger(__name__)

_CAPITAL_PATTERN = re.compile(r"(?i)^capital\s+(\d+(?:\.\d+)?)$")
_TAKEN_PATTERN = re.compile(r"(?i)^/?taken(?:\s+force)?(?:\s+(\d+))?$")


async def handle_taken(
    signal_repo,
    trade_repo,
    config_repo,
    exit_monitor,
    now: datetime | None = None,
    text: str | None = None,
    signal_action_repo=None,
) -> str:
    """Process the TAKEN command.

    Finds the latest active signal (or a specific one by ID), creates a
    trade record, starts exit monitoring, and returns a confirmation message.
    Enforces position limits unless FORCE keyword is used.
    """
    now = now or datetime.now(IST)

    # Parse optional signal ID from command text
    requested_id: int | None = None
    if text is not None:
        match = _TAKEN_PATTERN.match(text.strip())
        if match and match.group(1):
            requested_id = int(match.group(1))

    if requested_id is not None:
        signal: SignalRecord | None = await signal_repo.get_active_signal_by_id(requested_id, now)
        if signal is None:
            # Check if the signal exists but was skipped
            cursor = await signal_repo._conn.execute(
                "SELECT status FROM signals WHERE id = ?", (requested_id,)
            )
            row = await cursor.fetchone()
            if row and row["status"] == "skipped":
                return f"Signal #{requested_id} was already skipped."
            logger.warning("TAKEN %d: no active signal with that ID", requested_id)
            return f"No active signal with ID {requested_id}."
    else:
        signal = await signal_repo.get_latest_active_signal(now)
        if signal is None:
            logger.warning("TAKEN command received but no active signal found")
            return "No active signal to log."

    if signal.expires_at is not None and signal.expires_at <= now:
        logger.warning(
            "TAKEN command received but signal %d (%s) has expired",
            signal.id, signal.symbol,
        )
        return "Signal has expired and is no longer valid."

    # Check position limit (soft block unless FORCE)
    force = text is not None and re.search(r"(?i)\bforce\b", text)
    if not force:
        user_config = await config_repo.get_user_config()
        active_count = await trade_repo.get_active_trade_count()
        if user_config and active_count >= user_config.max_positions:
            return (
                f"Position limit reached ({active_count}/{user_config.max_positions}). "
                f"Use TAKEN FORCE to override."
            )

    trade = TradeRecord(
        signal_id=signal.id,
        date=signal.date,
        symbol=signal.symbol,
        strategy=signal.strategy,
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

    # Record action in signal_actions table (Phase 4)
    if signal_action_repo is not None:
        response_time_ms = None
        if signal.created_at:
            response_time_ms = int((now - signal.created_at).total_seconds() * 1000)
        await signal_action_repo.insert_action(SignalActionRecord(
            signal_id=signal.id,
            action="taken",
            response_time_ms=response_time_ms,
            acted_at=now,
        ))

    logger.info(
        "Trade logged for %s (signal_id=%d, trade_id=%d)",
        signal.symbol, signal.id, trade_id,
    )
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
    metrics = await metrics_calculator.calculate_performance_metrics()
    return format_journal_message(metrics)


async def handle_capital(config_repo, text: str) -> str:
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
    user_config = await config_repo.get_user_config()
    max_positions = user_config.max_positions if user_config else 8
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
        "<b>TAKEN [FORCE] [id]</b> - Log a signal as a trade (latest or by ID)\n"
        "<b>STATUS</b> - View active signals and open trades\n"
        "<b>JOURNAL</b> - View trading performance summary\n"
        "<b>CAPITAL &lt;amount&gt;</b> - Update trading capital\n"
        "<b>PAUSE &lt;strategy&gt;</b> - Pause a strategy (GAP/ORB/VWAP)\n"
        "<b>RESUME &lt;strategy&gt;</b> - Resume a strategy\n"
        "<b>ALLOCATE</b> - View/set capital allocation\n"
        "<b>STRATEGY</b> - View per-strategy performance\n"
        "<b>WATCHLIST</b> - View stocks on your watchlist\n"
        "<b>UNWATCH &lt;symbol&gt;</b> - Remove a stock from your watchlist\n"
        "<b>HELP</b> - Show this help message\n"
        "\n"
        "Tap buttons below signals for quick actions."
    )


# ---------------------------------------------------------------------------
# Phase 4: Signal Action Callback Handlers
# ---------------------------------------------------------------------------

_WATCHLIST_EXPIRY_DAYS = 5


async def handle_taken_callback(
    signal_repo,
    trade_repo,
    config_repo,
    exit_monitor,
    signal_action_repo,
    signal_id: int,
    callback_timestamp: datetime | None = None,
) -> CallbackResult:
    """Handle TAKEN button press on a signal."""
    from signalpilot.telegram.keyboards import build_taken_followup_keyboard

    now = callback_timestamp or datetime.now(IST)

    # Fetch signal by ID (raw query, not filtered by active)
    cursor = await signal_repo._conn.execute(
        "SELECT * FROM signals WHERE id = ?", (signal_id,)
    )
    row = await cursor.fetchone()
    if row is None:
        return CallbackResult(answer_text="Signal not found.", success=False)

    signal = signal_repo._row_to_record(row)

    if signal.status == "taken":
        return CallbackResult(answer_text="Already taken.", success=False)
    if signal.status == "skipped":
        return CallbackResult(answer_text="Already skipped.", success=False)
    if signal.expires_at is not None and signal.expires_at <= now:
        return CallbackResult(answer_text="Signal expired.", success=False)

    # Check position limit
    user_config = await config_repo.get_user_config()
    active_count = await trade_repo.get_active_trade_count()
    if user_config and active_count >= user_config.max_positions:
        return CallbackResult(
            answer_text=f"Position limit ({active_count}/{user_config.max_positions})."
            " Use TAKEN FORCE.",
            success=False,
        )

    # Create trade
    trade = TradeRecord(
        signal_id=signal.id,
        date=signal.date,
        symbol=signal.symbol,
        strategy=signal.strategy,
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

    # Record action
    response_time_ms = None
    if signal.created_at:
        response_time_ms = int((now - signal.created_at).total_seconds() * 1000)

    if signal_action_repo:
        await signal_action_repo.insert_action(SignalActionRecord(
            signal_id=signal.id,
            action="taken",
            response_time_ms=response_time_ms,
            acted_at=now,
        ))

    logger.info("TAKEN via button: %s (signal=%d, trade=%d)", signal.symbol, signal.id, trade_id)

    return CallbackResult(
        answer_text=f"Trade logged: {signal.symbol}",
        success=True,
        status_line=f"TAKEN -- Tracking {signal.symbol}",
        new_keyboard=build_taken_followup_keyboard(signal.id),
    )


async def handle_skip_callback(
    signal_repo,
    signal_action_repo,
    signal_id: int,
    callback_timestamp: datetime | None = None,
) -> CallbackResult:
    """Handle SKIP button press — show reason keyboard."""
    from signalpilot.telegram.keyboards import build_skip_reason_keyboard

    cursor = await signal_repo._conn.execute(
        "SELECT * FROM signals WHERE id = ?", (signal_id,)
    )
    row = await cursor.fetchone()
    if row is None:
        return CallbackResult(answer_text="Signal not found.", success=False)

    signal = signal_repo._row_to_record(row)
    if signal.status not in ("sent", "paper"):
        return CallbackResult(answer_text=f"Already {signal.status}.", success=False)

    return CallbackResult(
        answer_text="Select skip reason:",
        success=True,
        new_keyboard=build_skip_reason_keyboard(signal_id),
    )


async def handle_skip_reason_callback(
    signal_repo,
    signal_action_repo,
    signal_id: int,
    reason_code: str,
    callback_timestamp: datetime | None = None,
) -> CallbackResult:
    """Handle skip reason selection."""
    now = callback_timestamp or datetime.now(IST)

    cursor = await signal_repo._conn.execute(
        "SELECT * FROM signals WHERE id = ?", (signal_id,)
    )
    row = await cursor.fetchone()
    if row is None:
        return CallbackResult(answer_text="Signal not found.", success=False)

    signal = signal_repo._row_to_record(row)

    await signal_repo.update_status(signal.id, "skipped")

    reason_labels = {
        "no_capital": "No Capital",
        "low_confidence": "Low Confidence",
        "sector": "Already In Sector",
        "other": "Other",
    }
    label = reason_labels.get(reason_code, reason_code)

    # Record action
    response_time_ms = None
    if signal.created_at:
        response_time_ms = int((now - signal.created_at).total_seconds() * 1000)

    if signal_action_repo:
        await signal_action_repo.insert_action(SignalActionRecord(
            signal_id=signal.id,
            action="skip",
            reason=reason_code,
            response_time_ms=response_time_ms,
            acted_at=now,
        ))

    logger.info("SKIP via button: %s reason=%s (signal=%d)", signal.symbol, reason_code, signal.id)

    return CallbackResult(
        answer_text=f"Skipped: {label}",
        success=True,
        status_line=f"SKIPPED -- {signal.symbol} ({label})",
    )


async def handle_watch_callback(
    signal_repo,
    signal_action_repo,
    watchlist_repo,
    signal_id: int,
    callback_timestamp: datetime | None = None,
) -> CallbackResult:
    """Handle WATCH button press — add signal stock to watchlist."""
    now = callback_timestamp or datetime.now(IST)

    cursor = await signal_repo._conn.execute(
        "SELECT * FROM signals WHERE id = ?", (signal_id,)
    )
    row = await cursor.fetchone()
    if row is None:
        return CallbackResult(answer_text="Signal not found.", success=False)

    signal = signal_repo._row_to_record(row)

    if signal.expires_at is not None and signal.expires_at <= now:
        return CallbackResult(answer_text="Signal expired.", success=False)

    # Check if already on watchlist
    if await watchlist_repo.is_on_watchlist(signal.symbol, now):
        return CallbackResult(answer_text=f"{signal.symbol} already on watchlist.", success=False)

    # Add to watchlist
    entry = WatchlistRecord(
        symbol=signal.symbol,
        signal_id=signal.id,
        strategy=signal.strategy,
        entry_price=signal.entry_price,
        added_at=now,
        expires_at=now + timedelta(days=_WATCHLIST_EXPIRY_DAYS),
    )
    await watchlist_repo.add_to_watchlist(entry)

    # Record action
    response_time_ms = None
    if signal.created_at:
        response_time_ms = int((now - signal.created_at).total_seconds() * 1000)

    if signal_action_repo:
        await signal_action_repo.insert_action(SignalActionRecord(
            signal_id=signal.id,
            action="watch",
            response_time_ms=response_time_ms,
            acted_at=now,
        ))

    logger.info("WATCH via button: %s (signal=%d)", signal.symbol, signal.id)

    return CallbackResult(
        answer_text=f"{signal.symbol} added to watchlist",
        success=True,
        status_line=f"WATCHING -- {signal.symbol} (5 day alert)",
    )


# ---------------------------------------------------------------------------
# Phase 4: Trade Management Callback Handlers
# ---------------------------------------------------------------------------


async def handle_partial_exit_callback(
    trade_repo,
    trade_id: int,
    level: str,
) -> CallbackResult:
    """Handle partial exit at T1 or full exit at T2."""
    trades = await trade_repo.get_active_trades()
    trade = next((t for t in trades if t.id == trade_id), None)

    if trade is None:
        return CallbackResult(answer_text="Trade already closed.", success=False)

    if level == "t1":
        return CallbackResult(
            answer_text=f"Partial exit noted for {trade.symbol} at T1.",
            success=True,
            status_line=f"PARTIAL EXIT -- {trade.symbol} at T1",
        )
    elif level == "t2":
        return CallbackResult(
            answer_text=f"Full exit noted for {trade.symbol} at T2.",
            success=True,
            status_line=f"FULL EXIT -- {trade.symbol} at T2",
        )

    return CallbackResult(answer_text="Unknown exit level.", success=False)


async def handle_exit_now_callback(
    trade_repo,
    exit_monitor,
    get_current_prices,
    trade_id: int,
) -> CallbackResult:
    """Handle Exit Now button — close trade at market price."""
    trades = await trade_repo.get_active_trades()
    trade = next((t for t in trades if t.id == trade_id), None)

    if trade is None:
        return CallbackResult(answer_text="Trade already closed.", success=False)

    prices = await get_current_prices([trade.symbol])
    price = prices.get(trade.symbol)
    if price is None:
        return CallbackResult(answer_text="Could not get current price.", success=False)

    pnl_amount = (price - trade.entry_price) * trade.quantity
    pnl_pct = ((price - trade.entry_price) / trade.entry_price) * 100
    await trade_repo.close_trade(trade.id, price, pnl_amount, pnl_pct, "manual_exit")
    exit_monitor.stop_monitoring(trade.id)

    sign = "+" if pnl_pct >= 0 else ""
    return CallbackResult(
        answer_text=f"Exited {trade.symbol} at {price:,.2f}",
        success=True,
        status_line=f"EXITED -- {trade.symbol} at {price:,.2f} ({sign}{pnl_pct:.1f}%)",
    )


async def handle_take_profit_callback(
    trade_repo,
    exit_monitor,
    get_current_prices,
    trade_id: int,
) -> CallbackResult:
    """Handle Take Profit button — close trade at current price."""
    trades = await trade_repo.get_active_trades()
    trade = next((t for t in trades if t.id == trade_id), None)

    if trade is None:
        return CallbackResult(answer_text="Trade already closed.", success=False)

    prices = await get_current_prices([trade.symbol])
    price = prices.get(trade.symbol)
    if price is None:
        return CallbackResult(answer_text="Could not get current price.", success=False)

    pnl_amount = (price - trade.entry_price) * trade.quantity
    pnl_pct = ((price - trade.entry_price) / trade.entry_price) * 100
    await trade_repo.close_trade(trade.id, price, pnl_amount, pnl_pct, "t2_hit")
    exit_monitor.stop_monitoring(trade.id)

    sign = "+" if pnl_pct >= 0 else ""
    return CallbackResult(
        answer_text=f"Profit taken: {trade.symbol}",
        success=True,
        status_line=f"PROFIT TAKEN -- {trade.symbol} ({sign}{pnl_pct:.1f}%)",
    )


async def handle_hold_callback(trade_id: int) -> CallbackResult:
    """Handle Hold button — dismiss SL-approaching alert."""
    return CallbackResult(
        answer_text="Holding position.",
        success=True,
        status_line="HOLDING -- Alert dismissed",
    )


async def handle_let_run_callback(trade_id: int) -> CallbackResult:
    """Handle Let It Run button — dismiss near-T2 alert."""
    return CallbackResult(
        answer_text="Letting it run.",
        success=True,
        status_line="RUNNING -- Trailing stop active",
    )


# ---------------------------------------------------------------------------
# Phase 4: WATCHLIST / UNWATCH Text Commands
# ---------------------------------------------------------------------------

_UNWATCH_PATTERN = re.compile(r"(?i)^unwatch\s+(\w+)$")


async def handle_watchlist_command(watchlist_repo) -> str:
    """Process the WATCHLIST command — show active watchlist entries."""
    now = datetime.now(IST)
    entries = await watchlist_repo.get_active_watchlist(now)

    if not entries:
        return "No stocks on your watchlist."

    parts = [f"<b>Watchlist ({len(entries)} stocks)</b>"]
    for e in entries:
        days_left = max(0, (e.expires_at - now).days) if e.expires_at else 0
        trigger_info = f", triggered {e.triggered_count}x" if e.triggered_count > 0 else ""
        parts.append(
            f"  {e.symbol} ({e.strategy}) - Entry: {e.entry_price:,.2f}, "
            f"{days_left}d left{trigger_info}"
        )

    return "\n".join(parts)


async def handle_unwatch_command(watchlist_repo, text: str) -> str:
    """Process the UNWATCH command — remove a stock from the watchlist."""
    match = _UNWATCH_PATTERN.match(text.strip())
    if not match:
        return "Usage: UNWATCH <symbol>\nExample: UNWATCH SBIN"

    symbol = match.group(1).upper()
    count = await watchlist_repo.remove_from_watchlist(symbol)

    if count == 0:
        return f"{symbol} is not on your watchlist."

    return f"{symbol} removed from watchlist."
