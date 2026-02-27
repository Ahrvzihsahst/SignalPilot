"""Deduplication — filters out duplicate signals across strategies."""

from __future__ import annotations

import logging

from signalpilot.pipeline.context import ScanContext

logger = logging.getLogger(__name__)


class DeduplicationStage:
    """Remove cross-strategy duplicates for the current date."""

    def __init__(self, duplicate_checker=None) -> None:
        self._duplicate_checker = duplicate_checker

    @property
    def name(self) -> str:
        return "deduplication"

    async def process(self, ctx: ScanContext) -> ScanContext:
        if not ctx.all_candidates or self._duplicate_checker is None or ctx.now is None:
            return ctx
        ctx.all_candidates = await self._duplicate_checker.filter_duplicates(
            ctx.all_candidates, ctx.now.date()
        )
        return ctx
