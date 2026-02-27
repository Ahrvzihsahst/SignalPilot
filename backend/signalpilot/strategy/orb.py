"""Opening Range Breakout (ORB) strategy implementation."""

import logging
from datetime import datetime, time

from signalpilot.config import AppConfig
from signalpilot.data.market_data_store import MarketDataStore
from signalpilot.db.models import CandidateSignal, SignalDirection
from signalpilot.strategy.base import BaseStrategy
from signalpilot.utils.constants import IST
from signalpilot.utils.market_calendar import StrategyPhase

logger = logging.getLogger(__name__)


class ORBStrategy(BaseStrategy):
    """Opening Range Breakout strategy.

    Detects breakouts above the 30-min opening range (9:15-9:45)
    with volume confirmation. Active during CONTINUOUS phase only
    (after opening range is locked).
    """

    def __init__(self, config: AppConfig, market_data: MarketDataStore) -> None:
        self._range_min_pct = config.orb_range_min_pct
        self._range_max_pct = config.orb_range_max_pct
        self._volume_multiplier = config.orb_volume_multiplier
        self._target_1_pct = config.orb_target_1_pct
        self._target_2_pct = config.orb_target_2_pct
        self._gap_exclusion_pct = config.orb_gap_exclusion_pct
        self._max_risk_pct = config.max_risk_pct

        # Parse signal window end time
        parts = config.orb_signal_window_end.split(":")
        self._signal_window_end = time(int(parts[0]), int(parts[1]))

        self._market_data = market_data
        self._signals_generated: set[str] = set()
        self._excluded_stocks: set[str] = set()

    @property
    def name(self) -> str:
        return "ORB"

    @property
    def active_phases(self) -> list[StrategyPhase]:
        return [StrategyPhase.CONTINUOUS]

    async def evaluate(
        self,
        market_data: MarketDataStore,
        current_phase: StrategyPhase,
    ) -> list[CandidateSignal]:
        """Evaluate ORB breakout conditions."""
        now = datetime.now(IST)
        if now.time() >= self._signal_window_end:
            return []
        return await self._scan_for_breakouts(market_data, now)

    async def _scan_for_breakouts(
        self, market_data: MarketDataStore, now: datetime
    ) -> list[CandidateSignal]:
        """Scan all symbols for breakout above opening range high."""
        signals: list[CandidateSignal] = []
        all_ticks = await market_data.get_all_ticks()

        for symbol, tick in all_ticks.items():
            if symbol in self._signals_generated or symbol in self._excluded_stocks:
                continue

            opening_range = await market_data.get_opening_range(symbol)
            if opening_range is None or not opening_range.locked:
                continue

            # Range size filter
            if (
                opening_range.range_size_pct < self._range_min_pct
                or opening_range.range_size_pct > self._range_max_pct
            ):
                continue

            # Breakout detection
            if tick.ltp <= opening_range.range_high:
                continue

            # Volume confirmation
            current_candle = await market_data.get_current_candle(symbol)
            avg_vol = await market_data.get_avg_candle_volume(symbol)
            if current_candle is None or avg_vol <= 0:
                continue
            if current_candle.volume < avg_vol * self._volume_multiplier:
                continue

            # SL at range low, risk cap check
            entry_price = tick.ltp
            stop_loss = opening_range.range_low
            risk_pct = (entry_price - stop_loss) / entry_price * 100
            if risk_pct > self._max_risk_pct:
                continue

            target_1 = entry_price * (1 + self._target_1_pct / 100)
            target_2 = entry_price * (1 + self._target_2_pct / 100)

            distance_pct = (
                (entry_price - opening_range.range_high) / opening_range.range_high
            ) * 100

            signal = CandidateSignal(
                symbol=symbol,
                direction=SignalDirection.BUY,
                strategy_name=self.name,
                entry_price=entry_price,
                stop_loss=stop_loss,
                target_1=target_1,
                target_2=target_2,
                gap_pct=opening_range.range_size_pct,
                volume_ratio=current_candle.volume / avg_vol if avg_vol > 0 else 0,
                price_distance_from_open_pct=distance_pct,
                reason=(
                    f"ORB breakout above {opening_range.range_high:.2f}, "
                    f"range {opening_range.range_size_pct:.1f}%, "
                    f"volume {current_candle.volume / avg_vol:.1f}x avg"
                ),
                generated_at=now,
            )
            signals.append(signal)
            self._signals_generated.add(symbol)
            logger.info(
                "ORB signal: %s entry=%.2f SL=%.2f T1=%.2f T2=%.2f",
                symbol, entry_price, stop_loss, target_1, target_2,
            )

        return signals

    def mark_gap_stock(self, symbol: str) -> None:
        """Exclude a stock from ORB scanning (called when Gap & Go detects 3%+ gap)."""
        self._excluded_stocks.add(symbol)

    def reset(self) -> None:
        """Reset per-session state. Called at start of each trading day."""
        self._signals_generated.clear()
        self._excluded_stocks.clear()
