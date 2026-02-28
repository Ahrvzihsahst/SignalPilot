"""Tests for ExitMonitoringStage."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from signalpilot.db.models import TradeRecord
from signalpilot.pipeline.context import ScanContext
from signalpilot.pipeline.stages.exit_monitoring import ExitMonitoringStage
from signalpilot.utils.constants import IST


async def test_checks_active_trades():
    """Stage should call exit_monitor.check_trade for each active trade."""
    trade = TradeRecord(id=1, symbol="SBIN", entry_price=100.0, stop_loss=97.0, quantity=10)
    trade_repo = AsyncMock()
    trade_repo.get_active_trades = AsyncMock(return_value=[trade])
    exit_monitor = MagicMock()
    exit_monitor.check_trade = AsyncMock(return_value=None)
    signal_repo = AsyncMock()
    signal_repo.expire_stale_signals = AsyncMock(return_value=0)

    stage = ExitMonitoringStage(trade_repo, exit_monitor, signal_repo)
    ctx = ScanContext(now=datetime.now(IST))
    await stage.process(ctx)

    exit_monitor.check_trade.assert_awaited_once_with(trade)


async def test_expires_stale_signals():
    """Stage should call signal_repo.expire_stale_signals."""
    trade_repo = AsyncMock()
    trade_repo.get_active_trades = AsyncMock(return_value=[])
    exit_monitor = MagicMock()
    exit_monitor.check_trade = AsyncMock()
    signal_repo = AsyncMock()
    signal_repo.expire_stale_signals = AsyncMock(return_value=2)

    stage = ExitMonitoringStage(trade_repo, exit_monitor, signal_repo)
    ctx = ScanContext(now=datetime.now(IST))
    await stage.process(ctx)

    signal_repo.expire_stale_signals.assert_awaited_once()


async def test_no_trades_no_errors():
    """Stage should work fine with no active trades."""
    trade_repo = AsyncMock()
    trade_repo.get_active_trades = AsyncMock(return_value=[])
    exit_monitor = MagicMock()
    exit_monitor.check_trade = AsyncMock()
    signal_repo = AsyncMock()
    signal_repo.expire_stale_signals = AsyncMock(return_value=0)

    stage = ExitMonitoringStage(trade_repo, exit_monitor, signal_repo)
    ctx = ScanContext(now=datetime.now(IST))
    await stage.process(ctx)

    exit_monitor.check_trade.assert_not_awaited()
