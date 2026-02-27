"""Shared fixtures for database tests."""

import pytest

from signalpilot.db.adaptation_log_repo import AdaptationLogRepository
from signalpilot.db.circuit_breaker_repo import CircuitBreakerRepository
from signalpilot.db.config_repo import ConfigRepository
from signalpilot.db.database import DatabaseManager
from signalpilot.db.hybrid_score_repo import HybridScoreRepository
from signalpilot.db.metrics import MetricsCalculator
from signalpilot.db.signal_repo import SignalRepository
from signalpilot.db.trade_repo import TradeRepository


@pytest.fixture
async def db_manager(tmp_path):
    """Provide an initialized database manager with a temporary database."""
    db_path = str(tmp_path / "test.db")
    manager = DatabaseManager(db_path)
    await manager.initialize()
    yield manager
    await manager.close()


@pytest.fixture
def signal_repo(db_manager):
    return SignalRepository(db_manager.connection)


@pytest.fixture
def trade_repo(db_manager):
    return TradeRepository(db_manager.connection)


@pytest.fixture
def config_repo(db_manager):
    return ConfigRepository(db_manager.connection)


@pytest.fixture
def metrics(db_manager):
    return MetricsCalculator(db_manager.connection)


@pytest.fixture
def hybrid_score_repo(db_manager):
    return HybridScoreRepository(db_manager.connection)


@pytest.fixture
def circuit_breaker_repo(db_manager):
    return CircuitBreakerRepository(db_manager.connection)


@pytest.fixture
def adaptation_log_repo(db_manager):
    return AdaptationLogRepository(db_manager.connection)
