"""Core data models for SignalPilot.

All data models are Python dataclasses, serving as the contract between components.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum

# Re-export StrategyPhase from its canonical location
from signalpilot.utils.constants import IST
from signalpilot.utils.market_calendar import StrategyPhase

__all__ = [
    # Enums
    "SignalDirection",
    "ExitType",
    "StrategyPhase",
    # Instrument & Market Data
    "Instrument",
    "TickData",
    "HistoricalReference",
    "PreviousDayData",
    # Strategy
    "CandidateSignal",
    # Ranking
    "RankedSignal",
    "ScoringWeights",
    # Risk / Delivery
    "PositionSize",
    "FinalSignal",
    # Database Records
    "SignalRecord",
    "TradeRecord",
    "UserConfig",
    # Exit Monitor
    "ExitAlert",
    # Phase 4: Quick Action Buttons
    "SignalActionRecord",
    "WatchlistRecord",
    "CallbackResult",
    # Performance
    "PerformanceMetrics",
    "DailySummary",
    "StrategyDaySummary",
    "StrategyPerformanceRecord",
    # Phase 3
    "HybridScoreRecord",
    "CircuitBreakerRecord",
    "AdaptationLogRecord",
    # Phase 4: News Sentiment Filter
    "SentimentResult",
    "SuppressedSignal",
    "NewsSentimentRecord",
    "EarningsCalendarRecord",
    # Phase 4: Market Regime Detection
    "RegimeClassification",
    "RegimePerformanceRecord",
]


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SignalDirection(Enum):
    """Direction of a trading signal."""

    BUY = "BUY"
    SELL = "SELL"


class ExitType(Enum):
    """Reason a trade was exited."""

    SL_HIT = "sl_hit"
    T1_HIT = "t1_hit"
    T2_HIT = "t2_hit"
    TRAILING_SL_HIT = "trailing_sl"
    TIME_EXIT = "time_exit"


# ---------------------------------------------------------------------------
# Instrument & Market Data
# ---------------------------------------------------------------------------


@dataclass
class Instrument:
    """Represents an NSE instrument from the Nifty 500 universe."""

    symbol: str                 # e.g., "SBIN"
    name: str                   # e.g., "State Bank of India"
    angel_token: str            # e.g., "3045"
    exchange: str               # "NSE"
    nse_symbol: str             # e.g., "SBIN-EQ" (Angel One format)
    yfinance_symbol: str        # e.g., "SBIN.NS"
    lot_size: int = 1


@dataclass
class TickData:
    """Real-time tick data received from WebSocket."""

    symbol: str
    ltp: float                  # Last Traded Price
    open_price: float
    high: float
    low: float
    close: float                # Previous day close (from tick feed)
    volume: int                 # Cumulative volume for the day
    last_traded_timestamp: datetime
    updated_at: datetime


@dataclass
class HistoricalReference:
    """Pre-market reference data used for gap detection and volume validation."""

    previous_close: float
    previous_high: float
    average_daily_volume: float


@dataclass
class PreviousDayData:
    """Full previous day OHLCV data."""

    close: float
    high: float
    low: float
    open: float
    volume: int


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------


@dataclass
class CandidateSignal:
    """A raw signal produced by a strategy before ranking and filtering."""

    symbol: str
    direction: SignalDirection
    strategy_name: str
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float
    gap_pct: float = 0.0
    volume_ratio: float = 0.0
    price_distance_from_open_pct: float = 0.0
    reason: str = ""
    generated_at: datetime = field(default_factory=datetime.now)
    setup_type: str | None = None
    strategy_specific_score: float | None = None


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------


@dataclass
class ScoringWeights:
    """Configurable weights for multi-factor signal scoring."""

    gap_pct_weight: float = 0.40
    volume_ratio_weight: float = 0.35
    price_distance_weight: float = 0.25


@dataclass
class RankedSignal:
    """A candidate signal that has been scored and ranked."""

    candidate: CandidateSignal
    composite_score: float
    rank: int
    signal_strength: int        # 1-5 stars


# ---------------------------------------------------------------------------
# Risk / Delivery
# ---------------------------------------------------------------------------


@dataclass
class PositionSize:
    """Result of position sizing calculation."""

    quantity: int
    capital_required: float
    per_trade_capital: float


@dataclass
class FinalSignal:
    """A fully processed signal ready for delivery via Telegram."""

    ranked_signal: RankedSignal
    quantity: int
    capital_required: float
    expires_at: datetime


# ---------------------------------------------------------------------------
# Database Records
# ---------------------------------------------------------------------------


@dataclass
class SignalRecord:
    """Persistent record for the signals table."""

    id: int | None = None
    date: date = field(default_factory=date.today)
    symbol: str = ""
    strategy: str = ""
    entry_price: float = 0.0
    stop_loss: float = 0.0
    target_1: float = 0.0
    target_2: float = 0.0
    quantity: int = 0
    capital_required: float = 0.0
    signal_strength: int = 0
    gap_pct: float = 0.0
    volume_ratio: float = 0.0
    reason: str = ""
    created_at: datetime | None = None
    expires_at: datetime | None = None
    # "sent" | "taken" | "expired" | "paper" | "position_full" | "skipped"
    status: str = "sent"
    setup_type: str | None = None
    strategy_specific_score: float | None = None
    # Phase 3 fields
    composite_score: float | None = None
    confirmation_level: str | None = None
    confirmed_by: str | None = None
    position_size_multiplier: float = 1.0
    adaptation_status: str = "normal"
    # Phase 4: News Sentiment Filter fields
    news_sentiment_score: float | None = None
    news_sentiment_label: str | None = None
    news_top_headline: str | None = None
    news_action: str | None = None
    original_star_rating: int | None = None
    # Phase 4: Market Regime Detection fields
    market_regime: str | None = None
    regime_confidence: float | None = None
    regime_weight_modifier: float | None = None


@dataclass
class TradeRecord:
    """Persistent record for the trades table."""

    id: int | None = None
    signal_id: int = 0
    date: date = field(default_factory=date.today)
    symbol: str = ""
    strategy: str = "gap_go"
    entry_price: float = 0.0
    exit_price: float | None = None
    stop_loss: float = 0.0
    target_1: float = 0.0
    target_2: float = 0.0
    quantity: int = 0
    pnl_amount: float | None = None
    pnl_pct: float | None = None
    exit_reason: str | None = None
    taken_at: datetime | None = None
    exited_at: datetime | None = None


@dataclass
class UserConfig:
    """Persistent record for the user_config table."""

    id: int | None = None
    telegram_chat_id: str = ""
    total_capital: float = 50000.0
    max_positions: int = 8
    gap_go_enabled: bool = True
    orb_enabled: bool = True
    vwap_enabled: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
    # Phase 3 fields
    circuit_breaker_limit: int = 3
    confidence_boost_enabled: bool = True
    adaptive_learning_enabled: bool = True
    auto_rebalance_enabled: bool = True
    adaptation_mode: str = "aggressive"


# ---------------------------------------------------------------------------
# Exit Monitor
# ---------------------------------------------------------------------------


@dataclass
class ExitAlert:
    """Alert generated by the exit monitor for Telegram delivery."""

    trade: TradeRecord
    exit_type: ExitType | None
    current_price: float
    pnl_pct: float
    is_alert_only: bool         # True for T1 advisory, False for actual exits
    trailing_sl_update: float | None = None
    keyboard_type: str | None = None  # "t1", "t2", "sl_approaching", "near_t2"


# ---------------------------------------------------------------------------
# Phase 4: Quick Action Buttons
# ---------------------------------------------------------------------------


@dataclass
class SignalActionRecord:
    """Record of a user action on a signal (taken/skip/watch via button or text)."""

    id: int | None = None
    signal_id: int = 0
    action: str = ""             # "taken", "skip", "watch"
    # skip reason code: "no_capital", "low_confidence", "sector", "other"
    reason: str | None = None
    response_time_ms: int | None = None
    acted_at: datetime | None = None
    message_id: int | None = None


@dataclass
class WatchlistRecord:
    """A stock on the user's watchlist for re-alert on future signals."""

    id: int | None = None
    symbol: str = ""
    signal_id: int | None = None
    strategy: str = ""
    entry_price: float = 0.0
    added_at: datetime | None = None
    expires_at: datetime | None = None
    triggered_count: int = 0
    last_triggered_at: datetime | None = None


