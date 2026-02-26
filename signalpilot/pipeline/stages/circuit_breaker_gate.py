"""Circuit breaker gate — disables signal generation when circuit breaker is active."""

from __future__ import annotations

import logging

from signalpilot.pipeline.context import ScanContext

logger = logging.getLogger(__name__)


class CircuitBreakerGateStage:
    """If the circuit breaker is active, disable signal acceptance for this cycle."""

    def __init__(self, circuit_breaker=None) -> None:
        self._circuit_breaker = circuit_breaker

    @property
    def name(self) -> str:
        return "circuit_breaker_gate"

    async def process(self, ctx: ScanContext) -> ScanContext:
        if self._circuit_breaker is not None and self._circuit_breaker.is_active:
            ctx.accepting_signals = False
        return ctx
