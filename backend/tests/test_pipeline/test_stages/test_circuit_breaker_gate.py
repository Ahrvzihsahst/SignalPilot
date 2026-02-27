"""Tests for CircuitBreakerGateStage."""

from unittest.mock import MagicMock

from signalpilot.pipeline.context import ScanContext
from signalpilot.pipeline.stages.circuit_breaker_gate import CircuitBreakerGateStage


async def test_no_op_when_circuit_breaker_is_none():
    """Stage should be a no-op when circuit breaker is not configured."""
    stage = CircuitBreakerGateStage(circuit_breaker=None)
    ctx = ScanContext(accepting_signals=True)
    result = await stage.process(ctx)
    assert result.accepting_signals is True


async def test_disables_signals_when_active():
    """When circuit breaker is active, accepting_signals should be set to False."""
    cb = MagicMock()
    cb.is_active = True
    stage = CircuitBreakerGateStage(circuit_breaker=cb)
    ctx = ScanContext(accepting_signals=True)
    result = await stage.process(ctx)
    assert result.accepting_signals is False


async def test_keeps_signals_when_not_active():
    """When circuit breaker is not active, accepting_signals should stay True."""
    cb = MagicMock()
    cb.is_active = False
    stage = CircuitBreakerGateStage(circuit_breaker=cb)
    ctx = ScanContext(accepting_signals=True)
    result = await stage.process(ctx)
    assert result.accepting_signals is True


def test_stage_name():
    stage = CircuitBreakerGateStage()
    assert stage.name == "circuit_breaker_gate"