@dataclass
class CallbackResult:
    """Result of processing an inline keyboard callback."""

    answer_text: str = ""
    success: bool = True
    status_line: str | None = None
    new_keyboard: object | None = None  # InlineKeyboardMarkup or None


# ---------------------------------------------------------------------------
# Performance Metrics
# ---------------------------------------------------------------------------


@dataclass
class PerformanceMetrics:
    """Aggregated performance metrics for the JOURNAL command."""

    date_range_start: date
    date_range_end: date
    total_signals: int
    trades_taken: int
    wins: int
    losses: int
    win_rate: float
    total_pnl: float
    avg_win: float
    avg_loss: float
    risk_reward_ratio: float
    best_trade_symbol: str
    best_trade_pnl: float
    worst_trade_symbol: str
    worst_trade_pnl: float


@dataclass
class DailySummary:
    """End-of-day summary sent at 3:30 PM."""

    date: date
    signals_sent: int
    trades_taken: int
    wins: int
    losses: int
    total_pnl: float
    cumulative_pnl: float
    trades: list[TradeRecord] = field(default_factory=list)
    strategy_breakdown: dict[str, "StrategyDaySummary"] | None = None


@dataclass
class StrategyDaySummary:
    """Per-strategy breakdown within a daily summary."""

    strategy_name: str
    signals_generated: int
    signals_taken: int
    pnl: float


