"""Confidence detection — identifies multi-strategy confirmations."""

from __future__ import annotations

import logging

from signalpilot.pipeline.context import ScanContext

logger = logging.getLogger(__name__)


class ConfidenceStage:
    """Run confidence detection on candidates to build a confirmation map."""

    def __init__(self, confidence_detector=None) -> None:
        self._confidence_detector = confidence_detector

    @property
    def name(self) -> str:
        return "confidence"

    async def process(self, ctx: ScanContext) -> ScanContext:
        if not ctx.all_candidates or self._confidence_detector is None:
            return ctx

        confirmation_results = await self._confidence_detector.detect_confirmations(
            ctx.all_candidates, ctx.now
        )
        confirmation_map = {}
        for candidate, conf_result in confirmation_results:
            confirmation_map[candidate.symbol] = conf_result
        ctx.confirmation_map = confirmation_map
        return ctx
