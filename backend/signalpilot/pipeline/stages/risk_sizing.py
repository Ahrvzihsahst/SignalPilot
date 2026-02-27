"""Risk sizing — applies position sizing and capital limits."""

from __future__ import annotations

import logging

from signalpilot.pipeline.context import ScanContext

logger = logging.getLogger(__name__)


class RiskSizingStage:
    """Size positions using the risk manager."""

    def __init__(self, risk_manager, trade_repo) -> None:
        self._risk_manager = risk_manager
        self._trade_repo = trade_repo

    @property
    def name(self) -> str:
        return "risk_sizing"

    async def process(self, ctx: ScanContext) -> ScanContext:
        if not ctx.ranked_signals:
            return ctx
        ctx.active_trade_count = await self._trade_repo.get_active_trade_count()
        ctx.final_signals = self._risk_manager.filter_and_size(
            ctx.ranked_signals,
            ctx.user_config,
            ctx.active_trade_count,
            confirmation_map=ctx.confirmation_map,
        )
        return ctx
