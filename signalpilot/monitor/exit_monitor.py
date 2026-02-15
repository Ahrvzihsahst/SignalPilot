"""Exit monitor — checks active trades against exit conditions on every tick."""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from signalpilot.db.models import ExitAlert, ExitType, TickData, TradeRecord

logger = logging.getLogger(__name__)

# Type alias for the market data getter (async callable: symbol -> TickData | None)
MarketDataGetter = Callable[[str], Awaitable[TickData | None]]


@dataclass
class TrailingStopState:
    """Per-trade trailing stop loss state."""

    trade_id: int
    original_sl: float
    current_sl: float
    highest_price: float
    breakeven_triggered: bool = False
    trailing_active: bool = False
    t1_alerted: bool = False


class ExitMonitor:
    """Monitors active trades for exit conditions on every tick cycle.

    Exit conditions checked (in priority order):
    1. Stop loss / trailing stop loss hit
    2. Target 2 hit (full exit)
    3. Target 1 hit (advisory alert, trade stays open)
    4. Trailing SL updates (breakeven at configurable %, trail at configurable %)

    Note: Phase 1 supports BUY (long) trades only. All price comparisons
    and PnL calculations assume long direction.
    """

    def __init__(
        self,
        get_tick: MarketDataGetter,
        alert_callback: Callable[[ExitAlert], Awaitable[None]],
        breakeven_trigger_pct: float = 2.0,
        trail_trigger_pct: float = 4.0,
        trail_distance_pct: float = 2.0,
    ) -> None:
        self._get_tick = get_tick
        self._alert_callback = alert_callback
        self._breakeven_trigger_pct = breakeven_trigger_pct
        self._trail_trigger_pct = trail_trigger_pct
        self._trail_factor = 1.0 - trail_distance_pct / 100.0
        self._active_states: dict[int, TrailingStopState] = {}

    def start_monitoring(self, trade: TradeRecord) -> None:
        """Begin monitoring a trade by initializing its trailing stop state."""
        state = TrailingStopState(
            trade_id=trade.id,
            original_sl=trade.stop_loss,
            current_sl=trade.stop_loss,
            highest_price=trade.entry_price,
        )
        self._active_states[trade.id] = state
        logger.info("Started monitoring trade %d (%s)", trade.id, trade.symbol)

    def stop_monitoring(self, trade_id: int) -> None:
        """Stop monitoring a trade and clean up its state."""
        self._active_states.pop(trade_id, None)
        logger.info("Stopped monitoring trade %d", trade_id)

    async def check_trade(self, trade: TradeRecord) -> ExitAlert | None:
        """Check a single trade against all exit conditions.

        Returns the ExitAlert if an exit or advisory was triggered, None otherwise.
        """
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
            await self._alert_callback(alert)
            return alert

        # Check T2 hit (full exit)
        if current_price >= trade.target_2:
            alert = self._build_exit_alert(trade, current_price, ExitType.T2_HIT)
            logger.info(
                "T2 exit for trade %d (%s): price=%.2f", trade.id, trade.symbol, current_price,
            )
            self.stop_monitoring(trade.id)
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
            )
            logger.info(
                "T1 advisory for trade %d (%s): price=%.2f", trade.id, trade.symbol, current_price,
            )
            await self._alert_callback(alert)
            return alert

        # Send trailing SL update alert if one occurred
        if trailing_alert is not None:
            await self._alert_callback(trailing_alert)
            return trailing_alert

        return None

    def _update_trailing_stop(
        self,
        trade: TradeRecord,
        state: TrailingStopState,
        current_price: float,
    ) -> ExitAlert | None:
        """Update trailing stop loss based on current price.

        - At +breakeven_trigger_pct above entry: SL moves to entry (breakeven)
        - At +trail_trigger_pct above entry: SL trails at trail_distance below current
        - Trailing SL never moves down
        """
        move_pct = self._calc_pnl_pct(trade.entry_price, current_price)

        # Trailing logic (check first since it supersedes breakeven)
        if move_pct >= self._trail_trigger_pct:
            # Breakeven is implied once we reach trail trigger
            state.breakeven_triggered = True
            new_sl = current_price * self._trail_factor
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
        elif move_pct >= self._breakeven_trigger_pct and not state.breakeven_triggered:
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

            await self._alert_callback(alert)
            alerts.append(alert)

        return alerts

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
