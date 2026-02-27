"""Pydantic response and request schemas for the dashboard API."""

from __future__ import annotations

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Shared / utility schemas
# ---------------------------------------------------------------------------


class PaginationInfo(BaseModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int


class CircuitBreakerStatus(BaseModel):
    sl_count: int = 0
    sl_limit: int = 3
    is_active: bool = False
    is_overridden: bool = False
    triggered_at: str | None = None


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------


class SignalItem(BaseModel):
    id: int
    rank: int
    symbol: str
    strategy: str
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float
    quantity: int = 0
    capital_required: float = 0.0
    signal_strength: int = 0
    composite_score: float | None = None
    confirmation_level: str = "single"
    confirmed_by: str | None = None
    position_size_multiplier: float = 1.0
    status: str = "sent"
    current_price: float | None = None
    pnl_amount: float | None = None
    pnl_pct: float | None = None
    reason: str = ""
    setup_type: str | None = None
    adaptation_status: str = "normal"
    created_at: str = ""


class LiveSignalsResponse(BaseModel):
    market_status: str
    current_time: str
    capital: float
    positions_used: int
    positions_max: int
    today_pnl: float
    today_pnl_pct: float
    circuit_breaker: CircuitBreakerStatus
    active_signals: list[SignalItem]
    expired_signals: list[SignalItem]


class SignalHistoryResponse(BaseModel):
    signals: list[SignalItem]
    pagination: PaginationInfo


# ---------------------------------------------------------------------------
# Trades
# ---------------------------------------------------------------------------


class TradeItem(BaseModel):
    id: int
    signal_id: int = 0
    symbol: str
    strategy: str = "gap_go"
    entry_price: float
    exit_price: float | None = None
    stop_loss: float = 0.0
    target_1: float = 0.0
    target_2: float = 0.0
    quantity: int = 0
    pnl_amount: float | None = None
    pnl_pct: float | None = None
    exit_reason: str | None = None
    date: str = ""
    taken_at: str = ""
    exited_at: str | None = None


class TradeSummarySchema(BaseModel):
    total_trades: int = 0
    open_trades: int = 0
    closed_trades: int = 0
    total_pnl: float = 0.0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0


class TradesResponse(BaseModel):
    trades: list[TradeItem]
    summary: TradeSummarySchema
    pagination: PaginationInfo


# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------


class EquityCurvePoint(BaseModel):
    date: str
    cumulative_pnl: float


class EquityCurveResponse(BaseModel):
    data: list[EquityCurvePoint]


class DailyPnlPoint(BaseModel):
    date: str
    pnl: float
    trades_count: int = 0


class DailyPnlResponse(BaseModel):
    data: list[DailyPnlPoint]


class WinRatePoint(BaseModel):
    date: str
    win_rate: float
    trades_count: int = 0


class WinRateResponse(BaseModel):
    data: list[WinRatePoint]


class MonthlySummaryRow(BaseModel):
    month: str
    total_pnl: float
    trades_count: int
    wins: int
    losses: int
    win_rate: float


class MonthlySummaryResponse(BaseModel):
    data: list[MonthlySummaryRow]


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


class StrategyMetricsSchema(BaseModel):
    strategy: str
    total_signals: int = 0
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    expectancy: float = 0.0
    capital_weight_pct: float = 0.0


class StrategyComparisonResponse(BaseModel):
    strategies: list[StrategyMetricsSchema]


class ConfirmedPerformanceResponse(BaseModel):
    """Performance comparison: multi-confirmed vs single signals."""

    single_signals: int = 0
    single_win_rate: float = 0.0
    single_avg_pnl: float = 0.0
    multi_signals: int = 0
    multi_win_rate: float = 0.0
    multi_avg_pnl: float = 0.0


class StrategyPnlSeriesPoint(BaseModel):
    date: str
    strategy: str
    pnl: float


class StrategyPnlSeriesResponse(BaseModel):
    data: list[StrategyPnlSeriesPoint]


# ---------------------------------------------------------------------------
# Allocation
# ---------------------------------------------------------------------------


class AllocationItem(BaseModel):
    strategy: str
    weight_pct: float
    capital_allocated: float = 0.0


class AllocationResponse(BaseModel):
    total_capital: float
    allocations: list[AllocationItem]


class AllocationOverrideRequest(BaseModel):
    strategy: str
    weight_pct: float = Field(..., ge=0.0, le=100.0)


class AllocationHistoryItem(BaseModel):
    date: str
    strategy: str
    weight_pct: float


class AllocationHistoryResponse(BaseModel):
    data: list[AllocationHistoryItem]


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class SettingsResponse(BaseModel):
    total_capital: float = 50000.0
    max_positions: int = 8
    gap_go_enabled: bool = True
    orb_enabled: bool = True
    vwap_enabled: bool = True
    circuit_breaker_limit: int = 3
    confidence_boost_enabled: bool = True
    adaptive_learning_enabled: bool = True
    auto_rebalance_enabled: bool = True
    adaptation_mode: str = "aggressive"


class SettingsUpdateRequest(BaseModel):
    total_capital: float | None = None
    max_positions: int | None = None
    circuit_breaker_limit: int | None = None
    confidence_boost_enabled: bool | None = None
    adaptive_learning_enabled: bool | None = None
    auto_rebalance_enabled: bool | None = None
    adaptation_mode: str | None = None


class StrategyToggleRequest(BaseModel):
    gap_go_enabled: bool | None = None
    orb_enabled: bool | None = None
    vwap_enabled: bool | None = None


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------


class CircuitBreakerOverrideRequest(BaseModel):
    action: str = Field(..., pattern="^(override|reset)$")


class CircuitBreakerDetailResponse(BaseModel):
    date: str
    sl_count: int = 0
    sl_limit: int = 3
    is_active: bool = False
    is_overridden: bool = False
    triggered_at: str | None = None
    resumed_at: str | None = None
    override_at: str | None = None


class CircuitBreakerHistoryItem(BaseModel):
    date: str
    sl_count: int
    triggered_at: str | None = None
    resumed_at: str | None = None
    manual_override: bool = False
    override_at: str | None = None


class CircuitBreakerHistoryResponse(BaseModel):
    data: list[CircuitBreakerHistoryItem]


# ---------------------------------------------------------------------------
# Adaptation
# ---------------------------------------------------------------------------


class AdaptationStrategyStatus(BaseModel):
    strategy: str
    enabled: bool = True
    current_weight_pct: float = 0.0
    recent_win_rate: float = 0.0
    adaptation_status: str = "normal"


class AdaptationStatusResponse(BaseModel):
    mode: str = "aggressive"
    auto_rebalance_enabled: bool = True
    adaptive_learning_enabled: bool = True
    strategies: list[AdaptationStrategyStatus]


class AdaptationLogItem(BaseModel):
    id: int
    date: str
    strategy: str
    event_type: str
    details: str = ""
    old_weight: float | None = None
    new_weight: float | None = None
    created_at: str = ""


class AdaptationLogResponse(BaseModel):
    data: list[AdaptationLogItem]
    pagination: PaginationInfo
