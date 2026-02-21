"""Cross-strategy duplicate checker — prevents same-stock signals."""

import logging
from datetime import date

from signalpilot.db.models import CandidateSignal

logger = logging.getLogger(__name__)


class DuplicateChecker:
    """Prevents duplicate signals for the same stock across strategies."""

    def __init__(self, signal_repo, trade_repo) -> None:
        self._signal_repo = signal_repo
        self._trade_repo = trade_repo

    async def filter_duplicates(
        self, candidates: list[CandidateSignal], today: date
    ) -> list[CandidateSignal]:
        """Remove candidates that already have a signal or active trade today."""
        if not candidates:
            return []

        active_trades = await self._trade_repo.get_active_trades()
        active_symbols = {t.symbol for t in active_trades}

        filtered: list[CandidateSignal] = []
        for candidate in candidates:
            if candidate.symbol in active_symbols:
                logger.info(
                    "Duplicate suppressed: %s has active trade", candidate.symbol
                )
                continue
            has_signal = await self._signal_repo.has_signal_for_stock_today(
                candidate.symbol, today
            )
            if has_signal:
                logger.info(
                    "Duplicate suppressed: %s already signaled today",
                    candidate.symbol,
                )
                continue
            filtered.append(candidate)

        suppressed = len(candidates) - len(filtered)
        if suppressed:
            logger.info("Duplicate checker: %d candidates suppressed", suppressed)
        return filtered
