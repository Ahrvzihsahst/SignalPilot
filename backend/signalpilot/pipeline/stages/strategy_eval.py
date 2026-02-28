"""Strategy evaluation — runs enabled strategies to produce candidates."""

from __future__ import annotations

import logging

from signalpilot.db.models import UserConfig
from signalpilot.pipeline.context import ScanContext

logger = logging.getLogger(__name__)

# Maps strategy name → user_config flag attribute
_STRATEGY_FLAG_MAP = {
    "Gap & Go": "gap_go_enabled",
    "gap_go": "gap_go_enabled",
    "ORB": "orb_enabled",
    "VWAP Reversal": "vwap_enabled",
}


class StrategyEvalStage:
    """Evaluate all enabled strategies for the current phase."""

    def __init__(self, strategies: list, config_repo, market_data) -> None:
        self._strategies = strategies
        self._config_repo = config_repo
        self._market_data = market_data

    @property
    def name(self) -> str:
        return "strategy_eval"

    async def process(self, ctx: ScanContext) -> ScanContext:
        ctx.user_config = await self._config_repo.get_user_config()
        ctx.enabled_strategies = self._get_enabled_strategies(ctx.user_config)

        all_candidates = []
        for strat in ctx.enabled_strategies:
            if ctx.phase in strat.active_phases:
                candidates = await strat.evaluate(self._market_data, ctx.phase)
                if candidates:
                    all_candidates.extend(candidates)

        ctx.all_candidates = all_candidates
        return ctx

    def _get_enabled_strategies(self, user_config: UserConfig | None) -> list:
        """Filter strategies by the corresponding enabled flag in user_config."""
        if not self._strategies:
            return []
        if user_config is None:
            return list(self._strategies)

        enabled = []
        for strat in self._strategies:
            flag = _STRATEGY_FLAG_MAP.get(strat.name, None)
            if flag is None or getattr(user_config, flag, True):
                enabled.append(strat)
        return enabled
