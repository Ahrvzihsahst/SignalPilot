"""Market Regime Classifier for SignalPilot."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime

from signalpilot.db.models import RegimeClassification
from signalpilot.intelligence.regime_data import RegimeDataCollector, RegimeInputs
from signalpilot.utils.constants import IST

logger = logging.getLogger(__name__)

# Severity ordering for re-classification: only upgrades allowed
_SEVERITY_ORDER = {"TRENDING": 0, "RANGING": 1, "VOLATILE": 2}


class MarketRegimeClassifier:
    """Classifies the market regime and caches the result in memory.

    The classifier runs once at 9:30 AM via a scheduler job. Re-classification
    checkpoints at 11:00 AM, 1:00 PM, and 2:30 PM evaluate trigger conditions.
    The pipeline stage reads the in-memory cache in <1ms per cycle.
    """

    def __init__(
        self,
        data_collector: RegimeDataCollector,
        regime_repo,           # MarketRegimeRepository
        config,                # AppConfig
    ) -> None:
        self._data_collector = data_collector
        self._regime_repo = regime_repo
        self._config = config
        self._cache: dict[date, RegimeClassification] = {}
        self._reclass_count: dict[date, int] = {}
        self._morning_vix: dict[date, float] = {}

    def get_cached_regime(self, for_date: date | None = None) -> RegimeClassification | None:
        """Return the cached regime classification for the given date. <1ms."""
        target = for_date or datetime.now(IST).date()
        return self._cache.get(target)

    async def classify(self) -> RegimeClassification:
        """Run the initial 9:30 AM classification."""
        inputs = await self._data_collector.collect_regime_inputs()

        vix_score = self._compute_vix_score(inputs.india_vix)
        gap_score = self._compute_gap_score(inputs.nifty_gap_pct)
        range_score = self._compute_range_score(inputs.nifty_first_15_range_pct)
        alignment = self._compute_alignment(
            inputs.nifty_gap_pct,
            inputs.nifty_first_15_direction,
            inputs.sgx_direction,
            inputs.sp500_change_pct,
        )

        classification = self._classify_from_scores(
            vix_score, gap_score, range_score, alignment, inputs,
        )

        today = datetime.now(IST).date()
        if inputs.india_vix is not None:
            self._morning_vix[today] = inputs.india_vix

        self._cache[today] = classification

        try:
            await self._regime_repo.insert_classification(classification)
        except Exception:
            logger.exception("Failed to persist regime classification")

        logger.info(
            "Regime classified: %s (confidence: %.2f, trending=%.3f, ranging=%.3f, volatile=%.3f)",
            classification.regime, classification.confidence,
            classification.trending_score, classification.ranging_score,
            classification.volatile_score,
        )
        return classification

    async def check_reclassify(self, checkpoint: str) -> RegimeClassification | None:
        """Evaluate re-classification at a checkpoint ('11:00'|'13:00'|'14:30')."""
        today = datetime.now(IST).date()
        current = self._cache.get(today)
        if current is None:
            logger.debug("No classification to re-evaluate at %s", checkpoint)
            return None

        max_reclass = getattr(self._config, "regime_max_reclassifications", 2)
        count = self._reclass_count.get(today, 0)
        if count >= max_reclass:
            logger.info("Max re-classifications (%d) reached for today", max_reclass)
            return None

        triggered = False
        trigger_reason = ""

        if checkpoint == "11:00":
            triggered, trigger_reason = await self._check_vix_spike(today)
        elif checkpoint == "13:00":
            triggered, trigger_reason = await self._check_direction_reversal(today, current)
        elif checkpoint == "14:30":
            triggered, trigger_reason = await self._check_roundtrip(today)

        if not triggered:
            logger.debug(
                "No re-classification trigger at %s: %s",
                checkpoint, trigger_reason or "no trigger",
            )
            return None

        inputs = await self._data_collector.collect_regime_inputs()
        vix_score = self._compute_vix_score(inputs.india_vix)
        gap_score = self._compute_gap_score(inputs.nifty_gap_pct)
        range_score = self._compute_range_score(inputs.nifty_first_15_range_pct)
        alignment = self._compute_alignment(
            inputs.nifty_gap_pct,
            inputs.nifty_first_15_direction,
            inputs.sgx_direction,
            inputs.sp500_change_pct,
        )

        new_classification = self._classify_from_scores(
            vix_score, gap_score, range_score, alignment, inputs,
            is_reclassification=True,
            previous_regime=current.regime,
        )

        # Enforce severity-only upgrades
        current_severity = _SEVERITY_ORDER.get(current.regime, 0)
        new_severity = _SEVERITY_ORDER.get(new_classification.regime, 0)
        if new_severity <= current_severity:
            logger.info(
                "Re-classification blocked: %s -> %s (severity downgrade not allowed)",
                current.regime, new_classification.regime,
            )
            return None

        self._cache[today] = new_classification
        self._reclass_count[today] = count + 1

        try:
            await self._regime_repo.insert_classification(new_classification)
        except Exception:
            logger.exception("Failed to persist re-classification")

        logger.info(
            "Re-classified at %s: %s -> %s (reason: %s)",
            checkpoint, current.regime, new_classification.regime, trigger_reason,
        )
        return new_classification

    def apply_override(self, regime: str) -> RegimeClassification:
        """Apply a manual regime override with confidence=1.0."""
        today = datetime.now(IST).date()
        current = self._cache.get(today)

        modifiers = self._get_regime_modifiers(regime, 1.0)
        classification = RegimeClassification(
            regime=regime,
            confidence=1.0,
            trending_score=current.trending_score if current else 0.0,
            ranging_score=current.ranging_score if current else 0.0,
            volatile_score=current.volatile_score if current else 0.0,
            india_vix=current.india_vix if current else None,
            nifty_gap_pct=current.nifty_gap_pct if current else None,
            nifty_first_15_range_pct=current.nifty_first_15_range_pct if current else None,
            nifty_first_15_direction=current.nifty_first_15_direction if current else None,
            directional_alignment=current.directional_alignment if current else None,
            sp500_change_pct=current.sp500_change_pct if current else None,
            sgx_direction=current.sgx_direction if current else None,
            fii_net_crores=current.fii_net_crores if current else None,
            dii_net_crores=current.dii_net_crores if current else None,
            prev_day_range_pct=current.prev_day_range_pct if current else None,
            strategy_weights=modifiers["strategy_weights"],
            min_star_rating=modifiers["min_star_rating"],
            max_positions=modifiers["max_positions"],
            position_size_modifier=modifiers["position_size_modifier"],
            is_reclassification=False,
            previous_regime=current.regime if current else None,
            classified_at=datetime.now(IST),
        )

        self._cache[today] = classification
        logger.info("Regime manually overridden to %s", regime)
        return classification

    def reset_daily(self) -> None:
        """Reset daily state at session start."""
        today = datetime.now(IST).date()
        self._reclass_count[today] = 0
        logger.debug("Regime daily state reset")

    # -- Internal scoring methods --

    @staticmethod
    def _compute_vix_score(vix: float | None) -> float:
        """Map VIX level to score in [-0.5, 1.0]."""
        if vix is None:
            return 0.0
        if vix < 12:
            return -0.5
        if vix < 14:
            return 0.0
        if vix < 18:
            return 0.3
        if vix < 22:
            return 0.6
        return 1.0

    @staticmethod
    def _compute_gap_score(nifty_gap_pct: float | None) -> float:
        """Map Nifty gap percentage to score in [-0.5, 1.0]."""
        if nifty_gap_pct is None:
            return 0.0
        abs_gap = abs(nifty_gap_pct)
        if abs_gap > 1.5:
            return 1.0
        if abs_gap > 0.8:
            return 0.6
        if abs_gap > 0.3:
            return 0.2
        return -0.5

    @staticmethod
    def _compute_range_score(first_15_range_pct: float | None) -> float:
        """Map first-15-min range percentage to score in [-0.5, 1.0]."""
        if first_15_range_pct is None:
            return 0.0
        if first_15_range_pct > 1.0:
            return 1.0
        if first_15_range_pct > 0.5:
            return 0.5
        if first_15_range_pct > 0.2:
            return 0.0
        return -0.5

    @staticmethod
    def _compute_alignment(
        nifty_gap_pct: float | None,
        first_15_direction: str | None,
        sgx_direction: str | None,
        sp500_change_pct: float | None,
    ) -> float:
        """Compute directional alignment score in [0.0, 1.0]."""
        directions = []

        if nifty_gap_pct is not None and nifty_gap_pct > 0.3:
            directions.append(1)
        elif nifty_gap_pct is not None and nifty_gap_pct < -0.3:
            directions.append(-1)
        else:
            directions.append(0)

        if first_15_direction == "UP":
            directions.append(1)
        elif first_15_direction == "DOWN":
            directions.append(-1)
        else:
            directions.append(0)

        if sgx_direction == "UP":
            directions.append(1)
        elif sgx_direction == "DOWN":
            directions.append(-1)
        else:
            directions.append(0)

        if sp500_change_pct is not None and sp500_change_pct > 0.3:
            directions.append(1)
        elif sp500_change_pct is not None and sp500_change_pct < -0.3:
            directions.append(-1)
        else:
            directions.append(0)

        return abs(sum(directions)) / 4

    def _classify_from_scores(
        self,
        vix_score: float,
        gap_score: float,
        range_score: float,
        alignment: float,
        inputs: RegimeInputs,
        is_reclassification: bool = False,
        previous_regime: str | None = None,
    ) -> RegimeClassification:
        """Compute composite regime scores and select the winner."""
        trending_score = (
            (gap_score * 0.35)
            + (alignment * 0.30)
            + (range_score * 0.20)
            + ((1 - vix_score) * 0.15)
        )
        ranging_score = (
            ((-gap_score) * 0.35)
            + ((-range_score) * 0.30)
            + ((1 - vix_score) * 0.35)
        )
        volatile_score = (
            (vix_score * 0.40)
            + (range_score * 0.30)
            + ((1 - alignment) * 0.30)
        )

        scores = {
            "TRENDING": trending_score,
            "RANGING": ranging_score,
            "VOLATILE": volatile_score,
        }
        regime = max(scores, key=scores.get)

        total_abs = sum(abs(v) for v in scores.values())
        if total_abs > 0:
            confidence = max(0.0, min(1.0, scores[regime] / total_abs))
        else:
            confidence = 0.33

        modifiers = self._get_regime_modifiers(regime, confidence)

        return RegimeClassification(
            regime=regime,
            confidence=confidence,
            trending_score=trending_score,
            ranging_score=ranging_score,
            volatile_score=volatile_score,
            india_vix=inputs.india_vix,
            nifty_gap_pct=inputs.nifty_gap_pct,
            nifty_first_15_range_pct=inputs.nifty_first_15_range_pct,
            nifty_first_15_direction=inputs.nifty_first_15_direction,
            directional_alignment=alignment,
            sp500_change_pct=inputs.sp500_change_pct,
            sgx_direction=inputs.sgx_direction,
            fii_net_crores=inputs.fii_net_crores,
            dii_net_crores=inputs.dii_net_crores,
            prev_day_range_pct=inputs.prev_day_range_pct,
            strategy_weights=modifiers["strategy_weights"],
            min_star_rating=modifiers["min_star_rating"],
            max_positions=modifiers["max_positions"],
            position_size_modifier=modifiers["position_size_modifier"],
            is_reclassification=is_reclassification,
            previous_regime=previous_regime,
            classified_at=datetime.now(IST),
        )

    def _get_regime_modifiers(self, regime: str, confidence: float) -> dict:
        """Derive strategy weights, min stars, position modifier, max positions."""
        threshold = getattr(self._config, "regime_confidence_threshold", 0.55)
        is_high = confidence >= threshold

        _d_t_h = '{"gap_go": 45, "orb": 35, "vwap": 20}'
        _d_t_l = '{"gap_go": 38, "orb": 35, "vwap": 27}'
        _d_r_h = '{"gap_go": 20, "orb": 30, "vwap": 50}'
        _d_r_l = '{"gap_go": 28, "orb": 33, "vwap": 39}'
        _d_v_h = '{"gap_go": 25, "orb": 25, "vwap": 25}'
        _d_v_l = '{"gap_go": 30, "orb": 30, "vwap": 30}'

        if regime == "TRENDING":
            w_high = getattr(self._config, "regime_trending_weights_high", _d_t_h)
            w_low = getattr(self._config, "regime_trending_weights_low", _d_t_l)
            weights_json = w_high if is_high else w_low
            min_stars = getattr(self._config, "regime_trending_min_stars", 3)
            modifier = getattr(self._config, "regime_trending_position_modifier", 1.0)
            max_pos = getattr(self._config, "regime_trending_max_positions", 8)
        elif regime == "RANGING":
            w_high = getattr(self._config, "regime_ranging_weights_high", _d_r_h)
            w_low = getattr(self._config, "regime_ranging_weights_low", _d_r_l)
            weights_json = w_high if is_high else w_low
            min_stars = (
                getattr(self._config, "regime_ranging_high_min_stars", 3)
                if is_high else
                getattr(self._config, "regime_ranging_low_min_stars", 4)
            )
            modifier = getattr(self._config, "regime_ranging_position_modifier", 0.85)
            max_pos = getattr(self._config, "regime_ranging_max_positions", 6)
        elif regime == "VOLATILE":
            w_high = getattr(self._config, "regime_volatile_weights_high", _d_v_h)
            w_low = getattr(self._config, "regime_volatile_weights_low", _d_v_l)
            weights_json = w_high if is_high else w_low
            min_stars = (
                getattr(self._config, "regime_volatile_high_min_stars", 5)
                if is_high else
                getattr(self._config, "regime_volatile_low_min_stars", 4)
            )
            modifier = getattr(self._config, "regime_volatile_position_modifier", 0.65)
            max_pos = getattr(self._config, "regime_volatile_max_positions", 4)
        else:
            return {
                "strategy_weights": {"gap_go": 33, "orb": 33, "vwap": 34},
                "min_star_rating": 3,
                "position_size_modifier": 1.0,
                "max_positions": None,
            }

        try:
            weights = json.loads(weights_json) if isinstance(weights_json, str) else weights_json
        except (json.JSONDecodeError, TypeError):
            weights = {"gap_go": 33, "orb": 33, "vwap": 34}

        return {
            "strategy_weights": weights,
            "min_star_rating": min_stars,
            "position_size_modifier": modifier,
            "max_positions": max_pos,
        }

    # -- Re-classification trigger checks --

    async def _check_vix_spike(self, today: date) -> tuple[bool, str]:
        """Check if VIX spiked >15% from morning value."""
        morning_vix = self._morning_vix.get(today)
        if morning_vix is None:
            return False, "No morning VIX reference"
        try:
            current_vix = await self._data_collector.fetch_current_vix()
            if current_vix is None:
                return False, "Current VIX unavailable"
            spike_threshold = getattr(self._config, "regime_vix_spike_threshold", 0.15)
            change_pct = (current_vix - morning_vix) / morning_vix if morning_vix > 0 else 0
            if change_pct > spike_threshold:
                return True, f"VIX spiked {change_pct:.1%} ({morning_vix:.1f} -> {current_vix:.1f})"
            return False, f"VIX change {change_pct:.1%} below threshold {spike_threshold:.0%}"
        except Exception:
            logger.warning("VIX spike check failed")
            return False, "VIX check failed"

    async def _check_direction_reversal(
        self, today: date, current: RegimeClassification,
    ) -> tuple[bool, str]:
        """Check if Nifty reversed direction from morning classification."""
        try:
            nifty_data = await self._data_collector.get_current_nifty_data()
            if not nifty_data:
                return False, "Nifty data unavailable"
            ltp = nifty_data.get("ltp")
            open_price = nifty_data.get("open")
            if ltp is None or open_price is None or open_price == 0:
                return False, "Missing price data"
            morning_direction = current.nifty_first_15_direction
            current_direction = "UP" if ltp > open_price else "DOWN" if ltp < open_price else "FLAT"
            if morning_direction in ("UP", "DOWN") and current_direction != morning_direction:
                change_pct = (ltp - open_price) / open_price * 100
                return True, (
                    f"Direction reversed: {morning_direction}"
                    f" -> {current_direction} ({change_pct:+.2f}%)"
                )
            return False, "No direction reversal"
        except Exception:
            logger.warning("Direction reversal check failed")
            return False, "Direction check failed"

    async def _check_roundtrip(self, today: date) -> tuple[bool, str]:
        """Check if Nifty is within 0.3% of open (round-trip)."""
        try:
            nifty_data = await self._data_collector.get_current_nifty_data()
            if not nifty_data:
                return False, "Nifty data unavailable"
            ltp = nifty_data.get("ltp")
            open_price = nifty_data.get("open")
            if ltp is None or open_price is None or open_price == 0:
                return False, "Missing price data"
            roundtrip_threshold = getattr(self._config, "regime_roundtrip_threshold", 0.003)
            distance = abs(ltp - open_price) / open_price
            if distance <= roundtrip_threshold:
                return True, (
                    f"Round-trip detected: {distance:.4f}"
                    f" within {roundtrip_threshold:.4f} threshold"
                )
            return False, f"Distance from open: {distance:.4f}"
        except Exception:
            logger.warning("Round-trip check failed")
            return False, "Round-trip check failed"
