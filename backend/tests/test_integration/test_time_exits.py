"""Integration tests for time-based exits with real DB and lifecycle."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from signalpilot.scheduler.lifecycle import SignalPilotApp
from signalpilot.telegram.handlers import handle_taken
from signalpilot.utils.constants import IST
from tests.test_integration.conftest import make_signal_record


async def test_exit_reminder_sends_advisory_alert(db, repos):
    """3:00 PM exit reminder should send advisory alert, NOT close trades."""
    now = datetime.now(IST)

    # Create 2 trades
    for symbol in ["SBIN", "TCS"]:
        signal = make_signal_record(symbol=symbol, entry_price=100.0, created_at=now)
        await repos["signal_repo"].insert_signal(signal)
        mock_monitor = MagicMock(start_monitoring=MagicMock())
        await handle_taken(
            repos["signal_repo"], repos["trade_repo"], repos["config_repo"],
            mock_monitor, now=now,
        )

    # Create app with mock bot and exit monitor
    mock_bot = AsyncMock()
    mock_exit_monitor = MagicMock(
        check_all_trades=AsyncMock(),
        trigger_time_exit=AsyncMock(return_value=[]),
        start_monitoring=MagicMock(),
    )

    app = SignalPilotApp(
        db=db, signal_repo=repos["signal_repo"], trade_repo=repos["trade_repo"],
        config_repo=repos["config_repo"], metrics_calculator=repos["metrics"],
        authenticator=AsyncMock(), instruments=AsyncMock(), market_data=MagicMock(),
        historical=AsyncMock(), websocket=AsyncMock(),
        strategy=AsyncMock(), ranker=MagicMock(), risk_manager=MagicMock(),
        exit_monitor=mock_exit_monitor, bot=mock_bot, scheduler=MagicMock(),
    )

    await app.trigger_exit_reminder()

    # Advisory alert sent via exit monitor
    mock_exit_monitor.trigger_time_exit.assert_awaited_once()
    # Bot sends advisory message
    mock_bot.send_alert.assert_awaited_once()
    alert_msg = mock_bot.send_alert.call_args[0][0]
    assert "closing" in alert_msg.lower() or "close" in alert_msg.lower()

    # Trades still open
    active = await repos["trade_repo"].get_active_trades()
    assert len(active) == 2


async def test_mandatory_exit_triggers_exit_monitor(db, repos):
    """3:15 PM mandatory exit should trigger exit monitor with is_mandatory=True."""
    now = datetime.now(IST)

    # Create 2 trades
    for symbol in ["SBIN", "TCS"]:
        signal = make_signal_record(symbol=symbol, created_at=now)
        await repos["signal_repo"].insert_signal(signal)
        mock_monitor = MagicMock(start_monitoring=MagicMock())
        await handle_taken(
            repos["signal_repo"], repos["trade_repo"], repos["config_repo"],
            mock_monitor, now=now,
        )

    mock_exit_monitor = MagicMock(
        trigger_time_exit=AsyncMock(return_value=[]),
    )

    app = SignalPilotApp(
        db=db, signal_repo=repos["signal_repo"], trade_repo=repos["trade_repo"],
        config_repo=repos["config_repo"], metrics_calculator=repos["metrics"],
        authenticator=AsyncMock(), instruments=AsyncMock(), market_data=MagicMock(),
        historical=AsyncMock(), websocket=AsyncMock(),
        strategy=AsyncMock(), ranker=MagicMock(), risk_manager=MagicMock(),
        exit_monitor=mock_exit_monitor, bot=AsyncMock(), scheduler=MagicMock(),
    )

    await app.trigger_mandatory_exit()

    mock_exit_monitor.trigger_time_exit.assert_awaited_once()
