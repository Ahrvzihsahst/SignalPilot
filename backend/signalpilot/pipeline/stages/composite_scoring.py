"""Composite scoring — computes hybrid scores for each candidate."""

from __future__ import annotations

import logging

from signalpilot.pipeline.context import ScanContext

logger = logging.getLogger(__name__)


class CompositeScoringStage:
    """Score each candidate using the composite scorer."""

    def __init__(self, composite_scorer=None) -> None:
        self._composite_scorer = composite_scorer

    @property
    def name(self) -> str:
        return "composite_scoring"

    async def process(self, ctx: ScanContext) -> ScanContext:
        if not ctx.all_candidates or self._composite_scorer is None or ctx.now is None:
            return ctx

        composite_scores = {}
        for candidate in ctx.all_candidates:
            conf = None
            if ctx.confirmation_map is not None:
                conf = ctx.confirmation_map.get(candidate.symbol)
            if conf is None:
                from signalpilot.ranking.confidence import ConfirmationResult

                conf = ConfirmationResult(
                    confirmation_level="single",
                    confirmed_by=[candidate.strategy_name],
                )
            score_result = await self._composite_scorer.score(
                candidate, conf, ctx.now.date()
            )
            composite_scores[candidate.symbol] = score_result

        ctx.composite_scores = composite_scores
        return ctx
