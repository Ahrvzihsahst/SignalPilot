"""Shared fixtures for integration tests."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from signalpilot.db.config_repo import ConfigRepository
from signalpilot.db.database import DatabaseManager
from signalpilot.db.metrics import MetricsCalculator
from signalpilot.db.models import (
    CandidateSignal,
    FinalSignal,
    RankedSignal,
    SignalDirection,
    SignalRecord,
    TradeRecord,
)
from signalpilot.db.signal_repo import SignalRepository
from signalpilot.db.trade_repo import TradeRepository
from signalpilot.scheduler.lifecycle import SignalPilotApp
from signalpilot.utils.constants import IST


@pytest.fixture
async def db():
    """Provide a real in-memory SQLite database."""
    manager = DatabaseManager(":memory:")
    await manager.initialize()
    yield manager
    await manager.close()


@pytest.fixture
async def repos(db):
    """Provide all real repositories."""
    conn = db.connection
    return {
        "signal_repo": SignalRepository(conn),
        "trade_repo": TradeRepository(conn),
        "config_repo": ConfigRepository(conn),
        "metrics": MetricsCalculator(conn),
    }


def make_signal_record(
    symbol="SBIN",
    entry_price=100.0,
    stop_loss=97.0,
    target_1=105.0,
    target_2=107.0,
    quantity=15,
    capital_required=1500.0,
    created_at=None,
    expires_at=None,
    status="sent",
) -> SignalRecord:
    """Create a SignalRecord for testing."""
    now = datetime.now(IST)
    created_at = created_at or now
    expires_at = expires_at or (created_at + timedelta(minutes=30))
    return SignalRecord(
        date=created_at.date(),
        symbol=symbol,
        strategy="Gap & Go",
        entry_price=entry_price,
        stop_loss=stop_loss,
        target_1=target_1,
        target_2=target_2,
        quantity=quantity,
        capital_required=capital_required,
        signal_strength=4,
        gap_pct=4.0,
        volume_ratio=2.0,
        reason="Gap up 4.0%, volume 2.0x ADV",
        created_at=created_at,
        expires_at=expires_at,
        status=status,
    )


def make_final_signal(
    symbol="SBIN",
    entry_price=100.0,
    stop_loss=97.0,
    target_1=105.0,
    target_2=107.0,
    quantity=15,
    generated_at=None,
    expires_at=None,
) -> FinalSignal:
    """Create a FinalSignal for testing."""
    generated_at = generated_at or datetime.now(IST)
    expires_at = expires_at or (generated_at + timedelta(minutes=30))
    candidate = CandidateSignal(
        symbol=symbol,
        direction=SignalDirection.BUY,
        strategy_name="Gap & Go",
        entry_price=entry_price,
        stop_loss=stop_loss,
        target_1=target_1,
        target_2=target_2,
        gap_pct=4.0,
        volume_ratio=2.0,
        price_distance_from_open_pct=1.5,
        reason="Gap up 4.0%, volume 2.0x ADV",
        generated_at=generated_at,
    )
    ranked = RankedSignal(
        candidate=candidate, composite_score=0.80, rank=1, signal_strength=4,
    )
    return FinalSignal(
        ranked_signal=ranked,
        quantity=quantity,
        capital_required=entry_price * quantity,
        expires_at=expires_at,
    )


def make_trade_record(
    signal_id: int = 1,
    symbol: str = "SBIN",
    entry_price: float = 100.0,
    stop_loss: float = 97.0,
    target_1: float = 105.0,
    target_2: float = 107.0,
    quantity: int = 15,
    taken_at: datetime | None = None,
) -> TradeRecord:
    """Create a TradeRecord for testing."""
    taken_at = taken_at or datetime.now(IST)
    return TradeRecord(
        signal_id=signal_id,
        date=taken_at.date(),
        symbol=symbol,
        entry_price=entry_price,
        stop_loss=stop_loss,
        target_1=target_1,
        target_2=target_2,
        quantity=quantity,
        taken_at=taken_at,
    )


def make_mock_strategy(name="Gap & Go", active_phases=None, evaluate_return=None):
    """Create a mock strategy with configurable name, phases, and return value.

    Supports both positional usage (integration tests) and keyword-only
    usage with defaults (scheduler/pipeline tests).
    """
    from signalpilot.utils.market_calendar import StrategyPhase

    mock = AsyncMock(evaluate=AsyncMock(return_value=evaluate_return or []))
    mock.name = name
    mock.active_phases = active_phases or [
        StrategyPhase.OPENING,
        StrategyPhase.ENTRY_WINDOW,
    ]
    # reset() is synchronous on real strategies
    mock.reset = MagicMock()
    return mock


def make_mock_websocket():
    """Create an AsyncMock websocket with sync methods properly configured."""
    mock = AsyncMock()
    mock.reset_volume_tracking = MagicMock()
    return mock


def make_mock_market_data():
    """Create a MagicMock market_data with async methods that lifecycle calls."""
    mock = MagicMock()
    mock.clear_session = AsyncMock()
    mock.lock_opening_ranges = AsyncMock()
    mock.set_historical = AsyncMock()
    return mock


def make_mock_historical():
    """Create a properly configured mock for HistoricalDataFetcher."""
    mock = AsyncMock()
    mock.fetch_previous_day_data.return_value = {}
    mock.fetch_average_daily_volume.return_value = {}
    return mock


def make_app(db, repos, **overrides) -> SignalPilotApp:
    """Create a SignalPilotApp with real DB/repos and mocked external components."""
    defaults = {
        "db": db,
        "signal_repo": repos["signal_repo"],
        "trade_repo": repos["trade_repo"],
        "config_repo": repos["config_repo"],
        "metrics_calculator": repos["metrics"],
        "authenticator": AsyncMock(),
        "instruments": AsyncMock(),
        "market_data": make_mock_market_data(),
        "historical": make_mock_historical(),
        "websocket": make_mock_websocket(),
        "strategy": make_mock_strategy(),
        "ranker": MagicMock(),
        "risk_manager": MagicMock(),
        "exit_monitor": MagicMock(
            check_trade=AsyncMock(),
            trigger_time_exit=AsyncMock(return_value=[]),
            start_monitoring=MagicMock(),
        ),
        "bot": AsyncMock(),
        "scheduler": MagicMock(),
    }
    defaults.update(overrides)
    return SignalPilotApp(**defaults)


def make_final_signal_for_strategy(
    strategy_name="Gap & Go",
    symbol="SBIN",
    entry_price=100.0,
    stop_loss=97.0,
    target_1=105.0,
    target_2=107.0,
    quantity=15,
    generated_at=None,
    expires_at=None,
    setup_type=None,
) -> FinalSignal:
    """Create a FinalSignal for a specific strategy."""
    generated_at = generated_at or datetime.now(IST)
    expires_at = expires_at or (generated_at + timedelta(minutes=30))
    candidate = CandidateSignal(
        symbol=symbol,
        direction=SignalDirection.BUY,
        strategy_name=strategy_name,
        entry_price=entry_price,
        stop_loss=stop_loss,
        target_1=target_1,
        target_2=target_2,
        gap_pct=4.0,
        volume_ratio=2.0,
        price_distance_from_open_pct=1.5,
        reason=f"{strategy_name} signal for {symbol}",
        generated_at=generated_at,
        setup_type=setup_type,
    )
    ranked = RankedSignal(
        candidate=candidate, composite_score=0.80, rank=1, signal_strength=4,
    )
    return FinalSignal(
        ranked_signal=ranked,
        quantity=quantity,
        capital_required=entry_price * quantity,
        expires_at=expires_at,
    )
