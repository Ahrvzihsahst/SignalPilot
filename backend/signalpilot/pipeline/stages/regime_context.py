"""RegimeContextStage: Read cached regime and set modifiers on ScanContext."""

from __future__ import annotations

import logging

from signalpilot.pipeline.context import ScanContext

logger = logging.getLogger(__name__)


class RegimeContextStage:
    """Read cached regime classification and set modifiers on ScanContext.

    Position: After CircuitBreakerGateStage (1), before StrategyEvalStage (3).

    This stage reads the in-memory cache from MarketRegimeClassifier.
    If no classification exists yet (before 9:30 AM), it sets DEFAULT
    values (all neutral). In shadow mode, it sets regime and confidence
    for logging but leaves all modifier fields at their neutral defaults.

    Cost: <1ms per cycle (dict lookup + 6 attribute assignments).
    """

    def __init__(self, regime_classifier, config) -> None:
        self._classifier = regime_classifier  # MarketRegimeClassifier
        self._config = config  # AppConfig

    @property
    def name(self) -> str:
        return "RegimeContext"

    async def process(self, ctx: ScanContext) -> ScanContext:
        # Kill switch: if regime detection is disabled or classifier not configured
        if self._classifier is None:
            return ctx
        if not getattr(self._config, "regime_enabled", True):
            return ctx

        # Read cached regime (O(1) dict lookup)
        classification = self._classifier.get_cached_regime()

        if classification is None:
            # No classification yet (before 9:30 AM) -- use DEFAULT values
            return ctx

        # Set regime identification fields (always set, even in shadow mode)
        ctx.regime = classification.regime
        ctx.regime_confidence = classification.confidence

        # In shadow mode: classify and log, but do not apply modifiers
        if getattr(self._config, "regime_shadow_mode", False):
            logger.debug(
                "Shadow mode: regime=%s confidence=%.2f (modifiers not applied)",
                classification.regime,
                classification.confidence,
            )
            return ctx

        # Apply regime modifiers to context
        ctx.regime_min_stars = classification.min_star_rating
        ctx.regime_position_modifier = classification.position_size_modifier
        ctx.regime_max_positions = classification.max_positions
        ctx.regime_strategy_weights = classification.strategy_weights

        return ctx
