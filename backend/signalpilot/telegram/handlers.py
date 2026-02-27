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
_TAKEN_PATTERN = re.compile(r"(?i)^/?taken(?:\s+(\d+))?$")
_SCORE_PATTERN = re.compile(r"(?i)^score\s+(\S+)$")


async def handle_taken(
    signal_repo,
    trade_repo,
    exit_monitor,
    now: datetime | None = None,
    text: str | None = None,
) -> str:
    """Process the TAKEN command.

    Finds the latest active signal (or a specific one by ID), creates a
    trade record, starts exit monitoring, and returns a confirmation message.
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
        "<b>TAKEN [id]</b> - Log a signal as a trade (latest or by ID)\n"
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
        "<b>HELP</b> - Show this help message"
    )
