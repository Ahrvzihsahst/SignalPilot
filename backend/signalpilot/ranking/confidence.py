"""Multi-strategy confirmation detector for Phase 3 hybrid scoring."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from signalpilot.db.models import CandidateSignal

logger = logging.getLogger(__name__)


@dataclass
class ConfirmationResult:
    """Result of multi-strategy confirmation analysis."""

    confirmation_level: str  # "single", "double", "triple"
    confirmed_by: list[str] = field(default_factory=list)  # strategy names
    star_boost: int = 0  # 0, +1, +2
    position_size_multiplier: float = 1.0  # 1.0, 1.5, 2.0


class ConfidenceDetector:
    """Detects multi-strategy confirmations for the same symbol.

    Groups candidates by symbol and checks for:
    1. In-batch confirmations: multiple strategies in the current candidate batch.
    2. Cross-cycle confirmations: recent signals from the DB within
       ``CONFIRMATION_WINDOW``.
    """

    CONFIRMATION_WINDOW = timedelta(minutes=15)

    def __init__(self, signal_repo=None) -> None:
        self._signal_repo = signal_repo

    async def detect_confirmations(
        self,
        candidates: list[CandidateSignal],
        now: datetime,
    ) -> list[tuple[CandidateSignal, ConfirmationResult]]:
        """Analyze candidates for multi-strategy confirmations.

        Groups candidates by symbol. For each symbol, checks:
        1. In-batch: multiple strategies in current batch
        2. Cross-cycle: recent signals from DB within CONFIRMATION_WINDOW

        Returns every candidate exactly once with its ConfirmationResult.
        """
        logger.info(
            "Entering detect_confirmations",
            extra={"candidate_count": len(candidates)},
        )

        by_symbol = self._group_by_symbol(candidates)
        results: list[tuple[CandidateSignal, ConfirmationResult]] = []
        since = now - self.CONFIRMATION_WINDOW

        for symbol, symbol_candidates in by_symbol.items():
            # Collect strategies from current batch
            batch_strategies = {c.strategy_name for c in symbol_candidates}

            # Query DB for recent signals from other strategies
            db_strategies: set[str] = set()
            if self._signal_repo is not None:
                recent = await self._get_recent_signals_for_symbol(symbol, since)
                db_strategies = {strategy for strategy, _ in recent}

            # Combine all unique strategies
            all_strategies = list(batch_strategies | db_strategies)

            # Calculate confirmation for each candidate
            for candidate in symbol_candidates:
                confirmation = self._calculate_confirmation(all_strategies)
                results.append((candidate, confirmation))

            logger.debug(
                "Processed symbol %s: %d candidates, %d unique strategies",
                symbol,
                len(symbol_candidates),
                len(all_strategies),
            )

        logger.info(
            "Exiting detect_confirmations",
            extra={"result_count": len(results)},
        )
        return results

    @staticmethod
    def _group_by_symbol(
        candidates: list[CandidateSignal],
    ) -> dict[str, list[CandidateSignal]]:
        """Group candidates by their symbol."""
        groups: dict[str, list[CandidateSignal]] = defaultdict(list)
        for c in candidates:
            groups[c.symbol].append(c)
        return dict(groups)

    async def _get_recent_signals_for_symbol(
        self, symbol: str, since: datetime
    ) -> list[tuple[str, datetime]]:
        """Fetch recent signals for a symbol from the signal repository."""
        if self._signal_repo is None:
            return []
        return await self._signal_repo.get_recent_signals_by_symbol(symbol, since)

    @staticmethod
    def _calculate_confirmation(strategies: list[str]) -> ConfirmationResult:
        """Calculate confirmation level from a list of strategy names.

        Deduplicates strategies before counting:
        - 1 unique strategy  -> single (no boost)
        - 2 unique strategies -> double (+1 star, 1.5x position)
        - 3+ unique strategies -> triple (+2 stars, 2.0x position)
        """
        unique = list(set(strategies))
        count = len(unique)

        if count >= 3:
            return ConfirmationResult(
                confirmation_level="triple",
                confirmed_by=unique,
                star_boost=2,
                position_size_multiplier=2.0,
            )
        elif count == 2:
            return ConfirmationResult(
                confirmation_level="double",
                confirmed_by=unique,
                star_boost=1,
                position_size_multiplier=1.5,
            )
        else:
            return ConfirmationResult(
                confirmation_level="single",
                confirmed_by=unique,
                star_boost=0,
                position_size_multiplier=1.0,
            )
