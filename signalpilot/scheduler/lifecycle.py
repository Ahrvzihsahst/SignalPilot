"""Application lifecycle orchestrator."""

import asyncio
import logging
import uuid
from datetime import datetime

from signalpilot.db.models import (
    FinalSignal,
    HistoricalReference,
    HybridScoreRecord,
    SignalRecord,
    UserConfig,
)
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
        strategy=None,
        strategies: list | None = None,
        ranker,
        risk_manager,
        exit_monitor,
        bot,
        scheduler,
        duplicate_checker=None,
        capital_allocator=None,
        strategy_performance_repo=None,
        app_config=None,
        # Phase 3 components (all default to None for backward compatibility)
        confidence_detector=None,
        composite_scorer=None,
        adaptive_manager=None,
        circuit_breaker=None,
        hybrid_score_repo=None,
        circuit_breaker_repo=None,
        adaptation_log_repo=None,
        dashboard_app=None,
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
        # Support both single strategy (Phase 1 compat) and list (Phase 2)
        if strategies is not None:
            self._strategies = strategies
        elif strategy is not None:
            self._strategies = [strategy]
        else:
            self._strategies = []
        self._strategy = strategy  # backward compat for tests
        self._ranker = ranker
        self._risk_manager = risk_manager
        self._exit_monitor = exit_monitor
        self._bot = bot
        self._scheduler = scheduler
        self._duplicate_checker = duplicate_checker
        self._capital_allocator = capital_allocator
        self._strategy_performance_repo = strategy_performance_repo
        self._app_config = app_config
        # Phase 3
        self._confidence_detector = confidence_detector
        self._composite_scorer = composite_scorer
        self._adaptive_manager = adaptive_manager
        self._circuit_breaker = circuit_breaker
        self._hybrid_score_repo = hybrid_score_repo
        self._circuit_breaker_repo = circuit_breaker_repo
        self._adaptation_log_repo = adaptation_log_repo
        self._dashboard_app = dashboard_app
        # Internal state
        self._scanning = False
        self._accepting_signals = True
        self._scan_task: asyncio.Task | None = None
        self._max_consecutive_errors = 10
        self._fetch_cooldown = 5  # seconds between prev-day and ADV fetch passes

    async def startup(self) -> None:
        """Full startup sequence."""
        logger.info("Starting SignalPilot...")
        await self._db.initialize()
        if self._authenticator:
            await self._authenticator.authenticate()
        if self._instruments:
            await self._instruments.load()
        if self._historical:
            await self._load_historical_data()
        if self._config_repo:
            await self._config_repo.initialize_default(
                telegram_chat_id="",
            )
        if self._bot:
            await self._bot.start()
        self._scheduler.configure_jobs(self)
        self._scheduler.start()
        logger.info("SignalPilot startup complete")

    async def _load_historical_data(self) -> None:
        """Fetch previous-day OHLCV + ADV and store as HistoricalReferences.

        The two fetches run sequentially with a cooldown between them because
        they share the same Angel One rate limit.
        """
        prev_data = await self._historical.fetch_previous_day_data()

        # Cooldown: let Angel One's per-minute rate window reset before ADV pass
        reset_fn = getattr(self._historical, "reset_rate_limiter", None)
        if self._fetch_cooldown > 0 and reset_fn and not asyncio.iscoroutinefunction(reset_fn):
            logger.info("Cooling down %ds before ADV fetch...", self._fetch_cooldown)
            reset_fn()
            await asyncio.sleep(self._fetch_cooldown)

        adv_data = await self._historical.fetch_average_daily_volume()

        # Build HistoricalReference objects and store in MarketDataStore
        loaded = 0
        for symbol, prev in prev_data.items():
            adv = adv_data.get(symbol)
            if adv is None:
                continue
            ref = HistoricalReference(
                previous_close=prev.close,
                previous_high=prev.high,
                average_daily_volume=adv,
            )
            await self._market_data.set_historical(symbol, ref)
            loaded += 1

        logger.info(
            "Loaded historical references for %d/%d instruments",
            loaded,
            len(prev_data),
        )

    async def start_scanning(self) -> None:
        """Begin the continuous scanning loop (called at 9:15 AM)."""
        set_context(job_name="start_scanning")
        try:
            if not self._websocket:
                logger.warning("Skipping scan start: websocket component not configured")
                return

            # Reset per-session state so yesterday's data doesn't bleed over.
            await self._reset_session()

            # Phase 3: Daily resets for circuit breaker and adaptive manager
            if self._circuit_breaker is not None:
                self._circuit_breaker.reset_daily()
                logger.info("Circuit breaker daily reset")
            if self._adaptive_manager is not None:
                self._adaptive_manager.reset_daily()
                logger.info("Adaptive manager daily reset")

            logger.info("Starting market scanning")
            await self._websocket.connect()
            self._scanning = True
            self._accepting_signals = True
            self._scan_task = asyncio.create_task(self._scan_loop())
        finally:
            reset_context()

    async def lock_opening_ranges(self) -> None:
        """Lock opening ranges for all symbols (called at 9:45 AM).

        After this, ORB breakout detection can begin because the 30-minute
        opening range (9:15-9:45) is finalized.
        """
        set_context(job_name="lock_opening_ranges")
        try:
            if self._market_data:
                await self._market_data.lock_opening_ranges()
                logger.info("Opening ranges locked for ORB detection")
        finally:
            reset_context()

    async def _reset_session(self) -> None:
        """Reset all intraday state at the start of a new trading session.

        Clears:
        - Strategy per-day state (gap candidates, signal sets, cooldowns)
        - MarketDataStore session data (ticks, VWAP, candles, opening ranges)
        - WebSocket volume-tracking counters
        Historical references are preserved.
        """
        # Reset strategies
        for strat in self._strategies:
            if hasattr(strat, "reset"):
                strat.reset()
                logger.info("Reset strategy: %s", strat.name)

        # Clear intraday market data (keep historical references)
        if self._market_data and hasattr(self._market_data, "clear_session"):
            await self._market_data.clear_session()
            logger.info("Cleared intraday market data")

        # Reset WebSocket volume tracking
        if self._websocket and hasattr(self._websocket, "reset_volume_tracking"):
            self._websocket.reset_volume_tracking()

    async def _scan_loop(self) -> None:
        """Main scanning loop. Runs every second while active.

        Phase 3 integration points (all guarded by None checks):
        1. Circuit breaker check at start of each iteration
        2. Confidence detection on candidates
        3. Composite scoring
        4. Adaptive filtering
        5. Composite scores passed to ranker
        6. Confirmation map passed to risk manager
        7. Phase 3 fields persisted on signal records
        """
        consecutive_errors = 0
        _diag_cycle_count = 0
        while self._scanning:
            cycle_id = uuid.uuid4().hex[:8]
            try:
                now = datetime.now(IST)
                phase = get_current_phase(now)
                set_context(cycle_id=cycle_id, phase=phase.value)

                # Phase 3: Check circuit breaker at start of each cycle
                if self._circuit_breaker is not None and self._circuit_breaker.is_active:
                    # Circuit breaker active -- skip signal generation but
                    # continue exit monitoring
                    self._accepting_signals = False

                if self._accepting_signals and phase in (
                    StrategyPhase.OPENING,
                    StrategyPhase.ENTRY_WINDOW,
                    StrategyPhase.CONTINUOUS,
                ):
                    user_config = await self._config_repo.get_user_config()
                    enabled_strategies = self._get_enabled_strategies(user_config)

                    all_candidates = []
                    for strat in enabled_strategies:
                        if phase in strat.active_phases:
                            candidates = await strat.evaluate(self._market_data, phase)
                            if candidates:
                                all_candidates.extend(candidates)

                    # Exclude Gap & Go stocks from ORB scanning
                    gap_symbols = {
                        c.symbol
                        for c in all_candidates
                        if getattr(c, "strategy_name", None) == "Gap & Go"
                    }
                    if gap_symbols:
                        for strat in enabled_strategies:
                            if hasattr(strat, "mark_gap_stock"):
                                for sym in gap_symbols:
                                    strat.mark_gap_stock(sym)

                    if all_candidates:
                        # Deduplicate across strategies
                        if self._duplicate_checker:
                            all_candidates = await self._duplicate_checker.filter_duplicates(
                                all_candidates, now.date()
                            )

                        if all_candidates:
                            # Phase 3: Run confidence detection
                            confirmation_map = None
                            composite_scores = None

                            if self._confidence_detector is not None:
                                confirmation_results = (
                                    await self._confidence_detector.detect_confirmations(
                                        all_candidates, now
                                    )
                                )
                                # Build symbol -> ConfirmationResult map
                                confirmation_map = {}
                                for candidate, conf_result in confirmation_results:
                                    confirmation_map[candidate.symbol] = conf_result

                            # Phase 3: Run composite scoring
                            if self._composite_scorer is not None:
                                composite_scores = {}
                                for candidate in all_candidates:
                                    # Get confirmation for this candidate
                                    conf = None
                                    if confirmation_map is not None:
                                        conf = confirmation_map.get(candidate.symbol)
                                    if conf is None:
                                        from signalpilot.ranking.confidence import (
                                            ConfirmationResult,
                                        )
                                        conf = ConfirmationResult(
                                            confirmation_level="single",
                                            confirmed_by=[candidate.strategy_name],
                                        )
                                    score_result = await self._composite_scorer.score(
                                        candidate, conf, now.date()
                                    )
                                    composite_scores[candidate.symbol] = score_result

                            # Phase 3: Adaptive filtering
                            if self._adaptive_manager is not None:
                                filtered = []
                                for candidate in all_candidates:
                                    # Need to estimate signal strength for filtering
                                    strength = 3  # default
                                    if composite_scores and candidate.symbol in composite_scores:
                                        cs = composite_scores[candidate.symbol].composite_score
                                        if cs >= 80:
                                            strength = 5
                                        elif cs >= 65:
                                            strength = 4
                                        elif cs >= 50:
                                            strength = 3
                                        elif cs >= 35:
                                            strength = 2
                                        else:
                                            strength = 1
                                    if self._adaptive_manager.should_allow_signal(
                                        candidate.strategy_name, strength
                                    ):
                                        filtered.append(candidate)
                                    else:
                                        logger.info(
                                            "Adaptive filter blocked %s (%s)",
                                            candidate.symbol, candidate.strategy_name,
                                        )
                                all_candidates = filtered

                            if all_candidates:
                                # Pass composite scores and confirmations to ranker
                                ranked = self._ranker.rank(
                                    all_candidates,
                                    composite_scores=composite_scores,
                                    confirmations=confirmation_map,
                                )
                                active_count = await self._trade_repo.get_active_trade_count()
                                final_signals = self._risk_manager.filter_and_size(
                                    ranked,
                                    user_config,
                                    active_count,
                                    confirmation_map=confirmation_map,
                                )
                                for signal in final_signals:
                                    record = self._signal_to_record(signal, now)
                                    is_paper = self._is_paper_mode(signal, self._app_config)
                                    if is_paper:
                                        record.status = "paper"

                                    # Phase 3: Persist composite score and confirmation fields
                                    conf_level = None
                                    conf_by = None
                                    boosted_stars = None
                                    sym = signal.ranked_signal.candidate.symbol

                                    if composite_scores and sym in composite_scores:
                                        cs = composite_scores[sym]
                                        record.composite_score = cs.composite_score
                                        set_context(
                                            cycle_id=cycle_id,
                                            phase=phase.value,
                                            symbol=sym,
                                        )

                                    if confirmation_map and sym in confirmation_map:
                                        conf = confirmation_map[sym]
                                        record.confirmation_level = conf.confirmation_level
                                        record.confirmed_by = ",".join(conf.confirmed_by)
                                        record.position_size_multiplier = conf.position_size_multiplier
                                        conf_level = conf.confirmation_level
                                        conf_by = ",".join(conf.confirmed_by)
                                        if conf.star_boost > 0:
                                            boosted_stars = min(
                                                signal.ranked_signal.signal_strength + conf.star_boost, 5
                                            )

                                    if self._adaptive_manager is not None:
                                        state = self._adaptive_manager.get_all_states().get(
                                            signal.ranked_signal.candidate.strategy_name
                                        )
                                        if state is not None:
                                            record.adaptation_status = state.level.value

                                    signal_id = await self._signal_repo.insert_signal(record)
                                    record.id = signal_id

                                    # Phase 3: Persist hybrid score record
                                    if (
                                        self._hybrid_score_repo is not None
                                        and composite_scores
                                        and sym in composite_scores
                                    ):
                                        cs = composite_scores[sym]
                                        hs_record = HybridScoreRecord(
                                            signal_id=signal_id,
                                            composite_score=cs.composite_score,
                                            strategy_strength_score=cs.strategy_strength_score,
                                            win_rate_score=cs.win_rate_score,
                                            risk_reward_score=cs.risk_reward_score,
                                            confirmation_bonus=cs.confirmation_bonus,
                                            confirmed_by=conf_by,
                                            confirmation_level=conf_level or "single",
                                            position_size_multiplier=(
                                                confirmation_map[sym].position_size_multiplier
                                                if confirmation_map and sym in confirmation_map
                                                else 1.0
                                            ),
                                            created_at=now,
                                        )
                                        try:
                                            await self._hybrid_score_repo.insert_score(hs_record)
                                        except Exception:
                                            logger.warning(
                                                "Failed to persist hybrid score for signal %d",
                                                signal_id,
                                            )

                                    await self._bot.send_signal(
                                        signal,
                                        is_paper=is_paper,
                                        signal_id=signal_id,
                                        confirmation_level=conf_level,
                                        confirmed_by=conf_by,
                                        boosted_stars=boosted_stars,
                                    )
                                    logger.info(
                                        "Signal %s for %s (id=%d, composite_score=%s, confirmation=%s)",
                                        "paper-sent" if is_paper else "sent",
                                        record.symbol,
                                        signal_id,
                                        record.composite_score,
                                        record.confirmation_level or "single",
                                    )

                    # Periodic diagnostic: log when scanning is active but
                    # producing no candidates (every 60 cycles ~ 1 minute).
                    _diag_cycle_count += 1
                    if _diag_cycle_count % 60 == 0:
                        ws_ok = (
                            self._websocket.is_connected
                            if self._websocket
                            else False
                        )
                        logger.info(
                            "Scan heartbeat: phase=%s strategies=%d ws_connected=%s "
                            "candidates_this_cycle=%d",
                            phase.value,
                            len(enabled_strategies),
                            ws_ok,
                            len(all_candidates),
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
            if self._historical:
                await self._load_historical_data()
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

            # Respect signal cutoff if recovering after CONTINUOUS phase
            now = datetime.now(IST)
            phase = get_current_phase(now)
            if phase not in (
                StrategyPhase.OPENING,
                StrategyPhase.ENTRY_WINDOW,
                StrategyPhase.CONTINUOUS,
            ):
                self._accepting_signals = False
                logger.info("Recovery after signal cutoff; new signals disabled")

            logger.info(
                "Crash recovery complete, %d active trades restored", len(active_trades)
            )
        finally:
            reset_context()

    async def run_weekly_rebalance(self) -> None:
        """Weekly capital rebalancing (called Sunday 18:00 IST)."""
        set_context(job_name="weekly_rebalance")
        try:
            if not self._capital_allocator or not self._config_repo:
                logger.warning("Skipping weekly rebalance: allocator or config not configured")
                return

            user_config = await self._config_repo.get_user_config()
            if user_config is None:
                logger.warning("Skipping weekly rebalance: no user config")
                return

            today = datetime.now(IST).date()
            allocations = await self._capital_allocator.calculate_allocations(
                user_config.total_capital, user_config.max_positions, today
            )

            # Check for auto-pause recommendations
            pause_list = await self._capital_allocator.check_auto_pause(today)
            for strategy_name in pause_list:
                logger.warning("Auto-pause recommended for %s (win rate < 40%%)", strategy_name)

            if self._bot:
                from signalpilot.telegram.formatters import format_allocation_summary

                message = format_allocation_summary(allocations)
                await self._bot.send_alert(message)

                if pause_list:
                    pause_msg = (
                        "Auto-pause recommended for: "
                        + ", ".join(pause_list)
                        + ". Use PAUSE <strategy> to disable."
                    )
                    await self._bot.send_alert(pause_msg)

            logger.info("Weekly rebalance complete: %d strategies allocated", len(allocations))
        finally:
            reset_context()

    async def _expire_stale_signals(self) -> None:
        """Expire signals past their expiry time."""
        now = datetime.now(IST)
        count = await self._signal_repo.expire_stale_signals(now)
        if count > 0:
            logger.info("Expired %d stale signals", count)

    def _get_enabled_strategies(self, user_config: UserConfig | None) -> list:
        """Filter strategies by the corresponding enabled flag in user_config."""
        if not self._strategies:
            return []
        if user_config is None:
            return list(self._strategies)

        enabled = []
        strategy_flag_map = {
            "Gap & Go": "gap_go_enabled",
            "gap_go": "gap_go_enabled",
            "ORB": "orb_enabled",
            "VWAP Reversal": "vwap_enabled",
        }
        for strat in self._strategies:
            flag = strategy_flag_map.get(strat.name, None)
            if flag is None or getattr(user_config, flag, True):
                enabled.append(strat)
        return enabled

    @staticmethod
    def _is_paper_mode(signal: FinalSignal, app_config) -> bool:
        """Check if the signal's strategy is in paper trading mode.

        Paper mode is determined by the per-strategy paper_mode flags on the
        AppConfig (loaded from .env).  Gap & Go is never paper-traded because
        it was validated in Phase 1.
        """
        strategy_name = signal.ranked_signal.candidate.strategy_name
        if strategy_name == "ORB" and getattr(app_config, "orb_paper_mode", False):
            return True
        if strategy_name == "VWAP Reversal" and getattr(app_config, "vwap_paper_mode", False):
            return True
        return False

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
            setup_type=c.setup_type,
            strategy_specific_score=c.strategy_specific_score,
        )
