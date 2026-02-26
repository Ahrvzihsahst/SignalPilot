"""Gap & Go intraday strategy implementation."""

import logging
from dataclasses import dataclass
from datetime import datetime

from signalpilot.config import AppConfig
from signalpilot.data.market_data_store import MarketDataStore
from signalpilot.db.models import CandidateSignal, SignalDirection
from signalpilot.strategy.base import BaseStrategy
from signalpilot.utils.constants import IST
from signalpilot.utils.market_calendar import StrategyPhase

logger = logging.getLogger("signalpilot.strategy.gap_and_go")


@dataclass
class _GapCandidate:
    """Internal state for a stock identified as a gap candidate."""

    symbol: str
    open_price: float
    prev_close: float
    prev_high: float
    gap_pct: float


class GapAndGoStrategy(BaseStrategy):
    """Gap & Go strategy: identifies stocks that gap up 3-5% at open
    with strong volume, then hold above opening price.

    Phase behaviour:
    - OPENING (9:15-9:30 AM): detect gaps, accumulate volume.
    - ENTRY_WINDOW (9:30-9:45 AM): validate price hold, generate signals.
    """

    def __init__(self, config: AppConfig) -> None:
        self._gap_min_pct = config.gap_min_pct
        self._gap_max_pct = config.gap_max_pct
        self._volume_threshold_pct = config.volume_threshold_pct
        self._target_1_pct = config.target_1_pct
        self._target_2_pct = config.target_2_pct
        self._max_risk_pct = config.max_risk_pct

        # Per-session state (reset daily)
        self._gap_candidates: dict[str, _GapCandidate] = {}
        self._volume_validated: set[str] = set()
        self._disqualified: set[str] = set()
        self._signals_generated: set[str] = set()

    @property
    def name(self) -> str:
        return "Gap & Go"

    @property
    def active_phases(self) -> list[StrategyPhase]:
        return [StrategyPhase.OPENING, StrategyPhase.ENTRY_WINDOW]

    async def evaluate(
        self,
        market_data: MarketDataStore,
        current_phase: StrategyPhase,
    ) -> list[CandidateSignal]:
        """Phase-dependent evaluation.

        OPENING: detect gap candidates, accumulate volume, validate volume at boundary.
        ENTRY_WINDOW: validate price hold, generate signals.
        """
        if current_phase == StrategyPhase.OPENING:
            return await self._detect_gaps_and_accumulate_volume(market_data)
        if current_phase == StrategyPhase.ENTRY_WINDOW:
            return await self._validate_and_generate_signals(market_data)
        return []

    async def _detect_gaps_and_accumulate_volume(
        self, market_data: MarketDataStore
    ) -> list[CandidateSignal]:
        """Scan all symbols for gap-up conditions and validate volume.

        During OPENING phase (9:15-9:30 AM):
        1. Identify stocks gapping up 3-5% where open > prev high.
        2. Track volume accumulation.
        3. At each evaluation: check if cumulative volume > threshold.

        Returns empty list (signals are not generated during this phase).
        """
        all_ticks = await market_data.get_all_ticks()

        for symbol, tick in all_ticks.items():
            if symbol in self._disqualified:
                continue

            # Already a validated candidate, check volume
            if symbol in self._gap_candidates and symbol not in self._volume_validated:
                volume = await market_data.get_accumulated_volume(symbol)
                hist = await market_data.get_historical(symbol)
                if hist is not None and hist.average_daily_volume > 0:
                    volume_ratio = (volume / hist.average_daily_volume) * 100
                    if volume_ratio >= self._volume_threshold_pct:
                        self._volume_validated.add(symbol)
                        logger.info(
                            "%s volume validated: ratio=%.1f%% (threshold=%.1f%%)",
                            symbol,
                            volume_ratio,
                            self._volume_threshold_pct,
                        )
                continue

            # New symbol — check gap conditions
            if symbol in self._gap_candidates:
                continue

            hist = await market_data.get_historical(symbol)
            if hist is None:
                continue

            gap_pct = self._calculate_gap_percentage(tick.open_price, hist.previous_close)

            # Gap must be within range
            if gap_pct < self._gap_min_pct or gap_pct > self._gap_max_pct:
                continue

            # Open must be above previous day's high
            if tick.open_price <= hist.previous_high:
                continue

            self._gap_candidates[symbol] = _GapCandidate(
                symbol=symbol,
                open_price=tick.open_price,
                prev_close=hist.previous_close,
                prev_high=hist.previous_high,
                gap_pct=gap_pct,
            )
            logger.info(
                "Gap candidate: %s gap=%.2f%% open=%.2f prev_close=%.2f prev_high=%.2f",
                symbol,
                gap_pct,
                tick.open_price,
                hist.previous_close,
                hist.previous_high,
            )

            # Immediately check volume for this new candidate
            volume = await market_data.get_accumulated_volume(symbol)
            if hist.average_daily_volume > 0:
                volume_ratio = (volume / hist.average_daily_volume) * 100
                if volume_ratio >= self._volume_threshold_pct:
                    self._volume_validated.add(symbol)
                    logger.info(
                        "%s volume validated on detection: ratio=%.1f%%",
                        symbol,
                        volume_ratio,
                    )

        return []

    async def _validate_and_generate_signals(
        self, market_data: MarketDataStore
    ) -> list[CandidateSignal]:
        """Validate price hold above open and generate signals.

        First, continue volume validation for candidates that didn't reach
        the threshold during OPENING phase (extends the window to 30 min).
        Then, for each volume-validated gap candidate:
        - If current price > opening price → generate CandidateSignal.
        - If price drops below open → disqualify.
        """
        # Continue volume validation for candidates not yet validated
        for symbol in list(self._gap_candidates):
            if symbol in self._volume_validated or symbol in self._disqualified:
                continue
            volume = await market_data.get_accumulated_volume(symbol)
            hist = await market_data.get_historical(symbol)
            if hist is not None and hist.average_daily_volume > 0:
                volume_ratio = (volume / hist.average_daily_volume) * 100
                if volume_ratio >= self._volume_threshold_pct:
                    self._volume_validated.add(symbol)
                    logger.info(
                        "%s volume validated (entry_window): ratio=%.1f%%",
                        symbol,
                        volume_ratio,
                    )

        signals: list[CandidateSignal] = []
        now = datetime.now(IST)

        for symbol in list(self._volume_validated):
            if symbol in self._disqualified or symbol in self._signals_generated:
                continue

            candidate = self._gap_candidates.get(symbol)
            if candidate is None:
                continue

            tick = await market_data.get_tick(symbol)
            if tick is None:
                continue

            # Disqualify if price at or below opening price (spec: must hold ABOVE)
            if tick.ltp <= candidate.open_price:
                self._disqualified.add(symbol)
                self._volume_validated.discard(symbol)
                logger.info(
                    "%s disqualified: price %.2f below open %.2f",
                    symbol,
                    tick.ltp,
                    candidate.open_price,
                )
                continue

            # Price holds above open — generate signal
            entry_price = tick.ltp
            stop_loss = self._calculate_stop_loss(entry_price, candidate.open_price)
            target_1, target_2 = self._calculate_targets(entry_price)

            hist = await market_data.get_historical(symbol)
            if hist is None or hist.average_daily_volume <= 0:
                logger.warning("%s missing historical data at signal generation", symbol)
                continue

            volume = await market_data.get_accumulated_volume(symbol)
            volume_ratio = volume / hist.average_daily_volume

            price_distance_pct = ((entry_price - candidate.open_price) / candidate.open_price) * 100

            signal = CandidateSignal(
                symbol=symbol,
                direction=SignalDirection.BUY,
                strategy_name=self.name,
                entry_price=entry_price,
                stop_loss=stop_loss,
                target_1=target_1,
                target_2=target_2,
                gap_pct=candidate.gap_pct,
                volume_ratio=volume_ratio,
                price_distance_from_open_pct=price_distance_pct,
                reason=(
                    f"Gap up {candidate.gap_pct:.1f}% above prev close "
                    f"({candidate.prev_close:.2f}), "
                    f"open above prev high ({candidate.prev_high:.2f}), "
                    f"volume ratio {volume_ratio:.1f}x ADV"
                ),
                generated_at=now,
            )

            signals.append(signal)
            self._signals_generated.add(symbol)
            logger.info(
                "Signal generated: %s entry=%.2f SL=%.2f T1=%.2f T2=%.2f",
                symbol,
                entry_price,
                stop_loss,
                target_1,
                target_2,
            )

        return signals

    def _calculate_gap_percentage(self, open_price: float, prev_close: float) -> float:
        """Calculate gap percentage from previous close."""
        return ((open_price - prev_close) / prev_close) * 100

    def _calculate_stop_loss(self, entry_price: float, open_price: float) -> float:
        """Calculate stop loss.

        SL = opening price, but risk is capped at max_risk_pct from entry.
        If opening price is too far below entry, SL is raised to cap risk.
        """
        sl = open_price
        max_sl = entry_price * (1 - self._max_risk_pct / 100)
        return max(sl, max_sl)

    def _calculate_targets(self, entry_price: float) -> tuple[float, float]:
        """Calculate target prices."""
        target_1 = entry_price * (1 + self._target_1_pct / 100)
        target_2 = entry_price * (1 + self._target_2_pct / 100)
        return target_1, target_2

    def reset(self) -> None:
        """Reset all per-session state. Called at the start of each trading day."""
        self._gap_candidates.clear()
        self._volume_validated.clear()
        self._disqualified.clear()
        self._signals_generated.clear()
