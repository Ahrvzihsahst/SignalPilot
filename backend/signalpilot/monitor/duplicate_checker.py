"""Cross-strategy duplicate checker — prevents same-stock signals."""

import logging
from collections import defaultdict
from datetime import date

from signalpilot.db.models import CandidateSignal

logger = logging.getLogger(__name__)


class DuplicateChecker:
    """Prevents duplicate signals for the same stock across strategies.

    When a ``confidence_detector`` is provided, symbols that appear from
    multiple *different* strategies in the current batch are allowed through
    the cross-strategy dedup check (they represent multi-strategy
    confirmations).  Same-strategy duplicates and symbols with status="taken"
    or active trades are still blocked.
    """

    def __init__(self, signal_repo, trade_repo, confidence_detector=None) -> None:
        self._signal_repo = signal_repo
        self._trade_repo = trade_repo
        self._confidence_detector = confidence_detector

    async def filter_duplicates(
        self, candidates: list[CandidateSignal], today: date
    ) -> list[CandidateSignal]:
        """Remove candidates that already have a signal or active trade today."""
        if not candidates:
            return []

        active_trades = await self._trade_repo.get_active_trades()
        active_symbols = {t.symbol for t in active_trades}

        # When confidence_detector is provided, identify multi-strategy symbols
        multi_strategy_symbols: set[str] = set()
        if self._confidence_detector is not None:
            by_symbol: dict[str, set[str]] = defaultdict(set)
            for c in candidates:
                by_symbol[c.symbol].add(c.strategy_name)
            multi_strategy_symbols = {
                symbol for symbol, strategies in by_symbol.items()
                if len(strategies) > 1
            }

        filtered: list[CandidateSignal] = []
        for candidate in candidates:
            if candidate.symbol in active_symbols:
                logger.info(
                    "Duplicate suppressed: %s has active trade", candidate.symbol
                )
                continue

            # For multi-strategy symbols with confidence_detector, bypass
            # the existing-signal dedup (they are confirmations, not duplicates).
            # Still run the check for single-strategy candidates.
            if (
                self._confidence_detector is not None
                and candidate.symbol in multi_strategy_symbols
            ):
                filtered.append(candidate)
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
