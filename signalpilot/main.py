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


def create_app(config: AppConfig) -> SignalPilotApp:
    """Wire all components together and return a SignalPilotApp.

    NOTE: Full component wiring will be completed once all feature branches
    (data engine, strategy, ranking, risk, monitor) are merged.
    Currently creates the app with placeholder dependencies.
    """
    from signalpilot.db.database import DatabaseManager

    db = DatabaseManager(config.db_path)
    scheduler = MarketScheduler()

    return SignalPilotApp(
        db=db,
        signal_repo=None,
        trade_repo=None,
        config_repo=None,
        metrics_calculator=None,
        authenticator=None,
        instruments=None,
        market_data=None,
        historical=None,
        websocket=None,
        strategy=None,
        ranker=None,
        risk_manager=None,
        exit_monitor=None,
        bot=None,
        scheduler=scheduler,
    )


async def main() -> None:
    """Application entry point."""
    config = AppConfig()
    configure_logging(level=config.log_level, log_file=config.log_file)
    app = create_app(config)

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
