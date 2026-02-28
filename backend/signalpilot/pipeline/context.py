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
