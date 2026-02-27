"""Gap stock marking — excludes Gap & Go stocks from ORB scanning."""

from __future__ import annotations

import logging

from signalpilot.pipeline.context import ScanContext

logger = logging.getLogger(__name__)


class GapStockMarkingStage:
    """Mark Gap & Go stocks so ORB skips them."""

    @property
    def name(self) -> str:
        return "gap_stock_marking"

    async def process(self, ctx: ScanContext) -> ScanContext:
        gap_symbols = {
            c.symbol
            for c in ctx.all_candidates
            if getattr(c, "strategy_name", None) == "Gap & Go"
        }
        if gap_symbols:
            for strat in ctx.enabled_strategies:
                if hasattr(strat, "mark_gap_stock"):
                    for sym in gap_symbols:
                        strat.mark_gap_stock(sym)
        return ctx
