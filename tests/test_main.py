"""Tests for main entry point."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


async def test_main_normal_startup_outside_market_hours() -> None:
    """When not market hours, main() should call startup()."""
    mock_app = MagicMock()
    mock_app.startup = AsyncMock()
    mock_app.recover = AsyncMock()
    mock_app.shutdown = AsyncMock()

    async def _cancel_immediately(seconds):
        raise asyncio.CancelledError

    with patch("signalpilot.main.AppConfig"), \
         patch("signalpilot.main.configure_logging"), \
         patch("signalpilot.main.create_app", return_value=mock_app), \
         patch("signalpilot.main.is_market_hours", return_value=False), \
         patch("asyncio.sleep", side_effect=_cancel_immediately):
        from signalpilot.main import main
        # The CancelledError is caught inside main() by the try/except
        await main()

    mock_app.startup.assert_awaited_once()
    mock_app.recover.assert_not_awaited()


async def test_main_crash_recovery_during_market_hours() -> None:
    """When during market hours, main() should call recover()."""
    mock_app = MagicMock()
    mock_app.recover = AsyncMock()
    mock_app.startup = AsyncMock()
    mock_app.shutdown = AsyncMock()

    async def _cancel_immediately(seconds):
        raise asyncio.CancelledError

    with patch("signalpilot.main.AppConfig"), \
         patch("signalpilot.main.configure_logging"), \
         patch("signalpilot.main.create_app", return_value=mock_app), \
         patch("signalpilot.main.is_market_hours", return_value=True), \
         patch("signalpilot.main.is_trading_day", return_value=True), \
         patch("asyncio.sleep", side_effect=_cancel_immediately):
        from signalpilot.main import main
        await main()

    mock_app.recover.assert_awaited_once()
    mock_app.startup.assert_not_awaited()


async def test_main_startup_on_weekend_during_market_time() -> None:
    """On a weekend at market-time, main() should call startup(), not recover()."""
    mock_app = MagicMock()
    mock_app.startup = AsyncMock()
    mock_app.recover = AsyncMock()
    mock_app.shutdown = AsyncMock()

    async def _cancel_immediately(seconds):
        raise asyncio.CancelledError

    with patch("signalpilot.main.AppConfig"), \
         patch("signalpilot.main.configure_logging"), \
         patch("signalpilot.main.create_app", return_value=mock_app), \
         patch("signalpilot.main.is_market_hours", return_value=True), \
         patch("signalpilot.main.is_trading_day", return_value=False), \
         patch("asyncio.sleep", side_effect=_cancel_immediately):
        from signalpilot.main import main
        await main()

    mock_app.startup.assert_awaited_once()
    mock_app.recover.assert_not_awaited()
