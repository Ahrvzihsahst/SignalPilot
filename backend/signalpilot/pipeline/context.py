"""Mutable context object carrying intermediate state through pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from signalpilot.db.models import (
    CandidateSignal,
    FinalSignal,
    RankedSignal,
    SentimentResult,
    SuppressedSignal,
    UserConfig,
)
from signalpilot.utils.market_calendar import StrategyPhase


@dataclass
class ScanContext:
    """Mutable bag of state passed through every pipeline stage."""

    # Set by the pipeline runner
    cycle_id: str = ""
    now: datetime | None = None
    phase: StrategyPhase = StrategyPhase.OPENING
    accepting_signals: bool = True

    # Set by StrategyEvalStage
    user_config: UserConfig | None = None
    enabled_strategies: list = field(default_factory=list)
    all_candidates: list[CandidateSignal] = field(default_factory=list)

    # Set by ConfidenceStage
    confirmation_map: dict | None = None

    # Set by CompositeScoringStage
    composite_scores: dict | None = None

    # Set by RankingStage
    ranked_signals: list[RankedSignal] = field(default_factory=list)

    # Set by NewsSentimentStage
    sentiment_results: dict[str, SentimentResult] = field(default_factory=dict)
    suppressed_signals: list[SuppressedSignal] = field(default_factory=list)

    # Set by RiskSizingStage
    final_signals: list[FinalSignal] = field(default_factory=list)
    active_trade_count: int = 0

    # Set by RegimeContextStage (Phase 4: Market Regime Detection)
    regime: str | None = None                        # "TRENDING", "RANGING", "VOLATILE", or None
    regime_confidence: float = 0.0                   # 0.0-1.0
    regime_min_stars: int = 3                        # Minimum star threshold (3 = no filter)
    regime_position_modifier: float = 1.0            # 0.65x-1.0x multiplier (1.0 = no change)
    regime_max_positions: int | None = None           # Override (None = use config default)
    regime_strategy_weights: dict | None = None       # {"gap_go": 0.45, "orb": 0.35, "vwap": 0.20}
