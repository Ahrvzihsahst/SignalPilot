"""FastAPI dependency injection for dashboard routes."""

from __future__ import annotations

from fastapi import Request

from signalpilot.db.adaptation_log_repo import AdaptationLogRepository
from signalpilot.db.circuit_breaker_repo import CircuitBreakerRepository
from signalpilot.db.config_repo import ConfigRepository
from signalpilot.db.hybrid_score_repo import HybridScoreRepository
from signalpilot.db.metrics import MetricsCalculator
from signalpilot.db.signal_repo import SignalRepository
from signalpilot.db.strategy_performance_repo import StrategyPerformanceRepository
from signalpilot.db.trade_repo import TradeRepository


def get_read_conn(request: Request):
    """Return the read-only database connection."""
    return request.app.state.read_conn


def get_write_conn(request: Request):
    """Return the writable database connection (may be None)."""
    return request.app.state.write_conn


def get_signal_repo(request: Request) -> SignalRepository:
    return SignalRepository(request.app.state.read_conn)


def get_trade_repo(request: Request) -> TradeRepository:
    return TradeRepository(request.app.state.read_conn)


def get_config_repo(request: Request) -> ConfigRepository:
    return ConfigRepository(request.app.state.read_conn)


def get_metrics(request: Request) -> MetricsCalculator:
    return MetricsCalculator(request.app.state.read_conn)


def get_hybrid_score_repo(request: Request) -> HybridScoreRepository:
    return HybridScoreRepository(request.app.state.read_conn)


def get_circuit_breaker_repo(request: Request) -> CircuitBreakerRepository:
    return CircuitBreakerRepository(request.app.state.read_conn)


def get_adaptation_log_repo(request: Request) -> AdaptationLogRepository:
    return AdaptationLogRepository(request.app.state.read_conn)


def get_strategy_perf_repo(request: Request) -> StrategyPerformanceRepository:
    return StrategyPerformanceRepository(request.app.state.read_conn)
