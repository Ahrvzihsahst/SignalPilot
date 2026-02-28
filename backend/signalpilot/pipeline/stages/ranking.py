"""Ranking — scores and ranks candidates, selecting top signals."""

from __future__ import annotations

import logging

from signalpilot.pipeline.context import ScanContext

logger = logging.getLogger(__name__)


class RankingStage:
    """Rank candidates using the signal ranker."""

    def __init__(self, ranker) -> None:
        self._ranker = ranker

    @property
    def name(self) -> str:
        return "ranking"

    async def process(self, ctx: ScanContext) -> ScanContext:
        if not ctx.all_candidates:
            return ctx
        ctx.ranked_signals = self._ranker.rank(
            ctx.all_candidates,
            composite_scores=ctx.composite_scores,
            confirmations=ctx.confirmation_map,
        )

        # Phase 4: Market Regime Detection -- min-stars filter
        if ctx.regime_min_stars and ctx.regime_min_stars > 3:
            pre_filter_count = len(ctx.ranked_signals)
            ctx.ranked_signals = [
                s for s in ctx.ranked_signals
                if s.signal_strength >= ctx.regime_min_stars
            ]
            if pre_filter_count > len(ctx.ranked_signals):
                logger.info(
                    "Regime min-stars filter: %d -> %d signals (threshold: %d stars)",
                    pre_filter_count, len(ctx.ranked_signals), ctx.regime_min_stars,
                )

        return ctx
