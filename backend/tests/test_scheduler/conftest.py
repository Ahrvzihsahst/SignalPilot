"""Shared fixtures for scheduler tests."""

from unittest.mock import AsyncMock, MagicMock

from signalpilot.scheduler.lifecycle import SignalPilotApp
from tests.test_integration.conftest import (
    make_mock_historical,
    make_mock_market_data,
    make_mock_strategy,
    make_mock_websocket,
)


def make_scheduler_app(**overrides) -> SignalPilotApp:
    """Create a SignalPilotApp with all-mocked dependencies.

    Unlike ``make_app`` in the integration conftest (which uses real DB/repos),
    this version mocks everything for fast, isolated unit tests.
    """
    defaults = {
        "db": AsyncMock(),
        "signal_repo": AsyncMock(),
        "trade_repo": AsyncMock(),
        "config_repo": AsyncMock(),
        "metrics_calculator": AsyncMock(),
        "authenticator": AsyncMock(),
        "instruments": AsyncMock(),
        "market_data": make_mock_market_data(),
        "historical": make_mock_historical(),
        "websocket": make_mock_websocket(),
        "strategy": make_mock_strategy(),
        "ranker": MagicMock(),
        "risk_manager": MagicMock(),
        "exit_monitor": MagicMock(
            check_trade=AsyncMock(return_value=None),
            trigger_time_exit=AsyncMock(return_value=[]),
            start_monitoring=MagicMock(),
        ),
        "bot": AsyncMock(),
        "scheduler": MagicMock(),
    }
    defaults.update(overrides)
    return SignalPilotApp(**defaults)
