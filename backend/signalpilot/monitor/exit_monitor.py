"""Exit monitor — checks active trades against exit conditions on every tick."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from signalpilot.db.models import ExitAlert, ExitType, TickData, TradeRecord
from signalpilot.utils.constants import IST
from signalpilot.utils.log_context import log_context

if TYPE_CHECKING:
    from signalpilot.events import EventBus

logger = logging.getLogger(__name__)

# Type alias for trade closer
# (async callable: trade_id, exit_price, pnl_amount, pnl_pct, exit_reason -> None)
TradeCloser = Callable[[int, float, float, float, str], Awaitable[None]]

# Type alias for the market data getter (async callable: symbol -> TickData | None)
MarketDataGetter = Callable[[str], Awaitable[TickData | None]]


@dataclass
class TrailingStopConfig:
    """Per-strategy trailing stop loss configuration."""

    breakeven_trigger_pct: float
    trail_trigger_pct: float | None = None
    trail_distance_pct: float | None = None


# Default configs per strategy (and setup type for VWAP)
DEFAULT_TRAILING_CONFIGS: dict[str, TrailingStopConfig] = {
    "Gap & Go": TrailingStopConfig(
        breakeven_trigger_pct=2.0, trail_trigger_pct=4.0, trail_distance_pct=2.0
    ),
    "gap_go": TrailingStopConfig(
        breakeven_trigger_pct=2.0, trail_trigger_pct=4.0, trail_distance_pct=2.0
    ),
    "ORB": TrailingStopConfig(
        breakeven_trigger_pct=1.5, trail_trigger_pct=2.0, trail_distance_pct=1.0
    ),
    "VWAP Reversal": TrailingStopConfig(
        breakeven_trigger_pct=1.0, trail_trigger_pct=None, trail_distance_pct=None
    ),
    "VWAP Reversal:uptrend_pullback": TrailingStopConfig(
        breakeven_trigger_pct=1.0, trail_trigger_pct=None, trail_distance_pct=None
    ),
    "VWAP Reversal:vwap_reclaim": TrailingStopConfig(
        breakeven_trigger_pct=1.5, trail_trigger_pct=None, trail_distance_pct=None
    ),
}


@dataclass
class TrailingStopState:
    """Per-trade trailing stop loss state."""

    trade_id: int
    original_sl: float
    current_sl: float
    highest_price: float
    strategy: str = "gap_go"
    breakeven_triggered: bool = False
    trailing_active: bool = False
    t1_alerted: bool = False
    sl_approaching_alerted_at: datetime | None = None
    near_t2_alerted: bool = False


class ExitMonitor:
    """Monitors active trades for exit conditions on every tick cycle.

    Exit conditions checked (in priority order):
    1. Stop loss / trailing stop loss hit
    2. Target 2 hit (full exit)
    3. Target 1 hit (advisory alert, trade stays open)
    4. Trailing SL updates (breakeven at configurable %, trail at configurable %)

    Supports per-strategy trailing stop configurations.
    """

    def __init__(
        self,
        get_tick: MarketDataGetter,
        alert_callback: Callable[[ExitAlert], Awaitable[None]],
        breakeven_trigger_pct: float = 2.0,
        trail_trigger_pct: float = 4.0,
        trail_distance_pct: float = 2.0,
        trailing_configs: dict[str, TrailingStopConfig] | None = None,
        close_trade: TradeCloser | None = None,
        on_sl_hit_callback: Callable[..., Awaitable[None]] | None = None,
        on_trade_exit_callback: Callable[..., Awaitable[None]] | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self._get_tick = get_tick
        self._alert_callback = alert_callback
        self._close_trade = close_trade
        self._on_sl_hit_callback = on_sl_hit_callback
        self._on_trade_exit_callback = on_trade_exit_callback
        self._event_bus = event_bus
        self._breakeven_trigger_pct = breakeven_trigger_pct
        self._trail_trigger_pct = trail_trigger_pct
        self._trail_factor = 1.0 - trail_distance_pct / 100.0
        # When trailing_configs is explicitly provided, use per-strategy lookup.
        # Otherwise, constructor-level params apply to all trades (backward compat).
        self._trailing_configs = trailing_configs
        self._fallback_config = TrailingStopConfig(
            breakeven_trigger_pct=breakeven_trigger_pct,
            trail_trigger_pct=trail_trigger_pct,
            trail_distance_pct=trail_distance_pct,
        )
        self._active_states: dict[int, TrailingStopState] = {}

    async def _persist_exit(
        self, trade: TradeRecord, exit_price: float, pnl_pct: float, exit_reason: str,
    ) -> None:
        """Persist the trade closure in the database and fire Phase 3 callbacks."""
        pnl_amount = (exit_price - trade.entry_price) * trade.quantity
        is_loss = pnl_amount < 0

        if self._close_trade is not None:
            try:
                await self._close_trade(trade.id, exit_price, pnl_amount, pnl_pct, exit_reason)
                logger.info(
                    "Trade %d (%s) closed in DB: exit=%.2f pnl=%.2f",
                    trade.id, trade.symbol, exit_price, pnl_amount,
                )
            except Exception:
                logger.exception("Failed to persist trade %d closure", trade.id)

        strategy = getattr(trade, "strategy", "gap_go")

        if self._event_bus is not None:
            # Event-bus path: emit typed events
            from signalpilot.events import StopLossHitEvent, TradeExitedEvent

            if exit_reason in ("sl_hit", "trailing_sl"):
                await self._event_bus.emit(
                    StopLossHitEvent(symbol=trade.symbol, strategy=strategy, pnl_amount=pnl_amount)
                )
            await self._event_bus.emit(
                TradeExitedEvent(strategy_name=strategy, is_loss=is_loss)
            )
        else:
            # Legacy callback path
            if exit_reason in ("sl_hit", "trailing_sl") and self._on_sl_hit_callback is not None:
                try:
                    await self._on_sl_hit_callback(trade.symbol, strategy, pnl_amount)
                except Exception:
                    logger.exception("on_sl_hit_callback failed for trade %d", trade.id)

            if self._on_trade_exit_callback is not None:
                try:
                    await self._on_trade_exit_callback(strategy, is_loss)
                except Exception:
                    logger.exception("on_trade_exit_callback failed for trade %d", trade.id)

    def start_monitoring(self, trade: TradeRecord) -> None:
        """Begin monitoring a trade by initializing its trailing stop state."""
        state = TrailingStopState(
            trade_id=trade.id,
            original_sl=trade.stop_loss,
            current_sl=trade.stop_loss,
            highest_price=trade.entry_price,
            strategy=getattr(trade, "strategy", "gap_go"),
        )
        self._active_states[trade.id] = state
        logger.info("Started monitoring trade %d (%s)", trade.id, trade.symbol)

    def _get_config_for_trade(self, trade: TradeRecord) -> TrailingStopConfig:
        """Look up trailing stop config by trade strategy and setup type."""
        if self._trailing_configs is None:
            # No per-strategy configs provided; use constructor-level params
            return self._fallback_config

        strategy = getattr(trade, "strategy", "gap_go")
        # Try strategy:setup_type key first (for VWAP sub-types)
        setup_type = getattr(trade, "setup_type", None)
        if setup_type:
            key = f"{strategy}:{setup_type}"
            config = self._trailing_configs.get(key)
            if config:
                return config
        # Fall back to strategy key
        config = self._trailing_configs.get(strategy)
        if config:
            return config
        # Default to constructor-level params
        return self._fallback_config

    def stop_monitoring(self, trade_id: int) -> None:
        """Stop monitoring a trade and clean up its state."""
        self._active_states.pop(trade_id, None)
        logger.info("Stopped monitoring trade %d", trade_id)

    async def check_trade(self, trade: TradeRecord) -> ExitAlert | None:
        """Check a single trade against all exit conditions.

        Returns the ExitAlert if an exit or advisory was triggered, None otherwise.
        """
        async with log_context(symbol=trade.symbol):
            state = self._active_states.get(trade.id)
            if state is None:
                return None

            tick = await self._get_tick(trade.symbol)
            if tick is None:
                return None

            current_price = tick.ltp

            # Update highest price seen
            state.highest_price = max(state.highest_price, current_price)

            # Update trailing stop
            trailing_alert = self._update_trailing_stop(trade, state, current_price)

            # Check SL hit (using current trailing stop)
            if current_price <= state.current_sl:
                exit_type = (
                    ExitType.TRAILING_SL_HIT if state.trailing_active else ExitType.SL_HIT
                )
                alert = self._build_exit_alert(trade, current_price, exit_type)
                logger.info(
                    "%s for trade %d (%s): price=%.2f, sl=%.2f",
                    exit_type.value, trade.id, trade.symbol, current_price, state.current_sl,
                )
                self.stop_monitoring(trade.id)
                await self._persist_exit(trade, current_price, alert.pnl_pct, exit_type.value)
                await self._emit_alert(alert)
                return alert

            # Check T2 hit (full exit)
            if current_price >= trade.target_2:
                alert = self._build_exit_alert(trade, current_price, ExitType.T2_HIT)
                alert.keyboard_type = "t2"
                logger.info(
                    "T2 exit for trade %d (%s): price=%.2f", trade.id, trade.symbol, current_price,
                )
                self.stop_monitoring(trade.id)
                await self._persist_exit(trade, current_price, alert.pnl_pct, ExitType.T2_HIT.value)
                await self._emit_alert(alert)
                return alert

            # Check near-T2 (within 0.3% of T2, one-shot)
            if not state.near_t2_alerted and trade.target_2 > 0:
                t2_distance_pct = ((trade.target_2 - current_price) / trade.target_2) * 100
                if 0 < t2_distance_pct <= 0.3:
                    state.near_t2_alerted = True
                    pnl_pct = self._calc_pnl_pct(trade.entry_price, current_price)
                    alert = ExitAlert(
                        trade=trade,
                        exit_type=None,
                        current_price=current_price,
                        pnl_pct=pnl_pct,
                        is_alert_only=True,
                        keyboard_type="near_t2",
                    )
                    logger.info(
                        "Near-T2 alert for trade %d (%s): price=%.2f (%.2f%% from T2)",
                        trade.id, trade.symbol, current_price, t2_distance_pct,
                    )
                    await self._alert_callback(alert)
                    return alert

            # Check T1 hit (advisory, once only)
            if current_price >= trade.target_1 and not state.t1_alerted:
                state.t1_alerted = True
                pnl_pct = self._calc_pnl_pct(trade.entry_price, current_price)
                alert = ExitAlert(
                    trade=trade,
                    exit_type=ExitType.T1_HIT,
                    current_price=current_price,
                    pnl_pct=pnl_pct,
                    is_alert_only=True,
                    keyboard_type="t1",
                )
                logger.info(
                    "T1 advisory for trade %d (%s): price=%.2f",
                    trade.id, trade.symbol, current_price,
                )
                await self._emit_alert(alert)
                return alert

            # Send trailing SL update alert if one occurred
            if trailing_alert is not None:
                await self._emit_alert(trailing_alert)
                return trailing_alert

            # Check SL approaching (within 0.5% of current SL, 60s cooldown)
            if state.current_sl > 0:
                sl_distance_pct = ((current_price - state.current_sl) / state.current_sl) * 100
                if 0 < sl_distance_pct <= 0.5:
                    now = datetime.now(IST)
                    cooldown_ok = (
                        state.sl_approaching_alerted_at is None
                        or (now - state.sl_approaching_alerted_at).total_seconds() >= 60
                    )
                    if cooldown_ok:
                        state.sl_approaching_alerted_at = now
                        pnl_pct = self._calc_pnl_pct(trade.entry_price, current_price)
                        alert = ExitAlert(
                            trade=trade,
                            exit_type=None,
                            current_price=current_price,
                            pnl_pct=pnl_pct,
                            is_alert_only=True,
                            keyboard_type="sl_approaching",
                        )
                        logger.info(
                            "SL-approaching alert for trade %d (%s): price=%.2f (%.2f%% from SL)",
                            trade.id, trade.symbol, current_price, sl_distance_pct,
                        )
                        await self._alert_callback(alert)
                        return alert

            return None

    def _update_trailing_stop(
        self,
        trade: TradeRecord,
        state: TrailingStopState,
        current_price: float,
    ) -> ExitAlert | None:
        """Update trailing stop loss based on current price using per-strategy config.

        - At +breakeven_trigger_pct above entry: SL moves to entry (breakeven)
        - At +trail_trigger_pct above entry: SL trails at trail_distance below current
        - Trailing SL never moves down
        - If trail_trigger_pct is None, only breakeven is applied (no trailing)
        """
        config = self._get_config_for_trade(trade)
        move_pct = self._calc_pnl_pct(trade.entry_price, current_price)

        # Trailing logic (check first since it supersedes breakeven)
        if (
            config.trail_trigger_pct is not None
            and config.trail_distance_pct is not None
            and move_pct >= config.trail_trigger_pct
        ):
            state.breakeven_triggered = True
            trail_factor = 1.0 - config.trail_distance_pct / 100.0
            new_sl = current_price * trail_factor
            if new_sl > state.current_sl:
                state.current_sl = new_sl
                state.trailing_active = True
                logger.info(
                    "Trailing SL update for trade %d (%s): new_sl=%.2f",
                    trade.id, trade.symbol, new_sl,
                )
                return ExitAlert(
                    trade=trade,
                    exit_type=None,
                    current_price=current_price,
                    pnl_pct=move_pct,
                    is_alert_only=True,
                    trailing_sl_update=new_sl,
                )

        # Breakeven logic
        elif move_pct >= config.breakeven_trigger_pct and not state.breakeven_triggered:
            state.current_sl = trade.entry_price
            state.breakeven_triggered = True
            logger.info(
                "Breakeven SL for trade %d (%s): new_sl=%.2f",
                trade.id, trade.symbol, trade.entry_price,
            )
            return ExitAlert(
                trade=trade,
                exit_type=None,
                current_price=current_price,
                pnl_pct=move_pct,
                is_alert_only=True,
                trailing_sl_update=trade.entry_price,
            )

        return None

    async def trigger_time_exit(
        self,
        trades: list[TradeRecord],
        is_mandatory: bool,
    ) -> list[ExitAlert]:
        """Handle time-based exits.

        At 3:00 PM (is_mandatory=False): send advisory alerts with current P&L.
        At 3:15 PM (is_mandatory=True): trigger actual exit for all open trades.
        """
        alerts: list[ExitAlert] = []
        for trade in trades:
            async with log_context(symbol=trade.symbol):
                tick = await self._get_tick(trade.symbol)
                if tick is None:
                    continue
                current_price = tick.ltp
                pnl_pct = self._calc_pnl_pct(trade.entry_price, current_price)

                if is_mandatory:
                    alert = self._build_exit_alert(trade, current_price, ExitType.TIME_EXIT)
                    logger.info(
                        "Mandatory time exit for trade %d (%s): price=%.2f",
                        trade.id, trade.symbol, current_price,
                    )
                    self.stop_monitoring(trade.id)
                    await self._persist_exit(
                        trade, current_price, pnl_pct, ExitType.TIME_EXIT.value,
                    )
                else:
                    alert = ExitAlert(
                        trade=trade,
                        exit_type=ExitType.TIME_EXIT,
                        current_price=current_price,
                        pnl_pct=pnl_pct,
                        is_alert_only=True,
                    )
                    logger.info(
                        "Time exit advisory for trade %d (%s): price=%.2f, pnl=%.2f%%",
                        trade.id, trade.symbol, current_price, pnl_pct,
                    )

                await self._emit_alert(alert)
                alerts.append(alert)

        return alerts

    async def _emit_alert(self, alert: ExitAlert) -> None:
        """Send an exit alert via event bus or legacy callback."""
        if self._event_bus is not None:
            from signalpilot.events import ExitAlertEvent

            await self._event_bus.emit(ExitAlertEvent(alert=alert))
        else:
            await self._alert_callback(alert)

    @staticmethod
    def _calc_pnl_pct(entry_price: float, current_price: float) -> float:
        """Calculate P&L percentage."""
        return ((current_price - entry_price) / entry_price) * 100

    @staticmethod
    def _build_exit_alert(
        trade: TradeRecord,
        current_price: float,
        exit_type: ExitType,
    ) -> ExitAlert:
        """Build an ExitAlert for an actual exit (not advisory)."""
        pnl_pct = ExitMonitor._calc_pnl_pct(trade.entry_price, current_price)
        return ExitAlert(
            trade=trade,
            exit_type=exit_type,
            current_price=current_price,
            pnl_pct=pnl_pct,
            is_alert_only=False,
        )
