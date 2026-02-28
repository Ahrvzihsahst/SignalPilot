"""Tests for CircuitBreakerRepository."""

from datetime import date, datetime

import pytest

from signalpilot.utils.constants import IST


class TestCircuitBreakerRepository:
    async def test_log_activation_and_get_status(self, circuit_breaker_repo):
        today = date(2026, 2, 16)
        triggered_at = datetime(2026, 2, 16, 11, 30, 0, tzinfo=IST)

        record_id = await circuit_breaker_repo.log_activation(
            today=today, sl_count=3, triggered_at=triggered_at,
        )
        assert record_id is not None
        assert record_id > 0

        status = await circuit_breaker_repo.get_today_status(today)
        assert status is not None
        assert status.id == record_id
        assert status.date == today
        assert status.sl_count == 3
        assert status.triggered_at == triggered_at
        assert status.resumed_at is None
        assert status.manual_override is False
        assert status.override_at is None

    async def test_log_override_updates_record(self, circuit_breaker_repo):
        today = date(2026, 2, 16)
        triggered_at = datetime(2026, 2, 16, 11, 30, 0, tzinfo=IST)
        override_at = datetime(2026, 2, 16, 12, 0, 0, tzinfo=IST)

        await circuit_breaker_repo.log_activation(
            today=today, sl_count=3, triggered_at=triggered_at,
        )
        await circuit_breaker_repo.log_override(today=today, override_at=override_at)

        status = await circuit_breaker_repo.get_today_status(today)
        assert status is not None
        assert status.manual_override is True
        assert status.override_at == override_at

    async def test_log_resume_updates_record(self, circuit_breaker_repo):
        today = date(2026, 2, 16)
        triggered_at = datetime(2026, 2, 16, 11, 30, 0, tzinfo=IST)
        resumed_at = datetime(2026, 2, 16, 13, 0, 0, tzinfo=IST)

        await circuit_breaker_repo.log_activation(
            today=today, sl_count=3, triggered_at=triggered_at,
        )
        await circuit_breaker_repo.log_resume(today=today, resumed_at=resumed_at)

        status = await circuit_breaker_repo.get_today_status(today)
        assert status is not None
        assert status.resumed_at == resumed_at

    async def test_get_history_ordered_by_date_desc(self, circuit_breaker_repo):
        # Insert activations for three different dates
        for i in range(3):
            d = date(2026, 2, 14 + i)
            triggered = datetime(2026, 2, 14 + i, 11, 30, 0, tzinfo=IST)
            await circuit_breaker_repo.log_activation(
                today=d, sl_count=3 + i, triggered_at=triggered,
            )

        history = await circuit_breaker_repo.get_history(limit=10)
        assert len(history) == 3
        # Most recent date first
        assert history[0].date == date(2026, 2, 16)
        assert history[1].date == date(2026, 2, 15)
        assert history[2].date == date(2026, 2, 14)
        # SL counts correspond to insertion order
        assert history[0].sl_count == 5
        assert history[1].sl_count == 4
        assert history[2].sl_count == 3

    async def test_returns_none_when_no_record(self, circuit_breaker_repo):
        status = await circuit_breaker_repo.get_today_status(date(2026, 2, 16))
        assert status is None

    async def test_log_override_raises_when_no_record(self, circuit_breaker_repo):
        with pytest.raises(ValueError, match="No circuit breaker record found"):
            await circuit_breaker_repo.log_override(
                today=date(2026, 2, 16),
                override_at=datetime(2026, 2, 16, 12, 0, 0, tzinfo=IST),
            )

    async def test_log_resume_raises_when_no_record(self, circuit_breaker_repo):
        with pytest.raises(ValueError, match="No circuit breaker record found"):
            await circuit_breaker_repo.log_resume(
                today=date(2026, 2, 16),
                resumed_at=datetime(2026, 2, 16, 13, 0, 0, tzinfo=IST),
            )

    async def test_get_history_respects_limit(self, circuit_breaker_repo):
        for i in range(5):
            d = date(2026, 2, 12 + i)
            triggered = datetime(2026, 2, 12 + i, 11, 30, 0, tzinfo=IST)
            await circuit_breaker_repo.log_activation(
                today=d, sl_count=3, triggered_at=triggered,
            )

        history = await circuit_breaker_repo.get_history(limit=2)
        assert len(history) == 2
