"""Integration tests for daily summary with per-strategy breakdown."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from signalpilot.scheduler.lifecycle import SignalPilotApp
from signalpilot.utils.constants import IST
from tests.test_integration.conftest import make_signal_record


async def test_daily_summary_sent(db, repos):
    """Daily summary sends formatted summary via bot."""
    now = datetime.now(IST)

    # Insert signals for multiple strategies
    for sym, strat in [("SBIN", "Gap & Go"), ("TCS", "ORB"), ("INFY", "VWAP Reversal")]:
        record = make_signal_record(symbol=sym, created_at=now, status="sent")
        record.strategy = strat
        await repos["signal_repo"].insert_signal(record)

    mock_bot = AsyncMock()

    app = SignalPilotApp(
        db=db,
        signal_repo=repos["signal_repo"],
        trade_repo=repos["trade_repo"],
        config_repo=repos["config_repo"],
        metrics_calculator=repos["metrics"],
        authenticator=AsyncMock(),
        instruments=AsyncMock(),
        market_data=MagicMock(),
        historical=AsyncMock(),
        websocket=AsyncMock(),
        ranker=MagicMock(),
        risk_manager=MagicMock(),
        exit_monitor=MagicMock(check_trade=AsyncMock()),
        bot=mock_bot,
        scheduler=MagicMock(),
    )

    await app.send_daily_summary()

    mock_bot.send_alert.assert_awaited_once()
    summary_msg = mock_bot.send_alert.call_args[0][0]
    assert isinstance(summary_msg, str)
    assert len(summary_msg) > 0
