"""Circuit breaker integration test: ExitMonitor -> CircuitBreaker -> signal halt."""

from unittest.mock import AsyncMock

from signalpilot.monitor.circuit_breaker import CircuitBreaker


class TestCircuitBreakerFlow:
    async def test_three_sl_hits_activates(self):
        """3 SL hits trigger circuit breaker activation."""
        repo = AsyncMock()
        repo.log_activation = AsyncMock(return_value=1)
        callback = AsyncMock()

        cb = CircuitBreaker(circuit_breaker_repo=repo, on_circuit_break=callback, sl_limit=3)

        await cb.on_sl_hit("RELIANCE", "gap_go", -500.0)
        assert cb.is_active is False

        await cb.on_sl_hit("TCS", "ORB", -300.0)
        assert cb.is_active is False
        assert callback.call_count == 1  # Warning at 2

        await cb.on_sl_hit("INFY", "VWAP Reversal", -200.0)
        assert cb.is_active is True
        assert callback.call_count == 2  # Activation at 3
        repo.log_activation.assert_called_once()

    async def test_override_and_resume(self):
        """Override allows signals to resume, no re-activation."""
        repo = AsyncMock()
        repo.log_activation = AsyncMock(return_value=1)
        repo.log_override = AsyncMock()
        callback = AsyncMock()

        cb = CircuitBreaker(circuit_breaker_repo=repo, on_circuit_break=callback, sl_limit=3)

        for sym in ["A", "B", "C"]:
            await cb.on_sl_hit(sym, "gap_go", -100.0)

        assert cb.is_active is True

        result = await cb.override()
        assert result is True
        assert cb.is_active is False
        assert cb.is_overridden is True
        repo.log_override.assert_called_once()

        # Further SL should NOT re-activate
        await cb.on_sl_hit("D", "gap_go", -100.0)
        assert cb.is_active is False

    async def test_daily_reset(self):
        """Daily reset clears all state."""
        repo = AsyncMock()
        repo.log_activation = AsyncMock(return_value=1)
        callback = AsyncMock()

        cb = CircuitBreaker(circuit_breaker_repo=repo, on_circuit_break=callback, sl_limit=3)

        for sym in ["A", "B", "C"]:
            await cb.on_sl_hit(sym, "gap_go", -100.0)

        cb.reset_daily()
        assert cb.daily_sl_count == 0
        assert cb.is_active is False
        assert cb.is_overridden is False
