"""Risk management — position limits, sizing, and signal filtering."""

import logging
from datetime import timedelta

from signalpilot.db.models import FinalSignal, RankedSignal, UserConfig
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
    ) -> list[FinalSignal]:
        """Filter ranked signals through position limits and sizing constraints.

        1. If at max open positions, return empty list.
        2. Limit candidates to available slots.
        3. Calculate position size — auto-skip if quantity == 0 (too expensive).
        4. Set expiry to 30 minutes after signal generation time.
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
            size = self._sizer.calculate(
                entry_price=ranked.candidate.entry_price,
                total_capital=user_config.total_capital,
                max_positions=user_config.max_positions,
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
