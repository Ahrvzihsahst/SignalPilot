"""Exit monitoring — checks active trades and expires stale signals."""

from __future__ import annotations

import logging
from datetime import datetime

from signalpilot.pipeline.context import ScanContext
from signalpilot.utils.constants import IST

logger = logging.getLogger(__name__)


class ExitMonitoringStage:
    """Check active trades for exit conditions and expire stale signals."""

    def __init__(self, trade_repo, exit_monitor, signal_repo) -> None:
        self._trade_repo = trade_repo
        self._exit_monitor = exit_monitor
        self._signal_repo = signal_repo

    @property
    def name(self) -> str:
        return "exit_monitoring"

    async def process(self, ctx: ScanContext) -> ScanContext:
        active_trades = await self._trade_repo.get_active_trades()
        for trade in active_trades:
            await self._exit_monitor.check_trade(trade)

        # Expire stale signals
        now = datetime.now(IST)
        count = await self._signal_repo.expire_stale_signals(now)
        if count > 0:
            logger.info("Expired %d stale signals", count)

        return ctx
