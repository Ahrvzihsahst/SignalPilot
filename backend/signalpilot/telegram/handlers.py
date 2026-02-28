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
_TAKEN_PATTERN = re.compile(r"(?i)^/?taken(?:\s+(force))?(?:\s+(\d+))?$")
_SCORE_PATTERN = re.compile(r"(?i)^score\s+(\S+)$")
_NEWS_PATTERN = re.compile(r"(?i)^news(?:\s+(\S+))?$")
_UNSUPPRESS_PATTERN = re.compile(r"(?i)^unsuppress\s+(\S+)$")


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

    Supports ``TAKEN FORCE`` to bypass position limit soft-blocks.
    When ``signal_action_repo`` is provided, records the action for analytics.
    """
    now = now or datetime.now(IST)

    # Parse optional FORCE flag and signal ID from command text
    requested_id: int | None = None
    force: bool = False
    if text is not None:
        match = _TAKEN_PATTERN.match(text.strip())
        if match:
            if match.group(1):
                force = True
            if match.group(2):
                requested_id = int(match.group(2))

    if requested_id is not None:
        signal: SignalRecord | None = await signal_repo.get_active_signal_by_id(requested_id, now)
        if signal is None:
            # Check if signal was skipped via button
            if hasattr(signal_repo, "get_signal_status"):
                status = await signal_repo.get_signal_status(requested_id)
                if status == "skipped":
                    return f"Signal {requested_id} was already skipped."
            logger.warning("TAKEN %d: no active signal with that ID", requested_id)
            return f"No active signal with ID {requested_id}."
    else:
        signal = await signal_repo.get_latest_active_signal(now)
        if signal is None:
            logger.warning("TAKEN command received but no active signal found")
            return "No active signal to log."

    if signal.expires_at is not None and signal.expires_at <= now:
        logger.warning("TAKEN command received but signal %d (%s) has expired", signal.id, signal.symbol)
        return "Signal has expired and is no longer valid."

    # Position limit check (soft-block unless FORCE)
    if not force and config_repo is not None:
        try:
            user_config = await config_repo.get_user_config()
            if user_config is not None:
                max_pos = getattr(user_config, "max_positions", None)
                if max_pos is not None:
                    active_count = await trade_repo.get_active_trade_count()
                    if active_count >= max_pos:
                        logger.warning(
                            "TAKEN blocked: %d/%d positions filled",
                            active_count, max_pos,
                        )
                        return (
                            f"Position limit reached ({active_count}/{max_pos}). "
                            f"Use TAKEN FORCE to override."
                        )
        except Exception:
            logger.debug("Could not check position limit", exc_info=True)

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

    # Record signal action for analytics
    if signal_action_repo is not None:
        try:
            await signal_action_repo.insert_action(
                SignalActionRecord(
                    signal_id=signal.id,
                    action="taken",
                    acted_at=now,
                )
            )
        except Exception:
            logger.debug("Failed to record signal action", exc_info=True)

    logger.info("Trade logged for %s (signal_id=%d, trade_id=%d)", signal.symbol, signal.id, trade_id)
    return f"Trade logged. Tracking {signal.symbol}."


async def handle_status(
    signal_repo,
    trade_repo,
    get_current_prices,
    now: datetime | None = None,
    hybrid_score_repo=None,
) -> str:
    """Process the STATUS command.

    Returns formatted status of active signals and open trades with live P&L.
    ``get_current_prices`` is an async callable: list[str] -> dict[str, float].

    When ``hybrid_score_repo`` is provided, signals are sorted by composite_score
    and rank numbers and confirmation badges are added.
    """
    now = now or datetime.now(IST)
    today = now.date()

    signals = await signal_repo.get_active_signals(today, now)
    trades = await trade_repo.get_active_trades()

    symbols = [t.symbol for t in trades]
    current_prices = await get_current_prices(symbols) if symbols else {}

    # Fetch composite scores for active signals if hybrid_score_repo available
    score_map: dict[str, float] = {}
    confirmation_map: dict[str, str] = {}
    if hybrid_score_repo is not None:
        for s in signals:
            if s.id is not None:
                try:
                    hs = await hybrid_score_repo.get_by_signal_id(s.id)
                    if hs is not None:
                        score_map[s.symbol] = hs.composite_score
                        if hs.confirmation_level and hs.confirmation_level != "single":
                            confirmation_map[s.symbol] = hs.confirmation_level
                except Exception:
                    logger.debug("Could not fetch hybrid score for signal %d", s.id)

    return format_status_message(
        signals, trades, current_prices,
        score_map=score_map,
        confirmation_map=confirmation_map,
    )


async def handle_journal(
    metrics_calculator,
    hybrid_score_repo=None,
) -> str:
    """Process the JOURNAL command.

    Returns formatted performance metrics. When hybrid_score_repo is provided,
    includes a confirmed signals section.
    """
    metrics = await metrics_calculator.calculate_performance_metrics()

    # Build confirmed signals section
    confirmed_count = 0
    if hybrid_score_repo is not None:
        try:
            today = datetime.now(IST).date()
            scores = await hybrid_score_repo.get_by_date(today)
            confirmed_count = sum(
                1 for s in scores
                if s.confirmation_level and s.confirmation_level != "single"
            )
        except Exception:
            logger.debug("Could not fetch hybrid scores for journal")

    return format_journal_message(metrics, confirmed_count=confirmed_count)


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


async def handle_strategy(strategy_performance_repo, adaptive_manager=None) -> str:
    """Process the STRATEGY command -- show per-strategy performance.

    When ``adaptive_manager`` is provided, appends adaptation status
    (normal/reduced/paused) for each strategy.
    """
    if strategy_performance_repo is None:
        return "Strategy performance tracking not configured."

    today = datetime.now(IST).date()
    from datetime import timedelta
    start = today - timedelta(days=30)

    from signalpilot.telegram.formatters import format_strategy_report
    records = await strategy_performance_repo.get_by_date_range(start, today)
    base_report = format_strategy_report(records)

    # Append adaptation status if available
    if adaptive_manager is not None:
        states = adaptive_manager.get_all_states()
        if states:
            lines = [base_report, "", "<b>Adaptation Status</b>"]
            for strategy_name, state in states.items():
                level_display = state.level.value.upper()
                lines.append(
                    f"  {strategy_name}: {level_display} "
                    f"(W:{state.daily_wins} L:{state.daily_losses} "
                    f"streak:{state.consecutive_losses}L/{state.consecutive_wins}W)"
                )
            return "\n".join(lines)

    return base_report


# ---------------------------------------------------------------------------
# Phase 3 command handlers
# ---------------------------------------------------------------------------


async def handle_override_circuit(circuit_breaker, app=None) -> str:
    """Process the OVERRIDE CIRCUIT command.

    If the circuit breaker is active, return a confirmation prompt.
    Actual override happens when the user replies YES.
    """
    logger.info("Entering handle_override_circuit")

    if circuit_breaker is None:
        logger.info("Exiting handle_override_circuit: not configured")
        return "Circuit breaker not configured."

    if not circuit_breaker.is_active:
        logger.info("Exiting handle_override_circuit: not active")
        return "Circuit breaker is not active."

    logger.info("Exiting handle_override_circuit: prompting for confirmation")
    return (
        "Circuit breaker is currently active "
        f"({circuit_breaker.daily_sl_count}/{circuit_breaker.sl_limit} SL hits).\n"
        "Reply YES to override and resume signal generation."
    )


async def handle_override_confirm(circuit_breaker, app=None) -> str:
    """Process the YES confirmation for OVERRIDE CIRCUIT.

    Calls circuit_breaker.override() and re-enables signal generation.
    """
    logger.info("Entering handle_override_confirm")

    if circuit_breaker is None:
        logger.info("Exiting handle_override_confirm: not configured")
        return "Circuit breaker not configured."

    if not circuit_breaker.is_active:
        logger.info("Exiting handle_override_confirm: not active")
        return "Circuit breaker is not active. No override needed."

    result = await circuit_breaker.override()
    if result:
        # Re-enable signal acceptance on the app
        if app is not None and hasattr(app, "_accepting_signals"):
            app._accepting_signals = True
        logger.info("Exiting handle_override_confirm: override successful")
        return (
            "Circuit breaker overridden. Signal generation resumed.\n"
            "Use caution -- stop losses may continue."
        )

    logger.info("Exiting handle_override_confirm: override failed")
    return "Failed to override circuit breaker."


async def handle_score(hybrid_score_repo, text: str) -> str:
    """Process the SCORE [STOCK] command.

    Looks up the latest hybrid score for the given symbol and displays
    the composite score breakdown.
    """
    logger.info("Entering handle_score", extra={"text": text})

    if hybrid_score_repo is None:
        logger.info("Exiting handle_score: not configured")
        return "Hybrid scoring not configured."

    match = _SCORE_PATTERN.match(text.strip())
    if not match:
        return "Usage: SCORE <SYMBOL>\nExample: SCORE SBIN"

    symbol = match.group(1).upper()

    record = await hybrid_score_repo.get_latest_for_symbol(symbol)
    if record is None:
        logger.info("Exiting handle_score: no score found for %s", symbol)
        return f"No signal found for {symbol} today."

    lines = [
        f"<b>Composite Score -- {symbol}</b>",
        "",
        f"Composite Score: {record.composite_score:.1f}/100",
        f"  Strategy Strength: {record.strategy_strength_score:.1f}",
        f"  Win Rate Score: {record.win_rate_score:.1f}",
        f"  Risk-Reward Score: {record.risk_reward_score:.1f}",
        f"  Confirmation Bonus: {record.confirmation_bonus:.0f}",
        "",
        f"Confirmation: {record.confirmation_level}",
    ]
    if record.confirmed_by:
        lines.append(f"Confirmed By: {record.confirmed_by}")
    lines.append(f"Position Multiplier: {record.position_size_multiplier:.1f}x")

    logger.info("Exiting handle_score", extra={"symbol": symbol, "score": record.composite_score})
    return "\n".join(lines)


async def handle_adapt(adaptive_manager) -> str:
    """Process the ADAPT command.

    Shows per-strategy adaptation status.
    """
    logger.info("Entering handle_adapt")

    if adaptive_manager is None:
        logger.info("Exiting handle_adapt: not configured")
        return "Adaptive learning not configured."

    states = adaptive_manager.get_all_states()
    if not states:
        logger.info("Exiting handle_adapt: no states")
        return "No adaptation data yet. Strategies start in NORMAL mode."

    lines = ["<b>Adaptive Strategy Status</b>"]
    for strategy_name, state in states.items():
        level_display = state.level.value.upper()
        status_icon = {
            "NORMAL": "OK",
            "REDUCED": "THROTTLED",
            "PAUSED": "STOPPED",
        }.get(level_display, level_display)

        lines.append(f"\n<b>{strategy_name}</b>")
        lines.append(f"  Status: {status_icon}")
        lines.append(f"  Today: {state.daily_wins}W / {state.daily_losses}L")
        lines.append(
            f"  Streak: {state.consecutive_losses} consecutive losses / "
            f"{state.consecutive_wins} consecutive wins"
        )

    logger.info("Exiting handle_adapt", extra={"strategy_count": len(states)})
    return "\n".join(lines)


async def handle_rebalance(
    capital_allocator,
    config_repo,
    adaptation_log_repo=None,
    bot=None,
) -> str:
    """Process the REBALANCE command.

    Triggers a manual capital rebalance and logs the event.
    """
    logger.info("Entering handle_rebalance")

    if capital_allocator is None:
        logger.info("Exiting handle_rebalance: not configured")
        return "Capital allocator not configured."

    if config_repo is None:
        logger.info("Exiting handle_rebalance: no config repo")
        return "Configuration not available."

    user_config = await config_repo.get_user_config()
    if user_config is None:
        logger.info("Exiting handle_rebalance: no user config")
        return "No user config found."

    today = datetime.now(IST).date()
    allocations = await capital_allocator.calculate_allocations(
        user_config.total_capital, user_config.max_positions, today
    )

    # Log the manual rebalance event
    if adaptation_log_repo is not None:
        for strategy_name, alloc in allocations.items():
            await adaptation_log_repo.insert_log(
                today=today,
                strategy=strategy_name,
                event_type="manual_rebalance",
                details=f"Manual rebalance: {alloc.weight_pct:.0f}% / {alloc.allocated_capital:,.0f}",
                old_weight=None,
                new_weight=alloc.weight_pct,
            )

    # Format response
    lines = ["<b>Manual Rebalance Complete</b>"]
    for name, alloc in allocations.items():
        lines.append(
            f"  {alloc.strategy_name}: {alloc.weight_pct:.0f}% | "
            f"{alloc.allocated_capital:,.0f} | {alloc.max_positions} positions"
        )
    lines.append("  Reserve: 20%")

    logger.info("Exiting handle_rebalance", extra={"strategies": len(allocations)})
    return "\n".join(lines)


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
        "<b>SCORE &lt;SYMBOL&gt;</b> - View composite score breakdown\n"
        "<b>ADAPT</b> - View adaptive strategy status\n"
        "<b>REBALANCE</b> - Trigger manual capital rebalance\n"
        "<b>OVERRIDE CIRCUIT</b> - Override circuit breaker\n"
        "<b>WATCHLIST</b> - View active watchlist\n"
        "<b>UNWATCH &lt;symbol&gt;</b> - Remove from watchlist\n"
        "<b>REGIME</b> - View current market regime\n"
        "<b>REGIME HISTORY</b> - View recent regime history\n"
        "<b>REGIME OVERRIDE &lt;type&gt;</b> - Override regime (TRENDING/RANGING/VOLATILE)\n"
        "<b>VIX</b> - View current India VIX\n"
        "<b>MORNING</b> - View today's morning brief\n"
        "<b>HELP</b> - Show this help message\n"
        "\n"
        "Tap buttons below each signal to quickly TAKEN/SKIP/WATCH."
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


async def handle_news_command(news_sentiment_service, text: str) -> str:
    """Process the NEWS command — show sentiment for a stock or all stocks.

    Usage: NEWS <STOCK> or NEWS ALL or NEWS (for summary).
    """
    match = _NEWS_PATTERN.match(text.strip())
    if not match:
        return "Usage: NEWS <STOCK>\nExample: NEWS SBIN\nOr: NEWS ALL"

    stock = match.group(1)

    if stock is None or stock.upper() == "ALL":
        # Summary of all stocks
        all_sentiments = await news_sentiment_service._news_sentiment_repo.get_all_stock_sentiments()
        if not all_sentiments:
            return "No news sentiment data available. Data is fetched at 8:30 AM."

        parts = ["<b>News Sentiment Summary</b>"]
        label_icons = {
            "STRONG_NEGATIVE": "\u274c",
            "MILD_NEGATIVE": "\u26a0\ufe0f",
            "NEUTRAL": "\u2796",
            "POSITIVE": "\u2705",
        }
        for code, (score, label, count) in sorted(all_sentiments.items()):
            icon = label_icons.get(label, "\u2796")
            parts.append(f"  {icon} {code}: {score:+.2f} ({label}, {count} headlines)")
        return "\n".join(parts)

    stock_code = stock.upper()
    result = await news_sentiment_service.get_sentiment_for_stock(stock_code)

    parts = [f"<b>News Sentiment: {stock_code}</b>"]
    parts.append(f"Score: {result.score:+.2f}")
    parts.append(f"Label: {result.label}")
    parts.append(f"Action: {result.action}")
    parts.append(f"Headlines: {result.headline_count}")
    parts.append(f"Model: {result.model_used}")

    if result.headline:
        parts.append(f"\nTop: {result.headline}")
    if result.top_negative_headline and result.top_negative_headline != result.headline:
        parts.append(f"Most Negative: {result.top_negative_headline}")

    return "\n".join(parts)


async def handle_earnings_command(earnings_repo, days: int = 7) -> str:
    """Process the EARNINGS command — show upcoming earnings calendar."""
    upcoming = await earnings_repo.get_upcoming_earnings(days)

    if not upcoming:
        return "No upcoming earnings in the next 7 days."

    # Group by date
    by_date: dict[str, list] = {}
    for e in upcoming:
        date_str = e.earnings_date.isoformat() if e.earnings_date else "Unknown"
        by_date.setdefault(date_str, []).append(e)

    parts = [f"<b>Upcoming Earnings (next {days} days)</b>"]
    for dt, entries in sorted(by_date.items()):
        parts.append(f"\n<b>{dt}</b>")
        for e in entries:
            status = "Confirmed" if e.is_confirmed else "Tentative"
            parts.append(f"  {e.stock_code} - {e.quarter} ({status})")

    return "\n".join(parts)


async def handle_unsuppress_command(news_sentiment_service, text: str) -> str:
    """Process the UNSUPPRESS command — override suppression for a stock."""
    match = _UNSUPPRESS_PATTERN.match(text.strip())
    if not match:
        return "Usage: UNSUPPRESS <STOCK>\nExample: UNSUPPRESS SBIN"

    stock_code = match.group(1).upper()

    # Get current sentiment before adding override
    result = await news_sentiment_service.get_sentiment_for_stock(stock_code)
    news_sentiment_service.add_unsuppress_override(stock_code)

    return (
        f"Override added for {stock_code}\n"
        f"Current sentiment: {result.label} ({result.score:+.2f})\n"
        f"Signals for {stock_code} will pass through until end of day."
    )


# ---------------------------------------------------------------------------
# Phase 4: Market Regime Detection Command Handlers
# ---------------------------------------------------------------------------

_REGIME_OVERRIDE_PATTERN = re.compile(r"(?i)^regime\s+override\s+(trending|ranging|volatile)$")


async def handle_regime_command(regime_classifier) -> str:
    """Process the REGIME command — show current regime classification."""
    if regime_classifier is None:
        return "Market regime detection not configured."

    classification = regime_classifier.get_cached_regime()
    if classification is None:
        return "No regime classification yet. Classification happens at 9:30 AM."

    from signalpilot.telegram.formatters import format_regime_display
    return format_regime_display(classification)


async def handle_regime_history_command(regime_repo, days: int = 7) -> str:
    """Process the REGIME HISTORY command — show recent regime history."""
    if regime_repo is None:
        return "Market regime detection not configured."

    from signalpilot.telegram.formatters import format_regime_history
    history = await regime_repo.get_regime_history(days)
    return format_regime_history(history, days)


async def handle_regime_override_command(regime_classifier, text: str) -> str:
    """Process the REGIME OVERRIDE <REGIME> command — manually override regime."""
    if regime_classifier is None:
        return "Market regime detection not configured."

    match = _REGIME_OVERRIDE_PATTERN.match(text.strip())
    if not match:
        return "Usage: REGIME OVERRIDE <TRENDING|RANGING|VOLATILE>"

    new_regime = match.group(1).upper()
    result = regime_classifier.apply_override(new_regime)
    if result is None:
        return f"Failed to override regime to {new_regime}. No active classification."

    from signalpilot.telegram.formatters import format_regime_display
    return f"Regime overridden to {new_regime}.\n\n" + format_regime_display(result)


async def handle_vix_command(regime_data_collector) -> str:
    """Process the VIX command — show current India VIX and interpretation."""
    if regime_data_collector is None:
        return "Market regime detection not configured."

    vix = await regime_data_collector.fetch_current_vix()
    if vix is None:
        return "Could not fetch India VIX. Data may not be available yet."

    if vix < 12:
        interpretation = "Very calm — low volatility expected"
    elif vix < 14:
        interpretation = "Normal — standard conditions"
    elif vix < 18:
        interpretation = "Slightly elevated — caution advised"
    elif vix < 22:
        interpretation = "High — volatile conditions likely"
    else:
        interpretation = "Very high — defensive mode recommended"

    return (
        f"<b>India VIX: {vix:.2f}</b>\n"
        f"Interpretation: {interpretation}"
    )


async def handle_morning_command(morning_brief_generator) -> str:
    """Process the MORNING command — show cached morning brief."""
    if morning_brief_generator is None:
        return "Morning brief not configured."

    cached = morning_brief_generator.get_cached_brief()
    if cached is None:
        return "No morning brief available yet. Brief is generated at 8:45 AM."

    return cached
