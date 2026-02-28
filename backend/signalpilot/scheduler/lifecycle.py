"""Application lifecycle orchestrator."""

import asyncio
import logging
import uuid
from datetime import datetime

from signalpilot.db.models import (
    FinalSignal,
    HistoricalReference,
    SignalRecord,
    UserConfig,
)
from signalpilot.pipeline.context import ScanContext
from signalpilot.pipeline.stage import ScanPipeline
from signalpilot.pipeline.stages.adaptive_filter import AdaptiveFilterStage
from signalpilot.pipeline.stages.circuit_breaker_gate import CircuitBreakerGateStage
from signalpilot.pipeline.stages.composite_scoring import CompositeScoringStage
from signalpilot.pipeline.stages.confidence import ConfidenceStage
from signalpilot.pipeline.stages.deduplication import DeduplicationStage
from signalpilot.pipeline.stages.diagnostic import DiagnosticStage
from signalpilot.pipeline.stages.exit_monitoring import ExitMonitoringStage
from signalpilot.pipeline.stages.gap_stock_marking import GapStockMarkingStage
from signalpilot.pipeline.stages.news_sentiment import NewsSentimentStage
from signalpilot.pipeline.stages.persist_and_deliver import PersistAndDeliverStage
from signalpilot.pipeline.stages.ranking import RankingStage
from signalpilot.pipeline.stages.regime_context import RegimeContextStage
from signalpilot.pipeline.stages.risk_sizing import RiskSizingStage
from signalpilot.pipeline.stages.strategy_eval import StrategyEvalStage
from signalpilot.telegram.formatters import format_daily_summary, format_signal_actions_summary
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
        watchlist_repo=None,
        signal_action_repo=None,
        # Phase 3 components (all default to None for backward compatibility)
        confidence_detector=None,
        composite_scorer=None,
        adaptive_manager=None,
        circuit_breaker=None,
        hybrid_score_repo=None,
        circuit_breaker_repo=None,
        adaptation_log_repo=None,
        dashboard_app=None,
        # Phase 4: News Sentiment Filter
        news_sentiment_service=None,
        earnings_repo=None,
        earnings_calendar=None,
        news_sentiment_repo=None,
        # Phase 4: Market Regime Detection
        regime_classifier=None,
        regime_data_collector=None,
        regime_repo=None,
        regime_performance_repo=None,
        morning_brief_generator=None,
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
        self._watchlist_repo = watchlist_repo
        self._signal_action_repo = signal_action_repo
        # Phase 3
        self._confidence_detector = confidence_detector
        self._composite_scorer = composite_scorer
        self._adaptive_manager = adaptive_manager
        self._circuit_breaker = circuit_breaker
        self._hybrid_score_repo = hybrid_score_repo
        self._circuit_breaker_repo = circuit_breaker_repo
        self._adaptation_log_repo = adaptation_log_repo
        self._dashboard_app = dashboard_app
        # Phase 4: News Sentiment Filter
        self._news_sentiment_service = news_sentiment_service
        self._earnings_repo = earnings_repo
        self._earnings_calendar = earnings_calendar
        self._news_sentiment_repo = news_sentiment_repo
        # Phase 4: Market Regime Detection
        self._regime_classifier = regime_classifier
        self._regime_data_collector = regime_data_collector
        self._regime_repo = regime_repo
        self._regime_performance_repo = regime_performance_repo
        self._morning_brief_generator = morning_brief_generator
        # Internal state
        self._scanning = False
        self._accepting_signals = True
        self._scan_task: asyncio.Task | None = None
        self._max_consecutive_errors = 10
        self._fetch_cooldown = 5  # seconds between prev-day and ADV fetch passes
        self._pipeline: ScanPipeline | None = None

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

            # Phase 4: Regime detection daily reset
            if self._regime_classifier is not None:
                self._regime_classifier.reset_daily()
                logger.info("Regime classifier daily reset")

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

        # Phase 4: Reset regime data collector session
        if self._regime_data_collector and hasattr(self._regime_data_collector, "reset_session"):
            self._regime_data_collector.reset_session()

    def _build_pipeline(self) -> ScanPipeline:
        """Construct the composable scan pipeline from injected components."""
        signal_stages = [
            CircuitBreakerGateStage(self._circuit_breaker),
            RegimeContextStage(self._regime_classifier, self._app_config),
            StrategyEvalStage(self._strategies, self._config_repo, self._market_data),
            GapStockMarkingStage(),
            DeduplicationStage(self._duplicate_checker),
            ConfidenceStage(self._confidence_detector),
            CompositeScoringStage(self._composite_scorer),
            AdaptiveFilterStage(self._adaptive_manager),
            RankingStage(self._ranker),
            NewsSentimentStage(
                self._news_sentiment_service,
                self._earnings_repo,
                self._app_config,
            ),
            RiskSizingStage(self._risk_manager, self._trade_repo),
            PersistAndDeliverStage(
                self._signal_repo,
                self._hybrid_score_repo,
                self._bot,
                self._adaptive_manager,
                self._app_config,
            ),
            DiagnosticStage(self._websocket),
        ]
        always_stages = [
            ExitMonitoringStage(self._trade_repo, self._exit_monitor, self._signal_repo),
        ]
        return ScanPipeline(signal_stages=signal_stages, always_stages=always_stages)

    async def _scan_loop(self) -> None:
        """Main scanning loop. Runs every second while active.

        Delegates to composable pipeline stages for signal generation,
        exit monitoring, and diagnostics.
        """
        # Build pipeline lazily so test mutations to app attributes are captured
        if self._pipeline is None:
            self._pipeline = self._build_pipeline()

        consecutive_errors = 0
        while self._scanning:
            cycle_id = uuid.uuid4().hex[:8]
            try:
                now = datetime.now(IST)
                phase = get_current_phase(now)
                set_context(cycle_id=cycle_id, phase=phase.value)

                ctx = ScanContext(
                    cycle_id=cycle_id,
                    now=now,
                    phase=phase,
                    accepting_signals=self._accepting_signals,
                )
                ctx = await self._pipeline.run(ctx)

                # Propagate circuit-breaker gate back to app-level state
                self._accepting_signals = ctx.accepting_signals

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
            now = datetime.now(IST)
            summary = await self._metrics.calculate_daily_summary(today)
            message = format_daily_summary(summary)

            # Append button analytics if available
            if self._signal_action_repo:
                action_summary = await self._signal_action_repo.get_action_summary(today)
                if action_summary:
                    avg_ms = await self._signal_action_repo.get_average_response_time(1)
                    avg_s = avg_ms / 1000.0 if avg_ms else None
                    skip_reasons = await self._signal_action_repo.get_skip_reason_distribution(1)
                    total_signals = summary.signals_sent if summary else 0
                    taken = action_summary.get("taken", 0)
                    skipped = action_summary.get("skip", 0)
                    watched = action_summary.get("watch", 0)
                    no_action = max(0, total_signals - taken - skipped - watched)
                    actions_section = format_signal_actions_summary(
                        taken, skipped, watched, no_action, avg_s, skip_reasons,
                    )
                    if actions_section:
                        message += actions_section

            await self._bot.send_alert(message)
            logger.info("Daily summary sent")

            # Phase 4: End-of-day news cleanup
            if self._news_sentiment_service is not None:
                try:
                    purged = await self._news_sentiment_service.purge_old_entries(48)
                    self._news_sentiment_service.clear_unsuppress_overrides()
                    if purged > 0:
                        logger.info("Purged %d old news entries", purged)
                except Exception:
                    logger.exception("Failed to purge news entries")

            # Phase 4: End-of-day regime performance tracking
            if self._regime_classifier is not None:
                classification = self._regime_classifier.get_cached_regime()
                if classification is not None:
                    regime_line = (
                        f"\nMarket Regime: {classification.regime}"
                        f" (confidence: {classification.confidence:.0%})"
                    )
                    message += regime_line

            # Cleanup expired watchlist entries
            if self._watchlist_repo:
                deleted = await self._watchlist_repo.cleanup_expired(now)
                if deleted > 0:
                    logger.info("Cleaned up %d expired watchlist entries", deleted)
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

    async def fetch_pre_market_news(self) -> None:
        """Fetch and analyze news for all stocks (called at 8:30 AM)."""
        set_context(job_name="fetch_pre_market_news")
        try:
            if not self._app_config or not getattr(self._app_config, "news_enabled", False):
                logger.info("News sentiment disabled, skipping pre-market fetch")
                return
            if self._news_sentiment_service is None:
                logger.warning("Skipping pre-market news: service not configured")
                return
            try:
                count = await self._news_sentiment_service.fetch_and_analyze_all()
                logger.info("Pre-market news fetch complete: %d headlines", count)
            except Exception:
                logger.exception("Pre-market news fetch failed; proceeding with NO_NEWS defaults")
        finally:
            reset_context()

    async def refresh_news_cache(self) -> None:
        """Refresh news cache for active symbols (called at 11:15 and 13:15)."""
        set_context(job_name="refresh_news_cache")
        try:
            if not self._app_config or not getattr(self._app_config, "news_enabled", False):
                return
            if self._news_sentiment_service is None:
                return
            try:
                count = await self._news_sentiment_service.fetch_and_analyze_stocks()
                logger.info("News cache refresh complete: %d headlines", count)
            except Exception:
                logger.exception("News cache refresh failed")
        finally:
            reset_context()

    # -- Phase 4: Market Regime Detection lifecycle methods

    async def send_morning_brief(self) -> None:
        """Generate and send the morning brief (called at 8:45 AM)."""
        set_context(job_name="send_morning_brief")
        try:
            if self._morning_brief_generator is None:
                logger.info("Morning brief generator not configured, skipping")
                return
            if not self._app_config or not getattr(self._app_config, "regime_enabled", False):
                logger.info("Regime detection disabled, skipping morning brief")
                return
            try:
                brief = await self._morning_brief_generator.generate()
                if self._bot:
                    await self._bot.send_alert(brief)
                logger.info("Morning brief sent")
            except Exception:
                logger.exception("Failed to generate/send morning brief")
        finally:
            reset_context()

    async def classify_regime(self) -> None:
        """Classify the market regime (called at 9:30 AM)."""
        set_context(job_name="classify_regime")
        try:
            if self._regime_classifier is None or self._regime_data_collector is None:
                logger.info("Regime classifier not configured, skipping")
                return
            if not self._app_config or not getattr(self._app_config, "regime_enabled", False):
                logger.info("Regime detection disabled, skipping classification")
                return
            try:
                classification = await self._regime_classifier.classify()

                # Send notification
                if self._bot:
                    from signalpilot.telegram.formatters import format_classification_notification
                    msg = format_classification_notification(classification)
                    await self._bot.send_alert(msg)

                logger.info(
                    "Regime classified: %s (confidence=%.2f)",
                    classification.regime, classification.confidence,
                )
            except Exception:
                logger.exception("Regime classification failed")
        finally:
            reset_context()

    async def check_regime_reclassify_11(self) -> None:
        """Check for regime re-classification (called at 11:00 AM)."""
        await self._check_regime_reclassify("regime_reclass_11")

    async def check_regime_reclassify_13(self) -> None:
        """Check for regime re-classification (called at 1:00 PM)."""
        await self._check_regime_reclassify("regime_reclass_13")

    async def check_regime_reclassify_1430(self) -> None:
        """Check for regime re-classification (called at 2:30 PM)."""
        await self._check_regime_reclassify("regime_reclass_1430")

    async def _check_regime_reclassify(self, job_name: str) -> None:
        """Internal helper for regime re-classification checks."""
        set_context(job_name=job_name)
        try:
            if self._regime_classifier is None or self._regime_data_collector is None:
                return
            if not self._app_config or not getattr(self._app_config, "regime_enabled", False):
                return
            try:
                checkpoint_map = {
                    "regime_reclass_11": "11:00",
                    "regime_reclass_13": "13:00",
                    "regime_reclass_1430": "14:30",
                }
                checkpoint = checkpoint_map.get(job_name, "")
                new_classification = await self._regime_classifier.check_reclassify(checkpoint)
                if new_classification is not None:
                    # Send notification
                    if self._bot:
                        from signalpilot.telegram.formatters import format_reclass_notification
                        msg = format_reclass_notification(new_classification)
                        await self._bot.send_alert(msg)

                    logger.info(
                        "Regime re-classified: %s -> %s",
                        new_classification.previous_regime,
                        new_classification.regime,
                    )
            except Exception:
                logger.exception("Regime re-classification check failed")
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

            # Phase 4: Refresh earnings calendar
            if self._earnings_calendar is not None:
                try:
                    count = await self._earnings_calendar.refresh()
                    logger.info("Earnings calendar refreshed: %d entries", count)
                except Exception:
                    logger.exception("Failed to refresh earnings calendar")
        finally:
            reset_context()

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
