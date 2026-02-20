"""Application lifecycle orchestrator."""

import asyncio
import logging
import uuid
from datetime import datetime

from signalpilot.db.models import FinalSignal, SignalRecord
from signalpilot.telegram.formatters import format_daily_summary
from signalpilot.utils.constants import IST
from signalpilot.utils.log_context import reset_context, set_context
from signalpilot.utils.market_calendar import StrategyPhase, get_current_phase

logger = logging.getLogger(__name__)


class SignalPilotApp:
    """Main application orchestrator. Owns all components and manages lifecycle."""

    def __init__(
        self,
        *,
        db,
        signal_repo,
        trade_repo,
        config_repo,
        metrics_calculator,
        authenticator,
        instruments,
        market_data,
        historical,
        websocket,
        strategy,
        ranker,
        risk_manager,
        exit_monitor,
        bot,
        scheduler,
    ) -> None:
        self._db = db
        self._signal_repo = signal_repo
        self._trade_repo = trade_repo
        self._config_repo = config_repo
        self._metrics = metrics_calculator
        self._authenticator = authenticator
        self._instruments = instruments
        self._market_data = market_data
        self._historical = historical
        self._websocket = websocket
        self._strategy = strategy
        self._ranker = ranker
        self._risk_manager = risk_manager
        self._exit_monitor = exit_monitor
        self._bot = bot
        self._scheduler = scheduler
        self._scanning = False
        self._accepting_signals = True
        self._scan_task: asyncio.Task | None = None
        self._max_consecutive_errors = 10

    async def startup(self) -> None:
        """Full startup sequence."""
        logger.info("Starting SignalPilot...")
        await self._db.initialize()
        if self._authenticator:
            await self._authenticator.authenticate()
        if self._instruments:
            await self._instruments.load()
        if self._historical:
            await self._historical.fetch_previous_day_data()
            await self._historical.fetch_average_daily_volume()
        if self._config_repo:
            await self._config_repo.initialize_default(
                telegram_chat_id="",
            )
        if self._bot:
            await self._bot.start()
        self._scheduler.configure_jobs(self)
        self._scheduler.start()
        logger.info("SignalPilot startup complete")

    async def start_scanning(self) -> None:
        """Begin the continuous scanning loop (called at 9:15 AM)."""
        set_context(job_name="start_scanning")
        try:
            if not self._websocket:
                logger.warning("Skipping scan start: websocket component not configured")
                return
            logger.info("Starting market scanning")
            await self._websocket.connect()
            self._scanning = True
            self._accepting_signals = True
            self._scan_task = asyncio.create_task(self._scan_loop())
        finally:
            reset_context()

    async def _scan_loop(self) -> None:
        """Main scanning loop. Runs every second while active."""
        consecutive_errors = 0
        while self._scanning:
            cycle_id = uuid.uuid4().hex[:8]
            try:
                now = datetime.now(IST)
                phase = get_current_phase(now)
                set_context(cycle_id=cycle_id, phase=phase.value)

                if self._accepting_signals and phase in (
                    StrategyPhase.OPENING,
                    StrategyPhase.ENTRY_WINDOW,
                ):
                    candidates = await self._strategy.evaluate(self._market_data, phase)
                    if candidates:
                        ranked = self._ranker.rank(candidates)
                        user_config = await self._config_repo.get_user_config()
                        active_count = await self._trade_repo.get_active_trade_count()
                        final_signals = self._risk_manager.filter_and_size(
                            ranked,
                            user_config,
                            active_count,
                        )
                        for signal in final_signals:
                            record = self._signal_to_record(signal, now)
                            signal_id = await self._signal_repo.insert_signal(record)
                            record.id = signal_id
                            await self._bot.send_signal(signal)
                            logger.info(
                                "Signal sent for %s (id=%d)", record.symbol, signal_id
                            )

                active_trades = await self._trade_repo.get_active_trades()
                for trade in active_trades:
                    await self._exit_monitor.check_trade(trade)
                await self._expire_stale_signals()
                consecutive_errors = 0

            except Exception:
                consecutive_errors += 1
                logger.exception(
                    "Error in scan loop iteration (%d consecutive)", consecutive_errors
                )
                if consecutive_errors >= self._max_consecutive_errors:
                    logger.critical(
                        "Too many consecutive errors (%d), stopping scan loop",
                        consecutive_errors,
                    )
                    self._scanning = False
                    try:
                        await self._bot.send_alert(
                            "ALERT: Scan loop stopped due to repeated errors. "
                            "Manual intervention required."
                        )
                    except Exception:
                        logger.exception("Failed to send circuit-breaker alert")
                    break
            finally:
                reset_context()

            await asyncio.sleep(1)

    async def stop_new_signals(self) -> None:
        """Stop generating new signals (called at 2:30 PM)."""
        set_context(job_name="stop_new_signals")
        try:
            self._accepting_signals = False
            if self._bot:
                await self._bot.send_alert(
                    "No new signals after 2:30 PM. Monitoring existing positions only."
                )
            logger.info("Signal generation stopped")
        finally:
            reset_context()

    async def send_pre_market_alert(self) -> None:
        """Send pre-market alert (called at 9:00 AM)."""
        set_context(job_name="send_pre_market_alert")
        try:
            if self._bot:
                await self._bot.send_alert(
                    "Pre-market scan running. Signals coming shortly after 9:15 AM."
                )
            logger.info("Pre-market alert sent")
        finally:
            reset_context()

    async def trigger_exit_reminder(self) -> None:
        """Send exit reminder (called at 3:00 PM)."""
        set_context(job_name="trigger_exit_reminder")
        try:
            active_trades = await self._trade_repo.get_active_trades()
            await self._exit_monitor.trigger_time_exit(active_trades, is_mandatory=False)
            if self._bot:
                await self._bot.send_alert(
                    "Market closing soon. Close all intraday positions in the next 15 minutes."
                )
            logger.info("Exit reminder sent")
        finally:
            reset_context()

    async def trigger_mandatory_exit(self) -> None:
        """Trigger mandatory exit (called at 3:15 PM)."""
        set_context(job_name="trigger_mandatory_exit")
        try:
            active_trades = await self._trade_repo.get_active_trades()
            await self._exit_monitor.trigger_time_exit(active_trades, is_mandatory=True)
            logger.info("Mandatory exit triggered")
        finally:
            reset_context()

    async def send_daily_summary(self) -> None:
        """Generate and send daily summary (called at 3:30 PM)."""
        set_context(job_name="send_daily_summary")
        try:
            if not self._metrics or not self._bot:
                logger.warning("Skipping daily summary: missing metrics or bot component")
                return
            today = datetime.now(IST).date()
            summary = await self._metrics.calculate_daily_summary(today)
            message = format_daily_summary(summary)
            await self._bot.send_alert(message)
            logger.info("Daily summary sent")
        finally:
            reset_context()

    async def shutdown(self) -> None:
        """Graceful shutdown sequence."""
        set_context(job_name="shutdown")
        try:
            logger.info("Shutting down SignalPilot...")
            self._scanning = False
            if self._scan_task and not self._scan_task.done():
                self._scan_task.cancel()
                try:
                    await self._scan_task
                except asyncio.CancelledError:
                    pass

            cleanup = [("db", self._db.close())]
            if self._websocket:
                cleanup.insert(0, ("websocket", self._websocket.disconnect()))
            if self._bot:
                cleanup.insert(-1, ("bot", self._bot.stop()))
            for name, coro in cleanup:
                try:
                    await coro
                except Exception:
                    logger.exception("Error shutting down %s", name)

            self._scheduler.shutdown()
            logger.info("SignalPilot shutdown complete")
        finally:
            reset_context()

    async def recover(self) -> None:
        """Crash recovery: re-auth, reconnect, reload today's state."""
        set_context(job_name="recover")
        try:
            logger.info("Starting crash recovery...")
            await self._db.initialize()
            if self._authenticator:
                await self._authenticator.authenticate()
            if self._instruments:
                await self._instruments.load()
            if self._trade_repo and self._exit_monitor:
                active_trades = await self._trade_repo.get_active_trades()
                for trade in active_trades:
                    self._exit_monitor.start_monitoring(trade)
            else:
                active_trades = []
            if self._bot:
                await self._bot.start()
                await self._bot.send_alert(
                    "System recovered from interruption. Monitoring resumed."
                )
            self._scheduler.configure_jobs(self)
            self._scheduler.start()
            if self._websocket:
                await self.start_scanning()

            # Respect signal cutoff if recovering after entry window
            now = datetime.now(IST)
            phase = get_current_phase(now)
            if phase not in (StrategyPhase.OPENING, StrategyPhase.ENTRY_WINDOW):
                self._accepting_signals = False
                logger.info("Recovery after entry window; new signals disabled")

            logger.info(
                "Crash recovery complete, %d active trades restored", len(active_trades)
            )
        finally:
            reset_context()

    async def _expire_stale_signals(self) -> None:
        """Expire signals past their expiry time."""
        now = datetime.now(IST)
        count = await self._signal_repo.expire_stale_signals(now)
        if count > 0:
            logger.info("Expired %d stale signals", count)

    @staticmethod
    def _signal_to_record(signal: FinalSignal, now: datetime) -> SignalRecord:
        """Convert a FinalSignal to a SignalRecord for database storage."""
        c = signal.ranked_signal.candidate
        return SignalRecord(
            date=now.date(),
            symbol=c.symbol,
            strategy=c.strategy_name,
            entry_price=c.entry_price,
            stop_loss=c.stop_loss,
            target_1=c.target_1,
            target_2=c.target_2,
            quantity=signal.quantity,
            capital_required=signal.capital_required,
            signal_strength=signal.ranked_signal.signal_strength,
            gap_pct=c.gap_pct,
            volume_ratio=c.volume_ratio,
            reason=c.reason,
            created_at=c.generated_at,
            expires_at=signal.expires_at,
            status="sent",
        )
