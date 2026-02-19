"""Tests for MarketScheduler."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from signalpilot.scheduler.scheduler import MarketScheduler
from signalpilot.utils.constants import IST


def _make_mock_app():
    """Create a mock app with all required async methods."""
    app = MagicMock()
    app.send_pre_market_alert = AsyncMock()
    app.start_scanning = AsyncMock()
    app.stop_new_signals = AsyncMock()
    app.trigger_exit_reminder = AsyncMock()
    app.trigger_mandatory_exit = AsyncMock()
    app.send_daily_summary = AsyncMock()
    app.shutdown = AsyncMock()
    return app


EXPECTED_JOBS = {
    "pre_market_alert": (9, 0),
    "start_scanning": (9, 15),
    "stop_new_signals": (14, 30),
    "exit_reminder": (15, 0),
    "mandatory_exit": (15, 15),
    "daily_summary": (15, 30),
    "shutdown": (15, 35),
}


def test_all_seven_jobs_registered() -> None:
    scheduler = MarketScheduler()
    app = _make_mock_app()
    scheduler.configure_jobs(app)

    job_ids = {job.id for job in scheduler.jobs}
    assert job_ids == set(EXPECTED_JOBS.keys())
    assert len(scheduler.jobs) == 7


@pytest.mark.parametrize("job_id,expected_time", list(EXPECTED_JOBS.items()))
def test_job_trigger_times(job_id: str, expected_time: tuple[int, int]) -> None:
    scheduler = MarketScheduler()
    app = _make_mock_app()
    scheduler.configure_jobs(app)

    job = next(j for j in scheduler.jobs if j.id == job_id)
    trigger = job.trigger
    hour, minute = expected_time
    # CronTrigger fields: 0=year, 1=month, 2=day, 3=week, 4=day_of_week, 5=hour, 6=minute
    assert str(trigger.fields[5]) == str(hour)
    assert str(trigger.fields[6]) == str(minute)


def test_jobs_use_ist_timezone() -> None:
    scheduler = MarketScheduler()
    app = _make_mock_app()
    scheduler.configure_jobs(app)

    for job in scheduler.jobs:
        assert job.trigger.timezone == IST


async def test_start_and_shutdown() -> None:
    """start() requires a running event loop (AsyncIOScheduler); shutdown() stops it."""
    scheduler = MarketScheduler()
    app = _make_mock_app()
    scheduler.configure_jobs(app)
    scheduler.start()
    assert len(scheduler.jobs) == 7
    scheduler.shutdown()


def test_configure_without_start() -> None:
    """Jobs can be configured before the scheduler is started."""
    scheduler = MarketScheduler()
    app = _make_mock_app()
    scheduler.configure_jobs(app)
    assert len(scheduler.jobs) == 7


def test_shutdown_without_start_does_not_raise() -> None:
    """Calling shutdown on a scheduler that was never started should not raise."""
    scheduler = MarketScheduler()
    app = _make_mock_app()
    scheduler.configure_jobs(app)
    scheduler.shutdown()  # should not raise
