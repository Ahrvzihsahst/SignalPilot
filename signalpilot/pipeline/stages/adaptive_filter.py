"""Adaptive filter — blocks signals from underperforming strategies."""

from __future__ import annotations

import logging

from signalpilot.pipeline.context import ScanContext

logger = logging.getLogger(__name__)


class AdaptiveFilterStage:
    """Filter candidates using the adaptive manager's should_allow_signal check."""

    def __init__(self, adaptive_manager=None) -> None:
        self._adaptive_manager = adaptive_manager

    @property
    def name(self) -> str:
        return "adaptive_filter"

    async def process(self, ctx: ScanContext) -> ScanContext:
        if not ctx.all_candidates or self._adaptive_manager is None:
            return ctx

        filtered = []
        for candidate in ctx.all_candidates:
            strength = 3  # default
            if ctx.composite_scores and candidate.symbol in ctx.composite_scores:
                cs = ctx.composite_scores[candidate.symbol].composite_score
                if cs >= 80:
                    strength = 5
                elif cs >= 65:
                    strength = 4
                elif cs >= 50:
                    strength = 3
                elif cs >= 35:
                    strength = 2
                else:
                    strength = 1
            if self._adaptive_manager.should_allow_signal(
                candidate.strategy_name, strength
            ):
                filtered.append(candidate)
            else:
                logger.info(
                    "Adaptive filter blocked %s (%s)",
                    candidate.symbol, candidate.strategy_name,
                )
        ctx.all_candidates = filtered
        return ctx
