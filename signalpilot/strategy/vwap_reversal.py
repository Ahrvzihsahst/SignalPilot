"""VWAP Reversal strategy implementation."""

import logging
from datetime import datetime, time

from signalpilot.config import AppConfig
from signalpilot.data.market_data_store import MarketDataStore
from signalpilot.db.models import CandidateSignal, SignalDirection
from signalpilot.monitor.vwap_cooldown import VWAPCooldownTracker
from signalpilot.strategy.base import BaseStrategy
from signalpilot.utils.constants import IST
from signalpilot.utils.market_calendar import StrategyPhase

logger = logging.getLogger(__name__)


class VWAPReversalStrategy(BaseStrategy):
    """VWAP Reversal strategy.

    Identifies two setups:
    1. Uptrend Pullback: Price in uptrend pulls back to VWAP and bounces.
    2. VWAP Reclaim: Price trading below VWAP reclaims above it with volume.

    Active during CONTINUOUS phase (10:00 AM - 2:30 PM).
    """

    def __init__(
        self,
        config: AppConfig,
        market_data: MarketDataStore,
        cooldown_tracker: VWAPCooldownTracker,
    ) -> None:
        self._touch_threshold_pct = config.vwap_touch_threshold_pct
        self._reclaim_vol_mult = config.vwap_reclaim_volume_multiplier
        self._pullback_vol_mult = config.vwap_pullback_volume_multiplier
        self._setup1_sl_pct = config.vwap_setup1_sl_below_vwap_pct
        self._setup1_t1_pct = config.vwap_setup1_target1_pct
        self._setup1_t2_pct = config.vwap_setup1_target2_pct
        self._setup2_t1_pct = config.vwap_setup2_target1_pct
        self._setup2_t2_pct = config.vwap_setup2_target2_pct

        # Parse time windows
        start = config.vwap_scan_start.split(":")
        end = config.vwap_scan_end.split(":")
        self._scan_start = time(int(start[0]), int(start[1]))
        self._scan_end = time(int(end[0]), int(end[1]))

        self._market_data = market_data
        self._cooldown = cooldown_tracker
        self._last_evaluated_candle: dict[str, datetime] = {}

    @property
    def name(self) -> str:
        return "VWAP Reversal"

    @property
    def active_phases(self) -> list[StrategyPhase]:
        return [StrategyPhase.CONTINUOUS]

    async def evaluate(
        self,
        market_data: MarketDataStore,
        current_phase: StrategyPhase,
    ) -> list[CandidateSignal]:
        """Evaluate VWAP reversal conditions."""
        now = datetime.now(IST)
        current_time = now.time()
        if current_time < self._scan_start or current_time >= self._scan_end:
            return []
        return await self._scan_for_setups(market_data, now)

    async def _scan_for_setups(
        self, market_data: MarketDataStore, now: datetime
    ) -> list[CandidateSignal]:
        """Scan all symbols for VWAP reversal setups."""
        signals: list[CandidateSignal] = []
        all_ticks = await market_data.get_all_ticks()

        for symbol in all_ticks:
            if not self._cooldown.can_signal(symbol, now):
                continue

            completed = await market_data.get_completed_candles(symbol)
            if len(completed) < 2:
                continue

            # Skip if we already evaluated this candle
            last_candle = completed[-1]
            prev_eval = self._last_evaluated_candle.get(symbol)
            if prev_eval and prev_eval >= last_candle.start_time:
                continue

            vwap = await market_data.get_vwap(symbol)
            if vwap is None or vwap <= 0:
                continue

            avg_vol = await market_data.get_avg_candle_volume(symbol)
            if avg_vol <= 0:
                continue

            # Check Setup 1: Uptrend Pullback
            signal = self._check_uptrend_pullback(
                symbol, completed, vwap, avg_vol, now
            )
            if signal:
                signals.append(signal)
                self._cooldown.record_signal(symbol, now)
                self._last_evaluated_candle[symbol] = last_candle.start_time
                continue

            # Check Setup 2: VWAP Reclaim
            signal = self._check_vwap_reclaim(
                symbol, completed, vwap, avg_vol, now
            )
            if signal:
                signals.append(signal)
                self._cooldown.record_signal(symbol, now)
                self._last_evaluated_candle[symbol] = last_candle.start_time

        return signals

    def _check_uptrend_pullback(
        self,
        symbol: str,
        candles: list,
        vwap: float,
        avg_vol: float,
        now: datetime,
    ) -> CandidateSignal | None:
        """Setup 1: Uptrend pullback to VWAP.

        Conditions:
        - Prior candle(s) closed above VWAP (uptrend)
        - Price touched or dipped near VWAP (within threshold)
        - Current candle closes above VWAP
        - Volume on bounce candle >= avg candle volume
        """
        if len(candles) < 2:
            return None

        current = candles[-1]
        prior = candles[-2]

        # Prior candle must close above VWAP
        if prior.close <= vwap:
            return None

        # Current candle must have touched near VWAP
        touch_distance = abs(current.low - vwap) / vwap * 100
        if touch_distance > self._touch_threshold_pct and current.low > vwap:
            return None

        # Current candle must close above VWAP
        if current.close <= vwap:
            return None

        # Volume check
        if current.volume < avg_vol * self._pullback_vol_mult:
            return None

        entry_price = current.close
        stop_loss = vwap * (1 - self._setup1_sl_pct / 100)
        target_1 = entry_price * (1 + self._setup1_t1_pct / 100)
        target_2 = entry_price * (1 + self._setup1_t2_pct / 100)

        # Trend alignment for scoring
        candles_above = sum(1 for c in candles[:-1] if c.close > vwap)
        trend_ratio = candles_above / len(candles[:-1]) if len(candles) > 1 else 0

        touch_pct = touch_distance
        vol_ratio = current.volume / avg_vol if avg_vol > 0 else 0

        logger.info(
            "VWAP Setup 1 (Uptrend Pullback): %s entry=%.2f SL=%.2f",
            symbol, entry_price, stop_loss,
        )

        return CandidateSignal(
            symbol=symbol,
            direction=SignalDirection.BUY,
            strategy_name=self.name,
            entry_price=entry_price,
            stop_loss=stop_loss,
            target_1=target_1,
            target_2=target_2,
            gap_pct=trend_ratio,  # reused for trend alignment scoring
            volume_ratio=vol_ratio,
            price_distance_from_open_pct=touch_pct,  # reused for touch precision scoring
            reason=(
                f"VWAP pullback bounce at {vwap:.2f}, "
                f"volume {vol_ratio:.1f}x avg"
            ),
            generated_at=now,
            setup_type="uptrend_pullback",
        )

    def _check_vwap_reclaim(
        self,
        symbol: str,
        candles: list,
        vwap: float,
        avg_vol: float,
        now: datetime,
    ) -> CandidateSignal | None:
        """Setup 2: VWAP Reclaim.

        Conditions:
        - Prior candle(s) closed below VWAP
        - Current candle closes above VWAP
        - Volume on reclaim candle >= 1.5x avg volume (higher threshold)
        """
        if len(candles) < 2:
            return None

        current = candles[-1]
        prior = candles[-2]

        # Prior candle must close below VWAP
        if prior.close >= vwap:
            return None

        # Current candle must close above VWAP
        if current.close <= vwap:
            return None

        # Higher volume threshold for reclaim
        if current.volume < avg_vol * self._reclaim_vol_mult:
            return None

        entry_price = current.close
        # SL below recent swing low (lowest low of last 3 candles)
        recent_lows = [c.low for c in candles[-3:]]
        stop_loss = min(recent_lows)

        target_1 = entry_price * (1 + self._setup2_t1_pct / 100)
        target_2 = entry_price * (1 + self._setup2_t2_pct / 100)

        touch_pct = abs(current.close - vwap) / vwap * 100
        vol_ratio = current.volume / avg_vol if avg_vol > 0 else 0

        # Trend alignment
        candles_above = sum(1 for c in candles[:-1] if c.close > vwap)
        trend_ratio = candles_above / len(candles[:-1]) if len(candles) > 1 else 0

        logger.info(
            "VWAP Setup 2 (Reclaim): %s entry=%.2f SL=%.2f [Higher Risk]",
            symbol, entry_price, stop_loss,
        )

        return CandidateSignal(
            symbol=symbol,
            direction=SignalDirection.BUY,
            strategy_name=self.name,
            entry_price=entry_price,
            stop_loss=stop_loss,
            target_1=target_1,
            target_2=target_2,
            gap_pct=trend_ratio,
            volume_ratio=vol_ratio,
            price_distance_from_open_pct=touch_pct,
            reason=(
                f"VWAP reclaim above {vwap:.2f}, "
                f"volume {vol_ratio:.1f}x avg [Higher Risk]"
            ),
            generated_at=now,
            setup_type="vwap_reclaim",
        )

    def reset(self) -> None:
        """Reset per-session state. Called at start of each trading day."""
        self._last_evaluated_candle.clear()
        self._cooldown.reset()
