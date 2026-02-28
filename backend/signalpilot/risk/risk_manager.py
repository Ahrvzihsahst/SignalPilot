"""Risk management — position limits, sizing, and signal filtering."""

from __future__ import annotations

import logging
from datetime import timedelta

from signalpilot.db.models import FinalSignal, RankedSignal, UserConfig
from signalpilot.ranking.confidence import ConfirmationResult
from signalpilot.risk.position_sizer import PositionSizer

logger = logging.getLogger(__name__)


class RiskManager:
    """Applies risk filters to ranked signals before delivery."""

    def __init__(
        self,
        position_sizer: PositionSizer,
        capital_allocator=None,
    ) -> None:
        self._sizer = position_sizer
        self._capital_allocator = capital_allocator

    def filter_and_size(
        self,
        ranked_signals: list[RankedSignal],
        user_config: UserConfig,
        active_trade_count: int,
        confirmation_map: dict[str, ConfirmationResult] | None = None,
    ) -> list[FinalSignal]:
        """Filter ranked signals through position limits and sizing constraints.

        1. If at max open positions, return empty list.
        2. Limit candidates to available slots.
        3. Calculate position size -- auto-skip if quantity == 0 (too expensive).
        4. Set expiry to 30 minutes after signal generation time.

        When ``confirmation_map`` is provided, the position size multiplier
        from each symbol's ConfirmationResult is forwarded to the sizer.
        """
        available_slots = user_config.max_positions - active_trade_count
        if available_slots <= 0:
            logger.info(
                "Position limit reached (%d/%d active). No new signals.",
                active_trade_count,
                user_config.max_positions,
            )
            return []

        final_signals: list[FinalSignal] = []
        for ranked in ranked_signals[:available_slots]:
            # Determine multiplier from confirmation map
            multiplier = 1.0
            if confirmation_map is not None:
                symbol = ranked.candidate.symbol
                conf = confirmation_map.get(symbol)
                if conf is not None:
                    multiplier = conf.position_size_multiplier

            size = self._sizer.calculate(
                entry_price=ranked.candidate.entry_price,
                total_capital=user_config.total_capital,
                max_positions=user_config.max_positions,
                multiplier=multiplier,
            )
            if size.quantity == 0:
                logger.info(
                    "Auto-skipped %s: price %.2f exceeds per-trade allocation %.2f",
                    ranked.candidate.symbol,
                    ranked.candidate.entry_price,
                    size.per_trade_capital,
                )
                continue

            expires_at = ranked.candidate.generated_at + timedelta(minutes=30)
            final_signals.append(
                FinalSignal(
                    ranked_signal=ranked,
                    quantity=size.quantity,
                    capital_required=size.capital_required,
                    expires_at=expires_at,
                )
            )

        return final_signals
