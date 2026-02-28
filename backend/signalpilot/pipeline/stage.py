"""Pipeline stage protocol and runner."""

from __future__ import annotations

import logging
from typing import Protocol

from signalpilot.pipeline.context import ScanContext
from signalpilot.utils.market_calendar import StrategyPhase

logger = logging.getLogger(__name__)


class PipelineStage(Protocol):
    """Interface for a single composable pipeline stage."""

    @property
    def name(self) -> str: ...

    async def process(self, ctx: ScanContext) -> ScanContext: ...


class ScanPipeline:
    """Runs pipeline stages in order.

    *signal_stages* run only when ``ctx.accepting_signals`` is True and the
    phase is an active signal-generating phase (OPENING, ENTRY_WINDOW, CONTINUOUS).

    *always_stages* run every cycle regardless (exit monitoring, expiry, etc.).
    """

    _ACTIVE_PHASES = frozenset({
        StrategyPhase.OPENING,
        StrategyPhase.ENTRY_WINDOW,
        StrategyPhase.CONTINUOUS,
    })

    def __init__(
        self,
        signal_stages: list[PipelineStage],
        always_stages: list[PipelineStage],
    ) -> None:
        self._signal_stages = signal_stages
        self._always_stages = always_stages

    async def run(self, ctx: ScanContext) -> ScanContext:
        """Execute the pipeline on *ctx* and return the (mutated) context."""
        if ctx.accepting_signals and ctx.phase in self._ACTIVE_PHASES:
            for stage in self._signal_stages:
                ctx = await stage.process(ctx)

        for stage in self._always_stages:
            ctx = await stage.process(ctx)

        return ctx
