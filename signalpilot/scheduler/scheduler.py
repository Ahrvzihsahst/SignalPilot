"""Market day scheduler using APScheduler 3.x."""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from signalpilot.utils.constants import IST

logger = logging.getLogger(__name__)


class MarketScheduler:
    """Manages scheduled events for the trading day using APScheduler."""

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler(timezone=IST)

    def configure_jobs(self, app) -> None:
        """Register all trading day jobs.

        app should be a SignalPilotApp instance with these async methods:
        - send_pre_market_alert()
        - start_scanning()
        - stop_new_signals()
        - trigger_exit_reminder()
        - trigger_mandatory_exit()
        - send_daily_summary()
        - shutdown()
        """
        jobs = [
            ("pre_market_alert", 9, 0, app.send_pre_market_alert),
            ("start_scanning", 9, 15, app.start_scanning),
            ("stop_new_signals", 14, 30, app.stop_new_signals),
            ("exit_reminder", 15, 0, app.trigger_exit_reminder),
            ("mandatory_exit", 15, 15, app.trigger_mandatory_exit),
            ("daily_summary", 15, 30, app.send_daily_summary),
            ("shutdown", 15, 35, app.shutdown),
        ]
        for job_id, hour, minute, callback in jobs:
            self._scheduler.add_job(
                callback,
                CronTrigger(hour=hour, minute=minute, timezone=IST),
                id=job_id,
                replace_existing=True,
            )
            logger.info("Registered job %s at %02d:%02d IST", job_id, hour, minute)

    def start(self) -> None:
        """Start the scheduler."""
        self._scheduler.start()
        logger.info("MarketScheduler started")

    def shutdown(self) -> None:
        """Gracefully shutdown the scheduler."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        logger.info("MarketScheduler shut down")

    @property
    def jobs(self):
        """Return the list of scheduled jobs (for testing)."""
        return self._scheduler.get_jobs()
