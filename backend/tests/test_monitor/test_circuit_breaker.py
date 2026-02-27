"""Tests for CircuitBreaker."""

from unittest.mock import AsyncMock

import pytest

from signalpilot.monitor.circuit_breaker import CircuitBreaker


class TestCircuitBreaker:
    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock()
        repo.log_activation = AsyncMock(return_value=1)
        repo.log_override = AsyncMock()
        return repo

    @pytest.fixture
    def mock_callback(self):
        return AsyncMock()

    @pytest.fixture
    def cb(self, mock_repo, mock_callback):
        return CircuitBreaker(
            circuit_breaker_repo=mock_repo,
            on_circuit_break=mock_callback,
            sl_limit=3,
        )

    async def test_on_sl_hit_increments_count(self, cb):
        await cb.on_sl_hit("RELIANCE", "gap_go", -500.0)
        assert cb.daily_sl_count == 1

    async def test_warning_at_limit_minus_one(self, cb, mock_callback):
        await cb.on_sl_hit("RELIANCE", "gap_go", -500.0)
        await cb.on_sl_hit("TCS", "ORB", -300.0)
        # 2nd hit = limit-1, should warn
        assert mock_callback.call_count == 1
        msg = mock_callback.call_args[0][0]
        assert "2 stop losses" in msg

    async def test_activation_at_limit(self, cb, mock_callback):
        await cb.on_sl_hit("RELIANCE", "gap_go", -500.0)
        await cb.on_sl_hit("TCS", "ORB", -300.0)
        await cb.on_sl_hit("INFY", "VWAP Reversal", -200.0)
        assert cb.is_active is True
        # Warning at 2 + activation at 3 = 2 calls
        assert mock_callback.call_count == 2

    async def test_activation_callback_message(self, cb, mock_callback):
        await cb.on_sl_hit("RELIANCE", "gap_go", -500.0)
        await cb.on_sl_hit("TCS", "ORB", -300.0)
        await cb.on_sl_hit("INFY", "VWAP Reversal", -200.0)
        msg = mock_callback.call_args[0][0]
        assert "CIRCUIT BREAKER ACTIVATED" in msg
        assert "RELIANCE" in msg

    async def test_activation_logs_to_repo(self, cb, mock_repo):
        await cb.on_sl_hit("RELIANCE", "gap_go", -500.0)
        await cb.on_sl_hit("TCS", "ORB", -300.0)
        await cb.on_sl_hit("INFY", "VWAP Reversal", -200.0)
        mock_repo.log_activation.assert_called_once()

    async def test_override_when_active(self, cb, mock_repo):
        await cb.on_sl_hit("A", "gap_go", -100.0)
        await cb.on_sl_hit("B", "gap_go", -100.0)
        await cb.on_sl_hit("C", "gap_go", -100.0)
        assert cb.is_active is True

        result = await cb.override()
        assert result is True
        assert cb.is_active is False
        assert cb.is_overridden is True
        mock_repo.log_override.assert_called_once()

    async def test_override_when_not_active(self, cb):
        result = await cb.override()
        assert result is False
        assert cb.is_overridden is False

    async def test_reset_daily(self, cb):
        await cb.on_sl_hit("A", "gap_go", -100.0)
        await cb.on_sl_hit("B", "gap_go", -100.0)
        await cb.on_sl_hit("C", "gap_go", -100.0)
        cb.reset_daily()
        assert cb.daily_sl_count == 0
        assert cb.is_active is False
        assert cb.is_overridden is False

    async def test_sl_details_accumulation(self, cb):
        await cb.on_sl_hit("RELIANCE", "gap_go", -500.0)
        await cb.on_sl_hit("TCS", "ORB", -300.0)
        assert len(cb._sl_details) == 2

    async def test_no_reactivation_after_override(self, cb, mock_callback):
        # Trigger and override
        await cb.on_sl_hit("A", "gap_go", -100.0)
        await cb.on_sl_hit("B", "gap_go", -100.0)
        await cb.on_sl_hit("C", "gap_go", -100.0)
        await cb.override()

        # More SL hits should NOT re-activate
        await cb.on_sl_hit("D", "gap_go", -100.0)
        assert cb.is_active is False
