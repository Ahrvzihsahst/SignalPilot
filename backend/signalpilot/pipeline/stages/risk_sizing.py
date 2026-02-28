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

        # Phase 4: Market Regime Detection -- override max_positions
        effective_config = ctx.user_config
        if ctx.regime_max_positions is not None and ctx.user_config is not None:
            from signalpilot.db.models import UserConfig
            effective_config = UserConfig(
                id=ctx.user_config.id,
                telegram_chat_id=ctx.user_config.telegram_chat_id,
                total_capital=ctx.user_config.total_capital,
                max_positions=ctx.regime_max_positions,
                gap_go_enabled=ctx.user_config.gap_go_enabled,
                orb_enabled=ctx.user_config.orb_enabled,
                vwap_enabled=ctx.user_config.vwap_enabled,
                circuit_breaker_limit=ctx.user_config.circuit_breaker_limit,
                confidence_boost_enabled=ctx.user_config.confidence_boost_enabled,
                adaptive_learning_enabled=ctx.user_config.adaptive_learning_enabled,
                auto_rebalance_enabled=ctx.user_config.auto_rebalance_enabled,
                adaptation_mode=ctx.user_config.adaptation_mode,
            )

        ctx.final_signals = self._risk_manager.filter_and_size(
            ctx.ranked_signals,
            effective_config,
            ctx.active_trade_count,
            confirmation_map=ctx.confirmation_map,
        )

        # Phase 4: Market Regime Detection -- apply position size modifier
        if ctx.regime_position_modifier is not None and ctx.regime_position_modifier < 1.0:
            from signalpilot.db.models import FinalSignal
            adjusted = []
            for signal in ctx.final_signals:
                original_qty = signal.quantity
                adjusted_qty = max(1, int(original_qty * ctx.regime_position_modifier))
                adjusted.append(FinalSignal(
                    ranked_signal=signal.ranked_signal,
                    quantity=adjusted_qty,
                    capital_required=adjusted_qty * signal.ranked_signal.candidate.entry_price,
                    expires_at=signal.expires_at,
                ))
            ctx.final_signals = adjusted
            logger.info(
                "Regime position modifier %.2f applied to %d signals",
                ctx.regime_position_modifier, len(ctx.final_signals),
            )

        return ctx
