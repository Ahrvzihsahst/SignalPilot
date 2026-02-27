"""Diagnostic stage — periodic heartbeat logging."""

from __future__ import annotations

import logging

from signalpilot.pipeline.context import ScanContext

logger = logging.getLogger(__name__)


class DiagnosticStage:
    """Log a heartbeat message every 60 cycles to aid debugging."""

    def __init__(self, websocket=None) -> None:
        self._websocket = websocket
        self._cycle_count = 0

    @property
    def name(self) -> str:
        return "diagnostic"

    async def process(self, ctx: ScanContext) -> ScanContext:
        self._cycle_count += 1
        if self._cycle_count % 60 == 0:
            ws_ok = (
                self._websocket.is_connected
                if self._websocket
                else False
            )
            logger.info(
                "Scan heartbeat: phase=%s strategies=%d ws_connected=%s "
                "candidates_this_cycle=%d",
                ctx.phase.value,
                len(ctx.enabled_strategies),
                ws_ok,
                len(ctx.all_candidates),
            )
        return ctx
