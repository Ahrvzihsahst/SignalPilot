"""SignalPilot application entry point."""

import asyncio
import logging
import signal as signal_module
from datetime import datetime

from signalpilot.config import AppConfig
from signalpilot.scheduler.lifecycle import SignalPilotApp
from signalpilot.scheduler.scheduler import MarketScheduler
from signalpilot.utils.constants import IST
from signalpilot.utils.logger import configure_logging
from signalpilot.utils.market_calendar import is_market_hours, is_trading_day

logger = logging.getLogger(__name__)


async def create_app(config: AppConfig) -> SignalPilotApp:
    """Wire all components together and return a SignalPilotApp."""
    from signalpilot.data.auth import SmartAPIAuthenticator
    from signalpilot.data.historical import HistoricalDataFetcher
    from signalpilot.data.instruments import InstrumentManager
    from signalpilot.data.market_data_store import MarketDataStore
    from signalpilot.data.websocket_client import WebSocketClient
    from signalpilot.db.adaptation_log_repo import AdaptationLogRepository
    from signalpilot.db.circuit_breaker_repo import CircuitBreakerRepository
    from signalpilot.db.config_repo import ConfigRepository
    from signalpilot.db.database import DatabaseManager
    from signalpilot.db.hybrid_score_repo import HybridScoreRepository
    from signalpilot.db.metrics import MetricsCalculator
    from signalpilot.db.models import ScoringWeights
    from signalpilot.db.signal_repo import SignalRepository
    from signalpilot.db.strategy_performance_repo import StrategyPerformanceRepository
    from signalpilot.db.trade_repo import TradeRepository
    from signalpilot.monitor.adaptive_manager import AdaptiveManager
    from signalpilot.monitor.circuit_breaker import CircuitBreaker
    from signalpilot.monitor.duplicate_checker import DuplicateChecker
    from signalpilot.monitor.exit_monitor import ExitMonitor
    from signalpilot.monitor.vwap_cooldown import VWAPCooldownTracker
    from signalpilot.ranking.composite_scorer import CompositeScorer
    from signalpilot.ranking.confidence import ConfidenceDetector
    from signalpilot.ranking.orb_scorer import ORBScorer
    from signalpilot.ranking.ranker import SignalRanker
    from signalpilot.ranking.scorer import SignalScorer
    from signalpilot.ranking.vwap_scorer import VWAPScorer
    from signalpilot.risk.capital_allocator import CapitalAllocator
    from signalpilot.risk.position_sizer import PositionSizer
    from signalpilot.risk.risk_manager import RiskManager
    from signalpilot.strategy.gap_and_go import GapAndGoStrategy
    from signalpilot.strategy.orb import ORBStrategy
    from signalpilot.strategy.vwap_reversal import VWAPReversalStrategy
    from signalpilot.telegram.bot import SignalPilotBot

    # --- Database (must initialize before repos) ---
    db = DatabaseManager(config.db_path)
    await db.initialize()
    connection = db.connection

    # --- Repositories ---
    signal_repo = SignalRepository(connection)
    trade_repo = TradeRepository(connection)
    config_repo = ConfigRepository(connection)
    metrics_calculator = MetricsCalculator(connection)

    # --- Phase 3 Repositories ---
    hybrid_score_repo = HybridScoreRepository(connection)
    circuit_breaker_repo = CircuitBreakerRepository(connection)
    adaptation_log_repo = AdaptationLogRepository(connection)

    # --- Data layer (no DB deps) ---
    authenticator = SmartAPIAuthenticator(config)
    instruments = InstrumentManager(config.nifty500_csv_path)
    market_data = MarketDataStore()
    historical = HistoricalDataFetcher(
        authenticator, instruments, config.historical_api_rate_limit
    )

    # --- Strategies ---
    gap_and_go = GapAndGoStrategy(config)
    orb = ORBStrategy(config, market_data)
    cooldown_tracker = VWAPCooldownTracker(
        max_signals_per_stock=config.vwap_max_signals_per_stock,
        cooldown_minutes=config.vwap_cooldown_minutes,
    )
    vwap = VWAPReversalStrategy(config, market_data, cooldown_tracker)

    # --- Cross-strategy deduplication ---
    duplicate_checker = DuplicateChecker(signal_repo, trade_repo)

    # --- Ranking (with strategy-specific scorers) ---
    weights = ScoringWeights(
        gap_pct_weight=config.scoring_gap_weight,
        volume_ratio_weight=config.scoring_volume_weight,
        price_distance_weight=config.scoring_price_distance_weight,
    )
    orb_scorer = ORBScorer(
        volume_weight=config.orb_scoring_volume_weight,
        range_weight=config.orb_scoring_range_weight,
        distance_weight=config.orb_scoring_distance_weight,
    )
    vwap_scorer = VWAPScorer(
        volume_weight=config.vwap_scoring_volume_weight,
        touch_weight=config.vwap_scoring_touch_weight,
        trend_weight=config.vwap_scoring_trend_weight,
    )
    scorer = SignalScorer(weights, orb_scorer=orb_scorer, vwap_scorer=vwap_scorer)
    ranker = SignalRanker(scorer, max_signals=config.default_max_positions)

    # --- Phase 3: Confidence detection & composite scoring ---
    confidence_detector = ConfidenceDetector(signal_repo=signal_repo)
    strategy_performance_repo = StrategyPerformanceRepository(connection)
    composite_scorer = CompositeScorer(
        signal_scorer=scorer,
        strategy_performance_repo=strategy_performance_repo,
    )

    # --- Strategy performance tracking & capital allocation ---
    capital_allocator = CapitalAllocator(
        strategy_performance_repo, config_repo,
        adaptation_log_repo=adaptation_log_repo,
    )

    # --- Risk ---
    position_sizer = PositionSizer()
    risk_manager = RiskManager(position_sizer)

    # --- Exit monitor (needs bot callback -- use closure to break cycle) ---
    bot_ref: list[SignalPilotBot | None] = [None]

    async def _exit_alert_callback(alert):
        if bot_ref[0] is not None:
            await bot_ref[0].send_exit_alert(alert)

    # Build per-strategy trailing stop configs from AppConfig
    from signalpilot.monitor.exit_monitor import TrailingStopConfig

    trailing_configs = {
        "Gap & Go": TrailingStopConfig(
            breakeven_trigger_pct=config.trailing_sl_breakeven_trigger_pct,
            trail_trigger_pct=config.trailing_sl_trail_trigger_pct,
            trail_distance_pct=config.trailing_sl_trail_distance_pct,
        ),
        "gap_go": TrailingStopConfig(
            breakeven_trigger_pct=config.trailing_sl_breakeven_trigger_pct,
            trail_trigger_pct=config.trailing_sl_trail_trigger_pct,
            trail_distance_pct=config.trailing_sl_trail_distance_pct,
        ),
        "ORB": TrailingStopConfig(
            breakeven_trigger_pct=config.orb_breakeven_trigger_pct,
            trail_trigger_pct=config.orb_trail_trigger_pct,
            trail_distance_pct=config.orb_trail_distance_pct,
        ),
        "VWAP Reversal": TrailingStopConfig(
            breakeven_trigger_pct=config.vwap_setup1_breakeven_trigger_pct,
            trail_trigger_pct=None,
            trail_distance_pct=None,
        ),
        "VWAP Reversal:uptrend_pullback": TrailingStopConfig(
            breakeven_trigger_pct=config.vwap_setup1_breakeven_trigger_pct,
            trail_trigger_pct=None,
            trail_distance_pct=None,
        ),
        "VWAP Reversal:vwap_reclaim": TrailingStopConfig(
            breakeven_trigger_pct=config.vwap_setup2_breakeven_trigger_pct,
            trail_trigger_pct=None,
            trail_distance_pct=None,
        ),
    }

    # Forward-declare circuit_breaker / adaptive_manager for exit monitor callbacks.
    # These closures capture the objects created below.
    circuit_breaker_ref: list[CircuitBreaker | None] = [None]
    adaptive_manager_ref: list[AdaptiveManager | None] = [None]

    async def _on_sl_hit(symbol: str, strategy: str, pnl_amount: float) -> None:
        if circuit_breaker_ref[0] is not None:
            await circuit_breaker_ref[0].on_sl_hit(symbol, strategy, pnl_amount)

    async def _on_trade_exit(strategy_name: str, is_loss: bool) -> None:
        if adaptive_manager_ref[0] is not None:
            today = datetime.now(IST).date()
            await adaptive_manager_ref[0].on_trade_exit(strategy_name, is_loss, today)

    exit_monitor = ExitMonitor(
        get_tick=market_data.get_tick,
        alert_callback=_exit_alert_callback,
        breakeven_trigger_pct=config.trailing_sl_breakeven_trigger_pct,
        trail_trigger_pct=config.trailing_sl_trail_trigger_pct,
        trail_distance_pct=config.trailing_sl_trail_distance_pct,
        trailing_configs=trailing_configs,
        close_trade=trade_repo.close_trade,
        on_sl_hit_callback=_on_sl_hit,
        on_trade_exit_callback=_on_trade_exit,
    )

    # --- Phase 3: Circuit breaker ---
    # Forward-declare app_ref for circuit breaker callback
    app_ref: list[SignalPilotApp | None] = [None]

    async def _circuit_break_callback(message: str):
        if bot_ref[0] is not None:
            await bot_ref[0].send_alert(message)

    circuit_breaker = CircuitBreaker(
        circuit_breaker_repo=circuit_breaker_repo,
        config_repo=config_repo,
        on_circuit_break=_circuit_break_callback,
        sl_limit=config.circuit_breaker_sl_limit,
    )
    circuit_breaker_ref[0] = circuit_breaker

    # --- Phase 3: Adaptive manager ---
    async def _adaptive_alert_callback(message: str):
        if bot_ref[0] is not None:
            await bot_ref[0].send_alert(message)

    adaptive_manager = AdaptiveManager(
        adaptation_log_repo=adaptation_log_repo,
        config_repo=config_repo,
        strategy_performance_repo=strategy_performance_repo,
        alert_callback=_adaptive_alert_callback,
    )
    adaptive_manager_ref[0] = adaptive_manager

    # --- Telegram bot ---
    # Wrapper: handle_status expects list[str] -> dict[str, float], but
    # market_data.get_tick takes a single str -> TickData | None.
    async def _get_current_prices(symbols: list[str]) -> dict[str, float]:
        prices: dict[str, float] = {}
        for sym in symbols:
            tick = await market_data.get_tick(sym)
            if tick is not None:
                prices[sym] = tick.ltp
        return prices

    bot = SignalPilotBot(
        bot_token=config.telegram_bot_token,
        chat_id=config.telegram_chat_id,
        signal_repo=signal_repo,
        trade_repo=trade_repo,
        config_repo=config_repo,
        metrics_calculator=metrics_calculator,
        exit_monitor=exit_monitor,
        get_current_prices=_get_current_prices,
        capital_allocator=capital_allocator,
        strategy_performance_repo=strategy_performance_repo,
        # Phase 3
        circuit_breaker=circuit_breaker,
        adaptive_manager=adaptive_manager,
        hybrid_score_repo=hybrid_score_repo,
        adaptation_log_repo=adaptation_log_repo,
    )
    bot_ref[0] = bot  # complete the circular reference

    # --- WebSocket ---
    websocket = WebSocketClient(
        authenticator=authenticator,
        instruments=instruments,
        market_data_store=market_data,
        on_disconnect_alert=bot.send_alert,
        max_reconnect_attempts=config.ws_max_reconnect_attempts,
    )

    # --- Scheduler ---
    scheduler = MarketScheduler()

    # --- Dashboard (optional) ---
    dashboard_app = None
    if config.dashboard_enabled:
        try:
            from signalpilot.dashboard.app import create_dashboard_app
            dashboard_app = create_dashboard_app(
                db_path=config.db_path,
                write_connection=connection,
            )
        except ImportError:
            logger.info("Dashboard module not available, skipping")

    app = SignalPilotApp(
        db=db,
        signal_repo=signal_repo,
        trade_repo=trade_repo,
        config_repo=config_repo,
        metrics_calculator=metrics_calculator,
        authenticator=authenticator,
        instruments=instruments,
        market_data=market_data,
        historical=historical,
        websocket=websocket,
        strategies=[gap_and_go, orb, vwap],
        ranker=ranker,
        risk_manager=risk_manager,
        exit_monitor=exit_monitor,
        bot=bot,
        scheduler=scheduler,
        duplicate_checker=duplicate_checker,
        capital_allocator=capital_allocator,
        strategy_performance_repo=strategy_performance_repo,
        app_config=config,
        # Phase 3
        confidence_detector=confidence_detector,
        composite_scorer=composite_scorer,
        adaptive_manager=adaptive_manager,
        circuit_breaker=circuit_breaker,
        hybrid_score_repo=hybrid_score_repo,
        circuit_breaker_repo=circuit_breaker_repo,
        adaptation_log_repo=adaptation_log_repo,
        dashboard_app=dashboard_app,
    )

    # Wire app reference back to bot for OVERRIDE CIRCUIT command
    bot.set_app(app)

    return app


async def main() -> None:
    """Application entry point."""
    config = AppConfig()
    configure_logging(level=config.log_level, log_file=config.log_file)
    app = await create_app(config)

    loop = asyncio.get_running_loop()
    shutting_down = False

    def _handle_signal() -> None:
        nonlocal shutting_down
        if not shutting_down:
            shutting_down = True
            asyncio.create_task(app.shutdown())

    for sig in (signal_module.SIGINT, signal_module.SIGTERM):
        loop.add_signal_handler(sig, _handle_signal)

    now = datetime.now(IST)
    if is_market_hours(now) and is_trading_day(now.date()):
        logger.info("Detected market hours -- entering crash recovery mode")
        await app.recover()
    else:
        logger.info("Normal startup sequence")
        await app.startup()

    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    asyncio.run(main())