@dataclass
class StrategyPerformanceRecord:
    """Aggregated strategy performance record for a single date."""

    id: int | None = None
    strategy: str = ""
    date: str = ""
    signals_generated: int = 0
    signals_taken: int = 0
    wins: int = 0
    losses: int = 0
    total_pnl: float = 0.0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    expectancy: float = 0.0
    capital_weight_pct: float = 0.0


# ---------------------------------------------------------------------------
# Phase 3: Hybrid Scoring, Circuit Breaker, Adaptation
# ---------------------------------------------------------------------------


@dataclass
class HybridScoreRecord:
    """Persistent record for the hybrid_scores table."""

    id: int | None = None
    signal_id: int = 0
    composite_score: float = 0.0
    strategy_strength_score: float = 0.0
    win_rate_score: float = 0.0
    risk_reward_score: float = 0.0
    confirmation_bonus: float = 0.0
    confirmed_by: str | None = None
    confirmation_level: str = "single"
    position_size_multiplier: float = 1.0
    created_at: datetime | None = None


@dataclass
class CircuitBreakerRecord:
    """Persistent record for the circuit_breaker_log table."""

    id: int | None = None
    date: date = field(default_factory=date.today)
    sl_count: int = 0
    triggered_at: datetime | None = None
    resumed_at: datetime | None = None
    manual_override: bool = False
    override_at: datetime | None = None


@dataclass
class AdaptationLogRecord:
    """Persistent record for the adaptation_log table."""

    id: int | None = None
    date: date = field(default_factory=date.today)
    strategy: str = ""
    event_type: str = ""
    details: str = ""
    old_weight: float | None = None
    new_weight: float | None = None
    created_at: datetime | None = None


# ---------------------------------------------------------------------------
# Phase 4: News Sentiment Filter
# ---------------------------------------------------------------------------


@dataclass
class SentimentResult:
    """Per-stock sentiment output carried through the pipeline via ScanContext."""

    score: float
    label: str
    headline: str | None
    action: str
    headline_count: int
    top_negative_headline: str | None
    model_used: str


@dataclass
class SuppressedSignal:
    """A signal removed by the news sentiment filter before delivery."""

    symbol: str
    strategy: str
    original_stars: int
    sentiment_score: float
    sentiment_label: str
    top_headline: str | None
    reason: str
    entry_price: float
    stop_loss: float
    target_1: float


@dataclass
class NewsSentimentRecord:
    """Persistent record for the news_sentiment table."""

    id: int | None = None
    stock_code: str = ""
    headline: str = ""
    source: str = ""
    published_at: datetime | None = None
    positive_score: float = 0.0
    negative_score: float = 0.0
    neutral_score: float = 0.0
    composite_score: float = 0.0
    sentiment_label: str = ""
    fetched_at: datetime | None = None
    model_used: str = ""


@dataclass
class EarningsCalendarRecord:
    """Persistent record for the earnings_calendar table."""

    id: int | None = None
    stock_code: str = ""
    earnings_date: date | None = None
    quarter: str = ""
    source: str = ""
    is_confirmed: bool = False
    updated_at: datetime | None = None


# ---------------------------------------------------------------------------
# Phase 4: Market Regime Detection
# ---------------------------------------------------------------------------


@dataclass
class RegimeClassification:
    """Classification result from MarketRegimeClassifier.

    Represents a single regime classification with all inputs, scores,
    derived modifiers, and metadata.
    """

    regime: str                              # "TRENDING", "RANGING", "VOLATILE"
    confidence: float                        # 0.0-1.0
    trending_score: float = 0.0
    ranging_score: float = 0.0
    volatile_score: float = 0.0
    # Raw inputs
    india_vix: float | None = None
    nifty_gap_pct: float | None = None
    nifty_first_15_range_pct: float | None = None
    nifty_first_15_direction: str | None = None  # 'UP', 'DOWN', 'FLAT'
    directional_alignment: float | None = None
    sp500_change_pct: float | None = None
    sgx_direction: str | None = None             # 'UP', 'DOWN', 'FLAT'
    fii_net_crores: float | None = None
    dii_net_crores: float | None = None
    prev_day_range_pct: float | None = None
    # Derived modifiers
    strategy_weights: dict[str, float] = field(default_factory=dict)
    min_star_rating: int = 3
    max_positions: int | None = None
    position_size_modifier: float = 1.0
    # Metadata
    is_reclassification: bool = False
    previous_regime: str | None = None
    classified_at: datetime = field(default_factory=lambda: datetime.now(IST))


@dataclass
class RegimePerformanceRecord:
    """Daily strategy performance under a specific regime."""

    id: int | None = None
    regime_date: date = field(default_factory=lambda: datetime.now(IST).date())
    regime: str = ""                    # "TRENDING", "RANGING", "VOLATILE"
    strategy: str = ""                  # "Gap & Go", "ORB", "VWAP Reversal"
    signals_generated: int = 0
    signals_taken: int = 0
    wins: int = 0
    losses: int = 0
    pnl: float = 0.0
    win_rate: float | None = None
    created_at: datetime | None = None
